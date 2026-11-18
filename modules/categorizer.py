"""Advanced merchant extraction, transaction nature detection, and categorization engine.

Implements an explainable, multi-stage pipeline designed for Indian UPI narrations,
payment gateway unwrapping, and canonical category mapping.
"""

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Dict, List, Optional, Tuple

from modules.models import CategorizationRule


def mask_sensitive_account_numbers(text: str) -> str:
    """Mask account numbers (8 to 18 consecutive digits) for privacy."""
    if not isinstance(text, str):
        return ""
    # Mask numbers with 8-18 digits, keeping only last 4
    return re.sub(r"\b(\d{4,14})(\d{4})\b", lambda m: "••••" + m.group(2), text)


@dataclass
class CategorizationResult:
    """Detailed result of categorizing a single transaction."""

    merchant: str
    category: str
    category_id: str
    nature: str  # "payment", "refund", "reversal", "transfer", "income"
    mode: str  # "UPI", "IMPS", "NEFT", "Debit Card", "Autopay", "Online"
    confidence: float  # 0.0 to 1.0
    rule_matched: str  # Description of rule that triggered the match


# Standard Seeded Categories
CATEGORY_TAXONOMY: Dict[str, Tuple[str, str]] = {
    # category_id -> (Human readable name, Macro kind: need / want / saving / income / internal)
    "food_dining": ("Food & Dining", "want"),
    "groceries": ("Groceries & Essentials", "need"),
    "commute": ("Commute & Travel", "need"),
    "utilities": ("Utilities & Bills", "need"),
    "shopping": ("Shopping & E-Com", "want"),
    "entertainment": ("Entertainment & Subs", "want"),
    "health": ("Health & Medical", "need"),
    "housing": ("Rent & Housing", "need"),
    "salary": ("Salary & Income", "income"),
    "transfers": ("Peer Transfers", "internal"),
    "others": ("Others & Misc", "want"),
}

CATEGORY_NAME_TO_ID: Dict[str, str] = {
    name: cid for cid, (name, _) in CATEGORY_TAXONOMY.items()
}

# Known Payment Gateway & Aggregator Prefixes to strip
GATEWAY_PREFIX_PATTERN = re.compile(
    r"^(?:RAZORPAY\*?|BILLDESK\*?|PAYU\*?|CASHFREE\*?|PAYTM QR\*?|AMZN MKTP\*?|CCAVENUE\*?|PINELABS\*?|EASEBUZZ\*?)\s*",
    re.IGNORECASE,
)

