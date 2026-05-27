# VoltEdge Mobility A/S — MVP Solution

Welcome to the VoltEdge Mobility A/S MVP solution.  
This project demonstrates a **fully traceable data flow** from telemetry to invoice through an event-driven microservice architecture.

## Table of Contents

1. [Happy Path](#happy-path-5-steps)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Code Structure](#code-structure)
5. [Getting Started (Local Development)](#getting-started-local-development)
6. [Test the Full Flow](#test-the-full-flow)
7. [Testing with Postman](#testing-with-postman)
8. [Run Unit Tests](#run-unit-tests)
9. [Database](#database-sqlite)
10. [CI/CD Pipeline](#cicd-pipeline)
11. [Command Reference](#command-reference)
12. [Secrets Management](#secrets-management)

---

## Happy Path (5 steps)

```
Created → Charging → Completed → Rated → Invoiced
```

The **Session** aggregate (SessionID as root) follows a state machine through 5 statuses:
1. **Created** — Session created with charger_id and contract_id
2. **Charging** — Charging starts
3. **Completed** — Charging completed with meter data (energy_delivered, duration_minutes)
4. **Rated** — Price calculated via tariff rules (2.45 DKK/kWh + 0.50 DKK/min after 10 free minutes)
5. **Invoiced** — Invoice generated and persisted to the database

---

## Architecture

All modules run in a **single Azure Web App** on one port — each with its own URL prefix:

| Modul | Rolle i Bounded Context | URL prefix | Responsibility |
|---|---|---|---|
| **Session** | Aggregate 1 (Core) | `/sessions/*` | State machine: Created → Charging → Completed |
| **InvoiceLine** | Aggregate 2 (Generic) | `/billing/*` | Tarifberegning + fakturagenerering |
| **Analytics/ML** | 🚫 External capability (kun via API) | `/analytics/*` | ML-prediction — KUN via HTTP |

> **DDD note — Bounded Context:**  
> **Charging Session** er **én** Bounded Context, der ejer **to aggregater**:  
> - **Aggregate 1:** `Session` — entity med **SessionID** som rod, styrer ladningens tilstandsmaskine (Created → Charging → Completed)  
> - **Aggregate 2:** `InvoiceLine` — entity med **InvoiceID** som rod, håndterer prissætning og faktura (Rated → Invoiced)  
>  
> **Der er kun 1 API i løsningen** — mellem Charging Session Bounded Context og Analytics/ML.  
> Session og InvoiceLine kommunikerer via direkte Python-import (samme Bounded Context).  
>  
> Analytics/ML er en **ekstern capability** — den kan **KUN** tilgås via HTTP/API-kald (`/analytics/*`).  
> Der er ingen direkte Python-import mellem kerne-koden og ML-modellen — kun HTTP-kald.

**Azure Web App (live):**  
[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

👉 **Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Tech Stack

- **API:** Python (FastAPI) with Swagger/OpenAPI docs
- **Database:** SQLite (both local and in production)
- **Cloud:** Microsoft Azure (App Service) — code-based deployment
- **CI/CD:** GitHub Actions — automatic build, test, deploy and rollback
- **ML:** Scikit-learn Linear Regression (external capability via API)
- **Integration:** Session/Billing calls Analytics via HTTP (httpx) — proving separation
- **BI-readiness:** GET endpoints (`/sessions/`, `/billing/invoices`) kan kaldes direkte fra Power BI, Excel, eller andre BI-værktøjer — både lokalt og på Azure
- **CORS:** Aktiveret på tværs af alle endpoints
- **Secrets:** `.env.example` + GitHub Secrets
- **Secrets:** `.env.example` + GitHub Secrets

---

## Code Structure

### Root files

| File | Purpose |
|---|---|
| `README.md` | Project documentation |
| `.gitignore` | Ignores `venv/`, `__pycache__/`, `.env`, `*.db`, etc. |
| `requirements.txt` | Root requirements (references `src/requirements.txt`) |

### `src/` — Python application

#### `src/main.py`
**Entry point.** All 3 services run in one FastAPI app.  
Run with: `uvicorn src.main:app --reload --port 8000`  
Swagger at: `http://localhost:8000/docs`

#### `src/shared/events.py`
**Shared event models** used across all services:  
`SessionStarted`, `SessionValidated`, `SessionRated`, `InvoiceLineGenerated`

#### `src/shared/database.py`
**Database helper** — SQLite (both local and in production).  
- `DATABASE_URL` unset → SQLite (`voltedge.db` created automatically on startup)
- Also supports MySQL via `DATABASE_URL=mysql://...` (prepared but not used)

---

#### `src/session_service/session_api.py` — Aggregate 1: Session

**Purpose:** Manages a charging session as a **state machine** (Aggregate 1: Session entity with SessionID as root of the Charging Session Bounded Context).

| Endpoint | Description |
|---|---|
| `GET /sessions/health` | Health check |
| `POST /sessions/start` | Create new session → status: `Created` |
| `POST /sessions/{id}/start-charging` | Start charging → status: `Charging` |
| `POST /sessions/{id}/complete` | Complete → status: `Completed` |
| `POST /sessions/{id}/rate` | Calculate price → status: `Rated` |
| `POST /sessions/{id}/invoice` | Generate invoice → status: `Invoiced` |
| `GET /sessions/{id}` | Get session data |

**State machine:** `Created → Charging → Completed → Rated → Invoiced`


---

#### `src/billing_service/billing_api.py` — Aggregate 2: InvoiceLine

**Purpose:** Price calculation (rating) and invoice generation — persists invoices to SQLite (Aggregate 2: InvoiceLine entity with InvoiceID as root of the Charging Session Bounded Context).

> ⚠️ `POST /billing/rate` og `POST /billing/invoice` er ikke længere eksponeret som API-endpoints — de kaldes internt af Session-aggregatet via `POST /sessions/{id}/rate` og `POST /sessions/{id}/invoice`.

| Endpoint | Description |
|---|---|
| `GET /billing/health` | Health check |
| `GET /billing/invoices` | Return all invoices from the database |

**Pricing logic (defined in `tariff.py`):**
- Energy: 2.45 DKK/kWh
- Parking: 0.50 DKK/min after 10 free minutes

---

#### `src/analytics_service/analytics_api.py` — External Capability: Analytics/ML

**Purpose:** ML prediction of energy consumption and revenue via linear regression.

| Endpoint | Description |
|---|---|
| `GET /analytics/health` | Health check |
| `POST /analytics/predict-energy` | Predict kWh based on duration, temperature and time of day |
| `POST /analytics/predict-revenue` | Predict revenue based on same features + kWh price and number of sessions |

**ML model:** LinearRegression with 3 features (duration_minutes, temperature, hour_of_day).  
Trained on simulated data (12 samples).  
*Isolated in `ml_model.py` — separate from core microservice logic.*

---

### `src/requirements.txt`

**Dependencies:**
- `fastapi` + `uvicorn` (web server)
- `pydantic` (data validation)
- `scikit-learn` + `numpy` (ML)
- `httpx` (HTTP client for cross-service API calls)
- `mysql-connector-python` (MySQL driver — installed but not used)
- `pytest` + `httpx` (testing)

### Environment variables (`.env.example`)

- **`session_service/.env.example`**
  - `DATABASE_URL`: Database connection string (SQLite is used by default).

- **`billing_service/.env.example`**
  - Prices are hardcoded in `tariff.py` — no environment variables required.

- **`analytics_service/.env.example`**
  - ML model trained on simulated data — no environment variables required.

---

## Getting Started (Local Development)

### Prerequisites

- **Python 3.12+** installed ([python.org](https://python.org))
- **Git** installed ([git-scm.com](https://git-scm.com))
- A terminal (PowerShell, bash, etc.)

### Step-by-step setup from scratch

```bash
# 1. Clone the repository
git clone https://github.com/Lula0002/VoltEdge.git
cd VoltEdge

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
.\venv\Scripts\Activate     # Windows
# source venv/bin/activate  # Mac / Linux

# 4. Install dependencies
pip install -r src/requirements.txt

# 5. Start the server (all 3 services in one app)
uvicorn src.main:app --reload --port 8000

# 6. Open Swagger UI:
#    http://localhost:8000/docs
```

SQLite database (`voltedge.db`) is created automatically on app startup via `init_db()`.

---

## Test the Full Flow

### Happy Path via Swagger

1. Open Swagger UI:
   - **Local:** `http://localhost:8000/docs`
   - **Live:** `https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs`
2. Run requests in sequence:

**Step 1 — Start session:**
```json
POST /sessions/start
{"charger_id": "charger-1", "contract_id": "contract-1"}
```

**Step 2 — Start charging:** `POST /sessions/{session_id}/start-charging`

**Step 3 — Complete:**
```json
POST /sessions/{session_id}/complete
{"energy_delivered": 25.5, "duration_minutes": 60}
```

**Step 4 — Rate (transition to Rated):**
```
POST /sessions/{session_id}/rate
```
No body required — reads meter data from the session automatically.

**Step 5 — Invoice (transition to Invoiced):**
```
POST /sessions/{session_id}/invoice
```
No body required — reads total_cost from the session automatically.

### Test with curl

```bash
# Start a session
curl -X POST http://localhost:8000/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"charger_id": "charger-1", "contract_id": "contract-1"}'

# ML predict energy (external capability via HTTP)
curl -X POST http://localhost:8000/analytics/predict-energy \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60, "temperature": 15, "hour_of_day": 14}'

# ML predict revenue (external capability via HTTP)
curl -X POST http://localhost:8000/analytics/predict-revenue \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60, "temperature": 15, "hour_of_day": 14, "kwh_price": 2.45, "num_sessions": 100, "num_chargers": 10}'

# 🎯 Full Happy Path + Analytics via HTTP (demonstrates external capability)
# Dette endpoint viser at Analytics kun kan tilgås via HTTP — ikke direkte import
curl -X POST http://localhost:8000/auto-flow-with-ml \
  -H "Content-Type: application/json" \
  -d '{"charger_id": "charger-1", "contract_id": "contract-1", "energy_delivered": 25.5, "duration_minutes": 60}'
```

**Live deployment URL:**  
`https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net`

---

## Testing with Postman

1. Open Postman
2. **File → Import** → select `postman/VoltEdge MVP.postman_collection.json`
3. Set the `base_url` variable to your Azure URL or `http://localhost:8000`
4. Run requests in sequence (each step depends on the previous)

The collection includes requests across 4 groups:
- Health checks (all services)
- Session Happy Path (start → start-charging → complete → rate → invoice)
- Billing (rate → invoice)
- Analytics (predict-energy → predict-revenue)

---

## Run Unit Tests

```bash
python -m pytest tests/ -v
```

All 13 tests across 3 services:
- `tests/test_session_service.py` (4 tests) — state machine transitions
- `tests/test_billing_service.py` (5 tests) — price calculation accuracy
- `tests/test_analytics_service.py` (4 tests) — ML prediction (energy + revenue)

---

## Database: SQLite

The project uses **SQLite** both locally and in production. No database setup is required — `voltedge.db` is created automatically in `src/` on app startup via `init_db()`.

### Why SQLite?

| Benefit | Description |
|---------|-------------|
| **Zero setup** | No database server, no connection configuration |
| **Portable** | Single file — easy to share and version |
| **Good enough for MVP** | No concurrent writes = SQLite is sufficient |

> **Note:** The code also supports MySQL via `DATABASE_URL=mysql://...`, but it is not currently in use.

---

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/main_voltedge-app.yml`):

### Workflow triggers
- On push to `main` branch
- Manual trigger via `workflow_dispatch`

### Build job
1. **Checkout** source code
2. **Python 3.12** setup
3. **Install dependencies** from `requirements.txt`
4. **Upload artifact** for deployment

### Deploy job
1. **Download artifact** from build job
2. **Deploy to Azure Web App** using publish profile credentials

### Database creation (automatic)
The database is **not** provisioned by the CI/CD pipeline itself — instead, it is created **at application startup** via the `init_db()` function in `src/shared/database.py`. This means `voltedge.db` is created automatically on first request.

This approach makes the database fully automated as part of the deployment — no separate provisioning step needed.

### Rollback
If the deployment fails, the previous version remains untouched on Azure.

---

## Command Reference

### Setup & Installation

```bash
pip install -r src/requirements.txt   # Install all Python packages
python -m venv venv                    # Create virtual environment
.\venv\Scripts\Activate                # Activate venv (Windows)
```

### Run server

```bash
uvicorn src.main:app --reload --port 8000
```

### Run tests

```bash
python -m pytest tests/ -v                # Run all tests
python -m pytest tests/test_session_service.py -v  # Run specific test file
```

### Git commands

```bash
git init                                     # Initialize repository
git add .                                    # Stage all changes
git commit -m "message"                      # Commit locally
git remote add origin <url>                  # Link to GitHub
git branch -M main                           # Rename branch to main
git push -u origin main                      # First push to GitHub
git pull --rebase                            # Fetch remote changes
git push                                     # Push commits
git status                                   # Show working tree status
```

### Azure Startup Command

Set in Azure Portal → Configuration → General Settings:
```
cd src && uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Project Structure

```
├── src/
│   ├── main.py                       # FastAPI entry point (Session, Billing, Analytics)
│   ├── requirements.txt              # Python dependencies
│   ├── session_service/              # Aggregate 1: Session (SessionID as root)
│   │   ├── session_api.py            # FastAPI endpoints + state machine
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── billing_service/              # Aggregate 2: InvoiceLine (InvoiceID as root)
│   │   ├── billing_api.py            # Rating + invoice endpoints
│   │   ├── tariff.py                 # Pricing rules (Value Object)
│   │   ├── rating_service.py         # Domain service
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── analytics_service/            # 🚫 External capability: Analytics/ML (kun via API)
│   │   ├── analytics_api.py          # ML prediction endpoints
│   │   ├── ml_model.py               # Linear regression model (isolated)
│   │   ├── .env.example
│   │   └── __init__.py
│   └── shared/
│       ├── events.py                 # Shared event models
│       ├── database.py               # SQLite database helper
│       └── __init__.py
├── tests/                            # Unit tests
│   ├── test_session_service.py
│   ├── test_billing_service.py
│   └── test_analytics_service.py
├── .github/workflows/                # GitHub Actions CI/CD
├── requirements.txt                  # Root requirements (references src/)
└── README.md
```

---

## Secrets Management

- `src/*/.env.example` — templates for local environment variables
- GitHub Secrets: publish profile credentials configured via Azure Deployment Center
- No secrets in source code — only `.env.example` templates
- Database is created automatically as SQLite — no credentials needed

---

## License

This project is developed as part of the 6th semester exam at Københavns Erhvervsakademi.
