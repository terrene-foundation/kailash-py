"""
Unit tests for Intelligent Optimizer - Phase 3B

Test Coverage:
1. Bayesian hyperparameter optimization
2. Genetic algorithm optimization
3. Reinforcement learning optimization
4. Multi-objective optimization

CRITICAL: Write tests FIRST, then implement!
"""


class TestBayesianOptimization:
    """Test Bayesian hyperparameter optimization."""

    def test_create_bayesian_optimizer(self):
        """Test creating Bayesian optimizer."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="bayesian")

        assert optimizer.strategy == "bayesian"

    def test_bayesian_optimize_parameters(self):
        """Test Bayesian optimization of parameters."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="bayesian")

        result = optimizer.optimize(
            feature_id="test-feature",
            parameter_space={"learning_rate": (0.001, 0.1), "batch_size": (16, 128)},
            n_iterations=5,
        )

        assert "best_params" in result
        assert "improvement" in result

    def test_bayesian_uses_acquisition_function(self):
        """Test Bayesian optimizer uses acquisition function."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="bayesian", acquisition="ei")

        assert optimizer.acquisition_function == "ei"


class TestGeneticOptimization:
    """Test genetic algorithm optimization."""

    def test_create_genetic_optimizer(self):
        """Test creating genetic optimizer."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="genetic")

        assert optimizer.strategy == "genetic"

    def test_genetic_evolution(self):
        """Test genetic algorithm evolution."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="genetic", population_size=10)

        result = optimizer.optimize(
            feature_id="test-feature",
            parameter_space={"param1": (0, 100)},
            n_generations=5,
        )

        assert "best_genome" in result
        assert "fitness" in result

    def test_genetic_crossover_and_mutation(self):
        """Test genetic crossover and mutation."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(
            strategy="genetic", crossover_rate=0.8, mutation_rate=0.1
        )

        assert optimizer.crossover_rate == 0.8
        assert optimizer.mutation_rate == 0.1


class TestReinforcementLearningOptimization:
    """Test reinforcement learning optimization."""

    def test_create_rl_optimizer(self):
        """Test creating RL optimizer."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="reinforcement_learning")

        assert optimizer.strategy == "reinforcement_learning"

    def test_rl_policy_learning(self):
        """Test RL policy learning."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="reinforcement_learning")

        # Train policy
        for i in range(10):
            action = optimizer.select_action(state={"step": i})
            optimizer.update_policy(action, reward=0.8)

        policy = optimizer.get_policy()
        assert policy is not None

    def test_rl_exploration_exploitation(self):
        """Test RL exploration vs exploitation."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(strategy="reinforcement_learning", epsilon=0.1)

        actions = [optimizer.select_action(state={}) for _ in range(100)]
        assert len(set(actions)) > 1  # Should explore different actions


class TestMultiObjectiveOptimization:
    """Test multi-objective optimization."""

    def test_create_multi_objective_optimizer(self):
        """Test creating multi-objective optimizer."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(
            strategy="multi_objective", objectives=["accuracy", "speed", "cost"]
        )

        assert len(optimizer.objectives) == 3

    def test_pareto_frontier_calculation(self):
        """Test Pareto frontier calculation."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(
            strategy="multi_objective", objectives=["accuracy", "speed"]
        )

        result = optimizer.optimize(
            feature_id="test-feature",
            parameter_space={"param": (0, 10)},
            n_iterations=5,
        )

        assert "pareto_frontier" in result
        assert len(result["pareto_frontier"]) > 0

    def test_objective_weighting(self):
        """Test weighted multi-objective optimization."""
        from kaizen.research import IntelligentOptimizer

        optimizer = IntelligentOptimizer(
            strategy="multi_objective",
            objectives=["accuracy", "speed"],
            weights=[0.7, 0.3],
        )

        assert optimizer.weights == [0.7, 0.3]
