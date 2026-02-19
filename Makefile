.PHONY: install lint format typecheck test check clean

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

test:
	pytest tests/ -v

check: lint typecheck test

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache .mypy_cache *.egg-info
