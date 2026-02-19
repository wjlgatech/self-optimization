from src.recursive_self_improvement import RecursiveSelfImprovementProtocol


class TestRecursiveSelfImprovementProtocol:
    def setup_method(self):
        # Initialize with custom ethical constraints
        self.protocol = RecursiveSelfImprovementProtocol(
            {
                "do_no_harm": True,
                "human_alignment": True,
                "transparency": True,
                "reversibility": True,
            }
        )

    def test_capability_map_update(self):
        new_capabilities = {
            "advanced_reasoning": {"complexity": "high", "domain": "cognitive_enhancement"},
            "ethical_decision_making": {"complexity": "medium", "domain": "governance"},
        }

        self.protocol.update_capability_map(new_capabilities)

        # Check capability registration
        for capability, details in new_capabilities.items():
            assert capability in self.protocol.capability_map
            assert "added_timestamp" in self.protocol.capability_map[capability]

    def test_learning_strategy_registration(self):
        def mock_learning_strategy(capability_map, capability_gaps):
            # Simulate learning strategy
            return [
                {
                    "type": "capability_expansion",
                    "target": "new_domain",
                    "meets_do_no_harm": True,
                    "meets_human_alignment": True,
                    "meets_transparency": True,
                    "meets_reversibility": True,
                }
            ]

        # Register learning strategy
        self.protocol.register_learning_strategy(mock_learning_strategy)

        # Generate improvement proposals
        proposals = self.protocol.generate_improvement_proposals()

        assert len(proposals) > 0
        assert all("type" in proposal for proposal in proposals)

    def test_proposal_validation(self):
        # Test proposals with different ethical constraints
        valid_proposal = {
            "meets_do_no_harm": True,
            "meets_human_alignment": True,
            "meets_transparency": True,
            "meets_reversibility": True,
        }

        invalid_proposal = {"meets_do_no_harm": False, "meets_human_alignment": False}

        # Validate proposals
        valid_result = self.protocol._validate_proposal(valid_proposal)
        invalid_result = self.protocol._validate_proposal(invalid_proposal)

        assert valid_result is True
        assert invalid_result is False

    def test_improvement_execution(self):
        # Prepare a valid improvement proposal
        improvement_proposal = {
            "type": "capability_enhancement",
            "meets_do_no_harm": True,
            "meets_human_alignment": True,
            "meets_transparency": True,
            "meets_reversibility": True,
        }

        # Execute improvement
        self.protocol.execute_improvement(improvement_proposal)

        # Check improvement history
        assert len(self.protocol.improvement_history) > 0
        latest_log = self.protocol.improvement_history[-1]
        assert latest_log["type"] == "proposal_execution"

    def test_improvement_report_generation(self):
        # Simulate some improvements
        improvements = [{"type": "capability_update"}, {"type": "performance_optimization"}]

        # Manually add improvements to history
        for improvement in improvements:
            self.protocol._log_improvement(improvement["type"], {"details": "Test improvement"})

        # Generate improvement report
        report = self.protocol.generate_improvement_report()

        # Verify report structure
        assert "total_improvements" in report
        assert "improvement_types" in report
        assert "capability_growth" in report

        # Check improvement types
        assert len(report["improvement_types"]) > 0

    def test_custom_ethical_constraints(self):
        # Create protocol with custom ethical constraints
        custom_protocol = RecursiveSelfImprovementProtocol(
            {"innovation_priority": True, "risk_tolerance": 0.7}
        )

        # Validate custom constraint handling
        assert "innovation_priority" in custom_protocol.ethical_constraints
        assert "risk_tolerance" in custom_protocol.ethical_constraints
