# Self-Optimization System

**Your AI agents forget to work. This system catches them — and fixes them automatically.**

**Your AI bills are 19x higher than they need to be. One command cuts 94.7%.**

**All three OpenClaw services monitored: base gateway (3000), enterprise bot (18789), web UI (5173). Crash at 3 AM → detected in 5 minutes.**

A zero-dependency Python framework that makes AI agent operations reliable, affordable, and self-correcting. Built for [OpenClaw](https://docs.openclaw.ai). 377 tests. Zero external packages. Runs on your machine, on your schedule.

```bash
pip install -e ".[dev]" && make install-watchdog && make cost-audit
```

> See [NEWS.md](NEWS.md) for latest updates

---

## 1. Gateway Watchdog: Sleep Through Outages

**The problem you're solving:** Your AI gateway crashes at 3 AM on a Saturday. Your Telegram bot, Discord channels, and Slack integrations all go dark. You wake up Sunday to 47 undelivered messages and an angry group chat.

**With this:** The watchdog monitors all three OpenClaw services every 5 minutes: base gateway (port 3000), enterprise gateway (port 18789), and web UI (port 5173). Services with launchd agents get auto-restarted. Services without launchd (enterprise gateway) get flagged as `critical_down` for immediate manual intervention.

```bash
make install-watchdog      # one command, handles everything
make watchdog-status       # see what's happening
make uninstall-watchdog    # clean removal
```

<details>
<summary><b>Technical innovation: sandbox-aware cron deployment</b></summary>

macOS cron can't read `~/Documents/` or access Python virtualenvs due to TCC sandboxing. The installer solves this by deploying to `~/.openclaw/scripts/` with system Python, auto-detecting the gateway port from config and Node.js path from the LaunchAgent plist. One command replaces 5 manual steps.

</details>

<details>
<summary><b>Implementation: multi-service TCP probes + launchctl restart</b></summary>

Every 5 minutes via system crontab, probes all three services:

| Service | Port | Auto-restart | Critical |
|---------|------|-------------|----------|
| Base gateway | 3000 | Yes (launchd) | Yes |
| Enterprise gateway | 18789 | No (manual) | Yes |
| Web UI (Vite) | 5173 | No (manual) | No |

For services with launchd agents:
1. TCP socket probe to `127.0.0.1:{port}` (faster than HTTP health checks)
2. If down: `launchctl kickstart -k` (atomic kill + restart)
3. If kickstart fails: `bootout` + `bootstrap` (full service reload)
4. 3 retry attempts with 10s delays and post-restart verification

For services without launchd: detected and reported as `critical_down` or `degraded`. JSON results logged to `/tmp/openclaw-watchdog.log`.

Idempotent cron management via marker comments. Safe to run `make install-watchdog` repeatedly.

</details>

---

## 2. Cost Governor: Cut Your AI Bill by 94.7%

**The problem you're solving:** You're running Claude Opus at $15/M input tokens for every turn — including heartbeat inbox checks, simple Q&A, and routine tasks. Your monthly bill is 19x higher than it needs to be.

**With this:** One command audits your config, identifies waste, and applies optimized settings. Real result from our production setup:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Model cost | $15.00/M tokens | $0.80/M tokens | **-94.7%** |
| Compaction | safeguard (lazy) | default (eager) | Stops token growth |
| Heartbeat | Opus ($15/M) | Haiku ($0.80/M) | Trivial work, trivial cost |
| Bootstrap cap | 150K chars | 8K chars/file | 19x tighter |

```bash
make cost-audit     # find waste
make cost-status    # track savings vs baseline
make cost-govern    # periodic governance cycle
```

<details>
<summary><b>Technical innovation: non-additive savings estimation</b></summary>

Multiple optimizations don't add linearly — two 50% savings compound to 75%, not 100%. The governor uses `1 - product(1 - r_i)` to calculate compound savings honestly, capped at 95%. Each recommendation shows individual impact plus the realistic combined total. No overpromising.

</details>

<details>
<summary><b>Implementation: config audit + patch + baseline tracking</b></summary>

The governor reads `~/.openclaw/openclaw.json` and detects:

- **Expensive default model**: Flags Opus/GPT-4o, recommends Haiku/mini/local
- **Heartbeat waste**: Detects heartbeat inheriting expensive model for trivial inbox checks
- **Bootstrap bloat**: Measures all auto-injected files (AGENTS.md, SOUL.md, etc.), flags oversized caps
- **Weak compaction**: Detects `safeguard` mode, recommends `default` for earlier compaction

Three strategies: `aggressive` (local Ollama, free), `balanced` (Haiku, 19x cheaper), `conservative` (keep model, trim waste). Applies via deep-merge with automatic backup.

```bash
# Preview
.venv/bin/python src/__main__.py cost-apply --strategy balanced --dry-run
# Apply (creates ~/.openclaw/openclaw.json.pre-governor.bak)
.venv/bin/python src/__main__.py cost-apply --strategy balanced
# Track over time
.venv/bin/python src/__main__.py cost-baseline && .venv/bin/python src/__main__.py cost-status
```

</details>

---

## 3. Idle Detection + Auto-Recovery: Agents That Fix Themselves

**The problem you're solving:** Your AI agent has been "running" for 6 hours but produced nothing. No commits, no file changes, no output. Worse — even when the system detected the idle state, it only logged it. Nothing actually happened.

**With this:** Every 2 hours, the system scans real filesystem activity AND probes all service health. Zero output triggers automatic intervention: the idle detector dispatches emergency actions directly into the self-improvement engine. Critical services down? Reported immediately alongside idle rate. Strategic analysis kicks off, skill development starts, research sprints begin — all without human intervention.

```bash
.venv/bin/python src/__main__.py --agent-id loopy-0 idle-check
```

**What you get back:**
```json
{
  "triggered": true,
  "actions_proposed": ["conduct_strategic_analysis", "explore_new_skill_development"],
  "actions_executed": ["conduct_strategic_analysis", "explore_new_skill_development"],
  "idle_rate": 0.97,
  "service_health": {
    "gateway": {"healthy": true, "port": 3000},
    "enterprise": {"healthy": false, "port": 18789, "critical": true},
    "vite-ui": {"healthy": true, "port": 5173}
  },
  "services_down": ["enterprise"]
}
```

`actions_proposed` vs `actions_executed` = no more log-only interventions. `service_health` = every idle check also verifies all OpenClaw services are up.

<details>
<summary><b>Technical innovation: handler-dispatch architecture</b></summary>

Instead of a monolithic "detect idle, then do X" pipeline, emergency actions use a **handler registry pattern**. Each action name maps to a callable. The orchestrator registers 5 handlers at init that route directly to the self-improvement protocol:

- `conduct_strategic_analysis` -> improvement execution (target: problem_solving)
- `explore_new_skill_development` -> improvement execution (target: learning)
- `start_research_sprint` -> improvement execution (target: task_execution)
- `design_experimental_prototype` -> improvement execution (target: learning)
- `initiate_user_feedback_loop` -> improvement execution (target: communication)

Handlers are isolated: one failure doesn't block others. Unhandled actions fall back to logging. New actions can be registered without modifying core detection logic.

</details>

<details>
<summary><b>Implementation: filesystem scanner + action dispatch</b></summary>

The filesystem scanner examines `~/.openclaw/workspace/`:

- `git log` across all subdirectories with `.git`
- `mtime` checks across the workspace tree
- Markdown parsing in `memory/daily-reflections/`

Detection flow:
1. Calculate idle rate from real filesystem activity
2. If above threshold: generate context-aware emergency actions (contrasts dominant activity type)
3. Dispatch each action through registered handlers
4. Track `actions_proposed` vs `actions_executed` separately
5. Persist updated capability_map to state

</details>

---

## 4. Daily Reviews: Automated Performance Reflections

**The problem you're solving:** "Was today productive?" You either guess, or spend 30 minutes reviewing logs and commits manually. Every day.

**With this:** At 11 PM every night, the system scans the day's work, calculates performance metrics, and writes a data-driven reflection to markdown. When you arrive next morning, the summary is already there.

```bash
.venv/bin/python src/__main__.py --agent-id loopy-0 daily-review
```

<details>
<summary><b>Technical innovation: LLM-optional analysis</b></summary>

Set `ANTHROPIC_API_KEY` to get AI-generated narrative sections via Claude Haiku (stdlib `urllib.request`, no dependencies). Without the key, everything still works using rule-based analysis. The system never depends on an API to function.

</details>

<details>
<summary><b>Implementation: scan + score + write pipeline</b></summary>

1. Scan all git repos for the day's commits
2. Count file modifications across the workspace
3. Calculate performance metrics (goal completion, task efficiency)
4. Write reflection to `~/.openclaw/workspace/memory/daily-reflections/YYYY-MM-DD-reflection.md`
5. Persist state for trend analysis

</details>

---

## 5. Multi-Agent Performance Tracking: Find the Weak Link

**The problem you're solving:** You're running multiple AI agents in parallel. One is underperforming, but you can't tell which one or how badly without manual investigation.

**With this:** Per-agent performance tracking with automatic escalation. Score drops below 70%? Performance review. Below 50%? Targeted coaching. Sustained low? Full rehabilitation program.

```bash
.venv/bin/python src/__main__.py intervention --agent loopy-0
```

<details>
<summary><b>Technical innovation: weighted multi-signal scoring</b></summary>

Performance score = accuracy (40%) + efficiency (35%) + adaptability (25%). Uses first-half vs second-half comparison for trend detection (>5% = improving, <-5% = declining). Agent names normalized automatically (`loopy` -> `loopy-0`, `loopy1` -> `loopy-1`).

</details>

<details>
<summary><b>Implementation: config-driven escalation tiers</b></summary>

| Tier | Trigger | Duration | Actions |
|------|---------|----------|---------|
| Tier 1 | Score < 70% | 2 weeks | Performance review, skill assessment |
| Tier 2 | Score < 50% | 1 month | Targeted coaching, personalized learning plan |
| Tier 3 | Sustained low | 3 months | Comprehensive rehabilitation program |

Thresholds configured in `config.yaml`. Falls back to sensible defaults if config is missing.

</details>

---

## Safety, Efficiency & Scalability

Independent evaluation across 11 source modules (~3,200 lines):

| Dimension | Score | Highlights |
|-----------|-------|------------|
| **Safety** | 7.5/10 | Input validation on all public APIs. Atomic file writes (temp + rename) across all state persistence. Exception isolation in every loop — one failing callback never blocks others. Ethical constraint framework on self-improvement proposals. API keys read from env only, never logged. Subprocess calls use list form (no shell injection). |
| **Efficiency** | 8.0/10 | FIFO caps on activity_log (100), verification_history (1000), watchdog history (50), cost baselines (20). O(n) algorithms where n is bounded. State persistence every 2 hours, not every operation. LLM calls optional and single-shot (no retry loops). |
| **Scalability** | 7.0/10 | Multi-agent support via config.yaml. Handler/callback/strategy registries for extension without core modification. Daemon mode with SIGTERM handling. Config-driven thresholds and escalation tiers. |

<details>
<summary><b>What makes this safe to run as a daemon</b></summary>

- **Atomic writes everywhere**: State files use `write-to-tmp + os.replace()` pattern — no corruption on crash
- **Per-item exception handling**: Daemon loop, callback dispatch, handler dispatch all wrap individual items in try/except
- **Bounded memory**: Activity logs capped at 100 entries, verification at 1000, watchdog at 50
- **Graceful shutdown**: SIGTERM handler sets flag, current loop finishes cleanly
- **No shell injection**: All subprocess calls use `subprocess.run([...])` list form with timeouts
- **Secrets never logged**: API keys and gateway tokens read from env/config, never appear in logs or state files

</details>

<details>
<summary><b>Known limitations (honest accounting)</b></summary>

- `improvement_history` and `performance_history` are unbounded — will accumulate ~17 MB/year in daemon mode (tracked for future cap)
- State files not scoped by agent_id — concurrent multi-agent daemons can race on writes
- Config changes require daemon restart (no hot-reload)
- Ethical constraint fields on proposals are opt-in — not enforced if proposal omits them

</details>

---

## Quickstart

```bash
cd ~/.openclaw/workspace/self-optimization
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make install-watchdog    # gateway auto-recovery
make cost-audit          # find cost waste
```

## Scheduling

| Job | Schedule | Setup |
|-----|----------|-------|
| Gateway watchdog | Every 5 min | `make install-watchdog` |
| Idle check | Every 2 hours | `~/.openclaw/cron/jobs.json` |
| Daily review | 11 PM daily | `~/.openclaw/cron/jobs.json` |
| Cost governance | On demand | `make cost-govern` |

## Architecture

```
src/
├── cost_governor.py               # Token/cost optimization
├── gateway_watchdog.py            # Gateway health monitor
├── anti_idling_system.py          # Idle detection + action dispatch
├── filesystem_scanner.py          # Real activity detection
├── multi_agent_performance.py     # Performance tracking
├── recursive_self_improvement.py  # Self-improvement protocol
├── results_verification.py        # Result quality (SMARC)
├── orchestrator.py                # Integration layer
├── config_loader.py               # YAML parser (no PyYAML)
├── llm_provider.py                # Anthropic API (stdlib urllib)
└── __main__.py                    # CLI entry point
```

**Zero dependencies.** Entire system runs on Python stdlib. No `requests`, no `pyyaml`, no `psutil`. Cron jobs and launchd agents start fast and work without virtualenv activation.

## Development

```bash
source .venv/bin/activate
make check   # ruff lint + mypy typecheck + pytest (377 tests, all passing)
```

See `CLAUDE.md` for design decisions, test conventions, and contributor workflow.

## License

MIT
