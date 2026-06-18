.PHONY: up down logs build migrate revision test lint shell-backend shell-db

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

migrate:
	docker compose exec backend alembic upgrade head

revision:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

test:
	docker compose exec backend pytest -v --cov=app

lint:
	docker compose exec backend ruff check app

shell-backend:
	docker compose exec backend /bin/bash

shell-db:
	docker compose exec postgres psql -U candiq -d candiq
