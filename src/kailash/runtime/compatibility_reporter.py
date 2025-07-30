"""Compatibility reporting for conditional execution.

This module provides detailed compatibility analysis and reporting
for workflows using conditional execution.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kailash.analysis import ConditionalBranchAnalyzer
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class CompatibilityLevel(Enum):
    """Compatibility levels for conditional execution."""

    FULLY_COMPATIBLE = "fully_compatible"
    PARTIALLY_COMPATIBLE = "partially_compatible"
    INCOMPATIBLE = "incompatible"


@dataclass
class PatternInfo:
    """Information about a detected pattern."""

    pattern_type: str
    node_ids: List[str]
    description: str
    compatibility: CompatibilityLevel
    recommendation: Optional[str] = None


@dataclass
class CompatibilityReport:
    """Comprehensive compatibility report for a workflow."""

    workflow_id: str
    workflow_name: str
    overall_compatibility: CompatibilityLevel
    node_count: int
    switch_count: int
    detected_patterns: List[PatternInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    execution_estimate: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary format."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "overall_compatibility": self.overall_compatibility.value,
            "node_count": self.node_count,
            "switch_count": self.switch_count,
            "detected_patterns": [
                {
                    "type": p.pattern_type,
                    "nodes": p.node_ids,
                    "description": p.description,
                    "compatibility": p.compatibility.value,
                    "recommendation": p.recommendation,
                }
                for p in self.detected_patterns
            ],
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "execution_estimate": self.execution_estimate,
        }

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            "# Conditional Execution Compatibility Report",
            "",
            f"**Workflow**: {self.workflow_name} ({self.workflow_id})",
            f"**Overall Compatibility**: {self.overall_compatibility.value.replace('_', ' ').title()}",
            f"**Nodes**: {self.node_count} total, {self.switch_count} switches",
            "",
        ]

        if self.execution_estimate:
            lines.extend(
                [
                    "## Performance Estimate",
                    f"{self.execution_estimate}",
                    "",
                ]
            )

        if self.detected_patterns:
            lines.extend(
                [
                    "## Detected Patterns",
                    "",
                ]
            )
            for pattern in self.detected_patterns:
                compat_icon = (
                    "✅"
                    if pattern.compatibility == CompatibilityLevel.FULLY_COMPATIBLE
                    else "⚠️"
                )
                lines.extend(
                    [
                        f"### {compat_icon} {pattern.pattern_type}",
                        f"- **Nodes**: {', '.join(pattern.node_ids)}",
                        f"- **Description**: {pattern.description}",
                        f"- **Compatibility**: {pattern.compatibility.value.replace('_', ' ').title()}",
                    ]
                )
                if pattern.recommendation:
                    lines.append(f"- **Recommendation**: {pattern.recommendation}")
                lines.append("")

        if self.warnings:
            lines.extend(
                [
                    "## ⚠️ Warnings",
                    "",
                ]
            )
            for warning in self.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        if self.recommendations:
            lines.extend(
                [
                    "## 💡 Recommendations",
                    "",
                ]
            )
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


class CompatibilityReporter:
    """Analyze and report on conditional execution compatibility."""

    def __init__(self):
        """Initialize compatibility reporter."""
        self.analyzer = None

    def analyze_workflow(self, workflow: Workflow) -> CompatibilityReport:
        """Analyze workflow compatibility with conditional execution.

        Args:
            workflow: Workflow to analyze

        Returns:
            Comprehensive compatibility report
        """
        self.analyzer = ConditionalBranchAnalyzer(workflow)

        # Initialize report
        report = CompatibilityReport(
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.name or "Unnamed Workflow",
            overall_compatibility=CompatibilityLevel.FULLY_COMPATIBLE,
            node_count=len(workflow.graph.nodes()),
            switch_count=len(self.analyzer._find_switch_nodes()),
        )

        # Analyze various patterns
        self._analyze_basic_switches(report)
        self._analyze_cycles(workflow, report)
        self._analyze_merge_nodes(workflow, report)
        self._analyze_hierarchical_switches(report)
        self._analyze_complex_dependencies(workflow, report)

        # Determine overall compatibility
        self._determine_overall_compatibility(report)

        # Add performance estimate
        self._add_performance_estimate(report)

        # Generate recommendations
        self._generate_recommendations(report)

        return report

    def _analyze_basic_switches(self, report: CompatibilityReport) -> None:
        """Analyze basic switch patterns."""
        switch_nodes = self.analyzer._find_switch_nodes()

        if switch_nodes:
            # Check for simple conditional routing
            simple_switches = []
            complex_switches = []

            for switch_id in switch_nodes:
                branch_map = self.analyzer._get_switch_branch_map(switch_id)
                if len(branch_map) <= 2:  # true/false outputs
                    simple_switches.append(switch_id)
                else:
                    complex_switches.append(switch_id)

            if simple_switches:
                report.detected_patterns.append(
                    PatternInfo(
                        pattern_type="Simple Conditional Routing",
                        node_ids=simple_switches,
                        description="Basic true/false conditional branches",
                        compatibility=CompatibilityLevel.FULLY_COMPATIBLE,
                    )
                )

            if complex_switches:
                report.detected_patterns.append(
                    PatternInfo(
                        pattern_type="Multi-Case Switches",
                        node_ids=complex_switches,
                        description="Switches with multiple output cases",
                        compatibility=CompatibilityLevel.FULLY_COMPATIBLE,
                        recommendation="Multi-case switches are supported and will benefit from branch pruning",
                    )
                )

            # Also check for switches configured with cases parameter
            for switch_id in switch_nodes:
                node_data = self.analyzer.workflow.graph.nodes[switch_id]
                node_config = node_data.get("config", {})
                if "cases" in node_config and node_config["cases"]:
                    if switch_id not in complex_switches:
                        report.detected_patterns.append(
                            PatternInfo(
                                pattern_type="Multi-Case Switches",
                                node_ids=[switch_id],
                                description=f"Switch with {len(node_config['cases'])} cases",
                                compatibility=CompatibilityLevel.FULLY_COMPATIBLE,
                                recommendation="Multi-case switches are supported and will benefit from branch pruning",
                            )
                        )

    def _analyze_cycles(self, workflow: Workflow, report: CompatibilityReport) -> None:
        """Analyze cycle patterns."""
        try:
            import networkx as nx

            cycles = list(nx.simple_cycles(workflow.graph))

            if cycles:
                # Check if cycles contain switches
                switch_nodes = set(self.analyzer._find_switch_nodes())
                cycles_with_switches = []

                for cycle in cycles:
                    if any(node in switch_nodes for node in cycle):
                        cycles_with_switches.append(cycle)

                if cycles_with_switches:
                    report.detected_patterns.append(
                        PatternInfo(
                            pattern_type="Cycles with Conditional Routing",
                            node_ids=[
                                node for cycle in cycles_with_switches for node in cycle
                            ],
                            description="Cyclic workflows with conditional branches",
                            compatibility=CompatibilityLevel.PARTIALLY_COMPATIBLE,
                            recommendation="Conditional execution is disabled for cyclic workflows to prevent infinite loops",
                        )
                    )
                    report.warnings.append(
                        "Workflow contains cycles. Conditional execution will fall back to standard mode."
                    )
                    report.overall_compatibility = (
                        CompatibilityLevel.PARTIALLY_COMPATIBLE
                    )
                else:
                    report.detected_patterns.append(
                        PatternInfo(
                            pattern_type="Cycles without Switches",
                            node_ids=[node for cycle in cycles for node in cycle],
                            description="Cyclic workflows without conditional routing",
                            compatibility=CompatibilityLevel.PARTIALLY_COMPATIBLE,
                        )
                    )

        except Exception as e:
            logger.warning(f"Error analyzing cycles: {e}")

    def _analyze_merge_nodes(
        self, workflow: Workflow, report: CompatibilityReport
    ) -> None:
        """Analyze merge node patterns."""
        # Look for nodes with multiple incoming edges (potential merge points)
        merge_candidates = []

        for node_id in workflow.graph.nodes():
            in_degree = workflow.graph.in_degree(node_id)
            if in_degree > 1:
                # Check if any incoming edges are from switches
                incoming_from_switches = False
                for pred in workflow.graph.predecessors(node_id):
                    node_data = workflow.graph.nodes[pred]
                    node_instance = node_data.get("node") or node_data.get("instance")
                    if node_instance and "Switch" in node_instance.__class__.__name__:
                        incoming_from_switches = True
                        break

                if incoming_from_switches:
                    merge_candidates.append(node_id)

        if merge_candidates:
            # Check for MergeNode type
            actual_merge_nodes = []
            implicit_merge_nodes = []

            for node_id in merge_candidates:
                node_data = workflow.graph.nodes[node_id]
                node_instance = node_data.get("node") or node_data.get("instance")
                if node_instance and "Merge" in node_instance.__class__.__name__:
                    actual_merge_nodes.append(node_id)
                else:
                    implicit_merge_nodes.append(node_id)

            if actual_merge_nodes:
                report.detected_patterns.append(
                    PatternInfo(
                        pattern_type="Merge Nodes with Conditional Inputs",
                        node_ids=actual_merge_nodes,
                        description="MergeNodes receiving conditional branches",
                        compatibility=CompatibilityLevel.FULLY_COMPATIBLE,
                        recommendation="MergeNodes handle conditional inputs gracefully",
                    )
                )

            if implicit_merge_nodes:
                report.detected_patterns.append(
                    PatternInfo(
                        pattern_type="Implicit Merge Points",
                        node_ids=implicit_merge_nodes,
                        description="Regular nodes receiving multiple conditional inputs",
                        compatibility=CompatibilityLevel.PARTIALLY_COMPATIBLE,
                        recommendation="Consider using explicit MergeNode for better handling",
                    )
                )
                report.warnings.append(
                    f"Nodes {implicit_merge_nodes} receive multiple conditional inputs without explicit merge handling"
                )

    def _analyze_hierarchical_switches(self, report: CompatibilityReport) -> None:
        """Analyze hierarchical switch patterns."""
        switch_nodes = self.analyzer._find_switch_nodes()

        if len(switch_nodes) > 1:
            # Check for dependencies between switches
            hierarchies = self.analyzer.detect_switch_hierarchies()

            if hierarchies:
                for hierarchy in hierarchies:
                    if len(hierarchy["layers"]) > 1:
                        all_switches = [
                            s for layer in hierarchy["layers"] for s in layer
                        ]
                        report.detected_patterns.append(
                            PatternInfo(
                                pattern_type="Hierarchical Switches",
                                node_ids=all_switches,
                                description=f"{len(hierarchy['layers'])} layers of dependent switches",
                                compatibility=CompatibilityLevel.PARTIALLY_COMPATIBLE,
                                recommendation="Complex hierarchies may require careful testing",
                            )
                        )

                        if len(hierarchy["layers"]) > 3:
                            report.warnings.append(
                                "Deep switch hierarchies (>3 levels) may impact performance"
                            )

    def _analyze_complex_dependencies(
        self, workflow: Workflow, report: CompatibilityReport
    ) -> None:
        """Analyze complex dependency patterns."""
        # Check for nodes that depend on multiple switches
        switch_nodes = set(self.analyzer._find_switch_nodes())

        for node_id in workflow.graph.nodes():
            if node_id in switch_nodes:
                continue

            # Find all upstream switches
            upstream_switches = set()
            for pred in workflow.graph.predecessors(node_id):
                if pred in switch_nodes:
                    upstream_switches.add(pred)

            if len(upstream_switches) > 2:
                report.detected_patterns.append(
                    PatternInfo(
                        pattern_type="Complex Switch Dependencies",
                        node_ids=[node_id],
                        description=f"Node depends on {len(upstream_switches)} switches",
                        compatibility=CompatibilityLevel.PARTIALLY_COMPATIBLE,
                        recommendation="Complex dependencies are supported but may benefit from refactoring",
                    )
                )

    def _determine_overall_compatibility(self, report: CompatibilityReport) -> None:
        """Determine overall compatibility level."""
        if not report.detected_patterns:
            return

        # Check pattern compatibility levels
        has_incompatible = any(
            p.compatibility == CompatibilityLevel.INCOMPATIBLE
            for p in report.detected_patterns
        )
        has_partial = any(
            p.compatibility == CompatibilityLevel.PARTIALLY_COMPATIBLE
            for p in report.detected_patterns
        )

        if has_incompatible:
            report.overall_compatibility = CompatibilityLevel.INCOMPATIBLE
        elif has_partial:
            report.overall_compatibility = CompatibilityLevel.PARTIALLY_COMPATIBLE
        else:
            report.overall_compatibility = CompatibilityLevel.FULLY_COMPATIBLE

    def _add_performance_estimate(self, report: CompatibilityReport) -> None:
        """Add performance improvement estimate."""
        if report.switch_count == 0:
            report.execution_estimate = (
                "No conditional branches detected. No performance improvement expected."
            )
            return

        # Estimate based on switch patterns
        total_branches = sum(
            len(self.analyzer._get_switch_branch_map(switch_id))
            for switch_id in self.analyzer._find_switch_nodes()
        )

        avg_branches_per_switch = (
            total_branches / report.switch_count if report.switch_count > 0 else 0
        )

        # Rough estimate based on branching factor
        if avg_branches_per_switch <= 2:
            min_improvement = 20
            max_improvement = 30
        elif avg_branches_per_switch <= 4:
            min_improvement = 30
            max_improvement = 40
        else:
            min_improvement = 40
            max_improvement = 50

        # Adjust for complexity
        if report.overall_compatibility == CompatibilityLevel.PARTIALLY_COMPATIBLE:
            min_improvement *= 0.7
            max_improvement *= 0.7

        report.execution_estimate = (
            f"Expected performance improvement: {min_improvement:.0f}-{max_improvement:.0f}% "
            f"reduction in execution time with conditional execution enabled."
        )

    def _generate_recommendations(self, report: CompatibilityReport) -> None:
        """Generate actionable recommendations."""
        if report.overall_compatibility == CompatibilityLevel.FULLY_COMPATIBLE:
            report.recommendations.append(
                "Workflow is fully compatible with conditional execution. "
                "Enable with: LocalRuntime(conditional_execution='skip_branches')"
            )

        if report.warnings:
            report.recommendations.append(
                "Review warnings above and consider workflow refactoring for optimal performance"
            )

        # Check for optimization opportunities
        simple_switch_count = sum(
            1
            for p in report.detected_patterns
            if p.pattern_type == "Simple Conditional Routing"
        )

        if simple_switch_count > 5:
            report.recommendations.append(
                f"With {simple_switch_count} conditional branches, consider consolidating "
                "related logic to reduce workflow complexity"
            )

        # Performance testing recommendation
        if report.switch_count > 0:
            report.recommendations.append(
                "Run performance benchmarks to validate improvement estimates: "
                "python -m kailash.tools.benchmark_conditional <workflow_file>"
            )
