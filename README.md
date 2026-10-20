# Delivery Operations Platform

[![CI](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/ci.yml)
[![Docker](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/docker.yml/badge.svg)](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/docker.yml)

When a delivery fails, this backend decides automatically what happens next, records every change in an append-only audit log, and protects the data with role-based access.

All data is fake (seeded with Faker). No real personal data.

## What it does (Phase 1)

- Shipment state machine: created, assigned, out_for_delivery, delivered, attempt_failed, rescheduled, return_to_sender. Illegal moves return 409.
- Exception rule engine: failure reason decides the next action. Rules live in a versioned JSON file (`config/exception_rules.json`), not in code.
- Append-only audit log: PostgreSQL triggers block UPDATE, DELETE and TRUNCATE.
- JWT login with roles: admin, dispatcher, rider, viewer.
- QA material: test plan, test case sheet, Postman collection, 150 automated tests.

## Tech stack

Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL 17, pytest, pandas, Docker, GitHub Actions.

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

Open `.env` and fill in your own database password and a JWT secret of at least 32 characters. Then:

```powershell
alembic upgrade head
python -m scripts.seed --count 100 --seed 42
python -m scripts.create_user --help
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API.

Run the tests (local PostgreSQL must be running):

```powershell
python -m pytest -q
```

## Docker

`docker compose up --build` starts the API and PostgreSQL. This is verified by the Docker workflow in GitHub Actions. Docker Desktop does not run on the author's laptop, so it was not run locally.
