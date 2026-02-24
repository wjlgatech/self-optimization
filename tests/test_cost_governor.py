"""Tests for the CostGovernor module."""

import json
import os

import pytest

from cost_governor import (
    CHEAP_MODELS,
    DEFAULT_BOOTSTRAP_MAX_CHARS,
    DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS,
    EXPENSIVE_MODELS,
    MID_TIER_MODELS,
    RECOMMENDED_BOOTSTRAP_MAX_CHARS,
    RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS,
    CostGovernor,
    _deep_merge,
    _estimate_total_savings,
    _list_changed_keys,
)


@pytest.fixture
def tmp_env(tmp_path):
    """Create a temporary environment with config and workspace."""
    config_path = tmp_path / "openclaw.json"
    workspace_dir = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace_dir.mkdir()
    state_dir.mkdir()

    config = {
        "agents": {
            "defaults": {
                "workspace": str(workspace_dir),
                "compaction": {"mode": "safeguard"},
                "maxConcurrent": 4,
                "subagents": {"maxConcurrent": 8},
            }
        },
        "gateway": {
            "port": 31415,
            "auth": {"mode": "token", "token": "test-token"},
        },
    }
    config_path.write_text(json.dumps(config, indent=2))

    return {
        "config_path": str(config_path),
        "workspace_dir": str(workspace_dir),
        "state_dir": str(state_dir),
        "config": config,
    }


@pytest.fixture
def governor(tmp_env):
    """Create a CostGovernor with temporary environment."""
    return CostGovernor(
        config_path=tmp_env["config_path"],
        workspace_dir=tmp_env["workspace_dir"],
        state_dir=tmp_env["state_dir"],
    )


@pytest.fixture
def governor_with_bootstrap(tmp_env):
    """Create a CostGovernor with bootstrap files in workspace."""
    ws = tmp_env["workspace_dir"]
    # Create some bootstrap files
    with open(os.path.join(ws, "AGENTS.md"), "w") as f:
        f.write("# Agent Rules\n" * 200)  # ~2800 chars
    with open(os.path.join(ws, "SOUL.md"), "w") as f:
        f.write("# Core Values\n" * 150)  # ~2100 chars
    with open(os.path.join(ws, "TOOLS.md"), "w") as f:
        f.write("# Tool Guide\n" * 50)  # ~650 chars
    with open(os.path.join(ws, "IDENTITY.md"), "w") as f:
        f.write("# Identity\nI am a bot.\n")
    with open(os.path.join(ws, "MEMORY.md"), "w") as f:
        f.write("# Memory\n" * 300)  # ~2700 chars

    return CostGovernor(
        config_path=tmp_env["config_path"],
        workspace_dir=tmp_env["workspace_dir"],
        state_dir=tmp_env["state_dir"],
    )


# --- Model classification tests ---


class TestModelClassification:
    def test_opus_is_expensive(self):
        assert "anthropic/claude-opus-4-6" in EXPENSIVE_MODELS
        assert "claude-opus-4-6" in EXPENSIVE_MODELS

    def test_haiku_is_mid_tier(self):
        assert "claude-haiku-4-5" in MID_TIER_MODELS

    def test_ollama_is_cheap(self):
        assert "ollama/llama3.3" in CHEAP_MODELS

    def test_tiers_are_disjoint(self):
        assert not (EXPENSIVE_MODELS & MID_TIER_MODELS)
        assert not (EXPENSIVE_MODELS & CHEAP_MODELS)
        assert not (MID_TIER_MODELS & CHEAP_MODELS)


# --- Bootstrap measurement tests ---


class TestBootstrapMeasurement:
    def test_empty_workspace(self, governor):
        result = governor.measure_bootstrap_files()
        assert result["total_chars"] == 0
        assert result["files"] == []
        assert result["total_est_tokens"] == 0

    def test_measures_files(self, governor_with_bootstrap):
        result = governor_with_bootstrap.measure_bootstrap_files()
        assert result["total_chars"] > 0
        assert len(result["files"]) >= 4
        assert result["total_est_tokens"] == result["total_chars"] // 4

    def test_sorted_by_size_descending(self, governor_with_bootstrap):
        result = governor_with_bootstrap.measure_bootstrap_files()
        sizes = [f["chars"] for f in result["files"]]
        assert sizes == sorted(sizes, reverse=True)

    def test_includes_configured_caps(self, governor_with_bootstrap):
        result = governor_with_bootstrap.measure_bootstrap_files()
        assert result["configured_max_per_file"] == DEFAULT_BOOTSTRAP_MAX_CHARS
        assert result["configured_total_max"] == DEFAULT_BOOTSTRAP_TOTAL_MAX_CHARS
        assert result["recommended_max_per_file"] == RECOMMENDED_BOOTSTRAP_MAX_CHARS
        assert result["recommended_total_max"] == RECOMMENDED_BOOTSTRAP_TOTAL_MAX_CHARS


# --- Audit tests ---


