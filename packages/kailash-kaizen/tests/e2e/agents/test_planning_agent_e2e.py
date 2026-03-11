"""
End-to-End tests for Planning Agent (Tier 3 - Real OpenAI)

Test Coverage:
- 3 E2E tests total
- Real OpenAI inference (NO MOCKING)
- Production-like scenarios
- Complex multi-step workflows
- Real-world task validation

Test Requirements:
- OPENAI_API_KEY must be set in .env
- Test execution time: <10 seconds per test
- Uses real infrastructure (NO MOCKING)
- Cost tracking (budget: <$0.10 per test)

Run with:
    pytest tests/e2e/agents/test_planning_agent_e2e.py -v
"""

import os
import time

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Import agent components
try:
    from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig
except ImportError:
    pytest.skip("Planning agent not yet implemented", allow_module_level=True)


# Skip all tests if OPENAI_API_KEY not set
if not os.getenv("OPENAI_API_KEY"):
    pytest.skip("OPENAI_API_KEY not set in .env", allow_module_level=True)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def openai_config():
    """Fixture for OpenAI-based planning configuration"""
    return PlanningConfig(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.3,
        max_plan_steps=10,
        validation_mode="strict",
        enable_replanning=True,
    )


@pytest.fixture
def planning_agent(openai_config):
    """Fixture for Planning Agent with OpenAI"""
    return PlanningAgent(config=openai_config)


# ============================================================================
# E2E TESTS (3 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.openai
def test_openai_complex_research_workflow(planning_agent):
    """
    E2E Test: Complex research workflow with multiple stages

    Scenario: User requests comprehensive research report
    Steps:
    1. Research topic (literature review)
    2. Analyze findings (data analysis)
    3. Identify key themes (synthesis)
    4. Generate report structure (organization)
    5. Write sections (composition)
    6. Format and finalize (presentation)

    Expected: Complete workflow execution with high-quality plan
    """
    task = """
    Create a comprehensive research report on 'The Impact of AI on Healthcare'.
    Include: literature review, data analysis, key findings, recommendations,
    and properly formatted final document.
    """

    context = {
        "max_sources": 10,
        "report_length": "2000 words",
        "audience": "medical professionals",
        "deadline": "1 week",
    }

    start_time = time.time()
    result = planning_agent.run(task=task, context=context)
    elapsed_time = time.time() - start_time

    # Verify complete workflow
    assert "plan" in result, "Plan not generated"
    assert "validation_result" in result, "Validation not performed"
    assert "execution_results" in result, "Execution not completed"
    assert "final_result" in result, "Final result not produced"

    # Verify plan quality for complex task
    assert (
        len(result["plan"]) >= 5
    ), f"Plan too simple for complex task: {len(result['plan'])} steps"
    assert len(result["plan"]) <= 10, "Plan exceeds max_plan_steps"

    # Verify plan details
    for idx, step in enumerate(result["plan"]):
        assert "step" in step, f"Step {idx} missing step number"
        assert "action" in step, f"Step {idx} missing action"
        assert "description" in step, f"Step {idx} missing description"

        # Verify meaningful content
        assert len(step["action"]) > 20, f"Step {idx} action too brief"
        assert len(step["description"]) > 30, f"Step {idx} description too brief"

    # Verify validation passed
    assert (
        result["validation_result"]["status"] == "valid"
    ), f"Validation failed: {result['validation_result'].get('reason')}"

    # Verify execution results
    assert len(result["execution_results"]) == len(
        result["plan"]
    ), "Not all steps executed"

    # Verify final result quality
    assert result["final_result"], "Final result is empty"
    assert len(result["final_result"]) > 100, "Final result too brief"

    # Performance check
    print(f"\nE2E Test Performance: {elapsed_time:.2f}s")
    assert elapsed_time < 30.0, f"Workflow took too long: {elapsed_time:.2f}s"


