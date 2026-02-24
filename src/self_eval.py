"""Self-evaluation engine: discovers, heals, evaluates, and reports.

This is the module that makes self-optimization real — instead of incrementing
proficiency floats, it runs actual quality gates, measures actual metrics,
and produces actual reports that surface to humans.

Four loops:
  1. DISCOVER — scan for services, repos, config drift
  2. HEAL — auto-fix lint/format, clean corrupted state
  3. EVALUATE — run quality gates, score results
  4. REPORT — generate markdown, track trends, assign grade
"""

import contextlib
import glob
import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from gateway_watchdog import probe_port

logger = logging.getLogger(__name__)

# Grade thresholds (composite score 0-100)
GRADE_THRESHOLDS = {"A": 90, "B": 80, "C": 70, "D": 60}

# Expected services (canonical source of truth)
EXPECTED_SERVICES = [
    {"name": "gateway", "port": 3000, "critical": True},
    {"name": "enterprise", "port": 18789, "critical": True},
    {"name": "vite-ui", "port": 5173, "critical": False},
]


class SelfEvalEngine:
    """Runs real quality gates on the self-optimization codebase itself."""

    def __init__(
        self,
        project_root: str = "",
        state_dir: str = "",
        workspace_dir: str = "",
    ) -> None:
        if not project_root:
            # Auto-detect: this file lives in src/, project root is one up
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not state_dir:
            state_dir = os.path.join(project_root, "state")
        if not workspace_dir:
            workspace_dir = os.path.expanduser("~/.openclaw/workspace")

        self.project_root = project_root
        self.state_dir = state_dir
        self.workspace_dir = workspace_dir
        os.makedirs(state_dir, exist_ok=True)
        self._history_file = os.path.join(state_dir, "self_eval_history.json")

    # ── DISCOVER ────────────────────────────────────────────────────────

    def discover_services(self) -> list[dict[str, Any]]:
        """Probe expected services and discover unexpected listeners."""
        results: list[dict[str, Any]] = []
        for svc in EXPECTED_SERVICES:
            svc_port: int = svc["port"]  # type: ignore[assignment]
            health = probe_port(svc_port, timeout=3)
            results.append({
                "name": svc["name"],
                "port": svc["port"],
                "critical": svc["critical"],
                "healthy": health["healthy"],
                "detail": health["detail"],
            })
        return results

    def discover_repos(self) -> list[dict[str, Any]]:
        """Recursively find git repos in the workspace (up to 3 levels deep)."""
        repos: list[dict[str, Any]] = []
        if not os.path.isdir(self.workspace_dir):
            return repos

        for depth in range(3):
            pattern = os.path.join(self.workspace_dir, *["*"] * (depth + 1), ".git")
            for git_dir in glob.glob(pattern):
                repo_path = os.path.dirname(git_dir)
                repos.append({
                    "path": repo_path,
                    "name": os.path.basename(repo_path),
                    "depth": depth + 1,
                })
        # Deduplicate by path
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in repos:
            if r["path"] not in seen:
                seen.add(r["path"])
                unique.append(r)
        return unique

    def discover_config_drift(self) -> dict[str, Any]:
        """Compare current config hashes against last known state."""
        config_files = [
            os.path.expanduser("~/.openclaw/openclaw.json"),
            os.path.join(self.project_root, "pyproject.toml"),
            os.path.join(self.project_root, ".pre-commit-config.yaml"),
        ]
        current_hashes: dict[str, str] = {}
        for path in config_files:
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    current_hashes[path] = hashlib.sha256(f.read()).hexdigest()[:16]

        # Load previous hashes
        hash_file = os.path.join(self.state_dir, "config_hashes.json")
        previous_hashes: dict[str, str] = {}
        try:
            with open(hash_file, encoding="utf-8") as f:
                previous_hashes = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

        # Compare
        drifted: list[str] = []
        new_files: list[str] = []
        for path, current_hash in current_hashes.items():
            if path not in previous_hashes:
                new_files.append(path)
            elif previous_hashes[path] != current_hash:
                drifted.append(path)

        # Save current hashes
        try:
            tmp = hash_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(current_hashes, f, indent=2)
            os.replace(tmp, hash_file)
        except OSError as e:
            logger.warning("Failed to save config hashes: %s", e)

        return {
            "drifted": drifted,
            "new": new_files,
            "tracked_files": len(current_hashes),
        }

    # ── HEAL ────────────────────────────────────────────────────────────

    def heal_lint(self) -> dict[str, Any]:
        """Run ruff --fix to auto-fix lint issues. Returns what changed."""
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", "src/", "tests/"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root,
            )
            return {
                "success": result.returncode == 0,
                "fixed": "Fixed" in result.stdout or result.returncode == 0,
                "stdout": result.stdout[:500],
                "stderr": result.stderr[:500],
            }
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return {"success": False, "error": str(e)}

    def heal_format(self) -> dict[str, Any]:
        """Run ruff format to auto-fix formatting."""
        try:
            result = subprocess.run(
                ["ruff", "format", "src/", "tests/"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:500],
            }
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return {"success": False, "error": str(e)}

    def heal_state(self) -> dict[str, Any]:
        """Clean corrupted state files by re-initializing them."""
        repaired: list[str] = []
        for filename in os.listdir(self.state_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.state_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    json.load(f)
            except (json.JSONDecodeError, OSError):
                # Corrupted — back up and remove
                backup = filepath + ".corrupted"
                try:
                    os.replace(filepath, backup)
                    repaired.append(filename)
                    logger.warning("Repaired corrupted state file: %s", filename)
                except OSError:
                    pass
        return {"repaired": repaired, "count": len(repaired)}

    # ── EVALUATE ────────────────────────────────────────────────────────

    def eval_lint(self) -> dict[str, Any]:
        """Run ruff check and count errors."""
        try:
            result = subprocess.run(
                ["ruff", "check", "src/", "tests/"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root,
            )
            error_count = result.stdout.count("\n") if result.returncode != 0 else 0
            # Parse "Found N errors" from output
            for line in result.stdout.splitlines():
                if "Found" in line and "error" in line:
                    parts = line.split()
                    for i, word in enumerate(parts):
                        if word == "Found" and i + 1 < len(parts):
                            with contextlib.suppress(ValueError):
                                error_count = int(parts[i + 1])
            return {
                "passed": result.returncode == 0,
                "error_count": error_count,
                "score": 100 if result.returncode == 0 else max(0, 100 - error_count * 5),
            }
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return {"passed": False, "error_count": -1, "score": 0, "error": str(e)}

    def eval_typecheck(self) -> dict[str, Any]:
        """Run mypy and count errors."""
        try:
            result = subprocess.run(
                ["mypy", "src/"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.project_root,
            )
            error_count = 0
            for line in result.stdout.splitlines():
                if ": error:" in line:
                    error_count += 1
                if "no issues found" in line.lower():
                    error_count = 0
            return {
                "passed": result.returncode == 0,
                "error_count": error_count,
                "score": 100 if result.returncode == 0 else max(0, 100 - error_count * 10),
            }
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return {"passed": False, "error_count": -1, "score": 0, "error": str(e)}

    def eval_tests(self) -> dict[str, Any]:
        """Run pytest and count pass/fail/total."""
        try:
            start = time.monotonic()
            result = subprocess.run(
                ["pytest", "tests/", "-v", "--tb=no", "-q"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.project_root,
            )
            elapsed = round(time.monotonic() - start, 2)

            passed = 0
            failed = 0
            total = 0
            for line in result.stdout.splitlines():
                if " passed" in line or " failed" in line:
                    # Strip ANSI codes and comma-separated parts
                    clean = line.replace(",", "")
                    parts = clean.split()
                    for i, word in enumerate(parts):
                        if word == "passed" and i > 0:
                            with contextlib.suppress(ValueError):
                                passed = int(parts[i - 1])
                        if word == "failed" and i > 0:
                            with contextlib.suppress(ValueError):
                                failed = int(parts[i - 1])
            total = passed + failed
            return {
                "passed_count": passed,
                "failed_count": failed,
                "total": total,
                "all_passed": result.returncode == 0,
                "elapsed_seconds": elapsed,
                "score": 100 if result.returncode == 0 else round(
                    passed / max(1, total) * 100
                ),
            }
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return {
                "passed_count": 0,
                "failed_count": 0,
                "total": 0,
                "all_passed": False,
                "elapsed_seconds": 0,
                "score": 0,
                "error": str(e),
            }

    def eval_services(self) -> dict[str, Any]:
        """Check health of all expected services."""
        services = self.discover_services()
        healthy = sum(1 for s in services if s["healthy"])
        critical_down = [
            s["name"] for s in services
            if not s["healthy"] and s["critical"]
        ]
        total = len(services)
        score = round(healthy / max(1, total) * 100) if not critical_down else max(
            0, round(healthy / max(1, total) * 100) - 20
        )
        return {
            "services": services,
            "healthy_count": healthy,
            "total": total,
            "critical_down": critical_down,
            "score": score,
        }

    # ── FULL EVALUATION ─────────────────────────────────────────────────

    def run_full_eval(self, include_services: bool = True) -> dict[str, Any]:
        """Run all evaluation gates and produce a scored report.

        Args:
            include_services: If False, skip service health checks (for CI).
        """
        now = datetime.now(timezone.utc).isoformat()
        report: dict[str, Any] = {"timestamp": now}

        # Quality gates
        report["lint"] = self.eval_lint()
        report["typecheck"] = self.eval_typecheck()
        report["tests"] = self.eval_tests()

        # Service health (optional — skip in CI)
        if include_services:
            report["services"] = self.eval_services()
        else:
            report["services"] = {"score": 100, "skipped": True}

        # Discovery
        report["config_drift"] = self.discover_config_drift()

        # Composite score
        weights = {"lint": 0.20, "typecheck": 0.20, "tests": 0.40, "services": 0.20}
        composite = sum(
            report[k]["score"] * w for k, w in weights.items()
        )
        report["composite_score"] = round(composite, 1)
        report["grade"] = self._score_to_grade(composite)

        # Trend (compare to last eval)
        previous = self._load_last_eval()
        if previous:
            prev_score = previous.get("composite_score", 0)
            report["trend"] = {
                "previous_score": prev_score,
                "delta": round(composite - prev_score, 1),
                "direction": "improving" if composite > prev_score + 1
                else "declining" if composite < prev_score - 1
                else "stable",
                "previous_timestamp": previous.get("timestamp", ""),
            }
            # Track test count trend
            prev_tests = previous.get("tests", {}).get("total", 0)
            curr_tests = report["tests"]["total"]
            if prev_tests and curr_tests:
                report["trend"]["test_count_delta"] = curr_tests - prev_tests
        else:
            report["trend"] = {"previous_score": None, "direction": "first_run"}

        # Save to history
        self._save_eval(report)

        return report

    def _score_to_grade(self, score: float) -> str:
        """Convert composite score to letter grade."""
        for grade, threshold in GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"

    # ── REPORT GENERATION ───────────────────────────────────────────────

    def generate_markdown_report(self, report: dict[str, Any]) -> str:
        """Generate a human-readable markdown health report."""
        lines: list[str] = []
        grade = report.get("grade", "?")
        score = report.get("composite_score", 0)
        ts = report.get("timestamp", "")

        lines.append("# Self-Optimization Health Report")
        lines.append("")
        lines.append(f"**Grade: {grade}** ({score}/100) | {ts}")
        lines.append("")

        # Quality gates
        lint = report.get("lint", {})
        tc = report.get("typecheck", {})
        tests = report.get("tests", {})
        services = report.get("services", {})

        lines.append("## Quality Gates")
        lines.append("")
        lines.append("| Gate | Status | Score | Details |")
        lines.append("|------|--------|-------|---------|")
        lines.append(
            f"| Lint (ruff) | {'PASS' if lint.get('passed') else 'FAIL'} "
            f"| {lint.get('score', 0)}/100 "
            f"| {lint.get('error_count', '?')} errors |"
        )
        lines.append(
            f"| Types (mypy) | {'PASS' if tc.get('passed') else 'FAIL'} "
            f"| {tc.get('score', 0)}/100 "
            f"| {tc.get('error_count', '?')} errors |"
        )
        lines.append(
            f"| Tests (pytest) | {'PASS' if tests.get('all_passed') else 'FAIL'} "
            f"| {tests.get('score', 0)}/100 "
            f"| {tests.get('passed_count', 0)}/{tests.get('total', 0)} passed "
            f"in {tests.get('elapsed_seconds', 0)}s |"
        )
        if not services.get("skipped"):
            critical = services.get("critical_down", [])
            lines.append(
                f"| Services | "
                f"{'DEGRADED' if critical else 'HEALTHY'} "
                f"| {services.get('score', 0)}/100 "
                f"| {services.get('healthy_count', 0)}/{services.get('total', 0)} up"
                f"{' | DOWN: ' + ', '.join(critical) if critical else ''} |"
            )

        # Trend
        trend = report.get("trend", {})
        if trend.get("previous_score") is not None:
            lines.append("")
            lines.append("## Trend")
            lines.append("")
            delta = trend.get("delta", 0)
            arrow = "+" if delta > 0 else ""
            lines.append(
                f"- **Direction**: {trend.get('direction', '?')} "
                f"({arrow}{delta} from {trend.get('previous_score')})"
            )
            test_delta = trend.get("test_count_delta")
            if test_delta is not None:
                lines.append(
                    f"- **Test count**: {'+' if test_delta >= 0 else ''}{test_delta} "
                    f"tests since last eval"
                )

        # Config drift
        drift = report.get("config_drift", {})
        drifted = drift.get("drifted", [])
        if drifted:
            lines.append("")
            lines.append("## Config Drift Detected")
            lines.append("")
            for path in drifted:
                lines.append(f"- `{path}` changed since last eval")

        # Problems requiring human attention
        problems: list[str] = []
        if not lint.get("passed"):
            problems.append(f"Lint: {lint.get('error_count', '?')} errors")
        if not tc.get("passed"):
            problems.append(f"Types: {tc.get('error_count', '?')} errors")
        if not tests.get("all_passed"):
            problems.append(
                f"Tests: {tests.get('failed_count', '?')} failures "
                f"out of {tests.get('total', '?')}"
            )
        critical = services.get("critical_down", [])
        if critical:
            problems.append(f"Services down: {', '.join(critical)}")

        if problems:
            lines.append("")
            lines.append("## Action Required")
            lines.append("")
            for p in problems:
                lines.append(f"- [ ] {p}")
        else:
            lines.append("")
            lines.append("## Status: All Clear")
            lines.append("")
            lines.append("All quality gates passing. No action required.")

        lines.append("")
        lines.append(
            f"---\n*Generated by self-optimization self-eval at {ts}*"
        )

        return "\n".join(lines) + "\n"

    def generate_github_issue_body(self, report: dict[str, Any]) -> str | None:
        """Generate a GitHub Issue body if there are problems. Returns None if healthy."""
        grade = report.get("grade", "?")
        if grade in ("A", "B"):
            return None  # Healthy enough, no issue needed

        body = self.generate_markdown_report(report)
        trend = report.get("trend", {})
        direction = trend.get("direction", "?")

        header = (
            f"The self-optimization system scored **{grade}** "
            f"({report.get('composite_score', 0)}/100), "
            f"trend: {direction}.\n\n"
            "This issue was created automatically by the self-eval workflow. "
            "Review the report below and close when resolved.\n\n---\n\n"
        )
        return header + body

    # ── HISTORY ─────────────────────────────────────────────────────────

    def _load_last_eval(self) -> dict[str, Any] | None:
        """Load the most recent evaluation from history."""
        history = self._load_history()
        return history[-1] if history else None

    def _load_history(self) -> list[dict[str, Any]]:
        """Load evaluation history."""
        try:
            with open(self._history_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_eval(self, report: dict[str, Any]) -> None:
        """Append evaluation to history (capped at 90 entries ≈ 3 months daily)."""
        history = self._load_history()
        history.append(report)
        history = history[-90:]
        try:
            tmp = self._history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, default=str)
            os.replace(tmp, self._history_file)
        except OSError as e:
            logger.warning("Failed to save eval history: %s", e)

    def get_trend_summary(self) -> dict[str, Any]:
        """Summarize trends from evaluation history."""
        history = self._load_history()
        if len(history) < 2:
            return {"evaluations": len(history), "trend": "insufficient_data"}

        scores = [h.get("composite_score", 0) for h in history]
        test_counts = [h.get("tests", {}).get("total", 0) for h in history]

        return {
            "evaluations": len(history),
            "latest_score": scores[-1],
            "best_score": max(scores),
            "worst_score": min(scores),
            "average_score": round(sum(scores) / len(scores), 1),
            "latest_test_count": test_counts[-1] if test_counts else 0,
            "test_count_growth": test_counts[-1] - test_counts[0] if test_counts else 0,
            "scores_last_7": scores[-7:],
        }
