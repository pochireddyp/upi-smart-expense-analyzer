"""Database connection management, migrations runner, and transaction scopes.

Ensures strict SQLite invariants:
- PRAGMA foreign_keys = ON on all connections.
- PRAGMA journal_mode = WAL for concurrent performance.
- Atomic transaction rollbacks.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Generator, List, Optional, Union

# Default local database location
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection(db_path: Optional[Union[Path, str]] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with foreign keys and WAL mode.

    Args:
        db_path: Optional path to SQLite file or ':memory:'.

    Returns:
        sqlite3.Connection: Configured connection instance.
    """
    target_path = str(db_path) if db_path is not None else str(DEFAULT_DB_PATH)

    # Ensure parent directory exists for file-based databases
    if target_path != ":memory:":
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enforce SQLite Invariants
    conn.execute("PRAGMA foreign_keys = ON;")
    if target_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    return conn


@contextmanager
def transaction_scope(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for atomic unit-of-work database transactions.

    Yields the connection, then commits if no errors occur, or rolls back
    completely if any exception is raised.

    Args:
        conn: Open SQLite connection.
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def run_migrations(conn: sqlite3.Connection) -> int:
    """Discover and apply all unapplied SQL migration scripts in order.

    Args:
        conn: Open SQLite connection.

    Returns:
        int: Number of new migrations applied.
    """
    # Create migration tracking table if not present
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    # Query currently applied migration versions
    cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
    applied_versions = {row["version"] for row in cursor.fetchall()}

    # Discover migration files (e.g. 001_initial_schema.sql)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    newly_applied = 0

    for m_file in migration_files:
        # Extract version number prefix
        try:
            version_num = int(m_file.name.split("_")[0])
        except (ValueError, IndexError):
            continue

        if version_num not in applied_versions:
            sql_script = m_file.read_text(encoding="utf-8")
            with transaction_scope(conn):
                conn.executescript(sql_script)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                    (version_num, m_file.name, datetime.now(timezone.utc).isoformat()),
                )
            newly_applied += 1

    return newly_applied


def init_db(db_path: Optional[Union[Path, str]] = None) -> Path:
    """Initialize the database and ensure all migrations are up to date.

    Args:
        db_path: Optional path to SQLite file.

    Returns:
        Path: Path to initialized SQLite database.
    """
    target = Path(db_path) if db_path is not None and str(db_path) != ":memory:" else DEFAULT_DB_PATH
    conn = get_connection(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()
    return target
