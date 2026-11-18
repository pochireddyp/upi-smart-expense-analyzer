"""CSV statement parsing, normalization, and validation engine.

Reads bank statement CSVs, automatically bypasses preamble metadata,
maps columns, normalizes dates and Decimal amounts, applies heuristic UPI
categorization, and handles encoding/delimiter variances.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import io
import re
from typing import BinaryIO, List, Optional, Tuple, Union

from dateutil import parser as date_parser
import pandas as pd

from modules.money import to_money
from modules.normalizer import (
    CATEGORY_KEYWORDS,
    clean_merchant_name,
    infer_category,
    infer_mode,
    mask_sensitive_account_numbers,
)
from modules.schema_detector import ColumnMapping, detect_column_mapping, find_header_row

# Aliases for internal backward compatibility
_clean_merchant_name = clean_merchant_name
_infer_category = infer_category
_infer_mode = infer_mode
_mask_sensitive_account_numbers = mask_sensitive_account_numbers


@dataclass
class CSVParseResult:
    """Encapsulates the output of a CSV statement parsing operation."""

    success: bool
    df: Optional[pd.DataFrame] = None
    mapping: Optional[ColumnMapping] = None
    total_raw_rows: int = 0
    valid_rows: int = 0
    skipped_rows: int = 0
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


def _decode_csv_content(file_bytes: bytes) -> Tuple[str, str]:
    """Try common encodings to decode raw CSV bytes.

    Returns:
        Tuple[str, str]: (Decoded text content, Successful encoding name)
    """
    encodings_to_try = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    for enc in encodings_to_try:
        try:
            decoded = file_bytes.decode(enc)
            return decoded, enc
        except UnicodeDecodeError:
            continue

    # Fallback with replacement
    return file_bytes.decode("utf-8", errors="replace"), "utf-8"


def parse_csv_statement(
    file_input: Union[bytes, BinaryIO, str],
    custom_mapping: Optional[ColumnMapping] = None
) -> CSVParseResult:
    """Parse, clean, and validate a bank statement CSV into a standardized DataFrame.

    Args:
        file_input: Raw bytes, file buffer, or string path.
        custom_mapping: Optional manual ColumnMapping if pre-confirmed by the user.

    Returns:
        CSVParseResult: Dataframe and parsing metadata.
    """
    # 1. Read raw bytes
    if isinstance(file_input, bytes):
        raw_bytes = file_input
    elif hasattr(file_input, "read"):
        raw_bytes = file_input.read()
        if hasattr(file_input, "seek"):
            file_input.seek(0)
    elif isinstance(file_input, str):
        with open(file_input, "rb") as f:
            raw_bytes = f.read()
    else:
        return CSVParseResult(success=False, error_message="Invalid file input type.")

    if not raw_bytes.strip():
        return CSVParseResult(success=False, error_message="The uploaded CSV file is completely empty.")

    # 2. Decode text & sniff delimiter
    text_content, _ = _decode_csv_content(raw_bytes)
    lines = [line.strip() for line in text_content.splitlines() if line.strip()]

    if not lines:
        return CSVParseResult(success=False, error_message="No readable data lines found in file.")

    # Determine delimiter
    first_sample = "\n".join(lines[:20])
    delimiter = ";" if first_sample.count(";") > first_sample.count(",") else ","

    # 3. Detect Header Row & Column Schema
    sample_rows = [line.split(delimiter) for line in lines[:30]]
    header_idx, headers = find_header_row(sample_rows)

    mapping = custom_mapping or detect_column_mapping(headers, header_row_index=header_idx)

    if not mapping.is_valid:
        return CSVParseResult(
            success=False,
            mapping=mapping,
            error_message=(
                f"Could not automatically identify required transaction columns. "
                f"Detected headers: {', '.join(headers[:6])}. "
                f"Missing date, narration, or debit/credit columns."
            ),
        )

    # 4. Load with Pandas skipping preamble lines
    try:
        csv_buffer = io.StringIO(text_content)
        df_raw = pd.read_csv(
            csv_buffer,
            skiprows=mapping.header_row_index,
            sep=delimiter,
            dtype=str,
            on_bad_lines="skip"
        )
    except Exception as exc:
        return CSVParseResult(
            success=False,
            error_message=f"Failed to read CSV table structure: {str(exc)}"
        )

    # Clean raw column names to strip whitespace
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # Verify that mapped columns exist in df_raw
    for col_name in [mapping.date_col, mapping.desc_col]:
        if col_name and col_name not in df_raw.columns:
            return CSVParseResult(
                success=False,
                error_message=f"Expected column '{col_name}' was not found in table headers."
            )

    # 5. Normalize Rows into Canonical Format
    normalized_records = []
    warnings = []
    skipped_count = 0

    for idx, row in df_raw.iterrows():
        raw_date_str = str(row.get(mapping.date_col, "")).strip()
        raw_desc = str(row.get(mapping.desc_col, "")).strip()

        # Skip footer summary rows or empty rows
        if not raw_date_str or raw_date_str.lower() in ["nan", "none", "total", "closing balance"]:
            skipped_count += 1
            continue

        # Parse Date (Day-First preference)
        try:
            parsed_dt = date_parser.parse(raw_date_str, dayfirst=True)
            txn_date = parsed_dt.date()
        except (ValueError, OverflowError):
            warnings.append(f"Row {idx + 1}: Skipped invalid date '{raw_date_str}'.")
            skipped_count += 1
            continue

        # Parse Amounts and Direction
        txn_type = None
        txn_amount = Decimal("0.00")

        # Layout A: Separate Debit and Credit columns
        if mapping.debit_col and mapping.credit_col:
            debit_val = str(row.get(mapping.debit_col, "")).strip()
            credit_val = str(row.get(mapping.credit_col, "")).strip()

            is_debit = bool(debit_val and debit_val not in ["-", "0", "0.00", "nan", "None", ""])
            is_credit = bool(credit_val and credit_val not in ["-", "0", "0.00", "nan", "None", ""])

            if is_debit:
                try:
                    cleaned_amt = re.sub(r"[^\d.]", "", debit_val)
                    if cleaned_amt:
                        amt_dec = to_money(cleaned_amt)
                        if amt_dec > Decimal("0.00"):
                            txn_type = "DEBIT"
                            txn_amount = amt_dec
                except Exception:
                    pass

            if not txn_type and is_credit:
                try:
                    cleaned_amt = re.sub(r"[^\d.]", "", credit_val)
                    if cleaned_amt:
                        amt_dec = to_money(cleaned_amt)
                        if amt_dec > Decimal("0.00"):
                            txn_type = "CREDIT"
                            txn_amount = amt_dec
                except Exception:
                    pass

        # Layout B: Single Amount column with Direction/Type column
        elif mapping.amount_col:
            amount_val = str(row.get(mapping.amount_col, "")).strip()
            dir_val = str(row.get(mapping.direction_col, "")).strip().upper() if mapping.direction_col else ""

            try:
                # Check negative sign or parentheses
                is_negative = amount_val.startswith("-") or ("(" in amount_val and ")" in amount_val)
                cleaned_amt = re.sub(r"[^\d.]", "", amount_val)
                if cleaned_amt:
                    amt_dec = to_money(cleaned_amt)
                    if amt_dec > Decimal("0.00"):
                        if "CR" in dir_val or (not is_negative and not dir_val):
                            txn_type = "CREDIT"
                        else:
                            txn_type = "DEBIT"
                        txn_amount = amt_dec
            except Exception:
                pass

        if not txn_type or txn_amount <= Decimal("0.00"):
            skipped_count += 1
            continue

        # Mask account numbers for privacy
        sanitized_narration = _mask_sensitive_account_numbers(raw_desc)
        clean_merchant = _clean_merchant_name(raw_desc)
        category = _infer_category(raw_desc, txn_type)
        mode = _infer_mode(raw_desc)

        normalized_records.append({
            "date": txn_date,
            "merchant": clean_merchant,
            "narration": sanitized_narration,
            "category": category,
            "mode": mode,
            "type": txn_type,
            "amount": txn_amount,
        })

    if not normalized_records:
        return CSVParseResult(
            success=False,
            mapping=mapping,
            total_raw_rows=len(df_raw),
            skipped_rows=skipped_count,
            error_message="No valid transaction rows could be extracted from this statement.",
        )

    df_normalized = pd.DataFrame(normalized_records)
    df_normalized = df_normalized.sort_values(by="date", ascending=False).reset_index(drop=True)

    return CSVParseResult(
        success=True,
        df=df_normalized,
        mapping=mapping,
        total_raw_rows=len(df_raw),
        valid_rows=len(df_normalized),
        skipped_rows=skipped_count,
        warnings=warnings[:5],
    )
