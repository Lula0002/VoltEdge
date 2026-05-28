# VoltEdge Mobility — MVP Solution

[![Python](https://img.shields.io/badge/python-3.9+-blue?logo=python)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-00a393?logo=fastapi)](https://fastapi.tiangolo.com)
[![Azure](https://img.shields.io/badge/Azure-App%20Service-0078D4?logo=microsoftazure)](https://azure.microsoft.com)
[![Build](https://img.shields.io/github/actions/workflow/status/Lula0002/VoltEdge/main_voltedge-app.yml?logo=githubactions&label=build%20%26%20test)](https://github.com/Lula0002/VoltEdge/actions)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A **Domain-Driven Design** proof-of-concept for EV charging session management — from plug-in to invoice — deployed on Azure with CI/CD.

---

## Table of Contents

- [Architecture](#architecture)
- [Happy Path](#happy-path)
- [Pricing Model](#pricing-model)
- [Quick Start](#quick-start)
- [Testing](#testing)
- [API Endpoints](#api-endpoints)
- [Full Flow Example](#full-flow-example)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [CI/CD Pipeline](#cicd-pipeline)
- [Live Deployment](#live-deployment)
- [Database](#database)
- [Environment Variables](#environment-variables)
- [Secrets Management](#secrets-management)
- [License](#license)

---

## Architecture

All modules run in a **single Azure Web App** on one port, each with its own URL prefix:

| Module | Bounded Context | URL prefix | Responsibility |
|--------|----------------|------------|----------------|
| **Session** | Aggregate 1 (Core) | `/sessions/*` | State machine: Created → Charging → Completed → Rated → Invoiced |
| **InvoiceLine** | Aggregate 2 (Generic) | `/billing/*` | Tariff calculation + invoice generation |
| **Analytics/ML** | External Bounded context | `/analytics/*` | ML prediction — HTTP only (no direct imports) |

### DDD Structure

- **Charging Session** is **one** Bounded Context owning **two Aggregates**:
  - **Aggregate 1:** `Session` — entity with **SessionID** as root, manages the charging state machine
  - **Aggregate 2:** `InvoiceLine` — entity with **InvoiceLineID** as root, handles pricing and invoicing
- Session and InvoiceLine communicate via direct Python imports (same Bounded Context).
- Analytics/ML is an **external capability** — accessible **only** via HTTP (`/analytics/*`). No direct Python imports between core code and the ML model.

---

## Happy Path

The Session aggregate follows a 5-step state machine:

| Step | Endpoint | What happens |
|------|----------|-------------|
| 1. **Created** | `POST /sessions/start` | Session created with `charger_id` and `contract_id` |
| 2. **Charging** | `POST /sessions/{id}/start-charging` | Charging begins |
| 3. **Completed** | `POST /sessions/{id}/validate` | Meter data submitted (energy, duration, charging time) |
| 4. **Rated** | `POST /sessions/{id}/rate` | Invoice line ID (UUID) assigned — **no price calculation** |
| 5. **Invoiced** | `POST /sessions/{id}/invoice` | Price calculated via Tariff + OverstayPolicy, invoice persisted |

### Flow diagram

```
Created → Charging → Completed → Rated → Invoiced
```

---

## Pricing Model

| Component | Rate | Paid when |
|-----------|------|-----------|
| **Energy** (Tariff) | 2,45 DKK/kWh | **Always** — core product |
| **Parking overstay** (OverstayPolicy) | 15 DKK / 30 min (0,50 DKK/min) | **Only if** car remains after charging + 10 min grace period |

### Example: 25.5 kWh, 60 min total, 45 min charging

```
Energy:       25.5 kWh × 2,45 DKK/kWh  =  62,48 DKK
Parking:      max(0, 60 − 45 − 10) × 0,50  =   2,50 DKK
                                     Total  =  64,98 DKK
```

### Policy details

- **Tariff**: A data class representing the energy rate (frozen, immutable). Always charged when energy is delivered.
- **OverstayPolicy**: A separate penalty policy (not a tariff). Free to park while charging + 10 min grace period after charging ends. 15 DKK per 30 minutes after grace.

---

## Quick Start

### Prerequisites

- **Python 3.9+** installed
- **Git** installed

### Setup

```bash
git clone https://github.com/Lula0002/VoltEdge.git
cd VoltEdge
python -m venv venv && source venv/bin/activate
pip install -r src/requirements.txt
uvicorn src.main:app --reload --port 8000
```

Open [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs) for Swagger UI.

> The SQLite database (`voltedge.db`) is created automatically in `src/` on app startup via `init_db()` — no manual setup needed. Delete the file to reset all data.

---

## Testing

Run all unit and integration tests with a single command:

```bash
# From the repo root (after `pip install -r src/requirements.txt`)
pip install pytest httpx
python -m pytest tests -v --tb=short
```

| Test file | What it covers |
|-----------|----------------|
| `tests/test_billing_service.py` | Pure domain logic — Tariff, OverstayPolicy, RatingService (no HTTP, no DB) |
| `tests/test_session_service.py` | Full API flow — session state machine via FastAPI TestClient |
| `tests/test_analytics_service.py` | ML prediction endpoints — energy & revenue via HTTP |

The CI/CD pipeline automatically runs these tests on every push to `main`.

---

## API Endpoints

Full documentation with request/response schemas at [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs).

### Session endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sessions/start` | Create session → `Created` |
| POST | `/sessions/{id}/start-charging` | Start charging → `Charging` |
| POST | `/sessions/{id}/validate` | Submit meter data → `Completed` |
| POST | `/sessions/{id}/rate` | Assign invoice_line_id (UUID) → `Rated` |
| POST | `/sessions/{id}/invoice` | Calculate price + persist invoice → `Invoiced` |
| GET | `/sessions/` | List all sessions |
| GET | `/sessions/{id}` | Get session details |

### Billing endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/billing/invoices` | List all invoices |

### Analytics endpoints (external capability)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/analytics/predict-price-rate` | Predict DKK/kWh price rate (varies with weather) |
| POST | `/analytics/predict-revenue` | Predict revenue via ML |

### Demo endpoint

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auto-flow-with-ml` | Full happy path + Analytics/ML call |

---

## Full Flow Example

### Using curl

```bash
# Step 1: Start a session
SID=$(curl -s -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"charger_id":"charger-1","contract_id":"contract-1"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['session_id'])")

# Step 2: Start charging
curl -s -X POST "https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/$SID/start-charging"

# Step 3: Validate (submit meter data)
curl -s -X POST "https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/$SID/validate" \
  -H "Content-Type: application/json" \
  -d '{"energy_delivered":25.5,"duration_minutes":60,"charging_duration_minutes":45}'

# Step 4: Rate (assign invoice line ID — no price calculation)
curl -s -X POST "https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/$SID/rate"

# Step 5: Invoice (calculate price + persist)
curl -s -X POST "https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/$SID/invoice" | python3 -m json.tool
```

### One-call demo

```bash
curl -s -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/auto-flow-with-ml \
  -H "Content-Type: application/json" \
  -d '{"charger_id":"charger-1","contract_id":"contract-1","energy_delivered":25.5,"duration_minutes":60,"charging_duration_minutes":45}' | python3 -m json.tool
```

### Example invoice response

```json
{
  "invoice_line_id": "abc-123-def",
  "session_id": "uuid-here",
  "amount": 64.98,
  "currency": "DKK",
  "breakdown": {
    "charges": {
      "energy": {
        "amount": 62.48,
        "rate": 2.45,
        "unit": "DKK/kWh",
        "kwh": 25.5
      },
      "parking_overstay": {
        "amount": 2.5,
        "rate": 0.5,
        "unit": "DKK/min",
        "grace_minutes": 10,
        "billable_minutes": 5,
        "label": "15 DKK / 30 min"
      }
    },
    "session": {
      "total_duration_minutes": 60,
      "charging_duration_minutes": 45,
      "parking_duration_minutes": 15
    }
  },
  "timestamp": "2026-05-28T10:00:00Z"
}
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **API framework** | Python (FastAPI) with Swagger/OpenAPI docs |
| **Database** | SQLite (local + production) — zero-config, auto-created |
| **Cloud** | Microsoft Azure (App Service) |
| **ML** | Scikit-learn Linear Regression (external capability via HTTP) |
| **CI/CD** | GitHub Actions — automatic build, test, and deploy on push to `main` |
| **Integration** | Session/Billing calls Analytics via HTTP (httpx) — proving service isolation |
| **BI-readiness** | GET endpoints (`/sessions/`, `/billing/invoices`) callable from Power BI, Excel |
| **CORS** | Enabled across all endpoints |
| **Testing** | Pytest with FastAPI TestClient — unit and integration tests |

---

## Project Structure

```
├── src/
│   ├── main.py                       # FastAPI entry point (Session, Billing, Analytics)
│   ├── requirements.txt              # Python dependencies
│   ├── session_service/
│   │   ├── session_api.py            # Aggregate 1: Session endpoints + state machine
│   │   └── __init__.py
│   ├── billing_service/
│   │   ├── billing_api.py            # Invoice list endpoint
│   │   ├── tariff.py                 # Tariff (energy rate) + OverstayPolicy (parking penalty)
│   │   ├── rating_service.py         # Domain service: combines Tariff + OverstayPolicy
│   │   └── __init__.py
│   ├── analytics_service/
│   │   ├── analytics_api.py          # ML prediction endpoints
│   │   ├── ml_model.py               # Linear regression model (isolated, no core imports)
│   │   └── __init__.py
│   └── shared/
│       ├── events.py                 # Shared event models (SessionData, events)
│       ├── database.py               # SQLite database helper + schema init
│       └── __init__.py
├── tests/
│   ├── test_session_service.py       # Session state machine integration tests
│   ├── test_billing_service.py       # Tariff/RatingService domain logic tests
│   └── test_analytics_service.py     # ML prediction API tests
├── .github/workflows/
│   └── main_voltedge-app.yml         # CI/CD pipeline (build → test → deploy)
├── .gitignore
└── README.md
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/main_voltedge-app.yml`) runs on every push to `main` and can be triggered manually via `workflow_dispatch`.

### Pipeline steps

1. **Checkout** — source code checkout
2. **Python 3.12 setup** — environment setup
3. **Install dependencies** — `pip install -r requirements.txt`
4. **Run tests** — `pytest tests/ -v --tb=short` (unit + integration tests)
5. **Upload artifact** — prepare deployment package
6. **Deploy to Azure** — deploy to Azure Web App using publish profile credentials

### Test coverage

- **Unit tests**: Pure domain logic (Tariff, OverstayPolicy, RatingService) — no HTTP, no database
- **Integration tests**: Full API flow via FastAPI TestClient (session state machine, analytics endpoints)

### Rollback

If deployment fails, the previous version remains untouched on Azure. Database is created automatically at app startup — no migration step required.

---

## Live Deployment

**Production URL:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

**Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Database

The project uses **SQLite** — both locally and in production. No setup required.

- Auto-created at `src/voltedge.db` on first app startup
- To reset: delete `voltedge.db` and restart the server
- MySQL is supported via `DATABASE_URL=mysql://...` but not currently in use

### Tables

- **sessions** — stores charging session data (state machine tracking, energy, duration, cost)
- **invoices** — stores generated invoice lines (amount, currency, status)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(none — uses SQLite)* | MySQL connection string: `mysql://user:password@host:3306/voltedge` |
| `VOLTEDGE_DB_PATH` | `src/voltedge.db` | Custom path for the SQLite database file |

Set these in a `.env` file or export them in your shell. Examples are in `src/*/.env.example`.

---

## Secrets Management

- `src/*/.env.example` — templates for local environment variables
- GitHub Secrets: Azure publish profile credentials configured via Deployment Center
- No secrets in source code
- Database uses SQLite — no credentials needed
- `*.db` is in `.gitignore` — production database never committed

---

## License

Developed as part of the 6th semester exam project at Copenhagen Business Academy.

[Contribution guidelines](docs/CONTRIBUTING.md) *(placeholder — not yet created)*
