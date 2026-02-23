# Self-Optimization System

**Your AI agents forget to work. This system catches them.**

**Your AI bills are 19x higher than they need to be. This system fixes that.**

**Your gateway crashes at 3 AM. This system restarts it before anyone notices.**

A zero-dependency Python framework that makes AI agent operations reliable and affordable. Built for [OpenClaw](https://docs.openclaw.ai). Runs on your machine, on your schedule.

```bash
pip install -e ".[dev]" && make install-watchdog && make cost-audit
```

---

## 1. Gateway Watchdog: Sleep Through Outages

**The problem you're solving:** Your AI gateway crashes at 3 AM on a Saturday. Your Telegram bot, Discord channels, and Slack integrations all go dark. You wake up Sunday to 47 undelivered messages and an angry group chat.

**With this:** The watchdog detects the crash in under 5 minutes, restarts the gateway automatically, and your users never notice. You slept through the whole thing.

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
<summary><b>Implementation: TCP probe + launchctl restart pipeline</b></summary>

Every 5 minutes via system crontab:

1. TCP socket probe to `127.0.0.1:{port}` (faster than HTTP health checks)
2. If down: `launchctl kickstart -k` (atomic kill + restart)
3. If kickstart fails: `bootout` + `bootstrap` (full service reload)
4. 3 retry attempts with 10s delays and post-restart verification
5. JSON results logged to `/tmp/openclaw-watchdog.log`

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

## 3. Idle Detection: Know When Agents Stop Working

**The problem you're solving:** Your AI agent has been "running" for 6 hours but produced nothing. No commits, no file changes, no output. You don't find out until end of day when you check manually.

**With this:** Every 2 hours, the system scans real filesystem activity — git commits, file modifications, workspace changes. Zero output = idle alert with automatic intervention.

```bash
.venv/bin/python src/__main__.py --agent-id loopy-0 idle-check
```

<details>
<summary><b>Technical innovation: filesystem-based activity detection</b></summary>

Instead of polling AI provider APIs or scraping dashboards, the system measures work output directly. Git commits = code was produced. File modifications = work is happening. This is provider-agnostic, privacy-preserving, tamper-evident (git signatures), and works offline. No false positives from editor autosave — it looks for meaningful work artifacts.

</details>

<details>
<summary><b>Implementation: workspace scanner + intervention tiers</b></summary>

The filesystem scanner examines `~/.openclaw/workspace/`:

- `git log` across all subdirectories with `.git`
- `mtime` checks across the workspace tree
- Markdown parsing in `memory/daily-reflections/`

Idle = zero commits AND zero file modifications within the time window (default: 2 hours). Configurable thresholds and multi-tier escalation (warning at 70%, critical at 50%).

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
├── anti_idling_system.py          # Idle detection
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
make check   # ruff lint + mypy typecheck + pytest (304 tests)
```

See `CLAUDE.md` for design decisions, test conventions, and contributor workflow.

## License

MIT