# Known Brand Dictionary for Indian UPI Ecosystem
BRAND_CATALOG: Dict[str, Tuple[str, str]] = {
    # Brand Key (lowercase) -> (Canonical Display Name, category_id)
    # Food & Dining
    "swiggy": ("Swiggy", "food_dining"),
    "zomato": ("Zomato", "food_dining"),
    "mcdonald": ("McDonald's", "food_dining"),
    "starbucks": ("Starbucks", "food_dining"),
    "domino": ("Domino's Pizza", "food_dining"),
    "pizza hut": ("Pizza Hut", "food_dining"),
    "burger king": ("Burger King", "food_dining"),
    "kfc": ("KFC", "food_dining"),
    "subway": ("Subway", "food_dining"),
    "chai point": ("Chai Point", "food_dining"),
    "chaayos": ("Chaayos", "food_dining"),
    "blue tokai": ("Blue Tokai", "food_dining"),
    "third wave": ("Third Wave Coffee", "food_dining"),
    "eatclub": ("EatClub", "food_dining"),
    "box8": ("Box8", "food_dining"),
    "freshmenu": ("FreshMenu", "food_dining"),
    # Groceries
    "blinkit": ("Blinkit", "groceries"),
    "zepto": ("Zepto", "groceries"),
    "instamart": ("Swiggy Instamart", "groceries"),
    "bigbasket": ("BigBasket", "groceries"),
    "bbdaily": ("BB Daily", "groceries"),
    "dmart": ("DMart", "groceries"),
    "nature basket": ("Nature's Basket", "groceries"),
    "spencer": ("Spencer's", "groceries"),
    "reliance fresh": ("Reliance Fresh", "groceries"),
    "more retail": ("More Retail", "groceries"),
    "milkbasket": ("Milk Basket", "groceries"),
    "country delight": ("Country Delight", "groceries"),
    # Commute & Travel
    "uber": ("Uber", "commute"),
    "ola": ("Ola Cabs", "commute"),
    "rapido": ("Rapido", "commute"),
    "namma yatri": ("Namma Yatri", "commute"),
    "irctc": ("IRCTC", "commute"),
    "makemytrip": ("MakeMyTrip", "commute"),
    "cleartrip": ("Cleartrip", "commute"),
    "indigo": ("IndiGo", "commute"),
    "air india": ("Air India", "commute"),
    "fastag": ("FASTag Toll", "commute"),
    "iocl": ("Indian Oil (IOCL)", "commute"),
    "bpcl": ("Bharat Petroleum (BPCL)", "commute"),
    "hpcl": ("Hindustan Petroleum (HPCL)", "commute"),
    "shell": ("Shell Fuel", "commute"),
    # Utilities & Bills
    "bescom": ("BESCOM Electricity", "utilities"),
    "tata power": ("Tata Power", "utilities"),
    "adani electricity": ("Adani Electricity", "utilities"),
    "airtel": ("Airtel", "utilities"),
    "jio": ("Jio Telecom", "utilities"),
    "vodafone": ("Vi (Vodafone Idea)", "utilities"),
    "vi bill": ("Vi (Vodafone Idea)", "utilities"),
    "act fibernet": ("ACT Fibernet", "utilities"),
    "hathway": ("Hathway", "utilities"),
    "tatasky": ("Tata Play", "utilities"),
    "tata play": ("Tata Play", "utilities"),
    "billdesk": ("BillDesk Utility", "utilities"),
    # Shopping & E-Com
    "amazon": ("Amazon", "shopping"),
    "amzn": ("Amazon", "shopping"),
    "flipkart": ("Flipkart", "shopping"),
    "myntra": ("Myntra", "shopping"),
    "meesho": ("Meesho", "shopping"),
    "ajio": ("Ajio", "shopping"),
    "nykaa": ("Nykaa", "shopping"),
    "lenskart": ("Lenskart", "shopping"),
    "decathlon": ("Decathlon", "shopping"),
    "croma": ("Croma", "shopping"),
    "reliance digital": ("Reliance Digital", "shopping"),
    "zara": ("Zara", "shopping"),
    "h&m": ("H&M", "shopping"),
    "uniqlo": ("Uniqlo", "shopping"),
    # Entertainment & Subs
    "netflix": ("Netflix", "entertainment"),
    "spotify": ("Spotify", "entertainment"),
    "hotstar": ("Disney+ Hotstar", "entertainment"),
    "prime video": ("Prime Video", "entertainment"),
    "youtube": ("YouTube Premium", "entertainment"),
    "bookmyshow": ("BookMyShow", "entertainment"),
    "pvr": ("PVR Cinemas", "entertainment"),
    "inox": ("INOX Cinemas", "entertainment"),
    "sony liv": ("Sony LIV", "entertainment"),
    "zee5": ("Zee5", "entertainment"),
    "apple.com/bill": ("Apple Services", "entertainment"),
    "google play": ("Google Play", "entertainment"),
    # Health & Medical
    "apollo": ("Apollo Pharmacy", "health"),
    "medplus": ("MedPlus", "health"),
    "1mg": ("Tata 1mg", "health"),
    "pharmeasy": ("PharmEasy", "health"),
    "practo": ("Practo", "health"),
    "netmeds": ("Netmeds", "health"),
    "dr lal": ("Dr Lal PathLabs", "health"),
    "cult.fit": ("Cult.fit Gym", "health"),
    # Rent & Housing
    "nobroker": ("NoBroker", "housing"),
    "mygate": ("MyGate Society", "housing"),
    "society maintenance": ("Society Maintenance", "housing"),
}

