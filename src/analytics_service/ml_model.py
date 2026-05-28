"""ML Models — Linear Regression for energy & dynamic price rate prediction

Two models:
  1. Energy model: predicts kWh based on duration ONLY
     (same duration = same energy, regardless of temperature/time of day)
  2. Price rate model: predicts DKK/kWh based on temperature + hour of day
     (price varies with demand — peak hours and cold weather = higher rate)

Isolated from the API layer so the ML code can be replaced or reused independently.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from analytics_service.ml_data_store import (
    save_model_state,
    get_all_training_data,
    add_training_data,
    training_data_exists,
    clear_training_data,
    get_stored_schema_version,
)


# Schema version — incremented when training data or model structure changes.
# Forces a re-seed when old data exists in the database.
ML_SCHEMA_VERSION = 2  # v2: energy depends ONLY on duration; price varies with weather


# ═══════════════════════════════════════════════════════════════
# Model 1: Energy prediction — duration determines kWh
# ═══════════════════════════════════════════════════════════════

# Training data: same duration = same kWh, regardless of temperature/hour
# Features stored as (duration_minutes, temperature, hour_of_day, actual_energy_kwh)
# Note: temperature and hour_of_day are INCLUDED as features but the training
# data is structured so they have NO correlation with energy — proving the
# ML model learns they don't matter.

FALLBACK_SEED = [
    (10,  20, 10,  2.0),   # 10 min → 2.0 kWh
    (10,   5,  8,  2.0),   # 10 min → 2.0 kWh (samme — vejr/tid påvirker ikke)
    (20,  18, 14,  4.0),   # 20 min → 4.0 kWh
    (20,  30, 22,  4.0),   # 20 min → 4.0 kWh (samme)
    (30,  15,  8,  6.0),   # 30 min → 6.0 kWh
    (45,  22, 12,  9.0),   # 45 min → 9.0 kWh
    (60,  20, 14, 12.0),   # 60 min → 12.0 kWh
    (60,   5, 18, 12.0),   # 60 min → 12.0 kWh (kulde påvirker IKKE energimængde)
    (60,  30,  9, 12.0),   # 60 min → 12.0 kWh (varme påvirker IKKE energimængde)
    (90,  20, 16, 18.0),   # 90 min → 18.0 kWh
    (120, 10, 20, 24.0),   # 120 min → 24.0 kWh
    (180, 25, 11, 36.0),   # 180 min → 36.0 kWh
    (240,  0,  7, 48.0),   # 240 min → 48.0 kWh
    (300, 15, 22, 60.0),   # 300 min → 60.0 kWh
]

_energy_model = LinearRegression()
_model_version = "v0.0.0"


# ═══════════════════════════════════════════════════════════════
# Model 2: Price rate prediction — price varies with weather
# ═══════════════════════════════════════════════════════════════

# Features: [hour_of_day, temperature]
# Target: price_rate (DKK/kWh)
# Business logic:
#   - SOLSKIN/varmt → mere solenergi på nettet → lavere pris pr. kWh
#   - GRÅT/koldt/regn → mindre vedvarende energi → højere pris pr. kWh
#   - Myldretid (morgen/aften) → højere pris (højere efterspørgsel)
#   - Nat → lavere pris (lavere efterspørgsel)

PRICE_RATE_SEED = [
    # (hour_of_day, temperature, price_rate)
    ( 6, 20, 2.20),   # 06:00 — nat, lav takst
    ( 8, 20, 2.80),   # 08:00 — myldretid, høj takst
    (10, 20, 2.80),   # 10:00 — myldretid, høj takst
    (12, 20, 2.45),   # 12:00 — middag, normal takst
    (14, 20, 2.45),   # 14:00 — eftermiddag, normal takst
    (17, 20, 2.80),   # 17:00 — myldretid, høj takst
    (19, 20, 2.80),   # 19:00 — myldretid, høj takst
    (22, 20, 2.20),   # 22:00 — nat, lav takst
    (14,  5, 2.60),   # 14:00, 5°C — gråt/regnvejr → dyrere (mindre sol)
    (14, 30, 2.30),   # 14:00, 30°C — solskin → billigere (mere solenergi)
    ( 8,  5, 3.00),   # 08:00, 5°C — myldretid + gråt = dyrest
    (22, 30, 2.00),   # 22:00, 30°C — nat + solvarme = billigst
]

_price_model = LinearRegression()


def _train_price_model():
    """Train the price rate model on hardcoded seed data."""
    X_price = np.array([[h, t] for h, t, _ in PRICE_RATE_SEED])
    y_price = np.array([r for _, _, r in PRICE_RATE_SEED])
    _price_model.fit(X_price, y_price)


def predict_price_rate(temperature: float, hour_of_day: int) -> float:
    """Predict the price rate (DKK/kWh) based on weather and time of day.

    Price varies dynamically:
      - SOLSKIN/varmt → mere solenergi → lavere pris pr. kWh
      - GRÅT/koldt/regn → mindre vedvarende energi → højere pris pr. kWh
      - Myldretid (morgen/aften) → højere pris (efterspørgsel)
      - Nat → lavere pris
    """
    features = np.array([[hour_of_day, temperature]])
    return round(float(_price_model.predict(features)[0]), 2)


# ═══════════════════════════════════════════════════════════════
# Model 1: Energy — database seeding and training
# ═══════════════════════════════════════════════════════════════


def _seed_db_if_empty():
    """Populate the database with training data.

    Priority:
      1. CSV from VOLTEDGE_ML_SEED_CSV env var
      2. CSV at  scripts/ml_seed_data.csv  (relative to project root)
      3. Hardcoded FALLBACK_SEED list above

    Set env var  VOLTEDGE_ML_RESEED=1  to force re-seed from CSV on next startup
    (the old database is cleared first).

    If the stored schema version doesn't match the current code version,
    the data is re-seeded — this handles model updates where training
    data structure changes.
    """
    stored_version = get_stored_schema_version()
    if stored_version != 0 and stored_version != ML_SCHEMA_VERSION:
        clear_training_data()

    if os.getenv("VOLTEDGE_ML_RESEED") == "1":
        clear_training_data()

    if training_data_exists():
        return

    csv_path = os.getenv("VOLTEDGE_ML_SEED_CSV")
    if csv_path and Path(csv_path).exists():
        _seed_from_csv(csv_path)
        return

    default_csv = Path(__file__).parent.parent.parent / "scripts" / "ml_seed_data.csv"
    if default_csv.exists():
        _seed_from_csv(str(default_csv))
        return

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
    Only duration_minutes is used for energy prediction.
    """
    stored = get_all_training_data()
    features = np.array([
        [r["duration_minutes"]]  # Only duration — temperature/hour don't affect energy
        for r in stored
    ])
    energy = np.array([r["actual_energy_kwh"] for r in stored])
    return features, energy


