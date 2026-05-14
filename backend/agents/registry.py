"""Centralized agent registry — single source of truth for numbered agent names.

Every agent has:
  number       : Display number shown in the UI and reports
  name         : Internal DB key (agent_name column in agent_outputs)
  display_name : Full human-readable label used in UI headers and audit reports
  emoji        : Icon for the pipeline stage
  protected_by : Which security layers guard this agent's input

Lobster Trap (Agent 4) is the *primary* security layer. It gates the input
before Agents 1, 2, 3, 5, 6, and 7 ever see untrusted content. The offline
pattern detector is a belt-and-suspenders fallback that always runs.

Usage:
    from backend.agents.registry import AGENTS, agent_display

    label = agent_display("risk")          # "Agent 2 — Risk Assessment"
    info  = AGENTS["analytics"]            # full dict
"""

from typing import TypedDict


class AgentInfo(TypedDict):
    number: int
    name: str
    display_name: str
    emoji: str
    description: str


AGENTS: dict[str, AgentInfo] = {
    "extraction": {
        "number": 1,
        "name": "extraction",
        "display_name": "Agent 1 — Document Extraction",
        "emoji": "🔍",
        "description": "Parses parties, dates, obligations, and clause structure from raw contract text.",
    },
    "risk": {
        "number": 2,
        "name": "risk",
        "display_name": "Agent 2 — Risk Assessment",
        "emoji": "⚠️",
        "description": "Scores clause-level risk (0-100) and surfaces material risk findings.",
    },
    "compliance": {
        "number": 3,
        "name": "compliance",
        "display_name": "Agent 3 — Compliance Check",
        "emoji": "📋",
        "description": "Verifies HIPAA, GDPR, SOC 2 and other regulatory framework requirements.",
    },
    "security": {
        "number": 4,
        "name": "security",
        "display_name": "Agent 4 — Security Gate (Lobster Trap)",
        "emoji": "🪤",
        "description": (
            "PRIMARY security layer. Lobster Trap DPI proxy inspects every contract "
            "and every user query for prompt injection, credential leaks, data "
            "exfiltration, role impersonation, and policy bypass attempts. "
            "Runs BEFORE any LLM is called. Falls back to offline pattern detector "
            "when Lobster Trap is unreachable."
        ),
    },
    "recommendation": {
        "number": 5,
        "name": "recommendation",
        "display_name": "Agent 5 — Approval Recommendation",
        "emoji": "🎯",
        "description": "Rules-based (no LLM) recommendation: AUTO_APPROVE / MANAGER_REVIEW / LEGAL_REVIEW / REJECT.",
    },
    "analytics": {
        "number": 6,
        "name": "analytics",
        "display_name": "Agent 6 — Analytics (NL→SQL)",
        "emoji": "📊",
        "description": "Translates natural-language questions about the contracts corpus into safe, read-only SQL.",
    },
    "contract_qa": {
        "number": 7,
        "name": "contract_qa",
        "display_name": "Agent 7 — Contract Q&A",
        "emoji": "❓",
        "description": "Answers NL questions about ONE contract, grounded in its extracted clauses with citations.",
    },
}

# Ordered list for display (by agent number)
AGENTS_ORDERED: list[AgentInfo] = sorted(AGENTS.values(), key=lambda a: a["number"])


def agent_display(name: str) -> str:
    """Return 'Agent N — Display Name' for any internal agent name.

    Falls back gracefully if the name is not registered.
    """
    info = AGENTS.get(name)
    if info:
        return info["display_name"]
    return name


def agent_emoji(name: str) -> str:
    """Return the emoji for a given agent name."""
    return AGENTS.get(name, {}).get("emoji", "🤖")
