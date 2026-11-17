"""Smoke test suite for UPI Smart Expense Analyzer.

Verifies that the foundational project packages are discoverable and importable.
"""


def test_project_structure():
    """Ensure core project packages can be imported successfully."""
    import config
    import dashboard
    import database
    import modules
    import services

    assert config is not None
    assert dashboard is not None
    assert database is not None
    assert modules is not None
    assert services is not None
