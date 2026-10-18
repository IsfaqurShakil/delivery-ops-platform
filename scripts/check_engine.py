# scripts/check_engine.py
# Quick check: does our SQLAlchemy engine connect using the settings from .env?
from sqlalchemy import text

from app.db import engine

with engine.connect() as conn:
    print(conn.execute(text("SELECT current_user, current_database()")).one())
print("Engine OK")