# Broad category keyword markers for fallback classification
KEYWORD_TAXONOMY: Dict[str, List[str]] = {
    "food_dining": [
        "restaurant", "cafe", "coffee", "dhaba", "diner", "tea stall", "chai",
        "bakery", "sweets", "bakes", "kitchen", "biryani", "eatery", "tiffin",
        "barbeque", "canteen", "eats"
    ],
    "groceries": [
        "supermarket", "provision", "kirana", "hypermarket", "organic", "mart",
        "fruits", "vegetables", "dairy", "bakery & grocery"
    ],
    "commute": [
        "petrol", "diesel", "fuel", "cng", "parking", "toll", "metro rail",
        "railway", "bus", "transport", "cab", "auto"
    ],
    "utilities": [
        "electricity", "broadband", "water board", "gas", "recharge", "dth",
        "bill payment", "postpaid", "prepaid"
    ],
    "shopping": [
        "retail", "clothing", "apparel", "footwear", "fashion", "electronics",
        "boutique", "garments", "stationery"
    ],
    "entertainment": [
        "cinema", "theatre", "multiplex", "amusement", "gaming", "subscription",
        "streaming", "music"
    ],
    "health": [
        "pharmacy", "medical", "clinic", "hospital", "diagnostic", "dental",
        "pathology", "optical", "healthcare", "chemist"
    ],
    "housing": [
        "rent", "maintenance", "landlord", "flat", "apartment maintenance"
    ],
    "salary": [
        "salary", "payroll", "dividend", "interest credit", "corp salary",
        "monthly salary", "stipend"
    ],
    "transfers": [
        "transfer to", "trans to", "p2p", "split", "reimbursement", "self transfer",
        "to savings", "from savings", "credit card payment", "cred", "cheq"
    ],
}


def clean_merchant_advanced(narration: str) -> str:
    """Extract a clean, human-readable merchant title from messy bank narration.

    Strips payment gateway prefixes, UPI protocol tokens, terminal IDs, and
    location artifacts.

    Args:
        narration: Raw bank narration string.

    Returns:
        str: Sanitized merchant title.
    """
    if not narration or not isinstance(narration, str):
        return "Unknown Merchant"

    text = narration.strip()

    # 1. Mask sensitive account numbers first
    text = mask_sensitive_account_numbers(text)

    # 2. Check for known brand keywords in brand catalog first
    lower_text = text.lower()
    for brand_key, (canonical_name, _) in BRAND_CATALOG.items():
        # Match whole word or bounded brand key
        if re.search(r"\b" + re.escape(brand_key) + r"\b", lower_text):
            return canonical_name

    # 3. Strip Gateway Prefixes e.g. "RAZORPAY*SWIGGY" -> "SWIGGY"
    text = GATEWAY_PREFIX_PATTERN.sub("", text).strip()

    # 4. Standard UPI format parsing e.g. UPI/DR/401029381/MERCHANT/BANK/vpa...
    upi_match = re.search(
        r"UPI(?:/[A-Z0-9]+)?/[0-9]+/([A-Za-z0-9\s\.\&\-_]+?)(?:/[A-Z0-9]+)?(?:/[A-Za-z0-9\._\-@]+)?(?:/|$)",
        text,
        re.IGNORECASE,
    )
    if upi_match:
        extracted = upi_match.group(1).strip()
        cleaned = _sanitize_extracted_token(extracted)
        if cleaned:
            return cleaned

    # Secondary UPI pattern e.g. UPI-MERCHANT-VPA or UPI/MERCHANT
    upi_dash = re.search(r"UPI[/-]([A-Za-z0-9\s\.\&]+?)(?:[/-]|$)", text, re.IGNORECASE)
    if upi_dash:
        extracted = upi_dash.group(1).strip()
        cleaned = _sanitize_extracted_token(extracted)
        if cleaned:
            return cleaned

    # POS Card Swipe pattern e.g. "POS 40192348 RELIANCE FRESH BANGALORE"
    pos_match = re.search(r"POS\s*(?:\d+)?\s*([A-Za-z0-9\s\.\&]+?)(?:\s+[A-Z]{3,}\b|$)", text, re.IGNORECASE)
    if pos_match:
        extracted = pos_match.group(1).strip()
        cleaned = _sanitize_extracted_token(extracted)
        if cleaned:
            return cleaned

    # Fallback: Extract first 3 meaningful words
    words = re.split(r"[/_\-]+|\s+", text)
    meaningful = [
        w for w in words
        if len(w) > 2 and not w.isdigit() and w.upper() not in {"UPI", "IMPS", "NEFT", "RTGS", "DR", "CR", "TRANSFER", "TO", "FROM"}
    ]
    if meaningful:
        candidate = " ".join(meaningful[:3]).title()
        return candidate[:35]

    return text[:30].title()


