"""Tests for the self-evaluation engine."""

import json
import os
from unittest.mock import patch

import pytest

from self_eval import SelfEvalEngine


@pytest.fixture
def engine(tmp_path):
    """Create a SelfEvalEngine with tmp dirs."""
    project_root = str(tmp_path / "project")
    state_dir = str(tmp_path / "state")
    workspace_dir = str(tmp_path / "workspace")
    os.makedirs(project_root)
    os.makedirs(os.path.join(project_root, "src"))
    os.makedirs(os.path.join(project_root, "tests"))
    os.makedirs(state_dir)
    os.makedirs(workspace_dir)
    return SelfEvalEngine(
        project_root=project_root,
        state_dir=state_dir,
        workspace_dir=workspace_dir,
    )


# ── Grade thresholds ─────────────────────────────────────────────────


class TestGradeThresholds:
    def test_grade_a(self, engine):
        assert engine._score_to_grade(95) == "A"

    def test_grade_b(self, engine):
        assert engine._score_to_grade(85) == "B"

    def test_grade_c(self, engine):
        assert engine._score_to_grade(75) == "C"

    def test_grade_d(self, engine):
        assert engine._score_to_grade(65) == "D"

    def test_grade_f(self, engine):
        assert engine._score_to_grade(55) == "F"

    def test_boundary_a(self, engine):
        assert engine._score_to_grade(90) == "A"

    def test_boundary_b(self, engine):
        assert engine._score_to_grade(80) == "B"


# ── Discovery ────────────────────────────────────────────────────────


class TestDiscoverServices:
    def test_returns_expected_services(self, engine):
        with patch("self_eval.probe_port") as mock_probe:
            mock_probe.return_value = {
                "healthy": True,
                "detail": "ok",
                "port": 3000,
                "timestamp": "t",
            }
            services = engine.discover_services()
        assert len(services) == 3
        names = [s["name"] for s in services]
        assert "gateway" in names
        assert "enterprise" in names
        assert "vite-ui" in names

    def test_detects_unhealthy_service(self, engine):
        def mock_probe(port, timeout=3):
            healthy = port != 18789
            return {
                "healthy": healthy,
                "detail": "ok" if healthy else "refused",
                "port": port,
                "timestamp": "t",
            }

        with patch("self_eval.probe_port", side_effect=mock_probe):
            services = engine.discover_services()
        enterprise = next(s for s in services if s["name"] == "enterprise")
        assert enterprise["healthy"] is False
        assert enterprise["critical"] is True


class TestDiscoverRepos:
    def test_finds_git_repos(self, engine):
        # Create a fake git repo in workspace
        repo_dir = os.path.join(engine.workspace_dir, "my-project")
        os.makedirs(os.path.join(repo_dir, ".git"))
        repos = engine.discover_repos()
        assert len(repos) >= 1
        assert any(r["name"] == "my-project" for r in repos)

    def test_finds_nested_repos(self, engine):
        # Create a nested git repo (depth 2)
        nested = os.path.join(engine.workspace_dir, "org", "deep-project")
        os.makedirs(os.path.join(nested, ".git"))
        repos = engine.discover_repos()
        assert any(r["name"] == "deep-project" for r in repos)

    def test_empty_workspace(self, engine):
        repos = engine.discover_repos()
        assert repos == []


class TestDiscoverConfigDrift:
    def test_first_run_reports_new_files(self, engine):
        # Create a config file
        config_path = os.path.join(engine.project_root, "pyproject.toml")
        with open(config_path, "w") as f:
            f.write("[project]\nname = 'test'\n")

        with patch("self_eval.os.path.expanduser", return_value="/nonexistent"):
            drift = engine.discover_config_drift()
        # pyproject.toml should be detected as new
        assert drift["tracked_files"] >= 1

    def test_detects_change(self, engine):
        config_path = os.path.join(engine.project_root, "pyproject.toml")
        with open(config_path, "w") as f:
            f.write("[project]\nname = 'v1'\n")

        with patch("self_eval.os.path.expanduser", return_value="/nonexistent"):
            engine.discover_config_drift()  # First run

        # Change the file
        with open(config_path, "w") as f:
            f.write("[project]\nname = 'v2'\n")

        with patch("self_eval.os.path.expanduser", return_value="/nonexistent"):
            drift = engine.discover_config_drift()
        assert config_path in drift["drifted"]


# ── Healing ──────────────────────────────────────────────────────────


class TestHealLint:
    def test_heal_lint_success(self, engine):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 0, "stdout": "All checks passed!", "stderr": ""
            })()
            result = engine.heal_lint()
        assert result["success"] is True

    def test_heal_lint_not_found(self, engine):
        with patch("subprocess.run", side_effect=FileNotFoundError("ruff")):
            result = engine.heal_lint()
        assert result["success"] is False


