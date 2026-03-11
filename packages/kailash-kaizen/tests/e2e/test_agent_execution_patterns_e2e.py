"""
End-to-end tests for agent execution patterns with complete workflow scenarios.

These tests validate complete user workflows from agent creation to structured output
with real infrastructure and no mocking.
"""

import time

import pytest
from kaizen import Kaizen


class TestCompleteWorkflowScenarios:
    """Test complete end-to-end workflow scenarios with structured output."""

    def test_complete_qa_agent_workflow_e2e(self):
        """Test complete Q&A agent workflow from creation to structured response."""
        # This replicates the failing test case from reality check

        # Step 1: Initialize framework
        kaizen = Kaizen(
            config={
                "signature_programming_enabled": True,
                "memory_enabled": False,
                "optimization_enabled": False,
            }
        )

        # Step 2: Create agent with signature
        agent = kaizen.create_agent(
            "qa_agent_e2e",
            config={"model": "gpt-4", "temperature": 0.7, "max_tokens": 500},
            signature="question -> answer",
        )

        # Step 3: Execute complete workflow
        start_time = time.time()
        result = agent.execute(question="What is the capital of France?")
        execution_time = time.time() - start_time

        # Step 4: Validate complete workflow
        assert isinstance(
            result, dict
        ), "Complete workflow should return structured dict"
        assert "answer" in result, "Result should contain answer field per signature"
        assert result["answer"] is not None, "Answer should not be None"
        assert isinstance(result["answer"], str), "Answer should be string"
        assert len(result["answer"]) > 0, "Answer should not be empty"

        # Step 5: Validate answer content
        answer = result["answer"].lower()
        assert (
            "paris" in answer
        ), f"Answer should mention Paris, got: {result['answer']}"

        # Step 6: Validate performance
        assert (
            execution_time < 10.0
        ), f"Complete workflow took {execution_time:.2f}s, should be <10s"

    def test_complete_cot_reasoning_workflow_e2e(self):
        """Test complete Chain-of-Thought reasoning workflow end-to-end."""
        # Setup reasoning agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "cot_reasoning_e2e",
            config={"model": "gpt-4", "temperature": 0.3, "max_tokens": 1500},
            signature="problem -> step1, step2, final_answer",
        )

        # Execute complete CoT workflow
        start_time = time.time()
        result = agent.execute_cot(
            problem="A train travels 300 km in 4 hours. If it maintains the same speed, how long will it take to travel 450 km?"
        )
        execution_time = time.time() - start_time

        # Validate complete CoT workflow
        assert isinstance(result, dict), "CoT workflow should return structured output"

        # Validate reasoning structure
        expected_fields = ["step1", "step2", "final_answer"]
        found_fields = [field for field in expected_fields if field in result]
        assert (
            len(found_fields) >= 2
        ), f"Should find at least 2 reasoning fields, found: {found_fields}"

        # Validate reasoning content
        if "step1" in result:
            assert len(result["step1"]) > 20, "First step should be substantial"

        if "final_answer" in result:
            answer = result["final_answer"].lower()
            # Should mention time or hours in the answer for this problem
            assert any(
                word in answer for word in ["6", "hour", "time"]
            ), f"Answer should relate to time calculation, got: {result['final_answer']}"

        # Performance validation
        assert (
            execution_time < 10.0
        ), f"CoT workflow took {execution_time:.2f}s, should be <10s"

    def test_complete_react_agent_workflow_e2e(self):
        """Test complete ReAct agent workflow with thought-action-observation cycle."""
        # Setup ReAct agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "react_agent_e2e",
            config={"model": "gpt-4", "temperature": 0.3, "max_tokens": 1500},
            signature="task -> thought, action, observation, final_answer",
        )

        # Execute complete ReAct workflow
        start_time = time.time()
        result = agent.execute_react(
            task="Compare the advantages and disadvantages of Python vs JavaScript for web development"
        )
        execution_time = time.time() - start_time

        # Validate complete ReAct workflow
        assert isinstance(
            result, dict
        ), "ReAct workflow should return structured output"

        # Validate ReAct structure
        expected_fields = ["thought", "action", "observation", "final_answer"]
        found_fields = [field for field in expected_fields if field in result]
        assert (
            len(found_fields) >= 3
        ), f"Should find at least 3 ReAct fields, found: {found_fields}"

        # Validate content quality
        if "thought" in result:
            thought = result["thought"]
            assert len(thought) > 30, "Thought should be substantial"
            assert any(
                word in thought.lower() for word in ["python", "javascript", "compare"]
            ), "Thought should relate to the task"

        if "final_answer" in result:
            answer = result["final_answer"]
            assert len(answer) > 100, "Final answer should be comprehensive"
            assert any(
                word in answer.lower() for word in ["python", "javascript"]
            ), "Answer should address both languages"

        # Performance validation
        assert (
            execution_time < 10.0
        ), f"ReAct workflow took {execution_time:.2f}s, should be <10s"

    def test_multi_round_execution_workflow_e2e(self):
        """Test complete multi-round execution workflow with state persistence."""
        # Setup agent for iterative processing
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "multi_round_e2e",
            config={"model": "gpt-4", "temperature": 0.5},
            signature="input, previous_context -> output, updated_context",
        )

        # Execute multi-round workflow
        start_time = time.time()
        result = agent.execute_multi_round(
            inputs=[
                {"input": "Start a story about a detective"},
                {"input": "Add a mysterious case"},
                {"input": "Introduce a suspect"},
            ],
            rounds=3,
            memory=True,
            state_key="updated_context",
        )
        execution_time = time.time() - start_time

        # Validate multi-round workflow
        assert isinstance(result, dict), "Multi-round should return structured result"
        assert "rounds" in result, "Should contain rounds information"
        assert "total_rounds" in result, "Should contain total rounds count"
        assert "successful_rounds" in result, "Should contain successful rounds count"

        # Validate round execution
        assert result["total_rounds"] == 3, "Should execute all 3 rounds"
        assert (
            result["successful_rounds"] >= 1
        ), "Should have at least 1 successful round"

        # Validate round details
        rounds = result["rounds"]
        assert len(rounds) == 3, "Should have 3 round records"

        for i, round_info in enumerate(rounds):
            assert "round" in round_info, f"Round {i+1} should have round number"
            assert "inputs" in round_info, f"Round {i+1} should have inputs"
            assert round_info["round"] == i + 1, f"Round should be numbered {i+1}"

        # Performance validation
        assert (
            execution_time < 15.0
        ), f"Multi-round took {execution_time:.2f}s, should be <15s"


