"""Tests for the orchestrator — uses real filesystem via tmp_path."""

import json
import os

from orchestrator import SelfOptimizationOrchestrator, StateManager

# ── StateManager ────────────────────────────────────────────────────────


class TestStateManager:
    def test_save_and_load_roundtrip(self, tmp_path):
        sm = StateManager(str(tmp_path))
        data = {"key": "value", "count": 42, "nested": {"a": [1, 2, 3]}}
        sm.save("test", data)
        loaded = sm.load("test")
        assert loaded == data

    def test_load_missing_returns_default(self, tmp_path):
        sm = StateManager(str(tmp_path))
        assert sm.load("nonexistent") is None
        assert sm.load("nonexistent", default=[]) == []

    def test_save_creates_json_file(self, tmp_path):
        sm = StateManager(str(tmp_path))
        sm.save("mykey", {"a": 1})
        filepath = tmp_path / "mykey.json"
        assert filepath.exists()
        with open(filepath) as f:
            assert json.load(f) == {"a": 1}

    def test_load_corrupted_returns_default(self, tmp_path):
        sm = StateManager(str(tmp_path))
        (tmp_path / "bad.json").write_text("not json{{{")
        assert sm.load("bad", default="fallback") == "fallback"

    def test_creates_directory_if_missing(self, tmp_path):
        state_dir = str(tmp_path / "new" / "nested" / "dir")
        sm = StateManager(state_dir)
        sm.save("test", [1, 2, 3])
        assert sm.load("test") == [1, 2, 3]


# ── Orchestrator Init ───────────────────────────────────────────────────


