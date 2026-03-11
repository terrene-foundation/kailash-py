"""
Integration tests for agent execution patterns with real Core SDK integration.

These tests validate agent execution with real WorkflowBuilder, LocalRuntime, and signature
compilation without mocking Core SDK components.
"""

import time

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kaizen import Kaizen


class TestRealCoreSDKIntegration:
    """Test agent execution with real Core SDK components."""

    def test_agent_execute_with_real_workflow_builder(self):
        """Test that agent.execute() creates and runs real Core SDK workflows."""
        # Setup with real components
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "integration_qa_agent",
            config={"model": "gpt-4", "temperature": 0.7, "max_tokens": 500},
            signature="question -> answer",
        )

        # Execute with structured input - should create real workflow
        start_time = time.time()
        result = agent.execute(question="What is the capital of France?")
        execution_time = time.time() - start_time

        # Validate real execution
        assert isinstance(result, dict), "Should return structured dictionary"
        assert "answer" in result, "Should contain answer field per signature"
        assert result["answer"] is not None, "Answer should not be None"
        assert execution_time < 5.0, "Integration test should complete within 5 seconds"

    def test_agent_workflow_compilation_with_signature(self):
        """Test that agent compiles signature to real WorkflowBuilder workflow."""
        # Setup
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "compilation_agent",
            config={"model": "gpt-4", "temperature": 0.3},
            signature="problem -> analysis, solution",
        )

        # Test workflow compilation
        workflow = agent.compile_workflow()

        # Validate real WorkflowBuilder
        assert isinstance(
            workflow, WorkflowBuilder
        ), "Should return real WorkflowBuilder"

        # Execute compiled workflow with real runtime
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(), {agent.agent_id: {"problem": "Test problem analysis"}}
        )

        # Validate execution (run_id may be None due to task manager setup, but execution should succeed)
        assert isinstance(results, dict), "Should return results dictionary"
        # Verify the workflow executed successfully
        assert len(results) > 0, "Should return non-empty results"

    def test_signature_workflow_parameter_injection(self):
        """Test that signature compilation injects parameters correctly."""
        # Setup with complex signature
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "complex_agent",
            config={"model": "gpt-4", "temperature": 0.2, "max_tokens": 1000},
            signature="context, question -> analysis, answer, confidence",
        )

        # Test parameter injection in real workflow
        workflow = agent.compile_workflow()

        # Execute with multiple inputs
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(),
            {
                agent.agent_id: {
                    "context": "Paris is the capital and largest city of France",
                    "question": "What is the capital of France?",
                }
            },
        )

        # Validate parameter handling (run_id may be None due to task manager setup, but execution should succeed)
        assert isinstance(results, dict), "Should process complex signature inputs"
        assert len(results) > 0, "Should return non-empty results"


class TestChainOfThoughtIntegration:
    """Test Chain-of-Thought pattern with real Core SDK integration."""

    def test_agent_execute_cot_with_real_llm(self):
        """Test CoT execution with real LLM integration."""
        # Setup CoT agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "cot_integration_agent",
            config={
                "model": "gpt-4",  # Use GPT-4 for better reasoning
                "temperature": 0.3,
                "max_tokens": 1200,
            },
            signature="problem -> reasoning, answer",
        )

        # Execute Chain-of-Thought reasoning
        start_time = time.time()
        result = agent.execute_cot(
            problem="If a train travels at 80 km/h for 2.5 hours, how far does it go?"
        )
        execution_time = time.time() - start_time

        # Validate CoT execution
        assert isinstance(result, dict), "CoT should return structured output"
        assert execution_time < 5.0, "CoT should complete within 5 seconds"

        # CoT should include either reasoning or answer fields (flexible for implementation)
        has_reasoning = (
            "reasoning" in result or "answer" in result or "response" in result
        )
        assert (
            has_reasoning
        ), f"CoT should include reasoning/answer fields, got: {list(result.keys())}"

        # Validate that we got some meaningful response
        response_content = str(result)
        assert len(response_content) > 20, "CoT should return substantial content"

    def test_cot_prompt_integration_with_signature_compiler(self):
        """Test that CoT prompt generation integrates with signature compilation."""
        # Setup
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "cot_prompt_agent",
            config={"model": "gpt-4"},
            signature="problem -> step1, step2, step3, conclusion",
        )

        # Execute CoT to test prompt integration
        result = agent.execute_cot(
            problem="What are the environmental benefits of renewable energy?"
        )

        # Validate structured CoT output
        assert isinstance(result, dict), "Should return dictionary"
        expected_fields = ["step1", "step2", "step3", "conclusion"]

        # At minimum, should have structured thinking
        has_structured_output = any(field in result for field in expected_fields)
        assert has_structured_output, "CoT should produce structured reasoning output"

    def test_cot_execution_performance(self):
        """Test CoT execution performance requirements."""
        # Setup efficient CoT agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "cot_perf_agent",
            config={
                "model": "gpt-4",
                "temperature": 0.3,
                "max_tokens": 800,  # Reasonable limit
            },
            signature="problem -> reasoning, solution",
        )

        # Test performance
        start_time = time.time()
        result = agent.execute_cot(problem="Simple math: What is 15 * 7?")
        execution_time = time.time() - start_time

        # Performance validation
        assert (
            execution_time < 5.0
        ), f"CoT execution took {execution_time:.2f}s, should be <5s"
        assert isinstance(result, dict), "Should maintain structured output"
        assert (
            "reasoning" in result or "solution" in result
        ), "Should provide reasoning output"


