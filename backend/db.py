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
    """Create all tables on startup and apply any additive schema patches.

    For fresh databases `create_all` is sufficient.
    For existing databases we also run idempotent ALTER TABLE statements so
    new nullable columns land without a full Alembic migration.
    """
    from backend import models  # noqa: F401 — registers models on Base
    Base.metadata.create_all(bind=engine)
    _patch_schema()
    _seed_default_scoring_policy()
    logger.info("Database tables initialised")


def _patch_schema() -> None:
    """Idempotent DDL patches — safe to run on every startup."""
    if not _is_postgres:
        return  # SQLite handles new columns automatically via create_all
    patches = [
        # decisions.scoring_details — added for hybrid scoring engine
        "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS scoring_details JSONB",
        # scoring_feedback — human reinforcement signals
        """CREATE TABLE IF NOT EXISTS scoring_feedback (
            id              SERIAL PRIMARY KEY,
            contract_id     INTEGER REFERENCES contracts(id),
            decision_id     INTEGER REFERENCES decisions(id),
            feedback_type   VARCHAR(20) NOT NULL,
            ai_decision     VARCHAR(30),
            human_decision  VARCHAR(30),
            composite_score FLOAT,
            notes           TEXT,
            reviewer_role   VARCHAR(100),
            created_at      TIMESTAMP DEFAULT NOW()
        )""",
    ]
    try:
        with engine.begin() as conn:
            for sql in patches:
                conn.execute(text(sql))
        logger.info("Schema patches applied (%d statements)", len(patches))
    except Exception:
        logger.exception("Schema patch failed (non-fatal — existing columns are fine)")


def _seed_default_scoring_policy() -> None:
    """Insert the default scoring policy if no active policy exists yet."""
    try:
        from backend.models import ScoringPolicy
        from backend.agents.scoring import DEFAULT_POLICY
        db = SessionLocal()
        try:
            exists = db.query(ScoringPolicy).filter_by(is_active=True).first()
            if not exists:
                db.add(ScoringPolicy(
                    name="default",
                    is_active=True,
                    config=DEFAULT_POLICY,
                    updated_by="system",
                ))
                db.commit()
                logger.info("Seeded default scoring policy into scoring_policies table")
        finally:
            db.close()
    except Exception:
        logger.exception("Failed to seed default scoring policy (non-fatal)")


def check_db_connection() -> bool:
    """Health check — returns True if the DB is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database connection check failed")
        return False
