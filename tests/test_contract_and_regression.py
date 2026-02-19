"""
Contract tests — verify documented/expected API contracts hold.
Regression tests — verify all 10 bugs are fixed and stay fixed.
"""

import pytest

from anti_idling_system import AntiIdlingSystem
from results_verification import ResultsVerificationFramework

# ══════════════════════════════════════════════════════════════════════════
# CONTRACT TESTS — API surface guarantees
# ══════════════════════════════════════════════════════════════════════════


class TestAntiIdlingAPIContract:
    """Verify that the public API surface matches documentation."""

    def test_has_log_activity(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "log_activity", None))

    def test_has_calculate_idle_rate(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "calculate_idle_rate", None))

    def test_has_register_intervention_callback(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "register_intervention_callback", None))

    def test_has_detect_and_interrupt_idle_state(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "detect_and_interrupt_idle_state", None))

    def test_has_generate_emergency_actions(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "generate_emergency_actions", None))

    def test_has_run_periodic_check(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "run_periodic_check", None))

    def test_has_stop(self):
        ais = AntiIdlingSystem()
        assert callable(getattr(ais, "stop", None))

    def test_calculate_idle_rate_returns_float(self):
        ais = AntiIdlingSystem()
        assert isinstance(ais.calculate_idle_rate(), float)

    def test_generate_emergency_actions_returns_list_of_strings(self):
        ais = AntiIdlingSystem()
        actions = ais.generate_emergency_actions()
        assert isinstance(actions, list)
        assert all(isinstance(a, str) for a in actions)


class TestVerificationAPIContract:
    def test_has_verify_results(self):
        fw = ResultsVerificationFramework()
        assert callable(getattr(fw, "verify_results", None))

    def test_has_add_custom_verification_criterion(self):
        fw = ResultsVerificationFramework()
        assert callable(getattr(fw, "add_custom_verification_criterion", None))

    def test_has_export_verification_history(self):
        fw = ResultsVerificationFramework()
        assert callable(getattr(fw, "export_verification_history", None))

    def test_has_get_verification_success_rate(self):
        fw = ResultsVerificationFramework()
        assert callable(getattr(fw, "get_verification_success_rate", None))

    def test_verify_results_returns_dict_of_bools(self):
        fw = ResultsVerificationFramework()
        result = fw.verify_results({"a": 1, "b": 2})
        assert isinstance(result, dict)
        assert all(isinstance(v, bool) for v in result.values())

    def test_verify_results_keys_match_criteria(self):
        fw = ResultsVerificationFramework()
        result = fw.verify_results({"a": 1})
        assert set(result.keys()) == set(fw.verification_criteria.keys())

    def test_success_rate_returns_float(self):
        fw = ResultsVerificationFramework()
        assert isinstance(fw.get_verification_success_rate(), float)

    def test_success_rate_range(self):
        fw = ResultsVerificationFramework()
        fw.verification_history = [{"overall_valid": True}] * 3
        rate = fw.get_verification_success_rate()
        assert 0.0 <= rate <= 100.0


# ══════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS — Verify all 10 bugs are fixed
# ══════════════════════════════════════════════════════════════════════════


class TestRegressionBugsFixed:
    """
    Each test verifies that a specific bug is fixed.
    Assertions are written to confirm correct behavior.
    """

    def test_actionability_works_correctly(self):
        """
        BUG #1 FIXED: _check_actionability no longer raises TypeError.
        Returns True when next_step or recommendation is present.
        """
        fw = ResultsVerificationFramework()
        assert fw._check_actionability({"next_step": "test"}) is True
        assert fw._check_actionability({"recommendation": "do"}) is True
        assert fw._check_actionability({"data": "only"}) is False

    def test_idle_rate_clamped(self):
        """
        BUG #2 FIXED: calculate_idle_rate clamps to [0.0, 1.0].
        """
        ais = AntiIdlingSystem()
        ais.log_activity({"duration": 200, "is_productive": True})
        rate = ais.calculate_idle_rate(time_window=100)
        assert rate == 0.0  # clamped, not negative

    def test_zero_time_window_raises_valueerror(self):
        """
        BUG #3 FIXED: time_window=0 raises ValueError, not ZeroDivisionError.
        """
        ais = AntiIdlingSystem()
        with pytest.raises(ValueError):
            ais.calculate_idle_rate(time_window=0)

    def test_log_activity_does_not_mutate_input(self):
        """
        BUG #4 FIXED: log_activity no longer mutates the caller's dictionary.
        """
        ais = AntiIdlingSystem()
        original = {"type": "test"}
        ais.log_activity(original)
        assert "timestamp" not in original  # not mutated

    def test_input_validation_on_threshold(self):
        """
        BUG #5 FIXED: Invalid idle_threshold raises ValueError.
        """
        with pytest.raises(ValueError):
            AntiIdlingSystem(idle_threshold=5.0)
        with pytest.raises(ValueError):
            AntiIdlingSystem(idle_threshold=-0.1)
        with pytest.raises(ValueError):
            AntiIdlingSystem(minimum_productive_actions=-1)

    def test_specificity_accepts_zero_values(self):
        """
        BUG #6 FIXED: _check_specificity accepts zero, empty string, empty list.
        Only None values are rejected.
        """
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"score": 0, "name": "test"}) is True
        assert fw._check_specificity({"value": ""}) is True
        assert fw._check_specificity({"items": []}) is True
        assert fw._check_specificity({"key": None}) is False

    def test_measurability_rejects_empty_dict(self):
        """
        BUG #7 FIXED: _check_measurability returns False for empty dict.
        """
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({}) is False

    def test_measurable_and_compoundable_compatible(self):
        """
        BUG #8 FIXED: measurable uses any() so mixed-type dicts
        can pass both measurable and compoundable criteria.
        """
        fw = ResultsVerificationFramework()
        result = {
            "next_step": "deploy",
            "score": 95,
            "items": [1, 2, 3],
        }
        v = fw.verify_results(result)
        assert v["measurable"] is True  # has scalar values
        assert v["compoundable"] is True  # has list value
        assert fw.verification_history[-1]["overall_valid"] is True  # all 5 criteria pass

    def test_graceful_stop_for_periodic_check(self):
        """
        BUG #9 FIXED: run_periodic_check has a stop mechanism.
        """
        ais = AntiIdlingSystem()
        assert hasattr(ais, "_running")
        assert hasattr(ais, "stop")
        assert ais._running is False

    def test_verification_history_bounded(self):
        """
        BUG #10 FIXED: verification_history is FIFO-pruned at max_history.
        """
        fw = ResultsVerificationFramework(max_history=100)
        for i in range(200):
            fw.verify_results({f"k{i}": i, "b": 1})
        assert len(fw.verification_history) == 100
