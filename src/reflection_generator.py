import logging
from datetime import datetime
from typing import Any, Dict, List

from src.activity_scanner import ActivityScanner


class ReflectionGenerator:
    """
    Generates daily reflections based on actual activity data
    """

    def __init__(self, activity_scanner: ActivityScanner):
        self.scanner = activity_scanner

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def generate_daily_reflection(self) -> Dict[str, Any]:
        """
        Generate a daily reflection based on actual activity

        :return: Reflection content as dictionary
        """
        # Gather activity data
        commits = self.scanner.get_recent_commits(time_window_hours=24)
        activity_score = self.scanner.calculate_activity_score(time_window_hours=24)
        idle_duration = self.scanner.get_idle_duration()
        file_mods = self.scanner.get_file_modifications(time_window_hours=24)

        # Build reflection
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "activity_summary": {
                "total_commits": activity_score["total_commits"],
                "repositories_active": activity_score["repositories_active"],
                "is_idle": activity_score["is_idle"],
                "idle_duration_hours": idle_duration,
            },
            "achievements": self._extract_achievements(commits),
            "challenges": self._identify_challenges(commits, idle_duration),
            "growth_insights": self._analyze_growth(),
            "tomorrow_priorities": self._generate_priorities(commits),
            "quality_metrics": {
                "productivity_score": self._calculate_productivity_score(activity_score),
                "code_quality_indicators": self._assess_code_quality(file_mods),
            },
        }

        return reflection

    def _extract_achievements(self, commits: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """
        Extract key achievements from commit messages

        :param commits: Commit data by repository
        :return: List of achievements
        """
        achievements = []

        for repo_commits in commits.values():
            for commit in repo_commits:
                message = commit.get("message", "")
                if any(
                    keyword in message.lower()
                    for keyword in ["implemented", "completed", "fixed", "resolved", "deployed"]
                ):
                    achievements.append(f"- {message}")

        return achievements[:10]  # Top 10 achievements

    def _identify_challenges(
        self, commits: Dict[str, List[Dict[str, Any]]], idle_duration: float
    ) -> List[str]:
        """
        Identify challenges and friction points

        :param commits: Commit data
        :param idle_duration: Current idle duration
        :return: List of identified challenges
        """
        challenges = []

        if idle_duration > 2:
            challenges.append(f"- Idle for {idle_duration:.1f} hours - need to break stagnation")

        # Analyze commit frequency for patterns
        total_commits = sum(len(c) for c in commits.values())
        if total_commits == 0:
            challenges.append("- No activity detected in the past 24 hours")
        elif total_commits < 3:
            challenges.append("- Low commit frequency - productivity may be declining")

        return challenges

    def _analyze_growth(self) -> List[str]:
        """
        Analyze capability and skill growth

        :return: List of growth insights
        """
        return [
            "- Recursive self-improvement system now tracking real activity",
            "- Integration with git-based activity metrics improving accuracy",
            "- Multi-repository coordination enhancing overall capability",
        ]

    def _generate_priorities(self, commits: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """
        Generate tomorrow's priorities based on today's patterns

        :param commits: Today's commit data
        :return: Tomorrow's priority list
        """
        return [
            "- Continue momentum on active projects",
            "- Review and refine implemented features",
            "- Ensure comprehensive testing of new functionality",
        ]

    def _calculate_productivity_score(self, activity_score: Dict[str, Any]) -> float:
        """
        Calculate a 0-1 productivity score

        :param activity_score: Activity metrics
        :return: Productivity score
        """
        if activity_score["is_idle"]:
            return 0.0

        # Simple scoring based on commit count
        commit_count = activity_score["total_commits"]

        if commit_count >= 10:
            return 1.0
        elif commit_count >= 5:
            return 0.8
        elif commit_count >= 2:
            return 0.6
        else:
            return 0.3

    def _assess_code_quality(self, file_modifications: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Assess code quality based on modification patterns

        :param file_modifications: Modified files by repository
        :return: Code quality assessment
        """
        return {
            "files_modified": sum(len(files) for files in file_modifications.values()),
            "repositories_affected": len(file_modifications),
            "change_scope": "comprehensive" if len(file_modifications) > 2 else "focused",
        }

    def save_reflection(self, reflection: Dict[str, Any], output_path: str):
        """
        Save reflection to file

        :param reflection: Reflection data
        :param output_path: Path to save reflection
        """
        # Create markdown reflection
        md_content = self._format_reflection_as_markdown(reflection)

        try:
            with open(output_path, "w") as f:
                f.write(md_content)

            self.logger.info(f"Reflection saved to {output_path}")
        except Exception as e:
            self.logger.error(f"Error saving reflection: {e}")

    def _format_reflection_as_markdown(self, reflection: Dict[str, Any]) -> str:
        """
        Format reflection as markdown

        :param reflection: Reflection data
        :return: Markdown formatted reflection
        """
        md = f"# Daily Reflection - {reflection['timestamp'].split('T')[0]}\n\n"

        md += "## Activity Summary\n"
        for key, value in reflection["activity_summary"].items():
            md += f"- {key}: {value}\n"

        md += "\n## Achievements\n"
        for achievement in reflection["achievements"]:
            md += f"{achievement}\n"

        md += "\n## Challenges\n"
        for challenge in reflection["challenges"]:
            md += f"{challenge}\n"

        md += "\n## Growth Insights\n"
        for insight in reflection["growth_insights"]:
            md += f"{insight}\n"

        md += "\n## Tomorrow's Priorities\n"
        for priority in reflection["tomorrow_priorities"]:
            md += f"{priority}\n"

        md += "\n## Quality Metrics\n"
        md += f"- Productivity Score: {reflection['quality_metrics']['productivity_score']}\n"

        return md
