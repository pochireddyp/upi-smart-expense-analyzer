# 💳 UPI Smart Expense Analyzer

**UPI Smart Expense Analyzer** is an intelligent, local-first personal financial management application designed to help individuals analyze, categorize, and gain actionable insights from Unified Payments Interface (UPI) transaction records and bank statements.

---

## 🌟 Overview & Core Principles

UPI micro-transactions (groceries, food deliveries, ride-hailing, tea stalls, utility bills, and peer-to-peer transfers) accumulate rapidly, making monthly bank statements difficult to reconcile. Many web-based financial tools require transmitting sensitive bank statements to third-party cloud servers or paid AI APIs.

**UPI Smart Expense Analyzer** adheres to three non-negotiable architectural principles:
1. **🔒 100% Local-First Processing:** In local desktop mode, your financial statements, transaction narrations, and personal records remain entirely on your computer. All parsing, categorization, and analytics execute locally with zero cloud AI API dependencies.
2. **🎯 Financial Precision:** Currency amounts are calculated using Python's `decimal.Decimal` and stored as integer minor units (paise: ₹1 = 100 paise) in SQLite to guarantee zero binary floating-point roundoff errors.
3. **📐 Format-Agnostic Ingestion:** Rather than relying on rigid, hardcoded bank templates, statement structures are discovered dynamically through header and column mapping algorithms, supporting diverse Indian bank statements (HDFC, SBI, ICICI, Axis, Kotak, etc.).

---

## 📍 Project Roadmap & Milestones

The project was developed in 11 sequential, test-driven phases:

| Phase | Milestone | Status | Details |
| :---: | :--- | :---: | :--- |
| **Phase 1** | **Foundation & Scaffolding** | ✅ Completed | Directory architecture, dependency management, `.gitignore`, initial Streamlit shell. |
| **Phase 2** | **Technical Architecture** | ✅ Completed | System architecture documented in `TECHNICAL_ARCHITECTURE.md`. |
| **Phase 3** | **Financial Precision Foundation** | ✅ Completed | `modules/money.py` implemented (`Decimal` math, paise conversion, INR formatting, 18 tests). |
| **Phase 4** | **UI/UX Design Specification** | ✅ Completed | 12-section design blueprint in `UI_DESIGN.md` and gap analysis review completed. |
| **Phase 5** | **Dashboard UI Shell & Mock Data** | ✅ Completed | Interactive Streamlit dashboard, Plotly charts, KPI metrics, synthetic data generator, 27 tests. |
| **Phase 6** | **CSV Statement Processing** | ✅ Completed | Format-agnostic CSV parser, schema detector, preamble skipping, Decimal normalization, 36 tests. |
| **Phase 7** | **PDF Statement Processing** | ✅ Completed | Digital vector PDF parsing, in-memory password unlock, scanned document detection, 44 tests. |
| **Phase 8** | **SQLite Storage & Domain Models** | ✅ Completed | Strongly-typed dataclasses, schema migrations, paise precision, duplicate detection, 57 tests. |
| **Phase 9** | **Categorization & Smart Insights** | ✅ Completed | Gateway peeling, cadence subscription discovery, Decimal analytics, 86 tests. |
| **Phase 10** | **Overrides, Custom Rules & Exports** | ✅ Completed | Category overrides, audit trails, custom rules, rule promotion, CSV/Excel/PDF exports, 127 tests. |
| **Phase 11** | **Performance, Security & Finalization**| ✅ Completed | Vectorized analytics (8.5x speedup), 10 MB upload guard, UTF-8 standardization, 149 tests. |

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.11 / 3.12 | Core programming language |
| **Web Interface** | Streamlit (`1.67.0`) | Interactive web application framework |
| **Data Processing** | Pandas (`3.1.1`) & NumPy | Vectorized tabular operations and data manipulation |
| **PDF Extraction & Reports** | PyMuPDF (`pymupdf 2.1`) | High-speed PDF table extraction and executive PDF report generation |
| **Excel Generation** | openpyxl (`3.1.5`) | Multi-sheet formatted Excel (`.xlsx`) workbook generation with styling and borders |
| **Visualizations** | Plotly (`7.1.0`) | Interactive spending trendlines, bar charts, and category donut breakdowns |
| **Local Database** | SQLite (`sqlite3`) | Embedded database with WAL journal mode and foreign key enforcement |
| **Testing Suite** | Pytest (`9.2.0`) | Automated unit, regression, and security testing suite (149 tests) |

