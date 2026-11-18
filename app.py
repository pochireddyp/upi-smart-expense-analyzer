"""UPI Smart Expense Analyzer - Main Streamlit Application Entrypoint.

Provides navigation routing, session state initialization, and coordinates
views across the Overview Dashboard, Statement Upload, Transactions Ledger,
and Smart Spending Insights.
"""

import streamlit as st

from dashboard.insights import render_insights
from dashboard.overview import render_overview
from dashboard.transactions import render_transactions
from dashboard.upload import render_upload
from database.db import get_connection, init_db
from database.repositories import TransactionRepository
from sample_data.generator import get_sample_transactions

# Initialize local SQLite database and apply any pending migrations
init_db()

# Configure the Streamlit page
st.set_page_config(
    page_title="UPI Smart Expense Analyzer",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def load_sample_dataset():
    """Load and cache the synthetic sample transactions."""
    return get_sample_transactions()


def main():
    """Main application orchestrator."""
    # Initialize session state for transactions dataset (prefer SQLite if data exists)
    if "transactions_df" not in st.session_state or st.session_state["transactions_df"] is None:
        conn = get_connection()
        try:
            saved_txns = TransactionRepository.get_transactions(conn)
        finally:
            conn.close()

        if saved_txns:
            st.session_state["transactions_df"] = TransactionRepository.to_dataframe(saved_txns, include_metadata=True)
            st.session_state["is_demo_data"] = False
            st.session_state["statement_filename"] = "Stored SQLite Statements"
        else:
            st.session_state["transactions_df"] = load_sample_dataset()
            st.session_state["is_demo_data"] = True
            st.session_state["statement_filename"] = None

    df = st.session_state["transactions_df"]
    is_demo = st.session_state.get("is_demo_data", True)
    active_filename = st.session_state.get("statement_filename", "Demo Dataset")

    # --- Sidebar Navigation ---
    with st.sidebar:
        st.title("💳 UPI Analyzer")
        st.caption("Version: `1.0.0` • **Phase 11 Complete**")

        st.divider()

        # View Selector
        selected_view = st.radio(
            "Navigation",
            options=[
                "📊 Overview Dashboard",
                "📥 Upload Statement",
                "📑 Transactions Ledger",
                "💡 Smart Insights",
                "ℹ️ About & Privacy",
            ],
            index=0,
            label_visibility="collapsed",
        )

        st.divider()

        # Active Data Mode
        st.subheader("Data Source")
        if is_demo:
            st.info("🎲 **Active Mode:** Synthetic Demo Data (184 Transactions)", icon="ℹ️")
        else:
            st.success(f"📊 **Live Statement:** `{active_filename}` ({len(df)} txns)", icon="✅")
            if st.button("🔄 Reset to Demo Data", key="sidebar_reset_btn", use_container_width=True):
                st.session_state["transactions_df"] = None
                st.session_state["is_demo_data"] = True
                st.session_state["statement_filename"] = None
                st.rerun()

        st.divider()

        # Hosting & Privacy Badge
        st.caption("🔒 **Security & Cloud Disclosure:**")
        st.caption(
            "When running on Streamlit Community Cloud, uploaded files are processed "
            "in ephemeral memory on the hosting server. In local desktop mode, processing "
            "remains 100% on your device."
        )

    # --- Main Header ---
    st.title("💳 UPI Smart Expense Analyzer")
    st.caption("Intelligent, privacy-respecting financial analysis for personal UPI transactions")

    # --- View Routing ---
    if selected_view == "📊 Overview Dashboard":
        render_overview(df)
    elif selected_view == "📥 Upload Statement":
        render_upload()
    elif selected_view == "📑 Transactions Ledger":
        render_transactions(df)
    elif selected_view == "💡 Smart Insights":
        render_insights(df)
    elif selected_view == "ℹ️ About & Privacy":
        render_about_page()


def render_about_page():
    """Render the About, Privacy, and Architecture overview screen."""
    st.subheader("Welcome to Your Personal Financial Companion")
    st.markdown(
        """
        **UPI Smart Expense Analyzer** is designed to give you clarity and control over
        your daily UPI transactions without sacrificing financial precision.

        ### Why This App Exists
        UPI has made payments effortless, but keeping track of dozens of daily micro-transactions
        across tea stalls, groceries, ride-hailing, subscriptions, and transfers can quickly become
        overwhelming. This application helps you make sense of that data.

        ### Core Architectural Pillars
        * **🛡️ Transparent Local Privacy:** In local desktop mode, your bank statements never leave your device.
        * **🎯 Exact Financial Precision:** Powered by Python's `decimal.Decimal` and integer paise database storage.
        * **📄 Intelligent Ingestion:** Format-agnostic handling designed to ingest diverse bank CSV exports and digital PDF statements.
        * **🏷️ Automated Categorization:** Rules-based classification of UPI merchants, peer transfers, reversals, and recurring expenses.
        * **💡 Actionable Insights:** Discover recurring subscriptions, visualize monthly cash flows, and optimize savings.
        """
    )

    st.warning(
        """
        **⚠️ Public Demo Deployment Warning:**
        * **Do NOT upload real personal financial statements to public demo servers or shared web links.**
        * Bank statements contain confidential information (e.g., your name, full transaction history, balances).
        * On public shared instances, other users could potentially view active session data.
        * For real personal financial statements, **always run the application locally on your own computer**.
        * For testing public deployments, use the provided synthetic sample files in `sample_data/`.
        """,
        icon="⚠️",
    )

    with st.container(border=True):
        st.markdown("### 🔒 Privacy, Security & Storage Characteristics")
        st.markdown(
            """
            * **Local SQLite Persistence:** When running locally, imported statements and transactions are saved
              in a local SQLite database (`data/app.db`) on your disk. Records persist between application restarts.
            * **Streamlit Community Cloud Storage Limitations:** On Streamlit Community Cloud or containerized hosting,
              the filesystem is ephemeral. Data saved to `data/app.db` will be wiped whenever the container restarts or reboots.
              Cloud data persistence is neither guaranteed nor supported.
            * **Zero Banking API Integration:** The application has **no direct integration** with bank APIs, Netbanking,
              or Account Aggregators. All data enters solely via files you choose to upload.
            * **Zero Cloud AI Services:** Based on code inspection, the application uses **zero third-party cloud LLM or AI APIs**
              (such as OpenAI, Gemini, or Claude). Categorization and analytics execute purely via local deterministic algorithms.
            """
        )

    with st.container(border=True):
        st.markdown("### ⚠️ Known Technical Boundaries & Limitations")
        st.markdown(
            """
            * **Upload Size Restrictions:** Statement file uploads are restricted to a maximum size of **10 MB** (`MAX_UPLOAD_SIZE_BYTES`).
              Standard monthly or multi-year bank statements typically stay well within 50 KB to 5 MB.
            * **PDF Parsing Boundaries:** The parser supports digital vector PDFs downloaded directly from bank netbanking portals.
              **Scanned photocopies, image-only PDFs, and camera photos are NOT supported** because the application does not bundle external OCR engines.
            * **Account Number Masking Limitations:** The application automatically masks 8- to 18-digit consecutive numeric patterns (`••••XXXX`).
              However, highly non-standard bank narrations containing non-numeric account masks or text-based account representations may not be captured.
            * **Single-User Architecture:** The application is architected as a single-user personal desktop utility. It does not provide multi-tenant authentication, user roles, or remote multi-user synchronization.
            """
        )

    st.info(
        """
        **Project Status — Phase 11 Complete**

        All 11 implementation phases, including financial precision (`Decimal`), format-agnostic CSV/PDF ingestion,
        SQLite persistence, multi-stage categorization, custom rules with ReDoS protection, manual category overrides
        with audit logging, multi-format report exports (CSV, multi-sheet Excel with openpyxl, executive PDF with PyMuPDF),
        performance optimization, and reliability hardening have been completed and verified across 149 automated tests.
        """,
        icon="ℹ️",
    )


if __name__ == "__main__":
    main()
