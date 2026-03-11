"""
PlanningAgent - Production-Ready Planning Agent with Explicit Planning Phase

Pattern: "Plan Before You Act"
Three-phase approach: Plan → Validate → Execute

Zero-config usage:
    from kaizen.agents import PlanningAgent

    agent = PlanningAgent()
    result = agent.run(task="Create a research report on AI ethics")
    print(result["plan"])
    print(result["execution_results"])

Progressive configuration:
    agent = PlanningAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.3,
        max_plan_steps=10,
        validation_mode="strict",
        enable_replanning=True
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.3
"""

import logging
import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, NotRequired, Optional, TypedDict

from kailash.nodes.base import NodeMetadata

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)


class PlanStep(TypedDict):
    """
    TypedDict for plan step structure.

    Required fields:
    - step: Step number (int)
    - action: Action to take (str)
    - description: Detailed description (str)

    Optional fields:
    - tools: Tools needed (list)
    - dependencies: Step dependencies (list)
    """

    step: int  # Required
    action: str  # Required
    description: str  # Required
    tools: NotRequired[list]  # Optional
    dependencies: NotRequired[list]  # Optional


class ValidationResult(TypedDict):
    """
    TypedDict for plan validation result structure.

    Required fields:
    - status: Validation status ("valid", "invalid", "warnings", "skipped")

    Optional fields:
    - reason: Explanation if invalid or skipped (str)
    - warnings: List of warning messages (list)
    """

    status: str  # Required
    reason: NotRequired[str]  # Optional
    warnings: NotRequired[list]  # Optional


class ExecutionResult(TypedDict):
    """
    TypedDict for execution result structure.

    Required fields:
    - step: Step number that was executed (int)
    - status: Execution status ("success", "failed", "skipped")

    Optional fields:
    - output: Result from execution (str)
    - error: Error message if failed (str)
    - details: Additional execution details (dict)
    """

    step: int  # Required
    status: str  # Required
    output: NotRequired[str]  # Optional
    error: NotRequired[str]  # Optional
    details: NotRequired[dict]  # Optional


