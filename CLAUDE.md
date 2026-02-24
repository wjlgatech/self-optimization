# Self-Optimization Systems — Developer Guide

## Architecture

Python modules (stdlib only, except optional `urllib` for LLM):

```
src/
├── anti_idling_system.py          # Idle state detection & intervention
├── results_verification.py        # Result quality verification (SMARC criteria)
├── multi_agent_performance.py     # Multi-agent performance tracking
├── recursive_self_improvement.py  # Self-improvement protocol
├── filesystem_scanner.py          # Real activity detection (git, files, reflections)
├── gateway_watchdog.py             # OpenClaw gateway health monitor & auto-restart
├── config_loader.py               # Loads performance-system/monitoring/config.yaml
├── llm_provider.py                # Anthropic API client (optional, stdlib urllib)
├── orchestrator.py                # Integration layer: wires all systems + config
├── marketing_eval.py             # Marketing effectiveness monitor
├── __main__.py                    # CLI entry point
└── __init__.py
tests/
├── test_anti_idling_unit.py          # Unit tests
├── test_results_verification_unit.py # Unit tests
├── test_multi_agent_performance.py   # Performance optimizer tests
├── test_recursive_self_improvement.py # Self-improvement tests
├── test_filesystem_scanner.py        # Scanner tests (real filesystem)
├── test_config_loader.py            # Config loading + multi-agent tests
├── test_llm_provider.py             # LLM provider tests
├── test_orchestrator.py             # Orchestrator tests (real filesystem)
├── test_integration.py               # Integration tests
├── test_functional.py                # Functional/scenario tests
├── test_edge_cases.py                # Edge case & robustness tests
├── test_contract_and_regression.py   # Contract + regression tests
├── test_marketing_eval.py            # Marketing eval tests
├── conftest.py                       # Centralized sys.path setup
└── __init__.py
state/                                # Runtime state (gitignored)
```

## Orchestrator Architecture

```
┌─────────────────────────────────────────────────┐
│                  Orchestrator                     │
│  (config, multi-agent, scheduling, persistence)  │
├────────────┬───────────────┬────────────────────┤
│ AntiIdling │ Performance   │ SelfImprovement    │
│ +Filesystem│ +Config Thresh│ +Real Execution    │
│  Scanner   │ +Intervention │ +LLM Proposals     │
├────────────┴───────────────┴────────────────────┤
│            ConfigLoader (config.yaml)            │
│  Agents: loopy-0, loopy-1 (from monitoring cfg) │
│  Thresholds: goal_completion, task_efficiency    │
│  Intervention tiers: tier1/tier2/tier3           │
├─────────────────────────────────────────────────┤
│              LLM Provider (optional)             │
│  urllib → Anthropic API (ANTHROPIC_API_KEY)      │
│  Falls back to rule-based if no key              │
└─────────────────────────────────────────────────┘
```

Hybrid approach: rules handle scheduling, metrics, state, thresholds.
LLM (optional) enhances analysis and reflection writing.

## Multi-Agent Support

Agents are defined in `performance-system/monitoring/config.yaml`:
- `loopy` → normalized to `loopy-0` (primary agent)
- `loopy1` → normalized to `loopy-1` (parallel tasks)

Run as a specific agent: `python src/__main__.py --agent-id loopy-1 idle-check`

## Monitoring Config Integration

The orchestrator reads `~/.openclaw/workspace/performance-system/monitoring/config.yaml`:
- Agent names (normalized: `loopy` → `loopy-0`)
- Performance thresholds (goal_completion_rate, task_efficiency)
- Intervention escalation tiers (tier1/tier2/tier3 with durations and actions)
- Falls back to defaults if config file is missing

## CLI Commands

```bash
# Idle check (every 2 hours via cron)
python src/__main__.py idle-check

# Idle check as Loopy-1
python src/__main__.py --agent-id loopy-1 idle-check

# Daily review (once daily at 11 PM via cron — replaces daily_reflection.sh)
python src/__main__.py daily-review

# Check intervention tier for an agent
python src/__main__.py intervention --agent loopy-0

# Long-running daemon
python src/__main__.py run-daemon --interval 7200 --review-hour 23

# System status
python src/__main__.py status

# Gateway watchdog (checks health, restarts if down)
python src/__main__.py gateway-watchdog
python src/__main__.py gateway-watchdog --port 31415

# Cost governor (audit, optimize, track OpenClaw token/cost usage)
python src/__main__.py cost-audit                          # find cost waste
python src/__main__.py cost-apply --strategy balanced      # generate + apply optimized config
python src/__main__.py cost-apply --strategy balanced --dry-run  # preview only
python src/__main__.py cost-baseline                       # record current state as baseline
python src/__main__.py cost-status                         # show savings vs baseline
python src/__main__.py cost-govern                         # full governor cycle

# Self-evaluation (runs real quality gates on itself)
python src/__main__.py self-eval                           # JSON report
python src/__main__.py self-eval --markdown                # human-readable report
python src/__main__.py self-eval --no-services             # skip service probes (for CI)

# Self-healing (auto-fix lint + format + corrupted state)
python src/__main__.py self-heal

# Self-discovery (services, repos, config drift)
python src/__main__.py self-discover
```

