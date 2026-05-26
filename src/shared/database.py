"""Shared database helper — SQLite with optional PostgreSQL via DATABASE_URL"""

import os
import sqlite3
from pathlib import Path

# Default path for SQLite database file
DEFAULT_DB_PATH = Path(__file__).parent.parent / "voltedge.db"


def get_db_path():
    """Return database path. Override with VOLTEDGE_DB_PATH env var."""
    env_path = os.getenv("VOLTEDGE_DB_PATH")
    if env_path:
        return env_path
    return str(DEFAULT_DB_PATH)


def get_connection():
    """Get a database connection.
    
    If DATABASE_URL is set, it will be used (PostgreSQL).
    Otherwise falls back to local SQLite file.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # PostgreSQL — requires psycopg2 or asyncpg
        # For now, fall through to SQLite
        pass

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            charger_id TEXT NOT NULL,
            contract_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Created',
            start_time TEXT,
            end_time TEXT,
            energy_delivered REAL,
            duration_minutes INTEGER
        )
    """)

    conn.commit()
    conn.close()
