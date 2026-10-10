"""SQLite schema + helper functions for Indonesia Economic Dashboard.

Every connection is opened through the `db()` context manager, which guarantees
`close()` even when a query raises. Without it, an exception between `get_db()`
and `conn.close()` leaks a file descriptor; under gunicorn that eventually
surfaces as "too many open files".
"""
import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "economic_data.db")

INDICATOR_CODES = {
    "NY.GDP.MKTP.KD.ZG": "PDB Growth",
    "FP.CPI.TOTL.ZG": "Inflasi",
    "BN.GSR.GNFS.CD": "Trade Balance",
}


def get_db():
    """Return SQLite connection with row factory.

    timeout + busy_timeout + WAL are required on Render's ephemeral filesystem,
    where concurrent gunicorn workers can otherwise raise 'database is locked'.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def db(write=False):
    """Connection context manager: always closes, commits when asked.

    `with db() as conn:` guarantees close() on any exception, fixing the
    connection leak the code review flagged.
    """
    conn = get_db()
    try:
        yield conn
        if write:
            conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if not exist. Also sets WAL once for the database file."""
    with db(write=True) as conn:
        # WAL is a persistent property of the database file — setting it on every
        # connection (as before) was needless overhead on each request.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                value REAL,
                year INTEGER,
                fetched_at TEXT NOT NULL,
                UNIQUE(code, year)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)


def upsert_indicator(code, name, value, year):
    """Insert or update indicator value."""
    with db(write=True) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO indicators (code, name, value, year, fetched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (code, name, value, year, datetime.utcnow().isoformat()),
        )


def get_indicator_data(code, years=5):
    """Get last N years of data for an indicator, ordered by year desc."""
    with db() as conn:
        rows = conn.execute(
            """SELECT code, name, value, year, fetched_at
               FROM indicators WHERE code = ? AND value IS NOT NULL
               ORDER BY year DESC LIMIT ?""",
            (code, years),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest(code):
    """Get latest value for an indicator."""
    with db() as conn:
        row = conn.execute(
            """SELECT code, name, value, year, fetched_at
               FROM indicators WHERE code = ? AND value IS NOT NULL
               ORDER BY year DESC LIMIT 1""",
            (code,),
        ).fetchone()
    return dict(row) if row else None


def get_last_updated():
    """Get last updated timestamp from metadata."""
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_updated'"
        ).fetchone()
    return row["value"] if row else None


def set_last_updated():
    """Set last updated timestamp."""
    with db(write=True) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)""",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),),
        )


def count_rows():
    """Total indicator rows stored (used by /health to verify a deploy)."""
    try:
        with db() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM indicators").fetchone()
        return row["n"] if row else 0
    except Exception:
        return 0


def get_all_data():
    """Get all indicator data for dashboard."""
    result = {}
    for code, name in INDICATOR_CODES.items():
        result[code] = {
            "name": name,
            "data": get_indicator_data(code, years=5),
            "latest": get_latest(code),
        }
    return result
