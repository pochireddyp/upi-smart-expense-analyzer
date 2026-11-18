"""Plotly interactive chart builders for UPI Smart Expense Analyzer.

This module provides pure, testable visualization functions that transform
transaction DataFrames into responsive Plotly figures.
"""

from decimal import Decimal
import pandas as pd
import plotly.graph_objects as go

from modules.money import format_inr, sum_money

# Standard accessible palette for Indian UPI categories
CATEGORY_COLORS = {
    "Food & Dining": "#F97316",           # Coral Orange
    "Groceries & Essentials": "#10B981",  # Emerald Green
    "Shopping & E-Com": "#8B5CF6",        # Purple
    "Utilities & Bills": "#F59E0B",       # Amber
    "Commute & Travel": "#06B6D4",        # Cyan
    "Entertainment & Subs": "#EC4899",    # Pink
    "Rent & Housing": "#6366F1",          # Indigo
    "Health & Medical": "#14B8A6",        # Teal
    "Peer Transfers": "#64748B",          # Slate Gray
    "Others & Misc": "#94A3B8",           # Light Gray
}


def build_expense_trend_chart(df: pd.DataFrame) -> go.Figure:
    """Build an interactive daily spending bar chart with a 7-day moving average.

    Args:
        df: DataFrame containing transactions with 'date', 'type', and 'amount'.

    Returns:
        go.Figure: Plotly chart figure.
    """
    debits = df[df["type"] == "DEBIT"].copy()
    if debits.empty:
        fig = go.Figure()
        fig.add_annotation(text="No debit transactions found", showarrow=False)
        return fig

    # Group by date and calculate total daily spend
    daily_spend = debits.groupby("date")["amount"].apply(lambda s: float(sum_money(s))).reset_index()
    daily_spend = daily_spend.sort_values(by="date")

    # Calculate 7-day rolling average (minimum 1 period)
    daily_spend["moving_avg"] = daily_spend["amount"].rolling(window=7, min_periods=1).mean()

    fig = go.Figure()

    # Daily expense bars
    fig.add_trace(go.Bar(
        x=daily_spend["date"],
        y=daily_spend["amount"],
        name="Daily Expenses",
        marker_color="#F43F5E",
        opacity=0.85,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Daily Spend: ₹ %{y:,.2f}<extra></extra>"
    ))

    # 7-day moving average trendline
    fig.add_trace(go.Scatter(
        x=daily_spend["date"],
        y=daily_spend["moving_avg"],
        name="7-Day Moving Avg",
        line=dict(color="#4F46E5", width=2.5, shape="spline"),
        hovertemplate="7-Day Avg: ₹ %{y:,.2f}<extra></extra>"
    ))

    fig.update_layout(
        title="<b>Daily Spending Dynamics</b>",
        xaxis_title="",
        yaxis_title="Amount (₹)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=50, b=20),
        height=350,
        hovermode="x unified",
    )
    return fig


def build_category_donut_chart(df: pd.DataFrame) -> go.Figure:
    """Build an interactive category breakdown donut chart with centered total spend.

    Args:
        df: DataFrame containing transactions with 'category', 'type', and 'amount'.

    Returns:
        go.Figure: Plotly donut chart figure.
    """
    debits = df[df["type"] == "DEBIT"].copy()
    if debits.empty:
        fig = go.Figure()
        fig.add_annotation(text="No expenses to categorize", showarrow=False)
        return fig

    total_debit_decimal = sum_money(debits["amount"])
    cat_summary = debits.groupby("category")["amount"].apply(lambda s: float(sum_money(s))).reset_index()
    cat_summary = cat_summary.sort_values(by="amount", ascending=False)

    colors = [CATEGORY_COLORS.get(cat, "#94A3B8") for cat in cat_summary["category"]]

    fig = go.Figure()

    fig.add_trace(go.Pie(
        labels=cat_summary["category"],
        values=cat_summary["amount"],
        hole=0.6,
        marker=dict(colors=colors, line=dict(color="#1E293B", width=1.5)),
        textinfo="percent",
        hovertemplate="<b>%{label}</b><br>Spend: ₹ %{value:,.2f}<br>Share: %{percent}<extra></extra>",
    ))

    # Center label showing formatted total expenses
    formatted_total = format_inr(total_debit_decimal)
    fig.update_layout(
        title="<b>Expense Category Breakdown</b>",
        annotations=[dict(
            text=f"Total<br><b>{formatted_total}</b>",
            x=0.5, y=0.5,
            font_size=14,
            showarrow=False
        )],
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=50, b=30),
        height=350,
    )
    return fig
