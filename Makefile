.PHONY: install backend backend-only frontend test demo-test clean \
        docker-build docker-up docker-down docker-logs docker-rebuild docker-status \
        gcp-setup gcp-secrets gcp-build gcp-push \
        gcp-deploy-lobstertrap gcp-deploy-backend gcp-deploy-frontend gcp-deploy gcp-logs

# ── GCP config ────────────────────────────────────────────────────────────────
GCP_PROJECT       ?= gen-lang-client-0285486889
GCP_REGION        ?= us-central1
AR_REPO           ?= shield-ai
BACKEND_SVC       ?= shield-backend
FRONTEND_SVC      ?= shield-frontend
LOBSTERTRAP_SVC   ?= shield-lobstertrap
SA_EMAIL          ?= shield-ai-backend@$(GCP_PROJECT).iam.gserviceaccount.com

AR_HOST            := $(GCP_REGION)-docker.pkg.dev
IMAGE_BACKEND      := $(AR_HOST)/$(GCP_PROJECT)/$(AR_REPO)/shield-backend
IMAGE_FRONTEND     := $(AR_HOST)/$(GCP_PROJECT)/$(AR_REPO)/shield-frontend
IMAGE_LOBSTERTRAP  := $(AR_HOST)/$(GCP_PROJECT)/$(AR_REPO)/shield-lobstertrap

install:
	pip install -r requirements.txt

# Full dev stack: spawns Lobster Trap (if available) + uvicorn.
# Ctrl+C kills both.
backend:
	@python scripts/dev.py

# Just uvicorn — use when Lobster Trap is already running in another terminal,
# or when you don't want it at all.
backend-only:
	uvicorn backend.main:app --reload --port 8000

frontend:
	streamlit run frontend/app.py

test:
	pytest tests/ -v

demo-test:
	@echo "Re-running pipeline against demo contracts to check for regressions..."
	@echo "(backend must be running on port 8000)"
	@python scripts/demo_smoke_test.py

clean:
	rm -f shield.db
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +

# ─── Docker / production deploy ───────────────────────────────────────────

docker-build:
	docker-compose build

docker-up:
	@if [ ! -f .env ]; then \
		echo "ERROR: .env not found. Run: cp .env.example .env  and set GEMINI_API_KEY"; \
		exit 1; \
	fi
	docker-compose up -d
	@echo ""
	@echo "  ┌────────────────────────────────────────────────────────"
	@echo "  │  Shield AI is starting…"
	@echo "  │"
	@echo "  │  Frontend:        http://localhost:8501"
	@echo "  │  Backend API:     http://localhost:8000  (docs: /docs)"
	@echo "  │  Lobster Trap:    http://localhost:8080/_lobstertrap/"
	@echo "  │"
	@echo "  │  Logs:            make docker-logs"
	@echo "  │  Stop everything: make docker-down"
	@echo "  └────────────────────────────────────────────────────────"

docker-down:
	docker-compose down

docker-rebuild:
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

docker-logs:
	docker-compose logs -f --tail=100

docker-status:
	docker-compose ps

# ─── Google Cloud Run deploy ──────────────────────────────────────────────────

## One-time setup: enable APIs, create Artifact Registry repo, grant IAM roles
gcp-setup:
	@echo "Enabling GCP APIs..."
	gcloud config set project $(GCP_PROJECT)
	gcloud services enable \
		run.googleapis.com \
		artifactregistry.googleapis.com \
		cloudbuild.googleapis.com \
		secretmanager.googleapis.com \
		sqladmin.googleapis.com \
		storage.googleapis.com
	@echo "Creating Artifact Registry repository..."
	gcloud artifacts repositories create $(AR_REPO) \
		--repository-format=docker \
		--location=$(GCP_REGION) \
		--description="Shield AI Docker images" || true
	@echo "Granting Cloud Build service account roles..."
	gcloud projects add-iam-policy-binding $(GCP_PROJECT) \
		--member="serviceAccount:$$(gcloud projects describe $(GCP_PROJECT) --format='value(projectNumber)')@cloudbuild.gserviceaccount.com" \
		--role="roles/run.admin"
	gcloud projects add-iam-policy-binding $(GCP_PROJECT) \
		--member="serviceAccount:$$(gcloud projects describe $(GCP_PROJECT) --format='value(projectNumber)')@cloudbuild.gserviceaccount.com" \
		--role="roles/iam.serviceAccountUser"
	gcloud projects add-iam-policy-binding $(GCP_PROJECT) \
		--member="serviceAccount:$$(gcloud projects describe $(GCP_PROJECT) --format='value(projectNumber)')@cloudbuild.gserviceaccount.com" \
		--role="roles/secretmanager.secretAccessor"
	@echo "Granting backend service account Storage Object Admin..."
	gcloud projects add-iam-policy-binding $(GCP_PROJECT) \
		--member="serviceAccount:$(SA_EMAIL)" \
		--role="roles/storage.objectAdmin"
	@echo ""
	@echo "✅  GCP setup complete."

