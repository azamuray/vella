.PHONY: up down logs restart clean build shell-backend shell-frontend

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

restart: down up

clean:
	docker compose down -v --remove-orphans

build:
	docker compose build

shell-backend:
	docker compose exec backend /bin/bash

shell-frontend:
	docker compose exec frontend /bin/sh

# Development helpers
dev-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && python -m http.server 8080
