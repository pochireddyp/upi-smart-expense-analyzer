"""PDF statement parsing, table extraction, and normalization engine.

Utilizes PyMuPDF (`pymupdf`) to extract digital tables from Indian bank PDF statements,
handles in-memory password decryption, detects column schemas, and normalizes
transactions into the canonical DataFrame schema with Decimal monetary amounts.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import io
import re
from typing import BinaryIO, List, Optional, Union

from dateutil import parser as date_parser
import pandas as pd
import pymupdf

from modules.money import to_money
from modules.normalizer import (
    clean_merchant_name,
    infer_category,
    infer_mode,
    mask_sensitive_account_numbers,
)
from modules.schema_detector import ColumnMapping, detect_column_mapping, find_header_row


@dataclass
class PDFParseResult:
    """Encapsulates the output of a PDF statement parsing operation."""

    success: bool
    df: Optional[pd.DataFrame] = None
    mapping: Optional[ColumnMapping] = None
    page_count: int = 0
    total_raw_rows: int = 0
    valid_rows: int = 0
    skipped_rows: int = 0
    is_encrypted: bool = False
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


def parse_pdf_statement(
    file_input: Union[bytes, BinaryIO, str],
    password: Optional[str] = None,
    custom_mapping: Optional[ColumnMapping] = None,
) -> PDFParseResult:
    """Parse, decrypt, and normalize a bank statement PDF in memory.

    Args:
        file_input: Raw bytes, file buffer, or string path to PDF.
        password: Optional password for encrypted/locked bank PDFs.
        custom_mapping: Optional manual ColumnMapping if pre-confirmed.

    Returns:
        PDFParseResult: Standardized DataFrame and extraction metadata.
    """
    # 1. Read input bytes
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
        return PDFParseResult(success=False, error_message="Invalid PDF file input type.")

    if not raw_bytes or len(raw_bytes.strip()) == 0:
        return PDFParseResult(success=False, error_message="The uploaded PDF file is completely empty.")

    # 2. Open document in memory using PyMuPDF
    try:
        doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
    except Exception:
        return PDFParseResult(
            success=False,
            error_message="Failed to open PDF document: The file is not a valid or readable digital PDF."
        )

    try:
        page_count = len(doc)
        if page_count == 0:
            return PDFParseResult(success=False, error_message="The uploaded PDF contains no pages.")

        # 3. Check & Handle Password Encryption
        if doc.is_encrypted:
            if not password:
                return PDFParseResult(
                    success=False,
                    is_encrypted=True,
                    page_count=page_count,
                    error_message=(
                        "This PDF statement is password-protected. "
                        "Please enter your statement password to unlock it."
                    ),
                )
            auth_status = doc.authenticate(password)
            if auth_status <= 0:
                return PDFParseResult(
                    success=False,
                    is_encrypted=True,
                    page_count=page_count,
                    error_message=(
                        "Incorrect password. Many banks format passwords as your DOB (DDMMYYYY) "
                        "or Customer ID / PAN."
                    ),
                )

        # 4. Check for Scanned / Image-Only PDF (Vector Text Check)
        total_text = "".join(page.get_text() for page in doc)
        if len(total_text.strip()) < 50:
            return PDFParseResult(
                success=False,
                page_count=page_count,
                error_message=(
                    "Scanned Document Detected: This PDF contains raster scanned images rather than "
                    "selectable digital text. Please download an original digital e-statement from "
                    "your bank's netbanking portal."
                ),
            )

        # 5. Extract Tabular Rows across All Pages
        all_raw_rows: List[List[str]] = []

        for page in doc:
            # Tier 1: Try PyMuPDF native table extraction
            try:
                table_finder = page.find_tables()
                if table_finder.tables:
                    for tab in table_finder:
                        extracted = tab.extract()
                        for row in extracted:
                            cleaned_cells = [str(c).strip() if c is not None else "" for c in row]
                            # Only keep non-empty rows
                            if any(cleaned_cells):
                                all_raw_rows.append(cleaned_cells)
                    continue
            except Exception:
                pass

            # Tier 2: Text block fallback (if no vector borders/tables found)
            blocks = page.get_text("blocks")
            for block in blocks:
                if block[6] == 0:  # text block
                    lines = block[4].splitlines()
                    for line in lines:
                        parts = re.split(r"\s{2,}|\t+", line.strip())
                        if len(parts) >= 3:
                            all_raw_rows.append(parts)

        if not all_raw_rows:
            return PDFParseResult(
                success=False,
                page_count=page_count,
                error_message="Could not find any structured transaction tables in this PDF.",
            )

        # 6. Locate Header Row & Detect Column Schema
        header_idx, headers = find_header_row(all_raw_rows[:35])
        mapping = custom_mapping or detect_column_mapping(headers, header_row_index=header_idx)

        if not mapping.is_valid:
            return PDFParseResult(
                success=False,
                mapping=mapping,
                page_count=page_count,
                total_raw_rows=len(all_raw_rows),
                error_message=(
                    f"Could not automatically map required transaction columns in this PDF. "
                    f"Found headers: {', '.join(headers[:6])}. "
                    f"Missing date, narration, or debit/credit columns."
                ),
            )

        # Find column indices based on header names
        date_idx = headers.index(mapping.date_col) if mapping.date_col in headers else None
        desc_idx = headers.index(mapping.desc_col) if mapping.desc_col in headers else None
        debit_idx = headers.index(mapping.debit_col) if mapping.debit_col in headers else None
        credit_idx = headers.index(mapping.credit_col) if mapping.credit_col in headers else None
        amount_idx = headers.index(mapping.amount_col) if mapping.amount_col in headers else None
        dir_idx = headers.index(mapping.direction_col) if mapping.direction_col in headers else None

        # 7. Normalize Rows into Canonical Format
        normalized_records = []
        warnings = []
        skipped_count = 0

        for r_idx, row in enumerate(all_raw_rows[header_idx + 1:], start=header_idx + 1):
            # Skip repeated header rows on multi-page statements
            if row == headers or all(c in headers for c in row if c):
                skipped_count += 1
                continue

            # Extract cell values safely by index
            date_val = row[date_idx].strip() if date_idx is not None and date_idx < len(row) else ""
            desc_val = row[desc_idx].strip() if desc_idx is not None and desc_idx < len(row) else ""

            if not date_val or date_val.lower() in ["nan", "none", "total", "closing balance"]:
                skipped_count += 1
                continue

            # Parse Date with Day-First preference
            try:
                parsed_dt = date_parser.parse(date_val, dayfirst=True)
                txn_date = parsed_dt.date()
            except (ValueError, OverflowError):
                warnings.append(f"Row {r_idx}: Skipped invalid date '{date_val}'.")
                skipped_count += 1
                continue

            # Parse Amount and Direction
            txn_type = None
            txn_amount = Decimal("0.00")

            # Layout A: Separate Debit and Credit columns
            if debit_idx is not None and credit_idx is not None:
                deb_val = row[debit_idx].strip() if debit_idx < len(row) else ""
                crd_val = row[credit_idx].strip() if credit_idx < len(row) else ""

                is_debit = bool(deb_val and deb_val not in ["-", "0", "0.00", "nan", "None", ""])
                is_credit = bool(crd_val and crd_val not in ["-", "0", "0.00", "nan", "None", ""])

                if is_debit:
                    try:
                        clean_deb = re.sub(r"[^\d.]", "", deb_val)
                        if clean_deb:
                            amt_dec = to_money(clean_deb)
                            if amt_dec > Decimal("0.00"):
                                txn_type = "DEBIT"
                                txn_amount = amt_dec
                    except Exception:
                        pass

                if not txn_type and is_credit:
                    try:
                        clean_crd = re.sub(r"[^\d.]", "", crd_val)
                        if clean_crd:
                            amt_dec = to_money(clean_crd)
                            if amt_dec > Decimal("0.00"):
                                txn_type = "CREDIT"
                                txn_amount = amt_dec
                    except Exception:
                        pass

            # Layout B: Single Amount + Type column
            elif amount_idx is not None:
                amt_str = row[amount_idx].strip() if amount_idx < len(row) else ""
                type_str = row[dir_idx].strip().upper() if dir_idx is not None and dir_idx < len(row) else ""

                try:
                    is_neg = amt_str.startswith("-") or ("(" in amt_str and ")" in amt_str)
                    clean_amt = re.sub(r"[^\d.]", "", amt_str)
                    if clean_amt:
                        amt_dec = to_money(clean_amt)
                        if amt_dec > Decimal("0.00"):
                            if "CR" in type_str or (not is_neg and not type_str):
                                txn_type = "CREDIT"
                            else:
                                txn_type = "DEBIT"
                            txn_amount = amt_dec
                except Exception:
                    pass

            if not txn_type or txn_amount <= Decimal("0.00"):
                skipped_count += 1
                continue

            # Mask account numbers, infer merchant, category, and mode
            sanitized_narration = mask_sensitive_account_numbers(desc_val)
            clean_merchant = clean_merchant_name(desc_val)
            category = infer_category(desc_val, txn_type)
            mode = infer_mode(desc_val)

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
            return PDFParseResult(
                success=False,
                mapping=mapping,
                page_count=page_count,
                total_raw_rows=len(all_raw_rows),
                skipped_rows=skipped_count,
                error_message="No valid transaction rows could be extracted from this PDF statement.",
            )

        df_normalized = pd.DataFrame(normalized_records)
        df_normalized = df_normalized.sort_values(by="date", ascending=False).reset_index(drop=True)

        return PDFParseResult(
            success=True,
            df=df_normalized,
            mapping=mapping,
            page_count=page_count,
            total_raw_rows=len(all_raw_rows),
            valid_rows=len(df_normalized),
            skipped_rows=skipped_count,
            warnings=warnings[:5],
        )

    finally:
        # Guarantee doc closure and resource cleanup
        doc.close()
