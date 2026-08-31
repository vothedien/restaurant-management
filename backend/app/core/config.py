from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or `backend/.env`."""

    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    database_schema: str = Field(default="restaurant_ai", validation_alias="DATABASE_SCHEMA")
    app_name: str = Field(default="Restaurant Management API", validation_alias="APP_NAME")
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    frontend_url: str = Field(default="http://localhost:5173", validation_alias="FRONTEND_URL")
    jwt_secret_key: str | None = Field(default=None, validation_alias="JWT_SECRET_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
