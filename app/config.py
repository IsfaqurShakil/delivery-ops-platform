# app/config.py
# Reads settings (database host, user, password...) from the .env file.
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    # DB_HOST in .env becomes db_host here (upper/lower case does not matter)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "delivery_ops"
    db_user: str = "delivery_app"
    db_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> URL:
        # URL.create handles special characters in the password safely
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
