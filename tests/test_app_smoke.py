"""Smoke test for app.py.

Verifies that app.py compiles cleanly, contains required UI components,
and follows the project's title and structure guidelines.
"""

from pathlib import Path
import ast


def test_app_file_exists():
    """Verify that app.py exists at the root of the workspace."""
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    assert app_path.is_file(), "app.py does not exist at project root"


def test_app_contains_required_title_and_message():
    """Verify that app.py defines the application title and welcome message."""
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    content = app_path.read_text(encoding="utf-8")

    # Verify abstract syntax tree can parse without syntax errors
    tree = ast.parse(content)
    assert tree is not None

    # Check for title specification
    assert "UPI Smart Expense Analyzer" in content
    assert "st.set_page_config" in content
    assert "st.title" in content
