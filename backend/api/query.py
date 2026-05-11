"""NL Query endpoint — Agent 6 (Ask Shield AI).

POST /query/  with {"question": "..."}  →  {"sql": "...", "rows": [...], ...}
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.agents.analytics import run as analytics_run
from backend.db import get_db

router = APIRouter()


class QueryRequest(BaseModel):
    question: str


@router.post("/")
def nl_query(req: QueryRequest, db: Session = Depends(get_db)):
    """Translate NL → SQL via Agent 6, execute, return results.

    The response always includes the generated SQL so the user can see exactly
    what's being run — that transparency is part of the governance pitch.
    """
    return analytics_run(db, req.question)