class TestAudit:
    def test_audit_returns_required_keys(self, governor):
        result = governor.audit()
        assert "findings" in result
        assert "recommendations" in result
        assert "estimated_savings_pct" in result
        assert "timestamp" in result
        assert "current_model" in result

    def test_detects_expensive_model(self, tmp_env):
        """When config has an expensive model, audit flags it."""
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "anthropic/claude-opus-4-6"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        result = gov.audit()

        finding_ids = [f["id"] for f in result["findings"]]
        assert "expensive_model" in finding_ids

        rec_ids = [r["id"] for r in result["recommendations"]]
        assert "switch_default_model" in rec_ids

    def test_detects_weak_compaction(self, governor):
        """Default compaction='safeguard' should be flagged."""
        result = governor.audit()
        finding_ids = [f["id"] for f in result["findings"]]
        assert "weak_compaction" in finding_ids

    def test_detects_high_bootstrap_cap(self, governor):
        """Default bootstrap caps (20K/150K) should be flagged."""
        result = governor.audit()
        finding_ids = [f["id"] for f in result["findings"]]
        assert "high_bootstrap_cap" in finding_ids

    def test_detects_heartbeat_inheriting_expensive(self, tmp_env):
        """When heartbeat has no explicit model and primary is expensive."""
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "claude-opus-4-6"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        result = gov.audit()
        finding_ids = [f["id"] for f in result["findings"]]
        assert "heartbeat_inherits_expensive" in finding_ids

    def test_no_false_positive_for_cheap_model(self, tmp_env):
        """Cheap model should not trigger expensive_model finding."""
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "ollama/llama3.3"}
        config["agents"]["defaults"]["compaction"] = {"mode": "default"}
        config["agents"]["defaults"]["bootstrapMaxChars"] = 6000
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        result = gov.audit()
        finding_ids = [f["id"] for f in result["findings"]]
        assert "expensive_model" not in finding_ids

    def test_detects_high_concurrency(self, governor):
        """4 concurrent agents + 8 subagents should be noted."""
        result = governor.audit()
        finding_ids = [f["id"] for f in result["findings"]]
        assert "high_concurrency" in finding_ids

    def test_estimated_savings_nonzero_for_wasteful_config(self, tmp_env):
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "claude-opus-4-6"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        result = gov.audit()
        assert result["estimated_savings_pct"] > 0


# --- Config optimization tests ---


class TestConfigOptimization:
    def test_aggressive_uses_local_model(self, governor):
        result = governor.generate_optimized_config(strategy="aggressive")
        assert result["strategy"] == "aggressive"
        primary = result["patch"]["agents"]["defaults"]["model"]["primary"]
        assert "ollama" in primary

    def test_balanced_uses_haiku(self, governor):
        result = governor.generate_optimized_config(strategy="balanced")
        primary = result["patch"]["agents"]["defaults"]["model"]["primary"]
        assert "haiku" in primary

    def test_conservative_keeps_model(self, governor):
        result = governor.generate_optimized_config(strategy="conservative")
        # Conservative should NOT have model.primary in patch
        model = result["patch"].get("agents", {}).get("defaults", {}).get("model")
        assert model is None

    def test_conservative_still_fixes_compaction(self, governor):
        result = governor.generate_optimized_config(strategy="conservative")
        compaction = result["patch"]["agents"]["defaults"]["compaction"]["mode"]
        assert compaction == "default"

    def test_all_strategies_have_explanations(self, governor):
        for strategy in ["aggressive", "balanced", "conservative"]:
            result = governor.generate_optimized_config(strategy=strategy)
            assert len(result["explanations"]) > 0


# --- Config application tests ---


class TestConfigApplication:
    def test_apply_creates_backup(self, governor, tmp_env):
        patch = {"agents": {"defaults": {"compaction": {"mode": "default"}}}}
        result = governor.apply_config(patch, backup=True)
        assert result["success"]
        assert result["backup_path"] is not None
        assert os.path.isfile(result["backup_path"])

    def test_apply_merges_correctly(self, governor, tmp_env):
        patch = {"agents": {"defaults": {"compaction": {"mode": "default"}}}}
        result = governor.apply_config(patch)
        assert result["success"]

        # Reload and verify
        with open(tmp_env["config_path"]) as f:
            updated = json.load(f)
        assert updated["agents"]["defaults"]["compaction"]["mode"] == "default"
        # Original keys should still be there
        assert updated["agents"]["defaults"]["maxConcurrent"] == 4

    def test_apply_lists_changed_keys(self, governor):
        patch = {
            "agents": {
                "defaults": {
                    "model": {"primary": "claude-haiku-4-5"},
                    "compaction": {"mode": "default"},
                }
            }
        }
        result = governor.apply_config(patch)
        assert "agents.defaults.model.primary" in result["keys_changed"]
        assert "agents.defaults.compaction.mode" in result["keys_changed"]

    def test_apply_without_backup(self, governor, tmp_env):
        patch = {"agents": {"defaults": {"compaction": {"mode": "default"}}}}
        result = governor.apply_config(patch, backup=False)
        assert result["success"]
        assert result["backup_path"] is None


# --- Baseline tracking tests ---