## Store secrets in Secret Manager (run once; reads from your local .env)
gcp-secrets:
	@echo "Storing secrets in Secret Manager..."
	@for secret in GEMINI_API_KEY DATABASE_URL PINECONE_API_KEY PINECONE_INDEX_NAME GCS_BUCKET_NAME; do \
		value=$$(grep "^$$secret=" .env | cut -d'=' -f2-); \
		if [ -z "$$value" ]; then \
			echo "  SKIP $$secret (not set in .env)"; \
			continue; \
		fi; \
		echo "  $$secret"; \
		printf '%s' "$$value" | gcloud secrets create $$secret \
			--data-file=- --replication-policy=automatic 2>/dev/null || \
		printf '%s' "$$value" | gcloud secrets versions add $$secret --data-file=-; \
	done
	gcloud secrets add-iam-policy-binding GEMINI_API_KEY \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
	gcloud secrets add-iam-policy-binding DATABASE_URL \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
	gcloud secrets add-iam-policy-binding PINECONE_API_KEY \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
	gcloud secrets add-iam-policy-binding PINECONE_INDEX_NAME \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
	gcloud secrets add-iam-policy-binding GCS_BUCKET_NAME \
		--member="serviceAccount:$(SA_EMAIL)" --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
	@echo "✅  Secrets stored."

## Authenticate Docker with Artifact Registry
gcp-auth:
	gcloud auth configure-docker $(AR_HOST)

## Build all three images locally and tag for Artifact Registry
## --platform linux/amd64 required: Cloud Run only supports amd64 (Mac M-series builds arm64 by default)
gcp-build: gcp-auth
	docker build --platform linux/amd64 -t $(IMAGE_BACKEND):latest .
	docker build --platform linux/amd64 -f frontend.Dockerfile -t $(IMAGE_FRONTEND):latest .
	docker build --platform linux/amd64 -f lobstertrap.Dockerfile -t $(IMAGE_LOBSTERTRAP):latest .

## Push images to Artifact Registry
gcp-push:
	docker push $(IMAGE_BACKEND):latest
	docker push $(IMAGE_FRONTEND):latest
	docker push $(IMAGE_LOBSTERTRAP):latest

## Run Alembic migrations as a one-off Cloud Run Job (uses the backend image).
## Call this BEFORE gcp-deploy-backend whenever the schema has changed.
gcp-migrate:
	@echo "Running alembic upgrade head as a Cloud Run Job…"
	gcloud run jobs create shield-migrate-tmp \
		--image=$(IMAGE_BACKEND):latest \
		--region=$(GCP_REGION) \
		--service-account=$(SA_EMAIL) \
		--set-secrets=DATABASE_URL=DATABASE_URL:latest \
		--set-cloudsql-instances=gen-lang-client-0285486889:us-central1:free-trial-first-project \
		--command=alembic \
		--args=upgrade,head \
		--max-retries=1 \
		--task-timeout=120 2>/dev/null || \
	gcloud run jobs update shield-migrate-tmp \
		--image=$(IMAGE_BACKEND):latest \
		--region=$(GCP_REGION) \
		--service-account=$(SA_EMAIL) \
		--set-secrets=DATABASE_URL=DATABASE_URL:latest \
		--set-cloudsql-instances=gen-lang-client-0285486889:us-central1:free-trial-first-project \
		--command=alembic \
		--args=upgrade,head \
		--max-retries=1 \
		--task-timeout=120
	gcloud run jobs execute shield-migrate-tmp \
		--region=$(GCP_REGION) \
		--wait
	@echo "✅  Migrations complete."