def _sanitize_extracted_token(token: str) -> Optional[str]:
    """Helper to clean and title-case extracted merchant tokens."""
    # Remove leading/trailing non-alphanumeric chars
    cleaned = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", token).strip()
    if len(cleaned) < 3 or cleaned.isdigit():
        return None
    # Skip protocol words
    if cleaned.upper() in {"UPI", "IMPS", "NEFT", "RTGS", "DR", "CR", "REV", "REVERSAL", "PAYMENT", "TRANSFER"}:
        return None
    return cleaned.title()


def detect_transaction_nature(narration: str, direction: str) -> str:
    """Identify the financial nature of a transaction.

    Distinguishes between routine payments, refunds, failed reversals,
    internal transfers, and income credits.

    Args:
        narration: Raw bank narration string.
        direction: 'DEBIT' or 'CREDIT'.

    Returns:
        str: One of 'reversal', 'refund', 'transfer', 'income', or 'payment'.
    """
    upper_narr = str(narration).upper()
    upper_dir = str(direction).upper()

    # 1. Reversals / Failed Payments
    if any(k in upper_narr for k in ["REV-", "REVERSAL", "FAILED", "BOUNCE", "RETURN", "AUTO REVERSAL", "UNSUCCESSFUL"]):
        return "reversal"

    # 2. Refunds & Cashbacks
    if upper_dir == "CREDIT" and any(k in upper_narr for k in ["REFUND", "CASHBACK", "REV OF DEBIT", "REVERSAL CREDIT"]):
        return "refund"

    # 3. Internal Transfers & Peer Repayments
    if any(k in upper_narr for k in ["SELF TRANSFER", "OWN A/C", "TO SAVINGS", "FROM SAVINGS", "SWEEP", "CREDIT CARD PYMT", "CREDIT CARD PAYMENT", "CRED CLUB", "CHEQ"]):
        return "transfer"

    # 4. Income / Salary
    if upper_dir == "CREDIT":
        if any(k in upper_narr for k in ["SALARY", "PAYROLL", "STIPEND", "DIVIDEND", "INTEREST CREDIT", "CORP SALARY"]):
            return "income"
        # Peer credit transfer
        return "transfer"

    # 5. Routine Outgoing Payment
    return "payment"


def match_rules(
    narration: str,
    merchant: str,
    rules: List[CategorizationRule],
) -> Optional[CategorizationRule]:
    """Evaluate a transaction against an ordered list of categorization rules.

    Args:
        narration: Raw bank narration string.
        merchant: Cleaned merchant or payee name.
        rules: Categorization rules in deterministic priority order.

    Returns:
        Optional[CategorizationRule]: First matching rule or None.
    """
    clean_n = str(narration or "").strip()
    clean_m = str(merchant or "").strip()
    lower_n = clean_n.lower()
    lower_m = clean_m.lower()

    for rule in rules:
        if not rule.is_active:
            continue
        ptype = rule.pattern_type
        pattern = rule.pattern.strip()
        lower_p = pattern.lower()

        if ptype == "merchant_exact":
            if lower_m and lower_m == lower_p:
                return rule
        elif ptype == "merchant_contains":
            if lower_m and lower_p in lower_m:
                return rule
        elif ptype == "narration_contains":
            if lower_n and lower_p in lower_n:
                return rule
        elif ptype == "regex":
            try:
                if re.search(pattern, clean_n, re.IGNORECASE):
                    return rule
            except re.error:
                continue

    return None


