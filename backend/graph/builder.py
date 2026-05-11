"""NetworkX knowledge graph builder.

Builds a directed graph from current DB state:

  Vendor   --signed-->     Contract
  Contract --flagged-->    Risk            (one Risk node per unique risk label,
                                            so the same risk appearing across
                                            contracts collapses to a single hub)
  Contract --checked-->    Framework       (with passed=true|false on the edge)

Uses agent outputs that are already in the DB — no LLM calls. The same risk
label appearing in N contracts becomes a hub node, which is the visual story
the demo wants to tell.
"""
import logging
from typing import Any

import networkx as nx
from sqlalchemy.orm import Session

from backend.models import AgentOutput, Contract

logger = logging.getLogger(__name__)


# Severity ranking so we can compute max-severity per risk node
_SEVERITY_RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _latest_output(db: Session, contract_id: int, agent_name: str) -> dict | None:
    row = (
        db.query(AgentOutput)
        .filter_by(contract_id=contract_id, agent_name=agent_name)
        .order_by(AgentOutput.created_at.desc())
        .first()
    )
    return row.output if row else None


def _vendor_name(extraction: dict | None) -> str | None:
    if not extraction:
        return None
    parties = extraction.get("parties") or []
    for p in parties:
        if (p.get("role") or "").lower() == "vendor":
            return p.get("name")
    if parties:
        return parties[0].get("name")
    return None


def _max_severity(a: str | None, b: str | None) -> str:
    if not a:
        return b or "Low"
    if not b:
        return a
    return a if _SEVERITY_RANK.get(a, 0) >= _SEVERITY_RANK.get(b, 0) else b


def build(db: Session) -> nx.MultiDiGraph:
    """Construct the full knowledge graph from current DB state."""
    g: nx.MultiDiGraph = nx.MultiDiGraph()

    contracts = db.query(Contract).all()

    for c in contracts:
        contract_node = f"contract:{c.id}"
        ext = _latest_output(db, c.id, "extraction")
        risk = _latest_output(db, c.id, "risk")
        compliance = _latest_output(db, c.id, "compliance")

        g.add_node(
            contract_node,
            type="contract",
            label=c.filename,
            status=c.status,
            risk_score=(risk or {}).get("score"),
            uploaded_at=c.uploaded_at.isoformat() if c.uploaded_at else None,
        )

        # Vendor node + edge
        vendor = _vendor_name(ext)
        if vendor:
            vendor_node = f"vendor:{vendor}"
            if vendor_node not in g:
                g.add_node(vendor_node, type="vendor", label=vendor)
            g.add_edge(vendor_node, contract_node, type="signed")

        # Risk nodes + edges
        for f in (risk or {}).get("findings", []) or []:
            risk_label = f.get("risk") or "(unknown)"
            risk_node = f"risk:{risk_label}"
            if risk_node not in g:
                g.add_node(
                    risk_node,
                    type="risk",
                    label=risk_label,
                    max_severity=f.get("severity"),
                    occurrences=0,
                )
            else:
                g.nodes[risk_node]["max_severity"] = _max_severity(
                    g.nodes[risk_node].get("max_severity"),
                    f.get("severity"),
                )
            g.nodes[risk_node]["occurrences"] += 1
            g.add_edge(
                contract_node, risk_node,
                type="flagged",
                severity=f.get("severity"),
                clause_ref=f.get("clause_ref"),
            )

        # Framework nodes + edges
        for fw in (compliance or {}).get("frameworks", []) or []:
            fw_name = fw.get("framework") or "(unknown)"
            fw_node = f"framework:{fw_name}"
            if fw_node not in g:
                g.add_node(fw_node, type="framework", label=fw_name)
            g.add_edge(
                contract_node, fw_node,
                type="checked",
                passed=bool(fw.get("passed")),
            )

    logger.info(
        "Built knowledge graph: %d nodes, %d edges",
        g.number_of_nodes(), g.number_of_edges(),
    )
    return g


def to_payload(g: nx.MultiDiGraph) -> dict[str, Any]:
    """Convert NetworkX graph to {nodes, edges, stats} JSON for the frontend."""
    nodes = [
        {"id": n, **g.nodes[n]}
        for n in g.nodes
    ]
    edges = [
        {"source": u, "target": v, **data}
        for u, v, data in g.edges(data=True)
    ]

    by_type: dict[str, int] = {}
    for n in g.nodes:
        t = g.nodes[n].get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "n_nodes": g.number_of_nodes(),
            "n_edges": g.number_of_edges(),
            "by_type": by_type,
        },
    }


def hub_summary(g: nx.MultiDiGraph, top_n: int = 5) -> dict[str, list[dict]]:
    """Identify the most-connected nodes — the "hubs" the dashboard surfaces.

    Returns:
      top_vendors: most contracts signed
      top_risks:   risk labels appearing in the most contracts (graph hubs)
      top_frameworks: frameworks checked across the most contracts
    """
    top_vendors = sorted(
        [
            {
                "vendor": g.nodes[n]["label"],
                "n_contracts": g.out_degree(n),
            }
            for n in g.nodes
            if g.nodes[n].get("type") == "vendor"
        ],
        key=lambda x: x["n_contracts"],
        reverse=True,
    )[:top_n]

    top_risks = sorted(
        [
            {
                "risk": g.nodes[n]["label"],
                "occurrences": g.in_degree(n),
                "max_severity": g.nodes[n].get("max_severity", "Low"),
            }
            for n in g.nodes
            if g.nodes[n].get("type") == "risk"
        ],
        key=lambda x: (
            _SEVERITY_RANK.get(x["max_severity"], 0),
            x["occurrences"],
        ),
        reverse=True,
    )[:top_n]

    top_frameworks = sorted(
        [
            {
                "framework": g.nodes[n]["label"],
                "n_checks": g.in_degree(n),
            }
            for n in g.nodes
            if g.nodes[n].get("type") == "framework"
        ],
        key=lambda x: x["n_checks"],
        reverse=True,
    )[:top_n]

    return {
        "top_vendors": top_vendors,
        "top_risks": top_risks,
        "top_frameworks": top_frameworks,
    }
