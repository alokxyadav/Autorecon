.PHONY: help install test dev deploy docker-up docker-down seed reconcile clean

help:
	@echo "AutoRecon — available commands:"
	@echo "  make install      Install backend Python dependencies"
	@echo "  make test         Run the full backend test suite"
	@echo "  make dev          Start the backend dev server (uvicorn --reload)"
	@echo "  make deploy       Run the full orchestrated startup (tests -> backend -> seed -> reconcile)"
	@echo "  make docker-up    Start the full stack via Docker Compose"
	@echo "  make docker-down  Stop the Docker Compose stack"
	@echo "  make seed         Seed demo data (backend must already be running)"
	@echo "  make reconcile    Run reconciliation (backend must already be running)"
	@echo "  make clean        Remove __pycache__, .pytest_cache, and the local SQLite db"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

dev:
	uvicorn app.main:app --reload

deploy:
	./deploy.sh

docker-up:
	docker compose up --build

docker-down:
	docker compose down

seed:
	curl -X POST http://localhost:8000/demo/seed

reconcile:
	curl -X POST http://localhost:8000/reconcile/run

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
	rm -f autorecon.db
