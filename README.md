# 💳 UPI Smart Expense Analyzer

**UPI Smart Expense Analyzer** is an intelligent, local-first desktop application designed to help individuals analyze, categorize, and gain meaningful insights from their personal Unified Payments Interface (UPI) transaction records and bank statements.

---

## 🌟 Overview & Core Principles

UPI micro-transactions (groceries, food deliveries, cab rides, bills, peer-to-peer transfers) quickly accumulate and become difficult to track across monthly bank PDF and CSV statements. Most existing expense tracking solutions require uploading sensitive financial data to third-party cloud servers.

**UPI Smart Expense Analyzer** is built with three non-negotiable principles:
1. **🔒 100% Local-First & Private:** Your financial statements, transaction narrations, and personal records never leave your computer. Processing is performed locally with zero cloud API dependencies.
2. **🎯 Financial Precision:** Currency amounts are calculated with Python's `decimal.Decimal` and stored as integer paise (minor units) in SQLite to guarantee zero floating-point calculation errors.
3. **📐 Format-Agnostic Ingestion:** Rather than assuming fixed bank layouts, statement structure is discovered and verified for maximum compatibility across various Indian banks.

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.11+ / 3.12 | Core programming language |
| **Web UI** | Streamlit | Lightweight, reactive interactive user interface |
| **Data Processing** | Pandas & NumPy | Tabular data hygiene, sorting, and aggregation |
| **PDF Extraction** | PyMuPDF (`fitz`) | High-speed layout and text extraction from bank PDFs |
| **Visualizations** | Plotly | Interactive monthly spending charts and breakdowns |
| **Local Storage** | SQLite (`sqlite3`) | Embedded, zero-configuration local database |
| **Test Framework** | Pytest | Automated unit and integration testing suite |

---

## 📁 Project Folder Structure

```
upi-smart-expense-analyzer/
│
├── app.py                      # Main Streamlit application entry point
├── requirements.txt            # Pinned dependencies for the application
├── README.md                   # Setup guide, execution commands, and project docs
├── AGENTS.md                   # Coding guidelines and rules for developers & agents
├── TECHNICAL_ARCHITECTURE.md   # Comprehensive technical architecture & system design
├── .gitignore                  # Excludes venv, personal statements, DBs, and secrets
│
├── config/                     # Application configuration & category taxonomies
│   └── __init__.py
│
├── dashboard/                  # Streamlit UI presentation screens & widgets
│   └── __init__.py
│
├── database/                   # SQLite database models, connections, and migrations
│   ├── __init__.py
│   └── migrations/             # SQL schema migration files
│
├── modules/                    # Domain logic (money math, normalizers, validators)
│   ├── __init__.py
│   └── money.py                # Exact Decimal money arithmetic & INR formatter
│
├── services/                   # Application use-case orchestrators (import, analytics)
│   └── __init__.py
│
├── data/                       # Local runtime data directory (git-ignored)
│   └── uploads/                # Transient staging for uploads (auto-cleaned)
│
├── exports/                    # User export directory for reports (git-ignored)
│
├── sample_data/                # Synthetic sample statements for demos and testing
│
└── tests/                      # Automated test suite
    ├── __init__.py
    ├── test_smoke.py           # Smoke tests verifying package discoverability
    ├── test_app_smoke.py       # Syntax and UI structure verification tests
    ├── test_money.py           # Unit tests for Decimal financial precision
    └── fixtures/               # Test fixtures (synthetic CSV/PDF data)
```

---

## 🚀 Setup & Installation Instructions

Follow these step-by-step instructions to set up the project locally:

### 1. Prerequisites
Ensure you have **Python 3.11** or **Python 3.12** installed on your system.
Verify your Python installation by running:
```powershell
python --version
```

### 2. Set Up Virtual Environment

It is strongly recommended to use an isolated Python virtual environment.

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

*(Note: If PowerShell execution policy restricts scripts, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`)*

**On Windows (Command Prompt):**
```cmd
python -m venv venv
.\venv\Scripts\activate.bat
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
Install all required packages from `requirements.txt`:
```powershell
pip install -r requirements.txt
```

---

## 🖥️ Running the Application

To launch the Streamlit web dashboard:

```powershell
streamlit run app.py
```

Once executed, Streamlit will automatically launch the application in your default web browser at:
```
http://localhost:8501
```

---

## 🧪 Running the Test Suite

Execute the automated test suite with `pytest`:

```powershell
pytest
```

To run tests with detailed verbose output:
```powershell
pytest -v
```

---

## 🛡️ Privacy & Security Safeguards

* **Private Bank Statements:** Bank statements (`*.csv`, `*.pdf`, `*.xlsx`) and SQLite databases (`*.db`) are strictly excluded via `.gitignore` to prevent inadvertent commits to version control.
* **Transient Staging:** Uploaded statements are staged locally in `data/uploads/` only during processing and cleaned up immediately.
* **Sensitive Info Redaction:** Sensitive details such as full bank account numbers, debit card numbers, and virtual payment addresses (VPAs) are masked before persisting or logging.

---

## 📚 Development Guidelines

Please consult:
* [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md) for detailed architectural blueprints, state machines, and data flow designs.
* [AGENTS.md](AGENTS.md) for developer standards, monetary precision rules, and coding conventions.