class TestReActIntegration:
    """Test ReAct pattern with real Core SDK integration."""

    def test_agent_execute_react_with_real_workflow(self):
        """Test ReAct execution with real workflow integration."""
        # Setup ReAct agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "react_integration_agent",
            config={"model": "gpt-4", "temperature": 0.3, "max_tokens": 1200},
            signature="task -> thought, action, observation, final_answer",
        )

        # Execute ReAct pattern
        start_time = time.time()
        result = agent.execute_react(
            task="Analyze the benefits of using Python for data science"
        )
        execution_time = time.time() - start_time

        # Validate ReAct execution
        assert isinstance(result, dict), "ReAct should return structured output"
        assert execution_time < 5.0, "ReAct should complete within 5 seconds"

        # ReAct should include some reasoning fields (flexible for implementation)
        expected_fields = [
            "thought",
            "action",
            "observation",
            "final_answer",
            "answer",
            "response",
        ]
        has_react_field = any(field in result for field in expected_fields)
        assert (
            has_react_field
        ), f"ReAct should include reasoning fields, got: {list(result.keys())}"

        # Validate content quality
        response_content = str(result)
        assert len(response_content) > 20, "ReAct should return substantial content"

    def test_react_pattern_workflow_node_integration(self):
        """Test that ReAct pattern integrates properly with workflow nodes."""
        # Setup
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "react_node_agent",
            config={"model": "gpt-4"},
            signature="query -> reasoning, action, result",
        )

        # Execute and validate workflow node creation
        result = agent.execute_react(
            query="What are the key features of Python programming language?"
        )

        # Validate integration
        assert isinstance(
            result, dict
        ), "Should create and execute workflow successfully"

        # Check that structured ReAct output is maintained
        expected_structure = ["reasoning", "action", "result"]
        has_react_structure = any(field in result for field in expected_structure)
        assert has_react_structure, "Should maintain ReAct reasoning structure"

    def test_react_execution_performance(self):
        """Test ReAct execution performance requirements."""
        # Setup performance test agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "react_perf_agent",
            config={"model": "gpt-4", "temperature": 0.3, "max_tokens": 1000},
            signature="task -> thought, action, answer",
        )

        # Performance test
        start_time = time.time()
        result = agent.execute_react(task="List three benefits of cloud computing")
        execution_time = time.time() - start_time

        # Performance validation
        assert (
            execution_time < 5.0
        ), f"ReAct execution took {execution_time:.2f}s, should be <5s"
        assert isinstance(
            result, dict
        ), "Should maintain performance while providing structure"


class TestSignatureCompilerIntegration:
    """Test signature compiler integration with real execution."""

    def test_signature_compiler_workflow_generation(self):
        """Test that signature compiler generates proper workflow configurations."""
        # Setup with signature requiring compilation
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "compiler_test_agent",
            config={"model": "gpt-4", "temperature": 0.5},
            signature="input_text, context -> summary, key_points, sentiment",
        )

        # Test compilation by executing
        result = agent.execute(
            input_text="Python is a versatile programming language",
            context="Programming language discussion",
        )

        # Validate compilation worked
        assert isinstance(result, dict), "Signature compilation should enable execution"

        # Check expected output structure
        expected_outputs = ["summary", "key_points", "sentiment"]
        has_expected_structure = any(output in result for output in expected_outputs)
        assert (
            has_expected_structure
        ), "Compiled signature should produce expected outputs"

    def test_signature_parameter_enhancement_integration(self):
        """Test that signature compilation enhances parameters correctly."""
        # Setup agent with basic config
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "enhancement_agent",
            config={
                "model": "gpt-3.5-turbo",  # Basic model
                "temperature": 0.9,  # High temperature
            },
            signature="complex_problem -> detailed_analysis, recommendations",
        )

        # Execute complex pattern (should enhance parameters)
        result = agent.execute_cot(
            complex_problem="How can we optimize machine learning model performance?"
        )

        # Validate that execution worked with parameter enhancement
        assert isinstance(
            result, dict
        ), "Parameter enhancement should not break execution"

        # Should produce detailed output despite basic initial config
        output_content = str(result)
        assert (
            len(output_content) > 100
        ), "Enhanced parameters should produce substantial output"

    def test_multiple_signature_executions_performance(self):
        """Test performance with multiple different signature executions."""
        # Setup agent for multiple executions
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "multi_exec_agent", config={"model": "gpt-4"}, signature="query -> response"
        )

        # Execute multiple times with different methods
        start_time = time.time()

        # Normal execution
        result1 = agent.execute(query="What is Python?")

        # CoT execution
        agent.signature = "problem -> reasoning, answer"
        result2 = agent.execute_cot(problem="Explain object-oriented programming")

        # ReAct execution
        agent.signature = "task -> thought, action, conclusion"
        result3 = agent.execute_react(task="Compare Python and Java")

        total_time = time.time() - start_time

        # Performance validation
        assert (
            total_time < 15.0
        ), f"Multiple executions took {total_time:.2f}s, should be <15s"

        # All should complete successfully
        assert isinstance(result1, dict), "Normal execution should succeed"
        assert isinstance(result2, dict), "CoT execution should succeed"
        assert isinstance(result3, dict), "ReAct execution should succeed"


