# Delivery Operations Platform

[![CI](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/ci.yml)
[![Docker](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/docker.yml/badge.svg)](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/docker.yml)

When a delivery fails, this backend decides automatically what happens next, records every change in an append-only audit log, and protects the data with role-based access.

All data is fake (seeded with Faker). No real personal data. The system handles operations only.

## Why this project

Failed deliveries, cash-on-delivery (COD) and wrong addresses are everyday problems for last-mile delivery in Bangladesh. The value here is in business rules, state machines and audit trails, not in a UI. The project is built and tested like a real backend: migrations, CI, Docker, role-based security, and a QA package (test plan, test cases, Postman, automated tests).

## What it does (Phase 1)

- **Shipment state machine:** created, assigned, out_for_delivery, delivered, attempt_failed, rescheduled, return_to_sender. Illegal moves return 409 and change nothing.
- **Exception rule engine:** when an attempt fails, the failure reason decides the next action. Rules live in a versioned JSON file (`config/exception_rules.json`), not in code. Every decision is written to the audit log with the rule version and the matched rule.
- **Append-only audit log:** PostgreSQL triggers block UPDATE, DELETE and TRUNCATE on `audit_log`.
- **JWT login with roles:** admin, dispatcher, rider, viewer. The role is always read from the database, not trusted from the token.
- **QA package:** test plan, test case sheet, Postman collection, 150 automated tests, CI.

## Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /health | public | Is the API alive |
| POST | /login | public | Get a JWT token (OAuth2 form: username, password) |
| POST | /shipments | admin, dispatcher | Create a shipment |
| GET | /shipments/{id} | any logged-in role (riders: own shipments only) | Read a shipment |
| POST | /shipments/{id}/status | admin, dispatcher, rider (limited) | Change status |

Interactive docs: http://localhost:8000/docs

Access rules:
- 401: not logged in, or bad / expired token.
- 403: logged in but role not allowed (example: a viewer tries to change a status).
- 404 (not 403): a rider asks for another rider's shipment, so the existence of the shipment is not leaked.
- Riders may only report out_for_delivery, delivered and attempt_failed.

## Exception rules (config version 1.0.0)

| Situation | Result |
|---|---|
| phone_off | rescheduled + sms_reminder task |
| customer_not_available | rescheduled |
| wrong_address | stays attempt_failed, customer_service_task created (waits for a human) |
| refused_by_customer | return_to_sender |
| 3rd failed attempt (max_attempts = 3) | return_to_sender; for COD shipments "block COD" is recorded |
| any other reason | default rule: customer_service_task |

After an automatic reschedule the shipment goes back to assigned, and a human cannot reschedule it again (409). The state machine always has the final say.

## Tech stack

Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL 17, pytest, pandas, Faker, Docker, Docker Compose, GitHub Actions, Postman.

## Quick start (Windows PowerShell)

Needs Python and a local PostgreSQL.

```powershell
git clone https://github.com/IsfaqurShakil/delivery-ops-platform.git
cd delivery-ops-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and fill in your own database password and a JWT secret of at least 32 characters. Never commit `.env`. Then:

```powershell
alembic upgrade head
python -m scripts.seed --count 100 --seed 42
python -m scripts.create_user --help
uvicorn app.main:app --reload
```

The seed script refuses to run on a non-local database, because it wipes data first. Same `--seed` gives the same data.

## Docker

`docker compose up --build` starts the API and PostgreSQL 17 (the image uses Python 3.12). This is verified by the Docker workflow in GitHub Actions, which builds the image, starts both containers and checks `GET /health`. Docker Desktop does not run on the author's laptop, so Docker was NOT run locally. CI is the evidence.

## Testing

Run the tests (local PostgreSQL must be running):

```powershell
python -m pytest -q
```

| What | Result | Where |
|---|---|---|
| Automated tests | 150 passed | local and GitHub Actions |
| Known-answer test | passed at 100 and 10,000 rows | tests/test_known_answers.py |
| Docker build + compose up + /health | passed | GitHub Actions (Docker workflow) |

How the tests work:
- Tests run against a real PostgreSQL. Each test runs inside a transaction that is rolled back.
- Covered: state machine (all status pairs), rule engine (including the max_attempts boundary), config validation, login, forged / expired / alg=none tokens, wrong role, other rider's data, deactivated users, append-only audit log.
- Known-answer test: Python computes the expected totals while generating fake data. PostgreSQL (SQL) and pandas must both match it exactly (shipment count, COD count, COD amount).
- `scripts/verify_counts.py` repeats the pandas vs SQL check on the local database.

QA documents:
- [Test plan](docs/test-plan.md)
- [Test case sheet](docs/test-cases.md) (15 core cases, each linked to the automated test that covers it)
- [Postman collection](postman/delivery-ops-platform.postman_collection.json): login, create, read, change status, viewer 403, no token 401. Passwords are Postman variables and are not stored in the file.

## Known limits (honest notes)

- Docker was verified in CI only, not on a local machine.
- `block_cod` is only recorded in the audit log details. It is not enforced yet.
- The known-answer test proves data storage and aggregates (counts and COD totals). It does not prove every business rule; the other tests do that.
- Only fake, seeded data. Real-world data quality problems are not covered.
- The Postman collection is run by hand. It is not run in CI (Newman) yet.
- No performance numbers are published yet. Nothing was measured beyond the 10,000-row correctness test.
- The app is not deployed yet.
- There is one `requirements.txt`, so test libraries (pytest, pandas, Faker) are also inside the Docker image.

## Demo vs production

| Topic | This project | A real production system |
|---|---|---|
| Secrets | `.env` file (git-ignored), fake demo values in compose | Secret manager |
| Data | Seeded fake data | Real traffic and messy data |
| Migrations | Run at container start | Separate migration job |
| Audit log | Append-only triggers; the app DB user could still drop a trigger | Separate restricted database role or write-once storage |
| Monitoring | None | Logs, metrics, alerts |
| Postman | Run by hand | Newman in CI |

## Roadmap (planned, not built yet)

- Phase 2: dispatch engine, courier webhooks with idempotency keys, COD reconciliation, Hypothesis invariant tests, Telegram alerts via n8n.
- Phase 3: bulk CSV import, analytics endpoints with indexes, benchmarks at 100 / 10k / 100k rows, load test, small dashboard with one UI test.

## Project layout

```text
app/        FastAPI app, models, state machine, rule engine, security
config/     exception_rules.json (versioned rules)
alembic/    database migrations
scripts/    seed, create_user, verify_counts
tests/      pytest suite
docs/       test plan, test case sheet
postman/    Postman collection
```

## Author

Isfaqur Rahman Shakil, CSE graduate, University of Asia Pacific.
