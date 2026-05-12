"""Database setup.

Supports both SQLite (local dev fallback) and PostgreSQL (Cloud SQL production).
Switch between them by changing DATABASE_URL in .env:

  SQLite   : DATABASE_URL=sqlite:///./shield.db
  PostgreSQL: DATABASE_URL=postgresql://user:pass@host/dbname

Connection pooling is enabled for PostgreSQL only. SQLite uses the
check_same_thread=False workaround required by FastAPI's threading model.
"""
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shield.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_postgres = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")


def _build_engine():
    if _is_sqlite:
        logger.info("Database: SQLite (local dev)")
        return create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )

    if _is_postgres:
        logger.info("Database: PostgreSQL")
        return create_engine(
            DATABASE_URL,
            # Pool settings tuned for Cloud Run (each instance is single-process)
            pool_size=5,           # maintain up to 5 persistent connections
            max_overflow=10,       # allow up to 10 extra connections under load
            pool_timeout=30,       # wait up to 30s for a connection from pool
            pool_recycle=1800,     # recycle connections every 30 min (avoids stale)
            pool_pre_ping=True,    # test connection health before using it
        )

    # Generic fallback for any other DB URL
    logger.warning("Unrecognised DATABASE_URL scheme — using default engine settings")
    return create_engine(DATABASE_URL)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables on startup.

    For SQLite / fresh PostgreSQL databases this is sufficient.
    For existing PostgreSQL databases use Alembic migrations instead:
        alembic upgrade head
    """
    from backend import models  # noqa: F401 — registers models on Base
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialised")


def check_db_connection() -> bool:
    """Health check — returns True if the DB is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database connection check failed")
        return False
