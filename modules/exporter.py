"""Multi-format Report Exporter module for UPI Smart Expense Analyzer.

Provides independent, local-first export capabilities for:
1. Filtered CSV with formula-injection sanitization.
2. Formatted Multi-Sheet Excel (.xlsx) workbooks via openpyxl.
3. Clean, professional executive PDF reports via PyMuPDF.

Strict Guarantees:
- Decimal financial accuracy preserved throughout.
- Sensitive identifiers (internal IDs, file hashes, unmasked account numbers) are excluded.
- Zero external network transmission or paid API dependencies.
"""

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import io
import re
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd
import pymupdf

from modules.analytics import (
    calculate_category_breakdown,
    calculate_monthly_summary,
    calculate_top_merchants,
)
from modules.categorizer import mask_sensitive_account_numbers
from modules.money import format_inr, sum_money, to_money


# --- CSV Formula Injection Sanitization ---
def sanitize_csv_cell(value: Any) -> Any:
    """Sanitize cell contents to prevent CSV formula injection (DDE attacks).

    If a text value begins with formula trigger characters ('=', '+', '-', '@',
    tab, or newline), prepends a single quote so spreadsheet applications treat
    it strictly as literal text.

    Args:
        value: Any cell value.

    Returns:
        Sanitized value safe for CSV serialization.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)):
        return value

    text = str(value)
    if not text:
        return ""

    # Mask any sensitive account numbers present in text
    text = mask_sensitive_account_numbers(text)

    # Check for leading formula trigger symbols
    if text[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
        return f"'{text}"
    return text


def format_date_str(val: Any) -> str:
    """Format any date representation into ISO YYYY-MM-DD."""
    if val is None or pd.isna(val):
        return ""
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    return str(val)[:10]


# ==============================================================================
# 1. CSV Export
# ==============================================================================
def export_transactions_csv(
    df: pd.DataFrame,
    metadata: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Export filtered transaction records to standard UTF-8 CSV with injection protection.

    Excludes internal database primary keys, statement IDs, account IDs, and file hashes.

    Args:
        df: Filtered canonical DataFrame.
        metadata: Optional metadata dictionary.

    Returns:
        bytes: Encoded CSV file content (UTF-8 with BOM for universal Excel compatibility).
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Canonical public export headers
    headers = ["Date", "Merchant", "Description", "Category", "Mode", "Type", "Amount (INR)"]
    writer.writerow(headers)

    if not df.empty:
        # Sort by date descending
        sorted_df = df.sort_values(by="date", ascending=False)
        dates = sorted_df["date"].tolist() if "date" in sorted_df.columns else []
        merchants = sorted_df["merchant"].tolist() if "merchant" in sorted_df.columns else [""] * len(dates)
        narrations = sorted_df["narration"].tolist() if "narration" in sorted_df.columns else [""] * len(dates)
        categories = sorted_df["category"].tolist() if "category" in sorted_df.columns else ["Others & Misc"] * len(dates)
        modes = sorted_df["mode"].tolist() if "mode" in sorted_df.columns else ["UPI"] * len(dates)
        types = sorted_df["type"].tolist() if "type" in sorted_df.columns else ["DEBIT"] * len(dates)
        amounts = sorted_df["amount"].tolist() if "amount" in sorted_df.columns else [Decimal("0.00")] * len(dates)

        for d_val, m_val, n_val, c_val, mode_val, t_val, amt_val in zip(
            dates, merchants, narrations, categories, modes, types, amounts
        ):
            d_str = format_date_str(d_val)
            merchant = sanitize_csv_cell(m_val)
            narr = sanitize_csv_cell(n_val)
            cat = sanitize_csv_cell(c_val)
            mode = sanitize_csv_cell(mode_val)
            direction = str(t_val if t_val is not None else "DEBIT").upper()
            amt = to_money(amt_val)

            writer.writerow([d_str, merchant, narr, cat, mode, direction, f"{amt:.2f}"])

    # Encode with utf-8-sig (adds BOM) so Excel automatically parses UTF-8 without mojibake
    return output.getvalue().encode("utf-8-sig")


# ==============================================================================
# 2. Formatted Multi-Sheet Excel Export
# ==============================================================================
def export_transactions_excel(
    df: pd.DataFrame,
    metadata: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Export formatted multi-sheet Excel workbook using openpyxl.

    Sheets:
    1. Transaction Ledger: Full filtered transaction records with INR currency formatting.
    2. Category Breakdown: Total spend and share of wallet per category.
    3. Monthly Cashflow: Monthly inflow, outflow, routine spend, income, and savings rate.

    Args:
        df: Filtered canonical DataFrame.
        metadata: Optional metadata dictionary.

    Returns:
        bytes: Binary content of the .xlsx workbook.
    """
    wb = openpyxl.Workbook()

    # Shared Styles
    navy_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    right_align = Alignment(horizontal="right", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )

    # -------------------------------------------------------------------------
    # Sheet 1: Transaction Ledger
    # -------------------------------------------------------------------------
    ws_ledger = wb.active
    ws_ledger.title = "Transaction Ledger"
    ws_ledger.views.sheetView[0].showGridLines = True

    ledger_headers = ["Date", "Merchant", "Description", "Category", "Mode", "Type", "Amount (INR)"]
    ws_ledger.append(ledger_headers)

    for col_idx in range(1, len(ledger_headers) + 1):
        cell = ws_ledger.cell(row=1, column=col_idx)
        cell.fill = navy_fill
        cell.font = header_font
        cell.alignment = center_align

    if not df.empty:
        sorted_df = df.sort_values(by="date", ascending=False)
        dates = sorted_df["date"].tolist() if "date" in sorted_df.columns else []
        merchants = sorted_df["merchant"].tolist() if "merchant" in sorted_df.columns else [""] * len(dates)
        narrations = sorted_df["narration"].tolist() if "narration" in sorted_df.columns else [""] * len(dates)
        categories = sorted_df["category"].tolist() if "category" in sorted_df.columns else ["Others & Misc"] * len(dates)
        modes = sorted_df["mode"].tolist() if "mode" in sorted_df.columns else ["UPI"] * len(dates)
        types = sorted_df["type"].tolist() if "type" in sorted_df.columns else ["DEBIT"] * len(dates)
        amounts = sorted_df["amount"].tolist() if "amount" in sorted_df.columns else [Decimal("0.00")] * len(dates)

        for row_idx, (d_val, m_val, n_val, c_val, mode_val, t_val, amt_val) in enumerate(
            zip(dates, merchants, narrations, categories, modes, types, amounts), start=2
        ):
            d_str = format_date_str(d_val)
            merchant = mask_sensitive_account_numbers(str(m_val if m_val is not None else ""))
            narr = mask_sensitive_account_numbers(str(n_val if n_val is not None else ""))
            cat = str(c_val if (c_val is not None and not pd.isna(c_val)) else "Others & Misc")
            mode = str(mode_val if mode_val is not None else "UPI")
            direction = str(t_val if t_val is not None else "DEBIT").upper()
            amt = float(to_money(amt_val))

            ws_ledger.append([d_str, merchant, narr, cat, mode, direction, amt])

            # Apply row styling
            ws_ledger.cell(row=row_idx, column=1).alignment = center_align
            ws_ledger.cell(row=row_idx, column=2).alignment = left_align
            ws_ledger.cell(row=row_idx, column=3).alignment = left_align
            ws_ledger.cell(row=row_idx, column=4).alignment = left_align
            ws_ledger.cell(row=row_idx, column=5).alignment = center_align
            ws_ledger.cell(row=row_idx, column=6).alignment = center_align

            amt_cell = ws_ledger.cell(row=row_idx, column=7)
            amt_cell.alignment = right_align
            amt_cell.number_format = "#,##0.00"

            for c in range(1, 8):
                ws_ledger.cell(row=row_idx, column=c).font = data_font
                ws_ledger.cell(row=row_idx, column=c).border = thin_border
    else:
        ws_ledger.append(["No transaction records found matching the specified filters."])
        ws_ledger.merge_cells("A2:G2")
        ws_ledger.cell(row=2, column=1).alignment = center_align

    # -------------------------------------------------------------------------
    # Sheet 2: Category Breakdown
    # -------------------------------------------------------------------------
    ws_cat = wb.create_sheet(title="Category Breakdown")
    ws_cat.views.sheetView[0].showGridLines = True

    cat_headers = ["Category", "Macro Bucket", "Total Spend (INR)", "Share of Wallet", "Transactions"]
    ws_cat.append(cat_headers)

    for col_idx in range(1, len(cat_headers) + 1):
        cell = ws_cat.cell(row=1, column=col_idx)
        cell.fill = navy_fill
        cell.font = header_font
        cell.alignment = center_align

    cat_breakdown = calculate_category_breakdown(df) if not df.empty else []
    if cat_breakdown:
        for row_idx, item in enumerate(cat_breakdown, start=2):
            cat_name = item["category"]
            bucket = str(item.get("kind", item.get("macro_kind", "want"))).capitalize()
            spend = float(item["total_spend"])
            share = float(item["share_pct"]) / 100.0
            txns = item["txn_count"]

            ws_cat.append([cat_name, bucket, spend, share, txns])

            ws_cat.cell(row=row_idx, column=1).alignment = left_align
            ws_cat.cell(row=row_idx, column=2).alignment = center_align

            spend_cell = ws_cat.cell(row=row_idx, column=3)
            spend_cell.alignment = right_align
            spend_cell.number_format = "#,##0.00"

            share_cell = ws_cat.cell(row=row_idx, column=4)
            share_cell.alignment = right_align
            share_cell.number_format = "0.0%"

            txns_cell = ws_cat.cell(row=row_idx, column=5)
            txns_cell.alignment = center_align
            txns_cell.number_format = "#,##0"

            for c in range(1, 6):
                ws_cat.cell(row=row_idx, column=c).font = data_font
                ws_cat.cell(row=row_idx, column=c).border = thin_border
    else:
        ws_cat.append(["No category breakdown data available."])
        ws_cat.merge_cells("A2:E2")
        ws_cat.cell(row=2, column=1).alignment = center_align

    # -------------------------------------------------------------------------
    # Sheet 3: Monthly Cashflow
    # -------------------------------------------------------------------------
    ws_flow = wb.create_sheet(title="Monthly Cashflow")
    ws_flow.views.sheetView[0].showGridLines = True

    flow_headers = [
        "Month",
        "Total Inflow (INR)",
        "Total Outflow (INR)",
        "Routine Spend (INR)",
        "Inward Income (INR)",
        "Net Cash Flow (INR)",
        "Savings Rate",
        "Transactions",
    ]
    ws_flow.append(flow_headers)

    for col_idx in range(1, len(flow_headers) + 1):
        cell = ws_flow.cell(row=1, column=col_idx)
        cell.fill = navy_fill
        cell.font = header_font
        cell.alignment = center_align

    monthly_summary = calculate_monthly_summary(df) if not df.empty else []
    if monthly_summary:
        for row_idx, item in enumerate(monthly_summary, start=2):
            m_label = item["month_label"]
            inflow = float(item["total_credits"])
            outflow = float(item["total_debits"])
            routine = float(item["routine_spend"])
            income = float(item["income"])
            net_flow = float(item["net_cash_flow"])
            s_rate = float(item["savings_rate"]) / 100.0 if item["savings_rate"] is not None else "N/A"
            txns = item["txn_count"]

            ws_flow.append([m_label, inflow, outflow, routine, income, net_flow, s_rate, txns])

            ws_flow.cell(row=row_idx, column=1).alignment = center_align
            for col_c in range(2, 7):
                amt_c = ws_flow.cell(row=row_idx, column=col_c)
                amt_c.alignment = right_align
                amt_c.number_format = "#,##0.00"

            s_cell = ws_flow.cell(row=row_idx, column=7)
            s_cell.alignment = right_align
            if isinstance(s_rate, float):
                s_cell.number_format = "0.0%"
            else:
                s_cell.alignment = center_align

            t_cell = ws_flow.cell(row=row_idx, column=8)
            t_cell.alignment = center_align
            t_cell.number_format = "#,##0"

            for c in range(1, 9):
                ws_flow.cell(row=row_idx, column=c).font = data_font
                ws_flow.cell(row=row_idx, column=c).border = thin_border
    else:
        ws_flow.append(["No monthly cashflow records available."])
        ws_flow.merge_cells("A2:H2")
        ws_flow.cell(row=2, column=1).alignment = center_align

    # -------------------------------------------------------------------------
    # Auto-adjust Column Widths across all sheets
    # -------------------------------------------------------------------------
    # Adjust ws_ledger by sampling header + up to 100 data rows to prevent
    # iterating over hundreds of thousands of cell objects on large datasets.
    ledger_sample_rows = list(ws_ledger.iter_rows(min_row=1, max_row=min(ws_ledger.max_row, 101), values_only=True))
    if ledger_sample_rows:
        num_cols = len(ledger_sample_rows[0])
        for col_idx in range(num_cols):
            max_len = max((len(str(r[col_idx])) if r[col_idx] is not None else 0) for r in ledger_sample_rows)
            col_letter = get_column_letter(col_idx + 1)
            ws_ledger.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 50)

    # ws_cat and ws_flow have small bounded rows, so full column scanning is safe and fast
    for sheet in [ws_cat, ws_flow]:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = cell.value
                if val is not None:
                    max_len = max(max_len, len(str(val)))
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ==============================================================================
# 3. Clean Executive PDF Report Export
# ==============================================================================
def export_monthly_report_pdf(
    df: pd.DataFrame,
    metadata: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Generate a clean, aesthetic executive PDF financial statement using PyMuPDF.

    Features:
    - Executive Header with report period and local generation timestamp.
    - 4 Key Metric summary cards (Income, Routine Outflow, Net Cash Flow, Total Txns).
    - Category Spending Breakdown table.
    - Top Payees / Merchants table.
    - Informational disclaimer stating personal local-first privacy.
    - Gracefully handles empty filtered datasets without crashing.

    Args:
        df: Filtered canonical DataFrame.
        metadata: Optional metadata dictionary with period, account, or timestamp.

    Returns:
        bytes: Binary PDF document.
    """
    doc = pymupdf.open()
    page_width, page_height = 595.28, 841.89  # Standard A4 portrait
    page = doc.new_page(width=page_width, height=page_height)

    # Palette Constants
    c_navy = (0.118, 0.227, 0.541)  # #1E3A8A Primary Navy
    c_blue = (0.231, 0.510, 0.965)  # #3B82F6 Secondary Accent
    c_dark = (0.122, 0.161, 0.216)  # #1F2937 Charcoal text
    c_muted = (0.420, 0.447, 0.502)  # #6B7280 Slate gray text
    c_light_bg = (0.976, 0.980, 0.984)  # #F9FAFB Off-white
    c_border = (0.898, 0.906, 0.922)  # #E5E7EB Light border
    c_green = (0.020, 0.588, 0.412)  # #059669 Emerald
    c_red = (0.863, 0.149, 0.149)  # #DC2626 Crimson

    left_margin = 40.0
    right_margin = page_width - 40.0
    content_width = right_margin - left_margin

    # 1. Header Banner Box
    page.draw_rect(
        pymupdf.Rect(left_margin, 35, right_margin, 95),
        fill=c_navy,
        color=None,
    )
    page.insert_text(
        (left_margin + 16, 62),
        "UPI SMART EXPENSE ANALYZER",
        fontsize=16,
        fontname="helv",
        color=(1, 1, 1),
    )
    page.insert_text(
        (left_margin + 16, 80),
        "Personal Financial Statement & Expense Intelligence Report",
        fontsize=9,
        fontname="helv",
        color=(0.85, 0.90, 0.98),
    )

    # 2. Metadata Strip
    meta_y = 112
    meta = metadata or {}
    account_label = mask_sensitive_account_numbers(str(meta.get("account_label", "Primary Account")))
    gen_time = meta.get("generated_at", datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M UTC"))

    if not df.empty:
        min_d = df["date"].min()
        max_d = df["date"].max()
        period_str = f"{format_date_str(min_d)} to {format_date_str(max_d)}"
    else:
        period_str = "No Date Range"

    page.insert_text((left_margin, meta_y), f"Period: {period_str}", fontsize=9, fontname="helv", color=c_dark)
    page.insert_text((left_margin + 200, meta_y), f"Account: {account_label}", fontsize=9, fontname="helv", color=c_dark)
    page.insert_text((right_margin - 160, meta_y), f"Generated: {gen_time}", fontsize=9, fontname="helv", color=c_muted)

    page.draw_line(
        pymupdf.Point(left_margin, meta_y + 10),
        pymupdf.Point(right_margin, meta_y + 10),
        color=c_border,
        width=1,
    )

    # -------------------------------------------------------------------------
    # Handle Empty Dataset Gracefully
    # -------------------------------------------------------------------------
    if df.empty:
        empty_box = pymupdf.Rect(left_margin, 140, right_margin, 240)
        page.draw_rect(empty_box, fill=c_light_bg, color=c_border, width=1)
        page.insert_text(
            (left_margin + 30, 185),
            "No transaction records found matching the specified export criteria.",
            fontsize=12,
            fontname="helv",
            color=c_dark,
        )
        page.insert_text(
            (left_margin + 30, 205),
            "Please verify statement imports or adjust applied date/category filters.",
            fontsize=9,
            fontname="helv",
            color=c_muted,
        )

        # Footer & Disclaimer
        _draw_pdf_footer(page, left_margin, right_margin, page_height, c_muted, c_border)
        return doc.tobytes()

    # -------------------------------------------------------------------------
    # 3. Executive KPI Cards (4 Across)
    # -------------------------------------------------------------------------
    monthly_data = calculate_monthly_summary(df)
    total_income = sum((m["income"] for m in monthly_data), Decimal("0.00"))
    total_spend = sum((m["routine_spend"] for m in monthly_data), Decimal("0.00"))
    net_flow = total_income - total_spend
    total_txns = len(df)

    card_y = 135
    card_h = 55
    card_gap = 10
    card_w = (content_width - (3 * card_gap)) / 4.0

    cards = [
        ("INWARD INCOME", format_inr(total_income), c_green),
        ("ROUTINE EXPENSES", format_inr(total_spend), c_red),
        ("NET CASH FLOW", format_inr(net_flow), c_green if net_flow >= Decimal("0.00") else c_red),
        ("TRANSACTIONS", f"{total_txns:,}", c_navy),
    ]

    for i, (label, val_str, val_col) in enumerate(cards):
        cx = left_margin + (i * (card_w + card_gap))
        page.draw_rect(
            pymupdf.Rect(cx, card_y, cx + card_w, card_y + card_h),
            fill=c_light_bg,
            color=c_border,
            width=1,
        )
        page.insert_text((cx + 8, card_y + 18), label, fontsize=7.5, fontname="helv", color=c_muted)
        page.insert_text((cx + 8, card_y + 40), val_str, fontsize=11, fontname="helv", color=val_col)

    current_y = card_y + card_h + 25

    # -------------------------------------------------------------------------
    # 4. Category Spending Breakdown Table
    # -------------------------------------------------------------------------
    cat_breakdown = calculate_category_breakdown(df)
    page.insert_text((left_margin, current_y), "SPENDING BY CATEGORY", fontsize=11, fontname="helv", color=c_navy)
    current_y += 12

    # Category Table Headers
    th_h = 20
    page.draw_rect(pymupdf.Rect(left_margin, current_y, right_margin, current_y + th_h), fill=c_navy, color=None)
    page.insert_text((left_margin + 8, current_y + 14), "Category", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 170, current_y + 14), "Nature", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 280, current_y + 14), "Total Spend", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 390, current_y + 14), "Share", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 460, current_y + 14), "Txns", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    current_y += th_h

    row_h = 18
    # Render top categories
    for idx, c_item in enumerate(cat_breakdown[:8]):
        bg = c_light_bg if idx % 2 == 0 else (1.0, 1.0, 1.0)
        page.draw_rect(pymupdf.Rect(left_margin, current_y, right_margin, current_y + row_h), fill=bg, color=c_border, width=0.5)

        cat_title = str(c_item["category"])[:24]
        nature = str(c_item.get("kind", c_item.get("macro_kind", "want"))).capitalize()
        spend_str = format_inr(c_item["total_spend"])
        share_str = f"{c_item['share_pct']:.1f}%"
        count_str = str(c_item["txn_count"])

        page.insert_text((left_margin + 8, current_y + 12), cat_title, fontsize=8, fontname="helv", color=c_dark)
        page.insert_text((left_margin + 170, current_y + 12), nature, fontsize=8, fontname="helv", color=c_muted)
        page.insert_text((left_margin + 280, current_y + 12), spend_str, fontsize=8, fontname="helv", color=c_dark)
        page.insert_text((left_margin + 390, current_y + 12), share_str, fontsize=8, fontname="helv", color=c_dark)
        page.insert_text((left_margin + 460, current_y + 12), count_str, fontsize=8, fontname="helv", color=c_muted)
        current_y += row_h

    current_y += 20

    # -------------------------------------------------------------------------
    # 5. Top Payees & Merchants Table
    # -------------------------------------------------------------------------
    top_merchants = calculate_top_merchants(df, n=6)
    page.insert_text((left_margin, current_y), "TOP RECIPIENTS & MERCHANTS", fontsize=11, fontname="helv", color=c_navy)
    current_y += 12

    # Merchant Table Headers
    page.draw_rect(pymupdf.Rect(left_margin, current_y, right_margin, current_y + th_h), fill=c_navy, color=None)
    page.insert_text((left_margin + 8, current_y + 14), "Merchant / Payee", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 200, current_y + 14), "Category", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 340, current_y + 14), "Total Paid", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((left_margin + 460, current_y + 14), "Txns", fontsize=8.5, fontname="helv", color=(1, 1, 1))
    current_y += th_h

    for idx, m_item in enumerate(top_merchants):
        bg = c_light_bg if idx % 2 == 0 else (1.0, 1.0, 1.0)
        page.draw_rect(pymupdf.Rect(left_margin, current_y, right_margin, current_y + row_h), fill=bg, color=c_border, width=0.5)

        m_name = mask_sensitive_account_numbers(str(m_item["merchant"]))[:28]
        m_cat = str(m_item["category"])[:20]
        m_spend = format_inr(m_item["total_spend"])
        m_txns = str(m_item["txn_count"])

        page.insert_text((left_margin + 8, current_y + 12), m_name, fontsize=8, fontname="helv", color=c_dark)
        page.insert_text((left_margin + 200, current_y + 12), m_cat, fontsize=8, fontname="helv", color=c_muted)
        page.insert_text((left_margin + 340, current_y + 12), m_spend, fontsize=8, fontname="helv", color=c_dark)
        page.insert_text((left_margin + 460, current_y + 12), m_txns, fontsize=8, fontname="helv", color=c_muted)
        current_y += row_h

    # 6. Draw Footer & Disclaimer
    _draw_pdf_footer(page, left_margin, right_margin, page_height, c_muted, c_border)

    return doc.tobytes()


def _draw_pdf_footer(page, left_margin, right_margin, page_height, c_muted, c_border):
    """Draw standardized privacy disclaimer and footer line."""
    footer_y = page_height - 50
    page.draw_line(
        pymupdf.Point(left_margin, footer_y - 10),
        pymupdf.Point(right_margin, footer_y - 10),
        color=c_border,
        width=1,
    )
    disclaimer = (
        "Informational Disclaimer: Generated locally on-device by UPI Smart Expense Analyzer. "
        "Zero personal financial data was transmitted across the internet. "
        "This report is for personal recordkeeping only and does not constitute formal tax or banking advice."
    )
    page.insert_text(
        (left_margin, footer_y),
        disclaimer[:125],
        fontsize=7,
        fontname="helv",
        color=c_muted,
    )
    page.insert_text(
        (left_margin, footer_y + 10),
        disclaimer[125:],
        fontsize=7,
        fontname="helv",
        color=c_muted,
    )
    page.insert_text(
        (right_margin - 60, footer_y + 10),
        "Page 1 of 1",
        fontsize=7.5,
        fontname="helv",
        color=c_muted,
    )
