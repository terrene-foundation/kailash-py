"""
Comprehensive tests for Chain-of-Thought Reasoning Agent

Tests cover:
1. Signature functionality and validation
2. Agent initialization and performance
3. Reasoning quality and structure
4. Enterprise features (audit trails, monitoring)
5. Performance targets validation
6. Error handling and edge cases
"""

import logging
import time

import pytest
from chain_of_thought_agent import (
    ChainOfThoughtAgent,
    ChainOfThoughtSignature,
    CoTConfig,
)

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestChainOfThoughtSignature:
    """Test ChainOfThoughtSignature functionality."""

    def test_signature_initialization(self):
        """Test that ChainOfThoughtSignature initializes correctly."""
        signature = ChainOfThoughtSignature(
            name="test_cot_signature", description="Test signature for CoT reasoning"
        )

        assert signature.name == "test_cot_signature"
        assert "Test signature for CoT reasoning" in signature.description

    def test_signature_inputs_definition(self):
        """Test that signature defines correct input fields."""
        signature = ChainOfThoughtSignature()
        inputs = signature.define_inputs()

        # Verify required inputs
        assert "problem" in inputs
        assert "context" in inputs

        # Verify input specifications
        assert inputs["problem"]["type"] == str
        assert inputs["problem"]["required"] == True
        assert inputs["context"]["type"] == str
        assert inputs["context"]["default"] == ""

    def test_signature_outputs_definition(self):
        """Test that signature defines correct output fields."""
        signature = ChainOfThoughtSignature()
        outputs = signature.define_outputs()

        # Verify all reasoning steps
        expected_steps = ["step1", "step2", "step3", "step4", "step5"]
        for step in expected_steps:
            assert step in outputs
            assert outputs[step]["type"] == str

        # Verify final output fields
        assert "final_answer" in outputs
        assert "confidence" in outputs
        assert outputs["final_answer"]["type"] == str
        assert outputs["confidence"]["type"] == float

    def test_signature_step_descriptions(self):
        """Test that each step has meaningful descriptions."""
        signature = ChainOfThoughtSignature()
        outputs = signature.define_outputs()

        step_descriptions = [
            "Problem understanding",
            "Data identification",
            "Systematic calculation",
            "Solution verification",
            "Final answer formulation",
        ]

        for i, expected_desc in enumerate(step_descriptions, 1):
            step_key = f"step{i}"
            assert step_key in outputs
            description = outputs[step_key]["description"]
            assert any(
                keyword in description.lower()
                for keyword in expected_desc.lower().split()
            )