---

## 📁 Project Folder Structure

```
upi-smart-expense-analyzer/
│
├── app.py                      # Main Streamlit application entry point & router
├── requirements.txt            # Pinned dependencies (clean UTF-8 encoded)
├── README.md                   # Setup guide, execution commands, and project documentation
├── AGENTS.md                   # Architecture standards and coding guidelines
├── TECHNICAL_ARCHITECTURE.md   # System architecture & component specifications
├── UI_DESIGN.md                # Dashboard UI/UX wireframes and component specs
├── .gitignore                  # Excludes venv, personal statements, DBs, and secrets
│
├── .streamlit/                 # Streamlit configuration
│   └── config.toml             # Zero-telemetry, 10 MB upload limit, XSRF protection
│
├── config/                     # Configuration taxonomies
│   └── __init__.py
│
├── dashboard/                  # Streamlit UI views and widgets
│   ├── __init__.py
│   ├── charts.py               # Pure Plotly figure builders (Trendline, Donut)
│   ├── overview.py             # Executive KPI metrics and financial summaries
│   ├── upload.py               # Statement ingestion dropzone & password prompt
│   ├── transactions.py         # Multi-filter ledger, category overrides, rules & exports
│   └── insights.py             # Recurring subscription discovery & micro-spend analysis
│
├── database/                   # SQLite database models, connections, and migrations
│   ├── __init__.py
│   ├── db.py                   # Connection factory, WAL pragma, and migration runner
│   ├── repositories.py         # Account, Statement, and Transaction data repositories
│   ├── rules_repository.py     # Custom rules data access, CRUD, and ReDoS validation
│   └── migrations/             # SQL schema migration files
│       ├── 001_initial_schema.sql             # Initial DDL for accounts, statements, txns
│       └── 002_user_rules_and_overrides.sql   # DDL for rules, overrides tracking, audit log
│
├── modules/                    # Pure business logic and domain calculations
│   ├── __init__.py
│   ├── models.py               # Strongly-typed domain dataclasses (Account, Statement, Txn, Rule)
│   ├── money.py                # Exact Decimal money arithmetic & INR formatter
│   ├── categorizer.py          # Gateway prefix peeling, multi-stage classifier, nature detection
│   ├── analytics.py            # Vectorized monthly cash flows, category shares, 50/30/20 buckets
│   ├── recurring.py            # Cadence analysis, autopay detection, subscription cataloguer
│   ├── advisor.py              # Explainable recommendation rules & data sufficiency guards
│   ├── exporter.py             # CSV (formula safe), Excel (openpyxl), and PDF (PyMuPDF)
│   ├── normalizer.py           # Shared merchant cleaning, category & channel heuristics
│   ├── schema_detector.py      # Column alias detection & preamble header finder
│   ├── csv_parser.py           # Format-agnostic CSV parser, validator & normalizer
│   └── pdf_parser.py           # PyMuPDF digital table extractor & password unlocker
│
├── services/                   # Application use-case orchestrators
│   ├── __init__.py
│   ├── import_service.py       # ImportService: SHA-256 duplicate detection & atomic persistence
│   ├── overrides_service.py    # OverridesService: Atomic manual overrides & audit logs
│   └── rules_service.py        # RulesService: Custom rules, promotion, and batch evaluation
│
├── data/                       # Local runtime data directory (git-ignored)
│   ├── app.db                  # Local SQLite database file (created at runtime)
│   └── uploads/                # Transient staging for uploads (auto-cleaned)
│
├── exports/                    # User export directory for reports (git-ignored)
│
├── sample_data/                # Synthetic sample statements for demos and testing
│   ├── __init__.py
│   ├── generator.py            # Generates realistic mock UPI transactions with Decimals
│   ├── create_sample_pdfs.py   # Generates test fixtures (digital & encrypted PDFs)
│   ├── sample_hdfc_statement.csv # Synthetic HDFC CSV statement (separate Dr/Cr cols)
│   ├── sample_sbi_statement.csv  # Synthetic SBI CSV statement (with metadata preamble)
│   ├── sample_hdfc_statement.pdf # Synthetic multi-page HDFC PDF statement
│   ├── sample_locked_statement.pdf # Synthetic encrypted PDF statement (pw: password123)
│   └── sample_scanned_stub.pdf   # Synthetic scanned stub PDF (for rejection testing)
│
└── tests/                      # Automated test suite (149 passing tests)
    ├── __init__.py
    ├── test_smoke.py           # Smoke tests verifying package discoverability
    ├── test_app_smoke.py       # Syntax and UI structure verification tests
    ├── test_money.py           # Unit tests for Decimal financial precision
    ├── test_dashboard.py       # Unit tests for charts and sample data generation
    ├── test_csv_parser.py      # Unit tests for CSV parsing and schema detection
    ├── test_pdf_parser.py      # Unit tests for PDF parsing, decryption and validation
    ├── test_database.py        # Unit tests for SQLite persistence, repositories & ImportService
    ├── test_categorizer.py     # Unit tests for merchant cleaning, nature & brand classification
    ├── test_analytics.py       # Unit tests for monthly summaries, shares, and micro-spends
    ├── test_recurring.py       # Unit tests for subscription and recurring charge detection
    ├── test_advisor.py         # Unit tests for grounded recommendations & safety guards
    ├── test_migration_002.py   # Unit tests for migration 002, rules repository & ReDoS protection
    ├── test_overrides_service.py # Unit tests for manual overrides and audit trails
    ├── test_rules_service.py   # Unit tests for custom rules matching, promotion and rollback
    ├── test_exporter.py        # Unit tests for CSV, Excel, and PDF report exporters
    ├── test_dashboard_phase10.py # Unit tests for multi-filtering, override UI, and export flows
    ├── test_stage1_app_verification.py # Integration tests for end-to-end ingestion and views
    └── test_reliability_and_security.py # Reliability, size limits, rollback, and privacy tests
```