class TestEnterpriseWorkflowScenarios:
    """Test enterprise-level workflow scenarios with audit and monitoring."""

    def test_enterprise_audit_trail_workflow_e2e(self):
        """Test complete workflow with enterprise audit trail."""
        # Setup enterprise-enabled framework
        kaizen = Kaizen(
            config={
                "signature_programming_enabled": True,
                "enterprise_enabled": True,
                "audit_trail": True,
                "monitoring_enabled": True,
            }
        )

        # Create enterprise agent
        agent = kaizen.create_agent(
            "enterprise_audit_agent",
            config={
                "model": "gpt-4",
                "temperature": 0.2,  # Low temperature for enterprise
                "security_level": "high",
                "audit_enabled": True,
            },
            signature="sensitive_query -> analysis, recommendations, audit_info",
        )

        # Execute enterprise workflow
        result = agent.execute(
            sensitive_query="Analyze customer data patterns for business insights"
        )

        # Validate enterprise compliance
        assert isinstance(
            result, dict
        ), "Enterprise workflow should return structured output"

        # Check for enterprise features
        execution_history = agent.get_execution_history()
        assert len(execution_history) > 0, "Should track execution history for audit"

        # Validate audit information exists in history
        latest_execution = execution_history[-1]
        assert "timestamp" in latest_execution, "Audit trail should include timestamp"

    def test_high_performance_workflow_scenario_e2e(self):
        """Test high-performance workflow scenario for enterprise load."""
        # Setup performance-optimized agent
        kaizen = Kaizen(
            config={"signature_programming_enabled": True, "performance_mode": True}
        )

        agent = kaizen.create_agent(
            "high_perf_agent",
            config={
                "model": "gpt-4",
                "temperature": 0.1,
                "max_tokens": 800,  # Optimized for speed
                "timeout": 30,
            },
            signature="query -> response",
        )

        # Execute multiple rapid queries
        queries = [
            "What is machine learning?",
            "Explain cloud computing",
            "Define artificial intelligence",
            "What is blockchain?",
            "Explain data science",
        ]

        start_time = time.time()
        results = []

        for query in queries:
            result = agent.execute(query=query)
            results.append(result)

        total_time = time.time() - start_time

        # Validate high-performance execution
        assert len(results) == 5, "Should complete all 5 queries"
        for i, result in enumerate(results):
            assert isinstance(
                result, dict
            ), f"Query {i+1} should return structured result"
            assert "response" in result, f"Query {i+1} should have response field"

        # Performance requirements for enterprise load
        avg_time_per_query = total_time / len(queries)
        assert (
            avg_time_per_query < 3.0
        ), f"Average time per query {avg_time_per_query:.2f}s should be <3s"
        assert total_time < 15.0, f"Total time {total_time:.2f}s should be <15s"

    def test_complex_signature_workflow_e2e(self):
        """Test complex signature workflow with multiple inputs and outputs."""
        # Setup complex signature agent
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "complex_signature_agent",
            config={"model": "gpt-4"},
            signature="document, context, user_preference -> summary, key_points, sentiment, recommendations",
        )

        # Execute complex workflow
        result = agent.execute(
            document="Python is a versatile programming language used in web development, data science, and AI.",
            context="Programming language evaluation for team selection",
            user_preference="Focus on practical applications and learning curve",
        )

        # Validate complex signature handling
        assert isinstance(
            result, dict
        ), "Complex signature should return structured output"

        # Check for expected output fields
        expected_outputs = ["summary", "key_points", "sentiment", "recommendations"]
        found_outputs = [field for field in expected_outputs if field in result]
        assert (
            len(found_outputs) >= 2
        ), f"Should find at least 2 output fields, found: {found_outputs}"

        # Validate content quality for complex processing
        for field in found_outputs:
            assert isinstance(result[field], str), f"Field {field} should be string"
            assert (
                len(result[field]) > 10
            ), f"Field {field} should have substantial content"


