# Self-Optimization System

**Your AI agents forget to work. This system catches them.**

A zero-dependency Python framework that monitors AI agent activity through real filesystem signals — git commits, file modifications, workspace changes — and automatically intervenes when productivity drops. No cloud dashboards. No manual check-ins. Just a cron job that watches the work and tells you the truth.

Built for [OpenClaw](https://docs.openclaw.ai) multi-agent setups. Runs on your machine, on your schedule.

---

## Why This Exists

| Problem | What happens without this | What happens with this |
|---------|--------------------------|----------------------|
| **Agent goes idle for hours** | You don't notice until end of day | Detected in 2 hours, intervention triggered automatically |
| **Gateway crashes at 3 AM** | Telegram/Discord/Slack go dark until you wake up | Auto-restarted in under 5 minutes, zero downtime |
| **"Was today productive?"** | You guess, or spend 30 min reviewing logs | Data-driven daily reflection written to markdown, every night at 11 PM |
| **Running multiple agents** | No idea which one is underperforming | Per-agent performance tracking with escalation tiers |
| **Performance slowly degrades** | You notice weeks later | Threshold-based alerts: warning at 70%, critical at 50% |

<details>
<summary><b>Real-world scenario: weekend gateway recovery</b></summary>

Saturday 2 AM. Your OpenClaw gateway OOMs and crashes. The watchdog's cron job fires at 2:05 AM, detects the TCP port is dead, runs `launchctl kickstart -k`, and the gateway is back by 2:06 AM. Your Telegram bot never missed a message. You slept through the whole thing.

Without the watchdog: you wake up Sunday to 47 undelivered messages and an angry group chat.

</details>

---

## Quickstart

```bash
# Install the framework
cd ~/.openclaw/workspace/self-optimization
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Deploy the gateway watchdog (1 command, handles everything)
make install-watchdog

# Check system status
.venv/bin/python src/__main__.py status
```

That's it. The watchdog is now monitoring your gateway every 5 minutes, and you can schedule idle checks and daily reviews via cron.

---

## What It Does

### Gateway Watchdog — never lose uptime again

```bash
make install-watchdog     # deploy + schedule (1 command)
make watchdog-status      # see what's happening
make uninstall-watchdog   # clean removal
```

<details>
<summary><b>How the watchdog keeps your gateway alive</b></summary>

The watchdog runs every 5 minutes via system crontab. Each cycle:

1. **TCP probe** to `127.0.0.1:{port}` — faster and more reliable than HTTP health checks
2. If the port is down, **restart via `launchctl kickstart -k`** (kills + restarts in one atomic operation)
3. If kickstart fails, **fallback to `bootout` + `bootstrap`** (full service reload)
4. **3 retry attempts** with 10-second delays and post-restart health verification
5. Results logged to `/tmp/openclaw-watchdog.log` with full JSON history

The installer auto-detects your gateway port from `~/.openclaw/openclaw.json` and your Node.js path from the LaunchAgent plist. Scripts are deployed to `~/.openclaw/scripts/` using system Python — avoiding the macOS sandbox restrictions that block cron from reading `~/Documents/` or venv paths.

</details>

### Idle Detection — know when agents stop working

```bash
.venv/bin/python src/__main__.py --agent-id loopy-0 idle-check
```

<details>
<summary><b>How idle detection works under the hood</b></summary>

The filesystem scanner examines real activity across `~/.openclaw/workspace/`:

- **Git commits**: `git log` across the workspace root and all subdirectories with `.git`
- **File modifications**: Walks the workspace tree, checks `mtime` against the time window
- **Daily reflections**: Parses markdown files in `memory/daily-reflections/`

**Idle** = zero commits AND zero file modifications within the window (default: 2 hours).

When idle is detected, the system triggers configurable intervention tiers based on severity and duration. No false positives from editor autosave — it looks for meaningful work artifacts.

</details>

### Daily Reviews — automated performance reflections

```bash
.venv/bin/python src/__main__.py --agent-id loopy-0 daily-review
```

<details>
<summary><b>What goes into a daily review</b></summary>

Every night at 11 PM (via cron), the system:

1. Scans all git repos for the day's commits
2. Counts file modifications across the workspace
3. Calculates performance metrics (goal completion, task efficiency)
4. Writes a data-driven reflection to `~/.openclaw/workspace/memory/daily-reflections/YYYY-MM-DD-reflection.md`
5. Persists state for trend analysis

Optional: set `ANTHROPIC_API_KEY` to add an AI-generated narrative section (Claude Haiku via stdlib `urllib` — no extra dependencies).

</details>

### Multi-Agent Performance Tracking

```bash
.venv/bin/python src/__main__.py intervention --agent loopy-0
```

<details>
<summary><b>How multi-agent tracking and escalation work</b></summary>

Agents are defined in `~/.openclaw/workspace/performance-system/monitoring/config.yaml`:

| Agent | Role |
|-------|------|
| `loopy-0` | Primary agent (normalized from `loopy`) |
| `loopy-1` | Parallel tasks (normalized from `loopy1`) |

**Escalation tiers** based on performance score:

| Tier | Trigger | Duration | Actions |
|------|---------|----------|---------|
| **Tier 1** | Score < 70% | 2 weeks | Performance review, skill assessment |
| **Tier 2** | Score < 50% | 1 month | Targeted coaching, personalized learning plan |
| **Tier 3** | Sustained low | 3 months | Comprehensive rehabilitation program |

Performance score = weighted combination: accuracy (40%) + efficiency (35%) + adaptability (25%).

</details>

---

## Technical Innovation

<details>
<summary><b>Zero-dependency architecture</b></summary>

The entire system runs on Python stdlib only. No `requests`, no `pyyaml`, no `psutil`.

- **HTTP calls**: `urllib.request` (for optional LLM integration)
- **YAML parsing**: Custom regex parser in `config_loader.py` (no PyYAML)
- **Health checks**: Raw TCP sockets (faster and more reliable than HTTP in launchd contexts)
- **Process management**: Direct `launchctl` subprocess calls
- **State persistence**: JSON files with atomic write (tmp + `os.replace`)

Why: cron jobs and launchd agents need to start fast and work without virtualenv activation. Every external dependency is a potential failure point at 3 AM.

</details>

<details>
<summary><b>macOS sandbox-aware deployment</b></summary>

macOS cron cannot read files in `~/Documents/` or access Python virtualenvs due to sandboxing (TCC). The installer solves this by:

1. Copying scripts to `~/.openclaw/scripts/` (accessible to cron)
2. Using system Python (`/usr/local/bin/python3`) instead of venv Python
3. Generating a standalone runner script (no imports from the project tree)
4. Setting explicit `PATH` in the crontab entry with auto-detected Node.js path

One `make install-watchdog` handles all of this.

</details>

<details>
<summary><b>Filesystem-based activity detection (no API polling)</b></summary>

Instead of polling AI provider APIs or scraping dashboards, the system measures work output directly:

- Git commits = code was produced
- File modifications = work is happening
- Reflection files = reviews were written

This approach is:
- **Provider-agnostic**: Works with any AI agent, any LLM provider
- **Privacy-preserving**: Never sends activity data anywhere
- **Tamper-evident**: Git commits are cryptographically signed work artifacts
- **Offline-capable**: No network dependency for core monitoring

</details>

<details>
<summary><b>Idempotent cron management</b></summary>

The installer uses marker comments (`# openclaw-gateway-watchdog`) in crontab entries. Running `make install-watchdog` multiple times is safe — it removes old entries before adding the new one. Uninstall cleanly removes only the watchdog entry, preserving all other cron jobs.

</details>

---

## Scheduling

| Job | Schedule | Command |
|-----|----------|---------|
| Gateway watchdog | Every 5 min | `make install-watchdog` (system crontab) |
| Idle check (loopy-0) | Every 2 hours | via `~/.openclaw/cron/jobs.json` |
| Idle check (loopy-1) | Every 2 hours (+15 min offset) | via `~/.openclaw/cron/jobs.json` |
| Daily review | 11 PM daily | via `~/.openclaw/cron/jobs.json` |

<details>
<summary><b>Daemon mode (alternative to cron)</b></summary>

```bash
.venv/bin/python src/__main__.py run-daemon --interval 7200 --review-hour 23
```

Runs idle checks every 2 hours and the daily review at 11 PM. Stop with Ctrl+C.

</details>

<details>
<summary><b>Verifying cron is working</b></summary>

```bash
# Check the watchdog
make watchdog-status
crontab -l | grep watchdog

# Check idle/review jobs
cat ~/.openclaw/workspace/self-optimization/state/last_run.json
ls -la ~/.openclaw/workspace/memory/daily-reflections/
```

</details>

---

## Full Technical Reference

<details>
<summary><b>All CLI commands</b></summary>

```bash
# Status
.venv/bin/python src/__main__.py status

# Idle check (scans last 2 hours)
.venv/bin/python src/__main__.py --agent-id loopy-0 idle-check

# Daily review (scans last 24 hours, writes reflection)
.venv/bin/python src/__main__.py --agent-id loopy-0 daily-review

# Check intervention tier
.venv/bin/python src/__main__.py intervention --agent loopy-0

# Gateway watchdog (manual run)
.venv/bin/python src/__main__.py gateway-watchdog
.venv/bin/python src/__main__.py gateway-watchdog --port 31415

# Daemon mode
.venv/bin/python src/__main__.py run-daemon --interval 7200 --review-hour 23
```

</details>

<details>
<summary><b>Architecture</b></summary>

```
src/
├── anti_idling_system.py          # Idle state detection & intervention
├── results_verification.py        # Result quality verification (SMARC criteria)
├── multi_agent_performance.py     # Multi-agent performance tracking
├── recursive_self_improvement.py  # Self-improvement protocol
├── filesystem_scanner.py          # Real activity detection (git, files, reflections)
├── gateway_watchdog.py            # OpenClaw gateway health monitor & auto-restart
├── config_loader.py               # Loads config.yaml (custom regex parser, no PyYAML)
├── llm_provider.py                # Anthropic API client (optional, stdlib urllib)
├── orchestrator.py                # Integration layer: wires all systems + config
├── __main__.py                    # CLI entry point
└── __init__.py
```

```
┌─────────────────────────────────────────────────┐
│                  Orchestrator                    │
│  (config, multi-agent, scheduling, persistence) │
├────────────┬───────────────┬────────────────────┤
│ AntiIdling │ Performance   │ SelfImprovement    │
│ +Filesystem│ +Config Thresh│ +Real Execution    │
│  Scanner   │ +Intervention │ +LLM Proposals     │
├────────────┴───────────────┴────────────────────┤
│            ConfigLoader (config.yaml)            │
│  Agents: loopy-0, loopy-1 (from monitoring cfg) │
├─────────────────────────────────────────────────┤
│              LLM Provider (optional)             │
│  urllib → Anthropic API (ANTHROPIC_API_KEY)      │
│  Falls back to rule-based if no key              │
└─────────────────────────────────────────────────┘
```

</details>

<details>
<summary><b>State files</b></summary>

Runtime state persisted to `~/.openclaw/workspace/self-optimization/state/` (gitignored):

| File | Contents |
|------|---------|
| `last_run.json` | Timestamp and result of the most recent operation |
| `activity_log.json` | Recent activity entries (FIFO capped at 100) |
| `performance_history.json` | Performance tracking data over time |
| `improvement_history.json` | Self-improvement execution log |
| `capability_map.json` | Current capability proficiency levels |
| `gateway_watchdog.json` | Watchdog check history (last 50 entries) |

</details>

<details>
<summary><b>Monitoring config reference</b></summary>

`~/.openclaw/workspace/performance-system/monitoring/config.yaml`:

```yaml
monitoring:
  agents:
    - loopy      # normalized to loopy-0
    - loopy1     # normalized to loopy-1

performance_thresholds:
  goal_completion_rate:
    warning_level: 0.7
    critical_level: 0.5
  task_efficiency:
    warning_level: 0.65
    critical_level: 0.4

intervention_escalation:
  tier1:
    duration: 2 weeks
    actions: [performance_review, skill_assessment]
  tier2:
    duration: 1 month
    actions: [targeted_coaching, personalized_learning_plan]
  tier3:
    duration: 3 months
    actions: [comprehensive_performance_rehabilitation, external_skill_development_resources]
```

</details>

<details>
<summary><b>Troubleshooting</b></summary>

**"No module named orchestrator"** — run from the project directory or use the venv python:
```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py status
```

**`activities_found` is 0** — the scanner only finds activity within the time window (2 hours for idle-check). Make a commit or edit a file, then re-run.

**`daily_reflection.sh` still running** — deprecated, now forwards to the orchestrator. Delete `~/.openclaw/workspace/tools/daily_reflection.sh` to fully remove.

**State files missing** — created on first run. Run any command and the `state/` directory will be populated.

**Watchdog not running** — verify with `make watchdog-status`. If the crontab entry is missing, re-run `make install-watchdog`.

</details>

---

## Development

```bash
source .venv/bin/activate
make check   # ruff lint + mypy typecheck + pytest (259 tests)
```

See `CLAUDE.md` for design decisions, test conventions, and contributor workflow.

## License

MIT
