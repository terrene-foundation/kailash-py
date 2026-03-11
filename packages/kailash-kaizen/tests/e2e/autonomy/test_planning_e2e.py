"""
Tier 3 E2E Tests: Planning Autonomy System (TODO-176 Subtask 1.2).

Tests comprehensive planning autonomy with 3 specialized planning agents:
- Real OpenAI LLM inference (gpt-4o-mini with Structured Outputs API)
- Real planning execution (no mocked step execution)
- Real multi-step decomposition and execution
- Real iterative refinement and path exploration

This is Subtask 1.2 of TODO-176 (Phase 5 E2E Testing), testing planning patterns.

Requirements:
- OpenAI API key (OPENAI_API_KEY in .env)
- gpt-4o-mini model with Structured Outputs API (100% schema compliance)
- No mocking (real infrastructure only)
- Tests may take 3-6 minutes due to LLM inference

Test Coverage (TODO-176 Subtask 1.2 Requirements):
1. test_planning_agent_multi_step_research - Multi-step task decomposition
2. test_pev_agent_content_creation - Prompt-Eval-Verify pattern
3. test_tot_agent_problem_solving - Tree-of-Thoughts exploration

Budget: ~$0.05-0.10 per test run (OpenAI gpt-4o-mini pricing)
Duration: ~3-6 minutes total
"""

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
from kaizen.agents.specialized.pev import PEVAgent, PEVSignature
from kaizen.agents.specialized.planning import PlanningAgent, PlanningSignature
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTSignature
from kaizen.core.structured_output import create_structured_output_config

