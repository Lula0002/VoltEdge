# Database Choice: SQLite for MVP

## Why SQLite instead of PostgreSQL?

| Requirement | PostgreSQL | SQLite |
|---|---|---|
| **Setup complexity** | Requires server, credentials, network config | Zero setup — just a file |
| **Cost** | ~165 DKK/month (Azure Flexible Server B1ms) | **Free** — no infrastructure |
| **CI/CD integration** | Must provision server in pipeline | **Automatic** — created on app start |
| **MVP suitability** | Overkill for demo/traceability | **Perfect fit** — lightweight, portable |
| **Migration path** | Change `DATABASE_URL` env var | Same — just switch the URL |

## Decision rationale

The MVP focuses on demonstrating **traceability from telemetry to invoice** — not on database scalability. SQLite provides:

1. **Persistence without infrastructure** — data survives restarts without managing a server
2. **CI/CD ready** — database is created automatically when the app starts, fulfilling the requirement that *"the entire microservice and tech stack should be built automatically"*
3. **Portable** — the `.db` file can be copied, backed up, or reset in seconds
4. **Zero cost** — no Azure PostgreSQL costs during development or MVP demo

## Production path

When VoltEdge moves beyond MVP, **no code changes are needed** — simply set the `DATABASE_URL` environment variable to a PostgreSQL connection string, and the app switches automatically.
