"""Synthetic sample transaction generator for UPI Smart Expense Analyzer.

Provides realistic, mock UPI transactions for UI testing, dashboard preview,
and layout verification. Contains ZERO real personal or financial data.
All monetary amounts are generated using exact `Decimal` objects.
"""

from datetime import date, timedelta
from decimal import Decimal
import pandas as pd

from modules.money import to_money, sum_money, pct


def get_sample_transactions() -> pd.DataFrame:
    """Generate a realistic dataset of synthetic UPI transactions.

    Returns:
        pd.DataFrame: DataFrame containing mock transactions with columns:
            - date: Transaction date (YYYY-MM-DD)
            - merchant: Cleaned merchant or counterparty name
            - narration: Raw simulated UPI bank narration string
            - category: Standard Indian UPI spending category
            - mode: Payment channel (UPI, IMPS, Autopay)
            - type: DEBIT or CREDIT
            - amount: Monetary amount as Decimal
    """
    records = []
    base_date = date(2026, 1, 1)

    # 1. Monthly Salary (Credit)
    records.append({
        "date": date(2026, 1, 1),
        "merchant": "TechCorp Payroll",
        "narration": "NEFT/CMS/SALARY/JAN2026/TECHCORP",
        "category": "Salary & Income",
        "mode": "IMPS",
        "type": "CREDIT",
        "amount": to_money("95000.00"),
    })

    # 2. Fixed Bills & Recurring Subscriptions (Debits)
    recurring_items = [
        ("Netflix India", "UPI/401029381/NETFLIX/MANDATE", "Entertainment & Subs", to_money("649.00"), 5),
        ("Spotify Premium", "UPI/402910382/SPOTIFY/RECURRING", "Entertainment & Subs", to_money("119.00"), 12),
        ("Disney+ Hotstar", "UPI/403910283/HOTSTAR/SUB", "Entertainment & Subs", to_money("430.00"), 18),
        ("Airtel Broadband", "UPI/404910294/AIRTEL/BILL", "Utilities & Bills", to_money("1179.00"), 7),
        ("BESCOM Electricity", "UPI/405910285/BESCOM/PORTAL", "Utilities & Bills", to_money("1850.00"), 10),
        ("House Rent", "UPI/406910296/RENT/TRANSFER", "Rent & Housing", to_money("22000.00"), 3),
    ]

    for name, narration, cat, amt, day in recurring_items:
        records.append({
            "date": date(2026, 1, day),
            "merchant": name,
            "narration": narration,
            "category": cat,
            "mode": "Autopay" if "MANDATE" in narration or "RECURRING" in narration else "UPI",
            "type": "DEBIT",
            "amount": amt,
        })

    # 3. Frequent Daily Expenses (Food, Groceries, Commute, Shopping)
    daily_merchants = [
        ("Swiggy Food", "UPI/32187312/SWIGGY/PAYTM", "Food & Dining", "485.00", "DEBIT"),
        ("Zomato Delivery", "UPI/32189401/ZOMATO/AXIS", "Food & Dining", "340.00", "DEBIT"),
        ("Chai Point", "UPI/32201928/CHAIPOINT/HDFC", "Food & Dining", "85.00", "DEBIT"),
        ("Corner Tea Stall", "UPI/32291028/CHAI/PAYTMQR", "Food & Dining", "30.00", "DEBIT"),
        ("Zepto Groceries", "UPI/32391029/ZEPTO/INSTANT", "Groceries & Essentials", "620.00", "DEBIT"),
        ("Blinkit Commerce", "UPI/32481029/BLINKIT/ICICI", "Groceries & Essentials", "890.00", "DEBIT"),
        ("Nature Basket", "UPI/32581028/NATURESBASKET/POS", "Groceries & Essentials", "1450.00", "DEBIT"),
        ("Uber Rides", "UPI/32681029/UBER/PAYTM", "Commute & Travel", "340.00", "DEBIT"),
        ("Ola Cabs", "UPI/32781029/OLACABS/HDFC", "Commute & Travel", "280.00", "DEBIT"),
        ("Namma Metro", "UPI/32881029/METRO/SMARTCARD", "Commute & Travel", "100.00", "DEBIT"),
        ("Shell Petrol Bunk", "UPI/32981029/SHELL/FUEL", "Commute & Travel", "1200.00", "DEBIT"),
        ("Amazon India", "UPI/33081029/AMAZONPAY/ICICI", "Shopping & E-Com", "1650.00", "DEBIT"),
        ("Myntra Fashion", "UPI/33181029/MYNTRA/RETAIL", "Shopping & E-Com", "2499.00", "DEBIT"),
        ("Apollo Pharmacy", "UPI/33281029/APOLLO/MEDICAL", "Health & Medical", "420.00", "DEBIT"),
    ]

    # Generate entries across 31 days of January
    for day_offset in range(31):
        current_date = base_date + timedelta(days=day_offset)
        # Select 2 to 4 merchants per day cyclically
        indices = [
            (day_offset * 3 + 0) % len(daily_merchants),
            (day_offset * 3 + 1) % len(daily_merchants),
            (day_offset * 3 + 2) % len(daily_merchants),
        ]
        if day_offset % 3 == 0:
            indices.append((day_offset * 3 + 3) % len(daily_merchants))

        for idx in indices:
            m_name, narr, cat, amt_str, direction = daily_merchants[idx]
            # Add slight day variation to amounts
            amt = to_money(amt_str)
            records.append({
                "date": current_date,
                "merchant": m_name,
                "narration": f"{narr}/{day_offset + 1:02d}",
                "category": cat,
                "mode": "UPI",
                "type": direction,
                "amount": amt,
            })

    # 4. Peer Transfers (Friend split reimbursement & outgoing transfer)
    records.append({
        "date": date(2026, 1, 15),
        "merchant": "Rohan Sharma (Dinner Split)",
        "narration": "UPI/407910297/SPLIT/PAYTM",
        "category": "Peer Transfers",
        "mode": "UPI",
        "type": "CREDIT",
        "amount": to_money("1250.00"),
    })
    records.append({
        "date": date(2026, 1, 22),
        "merchant": "Priya Verma",
        "narration": "UPI/408910298/GIFT/PHONEPE",
        "category": "Peer Transfers",
        "mode": "UPI",
        "type": "DEBIT",
        "amount": to_money("1500.00"),
    })

    df = pd.DataFrame(records)
    # Sort descending by date
    df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
    return df


def calculate_sample_kpis(df: pd.DataFrame) -> dict:
    """Calculate key financial performance metrics from transactions.

    Args:
        df: DataFrame of transactions.

    Returns:
        dict: Summary dictionary containing:
            - total_credits (Decimal)
            - total_debits (Decimal)
            - net_savings (Decimal)
            - savings_rate (Decimal)
            - txn_count (int)
            - debit_count (int)
            - credit_count (int)
    """
    debits_df = df[df["type"] == "DEBIT"]
    credits_df = df[df["type"] == "CREDIT"]

    total_debits = sum_money(debits_df["amount"]) if not debits_df.empty else Decimal("0.00")
    total_credits = sum_money(credits_df["amount"]) if not credits_df.empty else Decimal("0.00")
    net_savings = total_credits - total_debits
    savings_rate = pct(net_savings, total_credits) if total_credits > Decimal("0.00") else Decimal("0.00")

    return {
        "total_credits": total_credits,
        "total_debits": total_debits,
        "net_savings": net_savings,
        "savings_rate": savings_rate,
        "txn_count": len(df),
        "debit_count": len(debits_df),
        "credit_count": len(credits_df),
    }
