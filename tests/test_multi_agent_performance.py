from multi_agent_performance import MultiAgentPerformanceOptimizer


class TestMultiAgentPerformanceOptimizer:
    def setup_method(self):
        self.optimizer = MultiAgentPerformanceOptimizer()

    def test_agent_registration(self):
        agent_details = {
            "name": "Test Agent",
            "capabilities": ["data_analysis", "machine_learning"],
        }
        agent_id = self.optimizer.register_agent(agent_details)

        assert agent_id in self.optimizer.agents
        assert self.optimizer.agents[agent_id]["name"] == "Test Agent"

    def test_update_agent_performance(self):
        # Register an agent
        agent_details = {"name": "Performance Agent", "capabilities": ["optimization"]}
        agent_id = self.optimizer.register_agent(agent_details)

        # Update performance
        performance_data = {"accuracy": 0.95, "efficiency": 0.90, "adaptability": 0.85}

        self.optimizer.update_agent_performance(agent_id, performance_data)

        # Check performance update
        updated_agent = self.optimizer.agents[agent_id]
        assert "performance_score" in updated_agent
        assert updated_agent["performance_score"] > 0

    def test_optimization_strategy_registration(self):
        def mock_optimization_strategy(agent):
            agent["optimized"] = True

        # Register optimization strategy
        self.optimizer.register_optimization_strategy(mock_optimization_strategy)

        # Trigger with low-performing agent
        agent_details = {"name": "Low Performer", "capabilities": ["basic_tasks"]}
        agent_id = self.optimizer.register_agent(agent_details)

        # Force low performance
        performance_data = {"accuracy": 0.3, "efficiency": 0.2, "adaptability": 0.1}

        self.optimizer.update_agent_performance(agent_id, performance_data)

        # Check if optimization strategy was applied
        updated_agent = self.optimizer.agents[agent_id]
        assert updated_agent.get("optimized", False)

    def test_top_performing_agents(self):
        # Register multiple agents with different performances
        agents = [
            {"name": "Agent A", "capabilities": ["high_performance"]},
            {"name": "Agent B", "capabilities": ["medium_performance"]},
            {"name": "Agent C", "capabilities": ["low_performance"]},
        ]

        performance_data = [
            {"accuracy": 0.95, "efficiency": 0.90, "adaptability": 0.85},
            {"accuracy": 0.75, "efficiency": 0.70, "adaptability": 0.65},
            {"accuracy": 0.45, "efficiency": 0.40, "adaptability": 0.35},
        ]

        for agent_details, perf_data in zip(agents, performance_data, strict=True):
            agent_id = self.optimizer.register_agent(agent_details)
            self.optimizer.update_agent_performance(agent_id, perf_data)

        # Get top performers
        top_agents = self.optimizer.get_top_performing_agents(2)

        assert len(top_agents) == 2
        assert top_agents[0]["name"] == "Agent A"
        assert top_agents[1]["name"] == "Agent B"

    def test_performance_report_generation(self):
        # Populate with some agents
        agents = [
            {"name": "Agent X", "capabilities": ["complex_task"]},
            {"name": "Agent Y", "capabilities": ["simple_task"]},
        ]

        performance_data = [
            {"accuracy": 0.85, "efficiency": 0.80, "adaptability": 0.75},
            {"accuracy": 0.55, "efficiency": 0.50, "adaptability": 0.45},
        ]

        for agent_details, perf_data in zip(agents, performance_data, strict=True):
            agent_id = self.optimizer.register_agent(agent_details)
            self.optimizer.update_agent_performance(agent_id, perf_data)

        # Generate performance report
        report = self.optimizer.generate_performance_report()

        assert "total_agents" in report
        assert "average_performance" in report
        assert "top_performers" in report
        assert "performance_trends" in report
