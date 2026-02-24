"""
Unit tests for AntiIdlingSystem.

Tests each method in isolation, covering happy paths, edge cases,
and verified bug fixes.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from anti_idling_system import AntiIdlingSystem

# ── Constructor ──────────────────────────────────────────────────────────


class TestAntiIdlingInit:
    def test_default_parameters(self):
        system = AntiIdlingSystem()
        assert system.idle_threshold == 0.10
        assert system.minimum_productive_actions == 10
        assert system.activity_log == []
        assert system.intervention_callbacks == []

    def test_custom_parameters(self):
        system = AntiIdlingSystem(idle_threshold=0.5, minimum_productive_actions=5)
        assert system.idle_threshold == 0.5
        assert system.minimum_productive_actions == 5

    def test_zero_threshold(self):
        system = AntiIdlingSystem(idle_threshold=0.0)
        assert system.idle_threshold == 0.0

    def test_threshold_above_one_rejected(self):
        """Threshold > 1.0 raises ValueError."""
        with pytest.raises(ValueError):
            AntiIdlingSystem(idle_threshold=2.0)

    def test_negative_threshold_rejected(self):
        """Negative threshold raises ValueError."""
        with pytest.raises(ValueError):
            AntiIdlingSystem(idle_threshold=-0.5)

    def test_negative_minimum_actions_rejected(self):
        """Negative minimum actions raises ValueError."""
        with pytest.raises(ValueError):
            AntiIdlingSystem(minimum_productive_actions=-1)

    def test_has_running_flag(self):
        system = AntiIdlingSystem()
        assert hasattr(system, "_running")
        assert system._running is False


# ── log_activity ─────────────────────────────────────────────────────────


class TestLogActivity:
    def test_basic_logging(self):
        system = AntiIdlingSystem()
        activity = {"type": "coding", "duration": 60, "is_productive": True}
        system.log_activity(activity)
        assert len(system.activity_log) == 1
        assert "timestamp" in system.activity_log[0]

    def test_timestamp_is_injected(self):
        system = AntiIdlingSystem()
        activity = {"type": "coding"}
        system.log_activity(activity)
        assert isinstance(system.activity_log[0]["timestamp"], float)

    def test_does_not_mutate_input_dict(self):
        """log_activity no longer mutates the caller's dict."""
        system = AntiIdlingSystem()
        activity = {"type": "coding"}
        system.log_activity(activity)
        assert "timestamp" not in activity

    def test_overwrites_existing_timestamp(self):
        """Caller-provided timestamp is overwritten in the copy."""
        system = AntiIdlingSystem()
        activity = {"type": "coding", "timestamp": 999999.0}
        system.log_activity(activity)
        assert system.activity_log[0]["timestamp"] != 999999.0
        # Original dict unchanged
        assert activity["timestamp"] == 999999.0

    def test_log_pruning_at_101(self):
        system = AntiIdlingSystem()
        for i in range(101):
            system.log_activity({"type": f"action_{i}", "duration": 1, "is_productive": True})
        assert len(system.activity_log) == 100

    def test_log_pruning_keeps_newest(self):
        system = AntiIdlingSystem()
        for i in range(105):
            system.log_activity({"type": f"action_{i}", "duration": 1, "is_productive": True})
        assert len(system.activity_log) == 100
        assert system.activity_log[0]["type"] == "action_5"
        assert system.activity_log[-1]["type"] == "action_104"

    def test_empty_activity_dict(self):
        system = AntiIdlingSystem()
        system.log_activity({})
        assert len(system.activity_log) == 1
        assert "timestamp" in system.activity_log[0]

    def test_activity_without_required_fields(self):
        """No duration or is_productive — accepted silently, affects idle calc."""
        system = AntiIdlingSystem()
        system.log_activity({"random_key": "random_value"})
        assert len(system.activity_log) == 1

    def test_rejects_non_dict(self):
        """log_activity rejects non-dict input."""
        system = AntiIdlingSystem()
        with pytest.raises(TypeError):
            system.log_activity("not a dict")
        with pytest.raises(TypeError):
            system.log_activity(None)
        with pytest.raises(TypeError):
            system.log_activity([1, 2, 3])


# ── calculate_idle_rate ──────────────────────────────────────────────────