---

## 🚀 Installation & Local Execution

### 1. Prerequisites
- **Python 3.11** or **Python 3.12** installed on your system.
- Check your Python version:
  ```powershell
  python --version
  ```

### 2. Set Up a Virtual Environment

It is recommended to use an isolated Python virtual environment.

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`)*

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

### 4. Run the Application
Start the Streamlit application:
```powershell
streamlit run app.py
```
Streamlit will automatically open your default browser at:
```
http://localhost:8501
```

---

## 📥 Statement Upload & Ingestion Instructions

1. Select **"📥 Upload Statement"** from the sidebar navigation.
2. Drag and drop any official bank statement in **CSV** or **PDF** format (HDFC, SBI, ICICI, Axis, Kotak, etc.).
   * *Available synthetic fixtures in `sample_data/` for testing:*
     - `sample_data/sample_hdfc_statement.csv`: HDFC layout with separate Debit and Credit columns.
     - `sample_data/sample_sbi_statement.csv`: SBI layout with an 8-line metadata preamble.
     - `sample_data/sample_hdfc_statement.pdf`: Multi-page digital vector PDF statement.
     - `sample_data/sample_locked_statement.pdf`: Password-encrypted PDF (**Password: `password123`**).
3. **Password-Protected PDFs:** If your PDF is encrypted, enter your statement password (often your DOB or Customer ID) and click **"🔓 Extract & Parse PDF Transactions"**. Decryption occurs strictly in-memory; passwords are never saved, persisted, or logged.
4. **Automated Normalization:** The ingestion pipeline automatically:
   - Skips preamble lines and locates the transaction header.
   - Maps column aliases to canonical fields (`date`, `narration`, `amount`, `type`).
   - Normalizes amounts to `Decimal` currency precision.
   - Peels payment gateway prefixes (`RAZORPAY*`, `PAYU*`, `BILLDESK*`) to reveal the true merchant.
   - Masks sensitive 8–18 digit account numbers (`••••7890`).
5. **Database Persistence:** Click **"💾 Save to SQLite & Load into Dashboard"** to persist the statement in your local database (`data/app.db`).
6. **Active Statement Management:** You can reload, view, or delete saved statements anytime under **"🗄️ Stored Statements in Local Database"**.

---

## ⚙️ Features & Functionality

### 1. Executive Dashboard (`dashboard/overview.py`)
- **KPI Summary Cards:** Total Spend, Inward Income, Net Cash Flow, and Savings Rate (with data sufficiency guards).
- **Macro-Budgeting Breakdown:** 50/30/20 allocation comparing Needs, Wants, and Savings.
- **Visualizations:** Interactive Plotly monthly spend trendline and category distribution donut chart.

### 2. Multi-Filter Ledger (`dashboard/transactions.py`)
- **6-Way Filter Matrix:**
  - Date Range (Start / End Date).
  - Bank Account selector.
  - Multi-select Categories.
  - Direction (`DEBIT`, `CREDIT`, or All).
  - Amount Range (Min / Max slider).
  - Free-Text Search across merchant names and narrations.
- Filter state applies consistently across the table view, analytics summaries, and exported files.

### 3. Manual Category Overrides & Audit Log (`services/overrides_service.py`)
- Change any transaction's category with an optional reason.
- **Non-Destructive Invariant:** The original auto-detected category is permanently preserved in `original_category_id`.
- Sets `category_source = 'user_override'` and resets `applied_rule_id = NULL`.
- Inserts an immutable audit record into `category_overrides_audit` in an atomic database transaction.

### 4. Custom Categorization Rules & Rule Promotion (`services/rules_service.py`)
- Author custom rules using 4 pattern strategies:
  - `merchant_exact`: Case-insensitive exact match.
  - `merchant_contains`: Case-insensitive substring match.
  - `narration_contains`: Substring match on raw bank narration.
  - `regex`: Regular expression with strict ReDoS validation (rejects nested quantifiers and patterns over 200 characters).
- **Deterministic Priority & Tie-Breaking:** Evaluated in order of `priority DESC`, `LENGTH(pattern) DESC`, `created_at ASC`, `rule_id ASC`.
- **Override Immutability:** Rule evaluations **never overwrite** transactions marked with `category_source == 'user_override'`.
- **Rule Promotion:** Promote any manual override into a persistent rule with one click.
- **Bidirectional Reversion:** Inactivating or deleting a rule automatically reverts affected transactions to their `original_category_id`.

### 5. Smart Spending Insights (`dashboard/insights.py`)
- **Recurring Payment Detection:** Cadence analysis identifies monthly subscriptions, autopay mandates, and recurring fees with amount variance tolerance.
- **Micro-Spend Profiling:** Identifies high-frequency micro-purchases under ₹150 (tea, snacks, quick deliveries) that silently accumulate.
- **Weekday vs. Weekend Spending Velocity:** Measures discretionary spending surge between weekdays and weekends.

### 6. Multi-Format Report Exports (`modules/exporter.py`)
- **CSV Export:** UTF-8 with BOM (`utf-8-sig`). Features **CSV formula injection (DDE) protection** (cells starting with `=`, `+`, `-`, `@`, `\t`, `\r` are prefixed with `'`).
- **Excel Export (`.xlsx`):** Formatted multi-sheet workbook using `openpyxl`:
  - `Transaction Ledger`: Formatted data table with INR currency styling (`#,##0.00`).
  - `Category Breakdown`: Category totals, macro buckets, share of wallet (`0.0%`), and transaction counts.
  - `Monthly Cashflow`: Inflows, outflows, routine spend, income, net cash flow, and savings rates (`N/A` when income is unavailable).
