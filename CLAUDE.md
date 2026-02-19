# Self-Optimization Systems — Developer Guide

## Architecture

Two independent Python modules with no external dependencies (stdlib only):

```
src/
├── anti_idling_system.py      # Idle state detection & intervention
├── results_verification.py    # Result quality verification (SMARC criteria)
└── __init__.py
tests/
├── test_anti_idling_unit.py          # Unit tests
├── test_results_verification_unit.py # Unit tests
├── test_integration.py               # Integration tests
├── test_functional.py                # Functional/scenario tests
├── test_edge_cases.py                # Edge case & robustness tests
├── test_contract_and_regression.py   # Contract + regression tests
├── conftest.py                       # Centralized sys.path setup
└── __init__.py
```

The two modules are **independent** — no imports between them. Integration happens at the application layer.

## Contributor Workflow

```bash
# First-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Before every commit
make check   # runs: ruff lint + mypy typecheck + pytest

# Individual gates
make lint        # ruff check src/ tests/
make format      # ruff format src/ tests/
make typecheck   # mypy src/
make test        # pytest tests/ -v
```

### Pre-commit hooks

```bash
pre-commit install   # one-time setup
```

Hooks run ruff (lint + format) and mypy on staged files automatically.

## Running Tests

```bash
make test
# or directly:
pytest tests/ -v
```

182 tests, all passing. Pytest config lives in `pyproject.toml`.

## Quality Gates

All three must pass before merging:

1. **Ruff** — linting and import sorting (`ruff check`)
2. **Mypy** — type checking on `src/` (`mypy src/`)
3. **Pytest** — 182+ tests (`pytest tests/ -v`)

Run all at once with `make check`.

## Test Conventions

- Unit tests cover individual methods in isolation
- Regression tests in `test_contract_and_regression.py` verify all 10 historical bugs stay fixed
- Use `pytest.approx()` for floating-point comparisons
- Use `tmp_path` fixture for file I/O tests
- Use `unittest.mock.MagicMock` for callback verification

## Key Design Decisions

- `activity_log` is FIFO-capped at 100 entries
- `verification_history` is FIFO-capped at `max_history` (default 1000)
- `calculate_idle_rate` clamps return to `[0.0, 1.0]`
- `calculate_idle_rate` raises `ValueError` for `time_window <= 0`
- Constructor validates `0.0 <= idle_threshold <= 1.0` and `minimum_productive_actions >= 0`
- `log_activity` makes a defensive copy (does not mutate caller's dict)
- `_check_specificity` uses `value is not None` (accepts zero, empty string, empty list)
- `_check_measurability` uses `any()` (mixed-type dicts can pass both measurable and compoundable)
- `_check_measurability` returns `False` for empty dicts
- `_check_actionability` checks `'next_step' in results or 'recommendation' in results`
- `run_periodic_check` uses `self._running` flag; call `stop()` to exit gracefully
- Idle detection uses strict `>` comparison (equal-to-threshold does NOT trigger)
- `generate_emergency_actions()` returns hardcoded strings — not adaptive
- `logging.basicConfig()` is called in both constructors (first-call-wins behavior)
- Input validation: `log_activity()` rejects non-dict, `register_intervention_callback()` rejects non-callable, `add_custom_verification_criterion()` rejects non-callable/empty name, `verify_results()` rejects non-dict

## Import Pattern

```python
# From application code (or use pip install -e ".[dev]")
from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework
```
