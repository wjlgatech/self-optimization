"""
Unit tests for ResultsVerificationFramework.

Tests each method in isolation, covering happy paths, edge cases,
and verified bug fixes.
"""

import json
import os

import pytest

from results_verification import ResultsVerificationFramework

# ── Constructor ──────────────────────────────────────────────────────────


class TestVerificationInit:
    def test_default_criteria_count(self):
        fw = ResultsVerificationFramework()
        assert len(fw.verification_criteria) == 5

    def test_default_criteria_names(self):
        fw = ResultsVerificationFramework()
        expected = {"specific", "measurable", "actionable", "reusable", "compoundable"}
        assert set(fw.verification_criteria.keys()) == expected

    def test_empty_history(self):
        fw = ResultsVerificationFramework()
        assert fw.verification_history == []

    def test_criteria_are_callable(self):
        fw = ResultsVerificationFramework()
        for func in fw.verification_criteria.values():
            assert callable(func)

    def test_default_max_history(self):
        fw = ResultsVerificationFramework()
        assert fw.max_history == 1000

    def test_custom_max_history(self):
        fw = ResultsVerificationFramework(max_history=50)
        assert fw.max_history == 50


# ── _check_specificity ───────────────────────────────────────────────────


class TestCheckSpecificity:
    def test_valid_results(self):
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"key": "value"}) is True

    def test_none_results(self):
        fw = ResultsVerificationFramework()
        assert fw._check_specificity(None) is False

    def test_empty_dict(self):
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({}) is False

    def test_zero_value_accepted(self):
        """Zero is a valid value — no longer rejected."""
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"score": 0}) is True

    def test_empty_string_accepted(self):
        """Empty string is accepted (not None)."""
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"name": ""}) is True

    def test_empty_list_accepted(self):
        """Empty list is accepted (not None)."""
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"items": []}) is True

    def test_none_value_rejected(self):
        """None values are rejected by specificity."""
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"key": None}) is False

    def test_multiple_truthy_values(self):
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"a": 1, "b": "text", "c": [1]}) is True

    def test_mixed_with_none(self):
        fw = ResultsVerificationFramework()
        assert fw._check_specificity({"a": 1, "b": None}) is False

    def test_non_dict_input(self):
        fw = ResultsVerificationFramework()
        assert fw._check_specificity("string") is False
        assert fw._check_specificity([1, 2]) is False
        assert fw._check_specificity(42) is False


# ── _check_measurability ────────────────────────────────────────────────


class TestCheckMeasurability:
    def test_all_numeric(self):
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": 1, "b": 2.5}) is True

    def test_all_strings(self):
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": "hello", "b": "world"}) is True

    def test_mixed_numeric_and_string(self):
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": 1, "b": "text"}) is True

    def test_contains_list_with_scalar(self):
        """Mixed types: has scalar, so measurable passes with any()."""
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": 1, "b": [1, 2, 3]}) is True

    def test_only_list(self):
        """All complex: no scalar, measurable fails."""
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": [1, 2, 3]}) is False

    def test_only_dict(self):
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": {"nested": True}}) is False

    def test_contains_bool(self):
        """bool is subclass of int, so isinstance(True, int) is True."""
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"flag": True}) is True

    def test_contains_none(self):
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({"a": None}) is False

    def test_empty_dict_returns_false(self):
        """Empty dict now returns False (guard added)."""
        fw = ResultsVerificationFramework()
        assert fw._check_measurability({}) is False


# ── _check_actionability ────────────────────────────────────────────────


class TestCheckActionability:
    def test_with_next_step(self):
        fw = ResultsVerificationFramework()
        assert fw._check_actionability({"next_step": "do something"}) is True

    def test_with_recommendation(self):
        fw = ResultsVerificationFramework()
        assert fw._check_actionability({"recommendation": "do this"}) is True

    def test_with_both_keys(self):
        fw = ResultsVerificationFramework()
        assert fw._check_actionability({"next_step": "x", "recommendation": "y"}) is True

    def test_without_action_keys(self):
        fw = ResultsVerificationFramework()
        assert fw._check_actionability({"data": "value"}) is False

    def test_empty_dict(self):
        fw = ResultsVerificationFramework()
        assert fw._check_actionability({}) is False


