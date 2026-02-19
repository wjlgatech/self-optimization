import os
import subprocess
import json
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging

class ActivityScanner:
    """
    Scans git repositories and file system for activity signals.
    Primary source of truth for determining idle vs. productive states.
    """
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.subdirectories = self._discover_git_repos()
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _discover_git_repos(self) -> List[str]:
        """
        Discover all git repositories in the workspace
        
        :return: List of git repository paths
        """
        repos = []
        for item in os.listdir(self.workspace_root):
            path = os.path.join(self.workspace_root, item)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, '.git')):
                repos.append(path)
        
        return repos

    def get_recent_commits(self, time_window_hours: int = 24) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all commits across repositories within time window
        
        :param time_window_hours: Hours to look back
        :return: Dictionary of commits by repository
        """
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
        all_commits = {}
        
        for repo_path in self.subdirectories:
            try:
                commits = self._get_repo_commits(repo_path, cutoff_time)
                all_commits[repo_path] = commits
            except Exception as e:
                self.logger.error(f"Error reading commits from {repo_path}: {e}")
        
        return all_commits

    def _get_repo_commits(self, repo_path: str, since_time: datetime) -> List[Dict[str, Any]]:
        """
        Get commits from a specific repository
        
        :param repo_path: Path to git repository
        :param since_time: Get commits after this time
        :return: List of commit data
        """
        format_str = '%H|%an|%ae|%ai|%s'
        # Handle timezone-aware datetime
        if since_time.tzinfo is not None:
            since_str = since_time.isoformat()
        else:
            since_str = since_time.isoformat()
        cmd = f'git log --since="{since_str}" --format="{format_str}"'
        
        try:
            result = subprocess.run(
                cmd, 
                shell=True, 
                cwd=repo_path,
                capture_output=True, 
                text=True
            )
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|')
                    commits.append({
                        'hash': parts[0],
                        'author': parts[1],
                        'email': parts[2],
                        'timestamp': parts[3],
                        'message': parts[4]
                    })
            
            return commits
        except Exception as e:
            self.logger.error(f"Error executing git log: {e}")
            return []

    def calculate_activity_score(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Calculate overall activity score
        
        :param time_window_hours: Hours to analyze
        :return: Activity score and breakdown
        """
        commits = self.get_recent_commits(time_window_hours)
        
        total_commits = sum(len(c) for c in commits.values())
        
        # Calculate metrics
        activity_score = {
            'total_commits': total_commits,
            'repositories_active': len([r for r in commits.values() if r]),
            'time_window_hours': time_window_hours,
            'is_idle': total_commits == 0,
            'breakdown_by_repo': {
                repo: len(commits_list) 
                for repo, commits_list in commits.items()
            }
        }
        
        return activity_score

    def get_idle_duration(self) -> float:
        """
        Calculate how long since last activity across all repositories
        
        :return: Hours since last activity
        """
        latest_commit_time = None
        
        for repo_path in self.subdirectories:
            try:
                # Get the timestamp of the most recent commit
                cmd = 'git log -1 --format=%ai'
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
                
                if result.stdout.strip():
                    # Parse timestamp: "2026-02-19 09:55:29 -0800"
                    timestamp_str = result.stdout.strip()
                    # Extract just the date and time part (first 19 chars)
                    try:
                        commit_time = datetime.strptime(timestamp_str[:19], '%Y-%m-%d %H:%M:%S')
                    except:
                        # Fallback: try fromisoformat on trimmed version
                        if '+' in timestamp_str or '-' in timestamp_str[10:]:
                            timestamp_str = timestamp_str.split('+')[0].split(' -')[0].split(' +')[0]
                        commit_time = datetime.fromisoformat(timestamp_str)
                    
                    if latest_commit_time is None or commit_time > latest_commit_time:
                        latest_commit_time = commit_time
            except Exception as e:
                self.logger.error(f"Error getting latest commit from {repo_path}: {e}")
        
        if latest_commit_time is None:
            return 999.0  # Large number instead of inf
        
        # Use timezone-naive comparison
        current_time = datetime.now()
        idle_duration = (current_time - latest_commit_time).total_seconds() / 3600
        return idle_duration

    def get_file_modifications(self, time_window_hours: int = 24) -> Dict[str, List[str]]:
        """
        Get modified files across repositories
        
        :param time_window_hours: Hours to look back
        :return: Modified files by repository
        """
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
        modifications = {}
        
        for repo_path in self.subdirectories:
            try:
                cmd = f'git diff --name-only HEAD~1..HEAD'
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
                
                if result.stdout.strip():
                    modifications[repo_path] = result.stdout.strip().split('\n')
            except Exception as e:
                self.logger.error(f"Error getting file modifications from {repo_path}: {e}")
        
        return modifications