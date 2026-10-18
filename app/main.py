# app/main.py
# The entry point of our API.
from fastapi import FastAPI

from app.routes import router as shipments_router

app = FastAPI(title="Delivery Operations Platform")
app.include_router(shipments_router)


@app.get("/health")
def health():
    # A simple "I am alive" endpoint. Hosting platforms and tests call this.
    return {"status": "ok"}