# ── _check_reusability ──────────────────────────────────────────────────


class TestCheckReusability:
    def test_multiple_keys(self):
        fw = ResultsVerificationFramework()
        assert fw._check_reusability({"a": 1, "b": 2}) is True

    def test_single_key(self):
        fw = ResultsVerificationFramework()
        assert fw._check_reusability({"a": 1}) is False

    def test_empty_dict(self):
        fw = ResultsVerificationFramework()
        assert fw._check_reusability({}) is False

    def test_exactly_two_keys(self):
        fw = ResultsVerificationFramework()
        assert fw._check_reusability({"a": 1, "b": 2}) is True


# ── _check_compoundability ──────────────────────────────────────────────


class TestCheckCompoundability:
    def test_with_list_value(self):
        fw = ResultsVerificationFramework()
        assert fw._check_compoundability({"items": [1, 2]}) is True

    def test_with_dict_value(self):
        fw = ResultsVerificationFramework()
        assert fw._check_compoundability({"nested": {"a": 1}}) is True

    def test_only_scalars(self):
        fw = ResultsVerificationFramework()
        assert fw._check_compoundability({"a": 1, "b": "text"}) is False

    def test_empty_dict(self):
        """any() on empty iterable returns False."""
        fw = ResultsVerificationFramework()
        assert fw._check_compoundability({}) is False

    def test_mixed_types_can_satisfy_both_measurable_and_compoundable(self):
        """With any() for measurability, mixed-type dicts can pass both."""
        fw = ResultsVerificationFramework()
        mixed = {"a": 1, "b": [1, 2]}
        assert fw._check_measurability(mixed) is True  # any scalar → True
        assert fw._check_compoundability(mixed) is True  # has list → True


# ── verify_results ──────────────────────────────────────────────────────


class TestVerifyResults:
    def test_basic_verification(self):
        fw = ResultsVerificationFramework()
        results = {"next_step": "do something", "score": 95, "items": [1, 2]}
        verification = fw.verify_results(results)
        assert isinstance(verification, dict)
        assert set(verification.keys()) == set(fw.verification_criteria.keys())

    def test_actionability_works_correctly(self):
        """Actionable returns True when next_step or recommendation is present."""
        fw = ResultsVerificationFramework()
        results = {"next_step": "act", "recommendation": "do", "items": [1]}
        verification = fw.verify_results(results)
        assert verification["actionable"] is True

    def test_overall_valid_can_be_true(self):
        """With all bugs fixed, overall_valid=True is now achievable."""
        fw = ResultsVerificationFramework()
        results = {
            "next_step": "deploy",
            "score": 95,
            "items": [1, 2, 3],
        }
        fw.verify_results(results)
        assert fw.verification_history[0]["overall_valid"] is True

    def test_history_recorded(self):
        fw = ResultsVerificationFramework()
        fw.verify_results({"a": 1, "b": 2})
        assert len(fw.verification_history) == 1
        entry = fw.verification_history[0]
        assert "timestamp" in entry
        assert "results" in entry
        assert "verification_results" in entry
        assert "overall_valid" in entry

    def test_overall_valid_requires_all_pass(self):
        fw = ResultsVerificationFramework()
        fw.verify_results({"a": 1, "b": 2})
        entry = fw.verification_history[0]
        expected = all(entry["verification_results"].values())
        assert entry["overall_valid"] == expected

    def test_custom_criterion_exception_handled(self):
        fw = ResultsVerificationFramework()

        def bad_check(results):
            raise ValueError("intentional")

        fw.add_custom_verification_criterion("bad", bad_check)
        verification = fw.verify_results({"a": 1})
        assert verification["bad"] is False

    def test_empty_results(self):
        fw = ResultsVerificationFramework()
        verification = fw.verify_results({})
        assert verification["specific"] is False
        assert verification["reusable"] is False

    def test_multiple_verifications_accumulate_history(self):
        fw = ResultsVerificationFramework()
        for i in range(5):
            fw.verify_results({"key": f"value_{i}", "other": i + 1})
        assert len(fw.verification_history) == 5

    def test_rejects_non_dict(self):
        fw = ResultsVerificationFramework()
        with pytest.raises(TypeError):
            fw.verify_results(None)
        with pytest.raises(TypeError):
            fw.verify_results([1, 2, 3])
        with pytest.raises(TypeError):
            fw.verify_results("string")


