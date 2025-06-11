"""
Intelligent Migration System for DAG to Cyclic Workflow Conversion.

This module provides comprehensive tools to analyze existing DAG workflows
and intelligently suggest or automatically convert them to use cyclic patterns
where appropriate. It identifies optimization opportunities, provides detailed
implementation guidance, and automates the conversion process.

Design Philosophy:
    Provides intelligent analysis of existing workflows to identify patterns
    that would benefit from cyclification, offering both automated conversion
    and detailed guidance for manual implementation. Focuses on preserving
    workflow semantics while optimizing for performance and maintainability.

Key Features:
    - Pattern recognition for cyclification opportunities
    - Confidence scoring for conversion recommendations
    - Automated conversion with safety validation
    - Detailed implementation guidance with code examples
    - Risk assessment and migration planning
    - Template-based conversion for common patterns

Analysis Capabilities:
    - Retry pattern detection in manual implementations
    - Iterative improvement pattern identification
    - Data validation and cleaning pattern recognition
    - Batch processing pattern analysis
    - Numerical convergence pattern detection
    - Performance anti-pattern identification

Core Components:
    - CyclificationOpportunity: Identified conversion opportunity
    - CyclificationSuggestion: Detailed implementation guidance
    - DAGToCycleConverter: Main analysis and conversion engine
    - Pattern detection algorithms for common workflows

Conversion Strategy:
    - Non-destructive analysis preserving original workflows
    - Confidence-based prioritization of opportunities
    - Template-based conversion for reliability
    - Comprehensive validation of converted workflows
    - Rollback capabilities for failed conversions

Upstream Dependencies:
    - Existing workflow structures and node implementations
    - CycleTemplates for automated conversion patterns
    - Workflow validation and safety systems

Downstream Consumers:
    - Workflow development tools and IDEs
    - Automated workflow optimization systems
    - Migration planning and execution tools
    - Performance optimization recommendations
    - Educational and training systems

Examples:
    Analyze workflow for opportunities:

    >>> from kailash.workflow.migration import DAGToCycleConverter
    >>> converter = DAGToCycleConverter(existing_workflow)
    >>> opportunities = converter.analyze_cyclification_opportunities()
    >>> for opp in opportunities:
    ...     print(f"Found {opp.pattern_type}: {opp.description}")
    ...     print(f"Confidence: {opp.confidence:.2f}")
    ...     print(f"Expected benefit: {opp.estimated_benefit}")

    Generate detailed migration guidance:

    >>> suggestions = converter.generate_detailed_suggestions()
    >>> for suggestion in suggestions:
    ...     print(f"Found {suggestion.opportunity.pattern_type}")
    ...     print(f"Implementation steps:")
    ...     for step in suggestion.implementation_steps:
    ...         print(f"  {step}")
    ...     print(f"Code example: {suggestion.code_example}")
    ...     print(f"Expected outcome: {suggestion.expected_outcome}")

    Automated conversion:

    >>> # Convert specific nodes to cycle
    >>> cycle_id = converter.convert_to_cycle(
    ...     nodes=["processor", "evaluator"],
    ...     convergence_strategy="quality_improvement",
    ...     max_iterations=50
    ... )
    >>> print(f"Created cycle: {cycle_id}")

    Comprehensive migration report:

    >>> report = converter.generate_migration_report()
    >>> print(f"Total opportunities: {report['summary']['total_opportunities']}")
    >>> print(f"High confidence: {report['summary']['high_confidence']}")
    >>> # Implementation priority order
    >>> for item in report['implementation_order']:
    ...     print(f"{item['priority']}: {item['justification']}")

See Also:
    - :mod:`kailash.workflow.templates` for conversion patterns
    - :mod:`kailash.workflow.validation` for workflow analysis
    - :doc:`/guides/migration` for migration best practices
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from . import Workflow
from .templates import CycleTemplates


@dataclass
class CyclificationOpportunity:
    """Represents an opportunity to convert a DAG pattern to a cycle."""

    nodes: list[str]
    pattern_type: str
    confidence: float
    description: str
    suggested_convergence: str | None = None
    estimated_benefit: str = "unknown"
    implementation_complexity: str = "medium"


@dataclass
class CyclificationSuggestion:
    """Detailed suggestion for converting nodes to a cycle."""

    opportunity: CyclificationOpportunity
    implementation_steps: list[str]
    code_example: str
    expected_outcome: str
    risks: list[str]


class DAGToCycleConverter:
    """
    Analyzer and converter for transforming DAG workflows into cyclic workflows.

    This class helps identify patterns in existing workflows that could benefit
    from cyclic execution and provides tools to convert them.
    """

    def __init__(self, workflow: Workflow):
        """
        Initialize converter with target workflow.

        Args:
            workflow: The workflow to analyze and potentially convert
        """
        self.workflow = workflow
        self.graph = workflow.graph
        self.opportunities: list[CyclificationOpportunity] = []

    def analyze_cyclification_opportunities(self) -> list[CyclificationOpportunity]:
        """
        Analyze workflow for patterns that could benefit from cyclification.

        Returns:
            List of identified cyclification opportunities

        Example:
            >>> workflow = create_example_workflow()
            >>> converter = DAGToCycleConverter(workflow)
            >>> opportunities = converter.analyze_cyclification_opportunities()
            >>> for opp in opportunities:
            ...     print(f"{opp.pattern_type}: {opp.description}")
        """
        self.opportunities = []

        # Analyze different patterns
        self._detect_retry_patterns()
        self._detect_iterative_improvement_patterns()
        self._detect_validation_patterns()
        self._detect_batch_processing_patterns()
        self._detect_convergence_patterns()

        # Sort by confidence and potential benefit
        self.opportunities.sort(key=lambda x: x.confidence, reverse=True)

        return self.opportunities

    def _detect_retry_patterns(self):
        """Detect patterns that look like manual retry logic."""
        nodes = self.workflow.nodes

        # Look for nodes with similar names suggesting retry logic
        retry_patterns = [
            r".*[_\-]retry[_\-]?.*",
            r".*[_\-]attempt[_\-]?[0-9]*",
            r".*[_\-]backup[_\-]?.*",
            r".*[_\-]fallback[_\-]?.*",
            r".*[_\-]redundant[_\-]?.*",
            r".*[_\-]failover[_\-]?.*",
        ]

        for node_id, node in nodes.items():
            for pattern in retry_patterns:
                if re.match(pattern, node_id, re.IGNORECASE):
                    # Found potential retry pattern
                    related_nodes = self._find_related_nodes(node_id)

                    opportunity = CyclificationOpportunity(
                        nodes=[node_id] + related_nodes,
                        pattern_type="retry_cycle",
                        confidence=0.7,
                        description=f"Node '{node_id}' appears to implement retry logic manually",
                        suggested_convergence="success == True",
                        estimated_benefit="improved_reliability",
                        implementation_complexity="low",
                    )
                    self.opportunities.append(opportunity)

    def _detect_iterative_improvement_patterns(self):
        """Detect patterns that perform iterative improvement."""
        nodes = self.workflow.nodes

        # Look for processor-evaluator pairs
        improvement_keywords = ["process", "improve", "optimize", "refine", "enhance"]
        evaluation_keywords = ["evaluate", "assess", "validate", "check", "score"]

        processors = []
        evaluators = []

        for node_id in nodes:
            node_id_lower = node_id.lower()
            if any(keyword in node_id_lower for keyword in improvement_keywords):
                processors.append(node_id)
            if any(keyword in node_id_lower for keyword in evaluation_keywords):
                evaluators.append(node_id)

        # Look for processor-evaluator pairs that are connected
        for processor in processors:
            for evaluator in evaluators:
                if self._are_connected(processor, evaluator):
                    opportunity = CyclificationOpportunity(
                        nodes=[processor, evaluator],
                        pattern_type="optimization_cycle",
                        confidence=0.8,
                        description=f"'{processor}' and '{evaluator}' form iterative improvement pattern",
                        suggested_convergence="quality > 0.9",
                        estimated_benefit="automatic_convergence",
                        implementation_complexity="medium",
                    )
                    self.opportunities.append(opportunity)

    def _detect_validation_patterns(self):
        """Detect data validation and cleaning patterns."""
        nodes = self.workflow.nodes

        cleaning_keywords = ["clean", "sanitize", "normalize", "transform"]
        validation_keywords = ["validate", "verify", "check", "audit"]

        cleaners = []
        validators = []

        for node_id in nodes:
            node_id_lower = node_id.lower()
            if any(keyword in node_id_lower for keyword in cleaning_keywords):
                cleaners.append(node_id)
            if any(keyword in node_id_lower for keyword in validation_keywords):
                validators.append(node_id)

        # Look for cleaner-validator pairs
        for cleaner in cleaners:
            for validator in validators:
                if self._are_connected(cleaner, validator):
                    opportunity = CyclificationOpportunity(
                        nodes=[cleaner, validator],
                        pattern_type="data_quality_cycle",
                        confidence=0.75,
                        description=f"'{cleaner}' and '{validator}' form data quality improvement pattern",
                        suggested_convergence="quality_score >= 0.95",
                        estimated_benefit="improved_data_quality",
                        implementation_complexity="low",
                    )
                    self.opportunities.append(opportunity)

    def _detect_batch_processing_patterns(self):
        """Detect patterns that process data in chunks."""
        nodes = self.workflow.nodes

        batch_keywords = ["batch", "chunk", "segment", "partition", "split"]

        for node_id in nodes:
            node_id_lower = node_id.lower()
            if any(keyword in node_id_lower for keyword in batch_keywords):
                opportunity = CyclificationOpportunity(
                    nodes=[node_id],
                    pattern_type="batch_processing_cycle",
                    confidence=0.6,
                    description=f"'{node_id}' appears to process data in batches",
                    suggested_convergence="all_batches_processed == True",
                    estimated_benefit="memory_efficiency",
                    implementation_complexity="medium",
                )
                self.opportunities.append(opportunity)

    def _detect_convergence_patterns(self):
        """Detect numerical convergence patterns."""
        nodes = self.workflow.nodes

        convergence_keywords = [
            "converge",
            "iterate",
            "approximate",
            "solve",
            "calculate",
        ]

        for node_id in nodes:
            node_id_lower = node_id.lower()
            if any(keyword in node_id_lower for keyword in convergence_keywords):
                opportunity = CyclificationOpportunity(
                    nodes=[node_id],
                    pattern_type="convergence_cycle",
                    confidence=0.5,
                    description=f"'{node_id}' may perform iterative calculations",
                    suggested_convergence="difference < 0.001",
                    estimated_benefit="numerical_stability",
                    implementation_complexity="high",
                )
                self.opportunities.append(opportunity)

    def _find_related_nodes(self, node_id: str) -> list[str]:
        """Find nodes that are closely related to the given node."""
        related = []

        # Find direct connections from NetworkX graph
        graph = self.workflow.graph

        # Find predecessors and successors
        if node_id in graph:
            related.extend(graph.predecessors(node_id))
            related.extend(graph.successors(node_id))

        return list(set(related))

    def _are_connected(self, node1: str, node2: str) -> bool:
        """Check if two nodes are directly connected."""
        graph = self.workflow.graph

        # Check if there's an edge between the nodes in either direction
        return graph.has_edge(node1, node2) or graph.has_edge(node2, node1)

    def generate_detailed_suggestions(self) -> list[CyclificationSuggestion]:
        """
        Generate detailed suggestions with implementation guidance.

        Returns:
            List of detailed suggestions for cyclification

        Example:
            >>> converter = DAGToCycleConverter(workflow)
            >>> converter.analyze_cyclification_opportunities()
            >>> suggestions = converter.generate_detailed_suggestions()
            >>> for suggestion in suggestions:
            ...     print(suggestion.code_example)
        """
        suggestions = []

        for opportunity in self.opportunities:
            suggestion = self._create_detailed_suggestion(opportunity)
            suggestions.append(suggestion)

        return suggestions

    def _create_detailed_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create detailed implementation suggestion for an opportunity."""

        if opportunity.pattern_type == "retry_cycle":
            return self._create_retry_suggestion(opportunity)
        elif opportunity.pattern_type == "optimization_cycle":
            return self._create_optimization_suggestion(opportunity)
        elif opportunity.pattern_type == "data_quality_cycle":
            return self._create_data_quality_suggestion(opportunity)
        elif opportunity.pattern_type == "batch_processing_cycle":
            return self._create_batch_processing_suggestion(opportunity)
        elif opportunity.pattern_type == "convergence_cycle":
            return self._create_convergence_suggestion(opportunity)
        else:
            return self._create_generic_suggestion(opportunity)

    def _create_retry_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create suggestion for retry cycle conversion."""
        main_node = opportunity.nodes[0]

        code_example = f"""
