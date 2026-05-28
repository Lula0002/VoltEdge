"""ML Model — Linear Regression for energy & revenue prediction

Isolated from the API layer so the ML code can be replaced or reused independently.
Trained on bootstrapped data. Auto-retrains when new data is added via the API.

The model state (coefficients, R2) is persisted in the ML database so PowerBI
can visualise the regression line.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from analytics_service.ml_data_store import (
    save_model_state,
    get_all_training_data,
    add_training_data,
)


# ── Bootstrapped training data ─────────────────────────────────
# Features: [duration_minutes, temperature, hour_of_day]
# These seed the model so it can make predictions immediately.

BOOTSTRAP_FEATURES = np.array([
    [10,  20, 10],   # 10 min, 20°C, at 10:00
    [20,  18, 14],   # 20 min, 18°C, at 14:00
    [30,  15,  8],   # 30 min, 15°C, at 08:00
    [45,  22, 12],   # 45 min, 22°C, at 12:00
    [60,  20, 14],   # 60 min, 20°C, at 14:00
    [60,   5, 18],   # 60 min,  5°C, at 18:00 (cold = more energy)
    [60,  30,  9],   # 60 min, 30°C, at 09:00 (hot = less energy)
    [90,  20, 16],   # 90 min, 20°C, at 16:00
    [120, 10, 20],   # 120 min, 10°C, at 20:00
    [180, 25, 11],   # 180 min, 25°C, at 11:00
    [240,  0,  7],   # 240 min,  0°C, at 07:00 (very cold)
    [300, 15, 22],   # 300 min, 15°C, at 22:00
])

BOOTSTRAP_ENERGY = np.array([
    2.0,   # 10 min
    4.5,   # 20 min
    7.5,   # 30 min
    11.5,  # 45 min
    15.0,  # 60 min, 20°C
    17.5,  # 60 min, cold (more consumption)
    13.0,  # 60 min, hot (less consumption)
    22.5,  # 90 min
    31.0,  # 120 min
    46.0,  # 180 min
    65.0,  # 240 min, cold
    76.0,  # 300 min
])

_model = LinearRegression()
_model_version = "v0.0.0"


def _load_data() -> tuple[np.ndarray, np.ndarray]:
    """Load all training data (bootstrap + user-added) from the database.

    Returns (features_matrix, energy_array).
    """
    stored = get_all_training_data()

    if not stored:
        return BOOTSTRAP_FEATURES.copy(), BOOTSTRAP_ENERGY.copy()

    user_features = np.array([
        [r["duration_minutes"], r["temperature"], r["hour_of_day"]]
        for r in stored
    ])
    user_energy = np.array([r["actual_energy_kwh"] for r in stored])

    features = np.vstack([BOOTSTRAP_FEATURES, user_features])
    energy = np.concatenate([BOOTSTRAP_ENERGY, user_energy])
    return features, energy


def _train():
    """Train (or retrain) the model on all available data."""
    global _model, _model_version
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
