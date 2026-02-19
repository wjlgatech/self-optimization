"""Orchestrator: wires all 4 self-optimization systems together.

Provides state persistence, idle checking, daily review, daemon mode,
multi-agent support, and monitoring config integration.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from anti_idling_system import AntiIdlingSystem
from config_loader import load_monitoring_config
from filesystem_scanner import FilesystemScanner
from llm_provider import LLMProvider
from multi_agent_performance import MultiAgentPerformanceOptimizer
from recursive_self_improvement import RecursiveSelfImprovementProtocol
from results_verification import ResultsVerificationFramework

logger = logging.getLogger(__name__)


class StateManager:
    """JSON-file-based state persistence."""

    def __init__(self, state_dir: str) -> None:
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)

    def save(self, key: str, data: Any) -> None:
        """Save data to a JSON file."""
        filepath = os.path.join(self.state_dir, f"{key}.json")
        tmp = filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, filepath)

    def load(self, key: str, default: Any = None) -> Any:
        """Load data from a JSON file. Returns default if missing."""
        filepath = os.path.join(self.state_dir, f"{key}.json")
        if not os.path.isfile(filepath):
            return default
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load state %s: %s", key, e)
            return default


class SelfOptimizationOrchestrator:
    """Integration layer wiring all 4 self-optimization systems."""

    def __init__(
        self,
        state_dir: str = "",
        workspace_dir: str = "",
        agent_id: str = "loopy-0",
        idle_threshold: float = 0.10,
        quality_threshold: float = 0.85,
        config_path: str = "",
    ) -> None:
        # Resolve directories
        if not workspace_dir:
            workspace_dir = os.path.expanduser("~/.openclaw/workspace")
        if not state_dir:
            state_dir = os.path.join(workspace_dir, "self-optimization", "state")

        self.workspace_dir = workspace_dir
        self.agent_id = agent_id
        self._daemon_running = False

        # Load monitoring config (agent names, thresholds, intervention tiers)
        self.config = load_monitoring_config(config_path)

        # Apply config thresholds if they override defaults
        gcr = self.config.get("thresholds", {}).get("goal_completion_rate", {})
        if gcr.get("warning"):
            quality_threshold = gcr["warning"]  # use warning level as quality bar

        # State persistence
        self.state = StateManager(state_dir)

        # Create all 4 systems
        self.anti_idling = AntiIdlingSystem(
            idle_threshold=idle_threshold, minimum_productive_actions=10
        )
        self.performance = MultiAgentPerformanceOptimizer(quality_threshold=quality_threshold)
        self.improvement = RecursiveSelfImprovementProtocol()
        self.verification = ResultsVerificationFramework()

        # Scanner and LLM
        self.scanner = FilesystemScanner(workspace_dir=workspace_dir)
        self.llm = LLMProvider()

        # Register all agents from config (or just the current one)
        self._agent_ids: Dict[str, str] = {}  # agent_name -> internal perf ID
        config_agents = self.config.get("agents", [])
        if agent_id not in config_agents:
            config_agents = [agent_id] + config_agents

        for name in config_agents:
            internal_id = self.performance.register_agent(
                {"name": name, "type": "autonomous"}
            )
            self._agent_ids[name] = internal_id

        self._agent_internal_id = self._agent_ids[agent_id]

        # Wire idle callback to improvement cycle
        self.anti_idling.register_intervention_callback(self._on_idle_triggered)

        # Restore persisted state
        self._restore_state()

    def idle_check(self) -> Dict[str, Any]:
        """Run an idle check: scan filesystem, assess idle rate, take action if needed.

        Returns dict with: timestamp, idle_rate, triggered, actions_taken, activities_found.
        """
        now = datetime.now().isoformat()
        result: Dict[str, Any] = {
            "timestamp": now,
            "idle_rate": 0.0,
            "triggered": False,
            "actions_taken": [],
            "activities_found": 0,
        }

        # 1. Scan real filesystem activity (last 2 hours)
        activities = self.scanner.scan_activity(hours=2)
        result["activities_found"] = len(activities)

        # 2. Feed activities into anti-idling system
        for activity in activities:
            self.anti_idling.log_activity(activity)

        # 3. Calculate idle rate from real data
        idle_rate = self.anti_idling.calculate_idle_rate(time_window=7200)
        result["idle_rate"] = idle_rate

        # 4. Check if triggered
        if idle_rate > self.anti_idling.idle_threshold:
            result["triggered"] = True
            actions = self.anti_idling.generate_emergency_actions()
            result["actions_taken"] = actions

            # Also generate an improvement proposal
            proposals = self.improvement.generate_improvement_proposals()
            if proposals:
                self.improvement.execute_improvement(proposals[0])
                result["improvement_proposal"] = proposals[0]

        # 5. Persist state
        self._persist_state()
        self.state.save("last_run", {"type": "idle_check", "timestamp": now, "result": result})

        logger.info(
            "Idle check: rate=%.2f triggered=%s activities=%d",
            idle_rate,
            result["triggered"],
            len(activities),
        )
        return result

    def daily_review(self) -> Dict[str, Any]:
        """Run a full daily review: scan, analyze, reflect, improve.

        Returns comprehensive review dict.
        """
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")

        review: Dict[str, Any] = {
            "timestamp": now,
            "date": today,
            "activities_found": 0,
            "performance_report": {},
            "capability_gaps": {},
            "improvement_executed": None,
            "reflection_path": "",
            "verification": {},
        }

        # 1. Scan 24h of activity
        activities = self.scanner.scan_activity(hours=24)
        review["activities_found"] = len(activities)

        # 2. Feed activities into systems
        productive_count = 0
        for activity in activities:
            self.anti_idling.log_activity(activity)
            if activity.get("is_productive", False):
                productive_count += 1

        # 3. Update performance metrics
        perf_data = {
            "accuracy": min(1.0, productive_count / max(1, len(activities))),
            "efficiency": min(1.0, len(activities) / 100.0),
            "adaptability": 0.7,  # baseline
        }
        self.performance.update_agent_performance(self._agent_internal_id, perf_data)

        # 4. Generate performance report
        review["performance_report"] = self.performance.generate_performance_report()

        # 5. Verify report quality via SMARC
        verification_input = {
            "total_activities": len(activities),
            "productive_activities": productive_count,
            "next_step": "review and adjust priorities",
            "recommendation": "continue current trajectory"
            if productive_count > len(activities) * 0.5
            else "increase productive output",
            "details": [{"metric": "activities", "value": len(activities)}],
        }
        review["verification"] = self.verification.verify_results(verification_input)

        # 6. Identify capability gaps
        review["capability_gaps"] = self.improvement._identify_capability_gaps()

        # 6b. Assess intervention tier from config thresholds
        review["intervention"] = self.get_intervention_tier()

        # 7. Generate and execute top improvement proposal
        proposals = self.improvement.generate_improvement_proposals()
        if proposals:
            self.improvement.execute_improvement(proposals[0])
            review["improvement_executed"] = proposals[0]

        # 8. Write daily reflection
        reflection_path = self._write_reflection(today, review, activities)
        review["reflection_path"] = reflection_path

        # 9. Persist state
        self._persist_state()
        self.state.save("last_run", {"type": "daily_review", "timestamp": now})

        logger.info(
            "Daily review complete: %d activities, reflection at %s",
            len(activities),
            reflection_path,
        )
        return review

    def run_daemon(self, idle_interval: int = 7200, review_hour: int = 23) -> None:
        """Run as a long-lived daemon: idle checks on interval, daily review once."""
        self._daemon_running = True
        last_review_date = ""
        logger.info("Daemon started: idle every %ds, review at hour %d", idle_interval, review_hour)

        while self._daemon_running:
            try:
                # Idle check
                self.idle_check()

                # Daily review (once per day at the specified hour)
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                if now.hour >= review_hour and last_review_date != today:
                    self.daily_review()
                    last_review_date = today

            except Exception as e:
                logger.error("Daemon cycle error: %s", e)

            time.sleep(idle_interval)

    def stop_daemon(self) -> None:
        """Stop the daemon loop."""
        self._daemon_running = False

    def log_activity(self, activity: Dict[str, Any]) -> None:
        """External API for bots to log activities explicitly."""
        self.anti_idling.log_activity(activity)

    def status(self) -> Dict[str, Any]:
        """Return current system status."""
        last_run = self.state.load("last_run", {})
        return {
            "agent_id": self.agent_id,
            "workspace_dir": self.workspace_dir,
            "activity_log_size": len(self.anti_idling.activity_log),
            "registered_agents": len(self.performance.agents),
            "all_agents": list(self._agent_ids.keys()),
            "capability_count": len(self.improvement.capability_map),
            "improvement_history_size": len(self.improvement.improvement_history),
            "verification_history_size": len(self.verification.verification_history),
            "llm_available": self.llm.available,
            "last_run": last_run,
            "daemon_running": self._daemon_running,
            "config": {
                "thresholds": self.config.get("thresholds", {}),
                "monitoring_interval": self.config.get("monitoring_interval", ""),
            },
        }

    def get_intervention_tier(self, agent_name: str = "") -> Dict[str, Any]:
        """Determine intervention tier for an agent based on config thresholds.

        Returns: {tier, actions, reason} or {tier: "none"} if performance is OK.
        """
        if not agent_name:
            agent_name = self.agent_id

        internal_id = self._agent_ids.get(agent_name)
        if not internal_id or internal_id not in self.performance.agents:
            return {"tier": "unknown", "reason": f"Agent {agent_name} not found"}

        score = self.performance.agents[internal_id].get("performance_score", 0.0)
        thresholds = self.config.get("thresholds", {})
        tiers = self.config.get("intervention_tiers", {})

        gcr = thresholds.get("goal_completion_rate", {})
        critical = gcr.get("critical", 0.5)
        warning = gcr.get("warning", 0.7)

        if score < critical:
            tier_data = tiers.get("tier3", {})
            return {
                "tier": "tier3",
                "score": score,
                "actions": tier_data.get("actions", []),
                "duration": tier_data.get("duration", ""),
                "reason": f"Score {score:.2f} below critical threshold {critical}",
            }
        if score < warning:
            tier_data = tiers.get("tier2", {})
            return {
                "tier": "tier2",
                "score": score,
                "actions": tier_data.get("actions", []),
                "duration": tier_data.get("duration", ""),
                "reason": f"Score {score:.2f} below warning threshold {warning}",
            }

        return {"tier": "none", "score": score, "reason": "Performance within acceptable range"}

    def _on_idle_triggered(self) -> None:
        """Callback fired when idle state is detected."""
        logger.warning("Idle state triggered for agent %s", self.agent_id)

    def _write_reflection(
        self,
        date: str,
        review: Dict[str, Any],
        activities: List[Dict[str, Any]],
    ) -> str:
        """Write a daily reflection markdown file."""
        reflection_dir = os.path.join(self.workspace_dir, "memory", "daily-reflections")
        os.makedirs(reflection_dir, exist_ok=True)
        filepath = os.path.join(reflection_dir, f"{date}-reflection.md")

        # Count activity types
        type_counts: Dict[str, int] = {}
        for a in activities:
            atype = a.get("type", "unknown")
            type_counts[atype] = type_counts.get(atype, 0) + 1

        perf_report = review.get("performance_report", {})
        avg_perf = perf_report.get("average_performance", 0.0)
        gaps = review.get("capability_gaps", {})

        # Try LLM-enhanced reflection
        llm_narrative = ""
        if self.llm.available:
            context = (
                f"Activities found: {len(activities)}\n"
                f"Activity types: {type_counts}\n"
                f"Average performance: {avg_perf:.2f}\n"
                f"Capability gaps: {gaps}\n"
            )
            llm_narrative = self.llm.analyze(
                "Write a brief, honest daily reflection for an AI agent. "
                "Include achievements, challenges, and priorities for tomorrow. "
                "Be concise (under 200 words).",
                context=context,
                max_tokens=512,
            )

        # Build markdown
        lines = [
            f"# Daily Reflection - {date}",
            "",
            "## Activity Summary",
            f"- Total activities detected: {len(activities)}",
        ]
        for atype, count in sorted(type_counts.items()):
            lines.append(f"- {atype}: {count}")

        lines.extend(
            [
                "",
                "## Performance",
                f"- Average score: {avg_perf:.2f}",
                f"- Quality threshold: {self.performance.quality_threshold}",
            ]
        )

        if gaps.get("missing_capabilities"):
            lines.extend(
                [
                    "",
                    "## Capability Gaps",
                ]
            )
            for cap in gaps["missing_capabilities"]:
                lines.append(f"- Missing: {cap}")
        if gaps.get("low_performance_areas"):
            for cap in gaps["low_performance_areas"]:
                lines.append(f"- Low proficiency: {cap}")

        if review.get("improvement_executed"):
            lines.extend(
                [
                    "",
                    "## Improvement Executed",
                    f"- Type: {review['improvement_executed'].get('type', 'unknown')}",
                ]
            )

        if llm_narrative:
            lines.extend(
                [
                    "",
                    "## AI Reflection",
                    llm_narrative,
                ]
            )

        lines.extend(
            [
                "",
                "## Tomorrow's Priorities",
                "1. Address capability gaps",
                "2. Maintain productive output",
                "3. Continue self-improvement cycle",
                "",
                f"---\n*Generated by self-optimization system at {review['timestamp']}*",
            ]
        )

        content = "\n".join(lines) + "\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def _persist_state(self) -> None:
        """Save system state to disk."""
        self.state.save("activity_log", self.anti_idling.activity_log)
        self.state.save("performance_history", self.performance.performance_history)
        self.state.save("improvement_history", self.improvement.improvement_history)
        self.state.save("capability_map", self.improvement.capability_map)

    def _restore_state(self) -> None:
        """Restore system state from disk."""
        activity_log = self.state.load("activity_log")
        if isinstance(activity_log, list):
            self.anti_idling.activity_log = activity_log

        perf_history = self.state.load("performance_history")
        if isinstance(perf_history, list):
            self.performance.performance_history = perf_history

        imp_history = self.state.load("improvement_history")
        if isinstance(imp_history, list):
            self.improvement.improvement_history = imp_history

        cap_map = self.state.load("capability_map")
        if isinstance(cap_map, dict):
            self.improvement.capability_map = cap_map
