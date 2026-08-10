"""
Integration tests for CORE-003: Complete core feature implementations beyond stubs.

This module implements Tier 2 integration tests with real Core SDK runtime execution,
validating that the implemented business logic actually works with real infrastructure.

Testing Strategy:
- Tier 2 (Integration): Real Core SDK runtime execution with LocalRuntime
- NO MOCKING - Real workflow compilation and execution
- Real signature parsing and validation
- Real pattern execution with actual LLM nodes
- Test execution time <5 seconds per test

Critical Success Criteria:
- All business logic implementations must work with real Core SDK
- Signature-based workflows must compile and execute successfully
- Pattern execution must generate proper structured output
- Enterprise workflows must execute with audit trails
- Multi-agent coordination must actually coordinate agents
"""

import time

import pytest

# Test the Kaizen framework with real Core SDK
from kaizen import Kaizen


class TestAgentSignatureIntegrationReal:
    """
    Test agent signature integration with real Core SDK runtime execution.

    Validates that signature integration actually works end-to-end.
    """

    def test_real_signature_execution_with_core_sdk(self):
        """Real signature-based agent execution with Core SDK runtime."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        # Create agent with signature
        agent = kaizen.create_agent(
            "qa",
            {
                "model": "gpt-3.5-turbo",
                "signature": "question -> answer",
                "temperature": 0.1,  # Low temperature for consistent testing
            },
        )

        # REAL execution - no mocking
        result = agent.execute(question="What is 2+2?")

        # Validate real structured output
        assert isinstance(result, dict), "Real execution should return dictionary"
        assert "answer" in result, "Result should contain 'answer' field per signature"
        assert isinstance(result["answer"], str), "Answer should be a string"
        assert len(result["answer"].strip()) > 0, "Answer should not be empty"

        # Validate signature preservation
        assert (
            agent.signature is not None
        ), "Signature should be preserved after execution"
        assert agent.has_signature == True, "Agent should report having signature"
        assert (
            agent.can_execute_structured == True
        ), "Agent should support structured execution"

    def test_complex_signature_real_execution(self):
        """Complex multi-field signature with real Core SDK execution."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        agent = kaizen.create_agent(
            "analyzer",
            {
                "model": "gpt-3.5-turbo",
                "signature": "text, task -> analysis, confidence",
                "temperature": 0.1,
            },
        )

        # Real execution with complex inputs
        result = agent.execute(
            text="The weather is sunny today.", task="Analyze sentiment"
        )

        # Validate complex structured output
        assert isinstance(result, dict), "Complex execution should return dictionary"
        assert "analysis" in result, "Result should contain analysis field"
        assert "confidence" in result, "Result should contain confidence field"

        # Both fields should have meaningful content
        for field in ["analysis", "confidence"]:
            assert result[field] is not None, f"{field} should not be None"
            assert len(str(result[field]).strip()) > 0, f"{field} should not be empty"

    def test_signature_error_handling_real(self):
        """Real error handling for signature validation."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        agent = kaizen.create_agent(
            "qa", {"model": "gpt-3.5-turbo", "signature": "question -> answer"}
        )

        # Real validation should catch missing inputs
        with pytest.raises(ValueError, match="Missing required inputs"):
            agent.execute()  # No question provided

        with pytest.raises(ValueError, match="Missing required inputs"):
            agent.execute(wrong_input="test")  # Wrong input name


class TestPatternExecutionReal:
    """
    Test pattern execution with real Core SDK runtime execution.

    Validates that CoT and ReAct patterns actually work end-to-end.
    """

    def test_real_chain_of_thought_execution(self):
        """Real Chain-of-Thought execution with Core SDK."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        # Create CoT agent
        cot_agent = kaizen.create_agent(
            "cot",
            {
                "model": "gpt-3.5-turbo",
                "signature": "problem -> reasoning, answer",
                "temperature": 0.1,
            },
        )

        # Real CoT execution
        result = cot_agent.execute_cot(
            problem="If a train travels 60 mph for 2 hours, how far does it go?"
        )

        # Validate real CoT structured output
        assert isinstance(result, dict), "CoT execution should return dictionary"
        assert "reasoning" in result, "CoT result should contain reasoning"
        assert "answer" in result, "CoT result should contain answer"

        # Validate reasoning quality
        reasoning = str(result["reasoning"]).lower()
        answer = str(result["answer"]).lower()

        # Should contain reasoning elements
        assert len(reasoning.strip()) > 10, "Reasoning should be substantive"
        assert len(answer.strip()) > 0, "Answer should not be empty"

        # Mathematical reasoning should be present
        assert any(
            word in reasoning
            for word in ["60", "speed", "distance", "time", "multiply"]
        ), "Reasoning should contain mathematical concepts"

    def test_real_react_execution(self):
        """Real ReAct execution with Core SDK."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        # Create ReAct agent
        react_agent = kaizen.create_agent(
            "react",
            {
                "model": "gpt-3.5-turbo",
                "signature": "task -> thought, action, observation, final_answer",
                "temperature": 0.1,
            },
        )

        # Real ReAct execution
        result = react_agent.execute_react(task="Explain the concept of gravity")

        # Validate real ReAct structured output
        assert isinstance(result, dict), "ReAct execution should return dictionary"
        required_fields = ["thought", "action", "observation", "final_answer"]

        for field in required_fields:
            assert field in result, f"ReAct result should contain {field}"
            assert len(str(result[field]).strip()) > 0, f"{field} should not be empty"

        # Validate ReAct pattern quality
        thought = str(result["thought"]).lower()
        action = str(result["action"]).lower()
        observation = str(result["observation"]).lower()

        # Should contain ReAct elements
        assert len(thought.strip()) > 5, "Thought should be substantive"
        assert len(action.strip()) > 5, "Action should be substantive"
        assert len(observation.strip()) > 5, "Observation should be substantive"


class TestEnterpriseWorkflowReal:
    """
    Test enterprise workflow execution with real Core SDK runtime.

    Validates that enterprise workflows execute with real audit trails.
    """

    def test_real_enterprise_approval_workflow(self):
        """Real enterprise approval workflow execution."""
        kaizen = Kaizen(
            config={
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "transparency_enabled": True,
            }
        )

        # Create real enterprise approval workflow
        workflow = kaizen.create_enterprise_workflow(
            "approval",
            {"approval_levels": ["manager"], "audit_requirements": "complete"},
        )

        # Real execution
        result = workflow.execute(
            {"request": "Budget approval for $10,000", "requester": "test@company.com"}
        )

        # Validate real enterprise execution
        assert isinstance(result, dict), "Enterprise workflow should return dictionary"
        assert "workflow_id" in result, "Result should contain workflow_id"
        assert "audit_trail" in result, "Result should contain audit_trail"
        assert "compliance_status" in result, "Result should contain compliance_status"

        # Validate audit trail
        audit_trail = result["audit_trail"]
        assert isinstance(audit_trail, list), "Audit trail should be list"
        assert len(audit_trail) > 0, "Audit trail should not be empty"

        # Each audit entry should have required fields
        for entry in audit_trail:
            assert "action" in entry, "Audit entry should have action"
            assert "timestamp" in entry, "Audit entry should have timestamp"

        # Validate execution metadata
        assert "execution_time_ms" in result, "Should include execution time"
        assert result["execution_time_ms"] > 0, "Execution time should be positive"

    def test_real_enterprise_document_analysis_workflow(self):
        """Real enterprise document analysis workflow execution."""
        kaizen = Kaizen(
            config={
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "transparency_enabled": True,
            }
        )

        workflow = kaizen.create_enterprise_workflow(
            "document_analysis",
            {
                "processing_stages": ["extraction", "analysis"],
                "compliance_checks": ["PII_detection"],
                "audit_requirements": "standard",
            },
        )

        # Real execution with document data
        result = workflow.execute(
            {
                "document_content": "This is a test document for analysis.",
                "processing_requirements": "Extract key information",
            }
        )

        # Validate real document analysis execution
        assert isinstance(result, dict), "Document analysis should return dictionary"
        assert "processing_status" in result, "Result should contain processing_status"
        assert (
            "documents_processed" in result
        ), "Result should contain documents_processed"
        assert (
            "compliance_checks_passed" in result
        ), "Result should contain compliance_checks_passed"

        # Validate processing results
        assert (
            result["processing_status"] == "completed"
        ), "Processing should be completed"
        assert result["documents_processed"] >= 1, "Should process at least 1 document"


class TestMultiAgentCoordinationReal:
    """
    Test multi-agent coordination with real Core SDK execution.

    Validates that multi-agent workflows actually coordinate agents.
    """

    def test_real_debate_workflow_execution(self):
        """Real multi-agent debate workflow execution."""
        kaizen = Kaizen(config={"multi_agent_enabled": True})

        # Create real agents for debate
        proponent = kaizen.create_specialized_agent(
            "proponent",
            "Argue for renewable energy",
            {"model": "gpt-3.5-turbo", "stance": "supporting"},
        )
        opponent = kaizen.create_specialized_agent(
            "opponent",
            "Present challenges about renewable energy",
            {"model": "gpt-3.5-turbo", "stance": "opposing"},
        )
        moderator = kaizen.create_specialized_agent(
            "moderator",
            "Moderate discussion and synthesize",
            {"model": "gpt-3.5-turbo", "stance": "neutral"},
        )

        # Create debate workflow
        debate_workflow = kaizen.create_debate_workflow(
            agents=[proponent, opponent, moderator],
            topic="Should we invest heavily in renewable energy?",
            rounds=2,
        )

        # Real debate execution
        result = debate_workflow.execute()

        # Validate real debate coordination
        assert isinstance(result, dict), "Debate workflow should return dictionary"
        assert "final_decision" in result, "Result should contain final_decision"
        assert "debate_rounds" in result, "Result should contain debate_rounds"
        assert "consensus_level" in result, "Result should contain consensus_level"
        assert (
            "coordination_status" in result
        ), "Result should contain coordination_status"

        # Validate debate structure
        assert (
            len(result["debate_rounds"]) == 2
        ), "Should have 2 debate rounds as specified"
        assert (
            result["coordination_status"] == "successful"
        ), "Coordination should be successful"
        assert isinstance(
            result["consensus_level"], float
        ), "Consensus level should be float"
        assert (
            0.0 <= result["consensus_level"] <= 1.0
        ), "Consensus level should be between 0 and 1"

        # Validate participants
        assert result["participants"] == 3, "Should have 3 participants"
        assert result["rounds_completed"] == 2, "Should complete 2 rounds"

    def test_real_consensus_workflow_execution(self):
        """Real multi-agent consensus workflow execution."""
        kaizen = Kaizen(config={"multi_agent_enabled": True})

        # Create real agents for consensus
        experts = [
            kaizen.create_specialized_agent(
                "expert1", "Technical expert", {"model": "gpt-3.5-turbo"}
            ),
            kaizen.create_specialized_agent(
                "expert2", "Business expert", {"model": "gpt-3.5-turbo"}
            ),
            kaizen.create_specialized_agent(
                "expert3", "Risk expert", {"model": "gpt-3.5-turbo"}
            ),
        ]

        # Create consensus workflow
        consensus_workflow = kaizen.create_consensus_workflow(
            agents=experts,
            topic="AI implementation strategy",
            consensus_threshold=0.75,
            max_iterations=3,
        )

        # Real consensus execution
        result = consensus_workflow.execute()

        # Validate real consensus coordination
        assert isinstance(result, dict), "Consensus workflow should return dictionary"
        assert (
            "consensus_achieved" in result
        ), "Result should contain consensus_achieved"
        assert "final_consensus" in result, "Result should contain final_consensus"
        assert "consensus_score" in result, "Result should contain consensus_score"
        assert "agent_positions" in result, "Result should contain agent_positions"

        # Validate consensus structure
        assert isinstance(
            result["consensus_achieved"], bool
        ), "Consensus achieved should be boolean"
        assert isinstance(
            result["consensus_score"], float
        ), "Consensus score should be float"
        assert isinstance(
            result["agent_positions"], dict
        ), "Agent positions should be dictionary"
        assert len(result["agent_positions"]) <= len(
            experts
        ), "Should have positions from experts"


class TestRealWorldPerformanceRequirements:
    """
    Test performance requirements with real Core SDK execution.

    Validates that implementations meet performance criteria in real scenarios.
    """

    def test_signature_execution_real_performance(self):
        """Signature execution performance with real Core SDK."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        agent = kaizen.create_agent(
            "perf_test",
            {
                "model": "gpt-3.5-turbo",
                "signature": "question -> answer",
                "temperature": 0.1,
            },
        )

        # Measure real execution time
        start_time = time.time()
        result = agent.execute(question="What is 1+1?")
        execution_time = time.time() - start_time

        # Performance requirement: reasonable time for real LLM call
        assert (
            execution_time < 30.0
        ), f"Real execution took {execution_time:.3f}s, should be <30s"

        # Validate result quality
        assert isinstance(result, dict), "Should return structured result"
        assert "answer" in result, "Should contain answer field"
        assert len(str(result["answer"]).strip()) > 0, "Answer should not be empty"

    def test_pattern_execution_real_performance(self):
        """Pattern execution performance with real Core SDK."""
        kaizen = Kaizen(config={"signature_programming_enabled": True})

        cot_agent = kaizen.create_agent(
            "perf_cot",
            {
                "model": "gpt-3.5-turbo",
                "signature": "problem -> reasoning, answer",
                "temperature": 0.1,
            },
        )

        # Measure real pattern execution time
        start_time = time.time()
        result = cot_agent.execute_cot(problem="Calculate 5*6")
        execution_time = time.time() - start_time

        # Performance requirement: reasonable time for real pattern execution
        assert (
            execution_time < 45.0
        ), f"Real pattern execution took {execution_time:.3f}s, should be <45s"

        # Validate result quality
        assert isinstance(result, dict), "Should return structured result"
        assert "reasoning" in result, "Should contain reasoning field"
        assert "answer" in result, "Should contain answer field"

    def test_enterprise_workflow_real_performance(self):
        """Enterprise workflow performance with real Core SDK."""
        kaizen = Kaizen(
            config={
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "transparency_enabled": True,
            }
        )

        workflow = kaizen.create_enterprise_workflow(
            "approval",
            {"approval_levels": ["manager"], "audit_requirements": "standard"},
        )

        # Measure real workflow execution time
        start_time = time.time()
        result = workflow.execute({"request": "Test approval"})
        execution_time = time.time() - start_time

        # Performance requirement: reasonable time for enterprise workflow
        assert (
            execution_time < 60.0
        ), f"Real enterprise workflow took {execution_time:.3f}s, should be <60s"

        # Validate enterprise result quality
        assert isinstance(result, dict), "Should return structured result"
        assert "audit_trail" in result, "Should contain audit trail"
        assert len(result["audit_trail"]) > 0, "Audit trail should not be empty"


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v"])
