"""Transaction Ledger, Multi-Filter Matrix, Category Overrides, Rules, and Exports view.

Provides:
1. Multi-criteria filtering (Date range, Account, Category multiselect, Type, Amount min/max, Text search).
2. One-click multi-format exports (CSV, openpyxl Excel, PyMuPDF PDF).
3. Manual category override interface with atomic persistence and audit log inspection.
4. Custom categorization rules manager with creation, activation, deletion, and rule promotion.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import pandas as pd
import streamlit as st

from database.db import get_connection
from database.repositories import (
    AccountRepository,
    CATEGORY_ID_TO_NAME,
    CATEGORY_NAME_TO_ID,
    TransactionRepository,
)
from database.rules_repository import validate_rule_pattern
from modules.exporter import (
    export_monthly_report_pdf,
    export_transactions_csv,
    export_transactions_excel,
)
from modules.money import format_inr, sum_money, to_money
from services.overrides_service import OverridesService
from services.rules_service import RulesService


def render_transactions(df: pd.DataFrame) -> None:
    """Render the full interactive transaction ledger with filters, overrides, rules, and exports.

    Args:
        df: Unfiltered canonical DataFrame of transactions.
    """
    st.subheader("📑 Transaction Ledger & Management")
    st.caption("Search, filter, categorize, manage custom rules, and export personal financial records.")

    tab_ledger, tab_overrides, tab_rules = st.tabs([
        "📑 Ledger & Exports",
        "✏️ Category Overrides & Audit",
        "⚙️ Custom Rules Engine",
    ])

    with tab_ledger:
        _render_ledger_and_filters(df)

    with tab_overrides:
        _render_overrides_view(df)

    with tab_rules:
        _render_rules_view(df)


# ==============================================================================
# 1. Ledger, Multi-Filter Matrix & Exports
# ==============================================================================
def _render_ledger_and_filters(df: pd.DataFrame) -> None:
    """Render multi-filter matrix, summary stats, export buttons, and transaction table."""
    with st.expander("🔍 Filter & Search Transactions", expanded=True):
        # Row 1: Search, Category multiselect, Type
        r1_c1, r1_c2, r1_c3 = st.columns([2, 2, 1])

        with r1_c1:
            search_query = st.text_input(
                "Search Merchant or Narration",
                placeholder="e.g., Swiggy, Netflix, UPI...",
                key="filter_search_input",
            )

        all_categories = sorted(list(df["category"].unique())) if not df.empty else []
        with r1_c2:
            selected_categories = st.multiselect(
                "Filter Categories",
                options=all_categories,
                default=[],
                placeholder="All Categories (leave blank)",
                key="filter_categories_input",
            )

        with r1_c3:
            type_filter = st.selectbox(
                "Transaction Type",
                options=["All", "DEBIT (Expenses)", "CREDIT (Inflows)"],
                index=0,
                key="filter_type_input",
            )

        # Row 2: Date range, Account, Amount Range
        r2_c1, r2_c2, r2_c3 = st.columns([1.5, 1.5, 2])

        # Date Range Filter
        min_date_val = None
        max_date_val = None
        if not df.empty:
            dates = pd.to_datetime(df["date"]).dt.date
            min_date_val = dates.min()
            max_date_val = dates.max()

        with r2_c1:
            if min_date_val and max_date_val:
                selected_dates = st.date_input(
                    "Date Range",
                    value=(min_date_val, max_date_val),
                    min_value=min_date_val,
                    max_value=max_date_val,
                    key="filter_date_range_input",
                )
            else:
                selected_dates = None
                st.caption("No dates available")

        # Account Filter
        account_options = ["All Accounts"]
        if "account_id" in df.columns:
            distinct_accs = [str(a) for a in df["account_id"].dropna().unique() if a]
            account_options.extend(distinct_accs)

        with r2_c2:
            selected_account = st.selectbox(
                "Bank Account",
                options=account_options,
                index=0,
                key="filter_account_input",
            )

        # Amount Range Filter
        max_amt_val = 100000.0
        if not df.empty:
            max_amt_val = float(max(to_money(a) for a in df["amount"]))

        with r2_c3:
            amt_col1, amt_col2 = st.columns(2)
            with amt_col1:
                min_amount = st.number_input(
                    "Min Amount (₹)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0,
                    key="filter_min_amt",
                )
            with amt_col2:
                max_amount = st.number_input(
                    "Max Amount (₹)",
                    min_value=0.0,
                    value=max_amt_val,
                    step=500.0,
                    key="filter_max_amt",
                )

    # -------------------------------------------------------------------------
    # Apply Filters to produce filtered_df
    # -------------------------------------------------------------------------
    filtered_df = df.copy()

    # 1. Text Search Filter
    if search_query and not filtered_df.empty:
        q = search_query.strip().lower()
        mask = (
            filtered_df["merchant"].astype(str).str.lower().str.contains(q, na=False)
            | filtered_df["narration"].astype(str).str.lower().str.contains(q, na=False)
        )
        filtered_df = filtered_df[mask]

    # 2. Category Multiselect Filter
    if selected_categories and not filtered_df.empty:
        filtered_df = filtered_df[filtered_df["category"].isin(selected_categories)]

    # 3. Transaction Type Filter
    if type_filter == "DEBIT (Expenses)" and not filtered_df.empty:
        filtered_df = filtered_df[filtered_df["type"] == "DEBIT"]
    elif type_filter == "CREDIT (Inflows)" and not filtered_df.empty:
        filtered_df = filtered_df[filtered_df["type"] == "CREDIT"]

    # 4. Date Range Filter
    if selected_dates and len(selected_dates) == 2 and not filtered_df.empty:
        start_d, end_d = selected_dates
        if start_d > end_d:
            start_d, end_d = end_d, start_d  # Auto-swap if inverted
        dates_series = pd.to_datetime(filtered_df["date"]).dt.date
        filtered_df = filtered_df[(dates_series >= start_d) & (dates_series <= end_d)]

    # 5. Account Filter
    if selected_account != "All Accounts" and "account_id" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["account_id"] == selected_account]

    # 6. Amount Range Filter
    if not filtered_df.empty:
        if min_amount > max_amount:
            st.warning("⚠️ Min Amount is greater than Max Amount. Swapping values.")
            min_amount, max_amount = max_amount, min_amount
        min_dec = to_money(min_amount)
        max_dec = to_money(max_amount)
        filtered_df = filtered_df[filtered_df["amount"].apply(lambda a: min_dec <= to_money(a) <= max_dec)]

    # -------------------------------------------------------------------------
    # Stats & Export Action Bar
    # -------------------------------------------------------------------------
    st.divider()
    stat_col, exp_col1, exp_col2, exp_col3 = st.columns([2.5, 1, 1, 1])

    with stat_col:
        total_filtered = sum_money(filtered_df["amount"]) if not filtered_df.empty else Decimal("0.00")
        st.markdown(
            f"**Showing {len(filtered_df):,} of {len(df):,} transactions** • "
            f"Filtered Sum: `{format_inr(total_filtered)}`"
        )

    # Export Buttons
    today_str = datetime.now().strftime("%Y%m%d")

    # CSV Download
    csv_bytes = export_transactions_csv(filtered_df)
    with exp_col1:
        st.download_button(
            label="📥 CSV",
            data=csv_bytes,
            file_name=f"upi_transactions_{today_str}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_download_csv",
        )

    # Excel Download
    excel_bytes = export_transactions_excel(filtered_df)
    with exp_col2:
        st.download_button(
            label="📊 Excel (.xlsx)",
            data=excel_bytes,
            file_name=f"upi_ledger_{today_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_download_excel",
        )

    # PDF Download
    pdf_bytes = export_monthly_report_pdf(filtered_df)
    with exp_col3:
        st.download_button(
            label="📑 PDF Report",
            data=pdf_bytes,
            file_name=f"upi_report_{today_str}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="btn_download_pdf",
        )

    # -------------------------------------------------------------------------
    # Render Transactions Table
    # -------------------------------------------------------------------------
    if filtered_df.empty:
        st.info("ℹ️ No transactions match the current filter criteria.", icon="🔍")
    else:
        display_df = filtered_df.copy()
        display_df["amount_numeric"] = display_df["amount"].apply(lambda a: float(to_money(a)))

        cols_to_show = ["date", "merchant", "narration", "category", "mode", "type", "amount_numeric"]
        if "category_source" in display_df.columns:
            cols_to_show.append("category_source")

        st.dataframe(
            display_df[cols_to_show],
            column_config={
                "date": st.column_config.DateColumn("Date", format="DD-MMM-YYYY"),
                "merchant": st.column_config.TextColumn("Merchant / Payee", width="medium"),
                "narration": st.column_config.TextColumn("Raw Narration", width="large"),
                "category": st.column_config.TextColumn("Category", width="small"),
                "mode": st.column_config.TextColumn("Mode", width="small"),
                "type": st.column_config.TextColumn("Type", width="small"),
                "amount_numeric": st.column_config.NumberColumn("Amount (₹)", format="₹ %.2f", width="small"),
                "category_source": st.column_config.TextColumn("Source", width="small"),
            },
            use_container_width=True,
            hide_index=True,
        )


# ==============================================================================
# 2. Manual Category Overrides & Live Audit Trail
# ==============================================================================
def _render_overrides_view(df: pd.DataFrame) -> None:
    """Render the category override form and the immutable audit log table."""
    st.subheader("✏️ Manual Category Override")
    st.caption("Manually recategorize any transaction with permanent audit tracking.")

    is_demo = st.session_state.get("is_demo_data", True)
    if is_demo or "txn_id" not in df.columns:
        st.warning(
            "⚠️ You are currently viewing synthetic Demo Data. "
            "Manual overrides and audit logs require live statement persistence in SQLite. "
            "Please import a bank statement via **Upload Statement** to enable category edits.",
            icon="ℹ️",
        )
        return

    # Transaction Selector
    # Map index to descriptive string
    txn_options = {}
    for idx, row in df.iterrows():
        t_id = row["txn_id"]
        d_str = format_date_str(row["date"])
        amt_str = format_inr(to_money(row["amount"]))
        label = f"{d_str} • {row['merchant'][:20]} • {amt_str} [{row['category']}] ({t_id[:12]})"
        txn_options[label] = t_id

    sel_label = st.selectbox(
        "Select Transaction to Override",
        options=list(txn_options.keys()),
        key="override_txn_select",
    )
    selected_txn_id = txn_options[sel_label]

    # Look up selected row
    selected_row = df[df["txn_id"] == selected_txn_id].iloc[0]
    curr_cat_name = selected_row["category"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Current Category:** `{curr_cat_name}`")
        st.markdown(f"**Merchant:** `{selected_row['merchant']}`")
        st.markdown(f"**Amount:** `{format_inr(to_money(selected_row['amount']))}`")
        st.markdown(f"**Narration:** `{selected_row['narration']}`")

    with col2:
        # Category options excluding current
        available_cats = [c for c in CATEGORY_NAME_TO_ID.keys() if c != curr_cat_name]
        target_cat_name = st.selectbox(
            "New Category",
            options=available_cats,
            key="override_target_cat",
        )
        reason = st.text_input(
            "Reason for correction (optional)",
            placeholder="e.g. Personal dinner, Work reimbursement...",
            key="override_reason_input",
        )

        if st.button("💾 Apply Manual Override", use_container_width=True, type="primary"):
            target_cat_id = CATEGORY_NAME_TO_ID[target_cat_name]
            conn = get_connection()
            try:
                OverridesService.override_category(
                    conn=conn,
                    txn_id=selected_txn_id,
                    new_category_id=target_cat_id,
                    reason=reason.strip() if reason else None,
                )
                # Refresh session state
                updated_txns = TransactionRepository.get_transactions(conn)
                st.session_state["transactions_df"] = TransactionRepository.to_dataframe(
                    updated_txns, include_metadata=True
                )
                st.success(f"✅ Category successfully updated to **{target_cat_name}**!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to apply override: {e}")
            finally:
                conn.close()

    # -------------------------------------------------------------------------
    # Audit Trail History
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("📜 Category Override Audit Trail")
    st.caption("Immutable record of all manual categorization changes.")

    conn = get_connection()
    try:
        audit_history = OverridesService.get_audit_history(conn)
    finally:
        conn.close()

    if not audit_history:
        st.info("No manual category overrides recorded yet.", icon="ℹ️")
    else:
        audit_records = []
        for a in audit_history:
            prev_name = CATEGORY_ID_TO_NAME.get(a.previous_category_id, a.previous_category_id or "Auto")
            new_name = CATEGORY_ID_TO_NAME.get(a.new_category_id, a.new_category_id)
            audit_records.append({
                "Timestamp (UTC)": a.changed_at.strftime("%Y-%m-%d %H:%M:%S"),
                "Transaction ID": a.txn_id,
                "Previous Category": prev_name,
                "New Category": new_name,
                "Reason": a.reason or "—",
            })

        st.dataframe(
            pd.DataFrame(audit_records),
            use_container_width=True,
            hide_index=True,
        )


# ==============================================================================
# 3. Custom Rules Engine & Rule Promotion
# ==============================================================================
def _render_rules_view(df: pd.DataFrame) -> None:
    """Render rule list, new rule authoring, active toggling, deletion, and rule promotion."""
    st.subheader("⚙️ Custom Categorization Rules")
    st.caption("Define deterministic rules that take top priority over default machine recognition.")

    is_demo = st.session_state.get("is_demo_data", True)
    if is_demo:
        st.warning(
            "⚠️ You are currently viewing synthetic Demo Data. "
            "Custom rules require live SQLite persistence. "
            "Please import a bank statement via **Upload Statement** to manage custom rules.",
            icon="ℹ️",
        )
        return

    conn = get_connection()
    try:
        rules = RulesService.list_rules(conn, active_only=False)
    finally:
        conn.close()

    # -------------------------------------------------------------------------
    # Active Rules Table
    # -------------------------------------------------------------------------
    if not rules:
        st.info("No custom categorization rules created yet. Create one below!", icon="💡")
    else:
        rules_data = []
        for r in rules:
            cat_name = CATEGORY_ID_TO_NAME.get(r.category_id, r.category_id)
            rules_data.append({
                "Rule ID": r.rule_id,
                "Pattern": r.pattern,
                "Match Type": r.pattern_type,
                "Category": cat_name,
                "Priority": r.priority,
                "Source": r.source.capitalize(),
                "Hit Count": r.hit_count,
                "Status": "🟢 Active" if r.is_active else "⚪ Inactive",
            })

        st.dataframe(pd.DataFrame(rules_data), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # Create New Rule Form
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("➕ Create New Categorization Rule")

    with st.form("create_rule_form"):
        col1, col2 = st.columns(2)
        with col1:
            pattern_text = st.text_input(
                "Match Pattern",
                placeholder="e.g. Chai Point, Metro, Netflix...",
                help="Text string or regular expression to match.",
            )
            pattern_type = st.selectbox(
                "Match Type",
                options=[
                    ("merchant_exact", "Exact Merchant Name (case-insensitive)"),
                    ("merchant_contains", "Merchant Contains Substring"),
                    ("narration_contains", "Narration Contains Substring"),
                    ("regex", "Regular Expression (Advanced)"),
                ],
                format_func=lambda x: x[1],
            )
        with col2:
            target_cat_name = st.selectbox("Assign to Category", options=list(CATEGORY_NAME_TO_ID.keys()))
            priority_val = st.number_input(
                "Rule Priority",
                min_value=1,
                max_value=1000,
                value=100,
                help="Higher priority rules evaluate first.",
            )

        submit_rule = st.form_submit_button("🚀 Create & Apply Rule", type="primary", use_container_width=True)

        if submit_rule:
            if not pattern_text or not pattern_text.strip():
                st.error("❌ Pattern cannot be empty.")
            else:
                p_type = pattern_type[0]
                try:
                    validate_rule_pattern(pattern_text.strip(), p_type)
                    target_cat_id = CATEGORY_NAME_TO_ID[target_cat_name]

                    conn = get_connection()
                    try:
                        rule, updated_count = RulesService.create_rule(
                            conn=conn,
                            pattern=pattern_text.strip(),
                            pattern_type=p_type,
                            category_id=target_cat_id,
                            priority=int(priority_val),
                            apply_to_historical=True,
                        )
                        # Refresh session state
                        updated_txns = TransactionRepository.get_transactions(conn)
                        st.session_state["transactions_df"] = TransactionRepository.to_dataframe(
                            updated_txns, include_metadata=True
                        )
                        st.success(
                            f"✅ Created rule `{rule.rule_id}`! "
                            f"Applied to {updated_count} historical transactions."
                        )
                        st.rerun()
                    finally:
                        conn.close()
                except Exception as e:
                    st.error(f"❌ Failed to create rule: {e}")

    # -------------------------------------------------------------------------
    # Manage Existing Rule (Toggle / Delete)
    # -------------------------------------------------------------------------
    if rules:
        st.divider()
        st.subheader("🛠️ Manage Existing Rules")

        rule_choices = {f"[{r.rule_id}] '{r.pattern}' -> {CATEGORY_ID_TO_NAME.get(r.category_id, r.category_id)}": r for r in rules}
        selected_rule_str = st.selectbox("Select Rule", options=list(rule_choices.keys()), key="manage_rule_select")
        target_rule = rule_choices[selected_rule_str]

        m_col1, m_col2 = st.columns(2)
        with m_col1:
            toggle_label = "⚪ Deactivate Rule" if target_rule.is_active else "🟢 Activate Rule"
            if st.button(toggle_label, use_container_width=True):
                conn = get_connection()
                try:
                    updated = RulesService.toggle_rule_active(
                        conn, target_rule.rule_id, not target_rule.is_active, reapply=True
                    )
                    updated_txns = TransactionRepository.get_transactions(conn)
                    st.session_state["transactions_df"] = TransactionRepository.to_dataframe(
                        updated_txns, include_metadata=True
                    )
                    st.success(f"Rule status toggled! {updated} transactions re-evaluated.")
                    st.rerun()
                finally:
                    conn.close()

        with m_col2:
            confirm_delete = st.checkbox(f"Confirm deletion of rule [{target_rule.rule_id}]", key="confirm_rule_del")
            if st.button("🗑️ Delete Rule", use_container_width=True, disabled=not confirm_delete):
                conn = get_connection()
                try:
                    reverted = RulesService.delete_rule(conn, target_rule.rule_id, reapply=True)
                    updated_txns = TransactionRepository.get_transactions(conn)
                    st.session_state["transactions_df"] = TransactionRepository.to_dataframe(
                        updated_txns, include_metadata=True
                    )
                    st.success(f"Rule deleted! {reverted} transactions reverted to original categories.")
                    st.rerun()
                finally:
                    conn.close()

    # -------------------------------------------------------------------------
    # Promote Override to Reusable Rule
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("🚀 Promote Override to Reusable Rule")
    st.caption("Convert a manual category override into a permanent rule across all existing and future transactions.")

    if "txn_id" in df.columns:
        # Transactions with manual overrides
        overridden_df = df[df.get("category_source", "") == "user_override"] if "category_source" in df.columns else pd.DataFrame()
        if overridden_df.empty:
            st.info("No manually overridden transactions available for promotion.", icon="ℹ️")
        else:
            p_options = {}
            for _, o_row in overridden_df.iterrows():
                p_label = f"{format_date_str(o_row['date'])} • {o_row['merchant']} • {format_inr(to_money(o_row['amount']))} [{o_row['category']}]"
                p_options[p_label] = o_row["txn_id"]

            chosen_promo_label = st.selectbox("Select Overridden Transaction", options=list(p_options.keys()), key="promo_select")
            chosen_promo_txn_id = p_options[chosen_promo_label]

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                promo_p_type = st.selectbox(
                    "Matching Type",
                    options=[
                        ("merchant_exact", "Exact Merchant Name"),
                        ("merchant_contains", "Merchant Contains Substring"),
                    ],
                    format_func=lambda x: x[1],
                    key="promo_type_select",
                )
            with col_p2:
                promo_prio = st.number_input("Priority", min_value=1, max_value=1000, value=100, key="promo_prio_input")

            if st.button("🌟 Promote to Reusable Rule", use_container_width=True, type="primary"):
                conn = get_connection()
                try:
                    p_rule, p_updated = RulesService.promote_override_to_rule(
                        conn=conn,
                        txn_id=chosen_promo_txn_id,
                        pattern_type=promo_p_type[0],
                        priority=int(promo_prio),
                    )
                    updated_txns = TransactionRepository.get_transactions(conn)
                    st.session_state["transactions_df"] = TransactionRepository.to_dataframe(
                        updated_txns, include_metadata=True
                    )
                    st.success(
                        f"🎉 Successfully promoted rule `{p_rule.rule_id}` for **{p_rule.pattern}**! "
                        f"{p_updated} transactions recategorized."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to promote rule: {e}")
                finally:
                    conn.close()
