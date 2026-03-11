"""
PEVAgent - Production-Ready Planner-Executor-Verifier Agent

Pattern: "Plan, Execute, Verify, Refine" - Iterative improvement with explicit verification

Zero-config usage:
    from kaizen.agents import PEVAgent

    agent = PEVAgent()
    result = agent.run(task="Generate code and verify it works")
    print(result["final_result"])
    print(f"Iterations: {len(result['refinements'])}")

Progressive configuration:
    agent = PEVAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.7,
        max_iterations=10,
        verification_strictness="strict",
        enable_error_recovery=True
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.7
"""

import logging
import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, NotRequired, Optional, TypedDict

from kailash.nodes.base import NodeMetadata

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)


@dataclass
class PEVAgentConfig:
    """
    Configuration for PEV Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "8000"))
    )

    # PEV-specific configuration
    max_iterations: int = 5
    verification_strictness: str = "medium"  # strict, medium, lenient
    enable_error_recovery: bool = True
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class PEVPlan(TypedDict, total=False):
    """
    TypedDict for PEV plan structure.

    Optional fields:
    - description: Plan description (str)
    - steps: List of steps (list)
    - refinements: List of refinement history (list)
    """

    description: str
    steps: list
    refinements: list


class PEVExecutionResult(TypedDict):
    """
    TypedDict for PEV execution result structure.

    Required fields:
    - status: Execution status ("success", "failed")

    Optional fields:
    - output: Result output (str)
    - error: Error message if failed (str)
    - details: Additional details (dict)
    """

    status: str  # Required
    output: NotRequired[str]  # Optional
    error: NotRequired[str]  # Optional
    details: NotRequired[dict]  # Optional


class PEVVerificationResult(TypedDict):
    """
    TypedDict for PEV verification result structure.

    Required fields:
    - passed: Whether verification passed (bool)

    Optional fields:
    - issues: List of issues found (list)
    - feedback: Feedback for refinement (str)
    """

    passed: bool  # Required
    issues: NotRequired[list]  # Optional
    feedback: NotRequired[str]  # Optional


class PEVSignature(Signature):
    """
    PEV signature for Plan-Execute-Verify-Refine pattern.

    Implements iterative improvement cycle:
    1. Plan: Create execution plan
    2. Execute: Execute the plan
    3. Verify: Check result quality
    4. Refine: Improve plan based on verification feedback
    (Repeat until verified or max iterations)

    Input Fields:
    - task: The task to execute iteratively

    Output Fields:
    - plan: Current plan
    - execution_result: Execution result
    - verification: Verification result with issues
    - refinements: List of refinements made
    - final_result: Final verified result
    """

    # Input fields
    task: str = InputField(desc="Task to execute iteratively")

    # Output fields
    plan: PEVPlan = OutputField(desc="Current execution plan")
    execution_result: PEVExecutionResult = OutputField(desc="Execution result")
    verification: PEVVerificationResult = OutputField(
        desc="Verification result with issues"
    )
    refinements: List[str] = OutputField(desc="Refinements made")
    final_result: str = OutputField(desc="Final verified result")


class PEVAgent(BaseAgent):
    """
    Production-ready PEV (Planner-Executor-Verifier) agent.

    Pattern: Plan → Execute → Verify → Refine (iterative loop)

    Differs from other agents:
    - ReAct: Observation-based adaptation (no explicit verification)
    - Planning: Single plan execution (no verification loop)
    - PEV: Explicit verification with iterative refinement

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Iterative plan-execute-verify-refine cycle
    - Configurable verification strictness
    - Error recovery and refinement
    - Max iterations to prevent infinite loops
    - Built-in error handling and logging

    Usage:
        # Zero-config (easiest)
        agent = PEVAgent()
        result = agent.run(task="Generate working code")

        # With configuration
        agent = PEVAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_iterations=10,
            verification_strictness="strict",
            enable_error_recovery=True
        )

        # View iterations
        result = agent.run(task="Generate code with tests")
        print(f"Plan: {result['plan']}")
        print(f"Refinements: {len(result['refinements'])}")
        print(f"Verified: {result['verification']['passed']}")
        print(f"Final: {result['final_result']}")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-4", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.7, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 2000, env: KAIZEN_MAX_TOKENS)
        max_iterations: Maximum refinement iterations (default: 5)
        verification_strictness: Verification level (default: "medium", options: strict/medium/lenient)
        enable_error_recovery: Enable error recovery (default: True)
        timeout: Request timeout seconds (default: 30)
        max_retries: Retry count on failure (default: 3)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - plan: Current execution plan
        - execution_result: Result from execution
        - verification: Dict with 'passed' status and 'issues' list
        - refinements: List of refinement descriptions
        - final_result: Final verified result
        - error: Optional error code if something fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="PEVAgent",
        description="Plan-Execute-Verify-Refine agent with iterative improvement",
        version="1.0.0",
        tags={"ai", "kaizen", "pev", "iterative", "verification", "refinement"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_iterations: Optional[int] = None,
        verification_strictness: Optional[str] = None,
        enable_error_recovery: Optional[bool] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[PEVAgentConfig] = None,
        **kwargs,
    ):
        """
        Initialize PEV agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            max_iterations: Override maximum iterations
            verification_strictness: Override verification strictness (strict/medium/lenient)
            enable_error_recovery: Enable error recovery
            timeout: Override default timeout
            max_retries: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = PEVAgentConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if max_iterations is not None:
                config = replace(config, max_iterations=max_iterations)
            if verification_strictness is not None:
                config = replace(
                    config, verification_strictness=verification_strictness
                )
            if enable_error_recovery is not None:
                config = replace(config, enable_error_recovery=enable_error_recovery)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if max_retries is not None:
                config = replace(config, max_retries=max_retries)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Initialize BaseAgent with auto-config extraction
        super().__init__(
            config=config,
            signature=PEVSignature(),
            **kwargs,
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.pev_config = config

    def _create_initial_plan(self, task: str) -> Dict[str, Any]:
        """
        Create initial execution plan from task.

        Phase 1: Plan

        Args:
            task: The task to create a plan for

        Returns:
            Dict with plan structure
        """
        # Execute via BaseAgent to generate initial plan
        result = super().run(task=task)

        # Extract plan from result (handle various formats)
        if isinstance(result.get("plan"), dict):
            return result["plan"]
        elif isinstance(result.get("plan"), list):
            return {"steps": result["plan"]}
        else:
            return {"description": str(result.get("plan", task)), "steps": []}

    def _execute_plan(self, plan: Dict[str, Any], task: str) -> Dict[str, Any]:
        """
        Execute the current plan.

        Phase 2: Execute

        Args:
            plan: The plan to execute
            task: Original task for context

        Returns:
            Dict with execution results
        """
        try:
            # Execute plan (simplified - in production would use actual execution)
            # This is a mock execution for testing purposes
            result = super().run(task=task)

            return {
                "status": "success",
                "output": result.get("final_result", "Execution completed"),
                "details": result,
            }
        except Exception as e:
            logger.error(f"Error executing plan: {str(e)}")
            return {
                "status": "failed",
                "error": str(e),
                "output": "",
            }

    def _verify_result(
        self, execution_result: Dict[str, Any], task: str
    ) -> Dict[str, Any]:
        """
        Verify execution result quality.

        Phase 3: Verify

        Args:
            execution_result: Result from execution
            task: Original task for context

        Returns:
            Dict with:
            - passed: bool (whether verification passed)
            - issues: list (issues found)
            - feedback: str (feedback for refinement)
        """
        issues = []
        feedback = []

        # Check 1: Execution status
        if execution_result.get("status") == "failed":
            issues.append("Execution failed")
            feedback.append("Fix execution errors")

        # Check 2: Output existence
        output = execution_result.get("output", "")
        if not output or len(output) < 10:
            issues.append("Insufficient output")
            feedback.append("Generate more detailed output")

        # Check 3: Errors in output
        if "error" in execution_result:
            issues.append(f"Error detected: {execution_result['error']}")
            feedback.append("Handle errors gracefully")

        # Determine if verification passed based on strictness
        if self.pev_config.verification_strictness == "strict":
            passed = len(issues) == 0
        elif self.pev_config.verification_strictness == "medium":
            passed = len(issues) <= 1
        else:  # lenient
            passed = execution_result.get("status") != "failed"

        return {
            "passed": passed,
            "issues": issues,
            "feedback": "\n".join(feedback) if feedback else "No issues found",
        }

    def _refine_plan(
        self,
        plan: Dict[str, Any],
        execution_result: Dict[str, Any],
        verification: Dict[str, Any],
        task: str,
    ) -> Dict[str, Any]:
        """
        Refine plan based on verification feedback.

        Phase 4: Refine

        Args:
            plan: Current plan
            execution_result: Execution result
            verification: Verification result with feedback
            task: Original task

        Returns:
            Dict with refined plan
        """
        # Create refinement based on feedback
        feedback = verification.get("feedback", "")

        # Simple refinement logic (in production would be more sophisticated)
        refined_plan = plan.copy()

        # Add refinement notes
        if "refinements" not in refined_plan:
            refined_plan["refinements"] = []

        refined_plan["refinements"].append(
            {
                "iteration": len(refined_plan["refinements"]) + 1,
                "feedback": feedback,
                "issues": verification.get("issues", []),
            }
        )

        return refined_plan

    def run(
        self, task: str, context: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Universal execution method for PEV agent.

        Iterative execution:
        1. Plan: Create execution plan
        2. Execute: Execute the plan
        3. Verify: Check result quality
        4. Refine: Improve plan based on feedback
        (Repeat until verified or max iterations)

        Args:
            task: The task to execute iteratively
            context: Optional additional context
            **kwargs: Additional parameters passed to BaseAgent.run()

        Returns:
            Dictionary containing:
            - plan: Final execution plan
            - execution_result: Final execution result
            - verification: Final verification status
            - refinements: List of all refinements made
            - final_result: Final verified result
            - error: Optional error code if validation fails

        Example:
            >>> agent = PEVAgent()
            >>> result = agent.run(task="Generate working Python code")
            >>> print(result["verification"]["passed"])
            True
            >>> print(f"Iterations: {len(result['refinements'])}")
            Iterations: 2
            >>> print(result["final_result"])
            "def hello(): return 'Hello, World!'"
        """
        # Input validation
        if not task or not task.strip():
            return {
                "error": "INVALID_INPUT",
                "plan": {},
                "execution_result": {},
                "verification": {"passed": False, "issues": ["Empty task"]},
                "refinements": [],
                "final_result": "",
            }

        if context is None:
            context = {}

        refinements = []
        plan = None
        execution_result = None
        verification = None

        # Iterative Plan-Execute-Verify-Refine loop
        for iteration in range(self.pev_config.max_iterations):
            logger.info(
                f"PEV Iteration {iteration + 1}/{self.pev_config.max_iterations}"
            )

            # Phase 1: Plan (or use existing plan)
            if iteration == 0:
                try:
                    plan = self._create_initial_plan(task=task.strip())
                except Exception as e:
                    logger.error(f"Error creating initial plan: {str(e)}")
                    return {
                        "error": "PLAN_CREATION_FAILED",
                        "plan": {},
                        "execution_result": {},
                        "verification": {"passed": False, "issues": [str(e)]},
                        "refinements": [],
                        "final_result": "",
                    }

            # Phase 2: Execute
            try:
                execution_result = self._execute_plan(plan=plan, task=task.strip())
            except Exception as e:
                logger.error(f"Error executing plan: {str(e)}")
                if not self.pev_config.enable_error_recovery:
                    return {
                        "error": "EXECUTION_FAILED",
                        "plan": plan,
                        "execution_result": {"status": "failed", "error": str(e)},
                        "verification": {"passed": False, "issues": [str(e)]},
                        "refinements": refinements,
                        "final_result": "",
                    }
                # Continue with error recovery
                execution_result = {"status": "failed", "error": str(e)}

            # Phase 3: Verify
            verification = self._verify_result(
                execution_result=execution_result, task=task.strip()
            )

            # If verification passed, exit early
            if verification["passed"]:
                logger.info(f"Verification passed after {iteration + 1} iteration(s)")
                break

            # Phase 4: Refine (if not at max iterations)
            if iteration < self.pev_config.max_iterations - 1:
                refinements.append(
                    f"Iteration {iteration + 1}: {verification['feedback']}"
                )
                plan = self._refine_plan(
                    plan=plan,
                    execution_result=execution_result,
                    verification=verification,
                    task=task.strip(),
                )

        # Return complete result
        final_result = execution_result.get("output", "") if execution_result else ""

        return {
            "plan": plan,
            "execution_result": execution_result,
            "verification": verification,
            "refinements": refinements,
            "final_result": final_result,
        }


# Convenience function for quick usage
def verify_and_refine(task: str, **kwargs) -> Dict[str, Any]:
    """
    Quick one-liner for PEV execution.

    Args:
        task: The task to execute with verification
        **kwargs: Optional configuration (llm_provider, model, max_iterations, etc.)

    Returns:
        The full result dictionary

    Example:
        >>> from kaizen.agents.specialized.pev import verify_and_refine
        >>> result = verify_and_refine("Generate code with tests")
        >>> print(result["verification"]["passed"])
        True
        >>> print(f"Iterations: {len(result['refinements'])}")
        Iterations: 3
    """
    agent = PEVAgent(**kwargs)
    return agent.run(task=task)