class TestChainOfThoughtAgent:
    """Test ChainOfThoughtAgent functionality and performance."""

    @pytest.fixture
    def agent_config(self):
        """Provide test configuration for agent."""
        return CoTConfig(
            llm_provider="mock",  # Use mock provider for unit tests
            model="gpt-4",
            temperature=0.1,
            max_tokens=1500,
            reasoning_steps=5,
            enable_verification=True,
        )

    @pytest.fixture
    def agent(self, agent_config):
        """Create agent instance for testing."""
        agent = ChainOfThoughtAgent(agent_config)
        yield agent
        agent.cleanup()

    def test_agent_initialization_performance(self, agent_config):
        """Test that agent initialization meets performance targets."""
        start_time = time.time()

        agent = ChainOfThoughtAgent(agent_config)

        try:
            initialization_time = (time.time() - start_time) * 1000

            # Validate performance targets
            metrics = agent.get_performance_metrics()
            assert (
                metrics["framework_init_time"] < 100
            ), f"Framework init took {metrics['framework_init_time']:.1f}ms (target: <100ms)"
            assert (
                metrics["agent_creation_time"] < 200
            ), f"Agent creation took {metrics['agent_creation_time']:.1f}ms (target: <200ms)"

            # Validate total initialization is reasonable
            assert (
                initialization_time < 300
            ), f"Total initialization took {initialization_time:.1f}ms (target: <300ms)"

            logger.info(
                f"Performance test passed - Framework: {metrics['framework_init_time']:.1f}ms, Agent: {metrics['agent_creation_time']:.1f}ms"
            )

        finally:
            agent.cleanup()

    def test_agent_components_initialization(self, agent):
        """Test that all agent components are properly initialized."""
        assert agent.kaizen_framework is not None
        assert agent.agent is not None
        assert agent.config is not None
        assert agent.performance_metrics is not None

        # Validate framework configuration
        framework_config = agent.kaizen_framework.config
        assert framework_config["signature_programming_enabled"] == True
        assert framework_config["optimization_enabled"] == True
        assert framework_config["monitoring_enabled"] == True
        assert framework_config["audit_trail_enabled"] == True

    def test_mathematical_reasoning_train_problem(self, agent):
        """Test mathematical reasoning with train speed/distance problem."""
        problem = (
            "If a train travels 60 mph for 3 hours, then speeds up to 80 mph for 2 more hours, "
            "what total distance did it travel?"
        )

        result = agent.solve_problem(problem)

        # Validate result structure
        assert "final_answer" in result
        assert "confidence" in result
        assert "execution_time_ms" in result
        assert "success" in result

        # Validate mathematical correctness
        assert "340" in result["final_answer"]  # 60*3 + 80*2 = 180 + 160 = 340
        assert result["confidence"] > 0.9  # High confidence for mathematical problem
        assert result["success"] == True

        # Validate reasoning steps
        for i in range(1, 6):
            step_key = f"step{i}"
            assert step_key in result
            assert len(result[step_key]) > 10  # Meaningful step content

        # Validate execution performance
        assert (
            result["execution_time_ms"] < 1000
        ), f"Execution took {result['execution_time_ms']:.1f}ms (target: <1000ms)"

        logger.info(
            f"Mathematical reasoning test passed - Answer: {result['final_answer']}, Confidence: {result['confidence']:.2f}"
        )

    def test_general_problem_reasoning(self, agent):
        """Test reasoning with a general problem."""
        problem = "What are the key factors to consider when choosing a programming language for a new project?"

        result = agent.solve_problem(problem)

        # Validate result structure
        assert "final_answer" in result
        assert "confidence" in result
        assert "success" in result
        assert result["success"] == True

        # Validate reasoning steps exist
        for i in range(1, 6):
            step_key = f"step{i}"
            assert step_key in result
            assert isinstance(result[step_key], str)

        # Validate confidence is reasonable for general question
        assert 0.5 <= result["confidence"] <= 1.0

        logger.info(
            f"General reasoning test passed - Confidence: {result['confidence']:.2f}"
        )

    def test_reasoning_with_context(self, agent):
        """Test reasoning with additional context."""
        problem = "Calculate the area of a rectangle"
        context = "The rectangle has a length of 10 meters and a width of 5 meters"

        result = agent.solve_problem(problem, context)

        assert "final_answer" in result
        assert result["success"] == True

        # For mathematical problems with context, should have high confidence
        assert result["confidence"] > 0.6

    def test_error_handling(self, agent):
        """Test error handling with problematic inputs."""
        # Test with empty problem
        result = agent.solve_problem("")
        assert "final_answer" in result
        # Should handle gracefully even with empty input

        # Test with very long problem
        long_problem = "x" * 10000
        result = agent.solve_problem(long_problem)
        assert "final_answer" in result

    def test_performance_metrics_tracking(self, agent):
        """Test that performance metrics are properly tracked."""
        # Execute multiple problems to test metrics
        problems = [
            "What is 2 + 2?",
            "Explain photosynthesis in simple terms",
            "Calculate the circumference of a circle with radius 5",
        ]

        for problem in problems:
            agent.solve_problem(problem)

        metrics = agent.get_performance_metrics()

        # Validate metrics structure
        assert "total_executions" in metrics
        assert "successful_executions" in metrics
        assert "average_execution_time" in metrics
        assert "framework_init_time" in metrics
        assert "agent_creation_time" in metrics

        # Validate metrics values
        assert metrics["total_executions"] == len(problems)
        assert metrics["successful_executions"] <= metrics["total_executions"]
        assert metrics["average_execution_time"] > 0

        # Validate performance targets
        assert metrics["framework_target_met"] == True
        assert metrics["agent_target_met"] == True

        logger.info(
            f"Performance metrics test passed - {metrics['total_executions']} executions, {metrics['success_rate']:.1%} success rate"
        )


