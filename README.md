# 🛡 Shield AI

**AI Governance Platform for Enterprise Contract Risk Assessment & Approval.**

Shield AI is an enterprise pipeline that ingests contracts, validates LLM
outputs through multi-agent cross-checks, retrieves relevant policy and prior
contracts via RAG over a multi-source corpus, answers natural-language
analytics queries, detects anomalies in document content, and extracts a
knowledge graph of parties, obligations, and risks — with governance and
security baked in.

---

## Focus area coverage

| Focus area | Where it lives | What we do |
|---|---|---|
| **RAG over proprietary / multi-source data** | `backend/rag/`, `backend/agents/risk.py`, `backend/agents/compliance.py` | FAISS index over past contracts + policy snippets + regulations. Risk Agent retrieves comparable prior clauses; Compliance Agent retrieves framework-relevant policy snippets. Both use `gemini-embedding-001`. |
| **AI-powered data pipelines & validation** | `backend/orchestrator.py`, `backend/agents/security.py`, `backend/lobstertrap.py` | 5-agent pipeline. Two-layer pre-LLM security gate: [Veea Lobster Trap](https://github.com/veeainc/lobstertrap) DPI proxy (primary) + an offline pattern detector (fallback + complement). Both run *before* any Gemini call. Agent 5 (recommendation) is rules-based, never LLM-driven. |
| **Analytics agents for NL querying** | `backend/agents/analytics.py`, `frontend/pages/5_Ask_Shield_AI.py` | Agent 6: Gemini text-to-SQL with multi-layer safety (forbidden keywords, allowed-table whitelist, multi-statement rejection). Generated SQL is shown in the UI for transparency. |
| **Anomaly detection** | `backend/agents/security.py`, `backend/api/dashboard.py` | Prompt-injection detection (13 patterns + zero-width unicode). Risk-score outliers flagged as anomalies on the dashboard. |
| **Knowledge graph extraction** | `backend/graph/builder.py`, `frontend/pages/6_Knowledge_Graph.py` | NetworkX graph of vendors → contracts → risks → frameworks built from extraction outputs. Recurring risks become hub nodes — visual proof of patterns across the corpus. |

---

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌────────────────────┐
│  Streamlit  │─────▶│  FastAPI Backend │─────▶│  Gemini Pro/Flash  │
│  Frontend   │      │                  │      └────────────────────┘
│             │      │  ┌────────────┐  │      ┌────────────────────┐
│  • Upload   │      │  │ Orchestr.  │  │─────▶│  Lobster Trap      │
│  • Review   │      │  └────────────┘  │      │  (offline)         │
│  • Risk DB  │      │  ┌────────────┐  │      └────────────────────┘
│  • Sec DB   │      │  │ 6 Agents   │  │      ┌────────────────────┐
│  • Ask AI   │      │  └────────────┘  │─────▶│  FAISS (in-memory) │
│  • KG view  │      │  ┌────────────┐  │      │  • past contracts  │
│  • Audit    │      │  │ Audit Log  │  │      │  • policy docs     │
└─────────────┘      │  └────────────┘  │      └────────────────────┘
                     └──────────────────┘      ┌────────────────────┐
                              │                │  SQLite            │
                              └───────────────▶│  • contracts       │
                                               │  • agent_outputs   │
                                               │  • decisions       │
                                               │  • security_events │
                                               │  • audit_logs      │
                                               └────────────────────┘
```

The 6 agents:

1. **Document Extraction** — Gemini Flash, structured output (parties, dates, clauses, obligations).
2. **Risk Assessment** — Gemini Flash + RAG (similar prior risks).
3. **Compliance** — Gemini Flash + RAG over policy corpus (HIPAA / SOC2 / GDPR).
4. **Security Governance** — Veea Lobster Trap DPI proxy + offline pattern detector, runs **before** any LLM call.
5. **Approval Recommendation** — rules-based router, **no LLM** — templated rationales.
6. **Analytics ("Ask Shield AI")** — Gemini Flash text-to-SQL over the contracts DB.

---

## Quick start

```bash
# 1. Install Python deps
make install

# 2. Configure secrets
cp .env.example .env
# edit .env with your Gemini API key (free tier works — see notes below)

# 3. (Optional but recommended) Run Lobster Trap locally
#    https://github.com/veeainc/lobstertrap
#    git clone, make build, then in a separate terminal:
./lobstertrap serve     # binds to localhost:8080
# If you skip this, the offline pattern detector still runs.

# 4. Generate the four demo contracts
python scripts/build_demo_contracts.py

# 5. Run backend (terminal 1)
make backend           # http://localhost:8000  ·  docs at /docs

# 6. Run frontend (terminal 2)
make frontend          # http://localhost:8501

# 7. Run the test suite
make test              # 85+ tests, no API calls (LLM/RAG mocked)
```

---

## Repository layout

```
shield-ai/
├── backend/
│   ├── main.py                 # FastAPI entry + lifespan
│   ├── db.py / models.py       # SQLAlchemy + SQLite (5 tables)
│   ├── audit.py                # single source of truth for audit logging
│   ├── orchestrator.py         # chain of agents 1-5 per upload
│   ├── extractors.py           # PDF / DOCX text extraction
│   ├── segmentation.py         # clause regex
│   ├── llm.py / gemini_client.py  # Gemini wrappers + retry/backoff
│   ├── api/                    # FastAPI routers
│   │   ├── contracts.py        # upload, list, detail, decide, audit-report
│   │   ├── query.py            # NL query (Ask Shield AI)
│   │   ├── graph.py            # knowledge graph + hubs
│   │   ├── dashboard.py        # risk + security summaries
│   │   ├── audit_logs.py       # filterable audit log
│   │   └── rag.py              # debug retrieval
│   ├── agents/                 # the 6 AI agents
│   ├── rag/
│   │   ├── embed.py            # gemini-embedding-001 wrapper
│   │   ├── index.py            # FAISS in-memory index
│   │   ├── ingest.py           # corpus → embeddings
│   │   ├── retrieve.py         # query helper
│   │   └── cache.py            # disk cache so restarts cost zero quota
│   ├── graph/builder.py        # NetworkX graph from DB state
│   └── corpus/                 # past contracts, policies, regulations
├── frontend/
│   ├── app.py                  # Streamlit entry + role switcher (RBAC sim)
│   ├── utils.py                # API client + role helpers
│   └── pages/                  # one file per dashboard / workflow page
├── prompts/                    # versioned prompt templates
├── demo_contracts/             # the 3 PDFs used in the demo
├── scripts/build_demo_contracts.py
└── tests/                      # 79 tests, mocked LLM
```

---

## Notes on free-tier Gemini

The defaults in `backend/llm.py` (`gemini-2.5-flash-lite`) are tuned for the
free tier (~30 RPM / ~1500 RPD). The retry-with-backoff in `llm.py` handles
transient rate limits transparently. The embedding cache in `backend/rag/cache.py`
means restarting the backend costs zero quota once the corpus is built.

If you have a paid plan, override either model in `.env`:

```
GEMINI_MODEL_PRO=gemini-2.5-pro
GEMINI_MODEL_FLASH=gemini-2.5-flash
```

---

## Demo

See [`DEMO_RUNBOOK.md`](./DEMO_RUNBOOK.md) for the 5-minute live demo script.
