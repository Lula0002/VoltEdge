"""Shared database helper — MySQL (production) with SQLite fallback (local dev)

Usage:
    DATABASE_URL=mysql://user:password@host:3306/voltedge  → MySQL
    DATABASE_URL=     (unset)                              → SQLite (local dev)
"""

from __future__ import annotations
import os
import re
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "voltedge.db"


def _parse_mysql_url(url: str) -> dict:
    """Parse mysql://user:password@host:port/dbname"""
    pattern = r"mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    m = re.match(pattern, url)
    if not m:
        raise ValueError(
            f"Invalid DATABASE_URL format.\n"
            f"Expected: mysql://user:password@host:port/database\n"
            f"Got:      {url}"
        )
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4)),
        "database": m.group(5),
    }


def _is_mysql(conn) -> bool:
    """Check if a connection object is a MySQL connection."""
    return type(conn).__module__.startswith("mysql")


def get_connection():
    """Get a database connection.

    - DATABASE_URL starting with ``mysql://`` → MySQL (production)
    - Otherwise                              → SQLite (local dev)
    """
    url = os.getenv("DATABASE_URL", "")

    if url.startswith("mysql://"):
        import mysql.connector

        config = _parse_mysql_url(url)
        conn = mysql.connector.connect(**config)
        return conn

    # ── SQLite fallback for local development ──
    import sqlite3

    db_path = os.getenv("VOLTEDGE_DB_PATH", str(DEFAULT_DB_PATH))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_cursor(conn):
    """Return a cursor with dict-like row access for both backends."""
    if _is_mysql(conn):
        return conn.cursor(dictionary=True)
    return conn.cursor()


def execute(conn, query: str, params: tuple | None = None):
    """Execute *query* with *params*, handling parameter-style differences.

    SQLite uses ``?``, MySQL uses ``%s``.  This helper transparently
    converts the query string so the same ``?``-style queries work
    everywhere.
    """
    cursor = get_cursor(conn)
    if _is_mysql(conn):
        query = query.replace("?", "%s")
    cursor.execute(query, params or ())
    return cursor


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = get_cursor(conn)

    if _is_mysql(conn):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id     VARCHAR(36)  PRIMARY KEY,
                charger_id     VARCHAR(255) NOT NULL,
                contract_id    VARCHAR(255) NOT NULL,
                status         VARCHAR(50)  NOT NULL DEFAULT 'Created',
                start_time     VARCHAR(50),
                end_time       VARCHAR(50),
                energy_delivered DOUBLE,
                duration_minutes INT,
                charging_duration_minutes INT,
                total_cost DOUBLE,
                invoice_line_id VARCHAR(36)
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id       TEXT PRIMARY KEY,
                charger_id       TEXT NOT NULL,
                contract_id      TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'Created',
                start_time       TEXT,
                end_time         TEXT,
                energy_delivered  REAL,
                duration_minutes  INTEGER,
                charging_duration_minutes  INTEGER,
                total_cost       REAL,
                invoice_line_id       TEXT
            )
        """)

    # ── Create invoices table ──
    if _is_mysql(conn):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_line_id     VARCHAR(36)  PRIMARY KEY,
                session_id     VARCHAR(36)  NOT NULL,
                amount         DOUBLE       NOT NULL,
                currency       VARCHAR(10)  NOT NULL DEFAULT 'DKK',
                status         VARCHAR(50)  NOT NULL DEFAULT 'Generated',
                timestamp      VARCHAR(50)  NOT NULL
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_line_id       TEXT PRIMARY KEY,
                session_id       TEXT NOT NULL,
                amount           REAL NOT NULL,
                currency         TEXT NOT NULL DEFAULT 'DKK',
                status           TEXT NOT NULL DEFAULT 'Generated',
                timestamp        TEXT NOT NULL
            )
        """)

    # ── Add temperature + hour_of_day columns (if not already present) ──
    # Supports ML dynamic pricing: weather at charging time determines kWh price
    if _is_mysql(conn):
        for col, dtype in [("temperature", "DOUBLE"), ("hour_of_day", "INT")]:
            try:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col} {dtype}")
            except Exception:
                pass  # Column already exists
    else:
        for col, dtype in [("temperature", "REAL"), ("hour_of_day", "INTEGER")]:
            try:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col} {dtype}")
            except Exception:
                pass  # Column already exists

    conn.commit()
    cursor.close()
    conn.close()