## Cost Governor

Monitors and optimizes OpenClaw token/cost usage. Targets 90%+ reduction via:
- **Model routing**: detect expensive model, recommend cheap/local alternatives
- **Bootstrap diet**: measure auto-injected workspace files, enforce caps
- **Compaction**: detect weak compaction mode, recommend aggressive
- **Heartbeat**: detect expensive heartbeat model, recommend cheap

```bash
make cost-audit     # audit current config for cost waste
make cost-status    # show savings vs baseline
make cost-govern    # full governor cycle (audit + compare + alert)
```

Strategies for `cost-apply`: `aggressive` (local model), `balanced` (Haiku), `conservative` (keep model, trim waste).

## Gateway Watchdog

Monitors all three OpenClaw services (base gateway:3000, enterprise:18789, vite-ui:5173).
One-command setup copies scripts to `~/.openclaw/scripts/`, uses system Python to avoid macOS sandbox issues with cron:

```bash
make install-watchdog     # deploy scripts + install cron job
make uninstall-watchdog   # remove cron job + deployed scripts (preserves log)
make watchdog-status      # show cron entry, deployed files, recent log
```

Services with launchd agents (base gateway) get auto-restarted.
Services without launchd (enterprise, vite) are detected and flagged for manual restart.

## Self-Eval Engine

Four closed loops: DISCOVER → HEAL → EVALUATE → HUMAN.

- **DISCOVER**: `discover_services()` (TCP probes), `discover_repos()` (recursive git scan), `discover_config_drift()` (SHA-256 hash tracking)
- **HEAL**: `heal_lint()` (ruff --fix), `heal_format()` (ruff format), `heal_state()` (quarantine corrupted JSON)
- **EVALUATE**: `eval_lint()`, `eval_typecheck()`, `eval_tests()`, `eval_services()` — runs real tools, parses output
- **REPORT**: Weighted composite score (lint 20%, typecheck 20%, tests 40%, services 20%) → A-F grade
- **HUMAN**: GitHub Issues on grade drop (C/D/F), auto-heal PRs for fixable lint issues

Grade thresholds: A≥90, B≥80, C≥70, D≥60, F<60. History capped at 90 entries.

CI/CD workflows:
- `.github/workflows/ci.yml` — on-push quality gates + self-eval
- `.github/workflows/self-eval.yml` — daily eval, creates GitHub Issues on degradation
- `.github/workflows/self-heal.yml` — weekly auto-fix PR

## Cron Setup

Jobs are configured in `~/.openclaw/cron/jobs.json`:
- **System crontab** (`crontab -l`): `gateway-watchdog` every 5 minutes (TCP health probe + launchctl restart) — installed via `make install-watchdog`
- `self-opt-idle-check-loopy0`: Loopy-0 idle check every 2 hours
- `self-opt-idle-check-loopy1`: Loopy-1 idle check every 2 hours (offset 15 min)
- `self-opt-daily-review`: daily at 11 PM (replaces `tools/daily_reflection.sh`)

## State Persistence

Runtime state is stored in `state/` (gitignored):
- `activity_log.json` — recent activity entries
- `performance_history.json` — performance tracking data
- `improvement_history.json` — improvement execution log
- `capability_map.json` — current capability proficiencies
- `last_run.json` — last operation timestamp and result
- `eval_history.json` — self-eval score history (90-entry FIFO)
- `config_hashes.json` — SHA-256 hashes for config drift detection

## LLM Integration

Set `ANTHROPIC_API_KEY` env var to enable LLM-enhanced analysis.
Uses `claude-haiku-4-5-20251001` via stdlib `urllib.request`.
Falls back to rule-based analysis if no key is set.

## Contributor Workflow

```bash
# First-time setup (installs deps + pre-commit hooks)
python3 -m venv .venv
source .venv/bin/activate
make install       # pip install -e ".[dev]" && pre-commit install

# Before every commit (pre-commit hooks run these automatically)
make check         # runs: ruff lint + mypy typecheck + pytest

# Individual gates
make lint          # ruff check src/ tests/
make fmt           # ruff format src/ tests/
make typecheck     # mypy src/
make test          # pytest tests/ -v
make pre-commit    # run all pre-commit hooks on all files
```

### Pre-commit hooks (mandatory)

Pre-commit hooks are installed automatically by `make install`. They enforce:

1. **Trailing whitespace** removal
2. **End-of-file newline** enforcement
3. **YAML/JSON validation** (catches syntax errors before commit)
4. **Merge conflict markers** detection
5. **Large file guard** (blocks files >200KB — prevents accidental binary commits)
6. **Ruff lint + format** (auto-fixes import sorting, modernizes syntax)
7. **Mypy** type checking on `src/`