class TestCalculateIdleRate:
    def test_empty_log_returns_full_idle(self):
        """With no activities, idle rate should be 1.0 (100% idle)."""
        system = AntiIdlingSystem()
        assert system.calculate_idle_rate() == 1.0

    def test_all_productive_time_covered(self):
        """If productive_time == time_window, idle rate should be 0.0."""
        system = AntiIdlingSystem()
        system.log_activity({"duration": 86400, "is_productive": True})
        rate = system.calculate_idle_rate(time_window=86400)
        assert rate == pytest.approx(0.0)

    def test_half_productive(self):
        system = AntiIdlingSystem()
        system.log_activity({"duration": 43200, "is_productive": True})
        rate = system.calculate_idle_rate(time_window=86400)
        assert rate == pytest.approx(0.5)

    def test_idle_rate_clamped_at_zero(self):
        """Idle rate is clamped to 0.0 when productive_time > time_window."""
        system = AntiIdlingSystem()
        system.log_activity({"duration": 200, "is_productive": True})
        rate = system.calculate_idle_rate(time_window=100)
        assert rate == 0.0

    def test_non_productive_activities_ignored(self):
        system = AntiIdlingSystem()
        system.log_activity({"duration": 100, "is_productive": False})
        rate = system.calculate_idle_rate(time_window=86400)
        assert rate == pytest.approx(1.0)

    def test_missing_duration_defaults_to_zero(self):
        system = AntiIdlingSystem()
        system.log_activity({"is_productive": True})
        rate = system.calculate_idle_rate(time_window=86400)
        assert rate == pytest.approx(1.0)

    def test_missing_is_productive_defaults_to_false(self):
        system = AntiIdlingSystem()
        system.log_activity({"duration": 100})
        rate = system.calculate_idle_rate(time_window=86400)
        assert rate == pytest.approx(1.0)

    def test_custom_time_window(self):
        system = AntiIdlingSystem()
        system.log_activity({"duration": 1800, "is_productive": True})
        rate = system.calculate_idle_rate(time_window=3600)
        assert rate == pytest.approx(0.5)

    def test_old_activities_excluded(self):
        """Activities outside the time window should be excluded."""
        system = AntiIdlingSystem()
        old_activity = {"duration": 86400, "is_productive": True}
        old_activity["timestamp"] = time.time() - 200000  # way in the past
        system.activity_log.append(old_activity)
        rate = system.calculate_idle_rate(time_window=86400)
        assert rate == pytest.approx(1.0)

    def test_zero_time_window_raises_valueerror(self):
        """time_window=0 raises ValueError."""
        system = AntiIdlingSystem()
        with pytest.raises(ValueError):
            system.calculate_idle_rate(time_window=0)

    def test_negative_time_window_raises_valueerror(self):
        """Negative time_window raises ValueError."""
        system = AntiIdlingSystem()
        with pytest.raises(ValueError):
            system.calculate_idle_rate(time_window=-1)


# ── register_intervention_callback ───────────────────────────────────────


class TestRegisterCallback:
    def test_register_single_callback(self):
        system = AntiIdlingSystem()

        def cb():
            return None

        system.register_intervention_callback(cb)
        assert len(system.intervention_callbacks) == 1
        assert system.intervention_callbacks[0] is cb

    def test_register_multiple_callbacks(self):
        system = AntiIdlingSystem()

        def cb1():
            return None

        def cb2():
            return None

        system.register_intervention_callback(cb1)
        system.register_intervention_callback(cb2)
        assert len(system.intervention_callbacks) == 2

    def test_register_duplicate_callback(self):
        """No deduplication — same callback registered twice."""
        system = AntiIdlingSystem()

        def cb():
            return None

        system.register_intervention_callback(cb)
        system.register_intervention_callback(cb)
        assert len(system.intervention_callbacks) == 2

    def test_register_non_callable_rejected(self):
        """Non-callable is rejected with TypeError."""
        system = AntiIdlingSystem()
        with pytest.raises(TypeError):
            system.register_intervention_callback("not a function")


# ── detect_and_interrupt_idle_state ──────────────────────────────────────


class TestDetectAndInterrupt:
    def test_no_intervention_when_below_threshold(self):
        system = AntiIdlingSystem(idle_threshold=0.99)
        callback = MagicMock()
        system.register_intervention_callback(callback)
        # Even with no activities (100% idle), threshold is 0.99, rate is 1.0
        # 1.0 > 0.99, so callback IS called
        system.detect_and_interrupt_idle_state()
        callback.assert_called_once()

    def test_intervention_triggered_when_idle(self):
        system = AntiIdlingSystem(idle_threshold=0.5)
        callback = MagicMock()
        system.register_intervention_callback(callback)
        system.detect_and_interrupt_idle_state()  # idle_rate=1.0 > 0.5
        callback.assert_called_once()

    def test_callback_exception_handled(self):
        system = AntiIdlingSystem(idle_threshold=0.01)

        def bad_callback():
            raise RuntimeError("callback error")

        system.register_intervention_callback(bad_callback)
        # Should not raise
        system.detect_and_interrupt_idle_state()

    def test_multiple_callbacks_all_called(self):
        system = AntiIdlingSystem(idle_threshold=0.01)
        cb1 = MagicMock()
        cb2 = MagicMock()
        system.register_intervention_callback(cb1)
        system.register_intervention_callback(cb2)
        system.detect_and_interrupt_idle_state()
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_failing_callback_doesnt_block_others(self):
        system = AntiIdlingSystem(idle_threshold=0.01)
        cb1 = MagicMock(side_effect=RuntimeError("fail"))
        cb2 = MagicMock()
        system.register_intervention_callback(cb1)
        system.register_intervention_callback(cb2)
        system.detect_and_interrupt_idle_state()
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_no_callbacks_no_error(self):
        system = AntiIdlingSystem(idle_threshold=0.01)
        system.detect_and_interrupt_idle_state()  # should not raise


