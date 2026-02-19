# Self-Optimization System

A self-monitoring framework for OpenClaw agents. Detects idle states from real filesystem activity (git commits, file modifications), generates data-driven daily reflections, tracks performance across multiple agents, and triggers self-improvement when productivity drops.

## Install (one-time setup)

```bash
cd ~/.openclaw/workspace/self-optimization
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify the install works:

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py status
```

You should see JSON output with `agent_id`, `registered_agents`, `llm_available`, etc.

## Running as Loopy-0 (primary agent)

### Quick status check

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py status
```

### Manual idle check (scans last 2 hours of activity)

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py --agent-id loopy-0 idle-check
```

Output includes: `activities_found`, `idle_rate`, `triggered` (true if idle threshold exceeded).

### Manual daily review (scans last 24 hours, writes reflection)

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py --agent-id loopy-0 daily-review
```

This will:
1. Scan all git repos in `~/.openclaw/workspace/` for commits
2. Scan file modifications across the workspace
3. Calculate performance metrics
4. Write a data-driven reflection to `~/.openclaw/workspace/memory/daily-reflections/YYYY-MM-DD-reflection.md`
5. Persist state to `state/` directory

### Check intervention tier

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py intervention --agent loopy-0
```

Returns the current intervention tier (none/tier1/tier2/tier3) based on performance thresholds from `config.yaml`.

## Running as Loopy-1 (parallel agent)

Same commands, just change `--agent-id`:

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py --agent-id loopy-1 idle-check
.venv/bin/python src/__main__.py --agent-id loopy-1 daily-review
```

## Automatic scheduling (cron)

Cron jobs are configured in `~/.openclaw/cron/jobs.json`:

| Job ID | Schedule | What it does |
|--------|----------|-------------|
| `self-opt-idle-check-loopy0` | Every 2 hours | Idle check for Loopy-0 |
| `self-opt-idle-check-loopy1` | Every 2 hours (offset 15 min) | Idle check for Loopy-1 |
| `self-opt-daily-review` | Daily at 11 PM | Full daily review + reflection |

The cron commands use absolute venv paths so they work without `source activate`:

```bash
cd ~/.openclaw/workspace/self-optimization && .venv/bin/python src/__main__.py --agent-id loopy-0 idle-check
```

### Verify cron is working

After a cron cycle runs, check state files:

```bash
cat ~/.openclaw/workspace/self-optimization/state/last_run.json
ls -la ~/.openclaw/workspace/memory/daily-reflections/
```

## Daemon mode (alternative to cron)

Run as a long-lived process instead of cron jobs:

```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py run-daemon --interval 7200 --review-hour 23
```

This runs idle checks every 7200 seconds (2 hours) and the daily review once at hour 23 (11 PM). Stop with Ctrl+C.

## What the system scans

The filesystem scanner looks at real activity in `~/.openclaw/workspace/`:

- **Git commits**: Runs `git log` in the workspace root and all immediate subdirectories that have a `.git` directory
- **File modifications**: Walks the workspace tree, checks `mtime` against the time window
- **Daily reflections**: Parses markdown files in `memory/daily-reflections/` and `memory/reflections/daily/`

Idle = no commits and no file modifications across any repository within the time window (default: 2 hours for idle check, 24 hours for daily review).

## LLM-enhanced analysis (optional)

Set the `ANTHROPIC_API_KEY` environment variable to enable AI-powered analysis:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py daily-review
```

When the API key is set, daily reflections include an "AI Reflection" section with intelligent narrative. Without the key, everything still works using rule-based analysis.

Uses `claude-haiku-4-5-20251001` via stdlib `urllib.request` (no extra dependencies).

## Monitoring config

The system reads thresholds and agent definitions from:
`~/.openclaw/workspace/performance-system/monitoring/config.yaml`

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
    actions:
      - performance_review
      - skill_assessment
  tier2:
    duration: 1 month
    actions:
      - targeted_coaching
      - personalized_learning_plan
  tier3:
    duration: 3 months
    actions:
      - comprehensive_performance_rehabilitation
      - external_skill_development_resources
```

If the config file is missing, sensible defaults are used.

## State files

Runtime state is persisted to `~/.openclaw/workspace/self-optimization/state/` (gitignored):

| File | Contents |
|------|---------|
| `last_run.json` | Timestamp and result of the most recent operation |
| `activity_log.json` | Recent activity entries (FIFO capped at 100) |
| `performance_history.json` | Performance tracking data over time |
| `improvement_history.json` | Self-improvement execution log |
| `capability_map.json` | Current capability proficiency levels |

## Troubleshooting

**"No module named orchestrator"**: You need to run from the project directory or use the venv python:
```bash
cd ~/.openclaw/workspace/self-optimization
.venv/bin/python src/__main__.py status
```

**activities_found is 0**: The scanner only finds activity within the time window. For idle-check that's 2 hours. Make a commit or edit a file, wait a moment, then re-run.

**daily_reflection.sh still running**: The old script has been deprecated and now forwards to the orchestrator. To fully remove it, delete `~/.openclaw/workspace/tools/daily_reflection.sh`.

**State files missing**: They're created on first run. Run any command (`status`, `idle-check`, `daily-review`) and the `state/` directory will be populated.

## Development

```bash
cd ~/.openclaw/workspace/self-optimization
source .venv/bin/activate
make check   # ruff lint + mypy typecheck + pytest (259 tests)
```

See `CLAUDE.md` for architecture details, design decisions, and test conventions.

## License

MIT