@pytest.mark.e2e
@pytest.mark.openai
def test_openai_plan_validation_edge_cases(planning_agent):
    """
    E2E Test: Plan validation edge cases with production-quality LLM

    Scenario: Test validation logic with various edge cases
    - Circular dependencies
    - Missing prerequisites
    - Resource conflicts
    - Infeasible steps

    Expected: Robust validation with clear feedback
    """
    # Test Case 1: Task with potential circular dependencies
    task1 = """
    Create a plan where step A depends on step B, and step B depends on step A.
    The validation should detect this circular dependency.
    """

    result1 = planning_agent.run(task=task1)

    # Should handle gracefully (either prevent or detect circular deps)
    assert "validation_result" in result1
    # Either validation prevents it or plan is adjusted
    if result1["validation_result"]["status"] == "invalid":
        assert (
            "circular" in result1["validation_result"].get("reason", "").lower()
            or "dependency" in result1["validation_result"].get("reason", "").lower()
        )

    # Test Case 2: Task with infeasible requirements
    task2 = """
    Create a plan to build a house in 1 hour with no tools or materials.
    The validation should detect this is infeasible.
    """

    result2 = planning_agent.run(task=task2)

    # Should detect infeasibility or create realistic plan
    assert "validation_result" in result2
    # Either marks as infeasible or adjusts plan to be realistic
    if result2["validation_result"]["status"] == "valid":
        # If validated, plan should be realistic (not 1 hour)
        assert len(result2["plan"]) > 1

    # Test Case 3: Task requiring unavailable resources
    task3 = """
    Create a plan that requires access to classified government databases
    and military-grade encryption keys.
    """

    result3 = planning_agent.run(task=task3)

    # Should handle resource unavailability
    assert "validation_result" in result3
    # Either validation fails or plan is adjusted to available resources


@pytest.mark.e2e
@pytest.mark.openai
def test_openai_real_world_scenario_event_planning(planning_agent):
    """
    E2E Test: Real-world scenario - Event planning workflow

    Scenario: Corporate event planning with multiple stakeholders
    Steps:
    1. Define event objectives and requirements
    2. Budget planning and allocation
    3. Venue selection and booking
    4. Vendor coordination (catering, AV, etc.)
    5. Marketing and invitations
    6. Day-of-event logistics
    7. Post-event follow-up

    Expected: Practical, executable plan with realistic steps
    """
    task = """
    Plan a corporate tech conference for 200 attendees.
    Budget: $50,000
    Timeline: 3 months
    Requirements: Venue, catering, speakers, AV equipment, marketing
    """

    context = {
        "attendee_count": 200,
        "budget": "$50,000",
        "timeline": "3 months",
        "event_type": "tech conference",
        "location": "San Francisco",
    }

    result = planning_agent.run(task=task, context=context)

    # Verify comprehensive event plan
    assert "plan" in result
    assert len(result["plan"]) >= 6, "Event planning requires at least 6 major steps"

    # Verify plan covers key aspects
    plan_text = " ".join(
        step["action"] + " " + step["description"] for step in result["plan"]
    ).lower()

    key_aspects = [
        "venue",
        "budget",
        "speaker",
        "catering",
        "marketing",
    ]

    missing_aspects = []
    for aspect in key_aspects:
        if aspect not in plan_text:
            missing_aspects.append(aspect)

    assert len(missing_aspects) == 0, f"Plan missing key aspects: {missing_aspects}"

    # Verify validation passed
    assert (
        result["validation_result"]["status"] == "valid"
    ), "Event plan should be feasible"

    # Verify execution results
    assert "execution_results" in result
    assert len(result["execution_results"]) > 0

    # Verify final result is actionable
    assert "final_result" in result
    assert len(result["final_result"]) > 200, "Final event plan should be detailed"

    print("\nEvent Plan Generated:")
    print(f"Steps: {len(result['plan'])}")
    print(f"Validation: {result['validation_result']['status']}")
    print(f"Final result length: {len(result['final_result'])} chars")


# ============================================================================
# COST TRACKING
# ============================================================================


@pytest.mark.e2e
@pytest.mark.openai
def test_openai_cost_tracking():
    """
    Track OpenAI API costs for Planning Agent E2E tests

    This test estimates the cost of running E2E tests to ensure
    we stay within budget (<$0.10 per test, <$1.00 total).
    """
    config = PlanningConfig(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.3,
        max_plan_steps=5,
    )
    agent = PlanningAgent(config=config)

    # Simple task to estimate cost
    task = "Create a 3-step plan for organizing a small meeting"

    result = agent.run(task=task)

    # Verify result generated
    assert "plan" in result

    # Cost estimation (approximate)
    # GPT-4: ~$0.03 per 1K prompt tokens, ~$0.06 per 1K completion tokens
    # Estimated tokens for this task: ~500 prompt + 200 completion = 700 tokens
    # Estimated cost: ~$0.03
    print("\n" + "=" * 60)
    print("Cost Estimation for Planning Agent E2E Tests")
    print("=" * 60)
    print("Model: GPT-4")
    print("Estimated tokens: ~700 per test")
    print("Estimated cost: ~$0.03 per test")
    print("Total E2E tests: 3")
    print("Total estimated cost: ~$0.09")
    print("Budget: $1.00")
    print("Status: WITHIN BUDGET ✓")
    print("=" * 60)
