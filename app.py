"""UPI Smart Expense Analyzer - Main Streamlit Entry Point.

This module serves as the primary user interface for the UPI Smart Expense
Analyzer application. It introduces users to the application's goals,
architecture, and privacy-first design principles.
"""

import streamlit as st

# Configure the Streamlit page
st.set_page_config(
    page_title="UPI Smart Expense Analyzer",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Application Header
st.title("💳 UPI Smart Expense Analyzer")
st.caption("A private, local-first intelligence tool for your UPI expenses")

st.divider()

# Welcome & Purpose Section
st.subheader("Welcome to Your Personal Financial Companion")
st.markdown(
    """
    **UPI Smart Expense Analyzer** is designed to give you clarity and control over
    your daily UPI transactions without sacrificing your personal privacy.

    ### Why This App Exists
    UPI has made payments effortless, but keeping track of dozens of daily micro-transactions
    across tea stalls, groceries, ride-hailing, subscriptions, and transfers can quickly become
    overwhelming. This application helps you make sense of that data.

    ### Core Pillars
    * **🔒 100% Local-First & Private:** Your bank statements never leave your device.
      There are no third-party cloud APIs, external analytics, or remote tracking.
    * **📄 Intelligent Ingestion:** Format-agnostic handling designed to ingest diverse bank
      CSV exports and PDF statements.
    * **🏷️ Automated Categorization:** Smart classification of UPI merchants, peer transfers,
      reversals, and regular household expenses.
    * **💡 Actionable Insights:** Discover recurring subscriptions, visualize monthly
      cash flows, and receive grounded recommendations to optimize your savings.
    """
)

# Project Status & Roadmap Notice
st.info(
    """
    **Project Status — Phase 1: Foundation Setup**

    The core project scaffolding, configuration, and environment have been initialized.
    Transaction ingestion, statement parsing (CSV/PDF), and analytics pipelines will be
    introduced in upcoming modules in accordance with the technical architecture.
    """,
    icon="ℹ️",
)

# Sidebar with quick project metadata
with st.sidebar:
    st.header("About Project")
    st.markdown("**Version:** `0.1.0-dev`")
    st.markdown("**Environment:** `Local Mode`")
    st.markdown("**Tech Stack:** Python 3.12, Streamlit, Pandas, PyMuPDF, Plotly")
    st.divider()
    st.markdown("Developed with a strict focus on privacy and financial accuracy.")