class TestHealState:
    def test_repairs_corrupted_json(self, engine):
        # Create a corrupted state file
        bad_file = os.path.join(engine.state_dir, "bad.json")
        with open(bad_file, "w") as f:
            f.write("{corrupted json{{{")
        result = engine.heal_state()
        assert result["count"] == 1
        assert "bad.json" in result["repaired"]
        # Original should be gone, backup should exist
        assert not os.path.exists(bad_file)
        assert os.path.exists(bad_file + ".corrupted")

    def test_leaves_valid_json_alone(self, engine):
        good_file = os.path.join(engine.state_dir, "good.json")
        with open(good_file, "w") as f:
            json.dump({"valid": True}, f)
        result = engine.heal_state()
        assert result["count"] == 0
        assert os.path.exists(good_file)


# ── Evaluation ───────────────────────────────────────────────────────


class TestEvalLint:
    def test_lint_pass(self, engine):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 0, "stdout": "All checks passed!", "stderr": ""
            })()
            result = engine.eval_lint()
        assert result["passed"] is True
        assert result["score"] == 100

    def test_lint_fail_with_errors(self, engine):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 1,
                "stdout": "src/foo.py:1 E501\nFound 3 errors.\n",
                "stderr": "",
            })()
            result = engine.eval_lint()
        assert result["passed"] is False
        assert result["error_count"] == 3
        assert result["score"] == 85  # 100 - 3*5


class TestEvalTests:
    def test_tests_pass(self, engine):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 0,
                "stdout": "343 passed in 2.5s\n",
                "stderr": "",
            })()
            result = engine.eval_tests()
        assert result["all_passed"] is True
        assert result["passed_count"] == 343
        assert result["score"] == 100

    def test_tests_with_failures(self, engine):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 1,
                "stdout": "340 passed, 3 failed in 3.0s\n",
                "stderr": "",
            })()
            result = engine.eval_tests()
        assert result["all_passed"] is False
        assert result["passed_count"] == 340
        assert result["failed_count"] == 3
        assert result["total"] == 343


# ── Full eval ────────────────────────────────────────────────────────


class TestRunFullEval:
    def test_full_eval_returns_all_keys(self, engine):
        with (
            patch.object(engine, "eval_lint", return_value={
                "passed": True, "error_count": 0, "score": 100
            }),
            patch.object(engine, "eval_typecheck", return_value={
                "passed": True, "error_count": 0, "score": 100
            }),
            patch.object(engine, "eval_tests", return_value={
                "all_passed": True, "passed_count": 343, "failed_count": 0,
                "total": 343, "elapsed_seconds": 2.5, "score": 100
            }),
            patch.object(engine, "discover_config_drift", return_value={
                "drifted": [], "new": [], "tracked_files": 3
            }),
        ):
            report = engine.run_full_eval(include_services=False)

        assert "timestamp" in report
        assert "lint" in report
        assert "typecheck" in report
        assert "tests" in report
        assert "composite_score" in report
        assert "grade" in report
        assert "trend" in report

    def test_full_eval_grade_a_when_all_pass(self, engine):
        lint_ok = {"score": 100, "passed": True, "error_count": 0}
        with (
            patch.object(engine, "eval_lint", return_value=lint_ok),
            patch.object(engine, "eval_typecheck", return_value=lint_ok),
            patch.object(engine, "eval_tests", return_value={
                "score": 100, "all_passed": True, "passed_count": 343,
                "failed_count": 0, "total": 343, "elapsed_seconds": 2
            }),
            patch.object(engine, "discover_config_drift", return_value={
                "drifted": [], "new": [], "tracked_files": 3
            }),
        ):
            report = engine.run_full_eval(include_services=False)

        assert report["grade"] == "A"
        assert report["composite_score"] == 100.0

    def test_trend_tracking_across_evals(self, engine):
        mock_results = {
            "score": 100,
            "passed": True,
            "all_passed": True,
            "error_count": 0,
            "passed_count": 343,
            "failed_count": 0,
            "total": 343,
            "elapsed_seconds": 2,
        }
        with (
            patch.object(engine, "eval_lint", return_value=mock_results),
            patch.object(engine, "eval_typecheck", return_value=mock_results),
            patch.object(engine, "eval_tests", return_value=mock_results),
            patch.object(engine, "discover_config_drift", return_value={
                "drifted": [], "new": [], "tracked_files": 3
            }),
        ):
            report1 = engine.run_full_eval(include_services=False)
            report2 = engine.run_full_eval(include_services=False)

        assert report1["trend"]["direction"] == "first_run"
        assert report2["trend"]["previous_score"] is not None
        assert report2["trend"]["direction"] == "stable"


