"""Tests for FilesystemScanner — uses real filesystem via tmp_path."""

import os
import time

from filesystem_scanner import FilesystemScanner


class TestGetModifiedFiles:
    def test_detects_recently_created_file(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        (tmp_path / "hello.txt").write_text("world")
        result = scanner.get_modified_files(str(tmp_path), hours=1)
        assert len(result) >= 1
        assert any("hello.txt" in r["path"] for r in result)

    def test_all_entries_have_required_keys(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        (tmp_path / "a.py").write_text("pass")
        result = scanner.get_modified_files(str(tmp_path), hours=1)
        for entry in result:
            assert "type" in entry
            assert "path" in entry
            assert "timestamp" in entry
            assert "is_productive" in entry
            assert entry["type"] == "file_modification"

    def test_ignores_old_files(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        f = tmp_path / "old.txt"
        f.write_text("ancient")
        # Set mtime to 48 hours ago
        old_time = time.time() - 48 * 3600
        os.utime(f, (old_time, old_time))
        result = scanner.get_modified_files(str(tmp_path), hours=1)
        assert not any("old.txt" in r["path"] for r in result)

    def test_empty_directory(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        result = scanner.get_modified_files(str(tmp_path), hours=24)
        assert result == []

    def test_missing_directory(self):
        scanner = FilesystemScanner(workspace_dir="/nonexistent/path")
        result = scanner.get_modified_files("/nonexistent/path", hours=24)
        assert result == []

    def test_skips_hidden_files(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("public")
        result = scanner.get_modified_files(str(tmp_path), hours=1)
        assert not any(".hidden" in r["path"] for r in result)
        assert any("visible.txt" in r["path"] for r in result)


class TestParseDailyReflection:
    def test_parses_filled_reflection(self, tmp_path):
        content = """# Daily Reflection - 2026-02-19

## Achievements
- Implemented the scanner module
- Fixed 3 bugs in the gateway

## Challenges
- API rate limiting issues

## Learnings
- Always check model name compatibility

## Tomorrow's Priorities
1. Deploy to production
2. Write more tests
"""
        f = tmp_path / "2026-02-19-reflection.md"
        f.write_text(content)
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        parsed = scanner.parse_daily_reflection(str(f))
        assert parsed["is_filled"] is True
        assert len(parsed["achievements"]) >= 1
        assert len(parsed["challenges"]) >= 1

    def test_parses_empty_template(self, tmp_path):
        content = """# Daily Reflection

## Achievements
-

## Challenges
-
"""
        f = tmp_path / "empty.md"
        f.write_text(content)
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        parsed = scanner.parse_daily_reflection(str(f))
        assert parsed["is_filled"] is False

    def test_missing_file(self):
        scanner = FilesystemScanner()
        parsed = scanner.parse_daily_reflection("/nonexistent/file.md")
        assert parsed["is_filled"] is False
        assert parsed["achievements"] == []


class TestGetRecentCommits:
    def test_non_git_directory(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        result = scanner.get_recent_commits(str(tmp_path), hours=24)
        assert result == []

    def test_git_repo_with_commits(self, tmp_path):
        """Create a real git repo with a commit and verify detection."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo),
            capture_output=True,
        )
        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=str(repo),
            capture_output=True,
        )

        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        commits = scanner.get_recent_commits(str(repo), hours=1)
        assert len(commits) == 1
        assert commits[0]["type"] == "git_commit"
        assert "initial commit" in commits[0]["description"]


class TestScanActivity:
    def test_aggregates_file_modifications(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        (tmp_path / "work.py").write_text("code")
        (tmp_path / "notes.md").write_text("notes")
        activities = scanner.scan_activity(hours=1)
        assert len(activities) >= 2

    def test_returns_sorted_by_timestamp(self, tmp_path):
        scanner = FilesystemScanner(workspace_dir=str(tmp_path))
        (tmp_path / "a.txt").write_text("a")
        time.sleep(0.05)
        (tmp_path / "b.txt").write_text("b")
        activities = scanner.scan_activity(hours=1)
        if len(activities) >= 2:
            assert activities[0]["timestamp"] >= activities[1]["timestamp"]