# ── generate_emergency_actions ───────────────────────────────────────────


class TestEmergencyActions:
    def test_returns_list(self):
        system = AntiIdlingSystem()
        actions = system.generate_emergency_actions()
        assert isinstance(actions, list)

    def test_returns_five_actions(self):
        system = AntiIdlingSystem()
        actions = system.generate_emergency_actions()
        assert len(actions) == 5

    def test_all_actions_are_strings(self):
        system = AntiIdlingSystem()
        for action in system.generate_emergency_actions():
            assert isinstance(action, str)

    def test_known_actions(self):
        system = AntiIdlingSystem()
        actions = system.generate_emergency_actions()
        expected = [
            "start_research_sprint",
            "design_experimental_prototype",
            "initiate_user_feedback_loop",
            "conduct_strategic_analysis",
            "explore_new_skill_development",
        ]
        assert actions == expected


# ── run_periodic_check / stop ────────────────────────────────────────────


class TestRunPeriodicCheck:
    def test_calls_detect_and_sleep(self):
        """Verify the loop calls detect then sleeps."""
        system = AntiIdlingSystem()
        call_count = 0

        def mock_detect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                system.stop()

        system.detect_and_interrupt_idle_state = mock_detect
        with patch("time.sleep"):
            system.run_periodic_check(interval=10)
        assert call_count == 2

    def test_stop_mechanism_exists(self):
        """run_periodic_check can be stopped gracefully via stop()."""
        system = AntiIdlingSystem()
        assert hasattr(system, "_running")
        assert hasattr(system, "stop")
        assert callable(system.stop)

    def test_stop_sets_flag(self):
        system = AntiIdlingSystem()
        system._running = True
        system.stop()
        assert system._running is False


# ── register_action_handler ──────────────────────────────────────────────


class TestRegisterActionHandler:
    def test_register_handler(self):
        system = AntiIdlingSystem()
        handler = MagicMock()
        system.register_action_handler("conduct_strategic_analysis", handler)
        assert "conduct_strategic_analysis" in system.action_handlers
        assert system.action_handlers["conduct_strategic_analysis"] is handler

    def test_register_non_callable_rejected(self):
        system = AntiIdlingSystem()
        with pytest.raises(TypeError):
            system.register_action_handler("test", "not callable")

    def test_overwrite_handler(self):
        system = AntiIdlingSystem()
        handler1 = MagicMock()
        handler2 = MagicMock()
        system.register_action_handler("action", handler1)
        system.register_action_handler("action", handler2)
        assert system.action_handlers["action"] is handler2


# ── Action handler dispatch in detect_and_interrupt_idle_state ───────────


class TestActionHandlerDispatch:
    def test_handlers_called_when_idle(self):
        """Registered action handlers are invoked when idle state triggers."""
        system = AntiIdlingSystem(idle_threshold=0.01)
        handler = MagicMock()
        # Register handler for all known actions
        for action in system.generate_emergency_actions():
            system.register_action_handler(action, handler)
        executed = system.detect_and_interrupt_idle_state()
        assert handler.call_count == len(executed)
        assert len(executed) > 0

    def test_returns_executed_action_names(self):
        """detect_and_interrupt_idle_state returns names of executed actions."""
        system = AntiIdlingSystem(idle_threshold=0.01)
        system.register_action_handler("conduct_strategic_analysis", MagicMock())
        executed = system.detect_and_interrupt_idle_state()
        assert "conduct_strategic_analysis" in executed

    def test_returns_empty_when_not_idle(self):
        """No actions executed when below idle threshold."""
        system = AntiIdlingSystem(idle_threshold=1.0)
        system.register_action_handler("conduct_strategic_analysis", MagicMock())
        executed = system.detect_and_interrupt_idle_state()
        assert executed == []

    def test_handler_exception_does_not_block_others(self):
        """A failing handler doesn't prevent other handlers from running."""
        system = AntiIdlingSystem(idle_threshold=0.01)
        failing = MagicMock(side_effect=RuntimeError("boom"))
        success = MagicMock()
        system.register_action_handler("start_research_sprint", failing)
        system.register_action_handler("conduct_strategic_analysis", success)
        executed = system.detect_and_interrupt_idle_state()
        failing.assert_called_once()
        success.assert_called_once()
        # Failed action should NOT be in executed list
        assert "start_research_sprint" not in executed
        assert "conduct_strategic_analysis" in executed

    def test_unhandled_actions_logged_not_executed(self):
        """Actions without handlers are logged but not in executed list."""
        system = AntiIdlingSystem(idle_threshold=0.01)
        # Only register one handler
        system.register_action_handler("conduct_strategic_analysis", MagicMock())
        executed = system.detect_and_interrupt_idle_state()
        # Only the handled action should appear
        assert "conduct_strategic_analysis" in executed
        # Unhandled ones should not
        for action in executed:
            assert action in system.action_handlers