- **Executive PDF Report:** Clean A4 portrait layout generated via PyMuPDF (`pymupdf`) with navy header, period metadata, KPI cards, category breakdown, top payees, and privacy notices.
- **Sanitization Invariant:** All exports exclude internal database primary keys (`txn_id`, `statement_id`, `account_id`, `file_sha256`) and mask sensitive account numbers.

---

## ⚡ Performance & Scalability Benchmarks

Stage 2 performance testing profiled the application using deterministic synthetic datasets across 1,000, 10,000, and 50,000 transactions:

| Operation | Dataset Size ($N$) | Baseline Time | Optimized Time | Speedup Factor | Latency Reduction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`calculate_monthly_summary`** | 1,000 | 0.0617s | **0.0109s** | **5.7x** | -82.3% |
| | 10,000 | 0.6489s | **0.0825s** | **7.9x** | -87.3% |
| | 50,000 | 3.2414s | **0.4303s** | **7.5x** | -86.7% |
| **`calculate_category_breakdown`** | 1,000 | 0.0302s | **0.0034s** | **8.9x** | -88.7% |
| | 10,000 | 0.3190s | **0.0311s** | **10.3x** | -90.3% |
| | 50,000 | 1.6737s | **0.1638s** | **10.2x** | -90.2% |
| **`calculate_top_merchants`** | 1,000 | 0.0222s | **0.0057s** | **3.9x** | -74.3% |
| | 10,000 | 0.2294s | **0.0237s** | **9.7x** | -89.7% |
| | 50,000 | 1.1778s | **0.1219s** | **9.7x** | -89.6% |
| **Total Analytics Compute (50k)** | **50,000** | **6.0929s** | **0.7160s** | **8.5x faster** | **-88.2%** |
| **`export_transactions_excel`** | 10,000 | 5.4464s | **3.6013s** | **1.5x** | -33.9% |
| | 50,000 | 27.0028s | **23.6256s** | **1.14x** | -12.5% |

