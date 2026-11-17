# UI_DESIGN.md — Dashboard UI/UX Specification

**Document Type:** UI/UX Specification & Visual Design Blueprint  
**Status:** Approved for Implementation (Design Phase)  
**Target Platform:** Python Streamlit (`~1.3x` / `1.67+`) & Plotly  
**Design Philosophy:** Clean, distraction-free, financial clarity, and 100% local-first privacy.

---

## 1. Executive Summary & Design Principles

The **UPI Smart Expense Analyzer** dashboard is crafted to bridge the gap between complex financial bank statements and everyday personal spending habits. Daily UPI usage in India is characterized by high transaction frequency, micro-payments (tea, snacks, groceries, auto-rickshaw rides), and cryptic bank narrations (e.g., `UPI/432109876543/SWIGGY/PAYTM...`). 

The interface must transform this noisy stream of data into an intuitive, elegant, and reassuring financial control room.

### Core Design Principles
1. **The 3-Second Rule (Instant Orientation):** A user should understand their total spend, total income, and net position within 3 seconds of opening the dashboard.
2. **Noise Reduction:** Cryptic narrations must be abstracted into recognizable merchant labels, clean category tags, and human-readable dates.
3. **Local-First Reassurance:** Every screen subtly reinforces that financial data is strictly stored and processed on the user's local machine.
4. **Beginner-Friendly Ergonomics:** Clear visual hierarchies, plain-English labels (avoiding dense accounting jargon), and sensible defaults that work out of the box without complex configuration.

---

## 2. Dashboard Layout & Navigation Architecture

The application adopts a **single-page multi-view layout** powered by Streamlit's native sidebar navigation and structured tabs. This eliminates disruptive full-page browser reloads while keeping the workflow focused.

