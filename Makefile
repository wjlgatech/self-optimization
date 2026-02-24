.PHONY: install lint format fmt typecheck test check clean \
       install-watchdog uninstall-watchdog watchdog-status \
       cost-audit cost-status cost-govern \
       pre-commit

# ── Setup ────────────────────────────────────────────────────────────────

install:
	pip install -e ".[dev]"
	pre-commit install

# ── Quality gates (all three must pass before merging) ───────────────────

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

fmt: format

typecheck:
	mypy src/

test:
	pytest tests/ -v

check: lint typecheck test

# ── Pre-commit ───────────────────────────────────────────────────────────

pre-commit:
	pre-commit run --all-files

# ── Cleanup ──────────────────────────────────────────────────────────────

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ \
	       .pytest_cache .mypy_cache *.egg-info src/*.egg-info

# ── Gateway watchdog ─────────────────────────────────────────────────────

install-watchdog:
	bash scripts/install-watchdog.sh install

uninstall-watchdog:
	bash scripts/install-watchdog.sh uninstall

watchdog-status:
	bash scripts/install-watchdog.sh status

# ── Cost governor ────────────────────────────────────────────────────────

cost-audit:
	.venv/bin/python src/__main__.py cost-audit

cost-status:
	.venv/bin/python src/__main__.py cost-status

cost-govern:
	.venv/bin/python src/__main__.py cost-govern
