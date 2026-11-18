"""Unit tests for the Phase 9 categorizer engine.

Tests merchant sanitization, gateway stripping, nature detection, brand matching,
and confidence ratings across Indian banking narrations.
"""

from decimal import Decimal
import pytest

from modules.categorizer import (
    clean_merchant_advanced,
    categorize_transaction,
    detect_transaction_nature,
    mask_sensitive_account_numbers,
)


class TestMerchantSanitization:
    """Tests for merchant cleaning and aggregator prefix removal."""

    def test_strip_gateway_prefixes(self):
        """Verify payment gateway prefixes are stripped."""
        assert clean_merchant_advanced("RAZORPAY*SWIGGY") == "Swiggy"
        assert clean_merchant_advanced("BILLDESK*BESCOM") == "BESCOM Electricity"
        assert clean_merchant_advanced("PAYU*ZOMATO") == "Zomato"
        assert clean_merchant_advanced("PAYTM QR*CHAAYOS") == "Chaayos"
        assert clean_merchant_advanced("AMZN MKTP*RETAIL") == "Amazon"

    def test_brand_dictionary_exact_match(self):
        """Verify known Indian brands are mapped to canonical names."""
        assert clean_merchant_advanced("UPI/DR/123/swiggy@icici/Food") == "Swiggy"
        assert clean_merchant_advanced("UPI/DR/456/zepto/Bangalore") == "Zepto"
        assert clean_merchant_advanced("POS 40192348 RELIANCE FRESH") == "Reliance Fresh"
        assert clean_merchant_advanced("UPI-UBER-RIDES-123") == "Uber"
        assert clean_merchant_advanced("ACH D- NETFLIX ENTERTAINMENT") == "Netflix"

    def test_mask_sensitive_account_numbers(self):
        """Verify 9-18 digit account numbers are masked."""
        raw = "Transfer to A/C 123456789012 at HDFC"
        masked = mask_sensitive_account_numbers(raw)
        assert "••••9012" in masked
        assert "123456789012" not in masked


class TestNatureDetection:
    """Tests for financial nature classification."""

    def test_reversal_detection(self):
        """Verify reversals and failed payments are flagged."""
        assert detect_transaction_nature("REV-UPI/401029/SWIGGY", "CREDIT") == "reversal"
        assert detect_transaction_nature("UPI REVERSAL FAILED TXN", "CREDIT") == "reversal"

    def test_refund_detection(self):
        """Verify refunds on credit transactions are recognized."""
        assert detect_transaction_nature("UPI/CR/123/REFUND SWIGGY", "CREDIT") == "refund"
        assert detect_transaction_nature("CASHBACK RECEIVED FROM GPAY", "CREDIT") == "refund"

    def test_transfer_detection(self):
        """Verify self-transfers and peer movements are recognized."""
        assert detect_transaction_nature("SELF TRANSFER TO SAVINGS", "DEBIT") == "transfer"
        assert detect_transaction_nature("CREDIT CARD PAYMENT HDFC", "DEBIT") == "transfer"
        assert detect_transaction_nature("IMPS P2A TRANSFER FROM ANANYA", "CREDIT") == "transfer"

    def test_income_detection(self):
        """Verify salary and corporate payouts are recognized."""
        assert detect_transaction_nature("NEFT CR-TECHCORP SOLUTIONS-SALARY JAN", "CREDIT") == "income"
        assert detect_transaction_nature("PAYROLL DIRECT CREDIT", "CREDIT") == "income"


class TestCategorizationPipeline:
    """Tests for multi-stage categorization and confidence scoring."""

    def test_brand_match_confidence(self):
        """Verify direct brand catalog matches have high confidence."""
        res = categorize_transaction("UPI/DR/4019283/ZOMATO/ORDER", "DEBIT")
        assert res.merchant == "Zomato"
        assert res.category == "Food & Dining"
        assert res.category_id == "food_dining"
        assert res.nature == "payment"
        assert res.confidence >= 0.90

    def test_keyword_match_confidence(self):
        """Verify keyword rule matches have medium confidence."""
        res = categorize_transaction("UPI/DR/999/LOCAL CHAI CORNER/TEA", "DEBIT")
        assert res.category == "Food & Dining"
        assert res.confidence >= 0.70

    def test_fallback_unmatched(self):
        """Verify unmatched narrations fall back to Others with low confidence."""
        res = categorize_transaction("RANDOM UNKNOWN CODE XYZ9876", "DEBIT")
        assert res.category == "Others & Misc"
        assert res.category_id == "others"
        assert res.confidence <= 0.40

    def test_autopay_mode_detection(self):
        """Verify autopay mode is detected from mandate markers."""
        res = categorize_transaction("AUTOPAY/NETFLIX/MANDATE123", "DEBIT")
        assert res.mode == "Autopay"