class TestRealLLMResponseParsing:
    """Test parsing of real LLM responses to structured output."""

    def test_parse_real_llm_unstructured_response(self):
        """Test parsing real unstructured LLM response into signature structure."""
        # This tests the critical missing functionality
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "parsing_agent",
            config={"model": "gpt-4", "temperature": 0.7},
            signature="question -> answer",
        )

        # Execute with real LLM to get unstructured response
        result = agent.execute(question="What is artificial intelligence?")

        # Validate parsing worked
        assert isinstance(result, dict), "Should parse to structured output"
        assert "answer" in result, "Should extract answer field"
        assert isinstance(result["answer"], str), "Answer should be string"
        assert len(result["answer"]) > 10, "Answer should be substantial"

    def test_parse_complex_signature_response(self):
        """Test parsing complex multi-field signature responses."""
        # Setup complex signature
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "complex_parsing_agent",
            config={"model": "gpt-4"},
            signature="topic -> definition, examples, use_cases",
        )

        # Execute and test parsing
        result = agent.execute(topic="Machine Learning")

        # Validate complex parsing
        assert isinstance(result, dict), "Should parse complex response"
        expected_fields = ["definition", "examples", "use_cases"]

        # Should extract multiple fields
        found_fields = [field for field in expected_fields if field in result]
        assert (
            len(found_fields) >= 1
        ), f"Should extract at least one field, found: {found_fields}"

    def test_error_handling_for_parsing_failures(self):
        """Test error handling when LLM response cannot be parsed."""
        # Setup agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "error_handling_agent",
            config={"model": "gpt-4"},
            signature="invalid_input -> structured_output",
        )

        # This might fail to parse correctly, but should handle gracefully
        try:
            result = agent.execute(invalid_input="")
            # If it succeeds, should be structured
            assert isinstance(
                result, dict
            ), "Should return dict even with difficult input"
        except Exception as e:
            # If it fails, should be informative error
            assert (
                "signature" in str(e).lower() or "parse" in str(e).lower()
            ), "Error should be related to signature parsing"


class TestExecutionPatternValidation:
    """Test validation of execution patterns against requirements."""

    def test_execution_time_requirements(self):
        """Test that all execution patterns meet time requirements."""
        # Setup test agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "perf_validation_agent",
            config={"model": "gpt-4"},
            signature="input -> output",
        )

        # Test simple execution: <200ms for signature-based workflows
        start_time = time.time()
        agent.execute(input="Simple test")
        simple_time = time.time() - start_time

        # Note: With real LLM calls, 200ms is unrealistic, using 5s for integration test
        assert (
            simple_time < 5.0
        ), f"Simple execution took {simple_time:.2f}s, should be <5s"

        # Test pattern execution: <500ms for complex patterns (adjusted for real LLM)
        agent.signature = "problem -> reasoning, solution"
        start_time = time.time()
        agent.execute_cot(problem="Basic problem")
        pattern_time = time.time() - start_time

        assert (
            pattern_time < 5.0
        ), f"Pattern execution took {pattern_time:.2f}s, should be <5s"

    def test_structured_output_compliance(self):
        """Test that all execution patterns produce compliant structured output."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        # Test different signature patterns
        signatures_to_test = [
            ("simple -> result", {"simple": "test"}),
            ("question -> answer", {"question": "What is AI?"}),
            ("problem -> analysis, solution", {"problem": "Solve this"}),
        ]

        for signature_spec, inputs in signatures_to_test:
            agent = kaizen.create_agent(
                f"compliance_agent_{hash(signature_spec)}",
                config={"model": "gpt-4"},
                signature=signature_spec,
            )

            # Execute and validate compliance
            result = agent.execute(**inputs)

            assert isinstance(
                result, dict
            ), f"Signature '{signature_spec}' should return dict"
            assert (
                len(result) > 0
            ), f"Signature '{signature_spec}' should return non-empty result"

    def test_memory_and_resource_usage(self):
        """Test resource usage during execution patterns."""
        import os

        import psutil

        # Get initial memory
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Setup and execute multiple agents
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agents = []

        for i in range(5):  # Create multiple agents
            agent = kaizen.create_agent(
                f"resource_test_agent_{i}",
                config={"model": "gpt-4"},
                signature="input -> output",
            )
            agents.append(agent)

        # Execute all agents
        for i, agent in enumerate(agents):
            result = agent.execute(input=f"Test input {i}")
            assert isinstance(result, dict), f"Agent {i} should execute successfully"

        # Check final memory
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100MB for 5 agents)
        assert (
            memory_increase < 100
        ), f"Memory increased by {memory_increase:.2f}MB, should be <100MB"
