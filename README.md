# VoltEdge Mobility A/S — MVP Løsning

Velkommen til VoltEdge Mobility A/S MVP-løsningen.  
Projektet demonstrerer et **komplet sporbart dataflow** fra telemetri til faktura gennem en event-drevet microservice-arkitektur.

## Happy Path (4 trin)

```
SessionStarted → SessionValidated → SessionRated → InvoiceLineCreated
```

## Arkitektur

Alle 3 services kører i **én Azure Web App** og er tilgængelige via URL-præfiks:

| Service | Type | URL-præfiks | Ansvarsområde |
|---|---|---|---|
| **session-service** | Core | `/sessions/*` | ChargingSession aggregate + state machine |
| **billing-service** | Generic | `/billing/*` | Tariff rating + invoice line generation |
| **analytics-service** | Supporting | `/analytics/*` | ML anomaly detection (linear regression) |

**Azure Web App (live):**  
[https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net)

👉 **Swagger UI:** [https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs](https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/docs)

## Teknisk Stack

- **API:** Python (FastAPI) med Swagger/OpenAPI docs
- **Database:** PostgreSQL (Azure Flexible Server — valgfri, services falder back til in-memory)
- **Cloud:** Microsoft Azure (App Service) — code-based deployment
- **CI/CD:** GitHub Actions → automatisk build, test, deploy og rollback
- **ML:** Scikit-learn Linear Regression (domain service)
- **Secrets:** `.env.example` + GitHub Secrets (client-id, tenant-id, subscription-id)

## Kom i gang (Lokal kørsel)

### Klargør miljøet

```bash
python -m venv venv
.\venv\Scripts\Activate  # Windows
# source venv/bin/activate  # Mac/Linux
```

### Mulighed A — Kør alle services samlet (anbefalet)

```bash
cd src
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

👉 Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

### Mulighed B — Kør services individuelt

Hver service kan også køres standalone (f.eks. til udvikling):

```bash
# Terminal 1: session-service
cd src/session-service
pip install -r requirements.txt
uvicorn session_api:app --reload --port 8000

# Terminal 2: billing-service
cd src/billing-service
pip install -r requirements.txt
uvicorn billing_api:app --reload --port 8001

# Terminal 3: analytics-service
cd src/analytics-service
pip install -r requirements.txt
uvicorn analytics_api:app --reload --port 8002
```

## Test hele flowet med curl

### Step 1 — Start session
```bash
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"chargerId": "charger-1", "contractId": "contract-1"}'
```

### Step 2 — Authorize → Start charging → Complete
```bash
# Authorize
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/{SESSION_ID}/authorize

# Start charging
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/{SESSION_ID}/start-charging

# Complete (emit SessionValidated)
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/sessions/{SESSION_ID}/complete \
  -H "Content-Type: application/json" \
  -d '{"energyDelivered": 25.5, "durationMinutes": 60}'
```

### Step 3 — Rate session (Billing)
```bash
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/billing/rate \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "{SESSION_ID}", "energyDelivered": 25.5, "durationMinutes": 60, "chargerId": "charger-1", "contractId": "contract-1"}'
```

### Step 4 — Create invoice (Billing)
```bash
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/billing/invoice \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "{SESSION_ID}", "totalCost": 92.50, "currency": "DKK", "breakdown": {"energy": 62.50, "parking": 30.0}}'
```

### ML — Anomaly detection (Analytics)
```bash
# Predict expected kWh
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/analytics/predict \
  -H "Content-Type: application/json" \
  -d '{"durationMinutes": 60}'

# Detect anomaly
curl -X POST https://voltedge-app-fqgdacaadyd9axds.germanywestcentral-01.azurewebsites.net/analytics/detect \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "test-1", "energyDelivered": 2.0, "durationMinutes": 60}'
```

## Kør tests

```bash
pip install pytest httpx
pytest tests/ -v
```

## Database

PostgreSQL er **valgfri** — alle services fungerer med in-memory storage som standard.

### Automatisk schema-creation
Hvis `DATABASE_URL` miljøvariablen sættes, opretter app'en automatisk tabeller ved opstart via `init_db()` i `session_api.py`.

### PostgreSQL via Azure CI/CD
CI/CD pipelinen indeholder et step, der automatisk provisonerer en Azure PostgreSQL Flexible Server (Burstable B1ms, laveste pris), opretter `sessions` databasen og sætter `DATABASE_URL` som App Setting i Web App'en.

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci-cd-azure-deploy.yml`):

### Build job
1. **Checkout** kode
2. **Python 3.11** setup
3. **Installér afhængigheder** (alle services' deps bundlet i `src/`)
4. **Zip artifact** (`release.zip` — indeholder alle services + main.py + deps)

### Deploy job
1. **Login til Azure** via OpenID Connect (client-id/tenant-id/subscription-id)
2. **Tjek WEBSITE_RUN_FROM_PACKAGE** — deaktiveres hvis sat (forhindrer Oryx build)
3. **Hent Kudu credentials** — til ZIP API deploy
4. **Slet forældede Oryx artifacts** — rydder output.tar.zst og oryx-manifest.toml
5. **Backup nuværende wwwroot** — muliggør rollback
6. **Deploy via Kudu ZIP API** — `PUT /api/zip/site/wwwroot/`
7. **Sæt startup command** — `uvicorn main:app --host 0.0.0.0 --port 8000`
8. **Provisionér PostgreSQL** — opretter Azure Flexible Server + sætter DATABASE_URL
9. **Restart og verify** — venter på /health → 200, ellers rollback

### Rollback
Hvis health check fejler efter deploy, gendannes den forrige wwwroot automatisk fra backup-zip'en.

## Projektstruktur

```
├── src/
│   ├── main.py                 # Combined FastAPI app (entry point)
│   ├── requirements.txt        # Combined dependencies for all services
│   ├── session-service/        # Core — ChargingSession aggregate
│   │   ├── session_api.py      # FastAPI endpoints + state machine
│   │   ├── .env.example
│   │   └── requirements.txt
│   ├── billing-service/        # Generic — Tariff & Invoice
│   │   ├── billing_api.py      # Rating + invoice endpoints
│   │   ├── .env.example
│   │   └── requirements.txt
│   ├── analytics-service/      # Supporting — ML anomaly detection
│   │   ├── analytics_api.py    # Linear regression model + endpoints
│   │   ├── .env.example
│   │   └── requirements.txt
│   └── shared/
│       ├── events.py           # Fælles event-modeller
│       └── event-schemas.md    # Event-dokumentation
├── tests/
│   ├── test_session_service.py
│   ├── test_billing_service.py
│   └── test_analytics_service.py
├── postman/
│   └── VoltEdge MVP.postman_collection.json
├── .github/workflows/
│   └── ci-cd-azure-deploy.yml
├── MVP.md                      # MVP-definition (røres ikke uden tilladelse)
└── README.md
```

## Secrets Management

- `src/*/.env.example` — skabeloner til lokale miljøvariabler
- GitHub Secrets: `AZUREAPPSERVICE_CLIENTID_*`, `AZUREAPPSERVICE_TENANTID_*`, `AZUREAPPSERVICE_SUBSCRIPTIONID_*`
- Ingen secrets i kildekoden — kun `.env.example` templates
