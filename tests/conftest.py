"""Pytest config — isolates tests from the dev DB.

Sets DATABASE_URL to a temp file BEFORE backend modules import, then
recreates schema between tests so each test starts fresh.
"""
import os
import tempfile

# Must run before any backend.* import
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "shield_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from backend.db import Base, engine  # noqa: E402


@pytest.fixture(autouse=True, scope="function")
def clean_db():
    """Drop + recreate all tables before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True, scope="function")
def _disable_upload_pipeline(monkeypatch):
    """Block the upload endpoint from auto-running the real agent pipeline
    (which would hit Gemini and burn API quota on every test).

    Tests that specifically want to exercise the orchestrator should import
    and call `backend.orchestrator.run_pipeline` directly with mocked agents
    (see test_extraction.py)."""
    def _noop(db, contract_id):
        return {"contract_id": contract_id, "ran": [], "test_mode": True}
    monkeypatch.setattr("backend.api.contracts.run_pipeline", _noop)


@pytest.fixture(autouse=True, scope="function")
def _stub_lobstertrap(monkeypatch):
    """Stub Lobster Trap as 'unavailable' for all tests by default.

    Specific tests that want to verify the Lobster Trap path can override
    this with their own monkeypatch."""
    monkeypatch.setattr("backend.agents.security.lobstertrap.scan",
                        lambda text, **kwargs: None)
