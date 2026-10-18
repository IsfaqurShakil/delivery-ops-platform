# tests/test_health.py
# First automated tests for the API.
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)  # a fake browser that talks to our app directly, no real server needed


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_404():
    # Negative test: asking for a page that does not exist must fail cleanly
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
