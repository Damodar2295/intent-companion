.PHONY: test run frontend lint
test:
	.venv/bin/python -m pytest -q
run:
	bash scripts/start_local.sh
frontend:
	cd frontend && npm ci && npm run build
lint:
	.venv/bin/ruff check agent config tests
