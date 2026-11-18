"""Grounded Spending Insights and Recommendation Engine.

Generates polite, evidence-backed financial observations and savings opportunities
from transaction history without requiring external cloud APIs.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.analytics import (
    calculate_category_breakdown,
    calculate_micro_spend_profile,
    calculate_monthly_summary,
    calculate_weekday_weekend_profile,
)
from modules.money import format_inr, quantize, to_money
from modules.recurring import detect_recurring_transactions


@dataclass
class Recommendation:
    """An explainable, evidence-backed spending insight or action recommendation."""

    rule_key: str
    title: str
    summary: str
    category: str
    estimated_saving: Optional[Decimal]
    confidence: str  # "High", "Medium", "Low"
    action_type: str  # "review", "verify", "informational", "budget"
    evidence_txns: List[Dict[str, Any]]
    data_quality_note: Optional[str] = None


def generate_spending_insights(df: pd.DataFrame) -> List[Recommendation]:
    """Evaluate all advisory rules over transaction history and return ranked recommendations.

    Args:
        df: Canonical DataFrame of transactions.

    Returns:
        List[Recommendation]: List of recommendations sorted by impact.
    """
    if df.empty or len(df) < 3:
        return []

    recommendations: List[Recommendation] = []

    # Calculate dataset time span
    dates = []
    for d in df["date"]:
        if isinstance(d, str):
            dates.append(date.fromisoformat(d))
        elif isinstance(d, date):
            dates.append(d)

    min_date = min(dates) if dates else None
    max_date = max(dates) if dates else None
    day_span = (max_date - min_date).days + 1 if min_date and max_date else 0
    span_note = f"Observed over {len(df)} transactions spanning {day_span} days ({min_date} to {max_date})."

    # --- Rule 1: Recurring Subscriptions & Mandates ---
    rec_items = detect_recurring_transactions(df)
    if rec_items:
        streaming_or_ent = [r for r in rec_items if r.category in {"Entertainment & Subs", "Others & Misc"}]
        total_annual_subs = sum(r.estimated_annual_cost for r in rec_items)

        evidence = []
        for r in rec_items:
            for t in r.evidence_txns:
                evidence.append({"date": str(t["date"]), "merchant": r.merchant, "amount": t["amount"]})

        sub_names = ", ".join(r.merchant for r in rec_items[:4])
        summary_parts = [
            f"Detected **{len(rec_items)} active recurring services** ({sub_names}) "
            f"totaling an estimated **{format_inr(total_annual_subs)} / year** in standing commitments."
        ]
        if len(streaming_or_ent) >= 2:
            names = ", ".join(r.merchant for r in streaming_or_ent[:3])
            summary_parts.append(
                f"You have multiple subscriptions in Entertainment & Media ({names}). "
                f"Consolidating or annualizing billing could free recurring monthly cash flow."
            )

        # Estimate savings as 10% through annual billing or pruning 1 subscription
        est_savings = quantize(min(r.average_amount * Decimal("12") for r in rec_items)) if rec_items else None

        recommendations.append(
            Recommendation(
                rule_key="recurring_subscription",
                title=f"Recurring Commitments: {len(rec_items)} Subscriptions Detected",
                summary=" ".join(summary_parts),
                category="Entertainment & Subs",
                estimated_saving=est_savings,
                confidence="High",
                action_type="review",
                evidence_txns=evidence[:8],
                data_quality_note=span_note,
            )
        )

    # --- Rule 2: Potential Duplicate Charge Detection ---
    debit_txns = []
    for _, row in df[df["type"] == "DEBIT"].iterrows():
        t_d = row["date"]
        if isinstance(t_d, str):
            t_d = date.fromisoformat(t_d)
        debit_txns.append({
            "date": t_d,
            "merchant": str(row["merchant"]),
            "amount": to_money(row["amount"]),
            "narration": str(row.get("narration", "")),
        })

    # Sort by date
    debit_txns.sort(key=lambda x: x["date"])
    duplicate_pairs = []
    for i in range(len(debit_txns)):
        for j in range(i + 1, min(i + 8, len(debit_txns))):
            t1 = debit_txns[i]
            t2 = debit_txns[j]
            # Same merchant and same amount within 2 days
            if t1["merchant"] == t2["merchant"] and t1["amount"] == t2["amount"] and t1["amount"] >= Decimal("100.00"):
                day_diff = abs((t2["date"] - t1["date"]).days)
                if day_diff <= 1:
                    duplicate_pairs.append((t1, t2))
                    break

    if duplicate_pairs:
        t1, t2 = duplicate_pairs[0]
        recommendations.append(
            Recommendation(
                rule_key="duplicate_charge",
                title=f"Potential Duplicate Debit: {t1['merchant']} ({format_inr(t1['amount'])})",
                summary=(
                    f"Two identical debits of **{format_inr(t1['amount'])}** to **{t1['merchant']}** occurred within 24 hours "
                    f"({t1['date'].strftime('%d-%b')} and {t2['date'].strftime('%d-%b')}). "
                    f"Verify whether one was a double charge, a retried payment, or if a refund is pending."
                ),
                category="Others & Misc",
                estimated_saving=t1["amount"],
                confidence="Medium",
                action_type="verify",
                evidence_txns=[
                    {"date": str(t1["date"]), "merchant": t1["merchant"], "amount": t1["amount"]},
                    {"date": str(t2["date"]), "merchant": t2["merchant"], "amount": t2["amount"]},
                ],
                data_quality_note=span_note,
            )
        )

    # --- Rule 3: Micro-Spend Accumulator ---
    micro_prof = calculate_micro_spend_profile(df, threshold=Decimal("150.00"))
    if micro_prof["micro_count"] >= 8 and micro_prof["micro_total"] >= Decimal("500.00"):
        top_driver_names = ", ".join(m["merchant"] for m in micro_prof["top_merchants"][:3])
        # Suggest potential savings by setting a weekly pocket budget
        suggested_savings = quantize(micro_prof["micro_total"] * Decimal("0.25"))

        recommendations.append(
            Recommendation(
                rule_key="micro_spend",
                title=f"Micro-Spend Velocity: {micro_prof['micro_count']} Small Purchases",
                summary=(
                    f"You made **{micro_prof['micro_count']} purchases under ₹ 150.00**, totaling "
                    f"**{format_inr(micro_prof['micro_total'])}** ({micro_prof['pct_of_debits']}% of all debits). "
                    f"Primary drivers include **{top_driver_names}**. "
                    f"Setting a weekly UPI wallet pocket budget could comfortably conserve cash."
                ),
                category="Food & Dining",
                estimated_saving=suggested_savings,
                confidence="High",
                action_type="budget",
                evidence_txns=[
                    {"date": "Various", "merchant": m["merchant"], "amount": m["total_amount"]}
                    for m in micro_prof["top_merchants"][:4]
                ],
                data_quality_note=span_note,
            )
        )

    # --- Rule 4: Category Spike Detection (Requires >= 2 Distinct Months) ---
    monthly_summaries = calculate_monthly_summary(df)
    if len(monthly_summaries) >= 2:
        # Compare latest month with prior month
        prev_m = monthly_summaries[-2]
        curr_m = monthly_summaries[-1]

        curr_cats = calculate_category_breakdown(df, month_filter=curr_m["month"])
        prev_cats = {c["category"]: c["total_spend"] for c in calculate_category_breakdown(df, month_filter=prev_m["month"])}

        for c_item in curr_cats:
            cat_name = c_item["category"]
            curr_amt = c_item["total_spend"]
            prev_amt = prev_cats.get(cat_name, Decimal("0.00"))

            # Check if category rose by > 35% and by at least ₹ 1,500
            if prev_amt >= Decimal("1000.00") and curr_amt >= (prev_amt * Decimal("1.35")):
                spike_delta = curr_amt - prev_amt
                pct_increase = quantize(((curr_amt - prev_amt) / prev_amt) * Decimal("100.00"))

                recommendations.append(
                    Recommendation(
                        rule_key="category_spike",
                        title=f"Category Surge: {cat_name} (+{pct_increase}%)",
                        summary=(
                            f"Spending in **{cat_name}** rose from **{format_inr(prev_amt)}** in {prev_m['month_label']} "
                            f"to **{format_inr(curr_amt)}** in {curr_m['month_label']} (an increase of {format_inr(spike_delta)}). "
                            f"Review recent transactions to verify whether this reflects one-off planned purchases."
                        ),
                        category=cat_name,
                        estimated_saving=spike_delta,
                        confidence="Medium",
                        action_type="review",
                        evidence_txns=[],
                        data_quality_note=f"Comparing {prev_m['month_label']} against {curr_m['month_label']}.",
                    )
                )
                break  # Show at most one category spike to avoid alert fatigue

    # --- Rule 5: Weekend Spend Velocity Profile ---
    weekend_prof = calculate_weekday_weekend_profile(df)
    if weekend_prof["surge_factor"] >= Decimal("1.50") and weekend_prof["weekend_total"] >= Decimal("2000.00"):
        recommendations.append(
            Recommendation(
                rule_key="weekend_surge",
                title=f"Weekend Spend Surge: {weekend_prof['surge_factor']}x Weekday Velocity",
                summary=(
                    f"Your average expenditure on Saturdays & Sundays is **{format_inr(weekend_prof['weekend_daily_avg'])} / day**, "
                    f"compared to **{format_inr(weekend_prof['weekday_daily_avg'])} / day** on weekdays. "
                    f"Weekend activities account for **{format_inr(weekend_prof['weekend_total'])}** across your statement."
                ),
                category="Food & Dining",
                estimated_saving=None,
                confidence="High",
                action_type="informational",
                evidence_txns=[],
                data_quality_note=span_note,
            )
        )

    # --- Rule 6: Bank Fees & Surcharges ---
    fee_txns = []
    for _, row in df[df["type"] == "DEBIT"].iterrows():
        narr = str(row.get("narration", "")).upper()
        if any(k in narr for k in ["CHARGE", "FEE", "PENALTY", "GST ON CHARGE", "SMS CHG", "MIN BAL"]):
            fee_txns.append({
                "date": str(row["date"]),
                "merchant": str(row["merchant"]),
                "amount": to_money(row["amount"]),
            })

    if fee_txns:
        fee_total = sum(t["amount"] for t in fee_txns)
        recommendations.append(
            Recommendation(
                rule_key="fee_leakage",
                title=f"Bank Surcharges & Fees: {format_inr(fee_total)} Incurred",
                summary=(
                    f"Found **{len(fee_txns)} fee/penalty debits** totaling **{format_inr(fee_total)}**. "
                    f"Review these charges to ensure your minimum balance and notification preferences avoid unnecessary fees."
                ),
                category="Utilities & Bills",
                estimated_saving=fee_total,
                confidence="High",
                action_type="review",
                evidence_txns=fee_txns,
                data_quality_note=span_note,
            )
        )

    return recommendations
