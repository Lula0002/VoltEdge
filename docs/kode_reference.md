# Kode-Reference — VoltEdge MVP

> **Til dig.** Her forklares hvad hver fil gør, så du nemt kan overskue projektet.

---

## Rod-filer

| Fil | Formål |
|---|---|
| `README.md` | Offentlig projektbeskrivelse — setup, test, CI/CD. Den du viser frem. |
| `MVP.md` | **MVP-definition.** Rører vi ikke uden din tilladelse. |
| `liste.md` | **Vores step-by-step plan.** Krydser af løbende. |
| `.gitignore` | Sikrer at `venv/`, `__pycache__/`, `.env` osv. **ikke** kommer med i git. |

---

## `src/` — Python applikation

### `src/main.py`
**Indgangspunkt.** Samler alle 3 services i én FastAPI app.  
Kør med: `uvicorn main:app --reload --port 8000`  
Swagger på: `http://localhost:8000/docs`

### `src/shared/events.py`
**Fælles event-modeller** — bruges på tværs af alle services.  
Indeholder: `SessionStarted`, `SessionValidated`, `PriceCalculated`, `InvoiceGenerated`  
(Det er vores "Happy Path" events)

---

### `src/session_service/session_api.py` — Session Service (Core)

**Hvad den gør:** Håndterer en ladesession som en **state machine**.

**Endpoints:**

| Endpoint | Hvad sker der? |
|---|---|
| `GET /sessions/health` | Sundhedstjek |
| `POST /sessions/start` | Opretter ny session → status: `Created` |
| `POST /sessions/{id}/authorize` | Godkender → status: `Authorized` |
| `POST /sessions/{id}/start-charging` | Starter ladning → status: `Charging` |
| `POST /sessions/{id}/complete` | Afslutter → status: `Completed` → emit `SessionValidated` |
| `GET /sessions/{id}` | Hent session data |

**State machine:** `Created → Authorized → Charging → Completed`  
(Du kan ikke authorize en der allerede er completed — fejl hvis forkert rækkefølge)

---

### `src/billing_service/billing_api.py` — Billing Service (Generic)

**Hvad den gør:** Prisberegning (rating) og fakturaoprettelse.

**Endpoints:**

| Endpoint | Hvad sker der? |
|---|---|
| `GET /billing/health` | Sundhedstjek |
| `POST /billing/rate` | Beregner pris: 2,45 DKK/kWh + 0,50 DKK/min efter 10 min gratis |
| `POST /billing/invoice` | Opretter faktura-linje → emit `InvoiceGenerated` |

**Prislogik (hardcoded i koden):**
- Energi: 2,45 DKK/kWh
- Parkering: 0,50 DKK/min efter 10 gratis minutter
- Disse kan overstyres med miljøvariabler (`.env.example`)

---

### `src/analytics_service/analytics_api.py` — Analytics Service (Supporting)

**Hvad den gør:** ML-anomali-detektion med linear regression.

**Endpoints:**

| Endpoint | Hvad sker der? |
|---|---|
| `GET /analytics/health` | Sundhedstjek |
| `POST /analytics/predict` | Forudsiger forventet kWh baseret på varighed (minutter) |
| `POST /analytics/detect` | Sammenligner faktisk vs forventet → flagger afvigelser > 40% |

**ML-model:** Trænet på simuleret data (10-300 min, 2-75 kWh).  
Hvis en session afviger >40% fra forventet, markeres den som **anomaly**.

---

### `src/requirements.txt`
**Afhængigheder.** Indeholder:
- `fastapi` + `uvicorn` (web server)
- `pydantic` (data validering)
- `scikit-learn` + `numpy` (ML)
- `pytest` + `httpx` (test)

---

## Miljøvariabler (`.env.example`)

| Fil | Variabler |
|---|---|
| `session_service/.env.example` | `DATABASE_URL` — PostgreSQL forbindelse (valgfri) |
| `billing_service/.env.example` | `ENERGY_RATE`, `PARKING_RATE`, `PARKING_FREE_MINUTES` |
| `analytics_service/.env.example` | `ANOMALY_THRESHOLD` — procentgrænse for anomali |

---

## Hvad mangler (kommer senere)

| Mappe/fil | Formål |
|---|---|
| `tests/` | Unit tests for alle 3 services (pytest) |
| `postman/` | Postman collection til at teste API'et |
| `.github/workflows/` | GitHub Actions CI/CD pipeline → Azure deploy |
