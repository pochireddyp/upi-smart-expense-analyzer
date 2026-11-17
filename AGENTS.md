# AGENTS.md — Developer & AI Agent Guidelines

Welcome to the **UPI Smart Expense Analyzer** codebase! This document outlines the architectural standards, coding principles, and development conventions that all contributors (human developers and AI agents alike) must follow.

---

## 1. Core Architecture Principles

The project follows a **layered monolith** architecture designed to be beginner-friendly, modular, and easily testable:

```
UI (app.py, dashboard/)
       │
       ▼
Application Services (services/)
       │
       ▼
Domain & Ingestion Modules (modules/)
       │
       ▼
Data Access & Storage (database/ -> SQLite)
```

### Strict One-Way Dependency Rules
* **UI Layer (`app.py`, `dashboard/`)**: Handles presentation, Streamlit layout, widgets, and user interaction. **Must NOT** perform SQL queries or implement core business logic.
* **Services Layer (`services/`)**: Orchestrates workflows (e.g., parsing a statement, running deduplication, triggering categorization).
* **Domain & Ingestion (`modules/`)**: Pure business logic, normalization, models, and calculation. **Must NOT** import Streamlit or execute direct SQL.
* **Data Access (`database/`)**: All SQL queries, SQLite connections, and migrations live here. **Must NOT** contain presentation or UI code.

---

## 2. Critical Financial Accuracy Rules (Money Math)

> [!IMPORTANT]
> **Never use floating-point numbers (`float`) for money arithmetic.**
> Floating point inaccuracies (e.g., `0.1 + 0.2 = 0.30000000000000004`) lead to reconciliation errors in financial applications.

1. **In Python Code:**
   * Always use Python's built-in `decimal.Decimal` for amounts.
   * Rounding mode must always be `ROUND_HALF_UP` to two decimal places for display.
   * Centralize money creation and rounding in `modules/money.py`.
2. **In SQLite Storage:**
   * Store all currency amounts as **integer minor units** (paise: ₹1 = 100 paise).
   * Example: ₹499.50 is stored as integer `49950`.

---

## 3. Privacy & Local-First Invariants

This project is strictly **local-first**:
* **Zero Outbound Data:** User bank statements and transaction details must **never** be transmitted across the internet. No external cloud analytics, telemetry, or paid LLM/OCR APIs.
* **Data Minimization:** Store only the last 4 digits of bank account numbers (`account_last4`). Never log or persist full card numbers or sensitive credentials.
* **Upload Safety:** Uploaded files staged in `data/uploads/` must be cleaned up immediately after processing in a `finally` block.
* **Git Safety:** Always check `.gitignore`. Never commit `.csv`, `.pdf`, `.db`, or `.env` files containing personal financial data.

---

## 4. Coding Standards for Beginners & Maintainers

* **Readability First:** Prefer simple, self-explanatory code over clever one-liners.
* **Type Annotations:** Annotate function parameters and return types using Python's standard `typing` features.
  ```python
  def parse_amount(raw_text: str) -> Decimal:
      ...
  ```
* **Comprehensive Docstrings:** Every module, class, and function should have a clear docstring explaining:
  * What it does
  * Parameters (`Args:`)
  * Return values (`Returns:`)
  * Possible exceptions (`Raises:`)
* **Standard Library Over New Dependencies:** Prefer Python standard library modules (`csv`, `sqlite3`, `pathlib`, `decimal`, `datetime`) where feasible.
* **Free & Open-Source Only:** Never introduce proprietary or paid libraries.

---

## 5. Testing & Verification

* All business logic, parsers, and services must be covered by `pytest` unit tests in the `tests/` directory.
* Use in-memory SQLite (`:memory:`) or pytest's `tmp_path` fixture for database and file tests. Tests must never modify `data/app.db`.
* **Before committing or finishing any task, run:**
  ```powershell
  pytest
  ```
* Ensure all tests pass with zero warnings or failures.

---

## 6. Incremental Development Rules

* **Phase 1 Focus:** Project structure, configuration, basic Streamlit entry point, tests, and documentation.
* **Do NOT:**
  * Implement partial CSV/PDF parsing until the schema detection and domain models are specified.
  * Add unrequested features or external API dependencies.
  * Overwrite existing documentation or architecture specs without reviewing them.
