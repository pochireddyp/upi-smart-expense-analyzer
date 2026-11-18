"""Statement Upload and Ingestion UI for UPI Smart Expense Analyzer.

Handles both CSV and PDF file uploads, automatic schema detection, in-memory
password decryption for locked PDFs, validation, previewing, and atomic SQLite
database persistence with duplicate-import prevention.
"""

from decimal import Decimal
import streamlit as st

from database.db import get_connection
from database.repositories import StatementRepository
from modules.csv_parser import parse_csv_statement
from modules.pdf_parser import parse_pdf_statement
from services.import_service import ImportService, MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB


def render_upload() -> None:
    """Render the Bank Statement Upload and processing screen."""
    st.subheader("📥 Bank Statement Upload")
    st.caption("Import your official bank statement in CSV or PDF format to generate automated spending insights.")

    # 1. Cloud vs Local Privacy Notice
    st.warning(
        """
        **🔒 Privacy & Processing Transparency:**
        * **Streamlit Community Cloud:** Files are read in temporary memory on the hosting server and discarded
          immediately after session termination. Zero data is shared with third-party AI APIs.
        * **Local Desktop Mode:** Processing is 100% offline and stays on your machine.
        * **Confidentiality:** Account numbers in narrations are automatically masked for privacy.
        """,
        icon="🛡️",
    )

    # 2. Check if a live statement is currently loaded
    if not st.session_state.get("is_demo_data", True):
        with st.container(border=True):
            st.info(
                f"✅ **Active Statement Loaded:** `{st.session_state.get('statement_filename', 'Uploaded File')}` "
                f"({len(st.session_state.get('transactions_df', []))} transactions active across dashboard).",
                icon="📊",
            )
            if st.button("🔄 Reset to Synthetic Demo Data", use_container_width=True):
                st.session_state["transactions_df"] = None
                st.session_state["is_demo_data"] = True
                st.session_state["statement_filename"] = None
                st.rerun()

    # 3. File Upload Area
    with st.container(border=True):
        st.markdown("#### 1. Select Your Statement File")
        uploaded_file = st.file_uploader(
            "Choose a statement file",
            type=["csv", "pdf"],
            help="Supports official digital statements from Indian banks (HDFC, SBI, ICICI, Axis, Kotak, etc.).",
        )

        if uploaded_file is not None:
            file_name = uploaded_file.name
            file_size = getattr(uploaded_file, "size", 0)

            # Pre-flight check: File size boundary
            if file_size > MAX_UPLOAD_SIZE_BYTES:
                st.error(
                    f"⚠️ **File Too Large:** `{file_name}` is {file_size / (1024 * 1024):.1f} MB. "
                    f"The maximum allowed statement upload limit is **{MAX_UPLOAD_SIZE_MB} MB**.\n\n"
                    f"Please upload a standard bank statement within the 10 MB limit."
                )
                return

            # Pre-flight check: Empty file
            if file_size == 0:
                st.error(f"⚠️ **Empty File:** `{file_name}` is empty (0 bytes). Please select a valid bank statement.")
                return

            st.caption(f"📁 Selected file: **{file_name}** ({file_size / 1024:.1f} KB)")
            file_bytes = uploaded_file.getvalue()

            # Handle CSV Processing
            if file_name.lower().endswith(".csv"):
                parse_result = parse_csv_statement(file_bytes)

                if not parse_result.success:
                    st.error(
                        f"❌ **Failed to parse CSV statement:** {parse_result.error_message}\n\n"
                        f"**Tips to resolve:**\n"
                        f"• Ensure the file is an original bank CSV export (not a spreadsheet summary).\n"
                        f"• Check that it contains columns for Date, Description, and Debit/Credit amounts."
                    )
                else:
                    _display_parse_success(parse_result, file_name, file_type="CSV", file_bytes=file_bytes)

            # Handle PDF Processing
            elif file_name.lower().endswith(".pdf"):
                st.markdown("#### 2. PDF Password (If Protected)")
                pdf_password = st.text_input(
                    "Statement Password",
                    type="password",
                    help="Many banks encrypt PDF statements with your DOB (DDMMYYYY) or Customer ID / PAN.",
                    placeholder="Enter password if your PDF is locked",
                )

                if st.button("🔓 Extract & Parse PDF Transactions", type="primary", use_container_width=True):
                    parse_result = parse_pdf_statement(file_bytes, password=pdf_password if pdf_password else None)

                    if not parse_result.success:
                        if parse_result.is_encrypted:
                            st.error(f"🔒 **Password Required / Incorrect:** {parse_result.error_message}")
                        else:
                            st.error(
                                f"❌ **Failed to parse PDF statement:** {parse_result.error_message}\n\n"
                                f"**Tips:**\n"
                                f"• Ensure this is an original digital e-statement (not a scanned image or photo).\n"
                                f"• If password-protected, verify your DOB / Customer ID format."
                            )
                    else:
                        st.session_state["latest_pdf_result"] = parse_result
                        st.session_state["latest_pdf_filename"] = file_name
                        st.session_state["latest_pdf_password"] = pdf_password

                # If previously parsed successfully in session, display preview
                if "latest_pdf_result" in st.session_state and st.session_state.get("latest_pdf_filename") == file_name:
                    _display_parse_success(
                        st.session_state["latest_pdf_result"],
                        file_name,
                        file_type="PDF",
                        file_bytes=file_bytes,
                        password=st.session_state.get("latest_pdf_password"),
                    )

    # 4. Previously Imported Statements in SQLite
    conn = get_connection()
    try:
        saved_statements = StatementRepository.list_statements(conn)
    finally:
        conn.close()

    if saved_statements:
        with st.expander(f"🗄️ Stored Statements in Local Database ({len(saved_statements)})", expanded=False):
            st.caption("These statements are securely stored in your local SQLite database (`data/app.db`).")
            for stmt in saved_statements:
                with st.container(border=True):
                    scol1, scol2, scol3 = st.columns([3, 2, 2])
                    with scol1:
                        st.markdown(f"**📄 {stmt.source_filename}** (`{stmt.source_kind.upper()}`)")
                        d_range = f"{stmt.period_start} to {stmt.period_end}" if stmt.period_start and stmt.period_end else "Full Statement"
                        st.caption(f"📅 Period: {d_range} • **{stmt.imported_count} transactions**")
                    with scol2:
                        imp_time = stmt.imported_at.strftime("%d-%b-%Y %H:%M") if stmt.imported_at else "Saved"
                        st.caption(f"🕒 Imported: {imp_time}")
                    with scol3:
                        bcol1, bcol2 = st.columns(2)
                        with bcol1:
                            if st.button("📊 Load", key=f"load_{stmt.statement_id}", use_container_width=True):
                                c = get_connection()
                                try:
                                    loaded_df = ImportService.get_active_transactions_df(c, statement_id=stmt.statement_id)
                                    st.session_state["transactions_df"] = loaded_df
                                    st.session_state["is_demo_data"] = False
                                    st.session_state["statement_filename"] = stmt.source_filename
                                    st.rerun()
                                finally:
                                    c.close()
                        with bcol2:
                            if st.button("🗑️ Delete", key=f"del_{stmt.statement_id}", use_container_width=True):
                                c = get_connection()
                                try:
                                    ImportService.delete_statement(stmt.statement_id, c)
                                    st.session_state.pop("latest_pdf_result", None)
                                    st.session_state.pop("latest_pdf_filename", None)
                                    # If active statement was this one, reset
                                    if st.session_state.get("statement_filename") == stmt.source_filename:
                                        st.session_state["transactions_df"] = None
                                        st.session_state["is_demo_data"] = True
                                        st.session_state["statement_filename"] = None
                                    st.rerun()
                                finally:
                                    c.close()

    st.divider()

    # Supported Formats Guide
    st.markdown("### 📋 Supported Statement Types")
    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("#### 📊 CSV / Excel Exports (Active)")
            st.markdown(
                """
                * **HDFC, SBI, ICICI, Axis, Kotak, PNB, Bank of Baroda**, etc.
                * Automatic handling of metadata headers and preambles.
                * Supports separate Withdrawal/Deposit columns or signed Amount + Dr/Cr types.
                * Automatic account number masking for privacy.
                """
            )

    with col2:
        with st.container(border=True):
            st.markdown("#### 📄 Digital PDF Statements (Active)")
            st.markdown(
                """
                * Digital vector PDFs downloaded from your bank's netbanking portal.
                * Automatic in-memory password unlock (passwords are never saved or sent to external servers).
                * Multi-page table extraction and column discovery.
                * *Note:* Scanned photos/image-only PDFs are not supported.
                """
            )