These hooks run on every `git commit`. You cannot bypass them without `--no-verify`.

## Running Tests

```bash
make test
# or directly:
pytest tests/ -v
```

377 tests, all passing. Pytest config lives in `pyproject.toml`.

## Quality Gates

All three must pass before merging — enforced by pre-commit hooks:

1. **Ruff** — linting (E/F/W/I/UP/B/SIM/T20), import sorting, modern syntax (`ruff check`)
2. **Mypy** — strict type checking on `src/` (`mypy src/`)
3. **Pytest** — 377 tests (`pytest tests/ -v`)

Run all at once with `make check`.

## Code Standards (enforced automatically)

- **Modern Python**: use `dict`, `list`, `X | None` — not `Dict`, `List`, `Optional` (ruff UP rules)
- **Imports**: stdlib first, then third-party, then local — enforced by ruff I rules
- **No `print()` in library code**: only allowed in `__main__.py` (ruff T20 rule)
- **All public methods typed**: `-> None` on constructors, return types on all methods (mypy strict)
- **Logging**: call `logging.basicConfig()` only in `__main__.py`, use `logging.getLogger(__name__)` in libraries
- **Test imports**: use `from module_name import Class` (no `src.` prefix) — conftest.py sets up sys.path
- **Line length**: 100 characters max

## Test Conventions

- Unit tests cover individual methods in isolation
- Regression tests in `test_contract_and_regression.py` verify all 10 historical bugs stay fixed
- Use `pytest.approx()` for floating-point comparisons
- Use `tmp_path` fixture for file I/O tests
- Use `unittest.mock.MagicMock` for callback verification
- Use `zip(..., strict=True)` when iterating paired sequences

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
- `logging.basicConfig()` is called only in `__main__.py`; library modules use `logging.getLogger(__name__)`
- Input validation: `log_activity()` rejects non-dict, `register_intervention_callback()` rejects non-callable, `add_custom_verification_criterion()` rejects non-callable/empty name, `verify_results()` rejects non-dict
- `config_loader.py` parses YAML subset with regex (no PyYAML dependency)
- Agent names normalized: `loopy` → `loopy-0`, `loopy1` → `loopy-1`
- Orchestrator registers ALL agents from config.yaml, not just the current one
- `get_intervention_tier()` maps performance score to tier1/tier2/tier3 via config thresholds
- `daily_reflection.sh` is deprecated; forwards to `python src/__main__.py daily-review`

## Marketing Eval Engine

Monitors marketing content effectiveness using the same DISCOVER → SCORE → RECOMMEND → REPORT pattern.

### CLI Commands

```bash
python src/__main__.py marketing-eval                   # full eval (JSON)
python src/__main__.py marketing-eval --markdown        # human-readable report
python src/__main__.py marketing-discover               # scan marketing/ for content
python src/__main__.py marketing-score                  # score all content
python src/__main__.py marketing-status                 # inventory: published vs draft
python src/__main__.py marketing-metrics --content-id social-posts-post-1 --impressions 5000 --engagements 200
python src/__main__.py marketing-publish --content-id social-posts-post-1 --url https://x.com/post/1
python src/__main__.py marketing-recommend              # improvement recommendations
```

Makefile shortcuts: `make marketing-eval`, `make marketing-discover`, `make marketing-status`.

### Scoring Formula (weighted composite, 0-100)

| Sub-score | Weight | Formula |
|-----------|--------|---------|
| engagement_rate | 30% | engagements / impressions * 1000, capped at 100 |
| reach | 20% | impressions normalized against channel benchmarks |
| conversion | 20% | (clicks + conversions) / engagements * 200, capped at 100 |
| content_quality | 15% | rule-based: word count + CTA + link + code + hashtags (20 pts each) |
| freshness | 15% | max(0, 100 - days_since_published * 2) |

Draft content receives `content_quality` score only. Grade: A≥90, B≥80, C≥70, D≥60, F<60.

### State Files (in `state/`, gitignored)

- `marketing_content.json` — content records with metrics and status
- `marketing_eval_history.json` — 90-entry FIFO eval history
- `marketing_content_hashes.json` — SHA-256 hashes for drift detection

### CI/CD

- `.github/workflows/marketing-eval.yml` — weekly Monday 9 AM UTC + on push to `marketing/**`
- Creates GitHub Issue if grade drops below B (label: `marketing-eval`)

### Orchestrator Integration

If `marketing/` directory exists, `daily_review()` automatically includes marketing eval results.

## Import Pattern

```python
# From application code (or use pip install -e ".[dev]")
from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework
from multi_agent_performance import MultiAgentPerformanceOptimizer
from recursive_self_improvement import RecursiveSelfImprovementProtocol
from orchestrator import SelfOptimizationOrchestrator
from filesystem_scanner import FilesystemScanner
from config_loader import load_monitoring_config
from llm_provider import LLMProvider
from self_eval import SelfEvalEngine
from marketing_eval import MarketingEvalEngine
```
