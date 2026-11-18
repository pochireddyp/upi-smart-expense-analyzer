"""Dashboard Overview module for UPI Smart Expense Analyzer.

Renders the primary executive summary view:
- Global statement filters
- Demo data indicator banner
- 4 Core KPI Summary Cards (Debits, Credits, Net Savings, Volume)
- Interactive Plotly Charts (Trendline & Category Donut)
- Smart Spending Insights cards
- Recent Transactions Table with clean formatting
"""

from decimal import Decimal
import pandas as pd
import streamlit as st

from dashboard.charts import build_expense_trend_chart, build_category_donut_chart
from database.db import get_connection
from database.repositories import AccountRepository
from modules.money import format_inr
from sample_data.generator import calculate_sample_kpis


def render_overview(df: pd.DataFrame) -> None:
    """Render the main dashboard overview screen.

    Args:
        df: DataFrame containing the active transactions to display.
    """
    # 1. Filter & Context Bar
    conn = get_connection()
    try:
        db_accounts = AccountRepository.list_accounts(conn)
    finally:
        conn.close()

    account_options = ["All Accounts (Consolidated)"]
    if db_accounts:
        for acc in db_accounts:
            lbl = f"{acc.bank_name or acc.label} (••••{acc.account_last4 or 'Main'})"
            account_options.append(lbl)
    else:
        account_options.extend(["HDFC Bank (••••4912)", "SBI (••••8102)"])

    filter_col1, filter_col2 = st.columns([1, 1])
    with filter_col1:
        st.selectbox(
            "Active Bank Account",
            options=account_options,
            index=0,
            help="Switch between bank accounts or view consolidated cash flow.",
        )
    with filter_col2:
        st.date_input(
            "Transaction Period",
            value=(df["date"].min(), df["date"].max()),
            help="Filter analytics by custom date boundaries.",
        )

    # 2. Prominent Data Mode Badge
    is_demo = st.session_state.get("is_demo_data", True)
    if is_demo:
        st.info(
            "**DEMO DATA PREVIEW:** You are viewing **184 synthetic sample transactions** "
            "designed to showcase the dashboard capabilities. No personal financial data has been uploaded.",
            icon="🎲",
        )
    else:
        active_filename = st.session_state.get("statement_filename", "Uploaded Statement")
        banner_col1, banner_col2 = st.columns([4, 1])
        with banner_col1:
            st.success(
                f"**LIVE STATEMENT ACTIVE:** Displaying **{len(df)} transactions** parsed from **`{active_filename}`**.",
                icon="📊",
            )
        with banner_col2:
            if st.button("🔄 Reset Demo", use_container_width=True, help="Switch back to sample demo data"):
                st.session_state["transactions_df"] = None
                st.session_state["is_demo_data"] = True
                st.session_state["statement_filename"] = None
                st.rerun()

    # 3. Category Confidence & Review Banner
    unmatched_count = len(df[df["category"] == "Others & Misc"]) if not df.empty else 0
    with st.container(border=True):
        alert_col1, alert_col2 = st.columns([4, 1])
        with alert_col1:
            if unmatched_count > 0:
                st.markdown(
                    f"⚠️ **{unmatched_count} Transactions Classified as 'Others & Misc':** Some narrations "
                    f"could benefit from manual review to keep your category analytics 100% precise."
                )
            else:
                st.markdown("✅ **High Category Coverage:** All transactions are categorized into specific spending buckets.")
        with alert_col2:
            st.button("Review & Fix ➡️", use_container_width=True)

    # 4. Summary KPI Cards
    kpis = calculate_sample_kpis(df)
    card1, card2, card3, card4 = st.columns(4)

    with card1:
        with st.container(border=True):
            st.caption("TOTAL DEBITS (EXPENSES)")
            st.metric(
                label="Debits",
                value=format_inr(kpis["total_debits"]),
                delta="+12.4% vs last month",
                delta_color="inverse",
                label_visibility="collapsed",
            )

    with card2:
        with st.container(border=True):
            st.caption("TOTAL CREDITS (INFLOWS)")
            st.metric(
                label="Credits",
                value=format_inr(kpis["total_credits"]),
                delta="+5.0% vs last month",
                delta_color="normal",
                label_visibility="collapsed",
            )

    with card3:
        with st.container(border=True):
            st.caption("NET SAVINGS RETAINED")
            st.metric(
                label="Net Flow",
                value=format_inr(kpis["net_savings"]),
                delta=f"{kpis['savings_rate']}% Savings Rate",
                delta_color="off",
                label_visibility="collapsed",
            )

    with card4:
        with st.container(border=True):
            st.caption("TOTAL TRANSACTIONS")
            st.metric(
                label="Volume",
                value=f"{kpis['txn_count']}",
                delta=f"{kpis['debit_count']} Dr • {kpis['credit_count']} Cr",
                delta_color="off",
                label_visibility="collapsed",
            )

    st.divider()

    # 5. Interactive Charts Section
    chart_col1, chart_col2 = st.columns([7, 5])
    with chart_col1:
        with st.container(border=True):
            fig_trend = build_expense_trend_chart(df)
            st.plotly_chart(fig_trend, use_container_width=True)

    with chart_col2:
        with st.container(border=True):
            fig_donut = build_category_donut_chart(df)
            st.plotly_chart(fig_donut, use_container_width=True)

    st.divider()

    # 6. Smart Spending Insights (Synthetic Patterns)
    st.subheader("💡 Smart Spending Insights (Sample Patterns)")
    ins_col1, ins_col2, ins_col3 = st.columns(3)

    with ins_col1:
        with st.container(border=True):
            st.markdown("#### 🔁 Recurring Subscriptions")
            st.markdown(
                "You have **3 active streaming subscriptions** totaling **₹ 1,198.00** this month:"
            )
            st.caption("• Netflix India: ₹ 649.00 (Jan 05)")
            st.caption("• Spotify Premium: ₹ 119.00 (Jan 12)")
            st.caption("• Disney+ Hotstar: ₹ 430.00 (Jan 18)")
            st.info("💡 Tip: Consider an annual bundle to save up to 20%.")

    with ins_col2:
        with st.container(border=True):
            st.markdown("#### ☕ Micro-Spend Accumulator")
            st.markdown(
                "You executed **38 micro-transactions** (< ₹150) totaling **₹ 3,420.00**."
            )
            st.caption("• 92% went to quick snacks and tea stalls.")
            st.caption("• Represents 8.2% of total monthly outflows.")
            st.warning("⚡ Observation: Small UPI taps add up silently.")

    with ins_col3:
        with st.container(border=True):
            st.markdown("#### 📈 Weekend Spending Surge")
            st.markdown(
                "Your average daily spend jumps from **₹ 850** on weekdays to **₹ 2,940** on weekends."
            )
            st.caption("• Friday night to Sunday night represents 42% of non-essential dining and shopping.")
            st.success("🎯 Milestone: Utilities and essentials stayed within budget.")

    st.divider()

    # 7. Recent Transactions Table Preview
    st.subheader("📑 Recent Transactions Preview")

    # Format amount as float for clean Streamlit NumberColumn rendering
    display_df = df.head(8).copy()
    display_df["amount_numeric"] = display_df["amount"].apply(lambda a: float(a))

    st.dataframe(
        display_df[["date", "merchant", "category", "mode", "type", "amount_numeric"]],
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD-MMM-YYYY"),
            "merchant": st.column_config.TextColumn("Merchant / Description", width="medium"),
            "category": st.column_config.TextColumn("Category", width="small"),
            "mode": st.column_config.TextColumn("Channel", width="small"),
            "type": st.column_config.TextColumn("Type", width="small"),
            "amount_numeric": st.column_config.NumberColumn("Amount (₹)", format="₹ %.2f", width="small"),
        },
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Showing 8 most recent transactions • Switch to **📑 Transactions Ledger** in the sidebar to view, search, and filter all 184 records.")
