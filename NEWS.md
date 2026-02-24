# NEWS

## 2026-02-24: Self-Discovering, Self-Healing, Self-Evaluating (v0.9)

**The gap:** The system could monitor services and detect idle agents, but couldn't evaluate *itself*. No CI/CD. No automated quality checks. No way to know if the codebase was degrading. "Self-improvement" was just incrementing a float — no real tools were run.

**The fix:** Four closed loops that actually run real tools on the codebase:

| Loop | What it does | Trigger |
|------|-------------|---------|
| **DISCOVER** | Finds services, git repos, config drift | On-demand / daily eval |
| **HEAL** | Runs `ruff --fix`, `ruff format`, repairs corrupted state JSON | Weekly CI (auto-PR) |
| **EVALUATE** | Runs ruff, mypy, pytest on itself — scores A-F with weighted composite | Daily CI + on-push |
| **HUMAN** | Creates GitHub Issues when grade drops below B; auto-heal creates PRs | Automated via Actions |

**What changed:**
- New `SelfEvalEngine` (`src/self_eval.py`) with discover, heal, eval, and report capabilities
- `discover_services()` — TCP probes all 3 OpenClaw services
- `discover_repos()` — finds git repos in workspace (recursive, depth 3)
- `discover_config_drift()` — SHA-256 hash tracking detects changed config files
- `heal_lint()` / `heal_format()` — runs ruff auto-fix
- `heal_state()` — detects and quarantines corrupted JSON state files
- `eval_lint()` / `eval_typecheck()` / `eval_tests()` — runs real quality gates, parses output
- `eval_services()` — scores service health with critical-service penalty
- `run_full_eval()` — weighted composite score (lint 20%, typecheck 20%, tests 40%, services 20%)
- `generate_markdown_report()` — human-readable health report with trend tracking
- `generate_github_issue_body()` — auto-creates issue content when grade drops
- 90-entry FIFO history for trend analysis (score direction, test count growth)
- New CLI commands: `self-eval`, `self-heal`, `self-discover`
- `.github/workflows/ci.yml` — on-push quality gates + self-eval
- `.github/workflows/self-eval.yml` — daily scheduled eval, creates GitHub Issues on degradation
- `.github/workflows/self-heal.yml` — weekly auto-fix PR for lint/format issues
- **377 tests passing**, ruff clean, mypy clean

**Bottom line:** The system now evaluates itself with the same tools a human developer would use. Grade drops → GitHub Issue. Fixable lint → auto-PR. Human stays in the loop via GitHub, not pager duty.

---

## 2026-02-24: Enterprise Gateway Monitoring — Closing the Biggest Gap (v0.8)

**The gap:** The README promised "your gateway crashes at 3 AM, users never notice." In reality, the watchdog only monitored the base gateway (port 3000). The Enterprise Gateway (port 18789) — the actual user-facing bot server — had **zero monitoring**. It could be down for days without detection. On top of that, `DEFAULT_PORT` was hardcoded to `31415`, a port nothing actually uses.

**The fix:** The watchdog now monitors all three OpenClaw services: base gateway (3000), enterprise gateway (18789), and web UI (5173). Each service is probed independently. The orchestrator's `idle_check()` and `status()` now include `service_health` — so every idle check also verifies all services are up.

**What changed:**
- `GatewayWatchdog` now supports multi-service monitoring via `services` list
- Auto-detects all three services from config (gateway, enterprise, vite-ui)
- `run_check()` probes all services, not just one port
- `check_all_services()` returns per-service health with `critical` flag
- `restart_service()` handles services with/without launchd labels (no-launchd → `critical_down`)
- `DEFAULT_PORT` fixed from `31415` to `3000`
- New `probe_port()` standalone function for ad-hoc health checks
- Orchestrator `idle_check()` and `status()` now include `service_health` dict
- Critical services down are logged with `services_down` list
- README claims updated to match reality (honest about auto-restart vs detect-only)
- **343 tests passing**, ruff clean, mypy clean

**Bottom line:** The system no longer lies about what it monitors. All three services are checked. If something is down, you know immediately — whether it can be auto-fixed or needs manual intervention.

---

## 2025-02-24: Idle Agents Now Fix Themselves (v0.7)

**The gap:** The anti-idling system could *detect* when agents stopped working and *propose* emergency actions — but never actually *executed* them. `actions_taken` was a lie. The actions were logged and forgotten.

**The fix:** Emergency actions now dispatch through a handler registry directly into the self-improvement engine. When your agent goes idle, strategic analysis, skill development, and research sprints kick off automatically. No human needed.

**What changed:**
- `AntiIdlingSystem` gained `action_handlers` registry with `register_action_handler()`
- `detect_and_interrupt_idle_state()` now dispatches actions and returns what was executed
- Orchestrator registers 5 handlers at init (strategic_analysis, skill_development, research_sprint, experimental_prototype, feedback_loop)
- `_on_idle_triggered` callback upgraded from no-op log to actual improvement cycle
- `idle_check()` result now honestly reports `actions_proposed` vs `actions_executed`
- Fixed pre-existing lint (ruff) and type (mypy) errors in cost_governor and gateway_watchdog
- **330 tests passing**, ruff clean, mypy clean (0 errors across 11 source files)

**Bottom line:** Your AI agent detects it's stuck, figures out what to do, and does it. The feedback loop is now closed.

---

## 2025-02-23: README Redesign for Viral Sharing (v0.6)

Rewrote README around real-life problems first, technical details second. Every section opens with "the problem you're solving" before showing the solution. Designed for X/LinkedIn sharing — the hook is the pain point, not the architecture.

---

## 2025-02-22: Cost Governor Ships (v0.5)

**Headline result: 94.7% cost reduction** on real production OpenClaw setup.

Audits `openclaw.json` for model waste, heartbeat overhead, bootstrap bloat, and weak compaction. Three optimization strategies (aggressive/balanced/conservative). Honest compound savings calculation — no overpromising. Baseline tracking for governance over time.

---

## 2025-02-21: Gateway Watchdog Installer (v0.4)

One-command setup: `make install-watchdog`. Handles macOS TCC sandbox issues, deploys to `~/.openclaw/scripts/` with system Python, manages cron idempotently. Gateway crashes at 3 AM? Restarted in under 5 minutes. You sleep through it.

---

## 2025-02-20: Reflection Quality Overhaul (v0.3)

Daily reflections upgraded from generic summaries to data-driven reports. Git commit detail per repo, achievement extraction from commit messages, score breakdown (accuracy/efficiency/adaptability), trend comparison vs previous day, smart prioritization.

---

## 2025-02-19: Dead Code Cleanup + SIGTERM Handling (v0.2)

Removed dead code, synced deps, fixed hardcoded values. Added SIGTERM handler for clean daemon shutdown. Daemon loop now survives per-cycle errors without crashing.

---

## 2025-02-18: Orchestrator + Real Implementations (v0.1)

Foundation release. Wired all 4 self-optimization systems (anti-idling, performance tracking, self-improvement, results verification) through a central orchestrator. Added filesystem scanner for real activity detection. Config-driven multi-agent support. State persistence with atomic writes. CLI entry point with idle-check, daily-review, status, and daemon mode.
