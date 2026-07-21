.DEFAULT_GOAL := help
COMPOSE := docker compose
SHELL := /bin/bash

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Create .env from .env.example with generated secrets
	@test -f .env && { echo ".env already exists - not overwriting"; exit 0; } || true
	@cp .env.example .env
	@python3 -c "import secrets,base64,pathlib;p=pathlib.Path('.env');t=p.read_text();\
t=t.replace('ENCRYPTION_KEY=','ENCRYPTION_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),1);\
t=t.replace('JWT_SECRET=','JWT_SECRET='+secrets.token_urlsafe(48),1);\
t=t.replace('INTERNAL_API_TOKEN=','INTERNAL_API_TOKEN='+secrets.token_urlsafe(32),1);\
p.write_text(t)"
	@echo "Wrote .env with generated ENCRYPTION_KEY / JWT_SECRET / INTERNAL_API_TOKEN"

.PHONY: keygen
keygen: ## Print a fresh set of secrets
	@python3 -c "import secrets,base64;print('ENCRYPTION_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode());print('JWT_SECRET='+secrets.token_urlsafe(48));print('INTERNAL_API_TOKEN='+secrets.token_urlsafe(32))"

.PHONY: up
up: ## Start all services
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Stop all services
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop services and delete all volumes (destructive)
	$(COMPOSE) down -v

.PHONY: migrate
migrate: ## Apply database migrations
	$(COMPOSE) run --rm app alembic upgrade head

.PHONY: revision
revision: ## Create a migration: make revision m="add thing"
	$(COMPOSE) run --rm app alembic revision --autogenerate -m "$(m)"

.PHONY: models
models: ## Pull local Ollama models (llama3.2 + nomic-embed-text)
	$(COMPOSE) exec ollama ollama pull llama3.2
	$(COMPOSE) exec ollama ollama pull nomic-embed-text

.PHONY: seed
seed: ## Create a demo business + admin user
	$(COMPOSE) run --rm app python -m callsentry.scripts.seed

.PHONY: bootstrap
bootstrap: env up migrate models seed ## Full first-run setup
	@echo ""
	@echo "CallSentry is up."
	@echo "  Dashboard : http://localhost:3000  (demo@callsentry.local / changeme)"
	@echo "  API docs  : http://localhost:8000/docs"
	@echo "  Providers : http://localhost:8000/settings/providers"

.PHONY: logs
logs: ## Tail logs (make logs s=app)
	$(COMPOSE) logs -f $(s)

.PHONY: shell
shell: ## Shell into a service (make shell s=app)
	$(COMPOSE) exec $(or $(s),app) /bin/bash

.PHONY: psql
psql: ## Open a psql session
	$(COMPOSE) exec postgres psql -U callsentry -d callsentry

.PHONY: test
test: ## Run the backend test suite
	$(COMPOSE) run --rm app pytest -q

.PHONY: lint
lint: ## Type-check and lint the backend
	$(COMPOSE) run --rm app ruff check callsentry
	$(COMPOSE) run --rm app mypy callsentry
