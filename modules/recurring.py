"""Recurring transaction and subscription detection engine.

Analyzes transaction intervals, amount stability, and autopay markers to identify
recurring debits, OTT streaming services, gym memberships, and utility cadences.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.money import quantize, to_money


@dataclass
class RecurringItem:
    """Represents a detected recurring subscription or standing debit."""

    merchant: str
    category: str
    cadence: str  # "Monthly", "Quarterly", "Annual", "Autopay Mandate"
    average_amount: Decimal
    last_billed_date: date
    occurrences: int
    estimated_annual_cost: Decimal
    is_autopay: bool
    evidence_txns: List[Dict[str, Any]]


def detect_recurring_transactions(df: pd.DataFrame) -> List[RecurringItem]:
    """Detect recurring debits and active subscriptions from transaction history.

    Args:
        df: Canonical DataFrame of transactions.

    Returns:
        List[RecurringItem]: List of recurring items sorted by annual cost descending.
    """
    if df.empty:
        return []

    # Filter for active outgoing debits, excluding peer transfers and reversals
    debit_rows = df[
        (df["type"] == "DEBIT")
        & (~df["category"].isin(["Peer Transfers", "Salary & Income"]))
        & (~df["narration"].str.contains("REVERSAL|REV-", case=False, na=False))
    ]

    if debit_rows.empty:
        return []

    # Group by merchant
    merchant_groups: Dict[str, List[Dict]] = defaultdict(list)
    for _, row in debit_rows.iterrows():
        t_date = row["date"]
        if isinstance(t_date, str):
            t_date = date.fromisoformat(t_date)
        elif not isinstance(t_date, date):
            continue

        merchant_groups[str(row["merchant"])].append({
            "date": t_date,
            "amount": to_money(row["amount"]),
            "narration": str(row.get("narration", "")),
            "category": str(row.get("category", "Others & Misc")),
            "mode": str(row.get("mode", "UPI")),
        })

    recurring_items: List[RecurringItem] = []

    for merchant, txns in merchant_groups.items():
        # Sort chronologically
        txns_sorted = sorted(txns, key=lambda x: x["date"])
        n = len(txns_sorted)

        # Check for explicit Autopay or Standing Mandate markers in narration
        has_autopay_marker = any(
            t["mode"] == "Autopay" or any(k in t["narration"].upper() for k in ["AUTOPAY", "MANDATE", "SI", "ACH", "ECS"])
            for t in txns_sorted
        )

        amounts = [t["amount"] for t in txns_sorted]
        min_amt = min(amounts)
        max_amt = max(amounts)
        avg_amt = quantize(sum(amounts) / Decimal(n))

        # Check amount stability: variance within 5%
        amount_is_stable = True
        if avg_amt > Decimal("0.00"):
            spread = (max_amt - min_amt) / avg_amt
            if spread > Decimal("0.08"):  # Allow up to 8% variation for minor tax/price changes
                amount_is_stable = False

        # If only 1 occurrence, only include if marked with an explicit Autopay mandate
        if n == 1:
            if has_autopay_marker and avg_amt >= Decimal("50.00"):
                recurring_items.append(
                    RecurringItem(
                        merchant=merchant,
                        category=txns_sorted[0]["category"],
                        cadence="Autopay Mandate",
                        average_amount=avg_amt,
                        last_billed_date=txns_sorted[0]["date"],
                        occurrences=1,
                        estimated_annual_cost=quantize(avg_amt * Decimal("12")),
                        is_autopay=True,
                        evidence_txns=txns_sorted,
                    )
                )
            continue

        # If 2 or more occurrences, inspect interval between debits
        intervals: List[int] = []
        for i in range(1, n):
            delta = (txns_sorted[i]["date"] - txns_sorted[i - 1]["date"]).days
            intervals.append(delta)

        avg_interval = sum(intervals) / len(intervals)

        cadence = None
        multiplier = Decimal("12")

        # Monthly recurrence: interval ~ 25 to 35 days
        if 25 <= avg_interval <= 35 and amount_is_stable:
            cadence = "Monthly"
            multiplier = Decimal("12")
        # Quarterly recurrence: interval ~ 80 to 100 days
        elif 80 <= avg_interval <= 100 and amount_is_stable:
            cadence = "Quarterly"
            multiplier = Decimal("4")
        # Annual recurrence: interval ~ 350 to 380 days
        elif 350 <= avg_interval <= 380 and amount_is_stable:
            cadence = "Annual"
            multiplier = Decimal("1")
        # Autopay mandate with slightly irregular intervals
        elif has_autopay_marker and amount_is_stable:
            cadence = "Monthly"
            multiplier = Decimal("12")

        if cadence is not None:
            annual_cost = quantize(avg_amt * multiplier)
            recurring_items.append(
                RecurringItem(
                    merchant=merchant,
                    category=txns_sorted[-1]["category"],
                    cadence=cadence,
                    average_amount=avg_amt,
                    last_billed_date=txns_sorted[-1]["date"],
                    occurrences=n,
                    estimated_annual_cost=annual_cost,
                    is_autopay=has_autopay_marker,
                    evidence_txns=txns_sorted,
                )
            )

    # Sort descending by annual cost
    return sorted(recurring_items, key=lambda x: x.estimated_annual_cost, reverse=True)
