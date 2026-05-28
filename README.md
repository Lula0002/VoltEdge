# VoltEdge Mobility MVP

A **Domain-Driven Design** proof-of-concept for EV charging session management — from plug-in to invoice — deployed on Azure.

---

## What this project does

VoltEdge manages a charging session through a state machine with **two Aggregates** in one Bounded Context:

| Aggregate | Root | Responsibility |
|-----------|------|---------------|
| **Session** | SessionID | State machine: `Created → Charging → Completed → Rated → Invoiced` |
| **InvoiceLine** | InvoiceLineID | Tariff calculation + invoice persistence |

A separate **Analytics/ML** service (external capability) predicts energy and revenue — accessible **only** via HTTP to prove service isolation.

### Pricing model

| Component | Rate | Paid when |
|-----------|------|-----------|
| Energy (Tariff) | 2,45 DKK/kWh | Always — core product |
| Parking overstay (OverstayPolicy) | 15 DKK / 30 min | Only if car stays after charging + 10 min grace |

---

## Quick start

```bash
git clone https://github.com/Lula0002/VoltEdge.git
cd VoltEdge
python -m venv venv && source venv/bin/activate
pip install -r src/requirements.txt
uvicorn src.main:app --reload --port 8000
```

Swagger UI opens at [http://localhost:8000/docs](http://localhost:8000/docs).  
The database (`voltedge.db`) is created automatically on first request.

### Full flow (5 requests)

```bash
SID=$(curl -s -X POST http://localhost:8000/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"charger_id":"charger-1","contract_id":"contract-1"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['session_id'])")

curl -s -X POST "http://localhost:8000/sessions/$SID/start-charging"

curl -s -X POST "http://localhost:8000/sessions/$SID/validate" \
  -H "Content-Type: application/json" \
  -d '{"energy_delivered":25.5,"duration_minutes":60,"charging_duration_minutes":45}'

curl -s -X POST "http://localhost:8000/sessions/$SID/rate"

curl -s -X POST "http://localhost:8000/sessions/$SID/invoice" | python3 -m json.tool
```

Or use the one-call demo:

```bash
curl -s -X POST http://localhost:8000/auto-flow-with-ml \
  -H "Content-Type: application/json" \
  -d '{"charger_id":"charger-1","contract_id":"contract-1","energy_delivered":25.5,"duration_minutes":60,"charging_duration_minutes":45}'
```

---

## Tech stack

- **API:** Python (FastAPI) — Swagger/OpenAPI docs at `/docs`
- **Database:** SQLite (auto-created on startup)
- **Cloud:** Azure App Service
- **ML:** Scikit-learn Linear Regression (external capability via HTTP)
- **CI/CD:** GitHub Actions — build + deploy on push to `main`

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| **Proof of API** | | |
| POST | `/auto-flow-with-ml` | Full happy path + Analytics/ML via HTTP |
| **Session** | | |
| POST | `/sessions/start` | Create session → `Created` |
| POST | `/sessions/{id}/start-charging` | Start charging → `Charging` |
| POST | `/sessions/{id}/validate` | Submit meter data → `Completed` |
| POST | `/sessions/{id}/rate` | Assign invoice_line_id (UUID) → `Rated` |
| POST | `/sessions/{id}/invoice` | Calculate price + persist invoice → `Invoiced` |
| GET | `/sessions/` | List all sessions |
| GET | `/sessions/{id}` | Get session details |
| **Billing** | | |
| GET | `/billing/invoices` | List all invoices |
| **Analytics (external)** | | |
| POST | `/analytics/predict-energy` | Predict kWh consumption |
| POST | `/analytics/predict-revenue` | Predict revenue |

Full documentation with request/response schemas at [http://localhost:8000/docs](http://localhost:8000/docs) (local) or the [live Swagger page](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs).

---

## Project structure

```
src/
├── main.py                       # FastAPI entry point
├── session_service/              # Aggregate 1: Session
│   ├── session_api.py            # Endpoints + state machine logic
├── billing_service/              # Aggregate 2: InvoiceLine
│   ├── billing_api.py            # Invoice list endpoint
│   ├── tariff.py                 # Tariff + OverstayPolicy
│   ├── rating_service.py         # Domain service
├── analytics_service/            # External capability (HTTP only)
│   ├── analytics_api.py          # ML prediction endpoints
│   ├── ml_model.py               # Linear regression (isolated)
└── shared/
    ├── events.py                 # Shared event models
    ├── database.py               # SQLite helper
```

---

## Live deployment

[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)  
Swagger: [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Who maintains this

Developed as part of the 6th semester exam project at Copenhagen Business Academy.

[Contribution guidelines](docs/CONTRIBUTING.md) *(placeholder — not yet created)*