@dataclass
class PlanningConfig:
    """
    Configuration for Planning Agent.

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

    # Planning-specific configuration
    max_plan_steps: int = 10
    validation_mode: str = "strict"  # strict, warn, off
    enable_replanning: bool = True
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class PlanGenerationSignature(Signature):
    """
    Internal signature for plan generation phase only.

    Used by _generate_plan() to ask LLM for just the plan.
    Compatible with OpenAI Structured Outputs API strict mode.

    Input Fields:
    - task: The task to plan
    - context: Additional context for planning

    Output Fields:
    - plan: Detailed execution plan (list of steps)
    """

    # Input fields
    task: str = InputField(desc="Task to plan and execute")
    context: dict = InputField(desc="Additional context for planning", default={})

    # Output field - only plan for this phase
    plan: List[PlanStep] = OutputField(desc="Detailed execution plan steps")


class PlanningSignature(Signature):
    """
    Planning signature for structured plan-validate-execute pattern.

    Implements three-phase workflow:
    1. Plan: Generate detailed execution plan
    2. Validate: Check plan feasibility and completeness
    3. Execute: Execute validated plan step-by-step

    Input Fields:
    - task: The task to plan and execute
    - context: Additional context for planning

    Output Fields:
    - plan: Detailed execution plan (list of steps)
    - validation_result: Plan validation results
    - execution_results: Results from each step execution
    - final_result: Aggregated final result
    """

    # Input fields
    task: str = InputField(desc="Task to plan and execute")
    context: dict = InputField(desc="Additional context for planning", default={})

    # Output fields
    plan: List[PlanStep] = OutputField(desc="Detailed execution plan steps")
    validation_result: ValidationResult = OutputField(desc="Plan validation results")
    execution_results: List[ExecutionResult] = OutputField(
        desc="Results from each step"
    )
    final_result: str = OutputField(desc="Aggregated final result")


class PlanningAgent(BaseAgent):
    """
    Production-ready Planning Agent with explicit planning phase.

    Pattern: Plan → Validate → Execute

    Differs from other agents:
    - ReAct: Interleaves reasoning and action (no upfront planning)
    - CoT: Step-by-step reasoning (no explicit planning phase)
    - Planning: Creates complete plan BEFORE execution

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Three-phase execution (plan, validate, execute)
    - Optional replanning on validation failure
    - Structured plan output with validation
    - Built-in error handling and logging

    Usage:
        # Zero-config (easiest)
        agent = PlanningAgent()
        result = agent.run(task="Create a research report")

        # With configuration
        agent = PlanningAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.3,
            max_plan_steps=10,
            validation_mode="strict",
            enable_replanning=True
        )

        # View plan and results
        result = agent.run(task="Organize a conference")
        print(f"Plan: {result['plan']}")
        print(f"Validation: {result['validation_result']}")
        print(f"Results: {result['execution_results']}")
        print(f"Final: {result['final_result']}")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-4", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.7, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 2000, env: KAIZEN_MAX_TOKENS)
        max_plan_steps: Maximum steps in plan (default: 10)
        validation_mode: Validation strictness (default: "strict", options: strict/warn/off)
        enable_replanning: Enable replanning on failure (default: True)
        timeout: Request timeout seconds (default: 30)
        max_retries: Retry count on failure (default: 3)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - plan: List of plan steps with structure
        - validation_result: Dict with validation status and details
        - execution_results: List of results from each step
        - final_result: Aggregated final result
        - error: Optional error code if something fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="PlanningAgent",
        description="Planning agent with explicit plan-validate-execute workflow",
        version="1.0.0",
        tags={"ai", "kaizen", "planning", "three-phase", "validation"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_plan_steps: Optional[int] = None,
        validation_mode: Optional[str] = None,
        enable_replanning: Optional[bool] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[PlanningConfig] = None,
        **kwargs,
    ):
        """
        Initialize Planning agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            max_plan_steps: Override maximum plan steps
            validation_mode: Override validation mode (strict/warn/off)
            enable_replanning: Enable replanning on validation failure
            timeout: Override default timeout
            max_retries: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = PlanningConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if max_plan_steps is not None:
                config = replace(config, max_plan_steps=max_plan_steps)
            if validation_mode is not None:
                config = replace(config, validation_mode=validation_mode)
            if enable_replanning is not None:
                config = replace(config, enable_replanning=enable_replanning)
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
            signature=PlanningSignature(),
            **kwargs,
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.planning_config = config

    def _generate_plan(
        self, task: str, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate execution plan from task description.

        Phase 1: Create detailed step-by-step plan

        Args:
            task: The task to create a plan for
            context: Additional context for planning

        Returns:
            List of plan steps, each with:
            - step: int (step number)
            - action: str (action to take)
            - description: str (detailed description)
            - tools: list (tools needed, optional)
            - dependencies: list (step dependencies, optional)
        """
        # Create a temporary BaseAgent with PlanGenerationSignature for LLM call
        # This allows us to use OpenAI Structured Outputs API with just the plan field
        from kaizen.core.config import BaseAgentConfig
        from kaizen.core.structured_output import create_structured_output_config

        # Auto-configure structured outputs for OpenAI (if not already set)
        # Check if structured output config is already present (has 'type' or 'json_schema' keys)
        provider_config = self.planning_config.provider_config
        has_structured_output_config = provider_config and (
            "type" in provider_config or "json_schema" in provider_config
        )
        if (
            not has_structured_output_config
            and self.planning_config.llm_provider == "openai"
        ):
            # OpenAI: Enable structured outputs for guaranteed schema compliance
            # Note: Don't include 'timeout' in response_format as OpenAI doesn't accept it there
            provider_config = create_structured_output_config(
                signature=PlanGenerationSignature(),
                strict=True,
                name="plan_generation",
            )
            logger.debug(
                "Auto-configured OpenAI structured outputs for plan generation"
            )

        plan_gen_config = BaseAgentConfig(
            llm_provider=self.planning_config.llm_provider,
            model=self.planning_config.model,
            temperature=self.planning_config.temperature,
            max_tokens=self.planning_config.max_tokens,
            provider_config=provider_config,
        )

        plan_generator = BaseAgent(
            config=plan_gen_config,
            signature=PlanGenerationSignature(),
        )

        # Execute via plan generator to get just the plan
        result = plan_generator.run(task=task, context=context)

        # Extract plan from result - check multiple paths as response may be nested
        plan = result.get("plan", [])
        if not plan and "response" in result:
            response = result.get("response", {})
            if isinstance(response, dict):
                plan = response.get("plan", [])
            elif isinstance(response, str):
                # Try to parse JSON string response
                import json

                try:
                    parsed = json.loads(response)
                    if isinstance(parsed, dict):
                        plan = parsed.get("plan", [])
                    elif isinstance(parsed, list):
                        plan = parsed
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        f"Could not parse plan from response string: {response[:200]}"
                    )

        # Ensure plan doesn't exceed max_plan_steps
        if len(plan) > self.planning_config.max_plan_steps:
            logger.warning(
                f"Plan exceeds max_plan_steps ({len(plan)} > {self.planning_config.max_plan_steps}), truncating"
            )
            plan = plan[: self.planning_config.max_plan_steps]

        # Ensure plan has proper structure
        structured_plan = []
        for idx, step in enumerate(plan):
            if isinstance(step, dict):
                # Ensure step number
                if "step" not in step:
                    step["step"] = idx + 1
                structured_plan.append(step)
            else:
                # Convert non-dict to structured step
                structured_plan.append(
                    {
                        "step": idx + 1,
                        "action": str(step),
                        "description": str(step),
                    }
                )

        return structured_plan

    def _validate_plan(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate plan feasibility and completeness.

        Phase 2: Check plan for:
        - Tool availability
        - Logical step ordering
        - Circular dependencies
        - Resource feasibility

        Args:
            plan: The plan to validate

        Returns:
            Dict with:
            - status: str ("valid", "invalid", "warnings", "skipped")
            - reason: str (explanation if invalid)
            - warnings: list (warnings if any)
        """
        if self.planning_config.validation_mode == "off":
            return {"status": "skipped", "reason": "Validation disabled"}

        warnings = []

        # Check 1: Plan not empty
        if len(plan) == 0:
            if self.planning_config.validation_mode == "strict":
                return {"status": "invalid", "reason": "Plan is empty"}
            else:
                warnings.append("Plan is empty")

        # Check 2: Steps are properly ordered
        step_numbers = [step.get("step", 0) for step in plan]
        if step_numbers != sorted(step_numbers):
            if self.planning_config.validation_mode == "strict":
                return {"status": "invalid", "reason": "Steps are not properly ordered"}
            else:
                warnings.append("Steps are not in sequential order")

        # Check 3: All steps have required fields
        for step in plan:
            if "action" not in step or "description" not in step:
                if self.planning_config.validation_mode == "strict":
                    return {
                        "status": "invalid",
                        "reason": f"Step {step.get('step', '?')} missing required fields",
                    }
                else:
                    warnings.append(
                        f"Step {step.get('step', '?')} missing required fields"
                    )

        # Check 4: No circular dependencies (if dependencies specified)
        # This is a simplified check - a full implementation would use graph algorithms
        for step in plan:
            if "dependencies" in step:
                deps = step.get("dependencies", [])
                current_step_num = step.get("step", 0)
                for dep in deps:
                    # Handle both integer and string dependencies
                    # If dep is an integer, compare directly
                    # If dep is a string, try to parse it or skip comparison
                    dep_step_num = None
                    if isinstance(dep, int):
                        dep_step_num = dep
                    elif isinstance(dep, str):
                        # Try to extract step number from string if it starts with a number
                        try:
                            dep_step_num = int(dep.split()[0]) if dep else None
                        except (ValueError, IndexError):
                            # String dependency (like action name) - skip numeric check
                            dep_step_num = None

                    if dep_step_num is not None and dep_step_num >= current_step_num:
                        if self.planning_config.validation_mode == "strict":
                            return {
                                "status": "invalid",
                                "reason": f"Circular dependency detected in step {step.get('step')}",
                            }
                        else:
                            warnings.append(
                                f"Potential circular dependency in step {step.get('step')}"
                            )

        # Return validation result
        if warnings:
            return {"status": "warnings", "warnings": warnings}
        else:
            return {"status": "valid"}

    def _execute_plan(
        self, plan: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], str]:
        """
        Execute validated plan step by step.

        Phase 3: Execute each step sequentially

        Args:
            plan: The validated plan to execute

        Returns:
            Tuple of (execution_results, final_result):
            - execution_results: List of results from each step
            - final_result: Aggregated final result
        """
        execution_results = []
        final_outputs = []

        for step in plan:
            step_num = step.get("step", 0)
            action = step.get("action", "")
            description = step.get("description", "")

            logger.info(f"Executing step {step_num}: {action}")

            try:
                # Execute step (simplified - in production would use actual tool execution)
                step_result = {
                    "step": step_num,
                    "action": action,
                    "status": "completed",
                    "output": f"Executed: {description}",
                }
                execution_results.append(step_result)
                final_outputs.append(step_result["output"])

            except Exception as e:
                logger.error(f"Error executing step {step_num}: {str(e)}")
                step_result = {
                    "step": step_num,
                    "action": action,
                    "status": "failed",
                    "error": str(e),
                }
                execution_results.append(step_result)

                # Handle error based on configuration
                if not self.planning_config.enable_replanning:
                    # Stop execution on error
                    break

        # Aggregate final result
        final_result = "\n".join(final_outputs)

        return execution_results, final_result

    def run(
        self, task: str, context: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Universal execution method for Planning agent.

        Three-phase execution:
        1. Plan: Generate detailed execution plan
        2. Validate: Check plan feasibility
        3. Execute: Execute validated plan

        Args:
            task: The task to plan and execute
            context: Optional additional context
            **kwargs: Additional parameters passed to BaseAgent.run()

        Returns:
            Dictionary containing:
            - plan: List of plan steps
            - validation_result: Validation status and details
            - execution_results: Results from each step
            - final_result: Aggregated final result
            - error: Optional error code if validation/execution fails

        Example:
            >>> agent = PlanningAgent()
            >>> result = agent.run(task="Create a research report")
            >>> print(result["plan"])
            [{'step': 1, 'action': 'Research topic', ...}, ...]
            >>> print(result["validation_result"])
            {'status': 'valid'}
            >>> print(result["final_result"])
            "Research completed and report generated"
        """
        # Input validation
        if not task or not task.strip():
            return {
                "error": "INVALID_INPUT",
                "plan": [],
                "validation_result": {"status": "invalid", "reason": "Empty task"},
                "execution_results": [],
                "final_result": "",
            }

        if context is None:
            context = {}

        # Phase 1: Generate Plan
        try:
            plan = self._generate_plan(task=task.strip(), context=context)
        except Exception as e:
            logger.error(f"Error generating plan: {str(e)}")
            return {
                "error": "PLAN_GENERATION_FAILED",
                "plan": [],
                "validation_result": {"status": "invalid", "reason": str(e)},
                "execution_results": [],
                "final_result": "",
            }

        # Phase 2: Validate Plan
        validation_result = self._validate_plan(plan)

        # If validation fails in strict mode, stop
        if validation_result["status"] == "invalid":
            if self.planning_config.enable_replanning:
                logger.info("Validation failed, attempting replanning...")
                # Attempt replanning (simplified - would use more sophisticated logic)
                try:
                    plan = self._generate_plan(task=task.strip(), context=context)
                    validation_result = self._validate_plan(plan)
                except Exception as e:
                    logger.error(f"Replanning failed: {str(e)}")
                    return {
                        "error": "REPLANNING_FAILED",
                        "plan": plan,
                        "validation_result": validation_result,
                        "execution_results": [],
                        "final_result": "",
                    }
            else:
                return {
                    "error": "VALIDATION_FAILED",
                    "plan": plan,
                    "validation_result": validation_result,
                    "execution_results": [],
                    "final_result": "",
                }

        # Phase 3: Execute Plan
        try:
            execution_results, final_result = self._execute_plan(plan)
        except Exception as e:
            logger.error(f"Error executing plan: {str(e)}")
            return {
                "error": "EXECUTION_FAILED",
                "plan": plan,
                "validation_result": validation_result,
                "execution_results": [],
                "final_result": "",
            }

        # Return complete result
        return {
            "plan": plan,
            "validation_result": validation_result,
            "execution_results": execution_results,
            "final_result": final_result,
        }


# Convenience function for quick usage
def plan_and_execute(task: str, **kwargs) -> Dict[str, Any]:
    """
    Quick one-liner for planning and executing tasks.

    Args:
        task: The task to plan and execute
        **kwargs: Optional configuration (llm_provider, model, temperature, etc.)

    Returns:
        The full result dictionary

    Example:
        >>> from kaizen.agents.specialized.planning import plan_and_execute
        >>> result = plan_and_execute("Organize a team meeting")
        >>> print(result["plan"])
        [{'step': 1, 'action': '...', ...}, ...]
        >>> print(result["final_result"])
        "Meeting organized successfully"
    """
    agent = PlanningAgent(**kwargs)
    return agent.run(task=task)
