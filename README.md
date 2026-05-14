# Shield AI

**AI Governance Platform for Enterprise Contract Risk Assessment & Approval**

Shield AI is a full-stack application that automates the review, risk scoring, compliance checking, and approval routing of enterprise contracts using a multi-agent AI pipeline built on Google Gemini. It enforces a two-layer security gate to block prompt injection attacks before any LLM ever sees a document, and maintains a complete audit trail for every decision.

---

## Table of Contents

- [Objective](#objective)
- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Agent Pipeline](#agent-pipeline)
- [Tech Stack](#tech-stack)
- [File Structure](#file-structure)
- [Frontend Pages](#frontend-pages)
- [Backend API](#backend-api)
- [Database Models](#database-models)
- [Role-Based Access Control](#role-based-access-control)
- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Docker (Local Production Stack)](#docker-local-production-stack)
- [Google Cloud Run Deployment](#google-cloud-run-deployment)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Sample Contracts](#sample-contracts)
- [Makefile Reference](#makefile-reference)

---

## Objective

Enterprise legal teams process hundreds of contracts monthly — NDAs, vendor agreements, employment contracts, data processing addenda — each requiring expert review for risk, compliance violations, and adversarial content. This is slow, expensive, and error-prone.

Shield AI solves this by:

1. **Extracting** structured metadata (parties, dates, clauses, obligations) from raw PDFs
2. **Scoring** contracts against a configurable risk policy
3. **Checking** regulatory compliance (HIPAA, GDPR, PCI-DSS, SOC 2) using RAG over a proprietary policy corpus
4. **Blocking** adversarial documents before they reach any LLM — prompt injection, hidden text, CSS-based attacks
5. **Routing** contracts to the right human reviewer based on risk score
6. **Logging** every agent decision and human action to an immutable audit trail

Contracts that should be auto-approved clear in ~15 seconds. High-risk contracts get routed to the right reviewer with a full AI-generated rationale. Adversarial contracts never reach any AI model.

---

## Key Features

| Feature | Description |
|---|---|
| **Multi-Agent Pipeline** | 5 specialised agents (Classification → Extraction → Risk → Compliance → Approval) running in sequence with structured Pydantic output |
| **Two-Layer Security Gate** | Veea Lobster Trap DPI proxy + offline pattern detector runs before any LLM; quarantines injections, adversarial payloads, and hidden text |
| **RAG** | Gemini `embedding-001` embeddings over past contracts, HIPAA/GDPR/SOC2 policies, and regulatory frameworks; retrieved at risk and compliance agents |
| **Configurable Scoring** | Weighted policy (clause weights, thresholds, framework rejection rules) editable at runtime without code changes |
| **Role-Based Review Queue** | Five roles with separate queues, assignment flow, and commenting — Legal Reviewer and Compliance Officer can assign contracts; Executives and Auditors have read-only access |
| **Ask Shield AI** | Natural language queries answered by Agent 6 (contract Q&A with citations) or Agent 7 (text-to-SQL across the full corpus) |
| **Audit Log** | Every agent call, human decision, upload, and assignment is logged with actor, action, timestamp, and full context |
| **Dashboards** | Live risk dashboard (score distribution, high-risk contracts) and security dashboard (event timeline, quarantine history with reasons) |
| **Sample Data** | 21 synthetic and real-world contracts (SEC filings) with in-browser PDF preview and direct upload to the pipeline |

---

## Architecture Overview

```
Browser (Next.js 16)
        │
        │  HTTPS — same-origin requests only
        ▼
/api/backend/[...path]         Next.js API proxy route (eliminates CORS)
        │
        │  Server-to-server HTTP
        ▼
FastAPI (port 8000)
        │
        ├── Security Gate ──────────────►  Veea Lobster Trap DPI proxy
        │   (runs BEFORE any LLM)           + offline pattern matcher
        │
        ├── Agent Pipeline ─────────────►  Google Gemini 2.5 Flash-Lite
        │   (Orchestrator)                  (1.5 Flash fallback)
        │
        ├── RAG Layer ──────────────────►  Pinecone (vector store, prod)
        │                                   FAISS (in-memory, corpus)
        │
        ├── Storage ────────────────────►  PostgreSQL / Cloud SQL (prod)
        │                                   SQLite (local dev)
        │                                   Google Cloud Storage (files)
        │
        └── Audit Log ──────────────────►  audit_logs table (append-only)
```

---

## Agent Pipeline

Each uploaded contract passes through a sequential pipeline. The Security Gate runs synchronously at upload time; all other agents run in a background task.

| # | Agent | Model | Description |
|---|---|---|---|
| **0** | **Security Gate** | Lobster Trap + regex | Runs first, before any LLM. Scans for prompt injection, hidden text (white-on-white, CSS-invisible), adversarial payloads. Quarantines on match — the LLM never sees the document. |
| **1** | **Classification** | Gemini 2.5 Flash-Lite | Identifies contract type (NDA, Vendor, Employment, DPA, SaaS…), governing jurisdiction, and parties involved. |
| **2** | **Extraction** | Gemini 2.5 Flash-Lite | Structured extraction of all clauses with title, full text, page number, and clause type. RAG retrieves similar past contracts for context. |
| **3** | **Risk Assessment** | Gemini 2.5 Flash-Lite | Scores each clause for risk. Produces an overall risk score 0–100. RAG retrieves prior risk findings. |
| **4** | **Compliance** | Gemini 2.5 Flash-Lite | Checks against HIPAA, GDPR, CCPA, SOC 2, PCI-DSS requirements using RAG over the policy corpus. Returns a violation list with severity. |
| **5** | **Approval Routing** | Rules-based (no LLM) | Converts risk score + compliance violations + scoring policy into a deterministic recommendation: `AUTO_APPROVE`, `MANAGER_REVIEW`, `LEGAL_REVIEW`, or `REJECT`. Writes a templated rationale. |

> **Fallback**: If Gemini 2.5 Flash-Lite is unavailable, agents automatically retry with Gemini 1.5 Flash.

---

## Tech Stack

### Backend
| Component | Technology |
|---|---|
| API framework | FastAPI 0.110+ |
| ORM | SQLAlchemy 2.0 |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL (Cloud SQL) |
| Migrations | Alembic |
| LLM | Google Gemini 2.5 Flash-Lite / 1.5 Flash |
| Embeddings | Gemini `embedding-001` |
| Vector store | Pinecone (production) + FAISS (in-memory) |
| File storage | Google Cloud Storage |
| Security proxy | Veea Lobster Trap |
| PDF parsing | pdfplumber |
| DOCX parsing | python-docx |

### Frontend
| Component | Technology |
|---|---|
| Framework | Next.js 16.2 (App Router) |
| Language | TypeScript 5 |
| Styling | Tailwind CSS 4 |
| Charts | Recharts |
| Icons | Lucide React |
| HTTP | Native `fetch` via Next.js API proxy route |

### Infrastructure
| Component | Technology |
|---|---|
| Containers | Docker |
| CI/CD | Google Cloud Build |
| Hosting | Google Cloud Run |
| Image registry | Google Artifact Registry |
| Secrets | Google Secret Manager |

---

## File Structure

```
Shield-AI/
│
├── backend/                           # FastAPI application
│   ├── main.py                        # App entry point, CORS, lifespan (RAG init)
│   ├── models.py                      # SQLAlchemy ORM models
│   ├── db.py                          # Database session management
│   ├── orchestrator.py                # Agent pipeline runner
│   ├── extractors.py                  # PDF / DOCX text extraction
│   ├── segmentation.py                # Clause regex segmentation
│   ├── llm.py                         # Gemini wrapper with retry / backoff
│   ├── gemini_client.py               # Gemini API client
│   ├── lobstertrap.py                 # Lobster Trap DPI proxy client
│   ├── audit.py                       # Audit log writer (single source of truth)
│   ├── cache.py                       # Embedding cache management
│   ├── logging_config.py              # Daily rotating log setup
│   │
│   ├── api/                           # FastAPI routers (one file per domain)
│   │   ├── contracts.py               # Upload, list, detail, decide, assign, delete
│   │   ├── dashboard.py               # Risk & security summary aggregation
│   │   ├── audit_logs.py              # Filterable, paginated audit log
│   │   ├── query.py                   # Natural language query (Ask Shield AI)
│   │   ├── scoring.py                 # Scoring policy CRUD
│   │   ├── rag.py                     # RAG debug (status, search)
│   │   └── health.py                  # Health check + data recovery
│   │
│   ├── agents/                        # One file per agent
│   │   ├── classifier.py              # Agent 0 – Contract classification
│   │   ├── extraction.py              # Agent 1 – Structured clause extraction
│   │   ├── risk.py                    # Agent 2 – Risk scoring + RAG
│   │   ├── compliance.py              # Agent 3 – Compliance + RAG
│   │   ├── security.py                # Agent 4 – Lobster Trap + offline detector
│   │   ├── recommendation.py          # Agent 5 – Approval routing (rules-based)
│   │   ├── contract_qa.py             # Agent 6 – Q&A with citations
│   │   ├── analytics.py               # Agent 7 – Text-to-SQL
│   │   ├── scoring.py                 # Scoring engine & default policy
│   │   ├── schemas.py                 # Pydantic output schemas for all agents
│   │   ├── registry.py                # Agent registry & metadata
│   │   └── history.py                 # Decision history tracking
│   │
│   ├── rag/                           # Retrieval-Augmented Generation layer
│   │   ├── embed.py                   # Gemini embedding-001 wrapper
│   │   ├── index.py                   # FAISS in-memory indexing
│   │   ├── ingest.py                  # Corpus ingestion pipeline
│   │   ├── retrieve.py                # Query retrieval helper
│   │   └── cache/                     # Persistent embedding cache (disk)
│   │
│   ├── corpus/                        # Read-only reference data (bundled in image)
│   │   ├── past_contracts/            # Anonymised prior contracts for RAG
│   │   ├── policies/                  # HIPAA, SOC 2, GDPR policy snippets
│   │   └── regulations/               # Regulatory framework documents
│   │
│   └── uploads/                       # Uploaded contract files (local dev only)
│
├── frontend-next/                     # Next.js 16 frontend
│   ├── src/
│   │   ├── app/                       # Next.js App Router pages
│   │   │   ├── layout.tsx             # Root layout (Sidebar + main area)
│   │   │   ├── api/backend/
│   │   │   │   └── [...path]/
│   │   │   │       └── route.ts       # Proxy: /api/backend/* → FastAPI
│   │   │   ├── home/page.tsx          # Dashboard home (health, stats, pipeline)
│   │   │   ├── upload/page.tsx        # Upload with real-time pipeline progress
│   │   │   ├── contracts/
│   │   │   │   ├── page.tsx           # Recent uploads (filter, sort, delete)
│   │   │   │   └── [id]/page.tsx      # Contract detail (clauses, risk, decisions)
│   │   │   ├── queue/page.tsx         # Review queue (role-based, assign, comment)
│   │   │   ├── dashboard/
│   │   │   │   ├── risk/page.tsx      # Risk dashboard (score distribution, charts)
│   │   │   │   └── security/page.tsx  # Security dashboard (events, quarantine)
│   │   │   ├── ask/page.tsx           # Ask Shield AI (NL query interface)
│   │   │   ├── audit/page.tsx         # Audit log (filterable, paginated)
│   │   │   ├── scoring/page.tsx       # Scoring policy editor + live simulator
│   │   │   ├── recovery/page.tsx      # Data recovery (health, cache, DB status)
│   │   │   └── samples/page.tsx       # Sample contracts (preview + download)
│   │   │
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx        # Navigation sidebar (all routes)
│   │   │   │   └── Topbar.tsx         # Page header bar
│   │   │   └── ui/
│   │   │       ├── StatusPill.tsx     # Coloured contract status badge
│   │   │       └── ScoreBar.tsx       # Animated risk score bar
│   │   │
│   │   └── lib/
│   │       ├── api.ts                 # Typed API client (all endpoints)
│   │       ├── roles.ts               # Role definitions, permissions, queues
│   │       └── utils.ts               # cn(), fmtDate(), status helpers
│   │
│   ├── public/
│   │   ├── shield-ai-icon.svg         # Two-colour shield logo (SVG)
│   │   └── samples/                   # 21 sample PDFs served as static assets
│   │
│   ├── next.config.ts                 # output: standalone (required for Docker)
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── alembic/                           # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 99733a20d3e2_initial_schema.py
│       └── a1b2c3_add_comments_and_assignments.py
│
├── scripts/
│   ├── dev.py                         # Local dev launcher (uvicorn + Lobster Trap)
│   ├── build_demo_contracts.py        # Generate synthetic test contracts
│   ├── demo_smoke_test.py             # Pipeline regression test
│   └── generate_test_contracts.py     # Bulk synthetic contract generator
│
├── tests/                             # 14 test files, 80+ unit/integration tests
│   ├── conftest.py                    # Fixtures, mocked Gemini client
│   ├── test_extraction.py
│   ├── test_risk_compliance.py
│   ├── test_recommendation.py
│   ├── test_analytics.py
│   ├── test_contract_qa.py
│   ├── test_rag.py
│   ├── test_pipeline.py
│   ├── test_lobstertrap.py
│   ├── test_dashboard.py
│   ├── test_audit_report.py
│   └── test_health.py
│
├── demo_contracts/                    # 21 sample contracts (synthetic + SEC filings)
├── prompts/                           # Versioned LLM prompt templates
├── logs/                              # Runtime logs (daily rotation)
│
├── Dockerfile                         # Backend image (Python 3.11, Cloud Run)
├── frontend-next.Dockerfile           # Next.js image (multi-stage Alpine, Cloud Run)
├── lobstertrap.Dockerfile             # Lobster Trap DPI proxy image
├── frontend.Dockerfile                # Legacy Streamlit image (deprecated)
├── docker-compose.yml                 # Local 3-container stack
│
├── cloudbuild.yaml                    # Cloud Build CI/CD pipeline
├── cloudrun-backend.yaml              # Cloud Run backend service manifest
├── cloudrun-frontend.yaml             # Cloud Run frontend service manifest
├── Makefile                           # All build / dev / deploy targets
├── requirements.txt                   # Python dependencies
├── alembic.ini                        # Alembic configuration
└── .env.example                       # Environment variable template
```

---

## Frontend Pages

| Route | Page | Description |
|---|---|---|
| `/home` | Home | System health (PostgreSQL, Pinecone, Security Gate), live stats, pipeline overview |
| `/upload` | Upload | Drag-and-drop PDF upload with real-time agent progress tracker |
| `/contracts` | Recent Uploads | Filterable / sortable contract table with status chips and delete |
| `/contracts/[id]` | Contract Detail | Full clause list, risk breakdown, agent outputs, decision history |
| `/queue` | Review Queue | Role-gated review queue with assignment, commenting, and approve/reject |
| `/dashboard/risk` | Risk Dashboard | Score distribution chart, high-risk contracts, status breakdown |
| `/dashboard/security` | Security Dashboard | Security event timeline, threat type breakdown, quarantine history with reasons |
| `/ask` | Ask Shield AI | Natural language query — contract Q&A or corpus-wide analytics |
| `/audit` | Audit Log | Filterable, paginated audit trail of every action |
| `/scoring` | Scoring Policy | Live policy editor (weights, thresholds, rejection rules) + risk simulator |
| `/recovery` | Data Recovery | System health details, cache flush, database status |
| `/samples` | Sample Data | 21 sample contracts with in-browser PDF preview, download, and upload-to-pipeline |

---

## Backend API

All endpoints served at `http://localhost:8000`. Interactive docs at `/docs`.

### Contracts — `/contracts`

| Method | Path | Description |
|---|---|---|
| `POST` | `/contracts/upload` | Upload a single PDF/DOCX; triggers the 5-agent pipeline |
| `POST` | `/contracts/bulk-upload` | Upload multiple files in one request |
| `GET` | `/contracts/` | List contracts (filter by status, paginated) |
| `GET` | `/contracts/{id}` | Full contract detail with agent outputs and decisions |
| `POST` | `/contracts/{id}/decide` | Submit a human approve/reject decision |
| `POST` | `/contracts/{id}/assign` | Assign to another role (Legal Reviewer / Compliance Officer only) |
| `POST` | `/contracts/{id}/comment` | Post a comment on a contract |
| `DELETE` | `/contracts/{id}` | Delete contract + clauses + Pinecone vectors + GCS file |

### Dashboard — `/dashboard`

| Method | Path | Description |
|---|---|---|
| `GET` | `/dashboard/risk-summary` | Risk score distribution, high-risk list, status counts |
| `GET` | `/dashboard/security-summary` | Security event counts, threat breakdown, quarantine stats |

### Query — `/query`

| Method | Path | Description |
|---|---|---|
| `POST` | `/query/` | NL query — routes to contract Q&A (with `contract_id`) or text-to-SQL (without) |

### Scoring Policy — `/scoring-policy`

| Method | Path | Description |
|---|---|---|
| `GET` | `/scoring-policy/` | Current active policy with metadata |
| `PUT` | `/scoring-policy/` | Replace active policy |
| `GET` | `/scoring-policy/history` | All historical policy versions |
| `GET` | `/scoring-policy/defaults` | The built-in default policy constant |

### Audit Log — `/audit-logs`

| Method | Path | Description |
|---|---|---|
| `GET` | `/audit-logs/` | Filterable, paginated audit log (actor, action, contract_id, date range) |

### Health & Recovery — `/health`

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Database, Pinecone, Lobster Trap, and cache status |
| `POST` | `/health/flush-cache` | Clear the embedding cache |

### RAG Debug — `/rag`

| Method | Path | Description |
|---|---|---|
| `GET` | `/rag/status` | Loaded indices and entry counts |
| `GET` | `/rag/search?q=...` | Top-k retrieval results with scores |

---

## Database Models

| Table | Description |
|---|---|
| `contracts` | Core contract record — filename, status, raw text, clauses (JSON array), GCS URI, file hash |
| `agent_outputs` | One row per agent per contract — agent name, structured JSON output, confidence, prompt hash |
| `decisions` | AI recommendations and human decisions — recommendation type, reasoning, reviewer role, scoring details |
| `security_events` | Lobster Trap findings — event type, details object (matched text, source, description), severity |
| `audit_logs` | Immutable append-only log — actor, action, contract_id, details (JSON), timestamp |
| `scoring_policies` | Versioned scoring policy records with weights, thresholds, and framework rejection rules |
| `contract_comments` | Comments left by any role on a contract |
| `contract_assignments` | Role-to-role assignment records with notes and can_approve flag |

---

## Role-Based Access Control

Five roles control which contracts appear in the Review Queue and what actions each user can take.

| Role | Queue Statuses Visible | Can Approve | Can Assign | Notes |
|---|---|---|---|---|
| **Procurement Analyst** | `uploaded`, `processing` | — | — | Upload only |
| **Legal Reviewer** | `legal_review` | ✓ | ✓ | Can assign to any role |
| **Compliance Officer** | `manager_review` | ✓ | ✓ | Can assign to any role |
| **Executive** | `manager_review`, `legal_review` | — | — | Read-only + commenting |
| **Auditor** | `manager_review`, `legal_review` | — | — | Read-only + commenting |

Role is selected from a dropdown in the Review Queue page header. No authentication is implemented — this is a simulation.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 works; 3.10 is untested |
| Node.js | 20+ | For the Next.js frontend |
| npm | 9+ | Bundled with Node 20 |
| Docker Desktop | Latest | For the local container stack |
| Google Gemini API key | — | [Get one free](https://aistudio.google.com/app/apikey) |
| Pinecone account | Free tier | Create an index: metric `cosine`, dimensions `3072` |
| Google Cloud account | — | For GCS file storage and Cloud Run deployment |

---

## Local Development Setup

### 1. Clone and configure

```bash
git clone https://github.com/yashasgowda11/Shield-AI.git
cd Shield-AI

cp .env.example .env
# Open .env and fill in:
#   GEMINI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME
#   GCS_BUCKET_NAME (optional for local dev)
#   DATABASE_URL (leave unset to use local SQLite)
```

### 2. Backend

```bash
# Create and activate a virtual environment
python3.11 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# Install all Python dependencies
pip install -r requirements.txt

# Initialise the database and run all migrations
alembic upgrade head

# Start the backend API server (port 8000)
make backend-only
# Or start with Lobster Trap DPI proxy: make backend
```

The API is now live at `http://localhost:8000`.
Interactive Swagger docs: `http://localhost:8000/docs`

### 3. Frontend

Open a second terminal:

```bash
cd frontend-next
npm install
npm run dev
```

The frontend is live at `http://localhost:3000`.

> All API calls go through the Next.js proxy route at `/api/backend/*` → `http://localhost:8000`. No CORS configuration is needed.

### 4. Verify everything is running

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "db": { "connected": true },
  "pinecone": { "available": true },
  "lobstertrap": { "reachable": false },
  "cache_pending": 0
}
```

Then open `http://localhost:3000/home` to see the live health indicators.

---

## Docker (Local Production Stack)

Runs the backend and Lobster Trap in containers with persistent volumes. Run the frontend with `npm run dev` for hot-reload.

```bash
# Build all images
make docker-build

# Start the stack (requires a populated .env)
make docker-up

# Watch combined logs
make docker-logs

# Stop and remove containers
make docker-down
```

| Service | Host Port | URL |
|---|---|---|
| Backend API | 8000 | http://localhost:8000 |
| Lobster Trap | 8080 | http://localhost:8080/_lobstertrap/ |

Then start the frontend in a separate terminal:

```bash
cd frontend-next && npm run dev    # http://localhost:3000
```

Persistent data is stored in three named Docker volumes:

| Volume | Contents |
|---|---|
| `shield_data` | SQLite database |
| `shield_uploads` | Uploaded PDF files |
| `shield_rag_cache` | Embedding cache |

---

## Google Cloud Run Deployment

The full production stack runs three Cloud Run services: `shield-backend`, `shield-frontend`, and `shield-lobstertrap`.

### One-time setup

```bash
# Log in and set the project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable APIs, create Artifact Registry repo, grant IAM roles
make gcp-setup

# Push all secrets from .env to Secret Manager
make gcp-secrets
```

### Manual deploy

```bash
# Authenticate Docker with Artifact Registry
make gcp-auth

# Build all images for linux/amd64 (required — Cloud Run does not support arm64)
make gcp-build

# Push to Artifact Registry
make gcp-push

# Run database migrations as a Cloud Run Job
make gcp-migrate

# Deploy each service
make gcp-deploy-lobstertrap
make gcp-deploy-backend
make gcp-deploy-frontend

# Or run the full pipeline in one command:
make gcp-deploy
```

### Automatic CI/CD on push

Cloud Build triggers on push to `main` or `testing`. Backend and frontend images are built in parallel.

```bash
# Create the GitHub trigger (one-time)
gcloud builds triggers create github \
  --repo-name=Shield-AI \
  --repo-owner=yashasgowda11 \
  --branch-pattern="^(main|testing)$" \
  --build-config=cloudbuild.yaml
```

### Cloud Run services

| Service | Memory | Concurrency | Notes |
|---|---|---|---|
| `shield-backend` | 1 Gi | 10 | FastAPI + all agents + RAG |
| `shield-frontend` | 512 Mi | 80 | Next.js standalone — proxies API calls server-side |
| `shield-lobstertrap` | 512 Mi | 20 | DPI proxy — internal only |

The `BACKEND_URL` env var is injected into the frontend container at deploy time. The browser never calls the backend directly — all API traffic goes through the Next.js server-side proxy, so no CORS configuration is needed on the backend.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. Never commit `.env`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | ✓ | — | Google AI Studio API key. [Get one free.](https://aistudio.google.com/app/apikey) |
| `DATABASE_URL` | Prod only | `sqlite:///./shield.db` | SQLAlchemy connection string. SQLite for local dev; PostgreSQL for production. |
| `PINECONE_API_KEY` | ✓ | — | Pinecone API key |
| `PINECONE_INDEX_NAME` | ✓ | — | Name of your Pinecone index (metric: `cosine`, dimensions: `3072`) |
| `GCS_BUCKET_NAME` | Prod only | — | GCS bucket for uploaded contracts |
| `GCS_SERVICE_ACCOUNT_KEY` | Local only | — | Path to GCS service account JSON key. Not needed on Cloud Run (uses Workload Identity). |
| `BACKEND_URL` | Frontend | `http://localhost:8000` | Backend URL used by the Next.js proxy route. Set as a Cloud Run env var in production. |
| `LOBSTERTRAP_URL` | Optional | `http://localhost:8080` | Lobster Trap DPI proxy URL. Falls back to offline pattern detection if unreachable. |
| `LOBSTERTRAP_TIMEOUT_SEC` | Optional | `5` | Timeout in seconds for Lobster Trap requests |
| `SKIP_RAG_INIT` | Optional | `false` | Set to `true` to skip corpus embedding on startup (faster iteration) |
| `SHIELD_LOG_LEVEL` | Optional | `INFO` | Root log level: `DEBUG`, `INFO`, or `WARNING` |
| `ALLOWED_ORIGINS` | Optional | `*` | Comma-separated CORS origins. Defaults to wildcard. Set explicitly in production. |

---

## Running Tests

```bash
# Activate your virtual environment first
source venv/bin/activate

# Run the full test suite
make test
# or: pytest tests/ -v

# Run a specific test file
pytest tests/test_pipeline.py -v

# Run pipeline regression against demo contracts (requires backend running on :8000)
make demo-test
```

The test suite uses a mocked Gemini client defined in `conftest.py`, so all tests run without real API calls. Coverage includes all agents, the RAG layer, dashboard aggregation, audit logging, and health endpoints.

---

## Sample Contracts

21 ready-to-use contracts are available in `demo_contracts/` and served statically from the **Sample Data** page (`/samples`). Each has in-browser PDF preview, direct download, and a one-click link to upload it through the pipeline.

| Category | Count | What it tests |
|---|---|---|
| **Security Threats** | 2 | CSS hidden injection, white-on-white prompt injection |
| **High Risk** | 5 | Zero liability cap, missing HIPAA BAA, aggressive non-compete, heavy IP assignment, risky vendor |
| **Medium Risk** | 5 | Standard procurement, contradictory clauses, expired termination date, multi-party (4 parties), moderate vendor |
| **Low Risk / Clean** | 4 | Clean NDA, SaaS standard, PCI-DSS finance, GDPR & CCPA dual DPA |
| **Real-World (SEC filings)** | 5 | NETGEAR distributor amendment, Scansource distributor agreement, Martin Midstream transport services, Entertainment Gaming Asia distributor, Energy Transportation agreement |

---

## Makefile Reference

```
make install                Install Python dependencies
make backend                Run full dev stack (uvicorn + Lobster Trap)
make backend-only           Run uvicorn only (port 8000)
make frontend               Run Next.js dev server (port 3000)
make test                   Run pytest suite
make demo-test              Pipeline regression test against demo contracts
make clean                  Delete shield.db and caches

make docker-build           Build all Docker images
make docker-up              Start the 3-container stack
make docker-down            Stop the stack
make docker-logs            Tail combined logs
make docker-rebuild         Rebuild images and restart containers
make docker-status          Show container status

make gcp-setup              One-time GCP API + IAM setup
make gcp-secrets            Push .env secrets to Secret Manager
make gcp-auth               Configure Docker for Artifact Registry
make gcp-build              Build linux/amd64 images for Cloud Run
make gcp-push               Push images to Artifact Registry
make gcp-migrate            Run Alembic migrations as a Cloud Run Job
make gcp-deploy-lobstertrap Deploy Lobster Trap to Cloud Run
make gcp-deploy-backend     Deploy backend to Cloud Run
make gcp-deploy-frontend    Deploy Next.js frontend to Cloud Run
make gcp-deploy             Full pipeline: build → push → migrate → deploy all
make gcp-logs-backend       Tail backend Cloud Run logs
make gcp-logs-frontend      Tail frontend Cloud Run logs
```