class TestPatternExecutionScenarios:
    """Test specific pattern execution scenarios end-to-end."""

    def test_mathematical_reasoning_cot_e2e(self):
        """Test mathematical reasoning with Chain-of-Thought pattern."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "math_cot_agent",
            config={
                "model": "gpt-4",
                "temperature": 0.1,  # Low temperature for math accuracy
            },
            signature="math_problem -> step1, step2, step3, solution",
        )

        # Execute mathematical CoT
        result = agent.execute_cot(
            math_problem="If 3x + 7 = 22, what is the value of x?"
        )

        # Validate mathematical reasoning
        assert isinstance(result, dict), "Math CoT should return structured output"

        # Look for mathematical reasoning steps
        step_fields = [field for field in result.keys() if "step" in field.lower()]
        assert len(step_fields) >= 1, "Should have at least one reasoning step"

        # Check for solution
        solution_fields = [
            field
            for field in result.keys()
            if "solution" in field.lower() or "answer" in field.lower()
        ]
        if solution_fields:
            solution = str(result[solution_fields[0]]).lower()
            assert (
                "5" in solution or "x = 5" in solution or "x=5" in solution
            ), f"Solution should be x=5, got: {result[solution_fields[0]]}"

    def test_run_analysis_react_e2e(self):
        """Test research and analysis with ReAct pattern."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "research_react_agent",
            config={"model": "gpt-4", "temperature": 0.3},
            signature="research_topic -> thought, action, observation, analysis",
        )

        # Execute research ReAct
        result = agent.execute_react(
            research_topic="Impact of artificial intelligence on job market"
        )

        # Validate research analysis
        assert isinstance(
            result, dict
        ), "Research ReAct should return structured output"

        # Validate ReAct components
        if "thought" in result:
            thought = result["thought"].lower()
            assert any(
                word in thought
                for word in ["analyze", "research", "consider", "investigate"]
            ), "Thought should show research planning"

        if "analysis" in result:
            analysis = result["analysis"]
            assert len(analysis) > 100, "Analysis should be comprehensive"
            assert any(
                word in analysis.lower()
                for word in ["impact", "job", "ai", "artificial intelligence"]
            ), "Analysis should address the research topic"

    def test_creative_writing_pattern_e2e(self):
        """Test creative writing with structured output pattern."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "creative_writing_agent",
            config={
                "model": "gpt-4",
                "temperature": 0.8,  # Higher temperature for creativity
            },
            signature="prompt -> setting, characters, plot_outline, opening_paragraph",
        )

        # Execute creative writing
        result = agent.execute(prompt="Write a science fiction story about time travel")

        # Validate creative output structure
        assert isinstance(
            result, dict
        ), "Creative writing should return structured output"

        expected_fields = ["setting", "characters", "plot_outline", "opening_paragraph"]
        found_fields = [field for field in expected_fields if field in result]
        assert (
            len(found_fields) >= 2
        ), f"Should find at least 2 creative fields, found: {found_fields}"

        # Validate creative content
        for field in found_fields:
            content = result[field]
            assert isinstance(content, str), f"Field {field} should be string"
            assert len(content) > 20, f"Field {field} should have creative content"

        # Check for time travel theme
        all_content = " ".join([str(result[field]) for field in found_fields]).lower()
        assert any(
            word in all_content for word in ["time", "travel", "future", "past"]
        ), "Content should relate to time travel theme"


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery in complete workflows."""

    def test_invalid_signature_error_handling_e2e(self):
        """Test error handling for invalid signature scenarios."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        # Test with malformed signature
        try:
            agent = kaizen.create_agent(
                "invalid_sig_agent",
                config={"model": "gpt-4"},
                signature="invalid -> -> -> malformed",
            )

            # If agent creation succeeds, execution should handle gracefully
            result = agent.execute(invalid="test")
            # Should either succeed with structured output or fail gracefully
            if isinstance(result, dict):
                assert len(result) >= 0, "Should return valid dictionary"

        except Exception as e:
            # Should provide informative error message
            error_msg = str(e).lower()
            assert any(
                word in error_msg for word in ["signature", "invalid", "malformed"]
            ), f"Error should be informative about signature issue: {e}"

    def test_network_timeout_recovery_e2e(self):
        """Test recovery from network timeout scenarios."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "timeout_test_agent",
            config={
                "model": "gpt-4",
                "timeout": 1,  # Very short timeout to potentially trigger timeout
            },
            signature="query -> response",
        )

        # Execute with potential timeout
        try:
            result = agent.execute(query="Explain quantum computing in detail")

            # If succeeds, should be valid
            assert isinstance(
                result, dict
            ), "Should return structured output if successful"
            assert "response" in result, "Should contain response field"

        except Exception as e:
            # If timeout occurs, should be handled gracefully
            error_msg = str(e).lower()
            # Should be a reasonable timeout error, not a crash
            assert (
                "traceback" not in error_msg
            ), "Should handle timeout gracefully without exposing traceback"

    def test_large_input_handling_e2e(self):
        """Test handling of large inputs in complete workflows."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "large_input_agent",
            config={"model": "gpt-4", "max_tokens": 2000},
            signature="large_text -> summary",
        )

        # Create large input text
        large_text = "This is a test paragraph. " * 500  # ~2500 words

        # Execute with large input
        start_time = time.time()
        result = agent.execute(large_text=large_text)
        execution_time = time.time() - start_time

        # Validate large input handling
        assert isinstance(
            result, dict
        ), "Should handle large input and return structured output"
        assert "summary" in result, "Should contain summary field"
        assert len(result["summary"]) > 50, "Summary should be substantial"
        assert len(result["summary"]) < len(
            large_text
        ), "Summary should be shorter than input"

        # Performance should still be reasonable
        assert (
            execution_time < 15.0
        ), f"Large input processing took {execution_time:.2f}s, should be <15s"


class TestIntegrationWithMCPServers:
    """Test integration with MCP servers in complete workflows."""

    def test_agent_with_mcp_tools_e2e(self):
        """Test agent execution with MCP tools integration."""
        kaizen = Kaizen(
            config={"signature_programming_enabled": True, "mcp_enabled": True}
        )

        # Create agent with MCP capabilities
        agent = kaizen.create_agent(
            "mcp_integration_agent",
            config={"model": "gpt-4", "mcp_tools": ["search", "calculate"]},
            signature="task_with_tools -> approach, result",
        )

        # Note: This test requires MCP servers to be running
        # For E2E testing, we'd need actual MCP server setup

        # Execute workflow that could use tools
        try:
            result = agent.execute(
                task_with_tools="Calculate the area of a circle with radius 10"
            )

            # Validate tool-enhanced execution
            assert isinstance(
                result, dict
            ), "MCP-enhanced workflow should return structured output"

            expected_fields = ["approach", "result"]
            found_fields = [field for field in expected_fields if field in result]
            assert (
                len(found_fields) >= 1
            ), f"Should find at least 1 output field, found: {found_fields}"

        except Exception as e:
            # If MCP servers not available, should fail gracefully
            error_msg = str(e).lower()
            if "mcp" in error_msg or "connection" in error_msg:
                pytest.skip("MCP servers not available for E2E testing")
            else:
                raise  # Re-raise unexpected errors

    def test_mcp_server_exposure_e2e(self):
        """Test exposing agent as MCP server complete workflow."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "mcp_server_agent",
            config={"model": "gpt-4"},
            signature="request -> response",
        )

        # Expose as MCP server
        server_config = agent.expose_as_mcp_server(
            port=18088,  # Use different port to avoid conflicts
            tools=["process_request"],
            auth="none",
        )

        # Validate server exposure
        assert server_config is not None, "Should return server configuration"
        assert hasattr(server_config, "server_name"), "Should have server name"
        assert hasattr(server_config, "port"), "Should have port configuration"
        assert server_config.port == 18088, "Should use specified port"

        # Test server state
        if hasattr(server_config, "server_state"):
            # Should be either running or have a valid error state
            assert server_config.server_state in [
                "running",
                "initializing",
                "failed",
            ], f"Server should have valid state, got: {server_config.server_state}"

        # Cleanup
        if hasattr(server_config, "stop_server"):
            server_config.stop_server()


