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

The **ChargingSession** aggregate follows a state machine through 5 statuses:
1. **Created** — Session created with charger_id and contract_id
2. **Charging** — Charging starts
3. **Completed** — Charging completed with meter data (energy_delivered, duration_minutes)
4. **Rated** — Price calculated via tariff rules (2.45 DKK/kWh + 0.50 DKK/min after 10 free minutes)
5. **Invoiced** — Invoice generated and persisted to the database

---

## Architecture

### Core Microservice (Session + Billing) — port 8000

Session and Billing run together as the **core microservice**:

| Service | Type | URL prefix | Responsibility |
|---|---|---|---|
| **session-service** | Core | `/sessions/*` | ChargingSession aggregate + state machine |
| **billing-service** | Generic | `/billing/*` | Tariff rating + invoice line generation |

> **DDD note — Bounded Context boundaries:**  
> Session service owns the `ChargingSession` aggregate and its state machine (`Created → Charging → Completed`).  
> Billing service is a **Bounded Context** that owns the `Invoice` aggregate. It handles its own state (`Generated`) and persists invoice data independently.  
> Session service mirrors the `Rated` and `Invoiced` statuses for readability, but the Billing service is the **authoritative source** for all invoicing data.

### External Capability (Analytics/ML) — port 8001

The **Analytics ML Service** is a **separate standalone service** — an external capability offered to customers (e.g. Copenhagen Municipality). It runs independently and is not part of the core microservice.

| Service | Port | Responsibility |
|---|---|---|
| **analytics-service** | `8001` | ML prediction (linear regression) — energy and revenue |


**Azure Web App (live):**  
[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

👉 **Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Tech Stack

- **API:** Python (FastAPI) with Swagger/OpenAPI docs
- **Database:** SQLite (both local and in production)
- **Cloud:** Microsoft Azure (App Service) — code-based deployment
- **CI/CD:** GitHub Actions — automatic build, test, deploy and rollback
- **ML:** Scikit-learn Linear Regression (separate standalone service)
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
**Entry point for core microservice (Session + Billing).**  
Run with: `uvicorn src.main:app --reload --port 8000`  
Swagger at: `http://localhost:8000/docs`

#### `src/analytics_service/main.py`
**Entry point for standalone Analytics ML service.**  
Run with: `uvicorn src.analytics_service.main:app --reload --port 8001`  
Swagger at: `http://localhost:8001/docs`

#### `src/shared/events.py`
**Shared event models** used across all services:  
`SessionStarted`, `SessionValidated`, `SessionRated`, `InvoiceLineGenerated`

#### `src/shared/database.py`
**Database helper** — SQLite (both local and in production).  
- `DATABASE_URL` unset → SQLite (`voltedge.db` created automatically on startup)
- Also supports MySQL via `DATABASE_URL=mysql://...` (prepared but not used)

---

#### `src/session_service/session_api.py` — Session Service (Core)

**Purpose:** Manages a charging session as a **state machine**.

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
*(Note: Rated/Invoiced statuses are mirrored from Billing Context. Billing is the authoritative source for invoice data.)*


---

#### `src/billing_service/billing_api.py` — Billing Service (Generic / Pure Domain Service)

**Purpose:** Price calculation (rating) and invoice generation — persists invoices to SQLite.

| Endpoint | Description |
|---|---|
| `GET /billing/health` | Health check |
| `POST /billing/rate` | Calculate price: 2.45 DKK/kWh + 0.50 DKK/min after 10 free min |
| `POST /billing/invoice` | Create invoice → emit `InvoiceLineGenerated` |

**Pricing logic (defined in `tariff.py`):**
- Energy: 2.45 DKK/kWh
- Parking: 0.50 DKK/min after 10 free minutes

---

#### `src/analytics_service/analytics_api.py` — Analytics Service (Supporting)

**Purpose:** ML prediction of energy consumption and revenue via linear regression.

| Endpoint | Description |
|---|---|
| `GET /analytics/health` | Health check |
| `POST /analytics/predict-energy` | Predict kWh based on duration, temperature and time of day |
| `POST /analytics/predict-revenue` | Predict revenue based on same features + kWh price and number of sessions |

**ML model:** LinearRegression with 3 features (duration_minutes, temperature, hour_of_day).  
Trained on simulated data (12 samples).

---

### `src/requirements.txt`

**Dependencies:**
- `fastapi` + `uvicorn` (web server)
- `pydantic` (data validation)
- `scikit-learn` + `numpy` (ML)
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

# 5a. Start the core microservice (Session + Billing) — Terminal 1
uvicorn src.main:app --reload --port 8000

# 5b. Start the Analytics ML service (external capability) — Terminal 2
uvicorn src.analytics_service.main:app --reload --port 8001

# 6. Open Swagger UI in your browser:
#    Core:  http://localhost:8000/docs
#    ML:    http://localhost:8001/docs
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

Replace `http://localhost:8000` with the Azure URL if testing the live deployment.

```bash
# Health check
curl http://localhost:8000/health

# Start a session
curl -X POST http://localhost:8000/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"charger_id": "charger-1", "contract_id": "contract-1"}'

# ML predict energy (Analytics runs on port 8001)
curl -X POST http://localhost:8001/analytics/predict-energy \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60, "temperature": 15, "hour_of_day": 14}'

# ML predict revenue (Analytics runs on port 8001)
curl -X POST http://localhost:8001/analytics/predict-revenue \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60, "temperature": 15, "hour_of_day": 14, "kwh_price": 2.45, "num_sessions": 100, "num_chargers": 10}'
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

### Run servers

**Core microservice (Session + Billing):**
```bash
uvicorn src.main:app --reload --port 8000
```

**Analytics ML service (external capability):**
```bash
uvicorn src.analytics_service.main:app --reload --port 8001
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

### Azure Startup Command (core microservice only)

Set in Azure Portal → Configuration → General Settings:
```
cd src && uvicorn main:app --host 0.0.0.0 --port 8000
```
*(Analytics ML service runs separately as an external capability)*

---

## Project Structure

```
├── src/
│   ├── main.py                       # Core microservice entry point (Session + Billing)
│   ├── requirements.txt              # Python dependencies
│   ├── session_service/              # Core — ChargingSession aggregate
│   │   ├── session_api.py            # FastAPI endpoints + state machine
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── billing_service/              # Generic — Tariff & Invoice
│   │   ├── billing_api.py            # Rating + invoice endpoints
│   │   ├── tariff.py                 # Pricing rules (Value Object)
│   │   ├── rating_service.py         # Domain service
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── analytics_service/            # External ML capability (standalone on port 8001)
│   │   ├── main.py                   # Standalone FastAPI app entry point
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
