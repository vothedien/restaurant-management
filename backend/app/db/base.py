from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

DATABASE_SCHEMA = "restaurant_ai"


class Base(DeclarativeBase):
    """Base for existing tables in the shared `restaurant_ai` schema."""

    metadata = MetaData(schema=DATABASE_SCHEMA)
