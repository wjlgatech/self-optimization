# Self-Optimization Systems — Developer Guide

## Architecture

Six Python modules (stdlib only, except optional `urllib` for LLM):

```
src/
├── anti_idling_system.py          # Idle state detection & intervention
├── results_verification.py        # Result quality verification (SMARC criteria)
├── multi_agent_performance.py     # Multi-agent performance tracking
├── recursive_self_improvement.py  # Self-improvement protocol
├── filesystem_scanner.py          # Real activity detection (git, files, reflections)
├── llm_provider.py                # Anthropic API client (optional, stdlib urllib)
├── orchestrator.py                # Integration layer: wires all systems
├── __main__.py                    # CLI entry point
└── __init__.py
tests/
├── test_anti_idling_unit.py          # Unit tests
├── test_results_verification_unit.py # Unit tests
├── test_multi_agent_performance.py   # Performance optimizer tests
├── test_recursive_self_improvement.py # Self-improvement tests
├── test_filesystem_scanner.py        # Scanner tests (real filesystem)
├── test_llm_provider.py             # LLM provider tests
├── test_orchestrator.py             # Orchestrator tests (real filesystem)
├── test_integration.py               # Integration tests
├── test_functional.py                # Functional/scenario tests
├── test_edge_cases.py                # Edge case & robustness tests
├── test_contract_and_regression.py   # Contract + regression tests
├── conftest.py                       # Centralized sys.path setup
└── __init__.py
state/                                # Runtime state (gitignored)
```

## Orchestrator Architecture

```
┌─────────────────────────────────────────────────┐
│                  Orchestrator                     │
│  (wires 4 systems, scheduling, state persistence)│
├─────────────┬───────────────┬───────────────────┤
│ AntiIdling  │ Performance   │ SelfImprovement   │
│ + Filesystem│ + Real Trends │ + Real Execution  │
│   Scanner   │   from Data   │ + LLM Proposals   │
├─────────────┴───────────────┴───────────────────┤
│              LLM Provider (optional)             │
│  urllib → Anthropic API (ANTHROPIC_API_KEY)      │
│  Falls back to rule-based if no key              │
└─────────────────────────────────────────────────┘
```

Hybrid approach: rules handle scheduling, metrics, state, thresholds.
LLM (optional) enhances analysis and reflection writing.

## CLI Commands

```bash
# Idle check (every 2 hours via cron)
python src/__main__.py idle-check

# Daily review (once daily at 11 PM via cron)
python src/__main__.py daily-review

# Long-running daemon
python src/__main__.py run-daemon --interval 7200 --review-hour 23

# System status
python src/__main__.py status
```

## Cron Setup

Jobs are configured in `~/.openclaw/cron/jobs.json`:
- `self-opt-idle-check`: every 2 hours
- `self-opt-daily-review`: daily at 11 PM

## State Persistence

Runtime state is stored in `state/` (gitignored):
- `activity_log.json` — recent activity entries
- `performance_history.json` — performance tracking data
- `improvement_history.json` — improvement execution log
- `capability_map.json` — current capability proficiencies
- `last_run.json` — last operation timestamp and result

## LLM Integration

Set `ANTHROPIC_API_KEY` env var to enable LLM-enhanced analysis.
Uses `claude-haiku-4-5-20251001` via stdlib `urllib.request`.
Falls back to rule-based analysis if no key is set.

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

200+ tests, all passing. Pytest config lives in `pyproject.toml`.

## Quality Gates

All three must pass before merging:

1. **Ruff** — linting and import sorting (`ruff check`)
2. **Mypy** — type checking on `src/` (`mypy src/`)
3. **Pytest** — 200+ tests (`pytest tests/ -v`)

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
- `generate_emergency_actions()` is context-aware when activity_log has data; returns full pool when empty (backward compatible)
- `_calculate_performance_score()` uses weighted scoring (accuracy=0.4, efficiency=0.35, adaptability=0.25)
- `_analyze_performance_trends()` uses first-half vs second-half comparison, >5% = improving, <-5% = declining
- `_identify_capability_gaps()` checks for low proficiency (<0.5), stale entries (>30 days), and missing expected capabilities
- `_implement_improvement()` updates capability_map: existing +0.1 proficiency (capped 1.0), new starts at 0.1
- `logging.basicConfig()` is called in constructors (first-call-wins behavior)
- Input validation: `log_activity()` rejects non-dict, `register_intervention_callback()` rejects non-callable, `add_custom_verification_criterion()` rejects non-callable/empty name, `verify_results()` rejects non-dict

## Import Pattern

```python
# From application code (or use pip install -e ".[dev]")
from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework
from multi_agent_performance import MultiAgentPerformanceOptimizer
from recursive_self_improvement import RecursiveSelfImprovementProtocol
from orchestrator import SelfOptimizationOrchestrator
from filesystem_scanner import FilesystemScanner
from llm_provider import LLMProvider
```
