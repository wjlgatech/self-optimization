"""Tests for config_loader — real file parsing, defaults, agent normalization."""

import os

from config_loader import (
    DEFAULT_CONFIG,
    _normalize_agent_name,
    load_monitoring_config,
)


class TestLoadMonitoringConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        config = load_monitoring_config(str(tmp_path / "nonexistent.yaml"))
        assert config["agents"] == DEFAULT_CONFIG["agents"]
        assert "goal_completion_rate" in config["thresholds"]

    def test_loads_real_config(self, tmp_path):
        config_text = """\
monitoring:
  interval: 1h
  agents:
    - loopy
    - loopy1

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

notification_channels:
  - email
  - internal_dashboard
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_text)
        config = load_monitoring_config(str(config_file))

        assert config["agents"] == ["loopy-0", "loopy-1"]
        assert config["monitoring_interval"] == "1h"
        assert config["thresholds"]["goal_completion_rate"]["warning"] == 0.7
        assert config["thresholds"]["goal_completion_rate"]["critical"] == 0.5
        assert config["thresholds"]["task_efficiency"]["warning"] == 0.65
        assert config["thresholds"]["task_efficiency"]["critical"] == 0.4

    def test_agent_name_normalization(self):
        assert _normalize_agent_name("loopy") == "loopy-0"
        assert _normalize_agent_name("loopy1") == "loopy-1"
        assert _normalize_agent_name("other-agent") == "other-agent"

    def test_empty_config_returns_defaults(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("# empty config\n")
        config = load_monitoring_config(str(config_file))
        assert config["agents"] == list(DEFAULT_CONFIG["agents"])

    def test_partial_thresholds(self, tmp_path):
        config_text = """\
performance_thresholds:
  goal_completion_rate:
    warning_level: 0.8
    critical_level: 0.3
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_text)
        config = load_monitoring_config(str(config_file))
        assert config["thresholds"]["goal_completion_rate"]["warning"] == 0.8
        assert config["thresholds"]["goal_completion_rate"]["critical"] == 0.3

    def test_intervention_tiers_parsed(self, tmp_path):
        config_text = """\
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
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_text)
        config = load_monitoring_config(str(config_file))
        assert "tier1" in config["intervention_tiers"]
        assert config["intervention_tiers"]["tier1"]["duration"] == "2 weeks"
        assert "performance_review" in config["intervention_tiers"]["tier1"]["actions"]

    def test_notification_channels_parsed(self, tmp_path):
        config_text = """\
notification_channels:
  - email
  - internal_dashboard
  - periodic_report
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_text)
        config = load_monitoring_config(str(config_file))
        assert "email" in config["notification_channels"]
        assert len(config["notification_channels"]) == 3

    def test_default_config_path_used(self):
        # When called with empty string, it tries the default location
        config = load_monitoring_config("")
        # Should return a valid config (either from real file or defaults)
        assert "agents" in config
        assert "thresholds" in config

    def test_unreadable_file_returns_defaults(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("valid content")
        os.chmod(str(config_file), 0o000)
        try:
            config = load_monitoring_config(str(config_file))
            assert config["agents"] == DEFAULT_CONFIG["agents"]
        finally:
            os.chmod(str(config_file), 0o644)


class TestMultiAgentOrchestrator:
    def test_registers_all_config_agents(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
            agent_id="loopy-0",
        )
        # Config has loopy-0 and loopy-1
        assert "loopy-0" in orch._agent_ids
        assert "loopy-1" in orch._agent_ids

    def test_all_agents_key_in_status(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        status = orch.status()
        assert "all_agents" in status
        assert "loopy-0" in status["all_agents"]

    def test_config_thresholds_in_status(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        status = orch.status()
        assert "config" in status
        assert "thresholds" in status["config"]

    def test_custom_agent_id_registered(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
            agent_id="loopy-1",
        )
        assert orch.agent_id == "loopy-1"
        assert "loopy-1" in orch._agent_ids


class TestInterventionTier:
    def test_no_performance_data_returns_tier(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        result = orch.get_intervention_tier()
        assert "tier" in result
        assert "reason" in result

    def test_unknown_agent_returns_unknown(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        result = orch.get_intervention_tier("nonexistent-agent")
        assert result["tier"] == "unknown"

    def test_high_score_returns_none_tier(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        # Set high performance
        orch.performance.update_agent_performance(
            orch._agent_internal_id,
            {"accuracy": 0.9, "efficiency": 0.9, "adaptability": 0.9},
        )
        result = orch.get_intervention_tier()
        assert result["tier"] == "none"

    def test_low_score_triggers_tier(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(tmp_path / "workspace"),
        )
        # Set low performance below critical (0.5)
        orch.performance.update_agent_performance(
            orch._agent_internal_id,
            {"accuracy": 0.2, "efficiency": 0.1, "adaptability": 0.1},
        )
        result = orch.get_intervention_tier()
        assert result["tier"] in ("tier2", "tier3")
        assert "actions" in result

    def test_daily_review_includes_intervention(self, tmp_path):
        from orchestrator import SelfOptimizationOrchestrator

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        orch = SelfOptimizationOrchestrator(
            state_dir=str(tmp_path / "state"),
            workspace_dir=str(workspace),
        )
        result = orch.daily_review()
        assert "intervention" in result
