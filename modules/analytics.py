"""Pure financial calculation and spending analytics module.

Implements monthly summaries, category breakdowns, 50/30/20 macro-budgeting,
micro-transaction profiling, and weekday/weekend dynamics with Decimal accuracy.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.categorizer import CATEGORY_TAXONOMY, CATEGORY_NAME_TO_ID
from modules.money import pct, quantize, sum_money, to_money


def calculate_monthly_summary(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Compute exact monthly cash flows, net spend, income, and savings rate.

    Args:
        df: Canonical DataFrame of transactions.

    Returns:
        List[Dict]: List of monthly metrics sorted chronologically.
    """
    if df.empty:
        return []

    # Bucket transactions by month string "YYYY-MM"
    # Column extraction avoids df.iterrows() and row.to_dict() overhead
    dates = df["date"].tolist() if "date" in df.columns else []
    amounts = df["amount"].tolist() if "amount" in df.columns else []
    types = df["type"].tolist() if "type" in df.columns else []
    categories = df["category"].tolist() if "category" in df.columns else [""] * len(dates)
    narrations = df["narration"].tolist() if "narration" in df.columns else [""] * len(dates)

    months_dict = defaultdict(lambda: {
        "credits": [],
        "debits": [],
        "routine": [],
        "income": [],
        "refunds": [],
        "txn_count": 0,
    })

    for t_date, raw_amt, raw_type, raw_cat, raw_narr in zip(dates, amounts, types, categories, narrations):
        if isinstance(t_date, str):
            month_key = t_date[:7]
        elif isinstance(t_date, date):
            month_key = t_date.strftime("%Y-%m")
        else:
            continue

        amt = to_money(raw_amt)
        r_type = str(raw_type).upper()
        cat = str(raw_cat) if (raw_cat is not None and not pd.isna(raw_cat)) else ""
        narr = str(raw_narr).upper() if raw_narr is not None else ""

        bucket = months_dict[month_key]
        bucket["txn_count"] += 1

        if r_type == "CREDIT":
            bucket["credits"].append(amt)
            # Check if refund
            if "REFUND" in narr or "CASHBACK" in narr or "REV OF DEBIT" in narr:
                bucket["refunds"].append(amt)
            # Income: salary, interest, dividend, or explicit salary category
            elif cat == "Salary & Income" or "SALARY" in narr or "PAYROLL" in narr or "DIVIDEND" in narr or "INTEREST" in narr:
                bucket["income"].append(amt)
        elif r_type == "DEBIT":
            bucket["debits"].append(amt)
            # Reversals and peer transfers are excluded from routine spend
            if "REV-" not in narr and "REVERSAL" not in narr and cat != "Peer Transfers":
                bucket["routine"].append(amt)

    summaries = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for month_key in sorted(months_dict.keys()):
        bucket = months_dict[month_key]
        total_credits = sum_money(bucket["credits"])
        total_debits = sum_money(bucket["debits"])
        gross_routine_spend = sum_money(bucket["routine"])
        refunds_total = sum_money(bucket["refunds"])

        # Net spend offsets refunds
        net_spend = gross_routine_spend - refunds_total
        if net_spend < Decimal("0.00"):
            net_spend = Decimal("0.00")

        total_income = sum_money(bucket["income"])
        net_cash_flow = total_income - net_spend

        savings_rate = None
        if total_income > Decimal("0.00"):
            savings_rate = pct(net_cash_flow, total_income)

        # Format human-readable month label e.g. "Jan 2026"
        year, month_num = month_key.split("-")
        month_label = f"{month_names[int(month_num) - 1]} {year}"

        summaries.append({
            "month": month_key,
            "month_label": month_label,
            "total_credits": total_credits,
            "total_debits": total_debits,
            "routine_spend": net_spend,
            "income": total_income,
            "net_cash_flow": net_cash_flow,
            "savings_rate": savings_rate,
            "txn_count": bucket["txn_count"],
        })

    return summaries


