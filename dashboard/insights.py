"""Smart Spending Insights and Advisory view for UPI Smart Expense Analyzer.

Analyzes spending velocity, subscription leakage, and micro-transaction accumulation
to provide actionable, grounded, and explainable recommendations.
"""

from decimal import Decimal
import pandas as pd
import streamlit as st

from modules.advisor import generate_spending_insights
from modules.analytics import (
    calculate_micro_spend_profile,
    calculate_weekday_weekend_profile,
)
from modules.money import format_inr
from modules.recurring import detect_recurring_transactions


def render_insights(df: pd.DataFrame) -> None:
    """Render the Smart Insights and Recommendations view.

    Args:
        df: DataFrame containing all transactions.
    """
    st.subheader("💡 Smart Spending Insights & Advisory")
    st.caption("Explainable financial pattern recognition designed to uncover savings opportunities from your statement.")

    is_demo = st.session_state.get("is_demo_data", True)
    active_filename = st.session_state.get("statement_filename", "Synthetic Demo Dataset")

    # Context Header Banner
    if is_demo:
        st.info(
            f"**DEMO DATA PREVIEW:** The observations below are computed dynamically from your "
            f"**{len(df)} sample transactions** to illustrate the automated pattern detection engine.",
            icon="🔍",
        )
    else:
        st.success(
            f"**LIVE STATEMENT ANALYSIS:** Insights computed from **{len(df)} transactions** in `{active_filename}`.",
            icon="📊",
        )

    # 1. Recurring Subscriptions Section
    st.markdown("### 🔁 1. Recurring Subscriptions & Autopay Mandates")
    recurring_items = detect_recurring_transactions(df)

    if recurring_items:
        st.markdown(f"Detected **{len(recurring_items)} active recurring commitments** across your statement history:")
        cols = st.columns(min(len(recurring_items), 3))
        for idx, item in enumerate(recurring_items[:3]):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"**{item.merchant}**")
                    st.markdown(f"`{format_inr(item.average_amount)} / {item.cadence.lower()}`")
                    st.caption(f"Last debited: {item.last_billed_date.strftime('%d-%b-%Y')}")
                    st.caption(f"Est. Annual: **{format_inr(item.estimated_annual_cost)}**")
                    if item.is_autopay:
                        st.caption("🔒 Autopay / Standing Mandate")

        # Annualization note
        total_annual = sum(r.estimated_annual_cost for r in recurring_items)
        st.info(
            f"💡 **Cumulative Annual Commitment:** You have committed approximately **{format_inr(total_annual)} / year** "
            f"across these standing services. Review them periodically to cancel unused memberships.",
            icon="ℹ️",
        )
    else:
        st.info("ℹ️ No recurring subscriptions or standing autopay mandates detected in this statement period.")

    st.divider()

    # 2. Micro-Transactions Breakdown
    st.markdown("### ☕ 2. The Micro-Spend Accumulator")
    st.markdown(
        "Frequent UPI micro-transactions under ₹150 (tea, quick snacks, small recharges) "
        "can silently accumulate into a significant portion of your monthly outflow."
    )

    micro_prof = calculate_micro_spend_profile(df, threshold=Decimal("150.00"))
    col1, col2 = st.columns([1, 2])

    with col1:
        with st.container(border=True):
            st.caption("MICRO-TRANSACTIONS COUNT")
            st.markdown(f"### {micro_prof['micro_count']} transactions")
            st.caption("Purchases under ₹ 150.00")
            st.markdown(f"**Total Spent:** `{format_inr(micro_prof['micro_total'])}`")
            st.caption(f"Share of Debits: **{micro_prof['pct_of_debits']}%**")

    with col2:
        with st.container(border=True):
            st.markdown("#### Primary Micro-Spend Drivers")
            if micro_prof["top_merchants"]:
                for m in micro_prof["top_merchants"][:4]:
                    st.caption(f"• **{m['merchant']}:** {m['count']} transactions ({format_inr(m['total_amount'])})")
                suggested_budget = max(micro_prof["micro_total"] // 4, Decimal("250.00"))
                st.info(f"💡 Setting a weekly pocket budget of **{format_inr(suggested_budget)}** for quick taps could conserve cash comfortably.")
            else:
                st.caption("No micro-transactions detected below ₹150.")

    st.divider()

    # 3. Weekend vs Weekday Dynamic
    st.markdown("### 📈 3. Weekend vs. Weekday Spend Velocity")
    weekend_prof = calculate_weekday_weekend_profile(df)

    w_col1, w_col2, w_col3 = st.columns(3)
    with w_col1:
        with st.container(border=True):
            st.caption("WEEKDAY DAILY AVERAGE")
            st.markdown(f"### {format_inr(weekend_prof['weekday_daily_avg'])}")
            st.caption(f"Across {weekend_prof['weekday_days_count']} active weekdays")

    with w_col2:
        with st.container(border=True):
            st.caption("WEEKEND DAILY AVERAGE")
            st.markdown(f"### {format_inr(weekend_prof['weekend_daily_avg'])}")
            st.caption(f"Across {weekend_prof['weekend_days_count']} active weekend days")

    with w_col3:
        with st.container(border=True):
            st.caption("WEEKEND SURGE FACTOR")
            st.markdown(f"### {weekend_prof['surge_factor']}x")
            surge_text = "Higher weekend velocity" if weekend_prof["surge_factor"] > Decimal("1.2") else "Balanced velocity"
            st.caption(surge_text)

    st.divider()

    # 4. Action Alerts & Anomaly Observations
    st.markdown("### 🔍 4. Grounded Observations & Action Items")
    recommendations = generate_spending_insights(df)

    # Filter out subscription and micro-spend rules (already featured above)
    action_recs = [r for r in recommendations if r.rule_key not in {"recurring_subscription", "micro_spend", "weekend_surge"}]

    if action_recs:
        for rec in action_recs:
            with st.container(border=True):
                r_col1, r_col2 = st.columns([4, 1])
                with r_col1:
                    st.markdown(f"**{rec.title}**")
                    st.markdown(rec.summary)
                    if rec.data_quality_note:
                        st.caption(f"ℹ️ {rec.data_quality_note}")
                with r_col2:
                    if rec.estimated_saving:
                        st.caption("POTENTIAL IMPACT")
                        st.markdown(f"**{format_inr(rec.estimated_saving)}**")
                    badge_color = "🔴" if rec.action_type == "verify" else "🟡"
                    st.caption(f"{badge_color} Action: `{rec.action_type.upper()}`")

                if rec.evidence_txns:
                    with st.expander("🔎 View Supporting Evidence Transactions"):
                        for e in rec.evidence_txns:
                            st.caption(f"• **{e.get('date', 'N/A')}:** {e.get('merchant', 'Payee')} — `{format_inr(e.get('amount', Decimal('0')))}`")
    else:
        st.success("✅ **No anomalous duplicate charges or unexpected fee spikes detected in this period.**")

    st.divider()

    # 5. Epistemic Transparency Disclaimer
    st.caption(
        """
        **🛡️ Financial & Advisory Transparency Notice:**
        All figures, classifications, and suggestions are automated mathematical calculations derived
        strictly from the transaction narrations and timestamps present in your uploaded statements.
        Because bank statements represent partial financial records, this application does not assess overall
        creditworthiness or net worth, and does not provide formal investment, tax, or legal advice.
        """
    )