*Key Optimizations:*
- Eliminated `df.iterrows()` and `.to_dict()` overhead in favor of vectorized column list extraction (`.tolist()`) and single-pass iteration.
- Optimized Excel export column width calculation on the ledger sheet by sampling headers and up to 100 rows, avoiding scanning 350,000 openpyxl cell objects.

---

## 🔒 Privacy & Security Disclosures

> [!WARNING]
> **Avoid Uploading Real Financial Statements to Public Deployments:**
> Bank statements contain sensitive personal data (full legal name, bank account numbers, transaction histories, merchant details, and financial balances).
> **If you are accessing this application on a public or shared demo deployment (e.g., Streamlit Community Cloud), DO NOT upload real personal bank statements.** Use the provided synthetic test statements in `sample_data/`.
> For real personal financial statements, **always run the application locally on your own computer**.

### 1. Local SQLite Persistence vs. Cloud Ephemeral Storage
- **Local Desktop Execution:** In local desktop mode, imported statements and transactions are persisted in your local SQLite database at `data/app.db`. Transactions persist permanently between application restarts.
- **Streamlit Community Cloud Limitation:** On Streamlit Community Cloud or containerized hosting platforms, the filesystem is ephemeral. Data written to `data/app.db` will be wiped whenever the container restarts or reboots. Cloud persistence is neither guaranteed nor supported.

### 2. Zero Banking API & Zero Cloud AI Integration
- **No Banking API Integration:** The application does not connect to bank servers, Netbanking portals, or Account Aggregator frameworks. All data enters solely through user-provided CSV or PDF files.
- **No Cloud AI / LLM APIs:** Based on code inspection, the application uses **zero third-party cloud AI or LLM APIs** (such as OpenAI, Gemini, or Claude). Categorization, pattern matching, and recommendations execute purely via local deterministic rules.
- **Zero Outbound Telemetry:** Streamlit telemetry is explicitly disabled (`gatherUsageStats = false` in `.streamlit/config.toml`).

