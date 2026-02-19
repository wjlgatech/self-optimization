"""
Edge case and robustness tests — adversarial inputs, boundary conditions,
type safety, concurrency concerns, and stress scenarios.
"""

import threading

import pytest

from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework

# ── Type Safety & Adversarial Inputs ─────────────────────────────────────


class TestAntiIdlingAdversarialInputs:
    def test_log_activity_with_none(self):
        """Passing None raises TypeError (validation)."""
        ais = AntiIdlingSystem()
        with pytest.raises(TypeError):
            ais.log_activity(None)

    def test_log_activity_with_list(self):
        ais = AntiIdlingSystem()
        with pytest.raises(TypeError):
            ais.log_activity([1, 2, 3])

    def test_log_activity_with_string(self):
        ais = AntiIdlingSystem()
        with pytest.raises(TypeError):
            ais.log_activity("not a dict")

    def test_log_activity_with_non_numeric_duration(self):
        """Non-numeric duration is silently accepted but breaks idle calculation."""
        ais = AntiIdlingSystem()
        ais.log_activity({"duration": "one hour", "is_productive": True})
        with pytest.raises(TypeError):
            ais.calculate_idle_rate()

    def test_very_large_duration_clamped(self):
        """Idle rate is clamped even with infinite duration."""
        ais = AntiIdlingSystem()
        ais.log_activity({"duration": float("inf"), "is_productive": True})
        rate = ais.calculate_idle_rate()
        assert rate == 0.0  # clamped

    def test_nan_duration(self):
        """NaN duration: clamping produces 1.0 since max/min with NaN returns 1.0."""
        ais = AntiIdlingSystem()
        ais.log_activity({"duration": float("nan"), "is_productive": True})
        rate = ais.calculate_idle_rate()
        assert rate == 1.0

    def test_negative_duration_clamped(self):
        """Negative duration: idle rate clamped to 1.0 max."""
        ais = AntiIdlingSystem()
        ais.log_activity({"duration": -1000, "is_productive": True})
        rate = ais.calculate_idle_rate(time_window=86400)
        assert rate == 1.0  # clamped

    def test_negative_time_window_raises(self):
        """Negative time_window raises ValueError."""
        ais = AntiIdlingSystem()
        ais.log_activity({"duration": 100, "is_productive": True})
        with pytest.raises(ValueError):
            ais.calculate_idle_rate(time_window=-1)


class TestVerificationAdversarialInputs:
    def test_verify_none_raises(self):
        """Passing None raises TypeError."""
        fw = ResultsVerificationFramework()
        with pytest.raises(TypeError):
            fw.verify_results(None)

    def test_verify_non_dict_raises(self):
        """Passing a list raises TypeError."""
        fw = ResultsVerificationFramework()
        with pytest.raises(TypeError):
            fw.verify_results([1, 2, 3])

    def test_verify_nested_deeply(self):
        fw = ResultsVerificationFramework()
        deep = {"level1": {"level2": {"level3": {"level4": "value"}}}}
        v = fw.verify_results(deep)
        assert v["compoundable"] is True  # has dict value
        assert v["measurable"] is False  # only dict value, no scalar

    def test_verify_with_special_characters(self):
        fw = ResultsVerificationFramework()
        v = fw.verify_results({"key\n\t": "value\x00", "other": 42})
        assert v["specific"] is True

    def test_verify_with_very_large_dict(self):
        fw = ResultsVerificationFramework()
        large = {f"key_{i}": i for i in range(10000)}
        v = fw.verify_results(large)
        assert v["specific"] is True  # zero is accepted now (value is not None)
        assert v["reusable"] is True
        assert v["measurable"] is True


# ── Boundary Conditions ──────────────────────────────────────────────────


class TestBoundaryConditions:
    def test_idle_threshold_exactly_equal_to_rate(self):
        """When idle_rate == threshold, should NOT trigger (uses > not >=)."""
        from unittest.mock import MagicMock

        ais = AntiIdlingSystem(idle_threshold=1.0)
        callback = MagicMock()
        ais.register_intervention_callback(callback)
        ais.detect_and_interrupt_idle_state()
        callback.assert_not_called()

    def test_activity_log_at_exactly_100(self):
        ais = AntiIdlingSystem()
        for i in range(100):
            ais.log_activity({"type": f"action_{i}"})
        assert len(ais.activity_log) == 100

    def test_activity_log_at_101_prunes_to_100(self):
        ais = AntiIdlingSystem()
        for i in range(101):
            ais.log_activity({"type": f"action_{i}"})
        assert len(ais.activity_log) == 100

    def test_single_key_reusability(self):
        fw = ResultsVerificationFramework()
        assert fw._check_reusability({"single": 1}) is False

    def test_two_keys_reusability(self):
        fw = ResultsVerificationFramework()
        assert fw._check_reusability({"a": 1, "b": 2}) is True

    def test_success_rate_single_success(self):
        fw = ResultsVerificationFramework()
        fw.verification_history = [{"overall_valid": True}]
        assert fw.get_verification_success_rate() == 100.0

    def test_success_rate_single_failure(self):
        fw = ResultsVerificationFramework()
        fw.verification_history = [{"overall_valid": False}]
        assert fw.get_verification_success_rate() == 0.0


# ── Thread Safety ────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_log_activity(self):
        ais = AntiIdlingSystem()
        errors = []

        def log_activities(start_id):
            try:
                for i in range(50):
                    ais.log_activity(
                        {
                            "type": f"thread_{start_id}_action_{i}",
                            "duration": 1,
                            "is_productive": True,
                        }
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=log_activities, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(ais.activity_log) <= 100

    def test_concurrent_verification(self):
        fw = ResultsVerificationFramework()
        errors = []

        def verify_batch(batch_id):
            try:
                for i in range(20):
                    fw.verify_results({f"key_{batch_id}_{i}": i, "b": 1})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=verify_batch, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ── Memory / Resource Concerns ───────────────────────────────────────────


class TestResourceConcerns:
    def test_verification_history_bounded(self):
        """verification_history is now FIFO-pruned at max_history."""
        fw = ResultsVerificationFramework(max_history=100)
        for i in range(1000):
            fw.verify_results({f"k{i}": i, "b": 1})
        assert len(fw.verification_history) == 100

    def test_activity_log_is_bounded(self):
        """activity_log is correctly bounded at 100."""
        ais = AntiIdlingSystem()
        for i in range(500):
            ais.log_activity({"type": f"a_{i}"})
        assert len(ais.activity_log) == 100


# ── API Misuse Tests ────────────────────────────────────────────────────


class TestAPIMisuse:
    def test_calculate_idle_rate_before_any_activity(self):
        ais = AntiIdlingSystem()
        rate = ais.calculate_idle_rate()
        assert rate == 1.0

    def test_detect_idle_before_any_activity(self):
        from unittest.mock import MagicMock

        ais = AntiIdlingSystem(idle_threshold=0.5)
        callback = MagicMock()
        ais.register_intervention_callback(callback)
        ais.detect_and_interrupt_idle_state()
        callback.assert_called_once()

    def test_export_before_any_verification(self, tmp_path):
        fw = ResultsVerificationFramework()
        filepath = str(tmp_path / "empty.json")
        fw.export_verification_history(filepath)
        import json

        with open(filepath) as f:
            assert json.load(f) == []

    def test_success_rate_before_any_verification(self):
        fw = ResultsVerificationFramework()
        assert fw.get_verification_success_rate() == 0.0
