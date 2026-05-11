# Shield AI — Deployment Guide

This document covers running the full stack — backend, frontend, and
Lobster Trap — outside of your laptop.

---

## Architecture

```
                       ┌─────────────────────┐
                  ┌───▶│  Streamlit (8501)   │  ← end users
                  │    └──────────┬──────────┘
                  │               │
  Internet ──────┤                ▼
                  │    ┌─────────────────────┐
                  └───▶│   FastAPI (8000)    │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │ Lobster Trap (8080) │ ← internal only in prod
                       └─────────────────────┘

                       ┌─────────────────────┐
                       │  Persistent volumes │
                       │  • shield_data      │  ← SQLite DB
                       │  • shield_uploads   │  ← uploaded PDFs
                       │  • shield_rag_cache │  ← embedding cache
                       └─────────────────────┘
```

The backend talks to Lobster Trap via the internal hostname `lobstertrap:8080`
(set by `LOBSTERTRAP_URL`). The frontend talks to the backend via
`backend:8000`. None of those hostnames need to be publicly resolvable.

---

## Local container run

The fastest way to verify the full stack works in containers:

```bash
cd /path/to/shield-ai
cp .env.example .env       # fill in GEMINI_API_KEY
docker compose up --build  # builds all three images, runs the stack
```

Then:
- Frontend: http://localhost:8501
- Backend docs: http://localhost:8000/docs
- Lobster Trap dashboard: http://localhost:8080/_lobstertrap/

`docker compose down` stops everything. Volumes persist so your DB and
embedding cache survive restarts. `docker compose down -v` wipes the volumes
too.

---

## Production hosting — recommended options

All three options support multi-container Docker stacks. Pick based on price
and how much infra you want to manage.

### 1. Fly.io  (recommended for hackathon-grade deploys)

Most developer-friendly. Free tier covers small apps. Each Compose service
becomes a separate Fly app.

```bash
brew install flyctl
flyctl auth signup

# One-time per service
flyctl launch --dockerfile Dockerfile --name shield-backend
flyctl launch --dockerfile frontend.Dockerfile --name shield-frontend
flyctl launch --dockerfile lobstertrap.Dockerfile --name shield-lobstertrap

# Set secrets per app
flyctl secrets set GEMINI_API_KEY=AIza... -a shield-backend
flyctl secrets set LOBSTERTRAP_URL=https://shield-lobstertrap.internal:8080 -a shield-backend
flyctl secrets set BACKEND_URL=https://shield-backend.fly.dev -a shield-frontend

# Volumes for backend persistence
flyctl volumes create shield_data --size 1 -a shield-backend

flyctl deploy -a shield-lobstertrap
flyctl deploy -a shield-backend
flyctl deploy -a shield-frontend
```

Internal networking (`.internal` hostnames) keeps Lobster Trap private —
only your backend can reach it. Public traffic only hits the frontend.

### 2. Render.com

Each service is a "Web Service" or "Private Service":

- `shield-frontend` → Web Service, exposed publicly
- `shield-backend`  → Web Service, exposed publicly (or Private Service if you only want UI to reach it)
- `shield-lobstertrap` → **Private Service** (internal-only)
- Add a **Disk** to the backend service mounted at `/data` for SQLite persistence

Render auto-detects Dockerfiles. Set env vars (`GEMINI_API_KEY`, `LOBSTERTRAP_URL=http://shield-lobstertrap:8080`) in each service's dashboard.

### 3. Single VM (DigitalOcean / EC2 / GCP Compute)

If you want one machine handling everything:

```bash
# On the VM, after Docker + Docker Compose are installed
git clone <your-repo>
cd shield-ai
cp .env.example .env  # add GEMINI_API_KEY
docker compose up -d --build

# Reverse proxy (nginx) in front of port 8501 + 8000
# Lobster Trap stays on localhost:8080, not exposed
```

Cheapest at scale (one $6/mo droplet), most operational work
(SSL, updates, monitoring).

---

## Critical production considerations

### Secrets

`GEMINI_API_KEY` must NEVER be in the image. Compose reads it from `.env` at
runtime. On hosted platforms use their secret management (`flyctl secrets set`,
Render env-var encryption, AWS Secrets Manager, etc.). Confirm with:

```bash
docker compose config | grep -i api_key   # should show ${GEMINI_API_KEY}, not the actual value
```

### Persistence

Three volumes matter:

| Volume | Why |
|---|---|
| `shield_data` | SQLite DB. Lose it = lose all contracts, decisions, audit log. |
| `shield_uploads` | Original PDF files. Lose it = audit reports can't link back to source. |
| `shield_rag_cache` | Embedding cache. Lose it = corpus re-embeds on next startup (burns ~33 API calls). Not catastrophic but annoying. |

For SQLite specifically, consider migrating to managed Postgres at any real
scale — concurrent writes will eventually bite. Change one line in `db.py`
(`DATABASE_URL`) and you're done.

### Lobster Trap visibility

Production decision: do you expose port 8080 publicly?

- **Don't** if you want a clean security boundary. Only the backend talks to LT.
- **Do** if you want auditors / SREs to see the LT dashboard. Put it behind
  basic auth or a VPN — never publicly accessible without authentication.

The `docker-compose.yml` exposes 8080 by default for local dev convenience.
In prod, remove the `ports:` block under `lobstertrap` so it's reachable
only from inside the compose network.

### Free-tier Gemini in production

Free tier is **not appropriate for production traffic** — the 30 RPM /
1500 RPD caps will be hit by the first real customer. Move to paid plan
before any real launch. The cost model:

- Gemini Flash-Lite: ~$0.075 per million input tokens, $0.30 per million output
- Average upload: ~5K input tokens × 5 agent calls = 25K → $0.002 per upload
- 1000 uploads/day ≈ $2/day on Gemini alone

### Lobster Trap availability

Lobster Trap should restart on crash (`restart: unless-stopped` handles
this). If it's down for an extended period, the backend gracefully falls back
to the offline pattern detector — but you lose the DPI layer. Add a health
check + alerting (Render and Fly both ship simple monitoring; for VMs use
Uptime Kuma or healthchecks.io).

### Streamlit behind a reverse proxy

Streamlit uses websockets for live updates. If you put it behind nginx, the
proxy needs websocket support:

```nginx
location / {
    proxy_pass http://localhost:8501;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}
```

Fly.io and Render handle this automatically.

---

## Quick decision matrix

| Goal | Best option |
|---|---|
| Show judges a live URL during the hackathon | Fly.io (free tier, ~5 min deploy) |
| Demo for a small enterprise pilot | Render with paid Postgres + Disk |
| Production with real traffic | Cloud VM or k8s + managed Postgres + paid Gemini |
| Just want to test the container build works | `docker compose up --build` locally |

---

## Verifying a fresh deployment

After deploy, run the smoke test against your live URL:

```bash
export BACKEND_URL=https://your-backend.fly.dev   # or wherever
# Edit scripts/demo_smoke_test.py to use this URL (or pass as env var if you wire it)
make demo-test
```

Expect all 7 demo contracts to land where the test expects. If any path
breaks, check:

1. `GEMINI_API_KEY` is set in the backend env
2. `LOBSTERTRAP_URL` points at the internal hostname of the LT container
3. The persistent volume is mounted and writable
4. The RAG cache built successfully on first start (check logs for
   `RAG ready: {...}`)