def calculate_category_breakdown(
    df: pd.DataFrame,
    month_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Compute category-wise total spend, share of wallet, and transaction counts.

    Excludes peer transfers and credit income from spend calculations. Offsets refunds.

    Args:
        df: Canonical DataFrame of transactions.
        month_filter: Optional month filter "YYYY-MM".

    Returns:
        List[Dict]: List of category summaries sorted by total spend descending.
    """
    if df.empty:
        return []

    # Apply month filter if provided
    filtered_df = df
    if month_filter:
        def _in_month(d):
            if isinstance(d, str):
                return d.startswith(month_filter)
            if isinstance(d, date):
                return d.strftime("%Y-%m") == month_filter
            return False
        filtered_df = df[df["date"].apply(_in_month)]

    if filtered_df.empty:
        return []

    amounts = filtered_df["amount"].tolist() if "amount" in filtered_df.columns else []
    types = filtered_df["type"].tolist() if "type" in filtered_df.columns else []
    categories = filtered_df["category"].tolist() if "category" in filtered_df.columns else ["Others & Misc"] * len(amounts)
    narrations = filtered_df["narration"].tolist() if "narration" in filtered_df.columns else [""] * len(amounts)

    cat_debits: Dict[str, List[Decimal]] = defaultdict(list)
    cat_refunds: Dict[str, List[Decimal]] = defaultdict(list)
    cat_txn_counts: Dict[str, int] = defaultdict(int)

    for raw_amt, raw_type, raw_cat, raw_narr in zip(amounts, types, categories, narrations):
        amt = to_money(raw_amt)
        r_type = str(raw_type).upper()
        cat = str(raw_cat) if (raw_cat is not None and not pd.isna(raw_cat)) else "Others & Misc"
        narr = str(raw_narr).upper() if raw_narr is not None else ""

        # Skip peer transfers and reversals from routine category spend
        if cat in {"Peer Transfers", "Salary & Income"} or "REVERSAL" in narr:
            continue

        if r_type == "DEBIT":
            cat_debits[cat].append(amt)
            cat_txn_counts[cat] += 1
        elif r_type == "CREDIT" and ("REFUND" in narr or "CASHBACK" in narr):
            cat_refunds[cat].append(amt)

    # Compute total discretionary spend across all categories
    all_net_spends = []
    category_results = []

    for cat_name, debits_list in cat_debits.items():
        gross = sum_money(debits_list)
        ref = sum_money(cat_refunds.get(cat_name, []))
        net = gross - ref
        if net < Decimal("0.00"):
            net = Decimal("0.00")
        all_net_spends.append(net)

        cat_id = CATEGORY_NAME_TO_ID.get(cat_name, "others")
        kind = CATEGORY_TAXONOMY.get(cat_id, ("Others", "want"))[1]

        category_results.append({
            "category": cat_name,
            "category_id": cat_id,
            "kind": kind,
            "total_spend": net,
            "txn_count": cat_txn_counts[cat_name],
            "avg_ticket": quantize(net / Decimal(cat_txn_counts[cat_name])) if cat_txn_counts[cat_name] > 0 else Decimal("0.00"),
        })

    total_spend_all = sum_money(all_net_spends)

    # Compute percentage share for each category
    for item in category_results:
        item["share_pct"] = pct(item["total_spend"], total_spend_all)

    # Sort descending by total spend
    return sorted(category_results, key=lambda x: x["total_spend"], reverse=True)


def calculate_macro_buckets(df: pd.DataFrame) -> Dict[str, Decimal]:
    """Aggregate spending into Needs, Wants, and Savings according to the 50/30/20 framework.

    Returns:
        Dict[str, Decimal]: {"needs": Decimal, "wants": Decimal, "savings": Decimal}
    """
    breakdown = calculate_category_breakdown(df)
    needs_total = Decimal("0.00")
    wants_total = Decimal("0.00")
    savings_total = Decimal("0.00")

    for item in breakdown:
        kind = item["kind"]
        amt = item["total_spend"]
        if kind == "need":
            needs_total += amt
        elif kind == "want":
            wants_total += amt
        elif kind == "saving":
            savings_total += amt

    return {
        "needs": quantize(needs_total),
        "wants": quantize(wants_total),
        "savings": quantize(savings_total),
    }


def calculate_micro_spend_profile(
    df: pd.DataFrame,
    threshold: Decimal = Decimal("150.00"),
) -> Dict[str, Any]:
    """Analyze micro-transactions (small UPI purchases under threshold, e.g. ₹150).

    Args:
        df: Canonical DataFrame of transactions.
        threshold: Upper limit for micro-spend classification.

    Returns:
        Dict: Micro-spend counts, total amount, percentage of total debits, and top drivers.
    """
    if df.empty:
        return {
            "micro_count": 0,
            "micro_total": Decimal("0.00"),
            "pct_of_debits": Decimal("0.00"),
            "top_merchants": [],
        }

    debit_rows = df[df["type"] == "DEBIT"]
    all_debits_total = sum_money(debit_rows["amount"]) if not debit_rows.empty else Decimal("0.00")

    micro_rows = debit_rows[debit_rows["amount"] <= threshold]
    micro_count = len(micro_rows)
    micro_total = sum_money(micro_rows["amount"]) if not micro_rows.empty else Decimal("0.00")
    micro_share = pct(micro_total, all_debits_total)

    # Top micro merchants
    merchant_counts: Dict[str, int] = defaultdict(int)
    merchant_totals: Dict[str, List[Decimal]] = defaultdict(list)
    merchants = micro_rows["merchant"].tolist()
    amounts = micro_rows["amount"].tolist()
    for m_val, amt_val in zip(merchants, amounts):
        m = str(m_val)
        merchant_counts[m] += 1
        merchant_totals[m].append(to_money(amt_val))

    top_merchants = []
    for m, count in sorted(merchant_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        top_merchants.append({
            "merchant": m,
            "count": count,
            "total_amount": sum_money(merchant_totals[m]),
        })

    return {
        "micro_count": micro_count,
        "micro_total": micro_total,
        "pct_of_debits": micro_share,
        "top_merchants": top_merchants,
    }


def calculate_weekday_weekend_profile(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze spending velocity between Weekdays (Mon-Fri) and Weekends (Sat-Sun).

    Returns:
        Dict: Weekday and weekend totals, day counts, daily averages, and surge factor.
    """
    if df.empty:
        return {
            "weekday_total": Decimal("0.00"),
            "weekday_daily_avg": Decimal("0.00"),
            "weekend_total": Decimal("0.00"),
            "weekend_daily_avg": Decimal("0.00"),
            "surge_factor": Decimal("1.00"),
        }

    weekday_amounts: List[Decimal] = []
    weekend_amounts: List[Decimal] = []
    weekday_dates = set()
    weekend_dates = set()

    debit_df = df[df["type"] == "DEBIT"]
    amounts = debit_df["amount"].tolist() if "amount" in debit_df.columns else []
    dates = debit_df["date"].tolist() if "date" in debit_df.columns else []

    for raw_amt, t_date in zip(amounts, dates):
        amt = to_money(raw_amt)
        if isinstance(t_date, str):
            t_date = date.fromisoformat(t_date)
        elif not isinstance(t_date, date):
            continue

        day_of_week = t_date.weekday()  # 0=Monday, 6=Sunday
        if day_of_week in (5, 6):  # Saturday, Sunday
            weekend_amounts.append(amt)
            weekend_dates.add(t_date)
        else:
            weekday_amounts.append(amt)
            weekday_dates.add(t_date)

    weekday_total = sum_money(weekday_amounts)
    weekend_total = sum_money(weekend_amounts)

    weekday_days = max(len(weekday_dates), 1)
    weekend_days = max(len(weekend_dates), 1)

    weekday_daily_avg = quantize(weekday_total / Decimal(weekday_days))
    weekend_daily_avg = quantize(weekend_total / Decimal(weekend_days))

    surge_factor = Decimal("1.00")
    if weekday_daily_avg > Decimal("0.00"):
        surge_factor = quantize(weekend_daily_avg / weekday_daily_avg)

    return {
        "weekday_total": weekday_total,
        "weekday_days_count": len(weekday_dates),
        "weekday_daily_avg": weekday_daily_avg,
        "weekend_total": weekend_total,
        "weekend_days_count": len(weekend_dates),
        "weekend_daily_avg": weekend_daily_avg,
        "surge_factor": surge_factor,
    }


def calculate_top_merchants(df: pd.DataFrame, n: int = 10) -> List[Dict[str, Any]]:
    """Return top N debit payees sorted by total expenditure volume.

    Excludes peer transfers and self-transfers from routine merchant spend.

    Args:
        df: Canonical DataFrame of transactions.
        n: Number of top merchants to return.

    Returns:
        List[Dict]: List of top merchants with total spent, transaction count, and category.
    """
    if df.empty:
        return []

    # Filter active debits, excluding internal peer transfers
    debit_rows = df[(df["type"] == "DEBIT") & (df["category"] != "Peer Transfers")]
    if debit_rows.empty:
        return []

    merchants = debit_rows["merchant"].tolist()
    amounts = debit_rows["amount"].tolist()
    categories = debit_rows["category"].tolist() if "category" in debit_rows.columns else ["Others & Misc"] * len(merchants)

    m_amounts: Dict[str, List[Decimal]] = defaultdict(list)
    m_counts: Dict[str, int] = defaultdict(int)
    m_categories: Dict[str, str] = {}

    for m_val, amt_val, cat_val in zip(merchants, amounts, categories):
        m = str(m_val)
        amt = to_money(amt_val)
        m_amounts[m].append(amt)
        m_counts[m] += 1
        if m not in m_categories:
            m_categories[m] = str(cat_val) if (cat_val is not None and not pd.isna(cat_val)) else "Others & Misc"

    results = []
    for m in m_amounts:
        total = sum_money(m_amounts[m])
        results.append({
            "merchant": m,
            "category": m_categories[m],
            "total_spend": total,
            "txn_count": m_counts[m],
        })

    return sorted(results, key=lambda x: x["total_spend"], reverse=True)[:n]
