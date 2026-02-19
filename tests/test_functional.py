"""
Functional tests — validate complete user-facing scenarios and
expected behavior from the end-user's perspective.
"""

import json
from unittest.mock import MagicMock

from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework

# ── Scenario: Agent Productivity Monitoring ──────────────────────────────


class TestAgentProductivityScenario:
    """Simulate a full day of agent activity monitoring."""

    def test_productive_agent_not_interrupted(self):
        """An agent with sufficient productive work should not trigger alerts."""
        ais = AntiIdlingSystem(idle_threshold=0.5)
        callback = MagicMock()
        ais.register_intervention_callback(callback)

        # Simulate 12+ hours of productive work in a 24h window
        ais.log_activity({"duration": 50000, "is_productive": True})
        # idle_rate = 1 - 50000/86400 ≈ 0.42 < 0.5
        ais.detect_and_interrupt_idle_state()
        callback.assert_not_called()

    def test_lazy_agent_gets_interrupted(self):
        """An agent with very little productive work should trigger intervention."""
        ais = AntiIdlingSystem(idle_threshold=0.9)
        callback = MagicMock()
        ais.register_intervention_callback(callback)

        # Only 1 hour productive in 24h
        ais.log_activity({"duration": 3600, "is_productive": True})
        # idle_rate = 1 - 3600/86400 ≈ 0.958 > 0.9
        ais.detect_and_interrupt_idle_state()
        callback.assert_called_once()

    def test_mixed_activity_day(self):
        """Simulate a realistic day with productive and non-productive activities."""
        ais = AntiIdlingSystem(idle_threshold=0.7)
        callback = MagicMock()
        ais.register_intervention_callback(callback)

        activities = [
            {"type": "coding", "duration": 14400, "is_productive": True},  # 4h
            {"type": "meeting", "duration": 3600, "is_productive": True},  # 1h
            {"type": "break", "duration": 1800, "is_productive": False},  # 30m
            {"type": "research", "duration": 7200, "is_productive": True},  # 2h
            {"type": "browsing", "duration": 3600, "is_productive": False},  # 1h
        ]
        for a in activities:
            ais.log_activity(a)

        # productive = 14400 + 3600 + 7200 = 25200s
        # idle_rate = 1 - 25200/86400 ≈ 0.708 > 0.7
        ais.detect_and_interrupt_idle_state()
        callback.assert_called_once()


# ── Scenario: Results Quality Pipeline ───────────────────────────────────


class TestResultsQualityPipeline:
    """Simulate verifying outputs from various subsystems."""

    def test_high_quality_result(self):
        """A result with all quality markers should pass all criteria."""
        fw = ResultsVerificationFramework()
        result = {
            "next_step": "deploy to staging",
            "recommendation": "increase cache TTL",
            "score": 92,
            "details": [{"metric": "latency", "value": 42}],
        }
        v = fw.verify_results(result)
        assert v["specific"] is True
        assert v["reusable"] is True
        assert v["compoundable"] is True
        assert v["actionable"] is True
        assert v["measurable"] is True

    def test_minimal_result(self):
        """A bare-minimum single-key result."""
        fw = ResultsVerificationFramework()
        v = fw.verify_results({"status": "ok"})
        assert v["specific"] is True
        assert v["reusable"] is False  # only 1 key
        assert v["compoundable"] is False  # no list/dict values

    def test_empty_result(self):
        fw = ResultsVerificationFramework()
        v = fw.verify_results({})
        assert v["specific"] is False
        assert v["reusable"] is False
        assert v["measurable"] is False  # empty dict now returns False
        assert v["compoundable"] is False

    def test_success_rate_tracking(self):
        """Verify success rate with mix of passing and failing results."""
        fw = ResultsVerificationFramework()
        # Good results: all 5 criteria pass
        for _ in range(5):
            fw.verify_results(
                {
                    "next_step": "go",
                    "score": 95,
                    "items": [1, 2, 3],
                }
            )
        # Bad results: missing action keys
        for _ in range(5):
            fw.verify_results({"a": 1, "b": 2})
        assert fw.get_verification_success_rate() == 50.0


# ── Scenario: Custom Verification Criteria ───────────────────────────────


class TestCustomCriteriaScenario:
    def test_domain_specific_criterion(self):
        """Add a domain-specific check (e.g., results must have a 'confidence' > 0.8)."""
        fw = ResultsVerificationFramework()

        def check_confidence(results):
            return results.get("confidence", 0) > 0.8

        fw.add_custom_verification_criterion("confident", check_confidence)

        v1 = fw.verify_results({"confidence": 0.95, "prediction": "cat"})
        assert v1["confident"] is True

        v2 = fw.verify_results({"confidence": 0.3, "prediction": "dog"})
        assert v2["confident"] is False

    def test_replace_actionability_with_custom(self):
        """User can replace the built-in actionability criterion."""
        fw = ResultsVerificationFramework()

        def custom_actionability(results):
            return "action" in results

        fw.add_custom_verification_criterion("actionable", custom_actionability)

        v = fw.verify_results({"action": "deploy", "score": 95, "items": [1]})
        assert v["actionable"] is True


# ── Scenario: Emergency Action Generation ────────────────────────────────


class TestEmergencyActionScenario:
    def test_emergency_actions_are_meaningful(self):
        """Emergency actions should be recognizable strategy names."""
        ais = AntiIdlingSystem()
        actions = ais.generate_emergency_actions()
        for action in actions:
            assert "_" in action  # snake_case format
            assert len(action) > 5  # not trivially short

    def test_emergency_actions_are_static(self):
        """Actions are hardcoded — not context-aware."""
        ais = AntiIdlingSystem()
        a1 = ais.generate_emergency_actions()
        a2 = ais.generate_emergency_actions()
        assert a1 == a2  # always identical


# ── Scenario: File Export and Reload ─────────────────────────────────────


class TestExportReloadScenario:
    def test_export_and_reload_roundtrip(self, tmp_path):
        """Verify exported JSON can be loaded back and inspected."""
        fw = ResultsVerificationFramework()
        fw.verify_results({"metric": 42, "label": "test"})
        fw.verify_results({"score": 99, "items": [1, 2, 3]})

        filepath = str(tmp_path / "history.json")
        fw.export_verification_history(filepath)

        with open(filepath) as f:
            reloaded = json.load(f)

        assert len(reloaded) == 2
        assert reloaded[0]["results"]["metric"] == 42
        assert reloaded[1]["results"]["score"] == 99
        assert isinstance(reloaded[0]["timestamp"], str)
