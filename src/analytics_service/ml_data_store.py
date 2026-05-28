"""ML Data Store — Persistent storage for training data, predictions, and model state

Analytics/ML is an external capability with its own dedicated database.
This keeps ML data separate from the operational session/billing data.

Tables:
  - training_data: features + actual energy consumed (appended over time)
  - predictions:   every prediction made (for PowerBI accuracy analysis)
  - model_state:   current model coefficients, intercept, R2 score
"""

from __future__ import annotations

import ast
import os
import sqlite3
from pathlib import Path
from typing import Optional


# ── Database location ─────────────────────────────────────────
DEFAULT_DB_PATH = Path(__file__).parent.parent / "ml_training.db"


def get_db_path() -> str:
    """Allow override via env var for testing."""
    return os.getenv("VOLTEDGE_ML_DB_PATH", str(DEFAULT_DB_PATH))


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Schema ─────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS training_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    duration_minutes INTEGER NOT NULL,
    temperature      REAL    NOT NULL,
    hour_of_day      INTEGER NOT NULL,
    actual_energy_kwh REAL   NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    duration_minutes INTEGER NOT NULL,
    temperature      REAL    NOT NULL,
    hour_of_day      INTEGER NOT NULL,
    predicted_kwh    REAL    NOT NULL,
    actual_kwh       REAL,
    model_version    TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slope            TEXT    NOT NULL,
    intercept        REAL    NOT NULL,
    r2_score         REAL,
    training_count   INTEGER NOT NULL DEFAULT 0,
    trained_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_initialized = False


def init_db():
    """Create tables if they don't exist. Idempotent — safe to call multiple times."""
    global _initialized
    if _initialized:
        return
    conn = _get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    _initialized = True


# ── Training Data ──────────────────────────────────────────────

def clear_training_data():
    """Delete all training data and predictions. Used for re-seeding."""
    init_db()
    conn = _get_connection()
    conn.execute("DELETE FROM training_data")
    conn.execute("DELETE FROM predictions")
    conn.execute("DELETE FROM model_state")
    conn.commit()
    conn.close()


def training_data_exists() -> bool:
    """Return True if at least one training data row exists."""
    init_db()
    conn = _get_connection()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM training_data").fetchone()
    conn.close()
    return row["cnt"] > 0


def add_training_data(
    duration_minutes: int,
    temperature: float,
    hour_of_day: int,
    actual_energy_kwh: float,
) -> int:
    """Insert a new training data point. Returns the row id."""
    init_db()
    conn = _get_connection()
    cursor = conn.execute(
        "INSERT INTO training_data (duration_minutes, temperature, hour_of_day, actual_energy_kwh) "
        "VALUES (?, ?, ?, ?)",
        (duration_minutes, temperature, hour_of_day, actual_energy_kwh),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_all_training_data() -> list[dict]:
    """Return all training data ordered by creation time."""
    init_db()
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, duration_minutes, temperature, hour_of_day, actual_energy_kwh, created_at "
        "FROM training_data ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Predictions ────────────────────────────────────────────────

def add_prediction(
    duration_minutes: int,
    temperature: float,
    hour_of_day: int,
    predicted_kwh: float,
    model_version: str,
) -> int:
    """Record a prediction. Returns the row id."""
    init_db()
    conn = _get_connection()
    cursor = conn.execute(
        "INSERT INTO predictions (duration_minutes, temperature, hour_of_day, predicted_kwh, model_version) "
        "VALUES (?, ?, ?, ?, ?)",
        (duration_minutes, temperature, hour_of_day, predicted_kwh, model_version),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def record_actual(prediction_id: int, actual_kwh: float) -> bool:
    """Record the actual energy for a previous prediction. Returns True if found."""
    init_db()
    conn = _get_connection()
    cursor = conn.execute(
        "UPDATE predictions SET actual_kwh = ? WHERE id = ?",
        (actual_kwh, prediction_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_prediction_by_id(prediction_id: int) -> Optional[dict]:
    """Return a single prediction by id, or None if not found."""
    init_db()
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, duration_minutes, temperature, hour_of_day, predicted_kwh, actual_kwh, model_version, created_at "
        "FROM predictions WHERE id = ?",
        (prediction_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_predictions() -> list[dict]:
    """Return all predictions ordered by creation time."""
    init_db()
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, duration_minutes, temperature, hour_of_day, predicted_kwh, actual_kwh, model_version, created_at "
        "FROM predictions ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_predictions_with_actual() -> list[dict]:
    """Return predictions where actual_kwh has been recorded (for accuracy analysis)."""
    init_db()
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, duration_minutes, temperature, hour_of_day, predicted_kwh, actual_kwh, "
        "       (predicted_kwh - actual_kwh) AS error, "
        "       ROUND(100.0 * (predicted_kwh - actual_kwh) / actual_kwh, 2) AS error_pct, "
        "       model_version, created_at "
        "FROM predictions "
        "WHERE actual_kwh IS NOT NULL "
        "ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Model State ────────────────────────────────────────────────

def save_model_state(
    coefficients: list[float],
    intercept: float,
    r2_score: Optional[float],
    training_count: int,
):
    """Save the current model state (overwrites previous)."""
    init_db()
    conn = _get_connection()
    conn.execute("DELETE FROM model_state")  # keep only latest
    conn.execute(
        "INSERT INTO model_state (slope, intercept, r2_score, training_count) VALUES (?, ?, ?, ?)",
        (str(coefficients), intercept, r2_score, training_count),
    )
    conn.commit()
    conn.close()


def get_model_state() -> Optional[dict]:
    """Return the latest model state, or None if never saved."""
    init_db()
    conn = _get_connection()
    row = conn.execute(
        "SELECT slope, intercept, r2_score, training_count, trained_at "
        "FROM model_state ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    # Parse the stored string back to a list of floats
    result["coefficients"] = ast.literal_eval(result.pop("slope"))
    return result
