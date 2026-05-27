"""ML Model — Linear Regression for energy & revenue prediction

Isolated from the API layer so the ML code can be replaced or reused independently.
Trained on simulated data. With real historical data the model can be improved.
"""

from sklearn.linear_model import LinearRegression
import numpy as np


# ── Simulated training data ──────────────────────────────────
# Features: [duration_minutes, temperature, hour_of_day]
# Eksempler: 60 min ved 20°C kl. 14 → ~15 kWh
#            Cold weather = slightly higher consumption (battery efficiency)
#            Rush hour = slightly higher consumption

TRAIN_FEATURES = np.array([
    [10,  20, 10],   # 10 min, 20°C, kl. 10
    [20,  18, 14],   # 20 min, 18°C, kl. 14
    [30,  15,  8],   # 30 min, 15°C, kl. 08
    [45,  22, 12],   # 45 min, 22°C, kl. 12
    [60,  20, 14],   # 60 min, 20°C, kl. 14
    [60,   5, 18],   # 60 min,  5°C, 18:00 (cold = more energy)
    [60,  30,  9],   # 60 min, 30°C, 09:00 (hot = less energy)
    [90,  20, 16],   # 90 min, 20°C, kl. 16
    [120, 10, 20],   # 120 min, 10°C, kl. 20
    [180, 25, 11],   # 180 min, 25°C, kl. 11
    [240,  0,  7],   # 240 min,  0°C, kl. 07 (meget koldt)
    [300, 15, 22],   # 300 min, 15°C, kl. 22
])

TRAIN_ENERGY = np.array([
    2.0,   # 10 min
    4.5,   # 20 min
    7.5,   # 30 min
    11.5,  # 45 min
    15.0,  # 60 min, 20°C
    17.5,  # 60 min, koldt (mere forbrug)
    13.0,  # 60 min, varmt (mindre forbrug)
    22.5,  # 90 min
    31.0,  # 120 min
    46.0,  # 180 min
    65.0,  # 240 min, koldt
    76.0,  # 300 min
])

_model = LinearRegression()
_model.fit(TRAIN_FEATURES, TRAIN_ENERGY)


def predict_energy_kwh(duration_minutes: int, temperature: float, hour_of_day: int) -> float:
    """Predict energy consumption (kWh) based on duration, temperature and time of day."""
    features = np.array([[duration_minutes, temperature, hour_of_day]])
    return float(_model.predict(features)[0])