class TestEnterpriseFeatures:
    """Test enterprise features like audit trails and monitoring."""

    @pytest.fixture
    def agent(self):
        """Create agent with enterprise features enabled."""
        config = CoTConfig(enable_verification=True)
        agent = ChainOfThoughtAgent(config)
        yield agent
        agent.cleanup()

    def test_audit_trail_functionality(self, agent):
        """Test that audit trail captures reasoning activities."""
        problem = "Test problem for audit trail"

        # Execute reasoning
        result = agent.solve_problem(problem)

        # Get audit trail
        audit_trail = agent.get_audit_trail()

        assert len(audit_trail) > 0

        # Find chain-of-thought entries
        cot_entries = [
            entry
            for entry in audit_trail
            if entry.get("action") == "chain_of_thought_reasoning"
        ]
        assert len(cot_entries) > 0

        latest_entry = cot_entries[-1]
        assert "problem" in latest_entry
        assert "execution_time_ms" in latest_entry
        assert "success" in latest_entry
        assert "confidence" in latest_entry
        assert "timestamp" in latest_entry

        logger.info(
            f"Audit trail test passed - {len(audit_trail)} total entries, {len(cot_entries)} CoT entries"
        )

    def test_monitoring_metrics(self, agent):
        """Test monitoring and metrics collection."""
        # Execute several problems
        problems = ["Simple math: 5 + 5", "Complex problem: optimization strategies"]

        for problem in problems:
            agent.solve_problem(problem)

        metrics = agent.get_performance_metrics()

        # Validate comprehensive metrics
        assert metrics["total_executions"] == len(problems)
        assert 0 <= metrics["success_rate"] <= 1.0
        assert metrics["average_execution_time"] > 0

        # Validate performance target tracking
        assert isinstance(metrics["framework_target_met"], bool)
        assert isinstance(metrics["agent_target_met"], bool)
        assert isinstance(metrics["average_execution_target_met"], bool)

    def test_compliance_features(self, agent):
        """Test compliance and security features."""
        # Verify enterprise configuration
        framework_config = agent.kaizen_framework.config

        assert framework_config["audit_trail_enabled"] == True
        assert framework_config["compliance_mode"] == "enterprise"
        assert framework_config["security_level"] == "standard"

        # Test compliance report generation
        compliance_report = agent.kaizen_framework.generate_compliance_report()

        assert "compliance_status" in compliance_report
        assert "workflow_count" in compliance_report
        assert "audit_entries" in compliance_report
        assert "gdpr_compliance" in compliance_report
        assert "sox_compliance" in compliance_report

        logger.info(
            f"Compliance test passed - Status: {compliance_report['compliance_status']}"
        )


class TestPerformanceValidation:
    """Specific tests for performance target validation."""

    def test_framework_initialization_benchmark(self):
        """Benchmark framework initialization time."""
        times = []

        # Run multiple initializations to get average
        for _ in range(5):
            start_time = time.time()
            config = CoTConfig()
            agent = ChainOfThoughtAgent(config)
            init_time = agent.performance_metrics["framework_init_time"]
            times.append(init_time)
            agent.cleanup()

        avg_time = sum(times) / len(times)
        assert (
            avg_time < 100
        ), f"Average framework init time {avg_time:.1f}ms exceeds 100ms target"

        logger.info(
            f"Framework benchmark passed - Average: {avg_time:.1f}ms, Range: {min(times):.1f}-{max(times):.1f}ms"
        )

    def test_agent_creation_benchmark(self):
        """Benchmark agent creation time."""
        times = []

        for _ in range(5):
            config = CoTConfig()
            agent = ChainOfThoughtAgent(config)
            creation_time = agent.performance_metrics["agent_creation_time"]
            times.append(creation_time)
            agent.cleanup()

        avg_time = sum(times) / len(times)
        assert (
            avg_time < 200
        ), f"Average agent creation time {avg_time:.1f}ms exceeds 200ms target"

        logger.info(
            f"Agent creation benchmark passed - Average: {avg_time:.1f}ms, Range: {min(times):.1f}-{max(times):.1f}ms"
        )

    def test_reasoning_execution_benchmark(self):
        """Benchmark reasoning execution time."""
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config)

        try:
            execution_times = []
            test_problems = [
                "Calculate 15 * 23",
                "If a car travels 120 km in 2 hours, what is its speed?",
                "What is the area of a circle with radius 7?",
                "Compare the advantages of Python vs JavaScript",
                "Explain the water cycle process",
            ]

            for problem in test_problems:
                result = agent.solve_problem(problem)
                execution_times.append(result["execution_time_ms"])

            avg_execution_time = sum(execution_times) / len(execution_times)
            assert (
                avg_execution_time < 1000
            ), f"Average execution time {avg_execution_time:.1f}ms exceeds 1000ms target"

            logger.info(
                f"Execution benchmark passed - Average: {avg_execution_time:.1f}ms, Range: {min(execution_times):.1f}-{max(execution_times):.1f}ms"
            )

        finally:
            agent.cleanup()


def run_comprehensive_tests():
    """Run all tests and provide summary report."""
    print("Chain-of-Thought Agent - Comprehensive Test Suite")
    print("=" * 60)

    # Run pytest with detailed output
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    success = run_comprehensive_tests()
    if success:
        print("\n✓ All tests passed successfully!")
    else:
        print("\n✗ Some tests failed. Check output above.")
        exit(1)
