"""ML Model — Linear Regression for energy & revenue prediction

Isolated from the API layer so the ML code can be replaced or reused independently.
On first startup the database is seeded with training data so the model never
starts from zero. All training data lives in the ML database (ml_training.db).

The model state (coefficients, R2) is persisted so PowerBI can visualise
the regression line.

To seed with your own historical data:
  1. Place a CSV at  scripts/ml_seed_data.csv  (columns: duration_minutes,
     temperature, hour_of_day, actual_energy_kwh), OR
  2. Set the env var  VOLTEDGE_ML_SEED_CSV  to point to your CSV, OR
  3. Run  python scripts/import_ml_data.py path/to/your_data.csv
     (this can be done anytime, even after the app has started)
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from analytics_service.ml_data_store import (
    save_model_state,
    get_all_training_data,
    add_training_data,
    training_data_exists,
    clear_training_data,
)


# ── Fallback seed data (used if no CSV is provided) ────────────
# Features: [duration_minutes, temperature, hour_of_day]

FALLBACK_SEED = [
    (10,  20, 10,  2.0),   # 10 min, 20°C, at 10:00
    (20,  18, 14,  4.5),   # 20 min, 18°C, at 14:00
    (30,  15,  8,  7.5),   # 30 min, 15°C, at 08:00
    (45,  22, 12, 11.5),   # 45 min, 22°C, at 12:00
    (60,  20, 14, 15.0),   # 60 min, 20°C, at 14:00
    (60,   5, 18, 17.5),   # 60 min,  5°C, at 18:00 (cold = more energy)
    (60,  30,  9, 13.0),   # 60 min, 30°C, at 09:00 (hot = less energy)
    (90,  20, 16, 22.5),   # 90 min, 20°C, at 16:00
    (120, 10, 20, 31.0),   # 120 min, 10°C, at 20:00
    (180, 25, 11, 46.0),   # 180 min, 25°C, at 11:00
    (240,  0,  7, 65.0),   # 240 min,  0°C, at 07:00 (very cold)
    (300, 15, 22, 76.0),   # 300 min, 15°C, at 22:00
]

_model = LinearRegression()
_model_version = "v0.0.0"


def _seed_db_if_empty():
    """Populate the database with training data.

    Priority:
      1. CSV from VOLTEDGE_ML_SEED_CSV env var
      2. CSV at  scripts/ml_seed_data.csv  (relative to project root)
      3. Hardcoded FALLBACK_SEED list above

    Set env var  VOLTEDGE_ML_RESEED=1  to force re-seed from CSV on next startup
    (the old database is cleared first).

    This ensures the model NEVER starts from zero.
    """
    # Force re-seed if env var is set
    if os.getenv("VOLTEDGE_ML_RESEED") == "1":
        clear_training_data()

    if training_data_exists():
        return

    csv_path = os.getenv("VOLTEDGE_ML_SEED_CSV")
    if csv_path and Path(csv_path).exists():
        _seed_from_csv(csv_path)
        return

    # Default path relative to project root (parents up to repo root)
    default_csv = Path(__file__).parent.parent.parent / "scripts" / "ml_seed_data.csv"
    if default_csv.exists():
        _seed_from_csv(str(default_csv))
        return

    # Fallback to hardcoded data
    for dur, temp, hour, energy in FALLBACK_SEED:
        add_training_data(dur, temp, hour, energy)


def _seed_from_csv(filepath: str):
    """Read a CSV and insert every row as training data."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            add_training_data(
                duration_minutes=int(row["duration_minutes"]),
                temperature=float(row["temperature"]),
                hour_of_day=int(row["hour_of_day"]),
                actual_energy_kwh=float(row["actual_energy_kwh"]),
            )


def _load_data() -> tuple[np.ndarray, np.ndarray]:
    """Load all training data from the database.

    Returns (features_matrix, energy_array).
    """
    stored = get_all_training_data()
    features = np.array([
        [r["duration_minutes"], r["temperature"], r["hour_of_day"]]
        for r in stored
    ])
    energy = np.array([r["actual_energy_kwh"] for r in stored])
    return features, energy


def _train():
    """Train (or retrain) the model on all available data."""
    global _model, _model_version

    # Seed the DB on very first startup so we never start from zero
    _seed_db_if_empty()

    X, y = _load_data()
    _model.fit(X, y)

    # Calculate R2 score
    predicted = _model.predict(X)
    r2 = float(r2_score(y, predicted))

    # Persist model state
    save_model_state(
        coefficients=[float(c) for c in _model.coef_],
        intercept=float(_model.intercept_),
        r2_score=round(r2, 4),
        training_count=len(y),
    )

    # Increment model version
    parts = _model_version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    _model_version = ".".join(parts)


def predict_energy_kwh(
    duration_minutes: int,
    temperature: float,
    hour_of_day: int,
) -> float:
    """Predict energy consumption (kWh) based on duration, temperature and time of day."""
    features = np.array([[duration_minutes, temperature, hour_of_day]])
    return float(_model.predict(features)[0])


def add_actual_and_retrain(
    duration_minutes: int,
    temperature: float,
    hour_of_day: int,
    actual_energy_kwh: float,
) -> dict:
    """Record actual energy consumption and retrain the model.

    Returns info about the retrained model.
    """
    add_training_data(duration_minutes, temperature, hour_of_day, actual_energy_kwh)
    _train()

    return {
        "model_version": _model_version,
        "training_count": len(_load_data()[1]),
        "coefficients": [float(c) for c in _model.coef_],
        "intercept": float(_model.intercept_),
    }


def get_model_info() -> dict:
    """Return current model version and parameters."""
    return {
        "model_version": _model_version,
        "coefficients": [float(c) for c in _model.coef_],
        "intercept": float(_model.intercept_),
        "training_count": len(_load_data()[1]),
    }


# ── Train on startup ───────────────────────────────────────────
_train()
