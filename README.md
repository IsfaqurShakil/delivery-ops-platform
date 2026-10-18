# Delivery Operations Platform

![CI](https://github.com/IsfaqurShakil/delivery-ops-platform/actions/workflows/ci.yml/badge.svg)

When a delivery fails, this backend decides automatically what happens next, assigns riders fairly, and checks that cash-on-delivery money matches.

**Status:** Phase 1 in progress. All data is fake. No real personal data is used.

## Tech stack

- Used now: Python, FastAPI, PostgreSQL, pytest, GitHub Actions
- Planned: SQLAlchemy, Alembic, JWT auth, Postman, Hypothesis, Locust, Playwright, n8n + Telegram

## Run locally (Windows PowerShell)

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    Copy-Item .env.example .env
    python -m uvicorn app.main:app --reload

Then open http://127.0.0.1:8000/docs

## Run the tests

    python -m pytest -v