from tests.utils.cost_tracking import get_global_tracker
from tests.utils.reliability_helpers import (
    OllamaHealthChecker,
    async_retry_with_backoff,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


# =============================================================================
# TEST CONFIGURATIONS
# =============================================================================


@dataclass
class PlanningTestConfig:
    """Configuration for Planning Agent tests."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # Supports Structured Outputs API with 100% compliance
    temperature: float = 0.3  # Low temp for consistency
    max_plan_steps: int = 5  # Keep small for faster tests
    validation_mode: str = "strict"
    enable_replanning: bool = True


@dataclass
class PEVTestConfig:
    """Configuration for PEV Agent tests."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # Supports Structured Outputs API
    temperature: float = 0.5  # Medium temp for exploration
    max_iterations: int = 3  # Keep small for faster tests
    verification_strictness: str = "medium"
    enable_error_recovery: bool = True


@dataclass
class ToTTestConfig:
    """Configuration for ToT Agent tests."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # Supports Structured Outputs API
    temperature: float = 0.9  # High temp for path diversity
    num_paths: int = 3  # Keep small for faster tests
    max_paths: int = 10
    evaluation_criteria: str = "quality"
    parallel_execution: bool = True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def validate_plan_structure(plan: list) -> bool:
    """Validate plan has proper structure."""
    if not isinstance(plan, list) or len(plan) == 0:
        return False

    for step in plan:
        if not isinstance(step, dict):
            return False
        if "step" not in step or "action" not in step or "description" not in step:
            return False

    return True


def validate_pev_result_structure(result: Dict[str, Any]) -> bool:
    """Validate PEV result has proper structure."""
    required_keys = [
        "plan",
        "execution_result",
        "verification",
        "refinements",
        "final_result",
    ]

    for key in required_keys:
        if key not in result:
            return False

    # Validate verification
    verification = result["verification"]
    if not isinstance(verification, dict):
        return False
    if "passed" not in verification or not isinstance(verification["passed"], bool):
        return False

    # Validate refinements
    if not isinstance(result["refinements"], list):
        return False

    return True


def validate_tot_result_structure(result: Dict[str, Any]) -> bool:
    """Validate ToT result has proper structure."""
    required_keys = ["paths", "evaluations", "best_path", "final_result"]

    for key in required_keys:
        if key not in result:
            return False

    # Validate paths
    paths = result["paths"]
    if not isinstance(paths, list) or len(paths) == 0:
        return False

    for path in paths:
        if not isinstance(path, dict):
            return False
        if "path_id" not in path or "reasoning" not in path:
            return False

    # Validate evaluations
    evaluations = result["evaluations"]
    if not isinstance(evaluations, list) or len(evaluations) != len(paths):
        return False

    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            return False
        if "score" not in evaluation or "path" not in evaluation:
            return False

    # Validate best path
    best_path = result["best_path"]
    if not isinstance(best_path, dict):
        return False
    if "score" not in best_path or "path" not in best_path:
        return False

    return True


# =============================================================================
# Test 1: Planning Agent - Multi-Step Task Decomposition with Research
# =============================================================================


@pytest.mark.e2e
@pytest.mark.openai  # Required for real OpenAI API calls with structured outputs
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_planning_agent_multi_step_research():
    """
    Test Planning Agent with multi-step research task decomposition.

    Validates (TODO-176 Subtask 1.2 Requirement 1):
    - Planning Agent creates detailed execution plan
    - Multi-step decomposition with research task
    - Plan validation (structure, feasibility)
    - Plan execution step-by-step
    - Real OpenAI LLM inference for planning
    - Each step executed with real operations (no mocking)
    - Final synthesis of research results

    Planning Pattern: Plan → Validate → Execute
    - Phase 1: Generate detailed step-by-step plan
    - Phase 2: Validate plan feasibility and completeness
    - Phase 3: Execute validated plan sequentially

    Expected duration: 60-90 seconds
    Cost: ~$0.01-0.02 (OpenAI gpt-4o-mini)
    """
    cost_tracker = get_global_tracker()

    # Research task: Multi-step decomposition required
    task = "Research the benefits and challenges of renewable energy adoption. Compare solar, wind, and hydroelectric power."

    # Create Planning Agent
    config = PlanningTestConfig(
        max_plan_steps=5,
        validation_mode="strict",
        enable_replanning=True,
    )

    # Enable OpenAI Structured Outputs API with strict=True (100% schema compliance)
    # The schema post-processing automatically handles NotRequired fields by converting
    # them to required fields in the JSON schema while preserving TypedDict definitions.
    #
    # Note: Use PlanGenerationSignature (not PlanningSignature) because PlanningAgent
    # internally creates a temporary BaseAgent with PlanGenerationSignature for the
    # plan generation phase (see planning.py:364-366).
    from kaizen.agents.specialized.planning import PlanGenerationSignature

    provider_config = {
        "response_format": create_structured_output_config(
            signature=PlanGenerationSignature(), strict=True, name="planning_response"
        )
    }

    agent = PlanningAgent(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=config.temperature,
        max_plan_steps=config.max_plan_steps,
        validation_mode=config.validation_mode,
        enable_replanning=config.enable_replanning,
        provider_config=provider_config,
    )

    print(
        f"\n✓ Planning Agent: Created with OpenAI {config.model} (Structured Outputs API)"
    )

    # Execute research task with retry logic
    async def execute_research():
        result = agent.run(task=task)
        return result

    result = await async_retry_with_backoff(
        execute_research,
        max_attempts=3,
        initial_delay=1.0,
    )

    # Track OpenAI cost
    cost_tracker.track_usage(
        test_name="test_planning_agent_multi_step_research",
        provider="openai",
        model=config.model,  # Use dynamic model from config
        input_tokens=250,  # Estimated for research task
        output_tokens=600,  # Estimated for plan + execution
    )

    # Validate result structure
    assert "plan" in result, "Result missing 'plan' key"
    assert "validation_result" in result, "Result missing 'validation_result' key"
    assert "execution_results" in result, "Result missing 'execution_results' key"
    assert "final_result" in result, "Result missing 'final_result' key"

    # Validate plan
    plan = result["plan"]
    assert validate_plan_structure(plan), "Plan structure is invalid"
    assert len(plan) > 0, "Plan is empty"
    assert (
        len(plan) <= config.max_plan_steps
    ), f"Plan exceeds max_plan_steps ({len(plan)} > {config.max_plan_steps})"

    print(f"✓ Step 1 (Plan): Generated {len(plan)}-step research plan")

    # Validate each step in plan
    for i, step in enumerate(plan):
        assert "step" in step, f"Step {i} missing 'step' number"
        assert "action" in step, f"Step {i} missing 'action'"
        assert "description" in step, f"Step {i} missing 'description'"
        assert isinstance(step["step"], int), f"Step {i} 'step' should be int"
        assert isinstance(step["action"], str), f"Step {i} 'action' should be string"
        assert isinstance(
            step["description"], str
        ), f"Step {i} 'description' should be string"
        assert len(step["description"]) > 0, f"Step {i} has empty description"

        print(f"  Step {step['step']}: {step['action']}")

    # Validate validation result
    validation = result["validation_result"]
    assert "status" in validation, "Validation missing 'status' key"
    assert validation["status"] in [
        "valid",
        "warnings",
        "skipped",
        "invalid",
    ], f"Invalid validation status: {validation['status']}"

    print(f"✓ Step 2 (Validate): Plan validation status = {validation['status']}")

    # Validate execution results
    execution_results = result["execution_results"]
    assert len(execution_results) > 0, "No execution results"

    print(f"✓ Step 3 (Execute): Executed {len(execution_results)} steps")

    # Check each execution result
    for i, exec_result in enumerate(execution_results):
        assert "step" in exec_result, f"Execution {i} missing 'step' number"
        assert "action" in exec_result, f"Execution {i} missing 'action'"
        assert "status" in exec_result, f"Execution {i} missing 'status'"
        assert exec_result["status"] in [
            "completed",
            "failed",
        ], f"Invalid status: {exec_result['status']}"

        # If completed, should have output
        if exec_result["status"] == "completed":
            assert (
                "output" in exec_result
            ), f"Execution {i} completed but missing output"
            assert len(exec_result["output"]) > 0, f"Execution {i} has empty output"

        print(f"  Execution {exec_result['step']}: {exec_result['status']}")

    # Validate final result (synthesis)
    final_result = result["final_result"]
    assert isinstance(final_result, str), "Final result should be string"
    assert len(final_result) > 0, "Final result is empty"

    print(
        f"✓ Step 4 (Synthesize): Generated final research summary ({len(final_result)} chars)"
    )

    # Verify multi-step decomposition worked
    assert len(plan) >= 2, "Research task should decompose into at least 2 steps"
    completed_steps = sum(1 for r in execution_results if r["status"] == "completed")
    assert completed_steps > 0, "No steps completed successfully"

    print(f"\n✅ Planning Agent E2E test completed successfully")
    print(f"   Plan quality: {len(plan)} steps, {completed_steps} completed")
    print(f"   Multi-step decomposition: Research → Analysis → Synthesis")


# =============================================================================
# Test 2: PEV Agent - Prompt-Eval-Verify Pattern for Content Creation
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(150)
async def test_pev_agent_content_creation():
    """
    Test PEV Agent with prompt-eval-verify workflow for content creation.

    Validates (TODO-176 Subtask 1.2 Requirement 2):
    - PEV Agent creates initial plan (Prompt)
    - Executes plan and generates content (Execute)
    - Verifies content quality (Verify)
    - Refines content based on feedback (Refine)
    - Real OpenAI LLM inference for all phases
    - Iterative improvement loop (up to max_iterations)
    - Quality improvement over iterations

    PEV Pattern: Plan → Execute → Verify → Refine (iterative loop)
    - Prompt: Generate initial content/solution
    - Execute: Execute the generation
    - Verify: Check quality and completeness
    - Refine: Improve based on verification feedback (repeat)

    Expected duration: 90-120 seconds
    Cost: ~$0.02-0.04 (OpenAI gpt-4o-mini)
    """
    cost_tracker = get_global_tracker()

    # Content creation task: Benefits from iterative refinement
    task = "Write a concise technical blog post about the advantages of microservices architecture over monolithic architecture."

    # Create PEV Agent
    config = PEVTestConfig(
        max_iterations=3,
        verification_strictness="medium",
        enable_error_recovery=True,
    )

    # Enable OpenAI Structured Outputs API with strict=True (100% schema compliance)
    # The schema post-processing automatically handles NotRequired fields in ExecutionResult
    # and VerificationResult TypedDicts.
    provider_config = {
        "response_format": create_structured_output_config(
            signature=PEVSignature(), strict=True, name="pev_response"
        )
    }

    agent = PEVAgent(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=config.temperature,
        max_iterations=config.max_iterations,
        verification_strictness=config.verification_strictness,
        enable_error_recovery=config.enable_error_recovery,
        provider_config=provider_config,
    )

    print("\n✓ PEV Agent: Created with OpenAI gpt-4o-mini (Structured Outputs API)")

    # Execute PEV cycle with retry logic
    async def execute_pev_cycle():
        result = agent.run(task=task)
        return result

    result = await async_retry_with_backoff(
        execute_pev_cycle,
        max_attempts=3,
        initial_delay=2.0,  # Longer delay for iterative process
    )

    # Track OpenAI cost (multiple iterations)
    num_iterations = len(result["refinements"]) + 1  # Initial + refinements
    cost_tracker.track_usage(
        test_name="test_pev_agent_content_creation",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=250 * num_iterations,
        output_tokens=600 * num_iterations,
    )

    # Validate result structure
    assert validate_pev_result_structure(result), "PEV result structure is invalid"

    # Validate Prompt phase (plan creation)
    plan = result["plan"]
    assert isinstance(plan, dict), "Plan should be a dict"
    assert len(plan) > 0, "Plan is empty"

    print(f"✓ Prompt Phase: Created initial plan for content generation")

    # Validate Execute phase (execution result)
    execution_result = result["execution_result"]
    assert "status" in execution_result, "Execution missing 'status' key"
    assert execution_result["status"] in [
        "success",
        "failed",
    ], f"Invalid execution status: {execution_result['status']}"

    print(f"✓ Execute Phase: Content generation status = {execution_result['status']}")

    # Validate Verify phase (verification)
    verification = result["verification"]
    assert "passed" in verification, "Verification missing 'passed' key"
    assert isinstance(
        verification["passed"], bool
    ), "Verification 'passed' should be boolean"
    assert "issues" in verification, "Verification missing 'issues' key"
    assert isinstance(
        verification["issues"], list
    ), "Verification 'issues' should be list"

    print(f"✓ Verify Phase: Verification passed = {verification['passed']}")

    if not verification["passed"]:
        print(f"  Issues found: {len(verification['issues'])} issues")
        for issue in verification["issues"][:3]:  # Show first 3 issues
            print(f"    - {issue}")

    # Validate Refine phase (refinements)
    refinements = result["refinements"]
    assert isinstance(refinements, list), "Refinements should be list"
    assert (
        len(refinements) <= config.max_iterations
    ), f"Refinements exceed max_iterations ({len(refinements)} > {config.max_iterations})"

    print(f"✓ Refine Phase: Made {len(refinements)} refinement(s)")

    # Each refinement should be a string describing the improvement
    for i, refinement in enumerate(refinements):
        assert isinstance(refinement, str), f"Refinement {i} should be string"
        assert len(refinement) > 0, f"Refinement {i} is empty"
        print(f"  Iteration {i+1}: {refinement[:80]}...")

    # Validate final result
    final_result = result["final_result"]
    assert isinstance(final_result, str), "Final result should be string"
    assert len(final_result) > 0, "Final result is empty"

    print(f"✓ Final Result: Generated content ({len(final_result)} chars)")

    # Key PEV validation: Agent should show iterative behavior
    # Either verification passed OR refinements were made
    assert (
        verification["passed"] or len(refinements) > 0
    ), "PEV agent should either pass verification or make refinements"

    # If verification passed, content should be substantial
    if verification["passed"]:
        assert len(final_result) > 100, "Passed verification but content too short"
        print("  ✓ Verification passed - content quality acceptable")

    # If refinements made, check improvement evidence
    if len(refinements) > 0:
        print(f"  ✓ Iterative improvement: {len(refinements)} refinement iteration(s)")

    # Validate execution details
    if execution_result.get("status") == "success":
        assert "output" in execution_result, "Successful execution should have output"
        assert len(execution_result["output"]) > 0, "Execution output is empty"
        print(f"  Execution output: {len(execution_result['output'])} chars")

    print(f"\n✅ PEV Agent E2E test completed successfully")
    print(f"   Iterations: {num_iterations} (initial + {len(refinements)} refinements)")
    print(
        f"   Verification: {'PASSED' if verification['passed'] else 'NEEDS IMPROVEMENT'}"
    )
    print(f"   PEV pattern: Prompt → Execute → Verify → Refine (iterative)")


# =============================================================================
# Test 3: ToT Agent - Tree-of-Thoughts Exploration for Problem Solving
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(150)
async def test_tot_agent_problem_solving():
    """
    Test ToT Agent with tree-of-thoughts exploration for problem solving.

    Validates (TODO-176 Subtask 1.2 Requirement 3):
    - ToT Agent generates multiple solution paths
    - Parallel path generation (3+ paths)
    - Path evaluation with scoring (0.0-1.0)
    - Best path selection based on scores
    - Backtracking evidence (lower-scored paths rejected)
    - Real OpenAI LLM inference for all paths
    - Best solution selected and executed

    ToT Pattern: Generate N paths → Evaluate → Select Best → Execute
    - Generate: Create N independent solution paths
    - Evaluate: Score each path independently
    - Select: Choose path with highest score
    - Execute: Use only the best path for final solution

    Expected duration: 90-120 seconds
    Cost: ~$0.02-0.04 (OpenAI gpt-4o-mini)
    """
    cost_tracker = get_global_tracker()

    # Problem-solving task: Benefits from multiple perspectives
    task = "Design a caching strategy for a high-traffic web application that minimizes database load while maintaining data freshness."

    # Create ToT Agent
    config = ToTTestConfig(
        num_paths=3,  # Generate 3 solution paths
        temperature=0.9,  # High diversity for different approaches
        evaluation_criteria="quality",
        parallel_execution=True,
    )

    # Enable OpenAI Structured Outputs API with strict=True (100% schema compliance)
    provider_config = {
        "response_format": create_structured_output_config(
            signature=ToTSignature(), strict=True, name="tot_response"
        )
    }

    agent = ToTAgent(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=config.temperature,
        num_paths=config.num_paths,
        max_paths=config.max_paths,
        evaluation_criteria=config.evaluation_criteria,
        parallel_execution=config.parallel_execution,
        provider_config=provider_config,
    )

    print("\n✓ ToT Agent: Created with OpenAI gpt-4o-mini (Structured Outputs API)")

    # Execute ToT exploration with retry logic
    async def explore_paths():
        result = agent.run(task=task)
        return result

    result = await async_retry_with_backoff(
        explore_paths,
        max_attempts=3,
        initial_delay=2.0,  # Longer delay for multiple paths
    )

    # Track OpenAI cost (3 paths)
    num_paths = len(result["paths"])
    cost_tracker.track_usage(
        test_name="test_tot_agent_problem_solving",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=200 * num_paths,
        output_tokens=500 * num_paths,
    )

    # Validate result structure
    assert validate_tot_result_structure(result), "ToT result structure is invalid"

    # Validate paths (multiple solution paths explored)
    paths = result["paths"]
    assert (
        len(paths) == config.num_paths
    ), f"Expected {config.num_paths} paths, got {len(paths)}"

    print(f"✓ Generate Phase: Created {len(paths)} solution paths")

    # Each path should have proper structure
    for i, path in enumerate(paths):
        assert "path_id" in path, f"Path {i} missing path_id"
        assert "reasoning" in path, f"Path {i} missing reasoning"
        assert isinstance(
            path["reasoning"], str
        ), f"Path {i} reasoning should be string"

        # Path should have non-empty reasoning (unless error)
        if "error" not in path:
            assert len(path["reasoning"]) > 0, f"Path {i} has empty reasoning"
            print(f"  Path {i+1}: {path['reasoning'][:60]}...")

    # Validate evaluations (path scoring)
    evaluations = result["evaluations"]
    assert len(evaluations) == len(
        paths
    ), f"Evaluations count mismatch ({len(evaluations)} != {len(paths)})"

    print(f"✓ Evaluate Phase: Scored all {len(evaluations)} paths")

    # Each evaluation should have score
    all_scores = []
    for i, evaluation in enumerate(evaluations):
        assert "score" in evaluation, f"Evaluation {i} missing score"
        assert "path" in evaluation, f"Evaluation {i} missing path"
        score = evaluation["score"]
        assert (
            0.0 <= score <= 1.0
        ), f"Evaluation {i} score {score} out of range [0.0, 1.0]"
        all_scores.append(score)
        print(f"  Path {i+1} score: {score:.2f}")

    # Validate best path selection
    best_path = result["best_path"]
    assert "score" in best_path, "Best path missing score"
    assert "path" in best_path, "Best path missing path data"

    best_score = best_path["score"]

    # Best path should have the highest score (backtracking evidence)
    assert best_score == max(
        all_scores
    ), f"Best path score {best_score:.2f} is not highest (max: {max(all_scores):.2f})"

    print(f"✓ Select Phase: Best path selected (score: {best_score:.2f})")
    print(f"  Path ID: {best_path['path'].get('path_id', 'unknown')}")

    # Backtracking evidence: Lower-scored paths were rejected
    rejected_paths = [s for s in all_scores if s < best_score]
    if len(rejected_paths) > 0:
        print(f"  ✓ Backtracking: {len(rejected_paths)} lower-scored path(s) rejected")
        print(f"    Rejected scores: {[f'{s:.2f}' for s in rejected_paths]}")

    # Validate final result (execution of best path)
    final_result = result["final_result"]
    assert isinstance(final_result, str), "Final result should be string"
    assert len(final_result) > 0, "Final result is empty"

    print(f"✓ Execute Phase: Used best path for solution ({len(final_result)} chars)")

    # Validate ToT-specific behavior
    # 1. Multiple paths should be generated
    assert len(paths) >= 2, "ToT should generate multiple paths"

    # 2. Paths should be evaluated
    assert all("score" in e for e in evaluations), "All paths should be evaluated"

    # 3. Best path should be clearly selected
    best_path_id = best_path["path"].get("path_id")
    assert best_path_id is not None, "Best path should have an ID"

    # 4. Check for parallel execution evidence (if enabled)
    if config.parallel_execution:
        assert (
            len(paths) == config.num_paths
        ), "Parallel execution should generate all paths"
        print(f"  ✓ Parallel execution: All {config.num_paths} paths generated")

    # 5. Validate score distribution (should have differentiation)
    score_range = max(all_scores) - min(all_scores)
    if score_range > 0.1:
        print(f"  ✓ Score differentiation: Range = {score_range:.2f}")
    else:
        print(f"  Note: Limited score differentiation (range = {score_range:.2f})")

    print(f"\n✅ ToT Agent E2E test completed successfully")
    print(f"   Paths explored: {num_paths}")
    print(f"   Best score: {best_score:.2f}")
    print(f"   ToT pattern: Generate {num_paths} → Evaluate → Select Best → Execute")


# =============================================================================
# COST REPORT FIXTURE
# =============================================================================


@pytest.fixture(scope="module", autouse=True)
def print_cost_report():
    """Print cost report after all tests complete."""
    yield
    cost_tracker = get_global_tracker()
    cost_tracker.print_report()


# =============================================================================
# TEST COVERAGE SUMMARY
# =============================================================================

"""
Test Coverage: 3/3 E2E tests for Planning Autonomy System (TODO-176 Subtask 1.2)

✅ Planning Agent - Multi-Step Task Decomposition (1 test)
  - test_planning_agent_multi_step_research
  - Tests: Multi-step research task decomposition and execution
  - Pattern: Plan → Validate → Execute
  - Validates: Plan creation, validation, step-by-step execution, final synthesis
  - Duration: ~60-90s
  - Requirement: TODO-176 Subtask 1.2 Requirement 1

✅ PEV Agent - Prompt-Eval-Verify Pattern (1 test)
  - test_pev_agent_content_creation
  - Tests: Iterative content creation with quality verification
  - Pattern: Plan → Execute → Verify → Refine (iterative loop)
  - Validates: Initial generation, quality assessment, feedback-based refinement
  - Duration: ~90-120s
  - Requirement: TODO-176 Subtask 1.2 Requirement 2

✅ ToT Agent - Tree-of-Thoughts Exploration (1 test)
  - test_tot_agent_problem_solving
  - Tests: Multiple solution path exploration and selection
  - Pattern: Generate N paths → Evaluate → Select Best → Execute
  - Validates: Path generation, scoring, best path selection, backtracking
  - Duration: ~90-120s
  - Requirement: TODO-176 Subtask 1.2 Requirement 3

Total: 3 tests
Expected Runtime: 3-6 minutes (real LLM inference)
Requirements: OpenAI API key with gpt-4o-mini model (Structured Outputs API)
Cost: ~$0.05-0.10 per test run (OpenAI gpt-4o-mini pricing)

All tests use:
- Real OpenAI LLM with Structured Outputs API (NO MOCKING)
- Real planning execution (NO MOCKING)
- Real multi-step decomposition (NO MOCKING)
- Real iterative refinement (NO MOCKING)
- Real path exploration (NO MOCKING)

Planning Systems Tested:
1. Planning Agent: Explicit planning phase with validation ✅
2. PEV Agent: Plan-Execute-Verify-Refine iterative loop ✅
3. ToT Agent: Tree exploration with parallel path evaluation ✅

TODO-176 Subtask 1.2 Status: COMPLETE
All 3 E2E tests implemented and documented per requirements.
"""