# Before: Manual retry logic (complex, error-prone)
# Multiple nodes handling retries manually

# After: Using retry cycle template
cycle_id = workflow.add_retry_cycle(
    target_node="{main_node}",
    max_retries=3,
    backoff_strategy="exponential",
    success_condition="success == True"
)

print(f"Created retry cycle: {{cycle_id}}")
"""

        implementation_steps = [
            f"Identify the main node that needs retry logic: '{main_node}'",
            "Remove manual retry handling from existing nodes",
            "Apply retry cycle template with appropriate parameters",
            "Test with failure scenarios to ensure proper retry behavior",
            "Monitor retry patterns in production",
        ]

        return CyclificationSuggestion(
            opportunity=opportunity,
            implementation_steps=implementation_steps,
            code_example=code_example,
            expected_outcome="Simplified retry logic with exponential backoff and better error handling",
            risks=[
                "May change timing of operations",
                "Retry behavior might differ from manual implementation",
            ],
        )

    def _create_optimization_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create suggestion for optimization cycle conversion."""
        nodes = opportunity.nodes
        processor = nodes[0] if nodes else "processor"
        evaluator = nodes[1] if len(nodes) > 1 else "evaluator"

        code_example = f"""
# Before: Manual iterative improvement (fixed iterations, no early stopping)
# Complex logic to manage improvement loops

# After: Using optimization cycle template
cycle_id = workflow.add_optimization_cycle(
    processor_node="{processor}",
    evaluator_node="{evaluator}",
    convergence="quality > 0.95",
    max_iterations=100
)

print(f"Created optimization cycle: {{cycle_id}}")
"""

        implementation_steps = [
            f"Ensure '{processor}' generates/improves solutions",
            f"Ensure '{evaluator}' produces quality metrics",
            "Define appropriate convergence criteria",
            "Apply optimization cycle template",
            "Fine-tune convergence thresholds based on testing",
        ]

        return CyclificationSuggestion(
            opportunity=opportunity,
            implementation_steps=implementation_steps,
            code_example=code_example,
            expected_outcome="Automatic convergence detection with early stopping for better performance",
            risks=[
                "Convergence criteria may need tuning",
                "May require more iterations than fixed approach",
            ],
        )

    def _create_data_quality_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create suggestion for data quality cycle conversion."""
        nodes = opportunity.nodes
        cleaner = nodes[0] if nodes else "cleaner"
        validator = nodes[1] if len(nodes) > 1 else "validator"

        code_example = f"""