### 3. Account Number Masking Limitations
- The application automatically masks 8- to 18-digit consecutive numeric sequences in transaction narrations, replacing all but the last 4 digits (`••••7890`).
- *Limitation:* Account numbers formatted with unusual separators, non-numeric masks, or textual representations not matching the `\b(\d{4,14})(\d{4})\b` pattern may not be automatically masked.

### 4. PDF Statement Extraction Limitations
- The application parses **digital vector PDFs** containing extractable text streams, as downloaded directly from netbanking portals.
- *Limitation:* **Scanned paper photocopies, camera photographs, and image-only PDFs are NOT supported.** Scanned PDFs are detected and rejected with a clear message to prevent corrupted data ingestion.

### 5. File Upload Size Restrictions
- Uploads are capped at a maximum of **10 MB** (`MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024`) in both `.streamlit/config.toml` and application-level validation.
- Files exceeding 10 MB are rejected immediately before reading into memory to prevent memory exhaustion and denial-of-service.

---

## 🧪 Testing & Verification

Run the automated test suite with `pytest`:

```powershell
pytest
```

For verbose, test-by-test output:
```powershell
pytest -v
```

All **149 unit, integration, and security tests** pass with zero failures:
```
============================ 149 passed in 47.15s =============================
```

### Test Coverage Breakdown
- `test_money.py`: 18 tests for Decimal precision, paise conversion, and INR formatting.
- `test_csv_parser.py`: 9 tests for schema detection, preamble handling, and column mapping.
- `test_pdf_parser.py`: 8 tests for vector PDF extraction, password decryption, and scanned rejection.
- `test_database.py`: 11 tests for SQLite migrations, foreign keys, and atomic rollbacks.
- `test_categorizer.py`: 12 tests for gateway peeling, brand matching, and nature detection.
- `test_analytics.py`: 7 tests for monthly cash flow, category breakdown, and micro-spends.
- `test_recurring.py`: 5 tests for recurring payments and autopay detection.
- `test_advisor.py`: 6 tests for grounded recommendations and safety guards.
- `test_migration_002.py`: 4 tests for migration 002, rules schema, and ReDoS protection.
- `test_overrides_service.py`: 7 tests for manual overrides, original category preservation, and audit logging.
- `test_rules_service.py`: 7 tests for custom rules matching, priority resolution, and rollback.
- `test_exporter.py`: 11 tests for CSV injection protection, Excel formatting, and PDF reports.
- `test_dashboard_phase10.py`: 6 tests for multi-filtering, override UI, and rule promotion.
- `test_stage1_app_verification.py`: 7 integration tests for synthetic statements and dashboard views.
- `test_reliability_and_security.py`: 15 tests for upload boundaries, size limits, atomicity, and privacy.

---

## ⚠️ Known Technical Limitations

1. **Single-User Architecture:** Designed as a personal, local desktop tool. It does not provide multi-tenant authentication, user permission levels, or multi-user cloud synchronization.
2. **Scanned PDF Support:** Requires digital e-statements. Scanned photocopies or photos from mobile cameras cannot be parsed without external OCR engines.
3. **Streamlit State Management:** Uploading or deleting statements causes a Streamlit UI rerun to refresh database state.
4. **Bank Statement Layout Diversity:** While format-agnostic heuristics cover major Indian banks, statements with non-standard column naming or unstructured free-form text may require custom column mapping.

---

## 📚 Development Guidelines

- Consult [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md) for architectural blueprints, state machines, and data flow specifications.
- Consult [UI_DESIGN.md](UI_DESIGN.md) for component mappings, wireframes, and Plotly chart configurations.
- Consult [AGENTS.md](AGENTS.md) for monetary precision rules, local-first invariants, and coding standards.
