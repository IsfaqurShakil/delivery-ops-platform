# Test Plan: Delivery Operations Platform

Version: 1.0 | Author: Isfaqur Rahman Shakil | Scope: Phase 1 (core)

## 1. Purpose
Verify that the backend decides correctly what happens when a delivery fails, protects data with role-based access, and keeps an append-only audit trail. All data is fake.

## 2. In scope
- Shipment API: create, read, change status
- Shipment state machine (all legal and illegal transitions)
- Exception rule engine (versioned JSON rules) and exception tasks
- Append-only audit log
- Authentication (JWT login) and role-based access (admin, dispatcher, rider, viewer)
- Data correctness at 100 and 10,000 rows (Python vs SQL vs pandas)
- Docker image build and startup

## 3. Out of scope (Phase 1)
- Dispatch engine, courier webhooks, COD reconciliation (Phase 2)
- Bulk CSV import, load testing, dashboard UI (Phase 3)
- Enforcement of COD blocking (currently recorded in audit details only)
- Real personal data, real payments, real SMS delivery

## 4. Test types and tools
| Type | Tool | Notes |
|---|---|---|
| Unit / rule tests | pytest | state machine, rule engine, config validation |
| API / integration | pytest + FastAPI TestClient | real PostgreSQL, each test rolled back |
| Security | pytest | missing, forged, expired tokens; wrong role; other rider's data; audit log tampering |
| Data correctness | pytest + pandas | known answers at 100 and 10,000 rows |
| Manual / exploratory | Swagger UI (/docs), Postman | documented in the test case sheet |
| Smoke (deployment) | GitHub Actions | docker compose up, GET /health |

## 5. Test environment
- Local: Windows 11, native PostgreSQL 17, Python 3.14
- CI: GitHub Actions, PostgreSQL 17 service container
- Docker: image based on Python 3.12, verified in CI only (Docker Desktop does not run on the author's laptop)

## 6. Test approach
- Positive, negative and boundary cases for every rule (example: max_attempts = 3, attempts 2, 3 and 4).
- Every illegal state transition must return 409.
- 401 for not logged in, 403 for wrong role, 404 (not 403) when a rider asks for another rider's shipment.
- Each test runs in a database transaction that is rolled back.
- Requirement changes update tests on purpose, with the reason in the commit message.

## 7. Entry and exit criteria
- Entry: code builds, database migrations apply (alembic upgrade head).
- Exit: all automated tests pass locally and in CI; no open high-severity bug; test case sheet executed.

## 8. Risks and limits
- Free-tier hosting sleeps when idle (cold start).
- Only fake, seeded data; real-world data quality problems are not covered.
- Known-answer tests prove aggregates (counts, COD totals), not every business rule.
- Docker was not run locally; CI is the evidence.

## 9. Defect handling
Real defects only, recorded with steps, expected result, actual result and severity, then fixed with a regression test.