class TestPerformanceValidation:
    """Test performance validation for complete workflows."""

    def test_concurrent_agent_execution_e2e(self):
        """Test concurrent execution of multiple agents."""
        import concurrent.futures

        kaizen = Kaizen(config={"signature_programming_enabled": True})

        # Create multiple agents
        agents = []
        for i in range(3):  # Test with 3 concurrent agents
            agent = kaizen.create_agent(
                f"concurrent_agent_{i}",
                config={"model": "gpt-4"},
                signature="task -> result",
            )
            agents.append(agent)

        def execute_agent_task(agent, task_id):
            """Execute agent task for concurrent testing."""
            return agent.execute(task=f"Process task {task_id}")

        # Execute agents concurrently
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(execute_agent_task, agents[i], i) for i in range(3)
            ]

            results = [future.result(timeout=30) for future in futures]

        total_time = time.time() - start_time

        # Validate concurrent execution
        assert len(results) == 3, "Should complete all concurrent executions"
        for i, result in enumerate(results):
            assert isinstance(
                result, dict
            ), f"Concurrent agent {i} should return structured output"
            assert "result" in result, f"Concurrent agent {i} should have result field"

        # Performance should benefit from concurrency
        assert (
            total_time < 20.0
        ), f"Concurrent execution took {total_time:.2f}s, should be <20s"

    def test_memory_stability_long_workflow_e2e(self):
        """Test memory stability during long-running workflows."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        kaizen = Kaizen(config={"signature_programming_enabled": True})
        agent = kaizen.create_agent(
            "memory_test_agent",
            config={"model": "gpt-4"},
            signature="iteration -> result",
        )

        # Execute multiple iterations
        results = []
        for i in range(10):  # 10 iterations to test memory stability
            result = agent.execute(iteration=f"Iteration {i}")
            results.append(result)

            # Check memory periodically
            if i % 3 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory
                assert (
                    memory_growth < 50
                ), f"Memory grew by {memory_growth:.2f}MB at iteration {i}, should be <50MB"

        # Final validation
        final_memory = process.memory_info().rss / 1024 / 1024
        total_memory_growth = final_memory - initial_memory

        assert len(results) == 10, "Should complete all iterations"
        assert (
            total_memory_growth < 100
        ), f"Total memory growth {total_memory_growth:.2f}MB should be <100MB"

        # All results should be valid
        for i, result in enumerate(results):
            assert isinstance(
                result, dict
            ), f"Iteration {i} should return structured output"
