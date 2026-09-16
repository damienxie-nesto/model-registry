export UV_LOCKED := 1

setup:
	uv venv
	uv sync --group dev
	GIT_CONFIG_GLOBAL=/dev/null uv run pre-commit install

update:
	UV_LOCKED=0 uv sync --group dev --upgrade

check-lock:
	uv lock --check

test: check

lint:
	uv run ruff check model_registry/ tests/

format:
	uv run ruff format model_registry/ tests/

format_check:
	uv run ruff format --check model_registry/ tests/

fix:
	uv run ruff check --fix model_registry/ tests/

typecheck:
	uv run mypy model_registry/ tests/

run_tests:
	uv run pytest -v ./tests --cov=model_registry --cov-report term-missing -p no:warnings

validate:
	uv run model-registry validate

render:
	uv run model-registry render

check: format_check lint typecheck run_tests validate
