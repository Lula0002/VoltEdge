"""Analytics Service — ML der forudsiger fremtidigt strømforbrug og indtjening

Modellen bruger lineær regression med features som varighed, temperatur og tidspunkt
til at forudsige energiforbrug. Derefter beregnes pris og forventet indtjening.

Til eksamen: Modellen er trænet på simuleret data. Med rigtige historiske data
ville den kunne lave langt mere præcise forudsigelser.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sklearn.linear_model import LinearRegression
import numpy as np

router = APIRouter(prefix="/analytics", tags=["analytics"])

# ── Simuleret træningsdata ──────────────────────────────────
# Features: [duration_minutes, temperature, hour_of_day]
# Eksempler: 60 min ved 20°C kl. 14 → ~15 kWh
#            Koldt vejr = lidt højere forbrug (batteri-effektivitet)
#            Myldretid = lidt højere forbrug

TRAIN_FEATURES = np.array([
    [10,  20, 10],   # 10 min, 20°C, kl. 10
    [20,  18, 14],   # 20 min, 18°C, kl. 14
    [30,  15,  8],   # 30 min, 15°C, kl. 08
    [45,  22, 12],   # 45 min, 22°C, kl. 12
    [60,  20, 14],   # 60 min, 20°C, kl. 14
    [60,   5, 18],   # 60 min,  5°C, kl. 18 (koldt = mere strøm)
    [60,  30,  9],   # 60 min, 30°C, kl. 09 (varmt = mindre strøm)
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

model = LinearRegression()
model.fit(TRAIN_FEATURES, TRAIN_ENERGY)


# ── Request/Response modeller ────────────────────────────────

class PredictEnergyRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Forventet ladetid i minutter", examples=[60])
    temperature: float = Field(default=15, description="Forventet temperatur i °C", examples=[15])
    hour_of_day: int = Field(default=14, description="Klokkeslæt (0-23)", examples=[14])


class RevenueRequest(BaseModel):
    duration_minutes: int = Field(default=60, description="Gennemsnitlig ladetid per session")
    temperature: float = Field(default=15, description="Forventet gennemsnitstemperatur")
    hour_of_day: int = Field(default=14, description="Typisk tidspunkt")
    kwh_price: float = Field(default=2.45, description="Forventet kWh-pris i DKK", examples=[2.45])
    num_sessions: int = Field(default=100, description="Antal forventede ladesessioner")
    num_chargers: int = Field(default=10, description="Antal ladestandere")


# ── Endpoints ────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Sundhedstjek for Analytics Service."""
    return {"status": "healthy", "service": "analytics-service"}


@router.post("/predict-energy")
async def predict_energy(req: PredictEnergyRequest):
    """Forudsige fremtidigt strømforbrug (kWh) baseret på varighed, vejr og tidspunkt.

    ML-model: Lineær regression trænet på simuleret historisk data.
    Features: varighed (min), temperatur (°C), tidspunkt (time).
    """
    features = np.array([[req.duration_minutes, req.temperature, req.hour_of_day]])
    predicted_kwh = float(model.predict(features)[0])

    return {
        "input": {
            "duration_minutes": req.duration_minutes,
            "temperature_celsius": req.temperature,
            "hour_of_day": req.hour_of_day,
        },
        "predicted_energy_kwh": round(predicted_kwh, 2),
        "model": "LinearRegression",
        "note": "Forudsigelse baseret på simuleret træningsdata"
    }


@router.post("/predict-revenue")
async def predict_revenue(req: RevenueRequest):
    """Forudsige fremtidig indtjening for en kunde (f.eks. Københavns Kommune).

    ML-modellen forudsiger først strømforbrug ud fra varighed, vejr og tidspunkt.
    Derefter beregnes:
      - Forventede omkostninger (kWh × kWh-pris)
      - Forventet indtjening på tværs af alle ladestandere og sessioner
    """
    features = np.array([[req.duration_minutes, req.temperature, req.hour_of_day]])
    predicted_kwh_per_session = float(model.predict(features)[0])

    # Prisberegning
    total_kwh = predicted_kwh_per_session * req.num_sessions
    total_cost_dkk = round(total_kwh * req.kwh_price, 2)

    # Indtjening per ladestander
    revenue_per_charger = round(total_cost_dkk / req.num_chargers, 2)

    return {
        "input": {
            "duration_minutes": req.duration_minutes,
            "temperature_celsius": req.temperature,
            "kwh_price_dkk": req.kwh_price,
            "num_sessions": req.num_sessions,
            "num_chargers": req.num_chargers,
        },
        "prediction": {
            "predicted_kwh_per_session": round(predicted_kwh_per_session, 2),
            "total_predicted_kwh": round(total_kwh, 2),
            "total_predicted_cost_dkk": total_cost_dkk,
            "revenue_per_charger_dkk": revenue_per_charger,
            "avg_revenue_per_session_dkk": round(total_cost_dkk / req.num_sessions, 2),
        },
        "model": "LinearRegression",
        "note": "Forudsigelse baseret på simuleret data. Med rigtige historiske data kan modellen forbedres."
    }
