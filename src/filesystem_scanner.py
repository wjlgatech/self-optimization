"""Real filesystem activity scanner for ground-truth activity detection.

Scans the OpenClaw workspace for git logs, file modification times,
and daily reflection markdown files.
"""

import logging
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FilesystemScanner:
    """Scans workspace filesystem for real activity signals."""

    def __init__(self, workspace_dir: str = "") -> None:
        if not workspace_dir:
            workspace_dir = os.path.expanduser("~/.openclaw/workspace")
        self.workspace_dir = os.path.expanduser(workspace_dir)

    def scan_activity(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Scan all sources for activity within the given time window.

        Returns list of activities with: type, path, timestamp, description,
        is_productive, duration (estimated).
        """
        activities: List[Dict[str, Any]] = []

        # 1. Git commits from workspace and known sub-repos
        for repo_path in self._find_git_repos():
            try:
                commits = self.get_recent_commits(repo_path, hours)
                activities.extend(commits)
            except Exception as e:
                logger.debug("Git scan failed for %s: %s", repo_path, e)

        # 2. File modifications
        try:
            modified = self.get_modified_files(self.workspace_dir, hours)
            activities.extend(modified)
        except Exception as e:
            logger.debug("File scan failed: %s", e)

        # 3. Daily reflections
        for reflection_dir in [
            os.path.join(self.workspace_dir, "memory", "daily-reflections"),
            os.path.join(self.workspace_dir, "memory", "reflections", "daily"),
        ]:
            if os.path.isdir(reflection_dir):
                try:
                    reflections = self._scan_reflections(reflection_dir, hours)
                    activities.extend(reflections)
                except Exception as e:
                    logger.debug("Reflection scan failed: %s", e)

        # Sort by timestamp descending
        activities.sort(key=lambda a: a.get("timestamp", 0), reverse=True)
        return activities

    def get_recent_commits(self, repo_path: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get git commits from the given repo within the time window.

        Runs: git -C {repo_path} log --since="{hours} hours ago" --format="%H|%ai|%s"
        """
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return []

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    repo_path,
                    "log",
                    "--all",
                    f"--since={hours} hours ago",
                    "--format=%H|%ai|%s",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        if result.returncode != 0:
            return []

        commits: List[Dict[str, Any]] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            commit_hash, date_str, subject = parts
            try:
                dt = datetime.fromisoformat(date_str.strip())
                ts = dt.timestamp()
            except ValueError:
                ts = time.time()
            commits.append(
                {
                    "type": "git_commit",
                    "path": repo_path,
                    "timestamp": ts,
                    "description": subject.strip(),
                    "is_productive": True,
                    "duration": 1800,  # estimate 30 min per commit
                    "commit_hash": commit_hash.strip(),
                }
            )
        return commits

    def get_modified_files(self, directory: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Find files modified within the time window via os.walk + os.stat.

        Groups by parent directory to estimate work sessions.
        """
        if not os.path.isdir(directory):
            return []

        cutoff = time.time() - (hours * 3600)
        modified: List[Dict[str, Any]] = []

        skip_dirs = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", ".venv"}

        for root, dirs, files in os.walk(directory):
            # Prune hidden/cache dirs
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                except OSError:
                    continue
                if st.st_mtime >= cutoff:
                    modified.append(
                        {
                            "type": "file_modification",
                            "path": fpath,
                            "timestamp": st.st_mtime,
                            "description": f"Modified: {os.path.relpath(fpath, directory)}",
                            "is_productive": True,
                            "duration": 300,  # estimate 5 min per file touch
                        }
                    )

        return modified

    def parse_daily_reflection(self, filepath: str) -> Dict[str, Any]:
        """Parse a daily reflection markdown file into structured data.

        Extracts: achievements, challenges, priorities, and raw sections.
        """
        result: Dict[str, Any] = {
            "filepath": filepath,
            "achievements": [],
            "challenges": [],
            "priorities": [],
            "learnings": [],
            "raw_sections": {},
            "is_filled": False,
        }

        if not os.path.isfile(filepath):
            return result

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return result

        # Parse sections
        current_section: Optional[str] = None
        section_lines: List[str] = []

        for line in content.splitlines():
            header_match = re.match(r"^#{1,3}\s+(.+)", line)
            if header_match:
                if current_section and section_lines:
                    result["raw_sections"][current_section] = "\n".join(section_lines)
                current_section = header_match.group(1).strip().lower()
                section_lines = []
            else:
                section_lines.append(line)

        if current_section and section_lines:
            result["raw_sections"][current_section] = "\n".join(section_lines)

        # Extract bullet items from known sections
        for section_key, result_key in [
            ("achievements", "achievements"),
            ("1. achievements", "achievements"),
            ("accomplishments", "achievements"),
            ("challenges", "challenges"),
            ("2. challenges", "challenges"),
            ("learnings", "learnings"),
            ("4. growth and insights", "learnings"),
            ("tomorrow's preparation", "priorities"),
            ("tomorrow's priorities", "priorities"),
        ]:
            text = result["raw_sections"].get(section_key, "")
            items = self._extract_bullet_items(text)
            if items:
                result[result_key] = list(set(result[result_key]) | set(items))

        # Check if reflection has real content (not just template blanks)
        all_items = result["achievements"] + result["challenges"] + result["learnings"]
        result["is_filled"] = any(len(item.strip()) > 2 for item in all_items)

        return result

    def _extract_bullet_items(self, text: str) -> List[str]:
        """Extract non-empty bullet items from markdown text."""
        items: List[str] = []
        for line in text.splitlines():
            match = re.match(r"^\s*[-*]\s+(.+)", line)
            if match:
                item = match.group(1).strip()
                # Skip blank template items
                if item and item not in ("", "-"):
                    items.append(item)
        return items

    def _find_git_repos(self) -> List[str]:
        """Find git repositories in the workspace."""
        repos: List[str] = []
        if os.path.isdir(os.path.join(self.workspace_dir, ".git")):
            repos.append(self.workspace_dir)

        # Check immediate subdirectories for git repos
        if os.path.isdir(self.workspace_dir):
            try:
                for entry in os.scandir(self.workspace_dir):
                    if entry.is_dir() and os.path.isdir(os.path.join(entry.path, ".git")):
                        repos.append(entry.path)
            except OSError:
                pass
        return repos

    def _scan_reflections(self, reflection_dir: str, hours: int) -> List[Dict[str, Any]]:
        """Scan reflection directory for recently modified reflections."""
        cutoff = time.time() - (hours * 3600)
        activities: List[Dict[str, Any]] = []

        if not os.path.isdir(reflection_dir):
            return activities

        for fname in os.listdir(reflection_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(reflection_dir, fname)
            try:
                st = os.stat(fpath)
            except OSError:
                continue
            if st.st_mtime >= cutoff:
                parsed = self.parse_daily_reflection(fpath)
                activities.append(
                    {
                        "type": "daily_reflection",
                        "path": fpath,
                        "timestamp": st.st_mtime,
                        "description": f"Reflection: {fname}",
                        "is_productive": True,
                        "duration": 900,  # estimate 15 min for reflection
                        "parsed": parsed,
                    }
                )
        return activities
