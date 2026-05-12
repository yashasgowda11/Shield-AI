# Shield AI — Local Development Setup

## Prerequisites

- **Python 3.11** — required (not 3.10, not 3.13)
- **Git**

Check your Python version:

```bash
python3 --version
```

If it's not 3.11, install it:
- Mac: `brew install python@3.11`
- Or download from [python.org/downloads](https://www.python.org/downloads/)

---

## Step 1 — Clone the repo

```bash
git clone <repo-url>
cd Shield-AI
```

---

## Step 2 — Create a virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate        # Mac / Linux
# venv\Scripts\activate         # Windows
```

You should see `(venv)` at the start of your terminal prompt.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 4 — Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the following values:

```env
# ── Gemini ────────────────────────────────────────────────────────────────────
# Get from: https://aistudio.google.com → "Get API key" (free)
GEMINI_API_KEY=AIza...

# ── Database ──────────────────────────────────────────────────────────────────
# Use SQLite for local dev — no database install needed
DATABASE_URL=sqlite:///./shield.db

# ── Frontend → Backend ────────────────────────────────────────────────────────
BACKEND_URL=http://localhost:8000

# ── Pinecone (vector store for RAG) ───────────────────────────────────────────
# Sign up free at https://app.pinecone.io
# Create a new index with: dimensions=3072, metric=cosine
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=shield-ai

# ── Google Cloud Storage (uploaded contract files) ────────────────────────────
# Ask your teammate for the bucket name and the SA key JSON file
GCS_BUCKET_NAME=shield-ai-uploads
GCS_SERVICE_ACCOUNT_KEY=/absolute/path/to/sa-key.json

# ── Lobster Trap (prompt security proxy) ──────────────────────────────────────
# Shared Cloud Run deployment — works out of the box, no local setup needed
LOBSTERTRAP_URL=https://shield-lobstertrap-aiffxvrl4q-uc.a.run.app
LOBSTERTRAP_TIMEOUT_SEC=8
```

### What to get from your teammate

| Item | How to use it |
|---|---|
| **GCS service account JSON key** | Save it anywhere on your machine, set `GCS_SERVICE_ACCOUNT_KEY` to its absolute path |
| **GCS bucket name** | Paste into `GCS_BUCKET_NAME` |
| **Pinecone index name** | Use the shared index name, or create your own with the same settings |

> The key file is in the `keys/` folder in the repo on your teammate's machine.  
> It's gitignored so it won't be in the clone — they need to send it to you directly.

---

## Step 5 — Initialize the database

```bash
alembic upgrade head
```

This creates `shield.db` (SQLite) with all the required tables. Only needs to be run once (or after pulling schema changes).

---

## Step 6 — Run the app

Open **two terminals**, both with the venv activated (`source venv/bin/activate`).

**Terminal 1 — Backend:**

```bash
make backend-only
```

Wait until you see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Terminal 2 — Frontend:**

```bash
make frontend
```

Then open **http://localhost:8501** in your browser.

---

## Step 7 — Verify everything is working

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok", "service": "shield-ai", "version": "0.2.0", "db": "connected"}
```

---

## Useful commands

| Command | What it does |
|---|---|
| `make backend-only` | Start the backend (uvicorn, auto-reloads on code changes) |
| `make frontend` | Start the Streamlit frontend |
| `make test` | Run the test suite |
| `make clean` | Delete `shield.db` and all `__pycache__` folders |
| `alembic upgrade head` | Apply any new DB migrations after a `git pull` |

---

## Common issues

**`ModuleNotFoundError` on any import**
→ The venv isn't activated. Run `source venv/bin/activate` and try again.

**`alembic: command not found`**
→ Same issue, or run `python -m alembic upgrade head` instead.

**Port 8000 already in use**
```bash
lsof -ti:8000 | xargs kill
```

**Port 8501 already in use**
```bash
lsof -ti:8501 | xargs kill
```

**GCS errors when uploading a contract**
→ The path in `GCS_SERVICE_ACCOUNT_KEY` is wrong or the file doesn't exist.  
→ Use the **absolute** path, e.g. `/Users/yourname/Shield-AI/keys/sa-key.json`.

**Pinecone errors on first startup**
→ Normal — the backend indexes the policy corpus into Pinecone on the first run. Wait ~30 seconds.  
→ After the first successful run, add `SKIP_RAG_INIT=true` to your `.env` to skip this on every subsequent startup.

**`alembic upgrade head` fails with a DB error after `git pull`**
→ Someone added a new migration. Delete `shield.db` and re-run `alembic upgrade head` to get a fresh DB.

---

## Live deployment (no setup needed)

If you just want to try the app without running it locally:

| Service | URL |
|---|---|
| **Frontend** | https://shield-frontend-aiffxvrl4q-uc.a.run.app |
| **Backend API docs** | https://shield-backend-aiffxvrl4q-uc.a.run.app/docs |
