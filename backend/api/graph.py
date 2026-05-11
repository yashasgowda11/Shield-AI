"""Knowledge graph endpoint.

  GET /graph        → full graph payload (nodes + edges + stats)
  GET /graph/hubs   → top vendors / risks / frameworks (for dashboard cards)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.graph.builder import build, hub_summary, to_payload

router = APIRouter()


@router.get("/")
def get_graph(
    node_types: str | None = Query(
        None,
        description="Comma-separated node types to include (vendor,contract,risk,framework). Default: all.",
    ),
    min_severity: str | None = Query(
        None,
        description="Filter risk nodes to those at or above this severity (Low|Medium|High|Critical).",
    ),
    db: Session = Depends(get_db),
):
    """Return the full knowledge graph as nodes + edges + stats."""
    g = build(db)

    # Apply filters by removing nodes not requested. Edges to/from removed nodes
    # disappear automatically.
    if node_types:
        wanted = {t.strip() for t in node_types.split(",")}
        for n in list(g.nodes):
            if g.nodes[n].get("type") not in wanted:
                g.remove_node(n)

    if min_severity:
        from backend.graph.builder import _SEVERITY_RANK
        threshold = _SEVERITY_RANK.get(min_severity, 0)
        for n in list(g.nodes):
            if g.nodes[n].get("type") == "risk":
                sev = g.nodes[n].get("max_severity", "Low")
                if _SEVERITY_RANK.get(sev, 0) < threshold:
                    g.remove_node(n)

    return to_payload(g)


@router.get("/hubs")
def get_hubs(
    top_n: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Top vendors / risks / frameworks for dashboard surfacing."""
    g = build(db)
    return hub_summary(g, top_n=top_n)
