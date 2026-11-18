"""Schema detector for format-agnostic bank statement CSV files.

Identifies the transaction table header row by skipping bank preambles and maps
various bank-specific column names (HDFC, SBI, ICICI, Axis, etc.) to canonical fields.
"""

from dataclasses import dataclass
import re
from typing import List, Optional, Tuple


@dataclass
class ColumnMapping:
    """Represents mapped canonical column names for a detected bank statement."""

    date_col: Optional[str] = None
    desc_col: Optional[str] = None
    debit_col: Optional[str] = None
    credit_col: Optional[str] = None
    amount_col: Optional[str] = None
    direction_col: Optional[str] = None
    balance_col: Optional[str] = None
    ref_col: Optional[str] = None
    header_row_index: int = 0
    confidence_score: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Check whether the minimum required columns are mapped."""
        has_date = self.date_col is not None
        has_desc = self.desc_col is not None
        has_amounts = (self.debit_col is not None and self.credit_col is not None) or (
            self.amount_col is not None
        )
        return has_date and has_desc and has_amounts


# Standard aliases for Indian bank statement columns
COLUMN_ALIASES = {
    "date": [
        "date", "txn date", "transaction date", "value date", "posting date",
        "trans date", "date of txn", "txn_date", "trans_date", "txndate",
        "transactiondate", "txndt"
    ],
    "desc": [
        "narration", "description", "particulars", "remarks", "transaction details",
        "details", "transaction remarks", "payee", "merchant", "narrative"
    ],
    "debit": [
        "withdrawal", "withdrawal amt", "withdrawal amt.", "withdrawal amount",
        "debit", "dr", "debit amount", "dr amount", "withdrawals", "debit (inr)",
        "withdrawal (inr)", "dr."
    ],
    "credit": [
        "deposit", "deposit amt", "deposit amt.", "deposit amount",
        "credit", "cr", "credit amount", "cr amount", "deposits", "credit (inr)",
        "deposit (inr)", "cr."
    ],
    "amount": [
        "amount", "txn amount", "transaction amount", "amt", "total amount",
        "amount (inr)"
    ],
    "direction": [
        "type", "dr/cr", "cr/dr", "transaction type", "dr_cr", "cr_dr",
        "type (dr/cr)", "indicator"
    ],
    "balance": [
        "balance", "closing balance", "avail bal", "available balance",
        "account balance", "balance (inr)", "closing bal"
    ],
    "ref": [
        "chq/ref no", "chq/ref no.", "ref no", "ref no.", "reference no",
        "cheque no", "utr", "transaction id", "ref no./cheque no.", "txn id"
    ],
}


def _clean_header_text(text: str) -> str:
    """Normalize a header string for alias comparison."""
    if not isinstance(text, str):
        return ""
    # Split camelCase e.g. TxnDate -> Txn Date
    split_case = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text))
    cleaned = split_case.lower().strip()
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def find_header_row(sample_rows: List[List[str]]) -> Tuple[int, List[str]]:
    """Scan the first N rows of a CSV to identify the table header row.

    Bank statements often contain 5-15 rows of account information, address,
    and blank lines before the actual transaction columns appear.

    Args:
        sample_rows: List of string rows from the beginning of the CSV.

    Returns:
        Tuple[int, List[str]]: Index of header row and list of header names.
    """
    best_row_idx = 0
    best_score = -1
    best_headers = []

    for idx, row in enumerate(sample_rows[:30]):
        # Count non-empty cells
        cleaned_cells = [_clean_header_text(c) for c in row if str(c).strip()]
        if len(cleaned_cells) < 3:
            continue

        score = 0
        matched_categories = set()

        for cell in cleaned_cells:
            for category, aliases in COLUMN_ALIASES.items():
                if category in matched_categories:
                    continue
                for alias in aliases:
                    if cell == alias or cell.startswith(alias):
                        score += 2
                        matched_categories.add(category)
                        break

        # A valid header must at least match date or narration plus an amount
        if ("date" in matched_categories or "desc" in matched_categories) and (
            "debit" in matched_categories or "credit" in matched_categories or "amount" in matched_categories
        ):
            score += 5

        if score > best_score:
            best_score = score
            best_row_idx = idx
            best_headers = [str(c).strip() for c in row]

    return best_row_idx, best_headers


def detect_column_mapping(headers: List[str], header_row_index: int = 0) -> ColumnMapping:
    """Map detected raw header columns to canonical transaction fields.

    Args:
        headers: List of column names found in the header row.
        header_row_index: 0-based row index where headers were found.

    Returns:
        ColumnMapping: Detected mapping with confidence score.
    """
    mapping = ColumnMapping(header_row_index=header_row_index)
    matched_categories = set()
    total_expected = 4  # date, desc, debit, credit (or amount)

    for header in headers:
        cleaned = _clean_header_text(header)
        if not cleaned:
            continue

        # Match Date
        if "date" not in matched_categories:
            for alias in COLUMN_ALIASES["date"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.date_col = header
                    matched_categories.add("date")
                    break

        # Match Description / Narration
        if "desc" not in matched_categories:
            for alias in COLUMN_ALIASES["desc"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.desc_col = header
                    matched_categories.add("desc")
                    break

        # Match Debit
        if "debit" not in matched_categories:
            for alias in COLUMN_ALIASES["debit"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.debit_col = header
                    matched_categories.add("debit")
                    break

        # Match Credit
        if "credit" not in matched_categories:
            for alias in COLUMN_ALIASES["credit"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.credit_col = header
                    matched_categories.add("credit")
                    break

        # Match Single Amount
        if "amount" not in matched_categories and "debit" not in matched_categories:
            for alias in COLUMN_ALIASES["amount"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.amount_col = header
                    matched_categories.add("amount")
                    break

        # Match Direction / Type
        if "direction" not in matched_categories:
            for alias in COLUMN_ALIASES["direction"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.direction_col = header
                    matched_categories.add("direction")
                    break

        # Match Balance
        if "balance" not in matched_categories:
            for alias in COLUMN_ALIASES["balance"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.balance_col = header
                    matched_categories.add("balance")
                    break

        # Match Reference / UTR
        if "ref" not in matched_categories:
            for alias in COLUMN_ALIASES["ref"]:
                if cleaned == alias or cleaned.startswith(alias):
                    mapping.ref_col = header
                    matched_categories.add("ref")
                    break

    # Calculate confidence score
    matches = 0
    if mapping.date_col:
        matches += 1
    if mapping.desc_col:
        matches += 1
    if mapping.debit_col and mapping.credit_col:
        matches += 2
    elif mapping.amount_col:
        matches += 1.5

    mapping.confidence_score = min(1.0, matches / total_expected)
    return mapping
