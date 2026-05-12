"""NL Query endpoint — Ask Shield AI (two modes).

POST /query/   {"question": "..."}
    → analytics mode (text-to-SQL across the whole corpus)

POST /query/   {"question": "...", "contract_id": 42}
    → contract Q&A mode (grounded answer about ONE contract with citations)

Frontend toggles between modes; backend chooses by presence of contract_id.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.agents.analytics import run as analytics_run
from backend.agents.contract_qa import run as contract_qa_run
from backend.db import get_db

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    contract_id: Optional[int] = None


@router.post("/")
def nl_query(req: QueryRequest, db: Session = Depends(get_db)):
    """Route to the right agent based on contract_id.

    Analytics responses include `sql` and `rows`.
    Contract-Q&A responses include `answer`, `cited_clauses`, and `confidence`.
    Both include `mode` so the frontend renders the right thing without
    inferring from the shape.
    """
    if req.contract_id is not None:
        result = contract_qa_run(db, req.contract_id, req.question)
        result["mode"] = "contract_qa"
        return result

    result = analytics_run(db, req.question)
    result["mode"] = "analytics"
    return result
