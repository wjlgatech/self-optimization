from src.anti_idling_system import AntiIdlingSystem


class TestAntiIdlingSystem:
    def setup_method(self):
        self.system = AntiIdlingSystem()

    def test_log_activity(self):
        activity = {"description": "test activity", "is_productive": True, "duration": 3600}
        self.system.log_activity(activity)
        assert len(self.system.activity_log) == 1
        assert self.system.activity_log[0]["description"] == "test activity"

    def test_calculate_idle_rate(self):
        # Log some activities
        self.system.log_activity(
            {"description": "productive task", "is_productive": True, "duration": 3600}
        )

        idle_rate = self.system.calculate_idle_rate()
        assert 0 <= idle_rate <= 1

    def test_intervention_callback(self):
        callback_called = False

        def mock_callback():
            nonlocal callback_called
            callback_called = True

        self.system.register_intervention_callback(mock_callback)

        # Simulate high idle rate
        self.system.idle_threshold = 0.5
        self.system.detect_and_interrupt_idle_state()

        assert callback_called

    def test_emergency_actions_generation(self):
        actions = self.system.generate_emergency_actions()
        assert len(actions) > 0
        assert all(isinstance(action, str) for action in actions)
