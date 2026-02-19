# Self-Optimization Systems

A Python framework for building self-monitoring intelligent agents that detect idle states, verify output quality, and maintain accountability through measurable criteria.

## Purpose

When building autonomous agents or long-running AI systems, two problems emerge quickly:

1. **Agents go idle** — they stall, spin on low-value tasks, or fail to self-correct when unproductive
2. **Output quality is unmeasured** — agents produce results with no structured check on whether those results are specific, actionable, or compounding

This library provides two independent, zero-dependency modules to solve both:

| Module | What it does |
|--------|-------------|
| `AntiIdlingSystem` | Tracks agent activity over time, calculates idle rates, triggers intervention callbacks when productivity drops below a threshold |
| `ResultsVerificationFramework` | Evaluates output dicts against 5 quality criteria (Specific, Measurable, Actionable, Reusable, Compoundable), logs verification history, and tracks success rates |

## When to use this

- You're building an **autonomous agent loop** and need a watchdog that fires callbacks when the agent isn't producing
- You want to **gate outputs** through a quality check before passing them downstream
- You need **audit trails** — both modules maintain bounded history logs exportable as JSON
- You want a **lightweight, stdlib-only** solution (no numpy, no frameworks, no external deps)

## Installation

```bash
git clone https://github.com/wjlgatech/self-optimization.git
cd self-optimization

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

### Anti-Idling: Monitor agent productivity

```python
from anti_idling_system import AntiIdlingSystem

# Alert if agent is idle more than 80% of the time
system = AntiIdlingSystem(idle_threshold=0.8)

# Register what happens when idling is detected
def on_idle():
    print("Agent is slacking — triggering new task!")

system.register_intervention_callback(on_idle)

# Log productive work as it happens
system.log_activity({"type": "research", "duration": 3600, "is_productive": True})
system.log_activity({"type": "waiting", "duration": 600, "is_productive": False})

# Check idle rate (returns 0.0–1.0, clamped)
rate = system.calculate_idle_rate(time_window=86400)
print(f"Idle rate: {rate:.1%}")

# Or run detection — fires callbacks if above threshold
system.detect_and_interrupt_idle_state()

# For continuous monitoring (in a thread or background process)
import threading
t = threading.Thread(target=system.run_periodic_check, kwargs={"interval": 60})
t.start()
# ... later ...
system.stop()  # graceful shutdown
```

### Results Verification: Check output quality

```python
from results_verification import ResultsVerificationFramework

fw = ResultsVerificationFramework(max_history=500)

# Verify a result dict against 5 SMARC criteria
result = {
    "next_step": "deploy to staging",   # actionable ✓
    "score": 92,                         # measurable ✓
    "details": [{"latency": 42}],        # compoundable ✓
}
# specific ✓ (non-empty, no None values), reusable ✓ (>1 key)

verification = fw.verify_results(result)
# {'specific': True, 'measurable': True, 'actionable': True,
#  'reusable': True, 'compoundable': True}

# Check if ALL criteria passed
print(fw.verification_history[-1]["overall_valid"])  # True

# Add domain-specific criteria
def check_confidence(results):
    return results.get("confidence", 0) > 0.8

fw.add_custom_verification_criterion("confident", check_confidence)

# Track success rate over time
print(f"Success rate: {fw.get_verification_success_rate():.1f}%")

# Export history for auditing
fw.export_verification_history("audit.json")
```

### Using both together

```python
from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework

agent = AntiIdlingSystem(idle_threshold=0.5)
verifier = ResultsVerificationFramework()

def intervention():
    """When agent idles, force a task and verify the output."""
    output = run_emergency_task()  # your agent logic
    v = verifier.verify_results(output)
    if not all(v.values()):
        log.warning(f"Low-quality emergency output: {v}")

agent.register_intervention_callback(intervention)
agent.run_periodic_check(interval=300)  # check every 5 minutes
```

## SMARC Verification Criteria

Each result dict is checked against 5 criteria:

| Criterion | Passes when |
|-----------|------------|
| **Specific** | Dict is non-empty and no values are `None` |
| **Measurable** | At least one value is `int`, `float`, or `str` |
| **Actionable** | Dict contains `"next_step"` or `"recommendation"` key |
| **Reusable** | Dict has more than 1 key |
| **Compoundable** | At least one value is a `list` or `dict` |

A result that passes all 5 (e.g. `{"next_step": "go", "score": 95, "items": [1,2]}`) gets `overall_valid=True`.

## Project Structure

```
src/
├── anti_idling_system.py         # Idle detection & intervention
├── results_verification.py       # SMARC quality verification
├── multi_agent_performance.py    # Multi-agent performance tracking
├── recursive_self_improvement.py # Self-improvement protocol
└── __init__.py
tests/
├── test_anti_idling_unit.py          # 48 unit tests
├── test_results_verification_unit.py # 60 unit tests
├── test_contract_and_regression.py   # 27 contract + regression tests
├── test_edge_cases.py                # 24 edge case tests
├── test_functional.py                # 12 functional scenario tests
├── test_integration.py               # 11 integration tests
├── conftest.py
└── __init__.py
```

182 tests, all passing. Zero external dependencies at runtime.

## Development

```bash
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy src/
make test        # pytest
make check       # all three gates (required before merge)
make clean       # remove caches
```

Quality gates: **ruff** (lint + format) + **mypy** (type check) + **pytest** (182 tests).

## License

MIT
