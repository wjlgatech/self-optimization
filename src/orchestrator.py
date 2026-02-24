"""Orchestrator: wires all 4 self-optimization systems together.

Provides state persistence, idle checking, daily review, daemon mode,
multi-agent support, and monitoring config integration.
"""

import json
import logging
import os
import signal
import time
from datetime import datetime
from typing import Any

from anti_idling_system import AntiIdlingSystem
from config_loader import load_monitoring_config
from filesystem_scanner import FilesystemScanner
from gateway_watchdog import GatewayWatchdog
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
            with open(filepath, encoding="utf-8") as f:
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

        # Scanner, LLM, and gateway watchdog
        self.scanner = FilesystemScanner(workspace_dir=workspace_dir)
        self.llm = LLMProvider()
        self.watchdog = GatewayWatchdog(state_dir=state_dir)

        # Register all agents from config (or just the current one)
        self._agent_ids: dict[str, str] = {}  # agent_name -> internal perf ID
        config_agents = self.config.get("agents", [])
        if agent_id not in config_agents:
            config_agents = [agent_id] + config_agents

        for name in config_agents:
            internal_id = self.performance.register_agent({"name": name, "type": "autonomous"})
            self._agent_ids[name] = internal_id

        self._agent_internal_id = self._agent_ids[agent_id]

        # Wire idle callback to improvement cycle
        self.anti_idling.register_intervention_callback(self._on_idle_triggered)

        # Map emergency action names to concrete improvement proposals
        action_to_proposal = {
            "conduct_strategic_analysis": {
                "type": "strategic_analysis",
                "target": "problem_solving",
            },
            "explore_new_skill_development": {"type": "skill_development", "target": "learning"},
            "start_research_sprint": {"type": "research_sprint", "target": "task_execution"},
            "design_experimental_prototype": {
                "type": "experimental_prototype",
                "target": "learning",
            },
            "initiate_user_feedback_loop": {"type": "feedback_loop", "target": "communication"},
        }
        for action_name, proposal in action_to_proposal.items():
            self.anti_idling.register_action_handler(
                action_name,
                lambda p=proposal: self.improvement.execute_improvement(p),
            )

        # Restore persisted state
        self._restore_state()

    def idle_check(self) -> dict[str, Any]:
        """Run an idle check: scan filesystem, assess idle rate, take action if needed.

        Returns dict with: timestamp, idle_rate, triggered, actions_proposed,
        actions_executed, activities_found.
        """
        now = datetime.now().isoformat()
        result: dict[str, Any] = {
            "timestamp": now,
            "idle_rate": 0.0,
            "triggered": False,
            "actions_proposed": [],
            "actions_executed": [],
            "activities_found": 0,
            "service_health": {},
        }

        # 0. Check service health (gateway, enterprise, vite-ui)
        service_health = self.watchdog.check_all_services()
        result["service_health"] = service_health
        down_services = [
            name for name, h in service_health.items()
            if not h["healthy"] and h.get("critical", False)
        ]
        if down_services:
            logger.warning(
                "Critical services DOWN: %s — attempting restart",
                ", ".join(down_services),
            )
            result["services_down"] = down_services

        # 1. Scan real filesystem activity (last 2 hours)
        activities = self.scanner.scan_activity(hours=2)
        result["activities_found"] = len(activities)

        # 2. Feed activities into anti-idling system
        for activity in activities:
            self.anti_idling.log_activity(activity)

        # 3. Calculate idle rate from real data
        idle_rate = self.anti_idling.calculate_idle_rate(time_window=7200)
        result["idle_rate"] = idle_rate

        # 4. Check if triggered — dispatch actions through registered handlers
        if idle_rate > self.anti_idling.idle_threshold:
            result["triggered"] = True
            actions = self.anti_idling.generate_emergency_actions()
            result["actions_proposed"] = actions
            executed = self.anti_idling.detect_and_interrupt_idle_state()
            result["actions_executed"] = executed

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

    def daily_review(self) -> dict[str, Any]:
        """Run a full daily review: scan, analyze, reflect, improve.

        Returns comprehensive review dict.
        """
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")

        review: dict[str, Any] = {
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
        activity_types = {a.get("type", "unknown") for a in activities}
        adaptability = min(1.0, len(activity_types) / 5.0) if activities else 0.0

        perf_data = {
            "accuracy": min(1.0, productive_count / max(1, len(activities))),
            "efficiency": min(1.0, len(activities) / 100.0),
            "adaptability": adaptability,
        }
        self.performance.update_agent_performance(self._agent_internal_id, perf_data)
        review["perf_data"] = perf_data

        # 4. Seed capability_map from real activities so gap analysis reflects reality
        self._seed_capabilities_from_activities(activities)

        # 5. Generate performance report
        review["performance_report"] = self.performance.generate_performance_report()

        # 6. Verify report quality via SMARC
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

        # 7. Identify capability gaps (now meaningful since capabilities are seeded)
        review["capability_gaps"] = self.improvement._identify_capability_gaps()

        # 7b. Assess intervention tier from config thresholds
        review["intervention"] = self.get_intervention_tier()

        # 7c. Load previous day's performance for trend comparison
        review["previous_perf"] = self._load_previous_performance()

        # 8. Generate and execute top improvement proposal
        proposals = self.improvement.generate_improvement_proposals()
        if proposals:
            self.improvement.execute_improvement(proposals[0])
            review["improvement_executed"] = proposals[0]

        # 9. Write daily reflection
        reflection_path = self._write_reflection(today, review, activities)
        review["reflection_path"] = reflection_path

        # 10. Persist state
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

        # Handle SIGTERM for clean shutdown (e.g. when killed by process manager)
        def _handle_sigterm(signum: int, frame: Any) -> None:
            logger.info("Received SIGTERM, shutting down daemon")
            self._daemon_running = False

        signal.signal(signal.SIGTERM, _handle_sigterm)
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

    def log_activity(self, activity: dict[str, Any]) -> None:
        """External API for bots to log activities explicitly."""
        self.anti_idling.log_activity(activity)

    def status(self) -> dict[str, Any]:
        """Return current system status including service health."""
        last_run = self.state.load("last_run", {})
        service_health = self.watchdog.check_all_services()
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
            "service_health": service_health,
            "config": {
                "thresholds": self.config.get("thresholds", {}),
                "monitoring_interval": self.config.get("monitoring_interval", ""),
            },
        }

    def get_intervention_tier(self, agent_name: str = "") -> dict[str, Any]:
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
        """Callback fired when idle state is detected — runs an improvement cycle."""
        logger.warning(
            "Idle state triggered for agent %s — running improvement cycle",
            self.agent_id,
        )
        proposals = self.improvement.generate_improvement_proposals()
        if proposals:
            self.improvement.execute_improvement(proposals[0])

    def _seed_capabilities_from_activities(self, activities: list[dict[str, Any]]) -> None:
        """Seed capability_map from real activity data so gap analysis is meaningful.

        Maps activity types to capabilities:
        - git_commit, file_modification → task_execution
        - daily_reflection → self_monitoring
        - Multiple activity types → learning, problem_solving
        - Commits with messages containing 'fix', 'refactor' → problem_solving
        """
        cap_map = self.improvement.capability_map
        now_iso = datetime.now().isoformat()

        # Count activities by type
        type_counts: dict[str, int] = {}
        commit_subjects: list[str] = []
        for a in activities:
            atype = a.get("type", "unknown")
            type_counts[atype] = type_counts.get(atype, 0) + 1
            if atype == "git_commit":
                commit_subjects.append(a.get("description", "").lower())

        total = max(1, len(activities))

        # task_execution: based on commits + file modifications
        task_count = type_counts.get("git_commit", 0) + type_counts.get("file_modification", 0)
        if task_count > 0:
            prof = min(1.0, task_count / total)
            if (
                "task_execution" not in cap_map
                or cap_map["task_execution"].get("proficiency", 0) < prof
            ):
                cap_map["task_execution"] = {
                    "added_timestamp": now_iso,
                    "proficiency": prof,
                    "source": "activity_scan",
                    "evidence": f"{task_count} task activities out of {total}",
                }

        # self_monitoring: based on reflections + reviews
        monitor_count = type_counts.get("daily_reflection", 0)
        if monitor_count > 0:
            prof = min(1.0, 0.3 + monitor_count * 0.2)
            if (
                "self_monitoring" not in cap_map
                or cap_map["self_monitoring"].get("proficiency", 0) < prof
            ):
                cap_map["self_monitoring"] = {
                    "added_timestamp": now_iso,
                    "proficiency": prof,
                    "source": "activity_scan",
                    "evidence": f"{monitor_count} reflections found",
                }

        # problem_solving: based on fix/refactor/debug commits
        fix_count = sum(
            1
            for s in commit_subjects
            if any(w in s for w in ("fix", "refactor", "debug", "resolve", "patch"))
        )
        if fix_count > 0:
            prof = min(1.0, 0.2 + fix_count * 0.15)
            if (
                "problem_solving" not in cap_map
                or cap_map["problem_solving"].get("proficiency", 0) < prof
            ):
                cap_map["problem_solving"] = {
                    "added_timestamp": now_iso,
                    "proficiency": prof,
                    "source": "activity_scan",
                    "evidence": f"{fix_count} fix/refactor commits",
                }

        # learning: based on diversity of activity types
        activity_type_count = len(type_counts)
        if activity_type_count >= 2:
            prof = min(1.0, activity_type_count / 5.0)
            if "learning" not in cap_map or cap_map["learning"].get("proficiency", 0) < prof:
                cap_map["learning"] = {
                    "added_timestamp": now_iso,
                    "proficiency": prof,
                    "source": "activity_scan",
                    "evidence": f"{activity_type_count} distinct activity types",
                }

        # communication: based on commit message quality (non-trivial messages)
        meaningful_msgs = sum(1 for s in commit_subjects if len(s) > 10)
        if meaningful_msgs > 0:
            prof = min(1.0, meaningful_msgs / max(1, len(commit_subjects)))
            if (
                "communication" not in cap_map
                or cap_map["communication"].get("proficiency", 0) < prof
            ):
                cap_map["communication"] = {
                    "added_timestamp": now_iso,
                    "proficiency": prof,
                    "source": "activity_scan",
                    "evidence": (
                        f"{meaningful_msgs}/{len(commit_subjects)}"
                        " commits with descriptive messages"
                    ),
                }

    def _load_previous_performance(self) -> dict[str, Any]:
        """Load the most recent previous performance entry for trend comparison.

        Returns dict with score and perf_data, or empty dict if none found.
        """
        history = self.performance.performance_history
        # Find the most recent entry for this agent that isn't from the current run
        # (the current run's entry was just appended, so look for the second-to-last)
        agent_entries = [h for h in history if h.get("agent_id") == self._agent_internal_id]
        if len(agent_entries) >= 2:
            prev = agent_entries[-2]
            return {
                "score": prev.get("performance_score", 0.0),
                "perf_data": prev.get("performance_data", {}),
                "timestamp": prev.get("timestamp", ""),
            }
        return {}

    def _write_reflection(
        self,
        date: str,
        review: dict[str, Any],
        activities: list[dict[str, Any]],
    ) -> str:
        """Write a detailed daily reflection markdown file with real data."""
        reflection_dir = os.path.join(self.workspace_dir, "memory", "daily-reflections")
        os.makedirs(reflection_dir, exist_ok=True)
        filepath = os.path.join(reflection_dir, f"{date}-reflection.md")

        # ── Analyze activities ──────────────────────────────────────────
        type_counts: dict[str, int] = {}
        commits_by_repo: dict[str, list[str]] = {}
        all_commits: list[str] = []
        for a in activities:
            atype = a.get("type", "unknown")
            type_counts[atype] = type_counts.get(atype, 0) + 1
            if atype == "git_commit":
                repo = os.path.basename(a.get("path", "unknown"))
                msg = a.get("description", "")
                commits_by_repo.setdefault(repo, []).append(msg)
                all_commits.append(msg)

        # ── Extract data from review ────────────────────────────────────
        perf_report = review.get("performance_report", {})
        avg_perf = perf_report.get("average_performance", 0.0)
        intervention = review.get("intervention", {})
        agent_score = intervention.get("score", avg_perf)
        perf_data = review.get("perf_data", {})
        accuracy = perf_data.get("accuracy", 0.0)
        efficiency = perf_data.get("efficiency", 0.0)
        adaptability = perf_data.get("adaptability", 0.0)
        gaps = review.get("capability_gaps", {})
        previous = review.get("previous_perf", {})

        # ── Build markdown ──────────────────────────────────────────────
        lines: list[str] = [f"# Daily Reflection - {date}", ""]

        # Activity Summary with git detail
        lines.extend(["## Activity Summary", f"- **Total activities**: {len(activities)}"])
        for atype, count in sorted(type_counts.items()):
            lines.append(f"- {atype}: {count}")
        if commits_by_repo:
            lines.append("")
            lines.append("### Git Activity")
            for repo, msgs in sorted(commits_by_repo.items()):
                lines.append(f"- **{repo}** ({len(msgs)} commits)")
                for msg in msgs[:5]:  # top 5 per repo
                    lines.append(f"  - {msg}")
                if len(msgs) > 5:
                    lines.append(f"  - ... and {len(msgs) - 5} more")

        # Achievements from commit messages
        if all_commits:
            lines.extend(["", "## Achievements"])
            for msg in all_commits[:10]:
                lines.append(f"- {msg}")
            if len(all_commits) > 10:
                lines.append(f"- ... and {len(all_commits) - 10} more commits")

        # Performance Breakdown
        lines.extend(
            [
                "",
                "## Performance",
                f"- **Agent score**: {agent_score:.2f}"
                f" (threshold: {self.performance.quality_threshold})",
                f"- **Average across all agents**: {avg_perf:.2f}",
                f"- **Accuracy** (productive/total): {accuracy:.2f}",
                f"- **Efficiency** (activity volume): {efficiency:.2f}",
                f"- **Adaptability** (type diversity): {adaptability:.2f}",
            ]
        )

        # Trend vs previous day
        if previous:
            prev_score = previous.get("score", 0.0)
            delta = avg_perf - prev_score
            direction = "up" if delta > 0 else "down" if delta < 0 else "unchanged"
            lines.append(
                f"- **Trend**: {direction} {abs(delta):.2f} from previous ({prev_score:.2f})"
            )
            prev_data = previous.get("perf_data", {})
            if prev_data:
                changes: list[str] = []
                for metric in ("accuracy", "efficiency", "adaptability"):
                    old_val = prev_data.get(metric, 0.0)
                    new_val = perf_data.get(metric, 0.0)
                    diff = new_val - old_val
                    if abs(diff) > 0.01:
                        arrow = "+" if diff > 0 else ""
                        changes.append(f"{metric}: {arrow}{diff:.2f}")
                if changes:
                    lines.append(f"- **Changes**: {', '.join(changes)}")

        # Intervention tier
        tier = intervention.get("tier", "none")
        if tier != "none":
            lines.extend(
                [
                    "",
                    "## Intervention Status",
                    f"- **Tier**: {tier}",
                    f"- **Reason**: {intervention.get('reason', '')}",
                ]
            )
            tier_actions = intervention.get("actions", [])
            if tier_actions:
                lines.append("- **Required actions**:")
                for action in tier_actions:
                    lines.append(f"  - {action}")
        else:
            lines.extend(
                [
                    "",
                    "## Intervention Status: NONE"
                    f" (score {intervention.get('score', 0.0):.2f}"
                    " within acceptable range)",
                ]
            )

        # Challenges — identify weak areas from performance data
        challenges: list[str] = []
        if accuracy < 0.5:
            unproductive = len(activities) - int(accuracy * len(activities))
            challenges.append(
                f"Low accuracy ({accuracy:.2f}): {unproductive} of {len(activities)} "
                f"activities were non-productive"
            )
        if efficiency < 0.5:
            challenges.append(
                f"Low efficiency ({efficiency:.2f}): only {len(activities)} activities "
                f"detected (target: 100+ for full score)"
            )
        if adaptability < 0.5:
            challenges.append(
                f"Low adaptability ({adaptability:.2f}): only {len(type_counts)} activity "
                f"types (target: 5+ for full score)"
            )
        if agent_score < self.performance.quality_threshold:
            challenges.append(
                f"Agent score ({agent_score:.2f}) below quality threshold "
                f"({self.performance.quality_threshold})"
            )
        # Add gaps as challenges
        for cap in gaps.get("low_performance_areas", []):
            challenges.append(f"Low proficiency in: {cap}")
        if challenges:
            lines.extend(["", "## Challenges"])
            for c in challenges:
                lines.append(f"- {c}")

        # Capability Gaps (now meaningful since seeded from activities)
        missing = gaps.get("missing_capabilities", [])
        stale = gaps.get("potential_improvements", [])
        if missing or stale:
            lines.extend(["", "## Capability Gaps"])
            for cap in missing:
                lines.append(f"- **Missing**: {cap} — no evidence found in today's activities")
            for cap in stale:
                lines.append(f"- **Stale**: {cap}")

        # Improvement executed
        if review.get("improvement_executed"):
            imp = review["improvement_executed"]
            lines.extend(
                [
                    "",
                    "## Improvement Executed",
                    f"- **Type**: {imp.get('type', 'unknown')}",
                    f"- **Target**: {imp.get('target', 'N/A')}",
                ]
            )

        # LLM-enhanced reflection (with richer context)
        if self.llm.available:
            commit_summary = "\n".join(f"- {m}" for m in all_commits[:15])
            context = (
                f"Date: {date}\n"
                f"Total activities: {len(activities)}\n"
                f"Activity types: {type_counts}\n"
                f"Git commits by repo: { {r: len(m) for r, m in commits_by_repo.items()} }\n"
                f"Top commit messages:\n{commit_summary}\n"
                f"Performance: overall={avg_perf:.2f}, accuracy={accuracy:.2f}, "
                f"efficiency={efficiency:.2f}, adaptability={adaptability:.2f}\n"
                f"Quality threshold: {self.performance.quality_threshold}\n"
                f"Intervention tier: {tier}\n"
                f"Challenges: {challenges}\n"
                f"Capability gaps (missing): {missing}\n"
            )
            if previous:
                context += f"Previous score: {previous.get('score', 0.0):.2f}\n"

            llm_narrative = self.llm.analyze(
                "Write a brief, honest daily reflection for an AI agent. "
                "Reference specific commits and metrics. Identify what went well, "
                "what needs improvement, and concrete priorities for tomorrow. "
                "Be concise (under 200 words).",
                context=context,
                max_tokens=512,
            )
            if llm_narrative:
                lines.extend(["", "## AI Reflection", llm_narrative])

        # Data-derived priorities
        priorities: list[str] = []
        if challenges:
            # Prioritize the biggest weakness
            if accuracy < efficiency and accuracy < adaptability:
                priorities.append("Increase productive output ratio (focus on meaningful commits)")
            elif efficiency < adaptability:
                priorities.append("Increase activity volume (more commits, more files touched)")
            else:
                priorities.append(
                    "Diversify activity types (research, testing, docs, not just coding)"
                )
        if missing:
            priorities.append(f"Build evidence for missing capabilities: {', '.join(missing)}")
        if tier != "none":
            tier_actions = intervention.get("actions", [])
            if tier_actions:
                priorities.append(f"Address intervention: {tier_actions[0]}")
        if not priorities:
            priorities.append("Maintain current trajectory — all metrics within acceptable range")
        # Always add a forward-looking item
        if len(priorities) < 3:
            priorities.append("Review and iterate on self-optimization feedback loop")

        lines.extend(["", "## Tomorrow's Priorities"])
        for i, p in enumerate(priorities, 1):
            lines.append(f"{i}. {p}")

        lines.extend(
            [
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
