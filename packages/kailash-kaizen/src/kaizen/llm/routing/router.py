"""
LLM Router for Intelligent Model Selection.

Routes tasks to appropriate LLM models based on:
- Explicit routing rules
- Task complexity and type
- Cost optimization
- Quality requirements
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from kaizen.llm.routing.analyzer import (
    TaskAnalysis,
    TaskAnalyzer,
    TaskComplexity,
    TaskType,
)
from kaizen.llm.routing.capabilities import (
    MODEL_REGISTRY,
    LLMCapabilities,
    get_model_capabilities,
)

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """Strategy for model selection."""

    RULES = "rules"  # Apply explicit rules only
    TASK_COMPLEXITY = "task_complexity"  # Route by analyzed complexity
    COST_OPTIMIZED = "cost_optimized"  # Minimize cost
    QUALITY_OPTIMIZED = "quality_optimized"  # Maximize quality
    BALANCED = "balanced"  # Balance cost and quality with specialty matching


@dataclass
class RoutingRule:
    """A rule for explicit model routing.

    Rules are evaluated in priority order (higher priority first).
    First matching rule determines the model.

    Example:
        >>> rule = RoutingRule(
        ...     name="code_tasks",
        ...     condition=lambda task, ctx: "code" in task.lower(),
        ...     model="gpt-4",
        ...     priority=10,
        ... )
    """

    name: str
    condition: Callable[[str, Dict], bool]
    model: str
    priority: int = 0
    description: str = ""

    def matches(self, task: str, context: Dict) -> bool:
        """Check if rule matches the task."""
        try:
            return self.condition(task, context)
        except Exception as e:
            logger.warning(f"Rule '{self.name}' condition error: {e}")
            return False


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    model: str
    strategy: RoutingStrategy
    rule_name: Optional[str] = None
    analysis: Optional[TaskAnalysis] = None
    reasoning: str = ""
    alternatives: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "strategy": self.strategy.value,
            "rule_name": self.rule_name,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
        }


class LLMRouter:
    """Intelligent LLM model router.

    Routes tasks to appropriate models based on:
    - Explicit routing rules (highest priority)
    - Task analysis and complexity
    - Cost/quality optimization strategy
    - Capability requirements

    Example:
        >>> router = LLMRouter(
        ...     available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus"],
        ...     default_model="gpt-4",
        ... )
        >>> router.add_keyword_rule(
        ...     keywords=["simple", "quick"],
        ...     model="gpt-3.5-turbo",
        ...     priority=5,
        ... )
        >>> decision = router.route(
        ...     task="Write a simple Python function",
        ...     strategy=RoutingStrategy.BALANCED,
        ... )
        >>> decision.model
        'gpt-3.5-turbo'
    """

    # Complexity to quality score mapping
    COMPLEXITY_MIN_QUALITY = {
        TaskComplexity.TRIVIAL: 0.6,
        TaskComplexity.LOW: 0.7,
        TaskComplexity.MEDIUM: 0.8,
        TaskComplexity.HIGH: 0.9,
        TaskComplexity.EXPERT: 0.95,
    }

    def __init__(
        self,
        available_models: Optional[List[str]] = None,
        default_model: str = "gpt-4",
        analyzer: Optional[TaskAnalyzer] = None,
    ):
        """Initialize LLMRouter.

        Args:
            available_models: List of available model identifiers
            default_model: Default model if no routing applies
            analyzer: TaskAnalyzer instance (created if not provided)
        """
        self._available_models = set(available_models or [])
        self._default_model = default_model
        self._analyzer = analyzer or TaskAnalyzer()
        self._rules: List[RoutingRule] = []

        # Ensure default model is in available models
        if self._default_model:
            self._available_models.add(self._default_model)

        logger.debug(
            f"Initialized LLMRouter with {len(self._available_models)} models, "
            f"default={default_model}"
        )

    @property
    def available_models(self) -> Set[str]:
        """Get available models."""
        return self._available_models.copy()

    @property
    def default_model(self) -> str:
        """Get default model."""
        return self._default_model

    @property
    def rules(self) -> List[RoutingRule]:
        """Get routing rules (sorted by priority)."""
        return sorted(self._rules, key=lambda r: r.priority, reverse=True)

    def add_model(self, model: str) -> None:
        """Add a model to available models."""
        self._available_models.add(model)

    def remove_model(self, model: str) -> None:
        """Remove a model from available models."""
        self._available_models.discard(model)
        if model == self._default_model:
            logger.warning(f"Removed default model: {model}")

    def add_rule(
        self,
        name: str,
        condition: Callable[[str, Dict], bool],
        model: str,
        priority: int = 0,
        description: str = "",
    ) -> None:
        """Add a routing rule.

        Args:
            name: Rule identifier
            condition: Function(task, context) -> bool
            model: Target model when rule matches
            priority: Higher priority rules evaluated first
            description: Human-readable description
        """
        rule = RoutingRule(
            name=name,
            condition=condition,
            model=model,
            priority=priority,
            description=description,
        )
        self._rules.append(rule)
        self._available_models.add(model)
        logger.debug(f"Added routing rule: {name} -> {model} (priority={priority})")

    def add_keyword_rule(
        self,
        keywords: List[str],
        model: str,
        priority: int = 0,
        match_any: bool = True,
    ) -> None:
        """Add a keyword-based routing rule.

        Args:
            keywords: Keywords to match in task
            model: Target model when keywords match
            priority: Rule priority
            match_any: If True, match any keyword; if False, match all
        """
        keywords_lower = [k.lower() for k in keywords]

        if match_any:

            def condition(task: str, ctx: dict) -> bool:
                return any(k in task.lower() for k in keywords_lower)

            name = f"keyword_any_{model}"
        else:

            def condition(task: str, ctx: dict) -> bool:
                return all(k in task.lower() for k in keywords_lower)

            name = f"keyword_all_{model}"

        self.add_rule(
            name=name,
            condition=condition,
            model=model,
            priority=priority,
            description=f"Keywords: {', '.join(keywords)}",
        )

    def add_type_rule(
        self,
        task_type: TaskType,
        model: str,
        priority: int = 0,
    ) -> None:
        """Add a task type routing rule.

        Args:
            task_type: TaskType to match
            model: Target model for this type
            priority: Rule priority
        """

        def condition(task: str, context: Dict) -> bool:
            analysis = self._analyzer.analyze(task, context)
            return analysis.type == task_type

        self.add_rule(
            name=f"type_{task_type.value}_{model}",
            condition=condition,
            model=model,
            priority=priority,
            description=f"Task type: {task_type.value}",
        )

    def add_complexity_rule(
        self,
        min_complexity: TaskComplexity,
        model: str,
        priority: int = 0,
    ) -> None:
        """Add a complexity threshold routing rule.

        Args:
            min_complexity: Minimum complexity for this rule
            model: Target model for complex tasks
            priority: Rule priority
        """
        complexity_order = [
            TaskComplexity.TRIVIAL,
            TaskComplexity.LOW,
            TaskComplexity.MEDIUM,
            TaskComplexity.HIGH,
            TaskComplexity.EXPERT,
        ]
        min_idx = complexity_order.index(min_complexity)

        def condition(task: str, context: Dict) -> bool:
            analysis = self._analyzer.analyze(task, context)
            current_idx = complexity_order.index(analysis.complexity)
            return current_idx >= min_idx

        self.add_rule(
            name=f"complexity_{min_complexity.value}_{model}",
            condition=condition,
            model=model,
            priority=priority,
            description=f"Complexity >= {min_complexity.value}",
        )

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""
        original_len = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < original_len

    def clear_rules(self) -> None:
        """Remove all routing rules."""
        self._rules.clear()

    def route(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
        required_capabilities: Optional[Dict[str, bool]] = None,
    ) -> RoutingDecision:
        """Route a task to an appropriate model.

        Args:
            task: Task description or prompt
            context: Optional context dict
            strategy: Routing strategy to use
            required_capabilities: Explicit capability requirements

        Returns:
            RoutingDecision with selected model and reasoning
        """
        context = context or {}
        required_capabilities = required_capabilities or {}

        # First: Check explicit rules (always evaluated first)
        if strategy == RoutingStrategy.RULES or self._rules:
            for rule in self.rules:
                if rule.matches(task, context):
                    if rule.model in self._available_models:
                        return RoutingDecision(
                            model=rule.model,
                            strategy=RoutingStrategy.RULES,
                            rule_name=rule.name,
                            reasoning=f"Matched rule: {rule.name}",
                        )
                    else:
                        logger.warning(
                            f"Rule '{rule.name}' matched but model '{rule.model}' "
                            "not available"
                        )

            # If strategy is RULES and no rule matched, use default
            if strategy == RoutingStrategy.RULES:
                return RoutingDecision(
                    model=self._default_model,
                    strategy=RoutingStrategy.RULES,
                    reasoning="No rules matched, using default",
                )

        # Analyze task
        analysis = self._analyzer.analyze(task, context)

        # Merge detected requirements with explicit requirements
        requirements = {
            "requires_vision": required_capabilities.get(
                "vision", analysis.requires_vision
            ),
            "requires_audio": required_capabilities.get(
                "audio", analysis.requires_audio
            ),
            "requires_tools": required_capabilities.get(
                "tools", analysis.requires_tools
            ),
            "requires_structured": required_capabilities.get(
                "structured", analysis.requires_structured
            ),
        }

        # Filter capable models
        capable_models = self._filter_capable_models(requirements, analysis)

        if not capable_models:
            logger.warning("No capable models found, using default")
            return RoutingDecision(
                model=self._default_model,
                strategy=strategy,
                analysis=analysis,
                reasoning="No capable models found",
            )

        # Route by strategy
        if strategy == RoutingStrategy.TASK_COMPLEXITY:
            model = self._select_by_complexity(capable_models, analysis)
            reasoning = f"Selected by complexity ({analysis.complexity.value})"

        elif strategy == RoutingStrategy.COST_OPTIMIZED:
            model = self._select_cheapest(capable_models)
            reasoning = "Selected cheapest capable model"

        elif strategy == RoutingStrategy.QUALITY_OPTIMIZED:
            model = self._select_best_quality(capable_models)
            reasoning = "Selected highest quality model"

        elif strategy == RoutingStrategy.BALANCED:
            model = self._select_balanced(capable_models, analysis)
            reasoning = f"Balanced selection for {analysis.type.value} task"

        else:
            model = self._default_model
            reasoning = "Using default model"

        # Get alternatives
        alternatives = [m for m in capable_models if m != model][:3]

        return RoutingDecision(
            model=model,
            strategy=strategy,
            analysis=analysis,
            reasoning=reasoning,
            alternatives=alternatives,
        )

    def _filter_capable_models(
        self, requirements: Dict[str, bool], analysis: TaskAnalysis
    ) -> List[str]:
        """Filter models that meet requirements."""
        capable = []

        for model_id in self._available_models:
            caps = get_model_capabilities(model_id)
            if not caps:
                # Unknown model - include but with lower priority
                capable.append(model_id)
                continue

            # Check capability requirements
            if requirements.get("requires_vision") and not caps.supports_vision:
                continue
            if requirements.get("requires_audio") and not caps.supports_audio:
                continue
            if requirements.get("requires_tools") and not caps.supports_tool_calling:
                continue
            if (
                requirements.get("requires_structured")
                and not caps.supports_structured_output
            ):
                continue

            # Check context size
            if analysis.estimated_tokens > caps.max_output:
                continue

            capable.append(model_id)

        return capable

    def _select_by_complexity(
        self, candidates: List[str], analysis: TaskAnalysis
    ) -> str:
        """Select model based on task complexity."""
        min_quality = self.COMPLEXITY_MIN_QUALITY.get(analysis.complexity, 0.8)

        # Get models meeting minimum quality
        qualified = []
        for model_id in candidates:
            caps = get_model_capabilities(model_id)
            if caps and caps.quality_score >= min_quality:
                qualified.append(
                    (model_id, caps.quality_score, caps.cost_per_1k_output)
                )
            elif not caps:
                # Unknown model, assume medium quality
                qualified.append((model_id, 0.75, 0.0))

        if not qualified:
            # Fallback to highest quality available
            return self._select_best_quality(candidates)

        # For given complexity, prefer cheaper among qualified
        qualified.sort(key=lambda x: (x[2], -x[1]))  # Sort by cost, then quality desc
        return qualified[0][0]

    def _select_cheapest(self, candidates: List[str]) -> str:
        """Select cheapest model."""
        costs = []
        for model_id in candidates:
            caps = get_model_capabilities(model_id)
            if caps:
                cost = caps.estimate_cost(1000, 500)  # Typical request
                costs.append((model_id, cost))
            else:
                # Unknown model, assume free
                costs.append((model_id, 0.0))

        costs.sort(key=lambda x: x[1])
        return costs[0][0]

    def _select_best_quality(self, candidates: List[str]) -> str:
        """Select highest quality model."""
        qualities = []
        for model_id in candidates:
            caps = get_model_capabilities(model_id)
            if caps:
                qualities.append((model_id, caps.quality_score))
            else:
                qualities.append((model_id, 0.7))  # Assume medium quality

        qualities.sort(key=lambda x: x[1], reverse=True)
        return qualities[0][0]

    def _select_balanced(self, candidates: List[str], analysis: TaskAnalysis) -> str:
        """Select model balancing cost, quality, and specialty.

        Score = 0.4 * quality_normalized + 0.3 * cost_normalized + 0.3 * specialty_bonus
        """
        scored = []

        # Get quality and cost ranges for normalization
        qualities = []
        costs = []
        for model_id in candidates:
            caps = get_model_capabilities(model_id)
            if caps:
                qualities.append(caps.quality_score)
                costs.append(caps.estimate_cost(1000, 500))

        if not qualities:
            # No known models, return first
            return candidates[0] if candidates else self._default_model

        min_quality, max_quality = min(qualities), max(qualities)
        min_cost, max_cost = min(costs), max(costs)
        quality_range = max_quality - min_quality or 1.0
        cost_range = max_cost - min_cost or 1.0

        for model_id in candidates:
            caps = get_model_capabilities(model_id)
            if not caps:
                scored.append((model_id, 0.5))  # Default score for unknown
                continue

            # Normalize quality (higher is better)
            quality_norm = (caps.quality_score - min_quality) / quality_range

            # Normalize cost (lower is better, so invert)
            cost = caps.estimate_cost(1000, 500)
            cost_norm = 1.0 - (cost - min_cost) / cost_range

            # Specialty bonus
            specialty_bonus = 0.0
            for specialty in analysis.specialties_needed:
                if caps.supports_specialty(specialty):
                    specialty_bonus += 0.3  # 30% bonus per matching specialty
            specialty_bonus = min(specialty_bonus, 1.0)  # Cap at 100%

            # Calculate balanced score
            score = 0.4 * quality_norm + 0.3 * cost_norm + 0.3 * specialty_bonus

            scored.append((model_id, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]