class TestBaselineTracking:
    def test_record_baseline(self, governor):
        baseline = governor.record_baseline(label="test")
        assert baseline["label"] == "test"
        assert "timestamp" in baseline
        assert "model" in baseline
        assert "bootstrap_total_chars" in baseline

    def test_baselines_persist(self, governor):
        governor.record_baseline(label="first")
        governor.record_baseline(label="second")
        baselines = governor.get_baselines()
        assert len(baselines) == 2
        assert baselines[0]["label"] == "first"
        assert baselines[1]["label"] == "second"

    def test_baselines_capped_at_20(self, governor):
        for i in range(25):
            governor.record_baseline(label=f"baseline-{i}")
        baselines = governor.get_baselines()
        assert len(baselines) == 20


# --- Governor loop tests ---


class TestGovernorLoop:
    def test_run_governor_returns_required_keys(self, governor):
        result = governor.run_governor()
        assert "timestamp" in result
        assert "status" in result
        assert "current_model" in result
        assert "alerts" in result
        assert "actions_taken" in result

    def test_governor_detects_expensive_model(self, tmp_env):
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "claude-opus-4-6"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        result = gov.run_governor()
        assert result["status"] == "needs_attention"
        assert any("Expensive model" in a for a in result["alerts"])

    def test_governor_detects_weak_compaction(self, governor):
        result = governor.run_governor()
        assert any("compaction" in a.lower() for a in result["alerts"])

    def test_governor_saves_history(self, governor):
        governor.run_governor()
        governor.run_governor()
        status = governor.status()
        assert status["governor_runs"] == 2

    def test_governor_detects_bootstrap_bloat_drift(self, tmp_env):
        """If bootstrap grows 20%+ vs baseline, governor should alert."""
        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        # Record baseline with small bootstrap
        ws = tmp_env["workspace_dir"]
        with open(os.path.join(ws, "AGENTS.md"), "w") as f:
            f.write("short")
        gov.record_baseline(label="before")

        # Grow the file significantly
        with open(os.path.join(ws, "AGENTS.md"), "w") as f:
            f.write("x" * 10000)

        result = gov.run_governor()
        assert any("bloat" in a.lower() for a in result["alerts"])


# --- Status tests ---


class TestStatus:
    def test_status_returns_required_keys(self, governor):
        result = governor.status()
        assert "current_model" in result
        assert "model_tier" in result
        assert "bootstrap_total_chars" in result
        assert "compaction_mode" in result
        assert "governor_runs" in result
        assert "baselines_recorded" in result

    def test_status_shows_savings_vs_baseline(self, tmp_env):
        """After recording baseline and switching model, savings should show."""
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "claude-opus-4-6"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        gov.record_baseline(label="expensive")

        # Switch to cheap model
        config["agents"]["defaults"]["model"] = {"primary": "claude-haiku-4-5"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov2 = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        status = gov2.status()
        savings = status["savings_vs_baseline"]
        assert savings is not None
        assert savings["model_cost_reduction_pct"] > 90  # Opus→Haiku = 94.7%


# --- Helper function tests ---


class TestHelpers:
    def test_deep_merge_simple(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99, "z": 100}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}

    def test_deep_merge_does_not_mutate(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1}}

    def test_list_changed_keys(self):
        patch = {"a": {"b": {"c": 1}, "d": 2}, "e": 3}
        keys = _list_changed_keys(patch)
        assert set(keys) == {"a.b.c", "a.d", "e"}

    def test_estimate_total_savings_empty(self):
        assert _estimate_total_savings([]) == 0

    def test_estimate_total_savings_single(self):
        recs = [{"savings_pct": 80}]
        assert _estimate_total_savings(recs) == 80

    def test_estimate_total_savings_multiple(self):
        """Multiple 50% savings should compound, not add to 100%."""
        recs = [{"savings_pct": 50}, {"savings_pct": 50}]
        result = _estimate_total_savings(recs)
        assert result == 75  # 1 - (0.5 * 0.5) = 0.75

    def test_estimate_total_savings_capped_at_95(self):
        recs = [{"savings_pct": 90}, {"savings_pct": 90}, {"savings_pct": 90}]
        result = _estimate_total_savings(recs)
        assert result <= 95


# --- Model detection tests ---


class TestModelDetection:
    def test_detects_from_config(self, tmp_env):
        config = tmp_env["config"]
        config["agents"]["defaults"]["model"] = {"primary": "gpt-4o-mini"}
        with open(tmp_env["config_path"], "w") as f:
            json.dump(config, f)

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        assert gov._detect_current_model() == "gpt-4o-mini"

    def test_detects_from_gateway_log(self, tmp_env, monkeypatch):
        """Falls back to gateway.log when config has no model."""
        # Redirect expanduser so it doesn't read the real gateway log
        fake_home = tmp_env["state_dir"]
        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: p.replace("~", fake_home),
        )

        gov = CostGovernor(
            config_path=tmp_env["config_path"],
            workspace_dir=tmp_env["workspace_dir"],
            state_dir=tmp_env["state_dir"],
        )
        # No model in config, no gateway log at fake path → empty/unknown
        model = gov._detect_current_model()
        assert model in ("", "unknown")