def _display_parse_success(
    parse_result,
    file_name: str,
    file_type: str,
    file_bytes: bytes,
    password: str = None,
) -> None:
    """Helper to display the detected schema, preview table, and database save action."""
    pages_info = f" across {parse_result.page_count} pages" if hasattr(parse_result, "page_count") and parse_result.page_count > 0 else ""
    st.success(
        f"✅ **{file_type} Statement Successfully Parsed!** Found **{parse_result.valid_rows} valid transactions**"
        f"{pages_info} (skipped {parse_result.skipped_rows} header/footer rows)."
    )

    # Show Detected Schema Mapping
    mapping = parse_result.mapping
    with st.expander("🔍 View Detected Column Mapping", expanded=True):
        map_col1, map_col2, map_col3 = st.columns(3)
        with map_col1:
            st.markdown(f"**Date Column:** `{mapping.date_col}`")
            st.markdown(f"**Description:** `{mapping.desc_col}`")
        with map_col2:
            st.markdown(f"**Debit Column:** `{mapping.debit_col or 'N/A'}`")
            st.markdown(f"**Credit Column:** `{mapping.credit_col or 'N/A'}`")
        with map_col3:
            st.markdown(f"**Single Amount:** `{mapping.amount_col or 'N/A'}`")
            st.markdown(f"**Header Row Index:** `Line {mapping.header_row_index + 1}`")

    # Preview Parsed Transactions Table
    st.markdown("#### Preview Parsed Transactions")
    preview_df = parse_result.df.head(6).copy()
    preview_df["amount_numeric"] = preview_df["amount"].apply(lambda a: float(a))

    st.dataframe(
        preview_df[["date", "merchant", "narration", "category", "mode", "type", "amount_numeric"]],
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD-MMM-YYYY"),
            "merchant": st.column_config.TextColumn("Merchant / Payee"),
            "narration": st.column_config.TextColumn("Sanitized Narration"),
            "category": st.column_config.TextColumn("Category"),
            "mode": st.column_config.TextColumn("Channel"),
            "type": st.column_config.TextColumn("Type"),
            "amount_numeric": st.column_config.NumberColumn("Amount (₹)", format="₹ %.2f"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Check for Duplicate Import in Database
    conn = get_connection()
    try:
        existing_stmt = ImportService.check_duplicate(file_bytes, conn)
    finally:
        conn.close()

    if existing_stmt is not None:
        imported_str = existing_stmt.imported_at.strftime("%d-%b-%Y %H:%M") if existing_stmt.imported_at else "earlier"
        st.info(
            f"ℹ️ **Statement Already Saved in SQLite:** This file was imported on **{imported_str}** "
            f"({existing_stmt.imported_count} transactions stored in database).",
            icon="💾",
        )
        bcol1, bcol2 = st.columns([3, 1])
        with bcol1:
            if st.button("📊 Load Saved Transactions into Active Dashboard", type="primary", use_container_width=True):
                c = get_connection()
                try:
                    df = ImportService.get_active_transactions_df(c, statement_id=existing_stmt.statement_id)
                    st.session_state["transactions_df"] = df
                    st.session_state["is_demo_data"] = False
                    st.session_state["statement_filename"] = file_name
                    st.success("🎉 Statement activated from database! Navigate to **📊 Overview Dashboard**.")
                    st.rerun()
                finally:
                    c.close()
        with bcol2:
            if st.button("🗑️ Re-import (Delete Old)", use_container_width=True):
                c = get_connection()
                try:
                    ImportService.delete_statement(existing_stmt.statement_id, c)
                    st.session_state.pop("latest_pdf_result", None)
                    st.session_state.pop("latest_pdf_filename", None)
                    st.rerun()
                finally:
                    c.close()
    else:
        # Action Button to Save into SQLite & Load into Dashboard
        if st.button("💾 Save to SQLite & Load into Dashboard", type="primary", use_container_width=True):
            save_conn = get_connection()
            try:
                import_res = ImportService.import_statement(
                    file_bytes=file_bytes,
                    filename=file_name,
                    password=password,
                    conn=save_conn,
                )
                if import_res.success:
                    st.session_state["transactions_df"] = parse_result.df
                    st.session_state["is_demo_data"] = False
                    st.session_state["statement_filename"] = file_name
                    st.success(
                        f"🎉 Saved {import_res.transactions_count} transactions to SQLite! "
                        f"Navigate to **📊 Overview Dashboard** in the sidebar."
                    )
                    st.rerun()
                else:
                    st.error(f"❌ Failed to persist statement: {import_res.error_message}")
            finally:
                save_conn.close()