# ── add_custom_verification_criterion ────────────────────────────────────


class TestCustomCriteria:
    def test_add_custom_criterion(self):
        fw = ResultsVerificationFramework()
        fw.add_custom_verification_criterion("custom", lambda r: True)
        assert "custom" in fw.verification_criteria

    def test_custom_criterion_used_in_verify(self):
        fw = ResultsVerificationFramework()
        fw.add_custom_verification_criterion("always_true", lambda r: True)
        result = fw.verify_results({"a": 1, "b": 2})
        assert result["always_true"] is True

    def test_overwrite_existing_criterion(self):
        """Adding a criterion with existing name silently overwrites."""
        fw = ResultsVerificationFramework()
        fw.add_custom_verification_criterion("specific", lambda r: True)
        result = fw.verify_results({})  # normally fails specificity
        assert result["specific"] is True  # overwritten to always-true

    def test_non_callable_criterion_rejected(self):
        """Non-callable is now rejected with TypeError."""
        fw = ResultsVerificationFramework()
        with pytest.raises(TypeError):
            fw.add_custom_verification_criterion("bad", "not a function")

    def test_empty_name_rejected(self):
        """Empty name is rejected with ValueError."""
        fw = ResultsVerificationFramework()
        with pytest.raises(ValueError):
            fw.add_custom_verification_criterion("", lambda r: True)


# ── export_verification_history ──────────────────────────────────────────


class TestExportHistory:
    def test_export_creates_file(self, tmp_path):
        fw = ResultsVerificationFramework()
        fw.verify_results({"a": 1, "b": 2})
        filepath = str(tmp_path / "history.json")
        fw.export_verification_history(filepath)
        assert os.path.exists(filepath)

    def test_export_valid_json(self, tmp_path):
        fw = ResultsVerificationFramework()
        fw.verify_results({"a": 1, "b": 2})
        filepath = str(tmp_path / "history.json")
        fw.export_verification_history(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_export_empty_history(self, tmp_path):
        fw = ResultsVerificationFramework()
        filepath = str(tmp_path / "history.json")
        fw.export_verification_history(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert data == []

    def test_export_default_filename_writes_to_cwd(self):
        fw = ResultsVerificationFramework()
        import inspect

        sig = inspect.signature(fw.export_verification_history)
        assert sig.parameters["filename"].default == "verification_history.json"


# ── get_verification_success_rate ────────────────────────────────────────


class TestSuccessRate:
    def test_no_history(self):
        fw = ResultsVerificationFramework()
        assert fw.get_verification_success_rate() == 0.0

    def test_all_pass_with_good_results(self):
        """With bugs fixed, good results can now pass all criteria."""
        fw = ResultsVerificationFramework()
        for _ in range(3):
            fw.verify_results(
                {
                    "next_step": "deploy",
                    "score": 95,
                    "items": [1, 2, 3],
                }
            )
        assert fw.get_verification_success_rate() == 100.0

    def test_with_manually_valid_history(self):
        """Test rate calculation by injecting valid history entries."""
        fw = ResultsVerificationFramework()
        fw.verification_history = [
            {"overall_valid": True},
            {"overall_valid": True},
            {"overall_valid": False},
        ]
        assert fw.get_verification_success_rate() == pytest.approx(66.666, abs=0.01)

    def test_all_valid(self):
        fw = ResultsVerificationFramework()
        fw.verification_history = [{"overall_valid": True}] * 5
        assert fw.get_verification_success_rate() == 100.0

    def test_returns_percentage_not_fraction(self):
        fw = ResultsVerificationFramework()
        fw.verification_history = [{"overall_valid": True}]
        rate = fw.get_verification_success_rate()
        assert rate == 100.0  # percentage, not 1.0