class TestOrchestratorInit:
    def test_creates_all_four_systems(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        assert orch.anti_idling is not None
        assert orch.performance is not None
        assert orch.improvement is not None
        assert orch.verification is not None

    def test_creates_scanner_and_llm(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        assert orch.scanner is not None
        assert orch.llm is not None

    def test_registers_agent(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
            agent_id="test-agent",
        )
        assert orch.agent_id == "test-agent"
        # At least the current agent is registered (config may add more)
        assert len(orch.performance.agents) >= 1
        assert "test-agent" in orch._agent_ids

    def test_default_agent_id(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        assert orch.agent_id == "loopy-0"


# ── Idle Check ──────────────────────────────────────────────────────────


class TestIdleCheck:
    def test_idle_check_returns_expected_keys(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
        )
        result = orch.idle_check()
        assert "timestamp" in result
        assert "idle_rate" in result
        assert "triggered" in result
        assert "actions_proposed" in result
        assert "actions_executed" in result
        assert "activities_found" in result
        assert "service_health" in result

    def test_idle_check_detects_files(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "work.py").write_text("print('hello')")
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
        )
        result = orch.idle_check()
        assert result["activities_found"] >= 1

    def test_idle_check_persists_state(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / "state"
        orch = SelfOptimizationOrchestrator(
            state_dir=str(state_dir),
            workspace_dir=str(workspace),
        )
        orch.idle_check()
        assert (state_dir / "last_run.json").exists()
        assert (state_dir / "activity_log.json").exists()


# ── Daily Review ────────────────────────────────────────────────────────


class TestDailyReview:
    def test_daily_review_returns_expected_keys(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "memory" / "daily-reflections").mkdir(parents=True)
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
        )
        result = orch.daily_review()
        assert "timestamp" in result
        assert "date" in result
        assert "activities_found" in result
        assert "performance_report" in result
        assert "capability_gaps" in result
        assert "reflection_path" in result
        assert "verification" in result

    def test_daily_review_writes_reflection_file(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
        )
        result = orch.daily_review()
        assert result["reflection_path"]
        assert os.path.isfile(result["reflection_path"])
        with open(result["reflection_path"]) as f:
            content = f.read()
        assert "Daily Reflection" in content

    def test_daily_review_runs_verification(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
        )
        result = orch.daily_review()
        assert "specific" in result["verification"]


# ── State Persistence ───────────────────────────────────────────────────


class TestStatePersistence:
    def test_state_roundtrip(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = str(tmp_path / "state")

        # Create orchestrator and add some data
        orch1 = SelfOptimizationOrchestrator(state_dir=state_dir, workspace_dir=str(workspace))
        orch1.anti_idling.log_activity({"type": "coding", "is_productive": True, "duration": 3600})
        orch1._persist_state()

        # Create new orchestrator and verify state restored
        orch2 = SelfOptimizationOrchestrator(state_dir=state_dir, workspace_dir=str(workspace))
        assert len(orch2.anti_idling.activity_log) >= 1


# ── Status ──────────────────────────────────────────────────────────────


class TestStatus:
    def test_status_returns_expected_keys(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        status = orch.status()
        assert "agent_id" in status
        assert "workspace_dir" in status
        assert "activity_log_size" in status
        assert "registered_agents" in status
        assert "capability_count" in status
        assert "llm_available" in status
        assert "last_run" in status
        assert "daemon_running" in status
        assert "service_health" in status

    def test_status_includes_service_health(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        status = orch.status()
        # Service health should include gateway, enterprise, and vite-ui
        health = status["service_health"]
        assert "gateway" in health
        assert "enterprise" in health
        for _name, h in health.items():
            assert "healthy" in h
            assert "port" in h

    def test_status_daemon_not_running(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        assert orch.status()["daemon_running"] is False


# ── Log Activity ────────────────────────────────────────────────────────


class TestLogActivity:
    def test_log_activity_adds_to_anti_idling(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        orch.log_activity({"type": "test", "is_productive": True, "duration": 60})
        assert len(orch.anti_idling.activity_log) >= 1


# ── Stop Daemon ─────────────────────────────────────────────────────────


class TestStopDaemon:
    def test_stop_daemon_sets_flag(self, tmp_path):
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        orch._daemon_running = True
        orch.stop_daemon()
        assert orch._daemon_running is False


# ── Action Handler Wiring ──────────────────────────────────────────────


class TestActionHandlerWiring:
    def test_action_handlers_registered_on_init(self, tmp_path):
        """Orchestrator registers action handlers for all 5 emergency actions."""
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        expected_actions = [
            "conduct_strategic_analysis",
            "explore_new_skill_development",
            "start_research_sprint",
            "design_experimental_prototype",
            "initiate_user_feedback_loop",
        ]
        for action in expected_actions:
            assert action in orch.anti_idling.action_handlers

    def test_idle_check_dispatches_actions(self, tmp_path):
        """idle_check populates actions_executed when idle rate exceeds threshold."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
            idle_threshold=0.01,  # very low threshold → always triggers
        )
        result = orch.idle_check()
        assert result["triggered"] is True
        assert len(result["actions_proposed"]) > 0
        assert len(result["actions_executed"]) > 0

    def test_idle_check_actions_executed_updates_capability_map(self, tmp_path):
        """Dispatched actions update capability_map via execute_improvement."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
            idle_threshold=0.01,
        )
        initial_history = len(orch.improvement.improvement_history)
        orch.idle_check()
        # execute_improvement should have been called, adding to history
        assert len(orch.improvement.improvement_history) > initial_history

    def test_on_idle_triggered_runs_improvement(self, tmp_path):
        """_on_idle_triggered executes an improvement proposal when strategies exist."""
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        # Register a learning strategy that returns a valid proposal
        orch.improvement.learning_strategies.append(
            lambda cap_map, gaps: [
                {
                    "type": "test_improvement",
                    "target": "learning",
                    "meets_do_no_harm": True,
                    "meets_human_alignment": True,
                    "meets_transparency": True,
                    "meets_reversibility": True,
                }
            ]
        )
        initial_history = len(orch.improvement.improvement_history)
        orch._on_idle_triggered()
        assert len(orch.improvement.improvement_history) > initial_history