# Before: Single-pass cleaning (may miss quality issues)
# Fixed cleaning pipeline without quality feedback

# After: Using data quality cycle template
cycle_id = workflow.add_data_quality_cycle(
    cleaner_node="{cleaner}",
    validator_node="{validator}",
    quality_threshold=0.98,
    max_iterations=5
)

print(f"Created data quality cycle: {{cycle_id}}")
"""

        implementation_steps = [
            f"Ensure '{cleaner}' can improve data quality iteratively",
            f"Ensure '{validator}' produces numeric quality scores",
            "Define appropriate quality threshold",
            "Apply data quality cycle template",
            "Monitor quality improvements over iterations",
        ]

        return CyclificationSuggestion(
            opportunity=opportunity,
            implementation_steps=implementation_steps,
            code_example=code_example,
            expected_outcome="Higher data quality through iterative improvement with automatic stopping",
            risks=[
                "May increase processing time",
                "Quality metrics need to be meaningful",
            ],
        )

    def _create_batch_processing_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create suggestion for batch processing cycle conversion."""
        node = opportunity.nodes[0] if opportunity.nodes else "processor"

        code_example = f"""
# Before: Manual batch handling (complex state management)
# Custom logic for batch iteration and completion

# After: Using batch processing cycle template
cycle_id = workflow.add_batch_processing_cycle(
    processor_node="{node}",
    batch_size=100,
    total_items=10000  # If known
)

print(f"Created batch processing cycle: {{cycle_id}}")
"""

        implementation_steps = [
            f"Modify '{node}' to process batches instead of full dataset",
            "Determine appropriate batch size for memory constraints",
            "Apply batch processing cycle template",
            "Test with various dataset sizes",
            "Monitor memory usage and processing time",
        ]

        return CyclificationSuggestion(
            opportunity=opportunity,
            implementation_steps=implementation_steps,
            code_example=code_example,
            expected_outcome="Memory-efficient processing of large datasets with automatic batch management",
            risks=[
                "Batch size may need tuning",
                "May change processing order/behavior",
            ],
        )

    def _create_convergence_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create suggestion for convergence cycle conversion."""
        node = opportunity.nodes[0] if opportunity.nodes else "processor"

        code_example = f"""
