"""SQLite schema + helper functions for Indonesia Economic Dashboard."""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "economic_data.db")


def get_db():
    """Return SQLite connection with row factory.

    timeout + busy_timeout + WAL are required on Render's ephemeral filesystem,
    where concurrent gunicorn workers can otherwise raise 'database is locked'.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    """Create tables if not exist."""
    conn = get_db()
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
    conn.commit()
    conn.close()


def upsert_indicator(code, name, value, year):
    """Insert or update indicator value."""
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO indicators (code, name, value, year, fetched_at)
           VALUES (?, ?, ?, ?, ?)""",
        (code, name, value, year, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_indicator_data(code, years=5):
    """Get last N years of data for an indicator, ordered by year desc."""
    conn = get_db()
    rows = conn.execute(
        """SELECT code, name, value, year, fetched_at
           FROM indicators WHERE code = ? AND value IS NOT NULL
           ORDER BY year DESC LIMIT ?""",
        (code, years),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest(code):
    """Get latest value for an indicator."""
    conn = get_db()
    row = conn.execute(
        """SELECT code, name, value, year, fetched_at
           FROM indicators WHERE code = ? AND value IS NOT NULL
           ORDER BY year DESC LIMIT 1""",
        (code,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_last_updated():
    """Get last updated timestamp from metadata."""
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'last_updated'"
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def set_last_updated():
    """Set last updated timestamp."""
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)""",
        (datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),),
    )
    conn.commit()
    conn.close()


def get_all_data():
    """Get all indicator data for dashboard."""
    codes = {
        "NY.GDP.MKTP.KD.ZG": "PDB Growth",
        "FP.CPI.TOTL.ZG": "Inflasi",
        "BN.GSR.GNFS.CD": "Trade Balance",
    }
    result = {}
    for code, name in codes.items():
        result[code] = {
            "name": name,
            "data": get_indicator_data(code, years=5),
            "latest": get_latest(code),
        }
    return result
