"""Root test configuration and dynamic synthetic test fixtures.

Generates 100% synthetic mock statement files in pytest session-scoped temporary
directories (tmp_path_factory) so that automated tests never depend on or access
real bank statement files in sample_data/.
"""

from pathlib import Path
import pytest

from sample_data.create_sample_csvs import create_hdfc_sample_csv, create_sbi_sample_csv
from sample_data.create_sample_pdfs import (
    create_hdfc_sample_pdf,
    create_locked_sample_pdf,
    create_scanned_stub_pdf,
)


@pytest.fixture(scope="session")
def synthetic_fixtures_dir(tmp_path_factory) -> Path:
    """Session-scoped fixture directory containing dynamically generated synthetic statements."""
    temp_dir = tmp_path_factory.mktemp("synthetic_statements")

    # Generate synthetic CSV statements
    create_hdfc_sample_csv(temp_dir / "sample_hdfc_statement.csv")
    create_sbi_sample_csv(temp_dir / "sample_sbi_statement.csv")

    # Generate synthetic PDF statements
    create_hdfc_sample_pdf(temp_dir / "sample_hdfc_statement.pdf")
    create_locked_sample_pdf(temp_dir / "sample_locked_statement.pdf", password="password123")
    create_scanned_stub_pdf(temp_dir / "sample_scanned_stub.pdf")

    return temp_dir


@pytest.fixture(scope="session")
def synthetic_hdfc_csv(synthetic_fixtures_dir: Path) -> Path:
    """Path to dynamically generated synthetic HDFC statement CSV."""
    return synthetic_fixtures_dir / "sample_hdfc_statement.csv"


@pytest.fixture(scope="session")
def synthetic_sbi_csv(synthetic_fixtures_dir: Path) -> Path:
    """Path to dynamically generated synthetic SBI statement CSV."""
    return synthetic_fixtures_dir / "sample_sbi_statement.csv"


@pytest.fixture(scope="session")
def synthetic_hdfc_pdf(synthetic_fixtures_dir: Path) -> Path:
    """Path to dynamically generated synthetic HDFC statement PDF."""
    return synthetic_fixtures_dir / "sample_hdfc_statement.pdf"


@pytest.fixture(scope="session")
def synthetic_locked_pdf(synthetic_fixtures_dir: Path) -> Path:
    """Path to dynamically generated synthetic password-encrypted statement PDF."""
    return synthetic_fixtures_dir / "sample_locked_statement.pdf"


@pytest.fixture(scope="session")
def synthetic_scanned_pdf(synthetic_fixtures_dir: Path) -> Path:
    """Path to dynamically generated synthetic scanned/image-only statement PDF."""
    return synthetic_fixtures_dir / "sample_scanned_stub.pdf"
