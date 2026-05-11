.PHONY: install backend backend-only frontend test demo-test clean \
        docker-build docker-up docker-down docker-logs docker-rebuild docker-status

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
