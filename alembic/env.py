import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from alembic import context

# Load .env so DATABASE_URL is available when running alembic locally
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read DATABASE_URL directly from env — avoids ConfigParser % interpolation
# issues when the password contains URL-encoded characters like %5B, %26 etc.
database_url = os.getenv("DATABASE_URL", "sqlite:///./shield.db")

# Import all models so Alembic autogenerate can detect schema changes
from backend.db import Base   # noqa: E402
import backend.models         # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection.

    Creates the engine directly from DATABASE_URL instead of going through
    alembic.ini / ConfigParser — this avoids ValueError on passwords that
    contain % characters (URL-encoded special chars like %5B, %26, %2A).
    """
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
