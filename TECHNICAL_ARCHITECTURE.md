# UPI Smart Expense Analyzer — Technical Architecture

**Document type:** Technical Architecture Document (TAD)
**Status:** Draft v1.0 — design only, no implementation yet
**Audience:** Beginner/intermediate Python developers, reviewers, future maintainers
**Scope:** Local-first, single-user desktop/web app that ingests bank statements (CSV/PDF), extracts transactions, categorizes them, analyzes spending, and generates savings suggestions.

---

## 0. Reading guide

This document is written to be read top to bottom, but each section stands alone:

| If you want to know... | Read |
| --- | --- |
| How the pieces fit together | §1, §4, §5 |
| Why each library was chosen | §2 |
| What happens when a user uploads a file | §3 |
| How the database and money types work | §6, §7 |
| How parsing handles "every bank is different" | §9 |
| How totals/savings are calculated exactly | §10 |
| How categories are assigned | §11 |
| How recommendations are produced | §12 |
| Privacy and safety rules | §13 |
| How it is tested and shipped for free | §14, §15 |

**Guiding principles (apply to every decision below):**

1. **Local-first.** Statements never leave the machine by default. No cloud API is on the critical path.
2. **Format-agnostic.** No parser assumes a fixed bank layout. Layout is *discovered*, then *confirmed* by the user.
3. **Exact money.** All arithmetic uses `decimal.Decimal`, never `float`. Storage uses integer minor units (paise).
4. **Explainable.** Every total, category, and recommendation can be traced back to specific transaction rows.
5. **Beginner-friendly.** One Python process, one SQLite file, plain modules, no message queues, no containers required to run locally.

---

## 1. System architecture

### 1.1 Architectural style

**A layered monolith**, delivered as a Streamlit app, with a strict one-way dependency rule:

```
UI  ->  Application services  ->  Domain (money, transactions)  ->  Data access  ->  SQLite
```

Why a monolith and not microservices:

- The workload is one user, one file at a time. Concurrency is negligible.
- A single process is far easier to debug for a beginner than 4 services plus a broker.
- Everything is a plain Python import; you can run a parser from a REPL or a test without booting the UI.
- The layering still gives us the main benefit of services: parsers, categorizer, and analytics are testable in isolation and replaceable later (e.g., swapping rule-based categorization for ML) without touching the UI.

### 1.2 Layers

| Layer | Responsibility | Must NOT do |
| --- | --- | --- |
| **Presentation** (`app.py`, `dashboard/`) | Screen layout, widgets, navigation, Plotly figures, user confirmation dialogs | Business rules, parsing, SQL |
| **Application / services** (`modules/`) | Orchestrate a use case: import a statement, recategorize, build a report | Render UI, open DB connections directly |
| **Domain** (`modules/money.py`, `models.py` dataclasses) | Money type, transaction entity, invariants, sign conventions | I/O of any kind |
| **Data access** (`database/db.py`, `database/repositories.py`) | SQL, transactions, migrations, schema templates | Business logic, formatting |
| **Storage** | `data/app.db` (SQLite), `data/uploads/` (transient) | — |

Dependency direction is enforced by convention and by a test that imports each module and asserts no `modules.*` file imports `dashboard.*` or `streamlit`.

### 1.3 Component view

```
+------------------------------------------------------------------+
|                        Streamlit UI (app.py)                     |
|  Pages: Upload | Review & Fix | Transactions | Dashboard |       |
|         Insights | Settings | Export                             |
+-------------------------------+----------------------------------+
                                | calls service functions
+-------------------------------v----------------------------------+
|                      Application services                        |
|                                                                  |
|  ImportService      CategorizationService     AnalyticsService   |
|  (orchestrator)     (rules + overrides)       (aggregations)     |
|  AdvisorService     ExportService             SettingsService    |
+------+------------------+------------------+---------------------+
       |                  |                  |
+------v------+    +------v------+    +------v------------------+
|  Ingestion  |    |  Analysis   |    |  Domain / shared        |
|             |    |             |    |                         |
| file_upload |    | categorizer |    | money.py  (Decimal)     |
| csv_parser  |    | analytics   |    | models.py (dataclasses) |
| pdf_parser  |    | advisor     |    | constants.py            |
| schema_     |    | recurring   |    | logging_utils.py        |
|  detector   |    |             |    | validators.py           |
| normalizer  |    |             |    |                         |
| deduplicator|    |             |    |                         |
+------+------+    +------+------+    +------+------------------+
       |                  |                  |
+------v------------------v------------------v---------------------+
|                    Data access layer                             |
|  db.py (connection, pragmas, migrations, unit of work)           |
|  repositories.py (accounts, statements, transactions, rules...)  |
+-------------------------------+----------------------------------+
                                |
+-------------------------------v----------------------------------+
|  SQLite  data/app.db      +   data/uploads/ (temp, auto-deleted) |
+------------------------------------------------------------------+
```

### 1.4 Runtime and deployment shapes

| Mode | Storage | Network | Intended use |
| --- | --- | --- | --- |
| **Local mode** (default) | `data/app.db` on disk | None required | Real statements — the only mode for real data |
| **Demo mode** | Temporary/ephemeral SQLite, sample data prefilled | Inbound only (hosting) | Free public demo for portfolio/recruiters |
| **Test mode** | In-memory SQLite (`:memory:`) | None | Pytest |

The same codebase runs all three; a single setting (`APP_MODE`) switches storage paths and disables features that require persistence.

### 1.5 Non-functional targets

| Attribute | Target |
| --- | --- |
| Cold start | < 5 s on a laptop |
| 12-month CSV (≈3,000 rows) import | < 3 s |
| 30-page PDF import | < 10 s (text-based); OCR off by default |
| Memory ceiling | < 500 MB for a 12-month statement |
| Re-import of same file | Idempotent — zero new transactions |
| Data loss on crash | No partial statement: import is one DB transaction |
| Offline | Fully functional with no internet |

---

## 2. Technology selection and justification

