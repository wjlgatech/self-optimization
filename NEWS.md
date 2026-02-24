# NEWS

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
