# VoltEdge Mobility A/S — MVP Solution

Welcome to the VoltEdge Mobility A/S MVP solution.  
This project demonstrates a **fully traceable data flow** from telemetry to invoice through an event-driven microservice architecture.

## Table of Contents

1. [Happy Path](#happy-path-4-steps)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Code Structure](#code-structure)
5. [Getting Started (Local Development)](#getting-started-local-development)
6. [Test the Full Flow](#test-the-full-flow)
7. [Testing with Postman](#testing-with-postman)
8. [Run Unit Tests](#run-unit-tests)
9. [Database Choice: SQLite](#database-choice-sqlite)
10. [CI/CD Pipeline](#cicd-pipeline)
11. [Command Reference](#command-reference)
12. [Secrets Management](#secrets-management)

---

## Happy Path (4 steps)

```
SessionStarted → SessionValidated → PriceCalculated → InvoiceGenerated

Each event represents a step in the billing chain:
1. **SessionStarted** — A vehicle connects to a charger
2. **SessionValidated** — Charging is completed with metered data
3. **PriceCalculated** — Price is calculated based on tariff rules
4. **InvoiceGenerated** — An invoice line is generated

---

## Architecture

All 3 services run in a **single Azure Web App** and are accessible via URL prefixes:

| Service | Type | URL prefix | Responsibility |
|---|---|---|---|
| **session-service** | Core | `/sessions/*` | ChargingSession aggregate + state machine |
| **billing-service** | Generic | `/billing/*` | Tariff rating + invoice line generation |
| **analytics-service** | Supporting | `/analytics/*` | ML anomaly detection (linear regression) |

**Azure Web App (live):**  
[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

👉 **Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Tech Stack

- **API:** Python (FastAPI) with Swagger/OpenAPI docs
- **Database:** SQLite (persistent file-based, zero config)
- **Cloud:** Microsoft Azure (App Service) — code-based deployment
- **CI/CD:** GitHub Actions — automatic build, test, deploy and rollback
- **ML:** Scikit-learn Linear Regression (domain service)
- **Secrets:** `.env.example` + GitHub Secrets

---

## Code Structure

### Root files

| File | Purpose |
|---|---|
| `README.md` | Project documentation |
| `MVP.md` | MVP definition |
| `.gitignore` | Ignores `venv/`, `__pycache__/`, `.env`, `*.db`, etc. |
| `requirements.txt` | Root requirements (references `src/requirements.txt`) |

### `src/` — Python application

#### `src/main.py`
**Entry point.** Combines all 3 services into a single FastAPI app.  
Run with: `uvicorn main:app --reload --port 8000`  
Swagger at: `http://localhost:8000/docs`

#### `src/shared/events.py`
**Shared event models** used across all services:  
`SessionStarted`, `SessionValidated`, `PriceCalculated`, `InvoiceGenerated`

#### `src/shared/database.py`
**Database helper** — creates and manages SQLite connection.  
Creates `voltedge.db` automatically on startup.  
Switches to PostgreSQL if `DATABASE_URL` is set.

---

#### `src/session_service/session_api.py` — Session Service (Core)

**Purpose:** Manages a charging session as a **state machine**.

| Endpoint | Description |
|---|---|
| `GET /sessions/health` | Health check |
| `POST /sessions/start` | Create new session → status: `Created` |
| `POST /sessions/{id}/authorize` | Authorize → status: `Authorized` |
| `POST /sessions/{id}/start-charging` | Start charging → status: `Charging` |
| `POST /sessions/{id}/complete` | Complete → status: `Completed` → emit `SessionValidated` |
| `GET /sessions/{id}` | Get session data |

**State machine:** `Created → Authorized → Charging → Completed`

---

#### `src/billing_service/billing_api.py` — Billing Service (Generic)

**Purpose:** Price calculation (rating) and invoice generation.

| Endpoint | Description |
|---|---|
| `GET /billing/health` | Health check |
| `POST /billing/rate` | Calculate price: 2.45 DKK/kWh + 0.50 DKK/min after 10 free min |
| `POST /billing/invoice` | Create invoice → emit `InvoiceGenerated` |

**Pricing logic:**
- Energy: 2.45 DKK/kWh
- Parking: 0.50 DKK/min after 10 free minutes
- Configurable via environment variables (`.env.example`)

---

#### `src/analytics_service/analytics_api.py` — Analytics Service (Supporting)

**Purpose:** ML anomaly detection using linear regression.

| Endpoint | Description |
|---|---|
| `GET /analytics/health` | Health check |
| `POST /analytics/predict` | Predict expected kWh based on duration |
| `POST /analytics/detect` | Compare actual vs expected → flag deviations > 40% |

**ML model:** Trained on simulated data (10-300 min, 2-75 kWh).  
Sessions deviating >40% from expected are flagged as **anomalies**.

---

### `src/requirements.txt`

**Dependencies:**
- `fastapi` + `uvicorn` (web server)
- `pydantic` (data validation)
- `scikit-learn` + `numpy` (ML)
- `pytest` + `httpx` (testing)

### Environment variables (`.env.example`)

| File | Variables |
|---|---|
| `session_service/.env.example` | `DATABASE_URL` — PostgreSQL connection (optional) |
| `billing_service/.env.example` | `ENERGY_RATE`, `PARKING_RATE`, `PARKING_FREE_MINUTES` |
| `analytics_service/.env.example` | `ANOMALY_THRESHOLD` — anomaly threshold percentage |

---

## Getting Started (Local Development)

### Setup environment

```bash
python -m venv venv
.\venv\Scripts\Activate  # Windows
# source venv/bin/activate  # Mac/Linux
```

### Option A — Run all services together (recommended)

```bash
cd src
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

👉 Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

### Option B — Run services individually

```bash
# Terminal 1: session-service
cd src/session_service
pip install -r requirements.txt
uvicorn session_api:app --reload --port 8000

# Terminal 2: billing-service
cd src/billing_service
pip install -r requirements.txt
uvicorn billing_api:app --reload --port 8001

# Terminal 3: analytics-service
cd src/analytics_service
pip install -r requirements.txt
uvicorn analytics_api:app --reload --port 8002
```

---

## Test the Full Flow

### Happy Path via Swagger

1. Open: `https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs`
2. Run requests in sequence:

**Step 1 — Start session:**
```json
POST /sessions/start
{"charger_id": "charger-1", "contract_id": "contract-1"}
```

**Step 2 — Authorize:** `POST /sessions/{session_id}/authorize`

**Step 3 — Start charging:** `POST /sessions/{session_id}/start-charging`

**Step 4 — Complete:**
```json
POST /sessions/{session_id}/complete
{"energy_delivered": 25.5, "duration_minutes": 60}
```

**Step 5 — Rate:**
```json
POST /billing/rate
{"session_id": "{SESSION_ID}", "energy_delivered": 25.5, "duration_minutes": 60, ...}
```

**Step 6 — Invoice:**
```json
POST /billing/invoice
{"session_id": "{SESSION_ID}", "total_cost": 92.50, "currency": "DKK", ...}
```

### Test with curl

```bash
# Health check
curl https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/health

# Start a session
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"charger_id": "charger-1", "contract_id": "contract-1"}'

# ML prediction
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/analytics/predict \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60}'

# ML anomaly detection
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/analytics/detect \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "energy_delivered": 2.0, "duration_minutes": 60}'
```

---

## Testing with Postman

1. Open Postman
2. **File → Import** → select `postman/VoltEdge MVP.postman_collection.json`
3. Set the `base_url` variable to your Azure URL or `http://localhost:8000`
4. Run requests in sequence (each step depends on the previous)

The collection includes 12 requests across 4 groups:
- Health checks (all services)
- Session Happy Path (start → authorize → start-charging → complete)
- Billing (rate → invoice)
- Analytics (predict → detect)

---

## Run Unit Tests

```bash
python -m pytest tests/ -v
```

All 19 tests across 3 services:
- `tests/test_session_service.py` (6 tests) — state machine transitions
- `tests/test_billing_service.py` (6 tests) — price calculation accuracy
- `tests/test_analytics_service.py` (7 tests) — ML prediction and anomaly detection

---

## Database Choice: SQLite

### Why SQLite instead of PostgreSQL?

| Requirement | PostgreSQL | SQLite |
|---|---|---|
| **Setup complexity** | Requires server, credentials, network config | Zero setup — just a file |
| **Cost** | ~165 DKK/month (Azure Flexible Server B1ms) | **Free** — no infrastructure |
| **CI/CD integration** | Must provision server in pipeline | **Automatic** — created on app start |
| **MVP suitability** | Overkill for demo/traceability | **Perfect fit** — lightweight, portable |
| **Migration path** | Change `DATABASE_URL` env var | Same — just switch the URL |

### Decision rationale

The MVP focuses on demonstrating **traceability from telemetry to invoice** — not on database scalability. SQLite provides:

1. **Persistence without infrastructure** — data survives restarts without managing a server
2. **CI/CD ready** — database is created automatically when the app starts
3. **Portable** — the `.db` file can be copied, backed up, or reset in seconds
4. **Zero cost** — no Azure PostgreSQL costs during development or MVP demo

### Production path

When VoltEdge moves beyond MVP, **no code changes are needed** — simply set the `DATABASE_URL` environment variable to a PostgreSQL connection string, and the app switches automatically.

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
cd src && uvicorn main:app --reload --port 8000
```

- `cd src` — enter source directory
- `uvicorn main:app` — start server with `app` from `main.py`
- `--reload` — auto-restart on file changes
- `--port 8000` — listen on port 8000

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
│   ├── main.py                       # Combined FastAPI app (entry point)
│   ├── requirements.txt              # Combined dependencies
│   ├── session_service/              # Core — ChargingSession aggregate
│   │   ├── session_api.py            # FastAPI endpoints + state machine
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── billing_service/              # Generic — Tariff & Invoice
│   │   ├── billing_api.py            # Rating + invoice endpoints
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── analytics_service/            # Supporting — ML anomaly detection
│   │   ├── analytics_api.py          # Linear regression model + endpoints
│   │   ├── .env.example
│   │   └── __init__.py
│   └── shared/
│       ├── events.py                 # Shared event models
│       ├── database.py               # SQLite database helper
│       └── __init__.py
├── tests/                            # 19 pytest tests
├── postman/                          # Postman collection (12 requests)
├── .github/workflows/                 # GitHub Actions CI/CD
├── requirements.txt                  # Root requirements
├── MVP.md                            # MVP definition
└── README.md
```

---

## Secrets Management

- `src/*/.env.example` — templates for local environment variables
- GitHub Secrets: publish profile credentials configured via Azure Deployment Center
- No secrets in source code — only `.env.example` templates
- Database is created automatically as SQLite — no credentials needed for development

---

## License

This project is developed as part of the 6th semester exam at Københavns Erhvervsakademi.