## Deploy Lobster Trap to Cloud Run (internal prompt inspection proxy)
gcp-deploy-lobstertrap:
	gcloud run deploy $(LOBSTERTRAP_SVC) \
		--image=$(IMAGE_LOBSTERTRAP):latest \
		--region=$(GCP_REGION) \
		--platform=managed \
		--allow-unauthenticated \
		--port=8080 \
		--memory=512Mi \
		--cpu=1 \
		--min-instances=1 \
		--max-instances=2 \
		--concurrency=20 \
		--timeout=30 \
		--service-account=$(SA_EMAIL)
	@echo "✅  Lobster Trap deployed."
	@gcloud run services describe $(LOBSTERTRAP_SVC) --region=$(GCP_REGION) --format='value(status.url)'

## Deploy backend to Cloud Run (auto-injects Lobster Trap URL)
gcp-deploy-backend:
	$(eval LT_URL := $(shell gcloud run services describe $(LOBSTERTRAP_SVC) \
		--region=$(GCP_REGION) --format='value(status.url)' 2>/dev/null || echo ""))
	@echo "Lobster Trap URL: $(LT_URL)"
	gcloud run deploy $(BACKEND_SVC) \
		--image=$(IMAGE_BACKEND):latest \
		--region=$(GCP_REGION) \
		--platform=managed \
		--allow-unauthenticated \
		--port=8000 \
		--memory=1Gi \
		--cpu=1 \
		--min-instances=1 \
		--max-instances=3 \
		--concurrency=10 \
		--timeout=300 \
		--service-account=$(SA_EMAIL) \
		--set-env-vars=SKIP_RAG_INIT=true,SHIELD_LOG_LEVEL=INFO,LOBSTERTRAP_URL=$(LT_URL),LOBSTERTRAP_TIMEOUT_SEC=5 \
		--set-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest,DATABASE_URL=DATABASE_URL:latest,PINECONE_API_KEY=PINECONE_API_KEY:latest,PINECONE_INDEX_NAME=PINECONE_INDEX_NAME:latest,GCS_BUCKET_NAME=GCS_BUCKET_NAME:latest \
		--add-cloudsql-instances=gen-lang-client-0285486889:us-central1:free-trial-first-project
	@echo "✅  Backend deployed."
	@gcloud run services describe $(BACKEND_SVC) --region=$(GCP_REGION) --format='value(status.url)'

## Deploy frontend to Cloud Run (auto-injects backend URL)
gcp-deploy-frontend:
	$(eval BACKEND_URL := $(shell gcloud run services describe $(BACKEND_SVC) \
		--region=$(GCP_REGION) --format='value(status.url)'))
	@echo "Backend URL: $(BACKEND_URL)"
	gcloud run deploy $(FRONTEND_SVC) \
		--image=$(IMAGE_FRONTEND):latest \
		--region=$(GCP_REGION) \
		--platform=managed \
		--allow-unauthenticated \
		--port=8501 \
		--memory=512Mi \
		--cpu=1 \
		--min-instances=0 \
		--max-instances=2 \
		--concurrency=20 \
		--timeout=120 \
		--service-account=$(SA_EMAIL) \
		--set-env-vars="BACKEND_URL=$(BACKEND_URL)"
	@echo "✅  Frontend deployed."
	@gcloud run services describe $(FRONTEND_SVC) --region=$(GCP_REGION) --format='value(status.url)'

## Full build → push → migrate → deploy all three services
gcp-deploy: gcp-build gcp-push gcp-migrate gcp-deploy-lobstertrap gcp-deploy-backend gcp-deploy-frontend
	@echo ""
	@echo "┌────────────────────────────────────────────────────────"
	@echo "│  Shield AI deployed to Cloud Run"
	@echo "│"
	@echo "│  Lobster Trap: $$(gcloud run services describe $(LOBSTERTRAP_SVC) --region=$(GCP_REGION) --format='value(status.url)')"
	@echo "│  Backend:      $$(gcloud run services describe $(BACKEND_SVC) --region=$(GCP_REGION) --format='value(status.url)')"
	@echo "│  Frontend:     $$(gcloud run services describe $(FRONTEND_SVC) --region=$(GCP_REGION) --format='value(status.url)')"
	@echo "└────────────────────────────────────────────────────────"

## Tail Cloud Run logs
gcp-logs-backend:
	gcloud run services logs tail $(BACKEND_SVC) --region=$(GCP_REGION)

gcp-logs-frontend:
	gcloud run services logs tail $(FRONTEND_SVC) --region=$(GCP_REGION)