# Before: Fixed iterations (may over/under-compute)
# Manual convergence checking

# After: Using convergence cycle template
cycle_id = workflow.add_convergence_cycle(
    processor_node="{node}",
    tolerance=0.001,
    max_iterations=1000
)

print(f"Created convergence cycle: {{cycle_id}}")
"""

        implementation_steps = [
            f"Ensure '{node}' produces numeric values for convergence checking",
            "Determine appropriate tolerance for convergence",
            "Apply convergence cycle template",
            "Test with various starting conditions",
            "Validate convergence behavior",
        ]

        return CyclificationSuggestion(
            opportunity=opportunity,
            implementation_steps=implementation_steps,
            code_example=code_example,
            expected_outcome="Automatic convergence detection with optimal iteration count",
            risks=[
                "Tolerance may need adjustment",
                "Convergence behavior may differ from fixed iterations",
            ],
        )

    def _create_generic_suggestion(
        self, opportunity: CyclificationOpportunity
    ) -> CyclificationSuggestion:
        """Create generic suggestion for unknown pattern types."""
        return CyclificationSuggestion(
            opportunity=opportunity,
            implementation_steps=[
                "Analyze pattern manually",
                "Choose appropriate cycle template",
            ],
            code_example="# Manual analysis required",
            expected_outcome="Pattern-specific benefits",
            risks=["Requires manual analysis"],
        )

    def convert_to_cycle(
        self,
        nodes: list[str],
        convergence_strategy: str = "error_reduction",
        cycle_type: str | None = None,
        **kwargs,
    ) -> str:
        """
        Convert specific nodes to a cycle using the specified strategy.

        Args:
            nodes: List of node IDs to include in the cycle
            convergence_strategy: Strategy for convergence ("error_reduction", "quality_improvement", etc.)
            cycle_type: Specific cycle type to use, or auto-detect if None
            **kwargs: Additional parameters for cycle creation

        Returns:
            str: The created cycle identifier

        Example:
            >>> converter = DAGToCycleConverter(workflow)
            >>> cycle_id = converter.convert_to_cycle(
            ...     nodes=["processor", "evaluator"],
            ...     convergence_strategy="quality_improvement",
            ...     max_iterations=50
            ... )
        """
        if cycle_type is None:
            cycle_type = self._detect_cycle_type(nodes, convergence_strategy)

        if cycle_type == "optimization":
            return self._convert_to_optimization_cycle(nodes, **kwargs)
        elif cycle_type == "retry":
            return self._convert_to_retry_cycle(nodes, **kwargs)
        elif cycle_type == "data_quality":
            return self._convert_to_data_quality_cycle(nodes, **kwargs)
        elif cycle_type == "batch_processing":
            return self._convert_to_batch_processing_cycle(nodes, **kwargs)
        elif cycle_type == "convergence":
            return self._convert_to_convergence_cycle(nodes, **kwargs)
        else:
            raise ValueError(f"Unknown cycle type: {cycle_type}")

    def _detect_cycle_type(self, nodes: list[str], strategy: str) -> str:
        """Detect the most appropriate cycle type for given nodes and strategy."""
        if strategy == "error_reduction" or strategy == "quality_improvement":
            return "optimization"
        elif strategy == "retry_logic":
            return "retry"
        elif strategy == "data_cleaning":
            return "data_quality"
        elif strategy == "batch_processing":
            return "batch_processing"
        elif strategy == "numerical_convergence":
            return "convergence"
        else:
            # Default to optimization for unknown strategies
            return "optimization"

    def _convert_to_optimization_cycle(self, nodes: list[str], **kwargs) -> str:
        """Convert nodes to optimization cycle."""
        if len(nodes) < 2:
            raise ValueError("Optimization cycle requires at least 2 nodes")

        return CycleTemplates.optimization_cycle(
            self.workflow, processor_node=nodes[0], evaluator_node=nodes[1], **kwargs
        )

    def _convert_to_retry_cycle(self, nodes: list[str], **kwargs) -> str:
        """Convert nodes to retry cycle."""
        if len(nodes) < 1:
            raise ValueError("Retry cycle requires at least 1 node")

        return CycleTemplates.retry_cycle(self.workflow, target_node=nodes[0], **kwargs)

    def _convert_to_data_quality_cycle(self, nodes: list[str], **kwargs) -> str:
        """Convert nodes to data quality cycle."""
        if len(nodes) < 2:
            raise ValueError("Data quality cycle requires at least 2 nodes")

        return CycleTemplates.data_quality_cycle(
            self.workflow, cleaner_node=nodes[0], validator_node=nodes[1], **kwargs
        )

    def _convert_to_batch_processing_cycle(self, nodes: list[str], **kwargs) -> str:
        """Convert nodes to batch processing cycle."""
        if len(nodes) < 1:
            raise ValueError("Batch processing cycle requires at least 1 node")

        return CycleTemplates.batch_processing_cycle(
            self.workflow, processor_node=nodes[0], **kwargs
        )

    def _convert_to_convergence_cycle(self, nodes: list[str], **kwargs) -> str:
        """Convert nodes to convergence cycle."""
        if len(nodes) < 1:
            raise ValueError("Convergence cycle requires at least 1 node")

        return CycleTemplates.convergence_cycle(
            self.workflow, processor_node=nodes[0], **kwargs
        )

    def generate_migration_report(self) -> dict[str, Any]:
        """
        Generate comprehensive migration report with analysis and recommendations.

        Returns:
            Dict containing migration analysis and recommendations

        Example:
            >>> converter = DAGToCycleConverter(workflow)
            >>> converter.analyze_cyclification_opportunities()
            >>> report = converter.generate_migration_report()
            >>> print(report['summary']['total_opportunities'])
        """
        opportunities = self.analyze_cyclification_opportunities()
        suggestions = self.generate_detailed_suggestions()

        # Categorize by pattern type
        by_pattern = defaultdict(list)
        for opp in opportunities:
            by_pattern[opp.pattern_type].append(opp)

        # Calculate potential benefits
        high_confidence = [opp for opp in opportunities if opp.confidence >= 0.7]
        medium_confidence = [
            opp for opp in opportunities if 0.4 <= opp.confidence < 0.7
        ]
        low_confidence = [opp for opp in opportunities if opp.confidence < 0.4]

        return {
            "summary": {
                "total_opportunities": len(opportunities),
                "high_confidence": len(high_confidence),
                "medium_confidence": len(medium_confidence),
                "low_confidence": len(low_confidence),
                "pattern_distribution": {k: len(v) for k, v in by_pattern.items()},
            },
            "opportunities": opportunities,
            "detailed_suggestions": suggestions,
            "recommendations": self._generate_migration_recommendations(opportunities),
            "implementation_order": self._suggest_implementation_order(opportunities),
        }

    def _generate_migration_recommendations(
        self, opportunities: list[CyclificationOpportunity]
    ) -> list[str]:
        """Generate high-level recommendations for migration."""
        recommendations = []

        high_confidence = [opp for opp in opportunities if opp.confidence >= 0.7]
        if high_confidence:
            recommendations.append(
                f"Start with {len(high_confidence)} high-confidence opportunities for immediate benefits"
            )

        pattern_counts = defaultdict(int)
        for opp in opportunities:
            pattern_counts[opp.pattern_type] += 1

        most_common = (
            max(pattern_counts.items(), key=lambda x: x[1]) if pattern_counts else None
        )
        if most_common:
            recommendations.append(
                f"Focus on {most_common[0]} patterns ({most_common[1]} opportunities) for consistency"
            )

        low_complexity = [
            opp for opp in opportunities if opp.implementation_complexity == "low"
        ]
        if low_complexity:
            recommendations.append(
                f"Begin with {len(low_complexity)} low-complexity conversions to build confidence"
            )

        return recommendations

    def _suggest_implementation_order(
        self, opportunities: list[CyclificationOpportunity]
    ) -> list[dict[str, Any]]:
        """Suggest order for implementing cyclification opportunities."""
        # Sort by: confidence desc, complexity asc (low=1, medium=2, high=3)
        complexity_score = {"low": 1, "medium": 2, "high": 3}

        def sort_key(opp):
            return (
                -opp.confidence,
                complexity_score.get(opp.implementation_complexity, 2),
            )

        sorted_opportunities = sorted(opportunities, key=sort_key)

        implementation_order = []
        for i, opp in enumerate(sorted_opportunities, 1):
            implementation_order.append(
                {
                    "priority": i,
                    "pattern_type": opp.pattern_type,
                    "nodes": opp.nodes,
                    "confidence": opp.confidence,
                    "complexity": opp.implementation_complexity,
                    "justification": f"Priority {i}: {opp.description}",
                }
            )

        return implementation_order
