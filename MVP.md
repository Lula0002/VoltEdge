# MVP Definition: VoltEdge Mobility Platform

## 1. MVP Fokus
Denne MVP realiserer en central del af VoltEdge Mobility A/S' arkitektur med fokus på **Automated billing & settlement** understøttet af **Data-driven services**. Vi skaber sporbarhed fra rå telemetri til faktura.

### Implementeringsstrategi (Happy Path):
For at sikre en realistisk og stærk MVP, implementeres "Happy Path" fuldt ud:
`SessionStarted` -> `SessionValidated` -> `SessionRated` -> `InvoiceLineGenerated`

### Strategisk vs. Teknisk Implementering:
Vi anerkender et bevidst misforhold mellem strategisk vigtighed og implementeringsdybde:
- **Core (Driftsoptimering):** Strategisk vigtigst (differentiering), men implementeret i en afgrænset form (session-validering).
- **Generic (Fakturering):** Strategisk standardiseret, men implementeret i dybden for at demonstrere et komplet, sporbart end-to-end flow.
- **Argument:** MVP'en demonstrerer integrationen mellem core-subdomænets session-håndtering og det generiske faktureringssubdomæne, hvor `SessionValidated` udgør kontraktgrænsen.

## 2. Ubiquitous Language (Sprog)
- **ChargingSession:** Entitet for processen fra tilslutning til afbrydelse.
- **Tariff:** Regelsæt for prissætning (time-of-use, abonnement, fleet-aftale).
- **Rating:** Domain service der beregner prisen for en session baseret på tarif.
- **InvoiceLine:** En beregnet post på en faktura.
- **Settlement:** Den endelige afregning mellem VoltEdge og partnere.

## 3. Teknologisk Arkitektur (Microservices)
Vi anvender en brugervenlig og læsevenlig arkitektur, hvor hver service er isoleret i sin egen mappe:

- **`/session-service/` (Core):** Håndterer `ChargingSession` aggregatet.
- **`/billing-service/` (Generic):** Håndterer `Tariff` og `Invoice` aggregater.
- **`/analytics-service/` (Supporting):** Aktiv **Domain Service** der kører ML-anomali-detektion.
- **`/shared/`:** Fælles event-modeller og event-bus konfiguration.

### Navngivningskonvention (Fil-præfiks):
For at sikre hurtigt overblik navngives alle filer efter deres funktion:
- `session-*.py`: Logik relateret til session-håndtering.
- `billing-*.py`: Logik relateret til afregning og fakturering.
- `analytics-*.py`: Logik relateret til ML og BI-data.

## 4. Teknologisk Stack
- **API:** Web API (Python/FastAPI) dokumenteret med **Swagger/OpenAPI**.
- **Database:** PostgreSQL (Relationel model til DDD-aggregater).
- **Cloud:** Microsoft Azure (App Service - Code-based deployment).
- **Data Analytics:** Power BI (uafhængig BI-løsning læser fra Analytics DB).
- **Arkitektur:** Microservice-baseret (fokuseret på *Driftsoptimering* Bounded Context).

## 5. Succeskriterier
1. **Sporbarhed:** Fuldt dataflow fra telemetri til faktura via "Happy Path".
2. **Automatisering:** Rating og fakturering sker uden manuel indgriven.
3. **Analyse:** ML-model detekterer afvigelser i afregningsdata (via flag-events).
4. **BI:** Dashboard viser omsætning pr. operatør/kommune.

## 6. Drift, Overvågning og CI/CD (Obligatoriske krav)
- **Logning:** Azure Application Insights integreres i Web API'et.
- **Health Checks:** `/health` endpoint pr. service.
- **Secrets Management:** API-nøgler håndteres via Azure Key Vault / miljøvariabler.
- **CI/CD:** GitHub Actions pipeline der automatisk deployer Python-kode direkte til Azure App Service.
- **Dokumentation:** Repository indeholder en fyldestgørende `README.md` med setup-guide og Swagger-link.
- **Test:** Unit tests for forretningslogik (f.eks. `RatingService`) og Postman collection til API-test.
- **Rollback:** Automatisk rollback-strategi ved fejlede builds.
