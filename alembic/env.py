# alembic/env.py
# Tells Alembic how to connect to our database and which tables it should know about.
from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (importing this registers our tables in Base.metadata)
from app.db import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata  # Alembic compares this with the real database


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
