# app/db.py
# Creates the database connection (engine), the session factory, and the Base class for our tables.
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings

settings = Settings()

# The engine is the connection manager. It does not connect until we actually run a query.
engine = create_engine(settings.database_url)

# A session is one "conversation" with the database. We open one per request later.
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    # Every table class (Shipment, Rider...) will inherit from this.
    pass