def _train():
    """Train (or retrain) the energy model on all available data."""
    global _model_version

    # Seed the DB on very first startup so we never start from zero
    _seed_db_if_empty()

    X, y = _load_data()
    _energy_model.fit(X, y)

    # Calculate R2 score
    predicted = _energy_model.predict(X)
    r2 = float(r2_score(y, predicted))

    # Persist model state
    save_model_state(
        coefficients=[float(c) for c in _energy_model.coef_],
        intercept=float(_energy_model.intercept_),
        r2_score=round(r2, 4),
        training_count=len(y),
        schema_version=ML_SCHEMA_VERSION,
    )

    parts = _model_version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    _model_version = ".".join(parts)


def predict_energy_kwh(
    duration_minutes: int,
    temperature: float = 0,
    hour_of_day: int = 0,
) -> float:
    """Predict energy consumption (kWh) based on duration ONLY.

    temperature and hour_of_day are accepted for API consistency but
    are NOT used — same duration always gives the same energy prediction.
    """
    features = np.array([[duration_minutes]])  # Only duration matters
    return round(float(_energy_model.predict(features)[0]), 2)


def add_actual_and_retrain(
    duration_minutes: int,
    temperature: float = 0,
    hour_of_day: int = 0,
    actual_energy_kwh: float = 0,
) -> dict:
    """Record actual energy consumption and retrain the model."""
    add_training_data(duration_minutes, temperature, hour_of_day, actual_energy_kwh)
    _train()

    return {
        "model_version": _model_version,
        "training_count": len(_load_data()[1]),
        "coefficients": [float(c) for c in _energy_model.coef_],
        "intercept": float(_energy_model.intercept_),
    }


def get_model_info() -> dict:
    """Return current energy model version and parameters."""
    return {
        "model_version": _model_version,
        "coefficients": [float(c) for c in _energy_model.coef_],
        "intercept": float(_energy_model.intercept_),
        "training_count": len(_load_data()[1]),
    }


# ── Train both models on startup ─────────────────────────────
_train()
_train_price_model()
