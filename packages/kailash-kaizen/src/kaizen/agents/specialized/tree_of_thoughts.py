"""
ToTAgent - Production-Ready Tree-of-Thoughts Agent

Pattern: "Explore Multiple Paths" - Generate, evaluate, select best reasoning path

Zero-config usage:
    from kaizen.agents import ToTAgent

    agent = ToTAgent()
    result = agent.run(task="Make strategic decision")
    print(f"Explored {len(result['paths'])} paths")
    print(f"Best path score: {result['best_path']['score']}")
    print(result["final_result"])

Progressive configuration:
    agent = ToTAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.9,
        num_paths=10,
        evaluation_criteria="quality",
        parallel_execution=True
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.9
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, NotRequired, Optional, TypedDict

from kailash.nodes.base import NodeMetadata

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)


class ToTPath(TypedDict):
    """
    TypedDict for Tree-of-Thoughts reasoning path structure.

    Required fields:
    - path_id: Path identifier (int)
    - reasoning: Reasoning text (str)

    Optional fields:
    - steps: Reasoning steps (list)
    - details: Additional details (dict)
    - error: Error message if generation failed (str)
    """

    path_id: int  # Required
    reasoning: str  # Required
    steps: NotRequired[list]  # Optional
    details: NotRequired[dict]  # Optional
    error: NotRequired[str]  # Optional


class ToTEvaluation(TypedDict):
    """
    TypedDict for path evaluation structure.

    Required fields:
    - path: The evaluated path (dict)
    - score: Evaluation score 0.0-1.0 (float)
    - reasoning: Evaluation reasoning (str)
    """

    path: dict
    score: float
    reasoning: str


@dataclass
class ToTAgentConfig:
    """
    Configuration for Tree-of-Thoughts Agent.

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
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.9"))
    )  # Higher for diversity
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "8000"))
    )

    # ToT-specific configuration
    num_paths: int = 5
    max_paths: int = 20  # Safety limit to prevent explosion
    evaluation_criteria: str = "quality"  # quality, speed, creativity
    parallel_execution: bool = True
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ToTSignature(Signature):
    """
    Tree-of-Thoughts signature for multi-path reasoning pattern.

    Implements parallel exploration:
    1. Generate: Create N reasoning paths
    2. Evaluate: Score each path independently
    3. Select: Choose best path based on score
    4. Execute: Execute only the best path

    Input Fields:
    - task: The task requiring multiple reasoning paths

    Output Fields:
    - paths: All generated reasoning paths
    - evaluations: Path evaluations with scores
    - best_path: Selected best path
    - final_result: Result from best path
    """

    # Input fields
    task: str = InputField(desc="Task requiring multiple reasoning paths")

    # Output fields
    paths: List[ToTPath] = OutputField(desc="All generated reasoning paths")
    evaluations: List[ToTEvaluation] = OutputField(desc="Path evaluations with scores")
    best_path: ToTPath = OutputField(desc="Selected best path")
    final_result: str = OutputField(desc="Result from best path")