# ── Report generation ────────────────────────────────────────────────


class TestMarkdownReport:
    def test_generates_valid_markdown(self, engine):
        report = {
            "timestamp": "2026-02-24T00:00:00Z",
            "grade": "A",
            "composite_score": 100.0,
            "lint": {"passed": True, "error_count": 0, "score": 100},
            "typecheck": {"passed": True, "error_count": 0, "score": 100},
            "tests": {
                "all_passed": True, "passed_count": 343,
                "failed_count": 0, "total": 343, "elapsed_seconds": 2.5,
                "score": 100,
            },
            "services": {"skipped": True, "score": 100},
            "trend": {"previous_score": None, "direction": "first_run"},
            "config_drift": {"drifted": [], "new": [], "tracked_files": 3},
        }
        md = engine.generate_markdown_report(report)
        assert "# Self-Optimization Health Report" in md
        assert "Grade: A" in md
        assert "PASS" in md
        assert "All Clear" in md

    def test_report_shows_failures(self, engine):
        report = {
            "timestamp": "2026-02-24T00:00:00Z",
            "grade": "D",
            "composite_score": 60.0,
            "lint": {"passed": False, "error_count": 5, "score": 75},
            "typecheck": {"passed": False, "error_count": 3, "score": 70},
            "tests": {
                "all_passed": False, "passed_count": 330,
                "failed_count": 13, "total": 343, "elapsed_seconds": 3,
                "score": 96,
            },
            "services": {"skipped": True, "score": 100},
            "trend": {"previous_score": 100, "delta": -40, "direction": "declining"},
            "config_drift": {"drifted": [], "new": [], "tracked_files": 3},
        }
        md = engine.generate_markdown_report(report)
        assert "Action Required" in md
        assert "FAIL" in md


class TestGitHubIssueBody:
    def test_no_issue_for_healthy(self, engine):
        report = {"grade": "A", "composite_score": 100}
        assert engine.generate_github_issue_body(report) is None

    def test_issue_for_grade_c(self, engine):
        report = {
            "timestamp": "2026-02-24T00:00:00Z",
            "grade": "C",
            "composite_score": 72,
            "lint": {"passed": True, "error_count": 0, "score": 100},
            "typecheck": {"passed": True, "error_count": 0, "score": 100},
            "tests": {
                "all_passed": False, "passed_count": 300,
                "failed_count": 43, "total": 343, "elapsed_seconds": 3,
                "score": 87,
            },
            "services": {"skipped": True, "score": 100},
            "trend": {"previous_score": None, "direction": "first_run"},
            "config_drift": {"drifted": [], "new": [], "tracked_files": 3},
        }
        body = engine.generate_github_issue_body(report)
        assert body is not None
        assert "Grade: C" in body
        assert "automatically" in body


# ── History ──────────────────────────────────────────────────────────


class TestHistory:
    def test_history_persists(self, engine):
        engine._save_eval({"composite_score": 95, "grade": "A"})
        engine._save_eval({"composite_score": 88, "grade": "B"})
        history = engine._load_history()
        assert len(history) == 2

    def test_history_capped_at_90(self, engine):
        for i in range(100):
            engine._save_eval({"composite_score": i, "grade": "A"})
        history = engine._load_history()
        assert len(history) == 90

    def test_trend_summary(self, engine):
        engine._save_eval({"composite_score": 80, "tests": {"total": 300}})
        engine._save_eval({"composite_score": 90, "tests": {"total": 343}})
        trend = engine.get_trend_summary()
        assert trend["evaluations"] == 2
        assert trend["latest_score"] == 90
        assert trend["test_count_growth"] == 43


class TestEvalServices:
    def test_all_healthy(self, engine):
        with patch("self_eval.probe_port") as mock_probe:
            mock_probe.return_value = {
                "healthy": True, "detail": "ok", "port": 3000, "timestamp": "t"
            }
            result = engine.eval_services()
        assert result["score"] == 100
        assert result["critical_down"] == []

    def test_critical_service_down_penalized(self, engine):
        def mock_probe(port, timeout=3):
            healthy = port != 18789
            return {
                "healthy": healthy, "detail": "ok" if healthy else "down",
                "port": port, "timestamp": "t",
            }

        with patch("self_eval.probe_port", side_effect=mock_probe):
            result = engine.eval_services()
        assert "enterprise" in result["critical_down"]
        assert result["score"] < 100