def categorize_transaction(
    narration: str,
    direction: str,
    amount: Optional[Decimal] = None,
    custom_rules: Optional[List[CategorizationRule]] = None,
) -> CategorizationResult:
    """Multi-stage categorization pipeline for a single transaction.

    Args:
        narration: Raw bank narration string.
        direction: 'DEBIT' or 'CREDIT'.
        amount: Optional transaction amount (Decimal).
        custom_rules: Optional active custom/promoted categorization rules (top priority).

    Returns:
        CategorizationResult: Fully classified transaction entity with confidence and rules.
    """
    clean_merchant = clean_merchant_advanced(narration)
    nature = detect_transaction_nature(narration, direction)
    lower_narr = str(narration).lower()
    lower_merchant = clean_merchant.lower()

    # Determine channel mode
    mode = "UPI"
    upper_narr = str(narration).upper()
    if "AUTOPAY" in upper_narr or "MANDATE" in upper_narr or "SI" in upper_narr or "ACH" in upper_narr or "ECS" in upper_narr:
        mode = "Autopay"
    elif "POS" in upper_narr or "DEBIT CARD" in upper_narr:
        mode = "Debit Card"
    elif "IMPS" in upper_narr:
        mode = "IMPS"
    elif "NEFT" in upper_narr:
        mode = "NEFT"
    elif "RTGS" in upper_narr:
        mode = "RTGS"

    # --- Stage 0: Custom / Promoted User Rules (Top Priority) ---
    if custom_rules:
        matched_rule = match_rules(narration, clean_merchant, custom_rules)
        if matched_rule:
            cat_name = CATEGORY_TAXONOMY.get(matched_rule.category_id, (matched_rule.category_id, "want"))[0]
            return CategorizationResult(
                merchant=clean_merchant,
                category=cat_name,
                category_id=matched_rule.category_id,
                nature=nature,
                mode=mode,
                confidence=1.0,
                rule_matched=f"Custom Rule: [{matched_rule.source}] '{matched_rule.pattern}' (rule_id: {matched_rule.rule_id})",
            )

    # --- Stage 1: Nature-driven assignments ---
    if nature == "reversal":
        return CategorizationResult(
            merchant=clean_merchant,
            category="Others & Misc",
            category_id="others",
            nature="reversal",
            mode=mode,
            confidence=0.95,
            rule_matched="Reversal / Failed Transaction Detection",
        )

    if nature == "income":
        return CategorizationResult(
            merchant=clean_merchant,
            category="Salary & Income",
            category_id="salary",
            nature="income",
            mode=mode,
            confidence=0.98,
            rule_matched="Salary / Inward Income Detection",
        )

    if nature == "refund":
        # Attempt to map refund to merchant category if known
        for brand_key, (brand_name, cat_id) in BRAND_CATALOG.items():
            if brand_key in lower_narr or brand_key in lower_merchant:
                cat_name = CATEGORY_TAXONOMY[cat_id][0]
                return CategorizationResult(
                    merchant=brand_name,
                    category=cat_name,
                    category_id=cat_id,
                    nature="refund",
                    mode=mode,
                    confidence=0.90,
                    rule_matched=f"Brand Refund Mapping: {brand_name}",
                )
        return CategorizationResult(
            merchant=clean_merchant,
            category="Others & Misc",
            category_id="others",
            nature="refund",
            mode=mode,
            confidence=0.80,
            rule_matched="General Refund Credit",
        )

    if nature == "transfer":
        return CategorizationResult(
            merchant=clean_merchant,
            category="Peer Transfers",
            category_id="transfers",
            nature="transfer",
            mode=mode,
            confidence=0.90,
            rule_matched="Internal Transfer / Peer Movement Detection",
        )

    # --- Stage 2: Direct Brand Dictionary Match ---
    for brand_key, (brand_name, cat_id) in BRAND_CATALOG.items():
        if re.search(r"\b" + re.escape(brand_key) + r"\b", lower_narr) or re.search(r"\b" + re.escape(brand_key) + r"\b", lower_merchant):
            cat_name = CATEGORY_TAXONOMY[cat_id][0]
            return CategorizationResult(
                merchant=brand_name,
                category=cat_name,
                category_id=cat_id,
                nature="payment",
                mode=mode,
                confidence=0.95,
                rule_matched=f"Brand Catalog Exact Match: {brand_name}",
            )

    # --- Stage 3: Keyword Pattern Matching ---
    for cat_id, keywords in KEYWORD_TAXONOMY.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", lower_narr):
                cat_name = CATEGORY_TAXONOMY[cat_id][0]
                return CategorizationResult(
                    merchant=clean_merchant,
                    category=cat_name,
                    category_id=cat_id,
                    nature="payment",
                    mode=mode,
                    confidence=0.75,
                    rule_matched=f"Keyword Rule Match: '{kw}' -> {cat_name}",
                )

    # --- Stage 4: Honest Fallback ---
    return CategorizationResult(
        merchant=clean_merchant,
        category="Others & Misc",
        category_id="others",
        nature="payment",
        mode=mode,
        confidence=0.30,
        rule_matched="Fallback: Unmatched Category (Others & Misc)",
    )
