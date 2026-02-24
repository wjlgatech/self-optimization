"""Cost Governor: monitors and optimizes OpenClaw token/cost usage.

Audits openclaw.json configuration, measures bootstrap file bloat,
generates optimized config patches, tracks baselines, and runs
a periodic governance loop to keep costs down by 90%+.

Strategy:
  A) Make most tokens cheap — route ~80-95% of turns to cheap/local model
  B) Make every turn smaller — shrink bootstrap files, compact early, prune tool output
  C) Prompt caching — stable prefixes get cached at ~90% discount
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Model cost tiers ($/1M input tokens, approximate) ---
MODEL_COSTS: Dict[str, Dict[str, float]] = {
    # Expensive tier ($10-15/M input)
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "anthropic/claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "anthropic/claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "openai/gpt-4o": {"input": 2.5, "output": 10.0},
    # Mid tier ($0.5-3/M input)
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
    "anthropic/claude-haiku-4-5": {"input": 0.8, "output": 4.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-mini": {"input": 0.15, "output": 0.6},
    # Cheap/local tier ($0/M)
    "ollama/llama3.3": {"input": 0.0, "output": 0.0},
    "ollama/llama3.2": {"input": 0.0, "output": 0.0},
    "ollama/mistral": {"input": 0.0, "output": 0.0},
    "ollama/qwen2.5": {"input": 0.0, "output": 0.0},
    "ollama/deepseek-r1": {"input": 0.0, "output": 0.0},
}

EXPENSIVE_MODELS = {
    m for m, c in MODEL_COSTS.items() if c["input"] >= 10.0
}
MID_TIER_MODELS = {
    m for m, c in MODEL_COSTS.items() if 0.1 <= c["input"] < 10.0
}
CHEAP_MODELS = {
    m for m, c in MODEL_COSTS.items() if c["input"] < 0.1
}

# Recommended defaults
RECOMMENDED_BOOTSTRAP_MAX_CHARS = 8000
RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS = 30000
# OpenClaw compaction modes: "default" (more eagerly) or "safeguard" (only near limit)
RECOMMENDED_COMPACTION_MODE = "default"
RECOMMENDED_HEARTBEAT_INTERVAL = "6h"

# Default OpenClaw caps
DEFAULT_BOOTSTRAP_MAX_CHARS = 20000
DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS = 150000

# Bootstrap files that get auto-injected
BOOTSTRAP_FILES = [
    "AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md",
    "USER.md", "HEARTBEAT.md", "MEMORY.md", "BOOTSTRAP.md",
    "TASKLOG.md",
]


class CostGovernor:
    """Monitors and optimizes OpenClaw token/cost usage."""

    def __init__(
        self,
        config_path: str = "",
        workspace_dir: str = "",
        state_dir: str = "",
    ) -> None:
        if not config_path:
            config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if not workspace_dir:
            workspace_dir = os.path.expanduser("~/.openclaw/workspace")
        if not state_dir:
            state_dir = os.path.expanduser(
                "~/.openclaw/workspace/self-optimization/state"
            )

        self.config_path = config_path
        self.workspace_dir = workspace_dir
        self.state_dir = state_dir
        self._state_file = os.path.join(state_dir, "cost_governor.json")
        os.makedirs(state_dir, exist_ok=True)

        self._config = self._load_config()

    # --- Config loading ---

    def _load_config(self) -> Dict[str, Any]:
        """Load ~/.openclaw/openclaw.json."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load openclaw config: %s", e)
            return {}

    def _get_nested(self, *keys: str, default: Any = None) -> Any:
        """Safely traverse nested config keys."""
        obj: Any = self._config
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k)
            else:
                return default
            if obj is None:
                return default
        return obj

    # --- Bootstrap file analysis ---

    def measure_bootstrap_files(self) -> Dict[str, Any]:
        """Measure size of all auto-injected bootstrap/workspace files."""
        files: List[Dict[str, Any]] = []
        total_chars = 0
        total_lines = 0

        for fname in BOOTSTRAP_FILES:
            fpath = os.path.join(self.workspace_dir, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    chars = len(content)
                    has_trailing = content and not content.endswith("\n")
                    lines = content.count("\n") + (1 if has_trailing else 0)
                    # Rough token estimate: ~4 chars per token for English
                    est_tokens = chars // 4
                    files.append({
                        "file": fname,
                        "chars": chars,
                        "lines": lines,
                        "est_tokens": est_tokens,
                        "path": fpath,
                    })
                    total_chars += chars
                    total_lines += lines
                except OSError:
                    pass

        # Sort by size descending
        files.sort(key=lambda f: f["chars"], reverse=True)

        bootstrap_max = self._get_nested(
            "agents", "defaults", "bootstrapMaxChars",
            default=DEFAULT_BOOTSTRAP_MAX_CHARS,
        )
        bootstrap_total_max = self._get_nested(
            "agents", "defaults", "bootstrapTotalMaxChars",
            default=DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS,
        )

        return {
            "files": files,
            "total_chars": total_chars,
            "total_lines": total_lines,
            "total_est_tokens": total_chars // 4,
            "configured_max_per_file": bootstrap_max,
            "configured_total_max": bootstrap_total_max,
            "recommended_max_per_file": RECOMMENDED_BOOTSTRAP_MAX_CHARS,
            "recommended_total_max": RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS,
        }

    # --- Core audit ---

    def audit(self) -> Dict[str, Any]:
        """Analyze current config for cost waste.

        Returns findings (issues found), recommendations (what to change),
        and estimated savings potential.
        """
        findings: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        # 1. Check current model
        current_model = self._detect_current_model()
        model_cost = MODEL_COSTS.get(current_model, {})
        if current_model in EXPENSIVE_MODELS:
            findings.append({
                "id": "expensive_model",
                "severity": "critical",
                "title": "Default model is expensive tier",
                "detail": (
                    f"Current model: {current_model} "
                    f"(${model_cost.get('input', '?')}/M input, "
                    f"${model_cost.get('output', '?')}/M output)"
                ),
            })
            recommendations.append({
                "id": "switch_default_model",
                "impact": "high",
                "title": "Switch default model to cheap/local",
                "detail": (
                    "Route 80-95% of turns to a cheap model. "
                    "Set agents.defaults.model.primary to 'ollama/llama3.3' "
                    "(free) or 'claude-haiku-4-5' ($0.80/M). "
                    "Escalate to expensive model only for complex tasks."
                ),
                "savings_pct": 80,
                "config_patch": {
                    "agents.defaults.model.primary": "claude-haiku-4-5",
                },
            })
        elif current_model in MID_TIER_MODELS:
            findings.append({
                "id": "mid_tier_model",
                "severity": "info",
                "title": "Default model is mid-tier",
                "detail": f"Current model: {current_model} — reasonable, but local is free.",
            })

        # 2. Check bootstrap file bloat
        bootstrap = self.measure_bootstrap_files()
        if bootstrap["total_chars"] > RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS:
            findings.append({
                "id": "bootstrap_bloat",
                "severity": "warning",
                "title": "Bootstrap files exceed recommended size",
                "detail": (
                    f"Total: {bootstrap['total_chars']:,} chars "
                    f"(~{bootstrap['total_est_tokens']:,} tokens) — "
                    f"re-sent every turn. "
                    f"Recommended: <{RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS:,} chars."
                ),
            })
            # Find the biggest offenders
            big_files = [f for f in bootstrap["files"] if f["chars"] > 3000]
            if big_files:
                names = ", ".join(f["file"] for f in big_files[:3])
                recommendations.append({
                    "id": "shrink_bootstrap",
                    "impact": "medium",
                    "title": "Put bootstrap files on a token diet",
                    "detail": (
                        f"Biggest files: {names}. "
                        "Move long policies/docs to on-demand memory/*.md files. "
                        "Keep AGENTS.md to 1-2 pages of operating rules."
                    ),
                    "savings_pct": 20,
                    "config_patch": {
                        "agents.defaults.bootstrapMaxChars": RECOMMENDED_BOOTSTRAP_MAX_CHARS,
                    },
                })

        # 3. Check bootstrap caps
        current_max = self._get_nested(
            "agents", "defaults", "bootstrapMaxChars",
            default=DEFAULT_BOOTSTRAP_MAX_CHARS,
        )
        current_total_max = self._get_nested(
            "agents", "defaults", "bootstrapTotalMaxChars",
            default=DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS,
        )
        if current_total_max > RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS:
            findings.append({
                "id": "high_bootstrap_cap",
                "severity": "warning",
                "title": "Bootstrap caps are too generous",
                "detail": (
                    f"bootstrapMaxChars={current_max:,}, "
                    f"bootstrapTotalMaxChars={current_total_max:,}. "
                    f"Recommended: {RECOMMENDED_BOOTSTRAP_MAX_CHARS:,} / "
                    f"{RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS:,}."
                ),
            })

        # 4. Check compaction mode
        compaction_mode = self._get_nested(
            "agents", "defaults", "compaction", "mode",
            default="safeguard",
        )
        if compaction_mode == "safeguard":
            findings.append({
                "id": "weak_compaction",
                "severity": "warning",
                "title": f"Compaction mode is '{compaction_mode}' (not default)",
                "detail": (
                    "'default' compaction summarizes earlier conversation "
                    "more eagerly, preventing token growth. "
                    "'safeguard' only triggers near the context limit."
                ),
            })
            recommendations.append({
                "id": "aggressive_compaction",
                "impact": "medium",
                "title": "Switch compaction to default",
                "detail": (
                    "Set agents.defaults.compaction.mode to 'default'. "
                    "Compacts earlier, keeping tokens/turn stable over time."
                ),
                "savings_pct": 30,
                "config_patch": {
                    "agents.defaults.compaction.mode": "default",
                },
            })

        # 5. Check heartbeat config
        heartbeat_model = self._get_nested(
            "agents", "defaults", "heartbeat", "model"
        )
        if heartbeat_model and heartbeat_model in EXPENSIVE_MODELS:
            findings.append({
                "id": "expensive_heartbeat",
                "severity": "warning",
                "title": "Heartbeat uses expensive model",
                "detail": (
                    f"Heartbeat model: {heartbeat_model}. "
                    "Heartbeats are full agent turns — should use cheapest model."
                ),
            })
            recommendations.append({
                "id": "cheap_heartbeat",
                "impact": "medium",
                "title": "Switch heartbeat to cheap model",
                "detail": (
                    "Set agents.defaults.heartbeat.model to a mini model. "
                    "Heartbeats don't need genius-level reasoning."
                ),
                "savings_pct": 15,
                "config_patch": {
                    "agents.defaults.heartbeat.model": "claude-haiku-4-5",
                },
            })
        # If no heartbeat model is explicitly set, the primary is used
        elif heartbeat_model is None and current_model in EXPENSIVE_MODELS:
            findings.append({
                "id": "heartbeat_inherits_expensive",
                "severity": "warning",
                "title": "Heartbeat inherits expensive primary model",
                "detail": (
                    f"No heartbeat.model set — inherits '{current_model}'. "
                    "Each heartbeat turn costs as much as a real user turn."
                ),
            })
            recommendations.append({
                "id": "set_heartbeat_model",
                "impact": "medium",
                "title": "Set explicit cheap heartbeat model",
                "detail": (
                    "Set agents.defaults.heartbeat.model to 'claude-haiku-4-5' "
                    "or 'gpt-4o-mini'. Heartbeats check inbox/calendar — trivial work."
                ),
                "savings_pct": 15,
                "config_patch": {
                    "agents.defaults.heartbeat.model": "claude-haiku-4-5",
                },
            })

        # 6. Check concurrent agents (more agents = more cost)
        max_concurrent = self._get_nested(
            "agents", "defaults", "maxConcurrent", default=1,
        )
        max_subagents = self._get_nested(
            "agents", "defaults", "subagents", "maxConcurrent", default=1,
        )
        if max_concurrent > 2 or max_subagents > 4:
            findings.append({
                "id": "high_concurrency",
                "severity": "info",
                "title": "High agent concurrency may multiply costs",
                "detail": (
                    f"maxConcurrent={max_concurrent}, "
                    f"subagents.maxConcurrent={max_subagents}. "
                    "Each concurrent agent burns tokens independently."
                ),
            })

        # Calculate overall estimated savings
        total_savings = _estimate_total_savings(recommendations)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_model": current_model,
            "model_cost_per_m_input": model_cost.get("input", 0),
            "bootstrap_total_chars": bootstrap["total_chars"],
            "bootstrap_est_tokens": bootstrap["total_est_tokens"],
            "findings": findings,
            "recommendations": recommendations,
            "estimated_savings_pct": total_savings,
            "bootstrap_detail": bootstrap,
        }

    def _detect_current_model(self) -> str:
        """Detect the current primary model from config or gateway logs."""
        # Check config first
        model = self._get_nested("agents", "defaults", "model", "primary")
        if model:
            return model  # type: ignore[no-any-return]

        # Try to parse from gateway log
        log_path = os.path.expanduser("~/.openclaw/logs/gateway.log")
        if os.path.isfile(log_path):
            try:
                with open(log_path, "rb") as f:
                    # Read last 5KB — model line is near recent startup
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 5000))
                    raw = f.read()
                tail = raw.decode("utf-8", errors="replace")
                for line in reversed(tail.splitlines()):
                    if "agent model:" in line:
                        # e.g. "[gateway] agent model: anthropic/claude-opus-4-6"
                        return line.split("agent model:")[-1].strip()
                return ""
            except OSError:
                pass
        return "unknown"

    # --- Config optimization ---

    def generate_optimized_config(
        self, strategy: str = "balanced"
    ) -> Dict[str, Any]:
        """Generate an optimized openclaw.json patch.

        Strategies:
          - "aggressive": maximize savings (local model, tight caps, aggressive compaction)
          - "balanced": good savings without quality loss (cheap cloud + tight caps)
          - "conservative": minimal changes (keep current model, just trim waste)
        """
        audit_result = self.audit()
        patch: Dict[str, Any] = {}
        explanations: List[str] = []

        if strategy == "aggressive":
            patch = {
                "agents": {
                    "defaults": {
                        "model": {"primary": "ollama/llama3.3"},
                        "compaction": {"mode": "default"},
                        "bootstrapMaxChars": 6000,
                        "heartbeat": {
                            "model": "ollama/llama3.3",
                            "every": "6h",
                        },
                    }
                }
            }
            explanations = [
                "Primary model → ollama/llama3.3 (free, runs locally)",
                "Compaction → default (compacts earlier than safeguard)",
                "Bootstrap cap → 6K chars per file (strict token diet)",
                "Heartbeat → local model, every 6 hours",
            ]

        elif strategy == "balanced":
            patch = {
                "agents": {
                    "defaults": {
                        "model": {"primary": "claude-haiku-4-5"},
                        "compaction": {"mode": "default"},
                        "bootstrapMaxChars": RECOMMENDED_BOOTSTRAP_MAX_CHARS,
                        "heartbeat": {
                            "model": "claude-haiku-4-5",
                            "every": "4h",
                        },
                    }
                }
            }
            explanations = [
                "Primary model → claude-haiku-4-5 ($0.80/M — 19x cheaper than Opus)",
                "Compaction → default (compacts earlier than safeguard)",
                f"Bootstrap cap → {RECOMMENDED_BOOTSTRAP_MAX_CHARS:,} chars per file",
                "Heartbeat → Haiku, every 4 hours",
            ]

        elif strategy == "conservative":
            patch = {
                "agents": {
                    "defaults": {
                        "compaction": {"mode": "default"},
                        "bootstrapMaxChars": RECOMMENDED_BOOTSTRAP_MAX_CHARS,
                    }
                }
            }
            # Add heartbeat fix only if needed
            current_model = self._detect_current_model()
            if current_model in EXPENSIVE_MODELS:
                patch["agents"]["defaults"]["heartbeat"] = {
                    "model": "claude-haiku-4-5",
                }
                explanations.append(
                    "Heartbeat model → Haiku (stops burning Opus tokens on inbox checks)"
                )
            explanations.extend([
                "Compaction → default (compacts earlier than safeguard)",
                f"Bootstrap cap → {RECOMMENDED_BOOTSTRAP_MAX_CHARS:,} chars per file",
                "Primary model unchanged — only trimming waste",
            ])

        return {
            "strategy": strategy,
            "patch": patch,
            "explanations": explanations,
            "current_model": audit_result["current_model"],
            "estimated_savings_pct": audit_result["estimated_savings_pct"],
        }

    def apply_config(
        self, patch: Dict[str, Any], backup: bool = True
    ) -> Dict[str, Any]:
        """Apply a config patch to openclaw.json.

        Deep-merges the patch into the existing config. Creates a backup first.
        """
        if backup:
            backup_path = self.config_path + ".pre-governor.bak"
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    original = f.read()
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(original)
                logger.info("Backed up config to %s", backup_path)
            except OSError as e:
                return {"success": False, "error": f"Backup failed: {e}"}

        # Deep merge
        merged = _deep_merge(self._config, patch)

        # Atomic write
        try:
            tmp = self.config_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
                f.write("\n")
            os.replace(tmp, self.config_path)
        except OSError as e:
            return {"success": False, "error": f"Write failed: {e}"}

        # Reload
        self._config = merged

        return {
            "success": True,
            "backup_path": backup_path if backup else None,
            "keys_changed": _list_changed_keys(patch),
        }

    # --- Baseline tracking ---

    def record_baseline(self, label: str = "manual") -> Dict[str, Any]:
        """Capture current state as a baseline for future comparison."""
        audit_result = self.audit()
        baseline = {
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": audit_result["current_model"],
            "model_cost_per_m_input": audit_result["model_cost_per_m_input"],
            "bootstrap_total_chars": audit_result["bootstrap_total_chars"],
            "bootstrap_est_tokens": audit_result["bootstrap_est_tokens"],
            "compaction_mode": self._get_nested(
                "agents", "defaults", "compaction", "mode", default="safeguard"
            ),
            "bootstrap_max_chars": self._get_nested(
                "agents", "defaults", "bootstrapMaxChars",
                default=DEFAULT_BOOTSTRAP_MAX_CHARS,
            ),
            "bootstrap_total_max_chars": self._get_nested(
                "agents", "defaults", "bootstrapTotalMaxChars",
                default=DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS,
            ),
            "findings_count": len(audit_result["findings"]),
        }

        state = self._load_state()
        baselines = state.get("baselines", [])
        baselines.append(baseline)
        baselines = baselines[-20:]  # Keep last 20
        state["baselines"] = baselines
        self._save_state(state)

        return baseline

    def get_baselines(self) -> List[Dict[str, Any]]:
        """Return all recorded baselines."""
        state = self._load_state()
        result: List[Dict[str, Any]] = state.get("baselines", [])
        return result

    # --- Governor loop ---

    def run_governor(self) -> Dict[str, Any]:
        """Full governor cycle: audit current state, compare to baseline,
        recommend actions, log results.

        This is designed to be called periodically (e.g., every 20 turns or daily).
        """
        now = datetime.now(timezone.utc).isoformat()
        audit_result = self.audit()

        # Load previous state for comparison
        state = self._load_state()
        baselines = state.get("baselines", [])
        initial_baseline = baselines[0] if baselines else None

        actions_taken: List[str] = []
        alerts: List[str] = []

        # Check 1: Model cost drift
        if audit_result["current_model"] in EXPENSIVE_MODELS:
            alerts.append(
                f"Expensive model in use: {audit_result['current_model']} "
                f"(${audit_result['model_cost_per_m_input']}/M input)"
            )

        # Check 2: Bootstrap bloat drift (compare to baseline if available)
        if initial_baseline:
            baseline_chars = initial_baseline.get("bootstrap_total_chars", 0)
            current_chars = audit_result["bootstrap_total_chars"]
            if baseline_chars > 0 and current_chars > baseline_chars * 1.2:
                alerts.append(
                    f"Bootstrap bloat: {current_chars:,} chars "
                    f"(+{((current_chars / baseline_chars) - 1) * 100:.0f}% vs baseline)"
                )

        # Check 3: Compaction still optimal
        compaction = self._get_nested(
            "agents", "defaults", "compaction", "mode", default="safeguard"
        )
        if compaction == "safeguard":
            alerts.append(f"Compaction mode '{compaction}' — should be 'default'")

        # Build result
        result: Dict[str, Any] = {
            "timestamp": now,
            "status": "healthy" if not alerts else "needs_attention",
            "current_model": audit_result["current_model"],
            "bootstrap_total_chars": audit_result["bootstrap_total_chars"],
            "bootstrap_est_tokens": audit_result["bootstrap_est_tokens"],
            "compaction_mode": compaction,
            "findings_count": len(audit_result["findings"]),
            "alerts": alerts,
            "actions_taken": actions_taken,
            "estimated_savings_pct": audit_result["estimated_savings_pct"],
            "recommendations_count": len(audit_result["recommendations"]),
        }

        # Save governor run
        history = state.get("governor_history", [])
        history.append(result)
        history = history[-50:]
        state["governor_history"] = history
        state["last_governor_run"] = result
        self._save_state(state)

        return result

    # --- Status ---

    def status(self) -> Dict[str, Any]:
        """Return current cost governance status and history summary."""
        state = self._load_state()
        history = state.get("governor_history", [])
        baselines = state.get("baselines", [])

        # Current snapshot
        current_model = self._detect_current_model()
        model_cost = MODEL_COSTS.get(current_model, {})
        bootstrap = self.measure_bootstrap_files()
        compaction = self._get_nested(
            "agents", "defaults", "compaction", "mode", default="safeguard"
        )

        # Compute savings vs first baseline
        savings_vs_baseline: Optional[Dict[str, Any]] = None
        if baselines:
            first = baselines[0]
            old_cost = first.get("model_cost_per_m_input", 0)
            new_cost = model_cost.get("input", 0)
            if old_cost > 0:
                cost_reduction = (1 - new_cost / old_cost) * 100
            else:
                cost_reduction = 0.0

            old_tokens = first.get("bootstrap_est_tokens", 0)
            new_tokens = bootstrap["total_est_tokens"]
            if old_tokens > 0:
                token_reduction = (1 - new_tokens / old_tokens) * 100
            else:
                token_reduction = 0.0

            savings_vs_baseline = {
                "baseline_date": first.get("timestamp", ""),
                "model_cost_reduction_pct": round(cost_reduction, 1),
                "bootstrap_token_reduction_pct": round(token_reduction, 1),
                "old_model": first.get("model", "unknown"),
                "new_model": current_model,
            }

        return {
            "current_model": current_model,
            "model_cost_per_m_input": model_cost.get("input", 0),
            "model_tier": (
                "expensive" if current_model in EXPENSIVE_MODELS
                else "mid" if current_model in MID_TIER_MODELS
                else "cheap/local" if current_model in CHEAP_MODELS
                else "unknown"
            ),
            "bootstrap_total_chars": bootstrap["total_chars"],
            "bootstrap_est_tokens": bootstrap["total_est_tokens"],
            "bootstrap_file_count": len(bootstrap["files"]),
            "compaction_mode": compaction,
            "governor_runs": len(history),
            "baselines_recorded": len(baselines),
            "savings_vs_baseline": savings_vs_baseline,
            "last_governor_run": state.get("last_governor_run"),
        }

    # --- State persistence ---

    def _load_state(self) -> Dict[str, Any]:
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            tmp = self._state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp, self._state_file)
        except OSError as e:
            logger.warning("Failed to save cost governor state: %s", e)


# --- Helpers ---

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base (returns new dict)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _list_changed_keys(
    patch: Dict[str, Any], prefix: str = ""
) -> List[str]:
    """Flatten a nested dict into dotted key paths."""
    keys: List[str] = []
    for k, v in patch.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_list_changed_keys(v, full))
        else:
            keys.append(full)
    return keys


def _estimate_total_savings(
    recommendations: List[Dict[str, Any]],
) -> int:
    """Estimate combined savings from all recommendations (not additive — diminishing)."""
    if not recommendations:
        return 0
    # Use 1 - product(1 - r) formula for non-additive savings
    remaining = 1.0
    for rec in recommendations:
        pct = rec.get("savings_pct", 0) / 100.0
        remaining *= (1.0 - pct)
    return min(95, int((1.0 - remaining) * 100))