| # | Technology | Version pin | Role | Why this, not something else |
| --- | --- | --- | --- | --- |
| 1 | **Python** | `>=3.11,<3.13` | Language | Huge data/PDF ecosystem, beginner-friendly, stdlib `decimal`, `csv`, `sqlite3` cover half the needs with zero dependencies. 3.11+ for speed and `tomllib`. |
| 2 | **Streamlit** | `~1.3x` | UI/UI state, multipage app | Pure Python, no HTML/JS required, built-in file uploader, `st.data_editor` for correcting parsed rows, `st.cache_data` for analytics caching. Alternatives: Flask/FastAPI + templates (more code, HTML/CSS), Dash (heavier, callback graph harder for beginners), NiceGUI (smaller community). |
| 3 | **Pandas** | `~2.x` | Tabular parsing, cleaning, grouping | Battle-tested CSV reader with encoding/delimiter/thousands-separator handling, easy column mapping, fast groupby for monthly aggregates. Used as a *transport format* only; money math uses `Decimal` (§10). |
| 4 | **PyMuPDF** | `~1.24` | PDF text + layout extraction | Very fast, gives text with coordinates and word blocks, exposes lines/tables-ish structures, handles most Indian bank e-statements. **Licence caveat:** PyMuPDF is AGPL-3.0. Fine for a personal/local project and open-source release; if you later want a closed-source or commercial distribution, swap in `pdfplumber` (MIT) or `pypdf` (BSD) behind the same `PdfTextExtractor` interface (§4.3). Keep PyMuPDF behind that interface *from day one*. |
| 5 | **Plotly** | `~5.x` | Interactive charts | Native Streamlit integration, hover tooltips, zoom, no JS. Alternatives: Matplotlib (static, less interactive), Altair (also good, but Plotly's table/treemap/sunburst suit category breakdowns better). |
| 6 | **SQLite** (stdlib `sqlite3`) | bundled | Local persistence | Zero-install, single file, transactional, supports `UPSERT`, `STRICT` tables, and is easy to back up (copy the file). Ideal for single-user local data. Alternative: DuckDB (great analytics, but a second query language mental model and weaker "row update" ergonomics for user corrections). |
| 7 | **Scikit-learn** | optional extra | Future ML categorizer | Only needed in Phase 3+. TF-IDF + linear model is small and trains in seconds on a few thousand labelled rows. Kept out of the mandatory install to keep the base app light. |
| 8 | **Pytest** | `~8.x` | Testing | Fixtures, parametrization, `tmp_path` for DB isolation, `pytest-cov` for coverage. |
| — | `chardet`/`charset-normalizer` | `charset-normalizer~3` | CSV encoding detection | Bank exports are frequently Windows-1252 or UTF-8-with-BOM; guessing wrong silently corrupts ₹ and names. |
| — | `python-dateutil` | `~2.9` | Date parsing | Indian statements mix `DD/MM/YYYY`, `DD-MMM-YY`, `YYYYMMDD`, and `01/02/24` ambiguity. `dateutil` with an explicit day-first policy is the pragmatic choice. |
| — | `rapidfuzz` | `~3.x` | Fuzzy header/merchant matching | Tolerant header mapping ("Withdrawal Amt." vs "Withdrawal Amount") without hand-writing 50 aliases. |
| — | `pytesseract` + Tesseract | **optional, off by default** | Scanned-PDF OCR fallback | Heavy (~50 MB+ native install), error-prone on tables, and adds a privacy-sensitive subprocess. Only offered with an explicit warning. |
| — | `cryptography` / `pysqlcipher3` | optional | Encryption at rest | Only if the user opts in; default is to rely on OS disk encryption (§13). |
| — | `openpyxl` | optional | `.xlsx` exports from banks | Many banks offer Excel rather than CSV; cheap to add later behind the same ingestion interface. |

**Deliberately excluded:** React/Node/JS/TypeScript (per requirement), Django (ORM + admin is overkill and hides SQL from a learner), FastAPI (no need for a second process or REST layer), any paid OCR/LLM API (cost + privacy), any analytics/telemetry SDK.

**Dependency policy:** pin exact versions in `requirements.txt`, keep runtime dependencies under ~10, put ML extras in `requirements-ml.txt`, and install with a virtual environment (`python -m venv .venv`).

---

## 3. Complete application workflow

### 3.1 Happy path (one statement)

```
[1] User opens app            -> Home/Upload page
[2] Upload CSV or PDF         -> saved to data/uploads/<uuid>.<ext>, size/type checked
[3] Detect file type          -> CSV vs PDF by extension + magic bytes
[4] Extract raw table/text    -> CSV rows | PDF text blocks
[5] Detect schema             -> identify header row, columns, date/amount formats
[6] Map columns               -> canonical field mapping (auto + user confirmation)
[7] Normalize rows            -> dates, Decimal amounts, direction, description cleanup
[8] Validate                  -> row-level rules + opening/closing balance reconciliation
[9] Deduplicate               -> hash-based, within file and against existing DB
[10] Classify special types   -> refund / reversal / transfer / fee / interest
[11] Categorize               -> rules -> merchant map -> heuristics -> Uncategorized
[12] Persist                  -> ONE transaction: statement + transactions + audit rows
[13] Review & Fix (UI)        -> user corrects rows; corrections saved as rules
[14] Analyze                  -> monthly totals, category split, trends, recurring
[15] Visualize                -> Plotly charts
[16] Advise                   -> ranked, explained recommendations
[17] Export / Delete          -> CSV/Excel export; hard delete statement on request
```

Steps 1–4 are *ingestion*; 5–8 *structuring*; 9–11 *enrichment*; 12 *persistence*; 13–17 *consumption*.

### 3.2 Sequence (import use case)

```
User          UploadPage        ImportService      Parser        SchemaDetector    Repos/DB
 |                 |                  |               |                 |              |
 |--upload file--->|                  |               |                 |              |
 |                 |--save temp file->|               |                 |              |
 |                 |                  |--parse()----->|                 |              |
 |                 |                  |<--RawTable----|                 |              |
 |                 |                  |--detect()---------------------->|              |
 |                 |<--needs mapping confirmation?---|                 |              |
 |--confirm cols-->|----------------->|               |                 |              |
 |                 |                  |--normalize/validate------------>|              |
 |                 |                  |--dedupe------------------------>|              |
 |                 |                  |--BEGIN TRANSACTION--------------------------->|
 |                 |                  |--insert statement + txns + audit------------->|
 |                 |                  |--COMMIT------------------------------------->|
 |                 |                  |--delete temp file                            |
 |<--preview + report---------------|               |                 |              |
```

### 3.3 Alternative and failure paths

| Situation | Behaviour |
| --- | --- |
| Wrong file type / > 20 MB | Reject before parsing, with a clear message; no temp file left behind |
| Password-protected PDF | Ask for password in-session (never stored); if absent, stop with instructions |
| Header row not found | Fall back to the **manual mapping wizard**: user picks which row is the header and which column is which |
| New/unknown bank | Mapping is saved as a reusable **schema template** keyed by a layout fingerprint, so the second import is one click |
| Rows fail validation | Import proceeds with *valid* rows; failures listed with row numbers and reasons, exportable; user may fix and re-import |
| Balance reconciliation fails | Warning banner showing expected vs actual closing balance and the likely cause (missing page, duplicate row, wrong sign); import still allowed but flagged |
| Re-upload of the same file | Detected by file hash; user is told "already imported on <date>" and nothing is inserted |
| User abandons mid-review | Temp file deleted by the session cleanup; no partial statement exists |

---

## 4. Module-wise architecture

Each module below lists: **purpose**, **key public functions** (names only — no implementation), **inputs → outputs**, **depends on**, and **failure behaviour**.

### 4.1 `modules/money.py` (domain foundation)

- **Purpose:** the single place where money is created, added, rounded, and formatted. If any other module does arithmetic on amounts directly, that is a bug.
- **Functions:** `to_money(value, currency="INR") -> Money`, `quantize(value)`, `sum_money(iterable)`, `pct(part, whole)`, `format_inr(money)`.
- **Rules:** `Decimal` internally; `ROUND_HALF_UP`; 2 decimal places for display and totals; storage as integer paise (§6.3); reject `float` inputs at the boundary and convert from strings.
- **Never:** parse dates, touch the DB, or format HTML.

### 4.2 `modules/file_upload.py`

- **Purpose:** validate and stage the uploaded bytes; own the temp-file lifecycle.
- **Functions:** `validate_upload(name, size, head_bytes)`, `stage_file(uploaded) -> StagedFile`, `cleanup(staged)`.
- **Checks:** extension allow-list (`.csv`, `.pdf`), magic-byte sniff (CSV has no magic; reject binary that isn't `%PDF-`), max size, sanitized filename (no path separators), SHA-256 of the content for idempotency.
- **Failure:** raises `UploadError` with a user-safe message; logs filename and size only, never content.

### 4.3 `modules/parsers/` (interface + implementations)

Define one small protocol so the rest of the app never knows whether a row came from CSV or PDF:

```text
Parser.extract(staged_file) -> RawTable
RawTable = { headers: list[str] | None, rows: list[list[str]], warnings: list[str],
             page_count: int | None, text_quality: float | None }
```

- **`csv_parser.py`** — encoding detection, delimiter sniffing, preamble skipping, ragged-row repair (§9.1).
- **`pdf_parser.py`** — text-block extraction and table reconstruction (§9.2), delegating the actual PDF library to `PdfTextExtractor` (PyMuPDF today, `pdfplumber` tomorrow).
- **`registry.py`** — `get_parser(ext)`; the only place that knows which parser exists.

Each parser has one job: produce the most faithful `RawTable` possible, plus warnings. No cleaning, no categorization.

### 4.4 `modules/schema_detector.py`

- **Purpose:** answer "which column is the date, which is the amount, and which row is the header?" without assuming a layout.
- **Functions:** `find_header_row(raw_table)`, `map_columns(headers) -> ColumnMapping`, `fingerprint(headers)`, `save_template(mapping)`, `load_template(fingerprint)`.
- **Technique:** alias dictionary + `rapidfuzz` scoring + content-based checks (does this column parse as dates ≥ 90% of the time? as numbers?). Confidence below threshold ⇒ ask the user.
- **Output:** `ColumnMapping(date, description, debit, credit, amount, direction, balance, reference, value_date, mode)` where unused fields are `None`. Supports both **split-column** (Withdrawal/Deposit) and **single-amount + direction** layouts.

### 4.5 `modules/normalizer.py`

- **Purpose:** turn mapped string rows into typed transaction drafts.
- **Functions:** `normalize_rows(rows, mapping, context) -> list[TransactionDraft]`, `parse_amount(text)`, `parse_date(text, policy)`, `clean_description(text)`.
- **Handles:** `₹`, `Rs.`, `INR`, thousands separators (`1,23,456.78` Indian grouping), trailing `Dr`/`Cr`, parentheses for negatives, non-breaking spaces, zero-width characters, `DD/MM/YY` day-first policy, two-digit years, `--`/blank placeholders.
- **Output:** drafts with `Decimal` amounts and explicit `direction`, plus per-row `warnings`.

### 4.6 `modules/validators.py`

- **Purpose:** row-level and statement-level sanity rules; decide what blocks, what warns.
- **Rules:** date within a plausible window; amount ≠ 0; exactly one of debit/credit populated (or amount+sign); balance continuity when a balance column exists; opening/closing balance reconciliation; date ordering; duplicate row-in-file; currency consistency.
- **Output:** `ValidationReport(blocking_errors, warnings, stats)`.

### 4.7 `modules/deduplicator.py`

- **Purpose:** guarantee "importing the same statement twice changes nothing".
- **Functions:** `content_hash(file_bytes)`, `txn_fingerprint(draft)`, `find_duplicates(drafts, existing)`, `decide(duplicate_candidates)`.
- **Fingerprint:** `sha256(account_id | iso_date | amount_minor | direction | normalized_description | reference_or_balance)`.
- **Nuance:** two genuinely identical small UPI payments on the same day (e.g., two ₹20 chai) must **not** be silently merged. Strategy: fingerprint includes an in-file occurrence index for ties; cross-file matches are surfaced to the user as "possible duplicate" rather than auto-deleted, unless the exact file hash matches (then auto-skip).

### 4.8 `modules/classifier.py` (special transaction types)

- **Purpose:** label refunds, reversals, transfers, fees, interest, cash withdrawals, salary.
- **Functions:** `classify(draft, context) -> TxnType + confidence`.
- **Signals:** description keywords (`REFUND`, `REVERSAL`, `FAILED`, `RETURN`, `SELF`, `IMPS to self`, `CHQ`, `ATM`, `INT.PD`, `SALARY`), matching amount against an earlier debit within N days (refund pairing), matching counterparty, debit/credit direction.
- **Rules of thumb:** a credit matching a prior debit of the same amount within 7 days and containing refund-ish text is linked as a **refund pair**; transfers between the user's own accounts are linked via `linked_txn_id` and excluded from "spending".

### 4.9 `modules/categorizer.py`

Rule-based categorization with a learning loop (§11).

- **Functions:** `categorize(draft, rules) -> Categorization`, `explain(categorization)`, `apply_bulk(txns, category)`, `promote_override_to_rule(txn, category)`.

### 4.10 `modules/analytics.py`

- **Purpose:** all aggregation. Input transactions, output frames/summaries consumed by charts and the advisor.
- **Functions:** `monthly_summary(txns)`, `category_breakdown(txns, month)`, `income_vs_expense(txns)`, `top_merchants(txns, n)`, `weekday_profile(txns)`, `trend(txns, metric)`, `recurring_candidates(txns)`.
- **Contract:** pure functions over lists of transactions; no DB calls, no Streamlit imports; returns pandas DataFrames with documented columns. Easily unit-tested and cacheable.

### 4.11 `modules/advisor.py`

- **Purpose:** convert analytics into ranked, explained recommendations (§12).
- **Functions:** `generate(txns, summary, prefs) -> list[Recommendation]`, `score(rec)`, `render_text(rec)`.

### 4.12 `modules/recurring.py`

- **Purpose:** detect subscriptions/EMIs/rent — the backbone of "unnecessary expense" analysis.
- **Method:** group by normalized merchant; require ≥3 occurrences, interval ≈ 28–31 days (or 7/15), amount tolerance ±5% (fixed for EMIs), then flag.
- **Output:** `RecurringSeries(merchant, cadence, typical_amount, last_seen, confidence)`.

### 4.13 `modules/exporter.py`

- **Purpose:** CSV/Excel/JSON export of normalized transactions and reports; includes a "redacted" mode (account numbers masked).
- **Never:** export the raw uploaded file path or internal hashes that leak content.

### 4.14 `database/db.py` + `database/repositories.py`

- **`db.py`:** connection factory, `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout`, schema version, `migrate()`, `unit_of_work()` context manager (BEGIN/COMMIT/ROLLBACK).
- **`repositories.py`:** `AccountRepo`, `StatementRepo`, `TransactionRepo`, `RuleRepo`, `RecommendationRepo`, `SettingsRepo`, `SchemaTemplateRepo`. All SQL lives here, fully parameterized.
- No repository ever returns raw `sqlite3.Row` to the UI; it returns dataclasses.

### 4.15 `dashboard/` (presentation)

| Module | Screen | Key widgets |
| --- | --- | --- |
| `overview.py` | Home summary | KPI cards (income, spend, net, savings rate), month selector, mini trend |
| `upload.py` | Import | File uploader, detected mapping editor, validation report, confirm button |
| `transactions.py` | Review & fix | `st.data_editor` grid, filters, category dropdown, bulk edit, rule promotion |
| `charts.py` | Visuals | Plotly figures only (pure `figure -> fig` functions, reusable in tests) |
| `insights.py` | Recommendations | Ranked cards, "why this?", dismiss/accept, savings total |
| `settings.py` | Preferences | Currency, month start day, budgets, privacy toggles, data deletion |

### 4.16 Cross-cutting

- **`config/settings.py`** — paths, limits, thresholds, `APP_MODE`; overridable by environment variables; no secrets.
- **`modules/logging_utils.py`** — structured logging with a **redaction filter** (mask account numbers/UPI IDs); file logs rotate at 1 MB; no transaction description at INFO level.
- **`modules/constants.py`** — canonical category taxonomy, merchant aliases, direction enums.
- **`modules/events.py`** (optional) — a tiny in-process publish/subscribe so dashboards can invalidate caches after an import. Plain dict of callbacks; no external broker.

### 4.17 Boundary rules (enforced by review + a test)

- `dashboard/*` may import `modules/*` and `database/*`; `modules/*` may not import `dashboard/*` or `streamlit`.
- Only `database/*` executes SQL.
- Only `money.py` constructs `Decimal` money from strings; everything else receives `Money`/`Decimal`.
- Parsers never write to the DB; services never parse raw bytes.

---

## 5. Data flow diagram

### 5.1 Level 0 — context

```
        +-------------+        statement file         +----------------------+
        |    User     |------------------------------>|  UPI Smart Expense   |
        |             |<------------------------------|      Analyzer        |
        +-------------+   dashboard, insights,       +----------+-----------+
             ^            exported CSV/report                    |
             |                                                    |
             | (optional, opt-in export only)                     |
        +----+----------------+                                   |
        | Local filesystem /  |<----------------------------------+
        | OS disk encryption  |      app.db, exports
        +---------------------+
```

External entities: **User**, **Local filesystem**. Network boundary: none by default.

### 5.2 Level 1 — major processes and stores

```
 User
  |  (1) upload CSV/PDF
  v
+----------------+   RawTable    +------------------+  drafts   +-----------------+
| P1  Ingest &   |-------------->| P2  Structure &  |---------->| P3  Enrich      |
|     Extract    |               |     Validate     |           | (classify +     |
+----------------+               +------------------+           |  categorize +   |
        |                                |                     |  dedupe)        |
        | temp file                      | validation report   +--------+--------+
        v                                v                              |
  D1 uploads/ (temp)              User review (UI)                      | vendored rows
                                                                        v
                                                              +-------------------+
                                                              | P4  Persist       |
                                                              +---------+---------+
                                                                        |
                                              +-------------------------+------------------+
                                              |                         |                  |
                                              v                         v                  v
                                        D2 app.db              D3 schema_templates   D4 rules
                                        (accounts, statements,
                                         transactions, insights)
                                              |
                                              v
                                    +------------------+     figures     +-------------+
                                    | P5  Analyze      |---------------->| P6 Visualize|
                                    | (aggregations)   |                 | (Plotly)    |
                                    +--------+---------+                 +-------------+
                                             | summaries
                                             v
                                    +------------------+  recommendations  User
                                    | P7 Advise        |------------------>|
                                    +------------------+                   |
                                                                           v
                                                                    +-------------+
                                                                    | P8 Export   |
                                                                    +-------------+
```

### 5.3 Level 2 — P2 "Structure & Validate" (the fragile part)

```
RawTable(headers?, rows, warnings)
   |
   v
[find_header_row] --confidence low--> [manual mapping wizard] --+
   |                                                             |
   v                                                             |
[map_columns]  <---- template lookup (D3) -----------------------+
   |
   v
[normalize_rows]  -- per-row warnings -->
   |                                     |
   v                                     v
[validate rows] --------------------> ValidationReport
   |
   v
[dedupe: file hash -> txn fingerprints]
   |
   v
[reconcile opening/closing balance]
   |
   v
list[TransactionDraft] (nothing persisted yet)
```

**Key property:** until P4, no data is written. A failed or abandoned import leaves no residue beyond a temp file that the session cleanup deletes.

---

## 6. Database design

### 6.1 Design goals

- Reproducible imports: re-importing the same statement is a no-op.
- Traceability: every transaction points to its statement and its row.
- User corrections survive re-imports (rules, not row edits).
- Easy backup: one file, `VACUUM INTO` for a consistent copy.
- Migratable: `schema_version` + forward-only migration scripts.

### 6.2 Tables

**`app_meta`** — single row of key/value: `schema_version`, `app_version`, `created_at`, `currency_default`.

**`accounts`**

| Column | Type | Notes |
| --- | --- | --- |
| `account_id` | TEXT PK | UUID |
| `label` | TEXT NOT NULL | "HDFC Savings" (user-named) |
| `bank_name` | TEXT | optional |
| `account_last4` | TEXT(4) | **only** the last 4 digits; never the full number |
| `account_type` | TEXT | savings / current / credit_card / wallet |
| `currency` | TEXT NOT NULL | `INR` |
| `is_own_account` | INTEGER NOT NULL | 1 if the user owns it (enables transfer detection) |
| `created_at`, `archived_at` | TEXT | ISO-8601 UTC |

**`statements`** (one per successful import)

| Column | Type | Notes |
| --- | --- | --- |
| `statement_id` | TEXT PK | UUID |
| `account_id` | TEXT FK → accounts | |
| `source_filename` | TEXT | display only, not a path |
| `source_kind` | TEXT | `csv` / `pdf` |
| `file_sha256` | TEXT UNIQUE | idempotency |
| `period_start`, `period_end` | TEXT | ISO dates |
| `opening_balance_minor`, `closing_balance_minor` | INTEGER | nullable |
| `currency` | TEXT | |
| `row_count`, `imported_count`, `skipped_count` | INTEGER | import stats |
| `reconciliation_status` | TEXT | `ok` / `mismatch` / `not_applicable` |
| `template_id` | TEXT FK → schema_templates | which layout was used |
| `imported_at` | TEXT | |

**`transactions`** — the core table (full field list in §7).

| Column | Type | Notes |
| --- | --- | --- |
| `txn_id` | TEXT PK | UUID |
| `statement_id` | TEXT FK → statements, ON DELETE CASCADE | |
| `account_id` | TEXT FK → accounts | denormalized for fast filtering |
| `txn_date` | TEXT NOT NULL | ISO `YYYY-MM-DD` |
| `value_date` | TEXT | some banks differ |
| `amount_minor` | INTEGER NOT NULL | **signed**: credits `> 0`, debits `< 0`; paise |
| `currency` | TEXT NOT NULL | |
| `direction` | TEXT NOT NULL | `credit` / `debit` (redundant but readable) |
| `txn_type` | TEXT NOT NULL | `payment`, `refund`, `reversal`, `transfer_in`, `transfer_out`, `fee`, `interest`, `cash_withdrawal`, `salary`, `other` |
| `raw_description` | TEXT NOT NULL | exactly as in the file (trimmed) |
| `merchant_norm` | TEXT | normalized counterparty/merchant |
| `category_id` | TEXT FK → categories | nullable until categorized |
| `category_source` | TEXT | `rule` / `template` / `heuristic` / `user` / `ml` |
| `category_confidence` | REAL | 0.0–1.0 |
| `is_transfer` | INTEGER NOT NULL DEFAULT 0 | excluded from spend/income |
| `is_refund` | INTEGER NOT NULL DEFAULT 0 | nets against original category |
| `is_reversal` | INTEGER NOT NULL DEFAULT 0 | cancels the original txn |
| `linked_txn_id` | TEXT FK → transactions | refund/reversal/transfer pair |
| `balance_after_minor` | INTEGER | nullable; used for reconciliation |
| `reference` | TEXT | UTR/RRN/cheque no, if present |
| `mode` | TEXT | `UPI`, `NEFT`, `IMPS`, `CARD`, `ATM`, `CASH`, `UNKNOWN` |
| `counterparty_vpa` | TEXT | UPI handle, redacted in exports by default |
| `is_recurring` | INTEGER NOT NULL DEFAULT 0 | |
| `status` | TEXT NOT NULL | `active` / `excluded` / `suspected_duplicate` |
| `fingerprint` | TEXT NOT NULL | dedupe key, indexed |
| `row_index` | INTEGER | source row/page for traceability |
| `created_at`, `updated_at` | TEXT | |

Indexes: `(account_id, txn_date)`, `(category_id, txn_date)`, `(fingerprint)`, `(merchant_norm, txn_date)`, `(statement_id)`.

**`categories`** — seeded taxonomy (§11.1).

| Column | Type | Notes |
| --- | --- | --- |
| `category_id` | TEXT PK | slug, e.g. `food_dining` |
| `name` | TEXT | "Food & Dining" |
| `parent_id` | TEXT FK → categories | 2-level tree |
| `kind` | TEXT | `need` / `want` / `saving` / `income` / `internal` |
| `is_system` | INTEGER | 1 for seeded rows |
| `sort_order` | INTEGER | |

**`categorization_rules`** — learned and built-in rules.

| Column | Type | Notes |
| --- | --- | --- |
| `rule_id` | TEXT PK | |
| `pattern` | TEXT NOT NULL | keyword/regex/substring |
| `pattern_type` | TEXT | `contains` / `regex` / `vpa` / `merchant` |
| `field` | TEXT | `description` / `merchant_norm` / `counterparty_vpa` |
| `category_id` | TEXT FK | |
| `priority` | INTEGER | higher wins; user rules > built-ins |
| `source` | TEXT | `builtin` / `user` / `ml` |
| `hit_count` | INTEGER | for pruning dead rules |
| `created_at`, `updated_at` | TEXT | |

**`schema_templates`** — remembered bank layouts.

| Column | Type | Notes |
| --- | --- | --- |
| `template_id` | TEXT PK | |
| `fingerprint` | TEXT UNIQUE | hash of normalized headers + column count |
| `bank_label` | TEXT | user-visible name |
| `header_row_index` | INTEGER | |
| `column_map_json` | TEXT NOT NULL | JSON `{canonical_field: column_index}` |
| `date_policy` | TEXT | `day_first` / `month_first` |
| `amount_convention` | TEXT | `split` / `single_signed` / `single_with_dr_cr` |
| `use_count`, `last_used_at` | | |

**`recommendations`** — generated insights with lifecycle.

| Column | Type | Notes |
| --- | --- | --- |
| `recommendation_id` | TEXT PK | |
| `period` | TEXT | `YYYY-MM` |
| `rule_key` | TEXT | e.g. `recurring_subscription` |
| `title`, `detail` | TEXT | user-facing copy |
| `estimated_saving_minor` | INTEGER | |
| `priority_score` | REAL | ranking (§12.4) |
| `evidence_json` | TEXT | txn ids, amounts, dates — for "why?" |
| `status` | TEXT | `new` / `accepted` / `dismissed` / `expired` |
| `created_at`, `acted_at` | TEXT | |

**`import_issues`** — non-blocking problems for the Review screen.

| Column | Type | Notes |
| --- | --- | --- |
| `issue_id` | TEXT PK | |
| `statement_id` | TEXT FK, CASCADE | |
| `row_index` | INTEGER | |
| `severity` | TEXT | `error` / `warning` / `info` |
| `code` | TEXT | `bad_date`, `no_amount`, `balance_break`, `possible_dup` |
| `message` | TEXT | user-facing |
| `raw_row_json` | TEXT | original row for debugging/fixing |

**`settings`** — key/value user preferences: month start day, budgets per category, privacy toggles, `APP_MODE`.

**`audit_log`** — append-only, privacy-aware: `event_type` (`import`, `categorize_override`, `delete_statement`, `export`), `entity_id`, `at`, `detail_json` (no raw description text).

### 6.3 Money storage — the important decision

SQLite has no true DECIMAL type: a `NUMERIC` column may end up stored as an IEEE-754 `REAL`, which reintroduces binary rounding. Therefore:

- **Store** `amount_minor` as `INTEGER` paise (₹1.00 = 100). Exact, indexable, sums exactly.
- **Compute** in Python with `Decimal`, quantized to 2 dp at the boundary.
- **Convert** only in the repository layer (`Decimal ↔ int`), so no UI code does `* 100` by hand.
- **Never** store `float` anywhere; a test scans the schema for `REAL` on money columns, and `category_confidence` is the only permitted `REAL`.

### 6.4 Integrity and deletion

- `PRAGMA foreign_keys = ON`; `ON DELETE CASCADE` from statements to transactions, issues, and recommendation evidence.
- Import = one transaction (statement + N transactions + issues). Crash ⇒ nothing.
- "Delete my data" = delete statements (cascade), then `VACUUM`; confirm dialog states exactly what is removed.
- Backup = `VACUUM INTO 'backup.db'` (consistent snapshot even with WAL).
- Migrations: `migrations/001_init.sql`, `002_*.sql`; applied in order, each inside a transaction, tracked in `app_meta.schema_version`.

---

## 7. Transaction data model

### 7.1 The entity

```text
Transaction
  identity      : txn_id (uuid), statement_id, account_id, fingerprint, row_index
  time          : txn_date, value_date, created_at, updated_at
  money         : amount (Decimal, signed), currency, direction, balance_after
  description   : raw_description, merchant_norm, reference, counterparty_vpa, mode
  semantics     : txn_type, is_transfer, is_refund, is_reversal, linked_txn_id
  categorization: category_id, category_source, category_confidence
  lifecycle     : status, is_recurring
```

### 7.2 Field rules

| Field | Rule |
| --- | --- |
| `amount` | **Signed** domain convention: credit `+`, debit `−`. Positive-only source data plus a `direction` column is converted at normalization, once. |
| `direction` | Kept for readability and for UIs that filter by it; must always agree in sign with `amount`. Enforced by a validator. |
| `txn_date` | ISO string in DB, `date` in Python. If a statement gives only `MMM YYYY`, the row is flagged, not silently guessed to day 1. |
| `raw_description` | Preserved byte-for-byte after whitespace collapse. Never mutated by categorization — `merchant_norm` holds the cleaned version. This is what makes rules auditable. |
| `merchant_norm` | Uppercased, punctuation-stripped, known-noise removed (`UPI/`, `POS/`, `NEFT/`, reference numbers, trailing `@okhdfcbank` kept separately). |
| `txn_type` vs category | **Type is about mechanics** (was money actually spent?), **category is about purpose** (what was it for?). A refund is `txn_type=refund` and inherits the original's category. Keeping these orthogonal prevents the classic bug of "refunds inflate my Food spend". |
| `status` | `excluded` rows stay in the DB (traceability) but are filtered from every aggregate. |
| `linked_txn_id` | Only set inside one account; refund/reversal pairs and self-transfers. |

### 7.3 Lifecycle states

```
draft ──validate──> normalized ──dedupe──> persisted ──user edit──> corrected
                        │                      │
                        └──blocking error──> rejected (kept in import_issues, never persisted)
                                               │
                                    suspected_duplicate ──user confirms──> excluded | active
```

### 7.4 The four tricky cases, explicitly

| Case | Detection | Accounting treatment |
| --- | --- | --- |
| **Refund** (merchant returns money) | Credit whose amount matches a debit within 7 days and description contains `REFUND`/`RETURN`/`REVERSED`, or same merchant | `txn_type=refund`, linked to the original, category inherited; **nets against that category's spend** for the period, never counted as income |
| **Reversal** (failed txn reversed) | Credit matching a debit within 1–3 days, description contains `FAILED`/`REVERSAL`/`DECLINED`, often same reference | `txn_type=reversal`, linked; **both** rows excluded from totals if the net is zero (pair removed from analytics, retained in DB) |
| **Duplicate** | Same `fingerprint` (date+amount+direction+description+ref); or exact file hash | Auto-skip only when the whole file was seen before; otherwise mark `suspected_duplicate` and ask. Two legitimate identical UPI payments are distinguished by an in-file occurrence index. |
| **Transfer** (own accounts, or credit-card bill payment) | Counterparty matches a known own account; description contains `SELF`, `OWN`, `CC PAYMENT`, `CREDIT CARD`; matching opposite amount/date across two imported accounts | `is_transfer=1`, **excluded from both income and expense**; shown separately as "moved money". Prevents double counting when both accounts are imported. |

### 7.5 Invariants (asserted in tests and at import time)

1. `amount ≠ 0`.
2. `direction == ("credit" if amount > 0 else "debit")`.
3. `is_refund or is_reversal` ⇒ `linked_txn_id` is not null (or an issue row explains why).
4. `status == excluded` ⇒ row is excluded from **all** aggregates (tested by comparing a filtered vs unfiltered summary).
5. Sum of `amount_minor` for a statement, plus opening balance, equals closing balance when reconciliation is `ok`.
6. `fingerprint` is unique per `(account_id)` among `active` rows, except for rows flagged as legitimate same-day repeats.

---

## 8. Suggested project folder structure

Your proposed skeleton is a good start; below is the same shape with the modules the requirements imply. **Bold** = added to your list, with the reason.

```
upi-smart-expense-analyzer/
│
├── app.py                      # Streamlit entry: nav, page routing, global state
├── requirements.txt
├── requirements-ml.txt         # optional: scikit-learn, joblib
├── pyproject.toml              # pytest/ruff config (optional but recommended)
├── README.md
├── PROJECT_REQUIREMENTS.md
├── TECHNICAL_ARCHITECTURE.md
├── .gitignore                  # data/, *.db, .venv, exports/, .env
│
├── config/
│   ├── settings.py             # paths, limits, APP_MODE, thresholds
│   └── categories.yaml         # seed taxonomy + built-in merchant aliases
│
├── modules/
│   ├── __init__.py
│   ├── money.py                # ** Decimal money type + rounding (critical)
│   ├── models.py               # ** dataclasses: TransactionDraft, Transaction, Report
│   ├── constants.py            # ** enums, canonical field names
│   ├── validators.py           # ** row/statement rules + reconciliation
│   ├── normalizer.py           # ** raw strings -> typed drafts (dates, amounts)
│   ├── schema_detector.py      # ** header/column discovery + templates
│   ├── deduplicator.py         # ** hashes, duplicate policy
│   ├── classifier.py           # ** refund / reversal / transfer / fee detection
│   ├── recurring.py            # ** subscription & EMI detection
│   ├── logging_utils.py        # ** redacting logger
│   ├── file_upload.py
│   ├── csv_parser.py           # (or parsers/csv_parser.py + registry)
│   ├── pdf_parser.py
│   ├── data_cleaner.py         # description normalization, dataframe hygiene
│   ├── transaction_processor.py# orchestration: parse->normalize->validate->dedupe->enrich
│   ├── categorizer.py
│   ├── analytics.py
│   ├── expense_advisor.py
│   └── exporter.py             # ** CSV/Excel export + redaction
│
├── parsers/                    # optional split if modules/ gets crowded
│   ├── base.py                 # Parser protocol, RawTable
│   ├── pdf_text.py             # PdfTextExtractor interface (PyMuPDF impl)
│   └── registry.py
│
├── database/
│   ├── db.py                   # connection, pragmas, unit_of_work, migrate()
│   ├── models.py               # table dataclasses / row mappers
│   ├── repositories.py         # ** all SQL, parameterized
│   └── migrations/
│       ├── 001_init.sql
│       └── 002_add_recurring.sql
│
├── dashboard/
│   ├── overview.py
│   ├── upload.py               # ** mapping confirmation screen
│   ├── transactions.py
│   ├── charts.py
│   ├── insights.py             # ** recommendations screen
│   └── settings.py             # ** privacy, budgets, delete data
│
├── services/                   # optional: thin use-case orchestration
│   ├── import_service.py       # ** the workflow in §3, testable without Streamlit
│   ├── analytics_service.py
│   └── advisor_service.py
│
├── data/                       # git-ignored at runtime
│   ├── app.db
│   └── uploads/                # transient
│
├── exports/                    # git-ignored
│
├── sample_data/
│   ├── sample_statement.csv    # synthetic, no real people
│   ├── sample_statement.pdf    # synthetic, 2 pages, 2 layouts
│   └── sample_credit_card.csv  # different layout on purpose
│
├── tests/
│   ├── conftest.py             # tmp DB, sample fixtures, Decimal helpers
│   ├── fixtures/               # csv/pdf/golden json
│   ├── test_money.py
│   ├── test_csv_parser.py
│   ├── test_pdf_parser.py
│   ├── test_schema_detector.py
│   ├── test_normalizer.py
│   ├── test_validators.py
│   ├── test_deduplicator.py
│   ├── test_classifier.py
│   ├── test_categorizer.py
│   ├── test_analytics.py
│   ├── test_advisor.py
│   ├── test_repositories.py
│   ├── test_import_service.py  # end-to-end: bytes -> DB rows
│   ├── test_architecture.py    # ** import-boundary rules
│   └── test_app_smoke.py       # ** Streamlit AppTest
│
└── .github/workflows/tests.yml # free CI
```

**Why the additions:** `money.py` and `models.py` prevent 80% of the classic bugs (float drift, sign confusion); `schema_detector.py` is the module that satisfies "do not assume all statements have the same format"; `deduplicator.py` and `classifier.py` isolate the four tricky cases so they can be tested independently; `services/` keeps Streamlit out of the business logic so the whole workflow can be tested headlessly.

---

## 9. CSV and PDF processing approach

### 9.1 CSV pipeline

```
bytes
 └─ encoding detect (utf-8-sig -> utf-8 -> cp1252 -> latin-1)  [attempt decode, validate sample]
     └─ delimiter sniff (csv.Sniffer + frequency fallback: , ; \t |)
         └─ skip preamble: find first row with >= 3 non-empty cells that looks tabular
             └─ header detection (alias/fuzzy match on cells; or numeric-row heuristic)
                 └─ ragged row repair (pad short rows, flag long rows)
                     └─ read with pandas (dtype=str, keep_default_na=False, thousands handling manual)
                         └─ RawTable(headers, rows, warnings)
```

Details that matter in practice:

- Always read as **strings** first (`dtype=str`). Letting pandas infer types turns `01/02/2024` into a date it guessed wrong, and `1,234.56` into a string or a wrong float.
- Disable automatic `NaN` coercion (`keep_default_na=False`) so a literal `"NA"` narration isn't lost.
- Indian number grouping (`1,23,456.78`) breaks naive `float()`; parse with a dedicated `parse_amount` that strips ₹/Rs/INR/commas/spaces, detects `Dr`/`Cr` suffixes and `(...)` negatives, then builds `Decimal`.
- Multi-sheet Excel and "statement summary at the top, table in the middle" CSVs are handled by preamble skipping + header detection, not by bank-specific offsets.
- BOM (`\ufeff`) on the first header is stripped, otherwise the first column never matches.
- Trailing blank rows and repeated header rows (page breaks in PDF-to-CSV exports) are dropped.

### 9.2 PDF pipeline

```
PDF bytes
 └─ open with PdfTextExtractor (PyMuPDF)
     ├─ is it encrypted? -> request password (session only)
     ├─ text layer present? (chars per page > threshold)
     │    ├─ YES -> for each page: get words with coordinates
     │    │           -> cluster words into lines (y proximity)
     │    │           -> split lines into columns (x gaps / recurring x-positions)
     │    │           -> join wrapped narration lines to the row above/below
     │    │           -> RawTable
     │    └─ NO  -> scanned: show "this looks like an image PDF"
     │              -> offer OCR (opt-in, local Tesseract) or manual CSV export instructions
     └─ page-continuity checks: repeated headers removed; footer/page numbers dropped
```

Why coordinate-based reconstruction rather than "extract tables":

- Bank e-statements are usually *not* ruled tables; they are text positioned in columns. Column x-positions repeat page to page, so clustering by x-gap is more reliable than generic table detection.
- Narration frequently wraps onto a second line. A row is only complete when the next line lacks a date and an amount — that heuristic is explicit and testable.
- Every reconstructed row is **cross-checked against the running balance column**, which is the strongest available signal that no row was missed or duplicated.

### 9.3 The "every bank is different" strategy

Five layers, each handling a different kind of difference:

| Difference | Handled by |
| --- | --- |
| Encoding/delimiter/preamble | `csv_parser` sniffing |
| Header names differ | alias dictionary + fuzzy match in `schema_detector` |
| Layout differs (split Dr/Cr vs single amount+sign vs `Dr`/`Cr` suffix) | `ColumnMapping` + `amount_convention` |
| Date format differs | `date_policy` per template (`day_first` default for India) |
| Same bank, slightly changed export | template fingerprint misses ⇒ re-confirm once, then a new template is saved |

The user confirms a detected mapping **once per layout**; after that, imports are one click. Nothing is hardcoded to a bank name.

### 9.4 Parsing acceptance criteria

- Three structurally different synthetic statements (savings CSV with split columns, credit-card CSV with single signed amount, multi-page PDF with wrapped narration) import with zero manual column mapping on the second run.
- A statement with a deliberately deleted row triggers a reconciliation **mismatch**, not silent acceptance.
- A Chinese/UTF-8-BOM/CP1252 trio of the same file produce identical normalized rows.
- No parser reads a file path from user input; all reads go through `StagedFile`.

---

## 10. Financial calculation logic

### 10.1 Money rules (non-negotiable)

| Rule | Detail |
| --- | --- |
| Type | `decimal.Decimal` everywhere in Python; `int` paise in SQLite |
| Construction | `Decimal(str_value)`, never `Decimal(float)` |
| Precision | `Decimal` context precision 28 (default is fine); quantize results to `0.01` |
| Rounding | `ROUND_HALF_UP` (matches Indian financial convention; `ROUND_HALF_EVEN` acceptable if documented — pick one and test it) |
| Intermediate values | Do **not** round per row before summing. Sum exact values, round once at presentation. |
| Percentage | Compute on `Decimal`, round only for display |
| Currency | Single currency per statement (`INR`); mixed-currency rows are flagged, not silently converted |

### 10.2 Sign convention and definitions

Let `t.amount` be signed: credits positive, debits negative.

```
total_credits      = Σ amount  where amount > 0 and status = active and not is_transfer
total_debits       = Σ |amount| where amount < 0 and status = active and not is_transfer
net_flow           = total_credits − total_debits
spend              = Σ |amount| where debit, not transfer, not reversal, not excluded
                     − Σ refunds linked to those debits (in the same period)
income             = Σ amount where credit, not transfer, not refund, not reversal
savings_rate       = (income − spend) / income        [guard: income == 0 ⇒ n/a]
category_spend(c)  = Σ |amount| in category c − refunds in c
share(c)           = category_spend(c) / spend
mom_change(c)      = (spend_c(m) − spend_c(m−1)) / spend_c(m−1)   [guard: previous = 0]
```

### 10.3 Refund / reversal / transfer effects (worked examples)

| Scenario | Rows | Result |
| --- | --- | --- |
| ₹500 Swiggy paid, ₹200 refunded | −500, +200 (refund) | Food spend ₹300; income unchanged |
| ₹1,000 UPI failed and reversed | −1000, +1000 (reversal) | Both excluded from spend and income; shown as "failed payment" |
| ₹20,000 moved savings → salary account | −20000 (transfer_out), +20000 (transfer_in) | Income ₹0, spend ₹0; "moved ₹20,000" |
| Credit-card bill paid from bank | −15000 (transfer_out), card spend already counted from card statement | Not double counted; card spend counted once from the card statement |
| Duplicate page imported twice | 2× identical rows | Second set is `suspected_duplicate`; totals unchanged |

### 10.4 Period and aggregation rules

- Period = calendar month by default; `month_start_day` setting supports salary-cycle months (e.g., 25th → 24th), applied consistently to all reports.
- Transactions are bucketed by `txn_date`, not `value_date` (documented, and `value_date` is retained for reconciliation).
- A statement may span periods; each transaction is bucketed independently — no pro-rating.
- Aggregates always filter `status = active` and, by default, `is_transfer = 0`.
- Empty categories are shown as ₹0 rather than omitted, so charts don't shift month to month.

### 10.5 Reconciliation (a correctness check, not a feature)

```
expected_closing = opening_balance + Σ signed amounts (all rows, including transfers & reversals)
if |expected_closing − stated_closing| > ₹0.01 -> reconciliation_status = mismatch
```

On mismatch the UI shows the delta and the top suspects (a date gap, a repeated page, a sign flip, a missing fee row). This single check catches most real-world extraction errors.

### 10.6 Determinism

Given the same input rows and the same rules, every total must be byte-identical across runs. Therefore: no `float`, no `set` iteration order in aggregation, no locale-dependent formatting inside calculations, and stable sort keys everywhere.

---

## 11. Transaction categorization approach

### 11.1 Taxonomy (seeded, 2 levels, `kind` drives the advisor)

| Category | Kind | Examples (Indian context) |
| --- | --- | --- |
| Food & Dining | want | Swiggy, Zomato, restaurants, cafes |
| Groceries | need | BigBasket, Blinkit, DMart, kirana |
| Transport | need | Uber, Ola, metro, fuel, FASTag |
| Bills & Utilities | need | electricity, broadband, mobile, gas |
| Rent & Housing | need | rent, maintenance |
| Health | need | pharmacy, hospital, gym (partly want) |
| Shopping | want | Amazon, Flipkart, Myntra |
| Entertainment | want | Netflix, Spotify, PVR, gaming |
| Subscriptions | want | SaaS, OTT, cloud storage |
| Education | need | courses, fees, books |
| Travel | want | IRCTC, MakeMyTrip, hotels |
| Fees & Charges | internal | bank charges, GST, penalties |
| Cash & ATM | internal | ATM withdrawals |
| Transfers | internal | self-transfer, CC payment |
| Investments | saving | SIP, mutual fund, stocks |
| Insurance | need | premiums |
| Income | income | salary, interest, freelance |
| Uncategorized | — | fallback |

`internal` categories are excluded from "spending" but shown in a separate section, so ATM cash doesn't look like a mystery expense.

### 11.2 Four-stage pipeline (first match wins, confidence recorded)

```
draft
  │
  ├─ 1. USER RULE      (source=user, highest priority)        conf 0.99
  ├─ 2. BUILT-IN RULE  (keyword/regex on raw_description)      conf 0.90
  ├─ 3. MERCHANT MAP   (merchant_norm / VPA exact + fuzzy)     conf 0.75–0.90
  ├─ 4. HEURISTIC      (amount pattern, day-of-month, mode)    conf 0.40–0.60
  └─ 5. FALLBACK       "Uncategorized", asks the user          conf 0.00
```

Stage notes:

1. **User rules first.** A correction is a promise; it must never be overridden by a built-in rule.
2. **Built-in keyword rules** live in `config/categories.yaml` (data, not code), e.g. `ZOMATO|SWIGGY -> food_dining`. `contains` matching on the uppercased description, longest/most specific pattern wins.
3. **Merchant map** handles the reality of UPI narrations: `UPI/DR/123456789/SWIGGY@YBL/...`. Extract the VPA/merchant token, normalize, then map. `rapidfuzz` handles typos and variants (`BIG BASKET` vs `BIGBASKET`).
4. **Heuristics** are hints, never decisions: recurring same-amount monthly debit → maybe subscription; small daily amounts at the same merchant → maybe food. Always low confidence, always reviewable.
5. **Fallback** is honest. `Uncategorized` is a first-class state with a UI badge, not a guessed category.

### 11.3 The learning loop

- User changes a category in the Review grid → `category_source=user`, `confidence=1.0`, and the UI offers "apply to all similar transactions" + "save as a rule".
- Saved rules go to `categorization_rules` with `source=user` and a higher priority; future imports hit stage 1.
- Rule quality is tracked via `hit_count`; rules that never fire can be pruned (with consent).
- Re-categorization on rule change is an explicit, previewable batch job ("this will change 34 transactions"), never a silent rewrite of history.
- Every categorization stores **why**: `category_source` + the rule id in the audit log, so the UI can answer "why is this Food?".

### 11.4 When ML arrives (Phase 3, optional)

- Only after there is a few thousand rows of *user-labelled* data; the rule engine remains the default.
- Model: `TfidfVectorizer(char_wb + word)` → `LogisticRegression` (or `SGDClassifier` for incremental training); trained locally, saved with `joblib`, versioned.
- ML output is applied **only** when confidence ≥ 0.75 **and** no user rule matched; otherwise the prediction is shown as a suggestion in the UI, not written.
- Users can disable ML entirely; nothing leaves the machine; the training file is the local DB.
- Evaluation: macro-F1 on a held-out split of the user's own data, reported honestly ("this model was trained on your 1,240 labelled transactions; it agrees with you on 86% of unseen ones").
- `scikit-learn` is an optional extra dependency so the base app stays light.

---

## 12. Expense recommendation engine

### 12.1 Philosophy

Recommendations must be **specific, evidenced, quantified, and polite**. No "you spend too much" — instead "You paid ₹649 × 6 = ₹3,894 for Netflix and two other OTT services this year; two were last used months apart. Cancelling one could free ~₹649/month." The engine is rule-based first (explainable, debuggable, no data requirement), ML-assisted never.

### 12.2 Rule catalogue (each rule = detector + evidence + estimate + priority)

| Rule key | Detects | Evidence | Estimated saving |
| --- | --- | --- | --- |
| `recurring_subscription` | ≥3 debits, monthly cadence, stable amount | merchant, amounts, dates | monthly amount of the smallest/least-used subscription |
| `category_spike` | category spend this month > 130% of 3-month median | both values | the excess over median |
| `wants_ratio` | wants / total spend > user threshold (default 40%) | split table | amount above threshold |
| `small_frequent` | ≥8 debits < ₹100 at one merchant/month | transactions | extrapolated annual amount |
| `duplicate_charge` | same merchant+amount within 24 h, not linked | txn pair | one duplicate amount |
| `fee_leakage` | bank charges, late fees, penalties trending up | fee rows | monthly fee sum |
| `subscription_cluster` | ≥2 services in the same purpose (OTT, cloud) | category group | overlap estimate, clearly labelled as an estimate |
| `dormant_recurring` | recurring debit with no matching activity signal | recurrence only | the full amount |
| `budget_breach` | user-set budget exceeded | budget vs actual | overage |
| `income_ratio` | spend/income > 90% | summary | advisory only, no ₹ estimate |
| `weekend_leak` | weekend spend per day > 1.5× weekday | weekday profile | descriptive only |

### 12.3 Recommendation object

```text
Recommendation
  rule_key, title, detail
  period
  estimated_saving (Decimal | None)     # None when not quantifiable
  priority_score (0–100)
  confidence ("high" | "medium" | "low")
  evidence [ {txn_id, date, amount, merchant} ]
  action ("review" | "cancel" | "set_budget" | "verify" | "informational")
```

### 12.4 Ranking

```
priority_score = w1 * estimated_saving_percentile
               + w2 * confidence
               + w3 * recency_of_evidence
               + w4 * actionability
```

Default weights (tunable in settings, documented): saving 0.45, confidence 0.25, recency 0.15, actionability 0.15. Scores are normalized 0–100 and shown as "High/Medium/Low impact", never as false precision.

### 12.5 Guardrails

- **Minimum evidence:** a rule needs ≥3 occurrences or ≥2 months of data before firing. No advice on one odd transaction.
- **Never count a transfer or refund as spend** (reuse §10.2 filters, don't re-implement).
- **No double counting:** if two rules describe the same ₹649 subscription, only the highest-priority one counts toward "potential savings".
- **Estimates are labelled** as estimates, with the arithmetic visible.
- **No investment, tax, or credit advice**; a persistent disclaimer states the app is not a financial adviser.
- **No shaming language**; second person, neutral, actionable ("review", "verify", "consider").
- **Dismissal is respected:** dismissed (`status=dismissed`) rules don't reappear for that period, and repeated dismissal lowers the rule's priority for that user.
- **Local only:** recommendations are computed in-process from the local DB; no LLM call.

---

## 13. Security and privacy considerations

### 13.1 Data classification

| Class | Examples | Where it may live |
| --- | --- | --- |
| **Highly sensitive** | full account numbers, card numbers, VPA, raw statement PDF | Memory + temp file only, deleted immediately after import |
| **Sensitive** | transaction narration, amounts, balances, salary | Local `app.db` (OS-encrypted disk), never logged in full |
| **Derived** | monthly totals, category shares, recommendations | Local `app.db`; safe to export (redaction optional) |
| **Public** | sample/test data (synthetic) | Repo |

### 13.2 Controls (mapped to the requirement "process locally")

| Area | Control |
| --- | --- |
| Network | No outbound calls in Local mode. No telemetry, no crash reporting, no analytics, no CDN. Plotly assets are bundled by Streamlit's local server. |
| Cloud sync | None. If the user puts the project folder in OneDrive/Dropbox, that is their choice and the README warns against it. |
| Minimization | Only the **last 4 digits** of an account number are stored (`account_last4`). Card numbers are never stored; if present in narration they are masked before persistence. VPAs are stored but masked in exports and logs by default. |
| Temp files | Uploaded bytes go to a per-session temp file, are deleted in a `finally` block (and by a startup sweep for orphans older than 24 h), and never written to the log. |
| In-memory | Prefer parsing from the uploaded `BytesIO`; write to disk only because PyMuPDF needs a file or stream. Never `pickle` untrusted data. |
| Encryption at rest | Default: rely on OS full-disk encryption (BitLocker / FileVault / LUKS). Optional: SQLCipher via `pysqlcipher3`, keyed from a user passphrase held in Streamlit session state and never persisted. Document the key-loss consequence plainly. |
| Encryption in transit | Only relevant for Demo mode: HTTPS enforced by the host. No real data in Demo mode. |
| Logging | Redaction filter masks `\d{9,}` account/card-like sequences and `...@...` VPAs. INFO logs record counts and IDs, not narrations. Log level configurable; logs are local files, git-ignored. |
| SQL | 100% parameterized queries; no f-string SQL; no dynamic table names from user input. `PRAGMA foreign_keys=ON`. |
| File handling | Extension allow-list + magic-byte check + 20 MB cap + row cap; filename sanitized (basename only, no `..`); no `eval`, no dynamic import, no `subprocess` except the opt-in Tesseract call. |
| UI injection | Any user-supplied text (narration, merchant) rendered via `st.text`/escaped markdown, never `unsafe_allow_html`. Plotly titles use escaped strings. |
| Dependencies | Pinned versions, `pip-audit` in CI, minimal dependency surface, review new deps for network behaviour. PyMuPDF's AGPL is a licensing risk, not a runtime one — kept behind an interface (§2). |
| Deletion / portability | "Delete all my data" removes DB rows, VACUUMs, deletes temp files, and lists what was removed. Full export (CSV/JSON) is available before deletion. |
| Backups | User-initiated `VACUUM INTO` snapshot; the app warns that backups are as sensitive as the original. |
| Hosting | Demo mode is public: no persistent storage, sample data only, uploads disabled or restricted to explicitly synthetic files, and a banner stating that uploaded data is public. |

### 13.3 Threat model (lightweight STRIDE)

| Threat | Vector | Mitigation |
| --- | --- | --- |
| Spoofing | Someone uses another person's laptop/DB | OS account security is the boundary; optional app passphrase (SQLCipher) |
| Tampering | Malicious CSV/PDF crafted to crash or exploit the parser | Size/row caps, strict typing, no `eval`, parser exceptions contained per row, dependency updates |
| Repudiation | "Who deleted my statement?" | Append-only `audit_log` (IDs, not content) |
| Information disclosure | Logs, exports, crash traces, cloud sync folder | Redaction, no telemetry, masked exports, `.gitignore` guard, warning in README |
| Denial of service | Huge PDF, zip bomb, pathological regex | Size and page caps, timeouts, bounded regexes (no nested quantifiers) |
| Elevation of privilege | Path traversal via filename, SQL injection | Basename-only filenames, parameterized SQL, no shell execution |

### 13.4 Compliance notes (not legal advice)

- India's **DPDP Act 2023** treats financial data as personal data; keeping processing on the user's device with no transfer greatly simplifies obligations. Collect nothing you don't need; delete on request; state the purpose in the README.
- **GDPR** (if used in the EU): local-only processing avoids most controller/processor complexity, but a privacy notice and data-portability/erasure features are still expected — both exist (§13.2).
- No PAN/Aadhaar/card-number capture; if such numbers appear in narration they are masked.
- The app displays a clear disclaimer: *educational tool, not financial, tax, or investment advice.*

---

## 14. Testing strategy

### 14.1 Test pyramid

| Level | Share | What | Tools |
| --- | --- | --- | --- |
| Unit | ~70% | `money`, `parse_amount`, `parse_date`, normalizer, validators, dedupe, classifier, each advisor rule, each analytics function | pytest |
| Integration | ~20% | parser → normalize → validate → dedupe → persist against a temp SQLite; reconciliation; re-import idempotency | pytest + `tmp_path` |
| UI / smoke | ~10% | app boots, pages render, upload happy path, mapping wizard | `streamlit.testing.v1.AppTest` |
| Manual | — | Real statements from 3–4 banks, checked once, results recorded in a checklist | human |

### 14.2 What must be tested (the "never break these" list)

1. **Money** — `Decimal` construction from strings, rounding half-up, sum of many values equals exact expected, no float leaks (`assert not isinstance(x, float)`).
2. **Idempotency** — importing the same file twice yields the same row count; file-hash short-circuit.
3. **Duplicates** — two genuine identical ₹20 payments on one day both survive; a re-imported page does not.
4. **Refunds/reversals/transfers** — the worked examples in §10.3, asserted to the paise.
5. **Schema variance** — three synthetic layouts (split columns, single signed amount, PDF with wrapped narration) map correctly.
6. **Balance reconciliation** — mismatch is detected, not silently accepted.
7. **Exclusions** — `status=excluded` and `is_transfer=1` never appear in any aggregate (property test over a random fixture).
8. **Categorization precedence** — user rule beats built-in rule beats fallback; a change of rule triggers a previewable batch.
9. **Advisor guardrails** — no recommendation from <3 occurrences; no double-counted savings; dismissed items stay dismissed.
10. **Architecture** — `modules/*` imports neither `streamlit` nor `dashboard/*`; only `database/*` contains SQL.
11. **Privacy** — the log capture fixture asserts no account-number-like or VPA-like strings; temp files are gone after a failed import.
12. **Deletion** — delete statement cascades and leaves counts at zero; `VACUUM` succeeds.

### 14.3 Fixtures and data hygiene

- `tests/fixtures/` holds **synthetic** statements only, with fictional names, plausible narrations, and at least one deliberately broken file per failure mode.
- A `golden/` JSON per fixture records expected normalized rows — makes parser regressions obvious in review diffs.
- `conftest.py` provides: `tmp_db` (in-memory or `tmp_path` file), `sample_csv`, `sample_pdf`, `money()` helper, and a `freeze_today()` utility so date-dependent rules are deterministic.
- **Never** commit real statements; add a CI check that fixture files contain no 12+ digit sequences.

### 14.4 Quality gates

- `pytest --cov=modules --cov=database --cov-fail-under=80` for non-UI code; UI modules are covered by smoke tests instead.
- `ruff` for lint/format, `mypy` (or `pyright`) on `modules/`, `database/`, `services/` — the domain layer is typed; the UI may be looser.
- `pip-audit` for known CVEs on every push.
- Performance test: a generated 5,000-row CSV must import in under 5 s on CI.

### 14.5 CI (free)

`.github/workflows/tests.yml`: matrix Python 3.11/3.12 on Ubuntu; steps = checkout, setup-python with pip cache, install, `ruff`, `mypy`, `pytest`, `pip-audit`. Windows-only PDF quirks are covered by a single Windows job if needed. No secrets required.

---

## 15. Deployment strategy using free resources

### 15.1 Recommendation: local-first, demo second

The privacy requirement (§13) means **real statements should only ever be processed locally**. Deployment is therefore split:

| Mode | Host | Cost | Persistence | Real data? |
| --- | --- | --- | --- | --- |
| **Primary: Local** | User's machine, `streamlit run app.py` | Free | `data/app.db` | ✅ Yes |
| **Secondary: Public demo** | Streamlit Community Cloud / Hugging Face Spaces | Free | Ephemeral | ❌ No |
| **Tertiary: Portfolio** | GitHub repo + README screenshots | Free | — | Sample only |

### 15.2 Local distribution (the main path)

- `README.md` quickstart: `python -m venv .venv` → activate → `pip install -r requirements.txt` → `streamlit run app.py`.
- Optional convenience: a `run.bat` (Windows) and `run.sh`, or `pipx`/`uv` instructions.
- `data/` is created on first run; `data/app.db` is initialized and migrated automatically.
- Backup/restore documented as file copy; delete-data documented in the UI.
- Packaging to a single executable (PyInstaller) is a later nice-to-have, not a v1 requirement.

### 15.3 Streamlit Community Cloud (free demo)

- Requirements: public GitHub repo, `app.py` at root, `requirements.txt` pinned.
- Caveats to document loudly: filesystem is **ephemeral** (DB resets on redeploy/sleep), apps sleep after inactivity, and uploads would be public. Therefore Demo mode: sample data prefilled, real uploads disabled or clearly labelled "do not upload real statements".
- Secrets (none needed v1) would go in the platform's secrets manager, never in the repo.

### 15.4 Hugging Face Spaces (free, Docker)

- Good alternative when you want a pinned Python version or system packages (e.g., Tesseract).
- Use a `Dockerfile` on the free CPU tier; keep the image small (no ML extras).
- Same ephemeral-storage caveat; persistent storage is a paid feature, so Demo mode only.

### 15.5 Other free tiers (fallbacks)

| Platform | Fit | Caveat |
| --- | --- | --- |
| Render (free web service) | Works with a `Dockerfile` | Spins down; ephemeral disk |
| Fly.io | Small free allowance | Card required; more ops knowledge |
| Railway / Koyeb | Quick deploys | Trial credits, not permanent |
| GitHub Pages | **Not suitable** | Static only; cannot run Python |

### 15.6 Deployment checklist

1. `APP_MODE=demo` disables persistence-required features and shows a privacy banner.
2. `requirements.txt` pinned; app boots on a clean environment.
3. Sample data loads in one click; all pages reachable without an upload.
4. No `.db`, `.env`, `exports/`, or real statements in the repo (`.gitignore` verified).
5. Logs go to stdout on hosted platforms; redaction still active.
6. Resource limits respected (≤1 GB RAM, single worker, no background threads beyond Streamlit's rerun model).
7. README states clearly: "Demo uses synthetic data. Run locally for real statements."
8. Health check = the app's home page returning 200.

---

## 16. Phased roadmap (suggested implementation order)

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| **P0 — Skeleton** | repo, venv, settings, logging, `money.py`, DB migration 001, empty Streamlit pages | `pytest` green, app boots, DB created |
| **P1 — CSV end-to-end** | csv parser, schema detector, normalizer, validators, repositories, import service, Review grid | one real-style CSV imports, reconciles, is idempotent |
| **P2 — Analysis** | categorizer + rules, analytics, Plotly dashboards | monthly totals and category split match hand-checked values |
| **P3 — PDF** | PDF extractor + reconstruction + reconciliation | 2-page synthetic PDF and one real text PDF import correctly |
| **P4 — Advice** | recurring detection, advisor rules, insights page | recommendations are evidenced, ranked, dismissible |
| **P5 — Hardening** | duplicates/refunds/transfers polish, exports, deletion, security tests, CI, demo deploy | §14 gates pass; demo live on free hosting |

Deliberately deferred: OCR, ML categorizer, multi-currency, budgets-alerts, mobile layout, encrypted DB, PyInstaller.

---

## 17. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PDF layouts vary wildly | Wrong rows / missing transactions | Coordinate reconstruction + balance reconciliation + manual mapping wizard + per-layout templates |
| Scanned PDFs | No extractable text | Detect early, explain clearly, offer opt-in local OCR |
| Naive float arithmetic creeping in | Silent paise drift, wrong advice | Single `money.py`, integer storage, lint/test guard against `float` |
| Duplicate detection over-eager | Real spending disappears | Conservative policy: auto-skip only on identical file hash; otherwise ask |
| Refund/transfer misclassification | Inflated income/spend | Explicit `txn_type` + linkage fields + §10.3 tests |
| PyMuPDF AGPL | Licensing constraints if closed-source | Interface abstraction, `pdfplumber` swap path |
| Streamlit reruns losing state | Confusing UX, repeated imports | Idempotency by hash, session-state keys, cached analytics |
| Public demo leaking data | Privacy incident | Demo mode with uploads disabled + banner + sample data only |
| Scope creep into "financial adviser" | Liability, bad advice | Rule-based, evidence-backed, labelled estimates, disclaimer |
| Beginner overwhelm | Project stalls | Phased roadmap, one module at a time, tests as a safety net |

---

## 18. Glossary

| Term | Meaning |
| --- | --- |
| **Minor units** | The smallest currency unit; paise for INR (₹1.00 = 100 paise) |
| **Signed amount** | Credit positive, debit negative — one number carries both magnitude and direction |
| **Fingerprint** | Hash of the fields that identify a transaction, used for deduplication |
| **Schema template** | Saved mapping for one bank's statement layout, reused on later imports |
| **Reconciliation** | Checking that opening balance + all rows = closing balance |
| **RawTable** | Parser output: headers + rows of strings + warnings, before any interpretation |
| **Draft** | A normalized but not-yet-persisted transaction |
| **Linked transaction** | A refund/reversal/transfer counterpart, referenced by `linked_txn_id` |
| **Internal category** | Transfers, ATM cash, fees — excluded from "spending" |
| **Idempotent import** | Importing the same file twice produces no additional rows |

---

## 19. Architecture decision record (summary)

| # | Decision | Alternatives considered | Rationale |
| --- | --- | --- | --- |
| ADR-1 | Layered monolith in one Python process | Microservices, separate API + SPA | Single user, offline, beginner-friendly |
| ADR-2 | Streamlit for UI | Flask/FastAPI + templates, Dash, NiceGUI | Pure Python, fastest path to a working data app |
| ADR-3 | SQLite + integer paise | Postgres, DuckDB, TEXT decimals | Zero-install, exact, single-file backup |
| ADR-4 | `Decimal` throughout | `float`, `numpy` money | Financial correctness; testability |
| ADR-5 | Discover-then-confirm schema mapping | Per-bank hardcoded parsers | Requirement: formats differ; new banks must "just work" after one confirmation |
| ADR-6 | Rule-based categorization first, ML later | ML-first | Explainability, zero data requirement, reviewability |
| ADR-7 | Rule-based advisor with evidence | LLM-generated advice | Privacy, determinism, no hallucinated numbers |
| ADR-8 | Local-first; demo mode separate | Cloud-only SaaS | Privacy of financial statements |
| ADR-9 | PyMuPDF behind an extractor interface | Direct PyMuPDF calls | AGPL optionality, future swap to `pdfplumber` |
| ADR-10 | Conservative duplicate policy | Aggressive auto-dedupe | Losing real transactions is worse than a prompt |

---

## 20. Definition of done (v1)

- [ ] CSV and PDF statements from at least three different layouts import without code changes.
- [ ] Re-importing any file changes no totals.
- [ ] Refunds, reversals, duplicates, and transfers are handled per §10.3 and covered by tests.
- [ ] Every monetary figure is computed with `Decimal` and stored as integer paise.
- [ ] Dashboard shows income, spend, net, category split, trend, top merchants, recurring items.
- [ ] Insights page shows ranked, evidenced recommendations with dismiss/accept.
- [ ] Users can correct categories, save rules, and see the rule applied to future imports.
- [ ] "Delete my data" and "Export my data" both work and are tested.
- [ ] No outbound network calls in Local mode (verified by a test that blocks sockets in `modules/`).
- [ ] `pytest` ≥80% coverage on domain/data layers; CI green; demo deployed on a free tier.

---

*End of document. Implementation has not started — this is the design baseline for review.*
