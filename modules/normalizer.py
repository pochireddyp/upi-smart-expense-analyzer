"""Transaction normalization and sanitization utilities.

Provides backwards-compatible interfaces for merchant cleaning, category inference,
and sensitive number masking, backed by the Phase 9 categorizer engine.
"""

from typing import Dict, List
from modules.categorizer import (
    BRAND_CATALOG,
    CATEGORY_TAXONOMY,
    clean_merchant_advanced,
    categorize_transaction,
    mask_sensitive_account_numbers,
)

# Standard keyword taxonomy preserved for backward compatibility
CATEGORY_KEYWORDS = {
    "Food & Dining": [
        "swiggy", "zomato", "chai", "tea", "mcdonald", "burger", "cafe",
        "starbucks", "restaurant", "pizza", "bakery", "subway", "kfc",
        "eats", "diner", "coffee", "dhaba"
    ],
    "Groceries & Essentials": [
        "zepto", "blinkit", "instamart", "bigbasket", "dmart", "supermarket",
        "grocery", "nature basket", "spencer", "reliance fresh", "more retail"
    ],
    "Commute & Travel": [
        "uber", "ola", "rapido", "metro", "petrol", "fuel", "shell", "hpcl",
        "bpcl", "ioc", "irctc", "railway", "indigo", "air india", "toll",
        "fastag"
    ],
    "Utilities & Bills": [
        "bescom", "airtel", "jio", "vodafone", "vi", "electricity", "broadband",
        "act", "billdesk", "recharge", "tata power", "gas", "water board",
        "dth", "tatasky"
    ],
    "Shopping & E-Com": [
        "amazon", "flipkart", "myntra", "meesho", "ajio", "zara", "retail",
        "croma", "reliancedigital", "nykaa", "lenskart", "decathlon"
    ],
    "Entertainment & Subs": [
        "netflix", "spotify", "hotstar", "prime", "youtube", "bookmyshow",
        "cinema", "pvr", "inox", "multiplex", "apple.com/bill", "playstore"
    ],
    "Health & Medical": [
        "apollo", "pharmacy", "medplus", "1mg", "practo", "hospital",
        "clinic", "dental", "diagnostic", "pathology", "dr."
    ],
    "Salary & Income": [
        "salary", "payroll", "dividend", "interest", "corp salary",
        "techcorp", "inward remittance"
    ],
    "Peer Transfers": [
        "transfer to", "trans to", "p2p", "split", "reimbursement",
        "upi/p2a", "friend"
    ],
}


def clean_merchant_name(narration: str) -> str:
    """Extract a concise, human-readable merchant title from a raw bank narration string."""
    return clean_merchant_advanced(narration)


def infer_category(narration: str, txn_type: str) -> str:
    """Assign a spending category based on narration keywords and transaction direction."""
    res = categorize_transaction(narration, txn_type)
    return res.category


def infer_mode(narration: str) -> str:
    """Determine the payment channel from narration markers."""
    res = categorize_transaction(narration, "DEBIT")
    return res.mode
