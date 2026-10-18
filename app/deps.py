# app/deps.py
# Gives each API request its own database session and closes it afterwards.
from app.db import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
