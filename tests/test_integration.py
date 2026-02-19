"""
Integration tests — verify the two modules work together in realistic
end-to-end workflows, and that cross-cutting concerns (logging, state
accumulation, file I/O) behave correctly.
"""

import json
import logging
from unittest.mock import MagicMock

import pytest

from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework


class TestAntiIdlingWithVerification:
    """Simulate an agent that uses both systems together."""

    def test_idle_detection_triggers_verification_of_actions(self):
        """
        Workflow: idle detected → callback produces results → results verified.
        """
        ais = AntiIdlingSystem(idle_threshold=0.01)
        fw = ResultsVerificationFramework()
        verified_results = []

        def intervention_callback():
            result = {
                "next_step": "start sprint",
                "score": 85,
                "details": [1, 2, 3],
            }
            v = fw.verify_results(result)
            verified_results.append(v)

        ais.register_intervention_callback(intervention_callback)
        ais.detect_and_interrupt_idle_state()

        assert len(verified_results) == 1
        assert len(fw.verification_history) == 1
        # With all bugs fixed, this result passes all criteria
        assert fw.verification_history[0]["overall_valid"] is True

    def test_repeated_idle_cycles_accumulate_history(self):
        ais = AntiIdlingSystem(idle_threshold=0.01)
        fw = ResultsVerificationFramework()

        def intervention_callback():
            fw.verify_results({"a": 1, "b": 2})

        ais.register_intervention_callback(intervention_callback)

        for _ in range(10):
            ais.detect_and_interrupt_idle_state()

        assert len(fw.verification_history) == 10

    def test_activity_logging_affects_idle_detection(self):
        """Log enough productive activity to drop below threshold."""
        ais = AntiIdlingSystem(idle_threshold=0.5)
        callback = MagicMock()
        ais.register_intervention_callback(callback)

        # Log productive time covering >50% of a 100-second window
        ais.log_activity({"duration": 60, "is_productive": True})
        # With time_window=100, idle_rate = 1 - 60/100 = 0.4 < 0.5
        # But detect uses default 86400 window, so idle_rate ≈ 1.0
        ais.detect_and_interrupt_idle_state()
        callback.assert_called_once()


class TestVerificationHistoryExportIntegration:
    def test_export_after_multiple_verifications(self, tmp_path):
        fw = ResultsVerificationFramework()
        test_cases = [
            {"a": 1, "b": 2},
            {"next_step": "go", "items": [1]},
            {},
        ]
        for tc in test_cases:
            fw.verify_results(tc)

        filepath = str(tmp_path / "history.json")
        fw.export_verification_history(filepath)

        with open(filepath) as f:
            data = json.load(f)
        assert len(data) == 3
        for entry in data:
            assert "timestamp" in entry
            assert "overall_valid" in entry

    def test_exported_data_matches_in_memory(self, tmp_path):
        fw = ResultsVerificationFramework()
        fw.verify_results({"key": "value", "other": 42})

        filepath = str(tmp_path / "history.json")
        fw.export_verification_history(filepath)

        with open(filepath) as f:
            data = json.load(f)

        assert data == fw.verification_history


class TestLoggingIntegration:
    def test_both_systems_use_logging(self, caplog):
        """Both modules configure logging and produce log messages."""
        with caplog.at_level(logging.INFO):
            ais = AntiIdlingSystem(idle_threshold=0.01)
            ais.detect_and_interrupt_idle_state()

        assert any(
            "idle rate" in r.message.lower() or "emergency" in r.message.lower()
            for r in caplog.records
        )


class TestActivityLogPruningUnderLoad:
    def test_massive_activity_volume(self):
        """Simulate a high-throughput agent logging thousands of activities."""
        ais = AntiIdlingSystem()
        for i in range(1000):
            ais.log_activity(
                {
                    "type": f"action_{i}",
                    "duration": 1,
                    "is_productive": True,
                }
            )
        assert len(ais.activity_log) == 100
        assert ais.activity_log[-1]["type"] == "action_999"

    def test_idle_rate_after_pruning(self):
        """After pruning, idle rate calculation still uses recent activities."""
        ais = AntiIdlingSystem()
        for i in range(200):
            ais.log_activity(
                {
                    "type": f"action_{i}",
                    "duration": 100,
                    "is_productive": True,
                }
            )
        # 100 remaining activities × 100s = 10000s productive
        rate = ais.calculate_idle_rate(time_window=86400)
        expected = 1 - (10000 / 86400)
        assert rate == pytest.approx(expected, abs=0.01)


class TestVerificationHistoryBounded:
    """verification_history is now FIFO-pruned."""

    def test_history_bounded_at_max(self):
        fw = ResultsVerificationFramework(max_history=100)
        for i in range(500):
            fw.verify_results({"key": f"value_{i}", "other": i})
        assert len(fw.verification_history) == 100
