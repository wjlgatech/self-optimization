from results_verification import ResultsVerificationFramework


class TestResultsVerificationFramework:
    def setup_method(self):
        self.verifier = ResultsVerificationFramework()

    def test_verification_criteria(self):
        # Test a fully valid result
        results = {
            "project_name": "Test Project",
            "output": 42,
            "next_step": "Proceed with implementation",
            "details": {"complexity": "moderate"},
            "components": ["feature1", "feature2"],
        }

        verification_results = self.verifier.verify_results(results)

        # All criteria should pass
        assert all(verification_results.values()), f"Verification failed: {verification_results}"

    def test_custom_verification_criterion(self):
        def custom_check(results):
            return "custom_key" in results

        self.verifier.add_custom_verification_criterion("has_custom_key", custom_check)

        results = {"project_name": "Custom Test", "custom_key": True}

        verification_results = self.verifier.verify_results(results)
        assert verification_results.get("has_custom_key", False)

    def test_verification_history(self):
        results1 = {"project_name": "Project A", "output": 100, "next_step": "Proceed"}
        results2 = {"project_name": "Project B", "output": 200, "details": {"complexity": "high"}}

        self.verifier.verify_results(results1)
        self.verifier.verify_results(results2)

        assert len(self.verifier.verification_history) == 2

        # Check success rate calculation
        success_rate = self.verifier.get_verification_success_rate()
        assert 0 <= success_rate <= 100

    def test_export_verification_history(self, tmp_path):
        results = {"project_name": "Export Test", "output": 50, "next_step": "Review"}

        self.verifier.verify_results(results)

        export_file = tmp_path / "verification_history.json"
        self.verifier.export_verification_history(str(export_file))

        assert export_file.exists()
        assert export_file.stat().st_size > 0
