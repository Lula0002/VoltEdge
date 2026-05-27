"""ML Model — Linear Regression for energy & revenue prediction

Isolated from the API layer so the ML code can be replaced or reused independently.
Trained on simulated data. With real historical data the model can be improved.
"""

from sklearn.linear_model import LinearRegression
import numpy as np


# ── Simulated training data ──────────────────────────────────
# Features: [duration_minutes, temperature, hour_of_day]
# Example: 60 min at 20°C at 14:00 → ~15 kWh
#            Cold weather = slightly higher consumption (battery efficiency)
#            Rush hour = slightly higher consumption

TRAIN_FEATURES = np.array([
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

TRAIN_ENERGY = np.array([
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
_model.fit(TRAIN_FEATURES, TRAIN_ENERGY)


def predict_energy_kwh(duration_minutes: int, temperature: float, hour_of_day: int) -> float:
    """Predict energy consumption (kWh) based on duration, temperature and time of day."""
    features = np.array([[duration_minutes, temperature, hour_of_day]])
    return float(_model.predict(features)[0])
