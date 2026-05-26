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
9. [Database: MySQL / SQLite](#database-mysql-production--sqlite-local-dev)
10. [CI/CD Pipeline](#cicd-pipeline)
11. [Command Reference](#command-reference)
12. [Secrets Management](#secrets-management)

---

## Happy Path (4 steps)

```
SessionStarted → SessionValidated → SessionRated → InvoiceLineGenerated
```

Each event represents a step in the billing chain:
1. **SessionStarted** — A vehicle connects to a charger
2. **SessionValidated** — Charging is completed with metered data
3. **SessionRated** — Price is calculated based on tariff rules
4. **InvoiceLineGenerated** — An invoice line is generated

---

## Architecture

All 3 services run in a **single Azure Web App** and are accessible via URL prefixes:

| Service | Type | URL prefix | Responsibility |
|---|---|---|---|
| **session-service** | Core | `/sessions/*` | ChargingSession aggregate + state machine |
| **billing-service** | Generic | `/billing/*` | Tariff rating + invoice line generation |
| **analytics-service** | Supporting | `/analytics/*` | ML anomaly detection (linear regression) |

> **DDD note — Bounded Context boundaries:**  
> Session service owns the `ChargingSession` aggregate and its state machine (`Created → Authorized → Charging → Completed`).  
> Billing service is a **Bounded Context** that owns the `Invoice` aggregate. It handles its own state (`Generated`) and persists invoice data independently.  
> Session service mirrors the `Rated` and `Invoiced` statuses for readability, but the Billing service is the **authoritative source** for all invoicing data.

**Azure Web App (live):**  
[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

👉 **Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Tech Stack

- **API:** Python (FastAPI) with Swagger/OpenAPI docs
- **Database:** MySQL (production on Azure) / SQLite (local dev, auto-fallback)
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
| `.gitignore` | Ignores `venv/`, `__pycache__/`, `.env`, `*.db`, etc. |
| `requirements.txt` | Root requirements (references `src/requirements.txt`) |

### `src/` — Python application

#### `src/main.py`
**Entry point.** Combines all 3 services into a single FastAPI app.  
Run with: `uvicorn main:app --reload --port 8000`  
Swagger at: `http://localhost:8000/docs`

#### `src/shared/events.py`
**Shared event models** used across all services:  
`SessionStarted`, `SessionValidated`, `SessionRated`, `InvoiceLineGenerated`

#### `src/shared/database.py`
**Database helper** — MySQL (production) with SQLite fallback (local dev).  
- `DATABASE_URL=mysql://user:password@host:3306/voltedge` → MySQL  
- `DATABASE_URL` unset → SQLite (`voltedge.db` created automatically on startup)

---

#### `src/session_service/session_api.py` — Session Service (Core)

**Purpose:** Manages a charging session as a **state machine**.

| Endpoint | Description |
|---|---|
| `GET /sessions/health` | Health check |
| `POST /sessions/start` | Create new session → status: `Created` |
| `POST /sessions/{id}/authorize` | Authorize → status: `Authorized` |
| `POST /sessions/{id}/start-charging` | Start charging → status: `Charging` |
| `POST /sessions/{id}/complete` | Complete → status: `Completed` |
| `POST /sessions/{id}/rate` | Calculate price → status: `Rated` |
| `POST /sessions/{id}/invoice` | Generate invoice → status: `Invoiced` |
| `GET /sessions/{id}` | Get session data |

**State machine:** `Created → Authorized → Charging → Completed → Rated → Invoiced`  
*(Note: Rated/Invoiced statuses are mirrored from Billing Context. Billing is the authoritative source for invoice data.)*


---

#### `src/billing_service/billing_api.py` — Billing Service (Generic / Pure Domain Service)

**Purpose:** Price calculation (rating) and invoice generation — no side effects, no DB writes.

| Endpoint | Description |
|---|---|
| `GET /billing/health` | Health check |
| `POST /billing/rate` | Calculate price: 2.45 DKK/kWh + 0.50 DKK/min after 10 free min |
| `POST /billing/invoice` | Create invoice → emit `InvoiceLineGenerated` |

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
- `mysql-connector-python` (MySQL driver for production)
- `pytest` + `httpx` (testing)

### Environment variables (`.env.example`)

- **`session_service/.env.example`**
  - `DATABASE_URL`: MySQL connection string (optional).

- **`billing_service/.env.example`**
  - `ENERGY_RATE`: DKK per kWh.
  - `PARKING_RATE`: DKK per minute.
  - `PARKING_FREE_MINUTES`: Free parking minutes.

- **`analytics_service/.env.example`**
  - `ANOMALY_THRESHOLD`: Anomaly threshold percentage.

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
cd src
pip install -r requirements.txt

# 5. Start the server (all 3 services in one app)
uvicorn main:app --reload --port 8000

# 6. Open Swagger UI in your browser:
#    http://localhost:8000/docs
```

That's it — the SQLite database (`voltedge.db`) is created automatically on app startup via `init_db()`.  
For MySQL, set `DATABASE_URL=mysql://user:password@host:3306/voltedge` in your environment.

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

1. Open Swagger UI:
   - **Local:** `http://localhost:8000/docs`
   - **Live:** `https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs`
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

**Step 5 — Rate (transition to Rated):**
```
POST /sessions/{session_id}/rate
```
No body required — reads meter data from the session automatically.

**Step 6 — Invoice (transition to Invoiced):**
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

# ML prediction
curl -X POST http://localhost:8000/analytics/predict \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60}'

# ML anomaly detection
curl -X POST http://localhost:8000/analytics/detect \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "energy_delivered": 2.0, "duration_minutes": 60}'
```

**Live deployment URL:**  
`https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net`

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

## Database: MySQL (Production) / SQLite (Local Dev)

### Why MySQL for production?

| Requirement | MySQL (Azure Flexible Server) | SQLite (local dev) |
|---|---|---|
| **Persistence on Azure** | ✅ Data survives restarts/scaling | ❌ Ephemeral storage — data lost |
| **Setup complexity** | Azure Portal wizard — 5 min | Zero setup — just a file |
| **Cost** | **Free tier** (B1ms, 12 months) | **Free** |
| **Concurrent access** | Multi-user, connection pooling | Single-writer only |
| **Exam relevance** | Demonstrates real-world DB architecture | Quick local iteration |

### Decision

The app uses **MySQL** when deployed on Azure via the `DATABASE_URL` environment variable, and falls back to **SQLite** automatically when developing locally (no config needed).

### Production path — Azure Database for MySQL Flexible Server

1. Go to **Azure Portal → Create a resource → Azure Database for MySQL Flexible Server**
2. Select **Free tier** (B1ms, 1 vCore, 2 GB RAM, 32 GB storage)
3. Create a database named `voltedge`
4. In **Networking**, add firewall rule: "Allow public access from Azure services"
5. Get the connection string: `mysql://user:password@server.mysql.database.azure.com:3306/voltedge`
6. Set as `DATABASE_URL` in Azure Portal: **App Service → Settings → Environment variables**

### Local development

No setup needed — SQLite is used automatically when `DATABASE_URL` is not set.
The database file `voltedge.db` is created in `src/` automatically on app startup via `init_db()`.

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
The database is **not** provisioned by the CI/CD pipeline itself — instead, it is created **at application startup** via the `init_db()` function in `src/shared/database.py`. This means:

- **SQLite** (local dev): `voltedge.db` is created automatically in `src/` on first request
- **MySQL** (production via `DATABASE_URL`): The `CREATE TABLE IF NOT EXISTS` statements run on app start, ensuring tables exist without manual setup

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
│   ├── requirements.txt              # Python dependencies
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
│   ├── database.py               # MySQL / SQLite database helper
│       └── __init__.py
├── .github/workflows/                # GitHub Actions CI/CD
├── requirements.txt                  # Root requirements (references src/)
└── README.md
```

---

## Secrets Management

- `src/*/.env.example` — templates for local environment variables
- GitHub Secrets: publish profile credentials configured via Azure Deployment Center
- No secrets in source code — only `.env.example` templates
- Database is created automatically as SQLite for local dev — no credentials needed
- For production, set `DATABASE_URL=mysql://user:password@host:3306/voltedge` as an Azure App Setting

---

## License

This project is developed as part of the 6th semester exam at Københavns Erhvervsakademi.
