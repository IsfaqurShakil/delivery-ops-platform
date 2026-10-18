# app/main.py
# The entry point of our API.
from fastapi import FastAPI

app = FastAPI(title="Delivery Operations Platform")


@app.get("/health")
def health():
    # A simple "I am alive" endpoint. Hosting platforms and tests call this.
    return {"status": "ok"}
