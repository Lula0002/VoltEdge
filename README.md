# VoltEdge Mobility A/S — MVP Solution

Welcome to the VoltEdge Mobility A/S MVP solution.  
This project demonstrates a **fully traceable data flow** from telemetry to invoice through an event-driven microservice architecture.

## Table of Contents

1. [Happy Path](#happy-path-5-steps)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Getting Started (Local Development)](#getting-started-local-development)
5. [Test the Full Flow](#test-the-full-flow)
6. [Database](#database-sqlite)
7. [CI/CD Pipeline](#cicd-pipeline)
8. [Project Structure](#project-structure)
9. [Secrets Management](#secrets-management)

---

## Happy Path (5 steps)

```
Created → Charging → Completed → Rated → Invoiced
```

The **Session** aggregate (SessionID as root) follows a state machine through 5 statuses:

| Step | Endpoint | What happens |
|------|----------|-------------|
| 1. **Created** | `POST /sessions/start` | Session created with charger_id and contract_id |
| 2. **Charging** | `POST /sessions/{id}/start-charging` | Charging begins |
| 3. **Completed** | `POST /sessions/{id}/validate` | Meter data submitted (energy, duration, charging time) |
| 4. **Rated** | `POST /sessions/{id}/rate` | Invoice line ID (UUID) assigned — **no price calculation** |
| 5. **Invoiced** | `POST /sessions/{id}/invoice` | Price calculated via Tariff + OverstayPolicy, invoice persisted |

### Pricing model

| Component | Rate | Paid when |
|-----------|------|-----------|
| **Energy** (Tariff) | 2,45 DKK/kWh | **Always** — core product |
| **Parking overstay** (OverstayPolicy) | 15 DKK / 30 min (0,50 DKK/min) | **Only if** car remains after charging + 10 min grace |

### Example: 25.5 kWh, 60 min total, 45 min charging

```
Energy:       25.5 kWh × 2,45 DKK/kWh  =  62,48 DKK
Parking:      max(0, 60 − 45 − 10) × 0,50  =   2,50 DKK
                                    Total  =  64,98 DKK
```

---

## Architecture

All modules run in a **single Azure Web App** on one port — each with its own URL prefix:

| Module | Role in Bounded Context | URL prefix | Responsibility |
|--------|------------------------|------------|---------------|
| **Session** | Aggregate 1 (Core) | `/sessions/*` | State machine: Created → Charging → Completed |
| **InvoiceLine** | Aggregate 2 (Generic) | `/billing/*` | Tariff calculation + invoice generation |
| **Analytics/ML** | External capability (API only) | `/analytics/*` | ML prediction — HTTP only (no direct imports) |

> **DDD note — Bounded Context:**  
> **Charging Session** is **one** Bounded Context owning **two aggregates**:  
> - **Aggregate 1:** `Session` — entity with **SessionID** as root, manages the charging state machine  
> - **Aggregate 2:** `InvoiceLine` — entity with **InvoiceLineID** as root, handles pricing and invoicing  
>  
> Session and InvoiceLine communicate via direct Python imports (same Bounded Context).  
> Analytics/ML is an **external capability** — accessible **only** via HTTP (`/analytics/*`).  
> No direct Python imports exist between core code and the ML model.

**Azure Web App:**  
[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

👉 **Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

---

## Tech Stack

- **API:** Python (FastAPI) with Swagger/OpenAPI docs
- **Database:** SQLite (both local and in production)
- **Cloud:** Microsoft Azure (App Service) — code-based deployment
- **CI/CD:** GitHub Actions — automatic build, deploy and rollback
- **ML:** Scikit-learn Linear Regression (external capability via HTTP)
- **Integration:** Session/Billing calls Analytics via HTTP (httpx) — proving separation
- **BI-readiness:** GET endpoints (`/sessions/`, `/billing/invoices`) can be called directly from Power BI, Excel, or other BI tools
- **CORS:** Enabled across all endpoints
- **Secrets:** `.env.example` + GitHub Secrets

---

## Getting Started (Local Development)

### Prerequisites

- **Python 3.9+** installed ([python.org](https://python.org))
- **Git** installed ([git-scm.com](https://git-scm.com))

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

**Step 3 — Validate (submit meter data):**
```json
POST /sessions/{session_id}/validate
{"energy_delivered": 25.5, "duration_minutes": 60, "charging_duration_minutes": 45}
```

**Step 4 — Rate (assign invoice line ID):**
```
POST /sessions/{session_id}/rate
```
Returns `invoice_line_id` (UUID). No price calculation yet.

**Step 5 — Invoice (calculate price + persist):**
```
POST /sessions/{session_id}/invoice
```
Returns full breakdown with energy and parking overstay charges.

### Auto flow (one-call demo)

```json
POST /auto-flow-with-ml
{
  "charger_id": "charger-1",
  "contract_id": "contract-1",
  "energy_delivered": 25.5,
  "duration_minutes": 60,
  "charging_duration_minutes": 45
}
```
Runs the full Happy Path **and** calls Analytics/ML via HTTP — proving the external capability pattern.

### Test with curl

```bash
# Start a session
SID=$(curl -s -X POST http://localhost:8000/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"charger_id":"charger-1","contract_id":"contract-1"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['session_id'])")

# Start charging
curl -s -X POST "http://localhost:8000/sessions/$SID/start-charging"

# Validate (submit meter data)
curl -s -X POST "http://localhost:8000/sessions/$SID/validate" \
  -H "Content-Type: application/json" \
  -d '{"energy_delivered":25.5,"duration_minutes":60,"charging_duration_minutes":45}'

# Rate (assign invoice line ID)
curl -s -X POST "http://localhost:8000/sessions/$SID/rate"

# Invoice (calculate price + persist)
curl -s -X POST "http://localhost:8000/sessions/$SID/invoice" | python3 -m json.tool
```

### Example invoice response

```json
{
  "invoice_line_id": "abc-123",
  "session_id": "...",
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
  "timestamp": "..."
}
```

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

> **Note:** Unit tests are not part of the current build pipeline. The `tests/` directory and Postman collection are not included in this repository.

### Deploy job
1. **Download artifact** from build job
2. **Deploy to Azure Web App** using publish profile credentials

### Database creation (automatic)
The database is created **at application startup** via `init_db()` in `src/shared/database.py`.  
`voltedge.db` is created automatically on first request — no separate provisioning step needed.

### Rollback
If the deployment fails, the previous version remains untouched on Azure.

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
│   ├── billing_service/              # Aggregate 2: InvoiceLine (InvoiceLineID as root)
│   │   ├── billing_api.py            # Invoice list endpoint
│   │   ├── tariff.py                 # Tariff (energy rate) + OverstayPolicy (parking penalty)
│   │   ├── rating_service.py         # Domain service
│   │   ├── .env.example
│   │   └── __init__.py
│   ├── analytics_service/            # External capability: Analytics/ML (API only)
│   │   ├── analytics_api.py          # ML prediction endpoints
│   │   ├── ml_model.py               # Linear regression model (isolated)
│   │   ├── .env.example
│   │   └── __init__.py
│   └── shared/
│       ├── events.py                 # Shared event models
│       ├── database.py               # SQLite database helper
│       └── __init__.py
├── .github/workflows/                # GitHub Actions CI/CD
│   └── main_voltedge-app.yml
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

This project is developed as part of the 6th semester exam at Copenhagen Business Academy.