### 2.1 Information Architecture & View Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Top Header: Brand & Global Context                     │
├─────────────────┬───────────────────────────────────────────────────────────┤
│    SIDEBAR      │                       MAIN CONTENT AREA                   │
│                 │                                                           │
│ 💳 App Branding │  ┌─────────────────────────────────────────────────────┐  │
│ 🔒 Privacy Tag  │  │ [1] Statement Context & Quick Date-Range Selector   │  │
│                 │  └─────────────────────────────────────────────────────┘  │
│ Navigation:     │  ┌─────────────────────────────────────────────────────┐  │
│  ● Overview     │  │ [2] Summary KPI Cards (Debits, Credits, Net, Count) │  │
│  ○ Transactions │  └─────────────────────────────────────────────────────┘  │
│  ○ Upload File  │  ┌───────────────────────────┬─────────────────────────┐  │
│  ○ Insights     │  │ [3] Monthly Expense Trend │ [4] Category Breakdown  │  │
│  ○ Settings     │  │     (Plotly Bar/Area)     │     (Plotly Donut)      │  │
│                 │  └───────────────────────────┴─────────────────────────┘  │
│ Filters:        │  ┌─────────────────────────────────────────────────────┐  │
│  • Account      │  │ [5] Smart Spending Insights & Recommendations       │  │
│  • Date Range   │  └─────────────────────────────────────────────────────┘  │
│  • Categories   │  ┌─────────────────────────────────────────────────────┐  │
│                 │  │ [6] Recent Transactions Table (Cleaned View)        │  │
│ Storage Info    │  └─────────────────────────────────────────────────────┘  │
└─────────────────┴───────────────────────────────────────────────────────────┘
```

### 2.2 Wireframe Blueprint (Overview Screen)

```text
+----------------------------------------------------------------------------------------------------+
| 💳 UPI Smart Expense Analyzer        [ HDFC Bank ••••4912 v ]  [ Date Range: Jan 1 - Jan 31, 2026 v] |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------+  |
|  | TOTAL DEBITS (OUT) |  | TOTAL CREDITS (IN) |  | NET SAVINGS FLOW   |  | TRANSACTION COUNT    |  |
|  | ₹ 42,850.00        |  | ₹ 95,000.00        |  | +₹ 52,150.00       |  | 184 Transactions    |  |
|  | 🔺 +12.4% vs Dec   |  | 🟢 +5.0% vs Dec    |  | 54.9% Savings Rate |  | 142 Debits | 42 In |  |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------+  |
|                                                                                                    |
|  +-----------------------------------------------+  +--------------------------------------------+  |
|  | 📊 Monthly Spending Dynamics                  |  | 🍩 Expense Breakdown by Category          |  |
|  | [ Daily | Weekly | Monthly ]                  |  |                                            |  |
|  |                                               |  |            .--""""--.     ■ Food (34%)     |  |
|  |   ₹ |        █                                |  |          .'          '.   ■ Shopping (22%) |  |
|  |     |   █    █   █                            |  |         /   ₹42,850    \  ■ Utilities (18%)|  |
|  |     | █ █  █ █ █ █ █                          |  |         |    TOTAL     |  ■ Travel (14%)   |  |
|  |     +--------------------                     |  |         \             /   ■ Others (12%)   |  |
|  |       Jan 1       Jan 31                      |  |          '.          .'                    |  |
|  |   Hover: Jan 15 • ₹4,200 (Swiggy + Amazon)    |  |            '--....--'                      |  |
|  +-----------------------------------------------+  +--------------------------------------------+  |
|                                                                                                    |
|  +-----------------------------------------------------------------------------------------------+  |
|  | 💡 Smart Spending Insights & Observations                                                     |  |
|  | • 🔁 Recurring Detected: 3 Streaming subscriptions paid this month (₹1,198 total).            |  |
|  | • ☕ Micro-Spend Alert: 38 transactions below ₹150 totaled ₹3,420 (Chai, Quick Snacks).       |  |
|  | • 📈 Weekend Surge: 42% of food expenses occurred between Friday night and Sunday.           |  |
|  +-----------------------------------------------------------------------------------------------+  |
|                                                                                                    |
|  +-----------------------------------------------------------------------------------------------+  |
|  | 📑 Recent Transactions                           [ Search: "Swiggy" ]  [ Filter: All Types v ]|  |
|  | Date        | Description       | Category         | Mode   | Type   | Amount (INR)           |  |
|  |-------------|-------------------|------------------|--------|--------|------------------------|  |
|  | 31-Jan-2026 | Swiggy Food       | Food & Dining    | UPI    | DEBIT  | -₹ 485.00              |  |
|  | 30-Jan-2026 | TechCorp Salary   | Salary / Income  | IMPS   | CREDIT | +₹ 95,000.00           |  |
|  | 30-Jan-2026 | Zepto Groceries   | Groceries        | UPI    | DEBIT  | -₹ 620.00              |  |
|  | 29-Jan-2026 | Uber Rides        | Commute & Travel | UPI    | DEBIT  | -₹ 340.00              |  |
|  | 28-Jan-2026 | Ramesh Sharma     | P2P Transfer     | UPI    | DEBIT  | -₹ 1,500.00            |  |
|  | [ Showing latest 5 of 184 transactions • View All Transactions in Ledger -> ]                 |  |
|  +-----------------------------------------------------------------------------------------------+  |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Sidebar Design

The sidebar acts as the **global control tower** for application navigation, statement switching, date slicing, and privacy verification.

```text
┌────────────────────────────────────────┐
│ 💳 UPI Expense Analyzer                │
│    v0.1.0-dev                          │
│                                        │
│ 🔒 LOCAL MODE                          │
│ [🟢 Safe: 100% On-Device Processing]   │
├────────────────────────────────────────┤
│ VIEW NAVIGATION                        │
│ (o) 📊 Overview Dashboard              │
│ ( ) 📥 Upload & Ingest                 │
│ ( ) 📑 Transactions Ledger             │
│ ( ) 💡 Savings & Insights              │
│ ( ) ⚙️ Settings & Rules                │
├────────────────────────────────────────┤
│ ACTIVE FILTERS                         │
│ Bank Account:                          │
│ [ All Accounts (2 Statements)       v] │
│                                        │
│ Date Range:                            │
│ [ 01/01/2026 ] to [ 31/01/2026 ]       │
│ [ Quick Presets: 30D | 90D | This Year]│
│                                        │
│ Category Filter:                       │
│ [ All Selected (8 Categories)       v] │
├────────────────────────────────────────┤
│ SYSTEM HEALTH                          │
│ • Database: data/app.db (1.4 MB)       │
│ • Total Loaded: 382 txns               │
│ • Last Import: 14-Jan-2026             │
└────────────────────────────────────────┘
```

### Streamlit Implementation Blueprint
```python
# Design Specification for Sidebar (to be implemented in dashboard/overview.py)
with st.sidebar:
    st.markdown("### 💳 UPI Expense Analyzer")
    st.caption("v0.1.0-dev • Local Edition")
    
    # Privacy Status Badge
    st.success("🔒 **Local Mode:** 100% Offline", icon="🛡️")
    
    st.divider()
    
    # Navigation Radio
    selected_view = st.radio(
        "Navigation",
        options=["📊 Overview", "📥 Upload Statement", "📑 Transactions", "💡 Smart Insights", "⚙️ Settings"],
        index=0,
        label_visibility="collapsed"
    )
    
    st.divider()
    st.subheader("Filters")
    selected_account = st.selectbox("Bank Account", ["All Accounts", "HDFC Bank (••••4912)", "SBI (••••8102)"])
    date_range = st.date_input("Date Range", value=(start_date, end_date))
```

---

## 4. Summary KPI Cards

Summary cards deliver immediate situational awareness. They are arranged horizontally across four columns using `st.columns(4)`.

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ TOTAL DEBITS     │  │ TOTAL CREDITS    │  │ NET SAVINGS FLOW │  │ TRANSACTIONS     │
│ ₹ 42,850.00      │  │ ₹ 95,000.00      │  │ +₹ 52,150.00     │  │ 184 Total        │
│ 🔺 +12.4% vs Mo  │  │ 🟢 +5.0% vs Mo   │  │ 54.9% Rate       │  │ 142 Dr / 42 Cr   │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Component Specification

| Card Name | Metric Displayed | Delta & Subtext | Visual Indicator / Color | Design Rational |
| :--- | :--- | :--- | :--- | :--- |
| **Total Debits** | Primary outflow sum (`₹ 42,850.00`) | `+12.4% vs last month` | Coral Red / Warning delta (`delta_color="inverse"`) | Highlighting expense growth alerts users to lifestyle expansion. |
| **Total Credits** | Primary inflow sum (`₹ 95,000.00`) | `+5.0% vs last month` | Emerald Green / Normal delta (`delta_color="normal"`) | Clear indicator of total deposits, salary, and peer reimbursements. |
| **Net Savings Flow**| Inflow minus Outflow (`+₹ 52,150.00`) | `Savings Rate: 54.9%` | Indigo Accent / Informational | Net cash retained is the truest gauge of financial health. |
| **Activity Count** | Total transactions (`184 Txns`) | `142 debits • 42 credits` | Slate Gray / Neutral | Highlights micro-transaction frequency and volume. |

### Visual Layout via Streamlit
```python
col1, col2, col3, col4 = st.columns(4)

with col1:
    with st.container(border=True):
        st.caption("TOTAL DEBITS (OUTFLOW)")
        st.metric(label="Debits", value="₹ 42,850.00", delta="-12.4% vs last month", delta_color="inverse")

with col2:
    with st.container(border=True):
        st.caption("TOTAL CREDITS (INFLOW)")
        st.metric(label="Credits", value="₹ 95,000.00", delta="+5.0% vs last month", delta_color="normal")

with col3:
    with st.container(border=True):
        st.caption("NET SAVINGS RETAINED")
        st.metric(label="Net Flow", value="₹ 52,150.00", delta="54.9% Savings Rate", delta_color="off")

with col4:
    with st.container(border=True):
        st.caption("TRANSACTION VOLUME")
        st.metric(label="Volume", value="184", delta="142 Dr / 42 Cr", delta_color="off")
```

---

## 5. Monthly & Daily Expense Analysis (Plotly)

This section visualizes spending patterns across time to uncover expense spikes, weekend surges, and month-end burn rates.

```text
  Expense (INR)
   ₹ 5,000 ┤              █ [Jan 15: BigBasket ₹4,200]
   ₹ 4,000 ┤              █
   ₹ 3,000 ┤        █     █           █
   ₹ 2,000 ┤   █    █     █     █     █     █
   ₹ 1,000 ┤ █ █  █ █ █ █ █   █ █ █ █ █   █ █ █  ─── 7-Day Moving Avg
       ₹ 0 └─┬────┬────┬────┬────┬────┬────┬────┬──
            Jan1 Jan5 Jan10 Jan15 Jan20 Jan25 Jan31
```

### Chart Configuration & Design Choices
* **Chart Type:** Interactive Combined Bar Chart (Daily Spend) + Smoothed Spline (7-Day Moving Average).
* **Hover Data:** Detailed tooltip displaying Date, Total Spend, Highest Single Transaction of the day, and Primary Category.
* **Toolbar & Controls:** Granularity switch (`Daily`, `Weekly Aggregate`, `Monthly Totals`).

### Plotly Specification Blueprint
```python
import plotly.graph_objects as go

def build_expense_trend_chart(df_daily):
    fig = go.Figure()
    
    # Daily Bar Chart
    fig.add_trace(go.Bar(
        x=df_daily["date"],
        y=df_daily["amount"],
        name="Daily Expenses",
        marker_color="#F43F5E",
        opacity=0.85,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Daily Spend: ₹%{y:,.2f}<extra></extra>"
    ))
    
    # 7-day Moving Average Trendline
    fig.add_trace(go.Scatter(
        x=df_daily["date"],
        y=df_daily["moving_avg"],
        name="7-Day Average",
        line=dict(color="#4F46E5", width=2.5, shape="spline"),
        hovertemplate="7-Day Avg: ₹%{y:,.2f}<extra></extra>"
    ))
    
    fig.update_layout(
        title="Spending Dynamics Over Time",
        xaxis_title="",
        yaxis_title="Amount (₹)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=40, b=20),
        height=340
    )
    return fig
```

---

## 6. Expense Category Breakdown

To prevent cognitive overload from dozens of disparate merchants, transactions are structured into standard Indian UPI spending categories.

### 6.1 Donut Chart & Progress Split

```text
┌───────────────────────────────────────┬──────────────────────────────────────────┐
│  🍩 Proportional Spend Distribution    │  📋 Category Ranking & Budget Share      │
│                                       │                                          │
│             .--"""""--.               │  🍔 Food & Dining       ₹14,570  (34.0%) │
│           .'     |     '.             │  [███████████████░░░░░░░░░░░░░░░░░░░░░]  │
│          /   1   |   2   \            │  🛍️ Shopping & E-Com   ₹ 9,420  (22.0%) │
│         |        |        |           │  [██████████░░░░░░░░░░░░░░░░░░░░░░░░░░]  │
│         |   ₹ 42,850.00   |           │  ⚡ Utilities & Bills   ₹ 7,710  (18.0%) │
│          \   3   |   4   /            │  [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  │
│           '.     |     .'             │  🚗 Commute & Fuel      ₹ 6,000  (14.0%) │
│             '--.....--'               │  [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  │
│                                       │  📦 Others & Misc       ₹ 5,150  (12.0%) │
│  Center Label: Total Spend            │  [█████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  │
└───────────────────────────────────────┴──────────────────────────────────────────┘
```

### 6.2 Standardized Indian UPI Category Taxonomy

| Category Code | Display Label | Common UPI Entities Matched | Accent Color |
| :--- | :--- | :--- | :--- |
| `food_dining` | 🍔 Food & Dining | Swiggy, Zomato, Starbucks, Chai Point, local QSRs | Coral (`#F97316`) |
| `groceries` | 🛒 Groceries & Essentials | Zepto, Blinkit, Instamart, BigBasket, DMart | Emerald (`#10B981`) |
| `shopping` | 🛍️ Shopping & E-Commerce | Amazon, Flipkart, Myntra, Meesho, Zara | Purple (`#8B5CF6`) |
| `utilities` | ⚡ Utilities & Recharge | Bescom, Tata Power, Airtel, Jio, ACT Broadband | Amber (`#F59E0B`) |
| `travel` | 🚗 Commute & Fuel | Uber, Ola, Rapido, Namma Metro, Indian Oil, Shell | Cyan (`#06B6D4`) |
| `entertainment`| 🎬 Entertainment & Subs | Netflix, Spotify, BookMyShow, Prime, Hotstar | Pink (`#EC4899`) |
| `transfers` | 🔄 Transfers & P2P | Payments to friends, rent transfers, UPI VPAs | Slate (`#64748B`) |
| `uncategorized`| ❓ Others / Uncategorized| Unmatched retail UPI narrations | Light Gray (`#94A3B8`)|

### Design Rationale
* **Donut over Standard Pie:** The central hole prevents visual overcrowding and provides a prominent spot to display the aggregate total spend (`₹ 42,850.00`).
* **Paired Ranking List:** Donut charts make it difficult to compare slices with similar sizes (e.g., 18% vs 14%). Accompanying the chart with a ranked bar list provides immediate numerical clarity.

---

## 7. Recent Transactions Table

The transactions ledger displays parsed and cleaned transactions. It transforms raw bank narration lines into clean merchant names with category badges.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 📑 Recent Transactions Ledger                [🔍 Search merchant...]  [Filter: All Categories v] │
├────────────┬──────────────────┬──────────────────┬──────────────┬─────────┬──────────────────────┤
│ Date       │ Clean Merchant   │ Category Tag     │ Payment Mode │ Type    │ Amount (₹)           │
├────────────┼──────────────────┼──────────────────┼──────────────┼─────────┼──────────────────────┤
│ 31-01-2026 │ Swiggy Food      │ 🍔 Food & Dining │ UPI          │ DEBIT   │ -₹ 485.00            │
│ 30-01-2026 │ TechCorp Payroll │ 💼 Salary/Income │ IMPS         │ CREDIT  │ +₹ 95,000.00         │
│ 30-01-2026 │ Zepto Groceries  │ 🛒 Groceries     │ UPI          │ DEBIT   │ -₹ 620.00            │
│ 29-01-2026 │ Uber India       │ 🚗 Travel        │ UPI          │ DEBIT   │ -₹ 340.00            │
│ 28-01-2026 │ Suresh Patel     │ 🔄 Peer Transfer │ UPI          │ DEBIT   │ -₹ 1,500.00          │
└────────────┴──────────────────┴──────────────────┴──────────────┴─────────┴──────────────────────┤
│ Showing 5 of 184 transactions                                     [ ➡️ Open Full Interactive Grid ]│
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Streamlit `st.dataframe` Column Configuration
```python
# Specification for Transaction Table
st.dataframe(
    df_recent,
    column_config={
        "date": st.column_config.DateColumn("Date", format="DD-MMM-YYYY"),
        "merchant": st.column_config.TextColumn("Merchant / Description", width="medium"),
        "category": st.column_config.SelectboxColumn("Category", options=CATEGORY_LIST, width="small"),
        "mode": st.column_config.TextColumn("Mode", width="small"),
        "type": st.column_config.TextColumn("Type", width="small"),
        "amount": st.column_config.NumberColumn("Amount (₹)", format="₹ %.2f", width="small"),
    },
    use_container_width=True,
    hide_index=True
)
```

---

## 8. Bank Statement Upload Section (CSV and PDF)

The upload area is designed with progressive disclosure: simple initially, expanding into validation checks and column mapping only after a file is selected.

### 8.1 Wireframe: Upload States

#### State A: Default Drag-and-Drop Dropzone
```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│  📤 UPLOAD YOUR BANK STATEMENT                                                   │
│                                                                                  │
│      ┌────────────────────────────────────────────────────────────────────┐      │
│      │               📂 Drag and drop your bank file here                 │      │
│      │                    Limit 20MB • CSV or PDF                         │      │
│      │                     [ Browse Local Files ]                         │      │
│      └────────────────────────────────────────────────────────────────────┘      │
│                                                                                  │
│   🔒 Privacy Assurance: Your statement is processed entirely in your browser     │
│   and local memory. No data is sent to external servers or cloud APIs.           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

#### State B: Password Prompt (For Protected Bank PDFs)
```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│  🔒 Password-Protected PDF Statement Detected                                    │
│  File: HDFC_Jan2026_Statement.pdf (1.2 MB)                                       │
│                                                                                  │
│  Enter Statement Password:                                                       │
│  [ ••••••••••••••••             ] [ 🔓 Unlock & Parse ]                          │
│  ℹ️ Hint: HDFC passwords are typically your Customer ID or DOB (DDMMYYYY).        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

#### State C: Schema Mapping Confirmation (Format-Agnostic Preview)
```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│  ✅ File Detected: SBI_Savings_Jan.csv (428 Rows Found)                          │
│  Please confirm detected column headers before importing into local database:    │
│                                                                                  │
│  Transaction Date Column:      [ "Txn Date"                  v ]                 │
│  Description / Narration:      [ "Narration"                 v ]                 │
│  Withdrawal / Debit Column:    [ "Debit Amount"              v ]                 │
│  Deposit / Credit Column:      [ "Credit Amount"             v ]                 │
│  Account Balance Column:       [ "Closing Balance"           v ]                 │
│                                                                                  │
│  [ Cancel & Re-upload ]                       [ 💾 Confirm & Ingest 428 Txns ]   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Smart Spending Insights Section

The insights section surfaces automated patterns, anomalies, and actionable recommendations. Each observation is wrapped in a structured card with an icon and severity tag.

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 💡 Smart Spending Insights & Optimizations                                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 🔁 RECURRING SUBSCRIPTIONS DETECTED                            [ Potential Review ]│
│    You paid 3 subscriptions totaling ₹1,198 this month:                          │
│    • Netflix (₹649 on Jan 05) • Spotify (₹119 on Jan 12) • Hotstar (₹430)       │
│    💡 Suggestion: Consider an annual bundle or pause unused entertainment apps.  │
├──────────────────────────────────────────────────────────────────────────────────┤
│ ☕ THE "MICRO-SPEND" ACCUMULATOR                                     [ High Volume ]│
│    You executed 38 transactions under ₹150 this month, totaling ₹3,420.          │
│    92% of these were quick street food, tea stalls, and convenience items.       │
│    💡 Observation: These small taps represent 8% of your total monthly debits.   │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 📈 WEEKEND SPENDING SURGE                                          [ Discretionary ]│
│    Your average daily spend is ₹850 on weekdays vs ₹2,940 on weekends.          │
│    Friday evening to Sunday night accounts for 42% of your non-essential spend.  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Design Details
* **Container Styling:** Bordered cards with distinct left-accent colors (Blue for Informative, Amber for Savings Opportunity, Green for Financial Wins).
* **Evidence Traceability:** Every insight explicitly states the transaction rows that generated it (e.g., listing Netflix, Spotify, Hotstar dates and amounts).

---

## 10. Empty States (When No Statement is Uploaded)

An empty dashboard should never present blank voids or confusing broken charts. Instead, it must serve as an inviting onboarding guide.

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│                                💳                                                │
│                 Welcome to UPI Smart Expense Analyzer                            │
│                                                                                  │
│            You have not imported any bank statements yet.                        │
│     Upload your first statement to unlock instant spending analytics,            │
│          merchant categorization, and smart savings suggestions.                 │
│                                                                                  │
│        ┌─────────────────────────┐     ┌─────────────────────────┐               │
│        │   📂 Upload Statement   │     │   🎲 Try with Demo Data │               │
│        └─────────────────────────┘     └─────────────────────────┘               │
│                                                                                  │
│   Supported Formats:                                                             │
│   • Bank CSV exports (HDFC, SBI, ICICI, Axis, Kotak, etc.)                      │
│   • Original e-PDF statements (text-based)                                       │
│                                                                                  │
│   🔒 Privacy Guarantee: Your financial files never leave this machine.           │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Component Logic
* **Dual Action Buttons:**
  1. `Upload Statement`: Immediately directs user to the upload panel.
  2. `Try with Demo Data`: Populates the app with 150 synthetic transactions across 3 months so users can explore the dashboard features immediately.

---

## 11. Error Messages & File Validation States

Clear feedback prevents user frustration when dealing with corrupted files, unsupported scans, or password issues.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ❌ Unsupported File Type                                                         │
│ Only .csv and .pdf bank statements are supported. You selected "image_scan.jpg". │
│ Please download a digital statement from your bank's netbanking portal.          │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│ ⚠️ Scanned Document Warning                                                      │
│ The uploaded PDF contains scanned bitmap images with no extractable text.        │
│ UPI Smart Expense Analyzer requires a digital e-statement (vector text).         │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│ ℹ️ Statement Already Processed (Deduplication Check)                            │
│ "HDFC_Jan_2026.csv" has already been imported on 14-Jan-2026 (SHA-256 match).    │
│ Zero duplicate records were inserted into data/app.db.                           │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│ ⚠️ Reconciliation Variance Alert                                                │
│ Opening Balance + Total Credits - Total Debits differs from Closing Balance      │
│ by ₹ 450.00. Check "Review & Fix" for potentially missing or skipped rows.       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Responsive Layout Considerations

Streamlit apps must adapt seamlessly across screen resolutions—from wide monitors (1440px+) to laptops (1080px) and tablet/mobile viewports.

### Responsive Breakpoints & Layout Strategies

```text
WIDE DESKTOP (> 1200px)           LAPTOP / TABLET (768px - 1199px)      MOBILE (< 768px)
┌───┬───┬───┬───┐                ┌─────────┬─────────┐                ┌─────────────────┐
│ C1│ C2│ C3│ C4│  (4 Cols)      │   C1    │   C2    │  (2x2 Grid)    │       C1        │ (Stacked)
└───┴───┴───┴───┘                ├─────────┼─────────┤                ├─────────────────┤
┌─────────┬─────┐                │   C3    │   C4    │                │       C2        │
│ Chart 1 │Chart│ (7:5 Split)    └─────────┴─────────┘                ├─────────────────┤
│ (Trend) │  2  │                ┌───────────────────┐                │       C3        │
└─────────┴─────┘                │ Chart 1 (Trend)   │ (Stacked)      ├─────────────────┤
                                 ├───────────────────┤                │       C4        │
                                 │ Chart 2 (Donut)   │                └─────────────────┘
                                 └───────────────────┘
```

* **Plotly Chart Sizing:** All charts must use `autosize=True` and relative margins (`margin=dict(l=20, r=20, t=30, b=20)`) to ensure legends and tooltips remain visible without horizontal clipping.
* **Table Wrapping:** `use_container_width=True` on `st.dataframe` ensures columns automatically stretch and wrap smoothly on smaller screens.

---

## 13. Color Palette, Typography & Visual Theme

The visual design follows a modern **FinTech design language** (reminiscent of modern financial tools like Stripe and Zerodha) with high-contrast text and deliberate functional color coding.

### 13.1 Design Palette

```
  Primary Brand Indigo        Inflow / Income            Outflow / Expense
       #4F46E5                    #10B981                    #F43F5E
  [████████████████]         [████████████████]         [████████████████]
  Navigation & Accents       Credits & Positive Flow    Debits & Spending Spikes

   Warning / Caution          Background Dark           Card Container Dark
       #F59E0B                    #0F172A                    #1E293B
  [████████████████]         [████████████████]         [████████████████]
  Thresholds & Alerts        Main App Background        Bordered Content Cards
```

### 13.2 Color Tokens

| Token Name | Hex Code | Purpose / Application |
| :--- | :--- | :--- |
| `color-primary` | `#4F46E5` | Active page icons, trendline highlights, primary buttons |
| `color-inflow` | `#10B981` | Credit transactions, positive savings delta |
| `color-outflow` | `#F43F5E` | Debit transactions, expense metric bars |
| `color-warning` | `#F59E0B` | Subscription alerts, reconciliation discrepancy warnings |
| `color-neutral-dark` | `#0F172A` | Background base (Dark mode) |
| `color-card-dark` | `#1E293B` | Card container background with `#334155` border |
| `color-text-main` | `#F8FAFC` | Primary headlines and metric figures |
| `color-text-muted` | `#94A3B8` | Captions, dates, secondary labels |

### 13.3 Typography Hierarchy
* **Headings (`H1`, `H2`):** Bold Sans-Serif (`Inter`, `system-ui`), high-contrast (`#F8FAFC` in dark, `#0F172A` in light).
* **Financial Figures & Metrics:** Tabular figures (`SF Pro Display`, `Roboto Mono`, or monospace) to ensure digit alignment across summary cards and transaction amounts.
* **Body Text:** Clean, accessible 14px–16px sans-serif with a 1.5 line height for maximum readability.

---

## 14. Implementation Roadmap (Design to Code)

This document serves as the implementation contract for upcoming development stages:

1. **Step 1:** Implement `dashboard/overview.py` housing the KPI cards and chart containers.
2. **Step 2:** Implement `dashboard/charts.py` containing modular, testable Plotly builder functions.
3. **Step 3:** Implement `dashboard/upload.py` with multi-state drag-and-drop file ingestion and column mapping.
4. **Step 4:** Wire application services (`modules/analytics.py` and `modules/advisor.py`) to feed live SQLite data into the dashboard components.

---
*End of Design Specification Document.*