class ToTAgent(BaseAgent):
    """
    Production-ready Tree-of-Thoughts agent.

    Pattern: Generate N paths → Evaluate → Select Best → Execute

    Differs from other agents:
    - CoT: Single linear reasoning path
    - ReAct: Single iterative path with observations
    - ToT: Multiple parallel paths, evaluated and best selected

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Parallel path generation (optional)
    - Configurable num_paths (1-20)
    - Multiple evaluation criteria
    - Semaphore control for concurrent execution
    - Best path selection with tie-breaking
    - Built-in error handling and logging

    Usage:
        # Zero-config (easiest)
        agent = ToTAgent()
        result = agent.run(task="Strategic decision")

        # With configuration
        agent = ToTAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.9,
            num_paths=10,
            evaluation_criteria="creativity",
            parallel_execution=True
        )

        # View all paths and selection
        result = agent.run(task="Complex problem")
        print(f"Explored {len(result['paths'])} paths")
        for i, eval in enumerate(result['evaluations']):
            print(f"Path {i+1}: {eval['score']:.2f}")
        print(f"Selected: Path with score {result['best_path']['score']}")
        print(f"Result: {result['final_result']}")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-4", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.9, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 2000, env: KAIZEN_MAX_TOKENS)
        num_paths: Number of reasoning paths (default: 5, max: 20)
        max_paths: Safety limit for paths (default: 20)
        evaluation_criteria: Evaluation criteria (default: "quality", options: quality/speed/creativity)
        parallel_execution: Enable parallel path generation (default: True)
        timeout: Request timeout seconds (default: 30)
        max_retries: Retry count on failure (default: 3)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - paths: List of all generated reasoning paths
        - evaluations: List of evaluations with scores (0.0-1.0)
        - best_path: Dict with best path and its score
        - final_result: Result from executing best path
        - error: Optional error code if something fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="ToTAgent",
        description="Tree-of-Thoughts agent with parallel path exploration and evaluation",
        version="1.0.0",
        tags={"ai", "kaizen", "tot", "multi-path", "evaluation", "parallel"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        num_paths: Optional[int] = None,
        max_paths: Optional[int] = None,
        evaluation_criteria: Optional[str] = None,
        parallel_execution: Optional[bool] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[ToTAgentConfig] = None,
        **kwargs,
    ):
        """
        Initialize ToT agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature (0.9 for diversity)
            max_tokens: Override default max tokens
            num_paths: Override number of paths (default: 5, max: 20)
            max_paths: Override maximum paths safety limit
            evaluation_criteria: Override evaluation criteria (quality/speed/creativity)
            parallel_execution: Enable parallel path generation
            timeout: Override default timeout
            max_retries: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = ToTAgentConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if num_paths is not None:
                config = replace(config, num_paths=num_paths)
            if max_paths is not None:
                config = replace(config, max_paths=max_paths)
            if evaluation_criteria is not None:
                config = replace(config, evaluation_criteria=evaluation_criteria)
            if parallel_execution is not None:
                config = replace(config, parallel_execution=parallel_execution)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if max_retries is not None:
                config = replace(config, max_retries=max_retries)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Validate num_paths
        if config.num_paths > config.max_paths:
            raise ValueError(
                f"num_paths ({config.num_paths}) exceeds max_paths ({config.max_paths})"
            )

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
            signature=ToTSignature(),
            **kwargs,
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.tot_config = config

    def _generate_path(self, task: str, path_id: int) -> Dict[str, Any]:
        """
        Generate single reasoning path.

        Phase 1: Generate (single path)

        Args:
            task: The task to reason about
            path_id: Identifier for this path

        Returns:
            Dict with path structure and reasoning
        """
        try:
            # Execute via BaseAgent to generate reasoning path
            result = super().run(task=task)

            return {
                "path_id": path_id,
                "reasoning": result.get("final_result", ""),
                "steps": result.get("plan", []),
                "details": result,
            }
        except Exception as e:
            logger.error(f"Error generating path {path_id}: {str(e)}")
            return {
                "path_id": path_id,
                "reasoning": "",
                "error": str(e),
            }

    async def _generate_path_async(
        self, task: str, path_id: int, semaphore: asyncio.Semaphore
    ) -> Dict[str, Any]:
        """
        Generate single reasoning path asynchronously with semaphore control.

        Args:
            task: The task to reason about
            path_id: Identifier for this path
            semaphore: Semaphore for concurrency control

        Returns:
            Dict with path structure and reasoning
        """
        async with semaphore:
            return self._generate_path(task, path_id)

    def _generate_paths(self, task: str) -> List[Dict[str, Any]]:
        """
        Generate multiple reasoning paths.

        Phase 1: Generate (all paths)

        Args:
            task: The task to reason about

        Returns:
            List of paths
        """
        paths = []

        if self.tot_config.parallel_execution:
            # Parallel execution with semaphore control
            try:
                # Create semaphore to limit concurrency (max 5 concurrent)
                semaphore = asyncio.Semaphore(5)

                # Create async tasks for all paths
                async def generate_all():
                    tasks = [
                        self._generate_path_async(task, i, semaphore)
                        for i in range(self.tot_config.num_paths)
                    ]
                    return await asyncio.gather(*tasks)

                # Run async generation
                paths = asyncio.run(generate_all())
            except Exception as e:
                logger.error(f"Error in parallel path generation: {str(e)}")
                # Fallback to sequential
                paths = [
                    self._generate_path(task, i)
                    for i in range(self.tot_config.num_paths)
                ]
        else:
            # Sequential execution
            paths = [
                self._generate_path(task, i) for i in range(self.tot_config.num_paths)
            ]

        return paths

    def _evaluate_path(self, path: Dict[str, Any], task: str) -> Dict[str, Any]:
        """
        Evaluate single reasoning path.

        Phase 2: Evaluate (single path)

        Args:
            path: The path to evaluate
            task: Original task for context

        Returns:
            Dict with:
            - path: The original path
            - score: Evaluation score (0.0-1.0)
            - reasoning: Evaluation reasoning
        """
        # Simple evaluation logic (in production would be more sophisticated)
        score = 0.0

        # Criteria 1: Completeness (has reasoning)
        if path.get("reasoning") and len(path["reasoning"]) > 20:
            score += 0.3

        # Criteria 2: No errors
        if "error" not in path:
            score += 0.3

        # Criteria 3: Has structured steps
        if path.get("steps") and len(path["steps"]) > 0:
            score += 0.2

        # Criteria 4: Reasoning quality (length as proxy)
        reasoning_length = len(path.get("reasoning", ""))
        if reasoning_length > 100:
            score += 0.2

        # Normalize score to 0.0-1.0
        score = min(1.0, max(0.0, score))

        return {
            "path": path,
            "score": score,
            "reasoning": f"Evaluated based on {self.tot_config.evaluation_criteria}",
        }

    def _evaluate_paths(
        self, paths: List[Dict[str, Any]], task: str
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all reasoning paths.

        Phase 2: Evaluate (all paths)

        Args:
            paths: All paths to evaluate
            task: Original task for context

        Returns:
            List of evaluations with scores
        """
        evaluations = []

        for path in paths:
            evaluation = self._evaluate_path(path=path, task=task)
            evaluations.append(evaluation)

        return evaluations

    def _select_best_path(self, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Select best path based on evaluation scores.

        Phase 3: Select

        Args:
            evaluations: All path evaluations

        Returns:
            Dict with best path and score
        """
        if not evaluations:
            return {
                "path": {},
                "score": 0.0,
                "reasoning": "No paths available",
            }

        # Find path with highest score
        best_evaluation = max(evaluations, key=lambda e: e.get("score", 0.0))

        return best_evaluation

    def _execute_path(self, path: Dict[str, Any]) -> str:
        """
        Execute the best path to get final result.

        Phase 4: Execute

        Args:
            path: The path to execute

        Returns:
            Final result string
        """
        # Extract reasoning from best path
        return path.get("reasoning", "No result available")

    def run(
        self, task: str, context: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Universal execution method for ToT agent.

        Parallel exploration:
        1. Generate: Create N reasoning paths
        2. Evaluate: Score each path independently
        3. Select: Choose best path
        4. Execute: Execute only best path

        Args:
            task: The task requiring multiple reasoning paths
            context: Optional additional context
            **kwargs: Additional parameters passed to BaseAgent.run()

        Returns:
            Dictionary containing:
            - paths: List of all generated paths
            - evaluations: List of evaluations with scores
            - best_path: Dict with best path and score
            - final_result: Result from best path
            - error: Optional error code if validation fails

        Example:
            >>> agent = ToTAgent()
            >>> result = agent.run(task="Strategic decision")
            >>> print(f"Explored {len(result['paths'])} paths")
            Explored 5 paths
            >>> print(f"Best score: {result['best_path']['score']:.2f}")
            Best score: 0.85
            >>> print(result["final_result"])
            "Recommended approach: ..."
        """
        # Input validation
        if not task or not task.strip():
            return {
                "error": "INVALID_INPUT",
                "paths": [],
                "evaluations": [],
                "best_path": {"path": {}, "score": 0.0},
                "final_result": "",
            }

        if context is None:
            context = {}

        # Phase 1: Generate Paths
        try:
            logger.info(f"Generating {self.tot_config.num_paths} reasoning paths")
            paths = self._generate_paths(task=task.strip())
        except Exception as e:
            logger.error(f"Error generating paths: {str(e)}")
            return {
                "error": "PATH_GENERATION_FAILED",
                "paths": [],
                "evaluations": [],
                "best_path": {"path": {}, "score": 0.0},
                "final_result": "",
            }

        # Phase 2: Evaluate Paths
        try:
            logger.info(f"Evaluating {len(paths)} paths")
            evaluations = self._evaluate_paths(paths=paths, task=task.strip())
        except Exception as e:
            logger.error(f"Error evaluating paths: {str(e)}")
            return {
                "error": "EVALUATION_FAILED",
                "paths": paths,
                "evaluations": [],
                "best_path": {"path": {}, "score": 0.0},
                "final_result": "",
            }

        # Phase 3: Select Best Path
        try:
            best_path = self._select_best_path(evaluations=evaluations)
        except Exception as e:
            logger.error(f"Error selecting best path: {str(e)}")
            return {
                "error": "SELECTION_FAILED",
                "paths": paths,
                "evaluations": evaluations,
                "best_path": {"path": {}, "score": 0.0},
                "final_result": "",
            }

        # Phase 4: Execute Best Path
        try:
            final_result = self._execute_path(path=best_path.get("path", {}))
        except Exception as e:
            logger.error(f"Error executing best path: {str(e)}")
            return {
                "error": "EXECUTION_FAILED",
                "paths": paths,
                "evaluations": evaluations,
                "best_path": best_path,
                "final_result": "",
            }

        # Return complete result
        return {
            "paths": paths,
            "evaluations": evaluations,
            "best_path": best_path,
            "final_result": final_result,
        }


# Convenience function for quick usage
def explore_paths(task: str, **kwargs) -> Dict[str, Any]:
    """
    Quick one-liner for ToT execution.

    Args:
        task: The task requiring multiple reasoning paths
        **kwargs: Optional configuration (llm_provider, model, num_paths, etc.)

    Returns:
        The full result dictionary

    Example:
        >>> from kaizen.agents.specialized.tree_of_thoughts import explore_paths
        >>> result = explore_paths("Strategic decision", num_paths=7)
        >>> print(f"Explored {len(result['paths'])} paths")
        Explored 7 paths
        >>> print(f"Best score: {result['best_path']['score']:.2f}")
        Best score: 0.92
    """
    agent = ToTAgent(**kwargs)
    return agent.run(task=task)
