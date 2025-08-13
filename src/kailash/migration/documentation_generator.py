"""Automated documentation generator for LocalRuntime migration guides.

This module generates comprehensive migration documentation based on analysis
results, configuration changes, and best practices. It creates tailored
migration guides for different scenarios and audiences.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .compatibility_checker import (
    AnalysisResult,
    CompatibilityChecker,
    IssueSeverity,
    IssueType,
)
from .configuration_validator import ConfigurationValidator, ValidationResult
from .migration_assistant import MigrationAssistant, MigrationPlan, MigrationResult
from .performance_comparator import PerformanceComparator, PerformanceReport


@dataclass
class DocumentationSection:
    """A section of migration documentation."""

    title: str
    content: str
    order: int = 0
    audience: str = "all"  # "developer", "admin", "architect", "all"
    importance: str = "medium"  # "critical", "high", "medium", "low"


@dataclass
class MigrationGuide:
    """Complete migration guide with all sections."""

    title: str
    sections: List[DocumentationSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_section(self, section: DocumentationSection) -> None:
        """Add a section to the guide."""
        self.sections.append(section)
        # Keep sections sorted by order
        self.sections.sort(key=lambda s: s.order)


class MigrationDocGenerator:
    """Automated generator for migration documentation and guides."""

    def __init__(self):
        """Initialize the documentation generator."""
        self.template_sections = {
            "overview": self._generate_overview_section,
            "prerequisites": self._generate_prerequisites_section,
            "compatibility": self._generate_compatibility_section,
            "migration_steps": self._generate_migration_steps_section,
            "configuration": self._generate_configuration_section,
            "performance": self._generate_performance_section,
            "validation": self._generate_validation_section,
            "troubleshooting": self._generate_troubleshooting_section,
            "best_practices": self._generate_best_practices_section,
            "rollback": self._generate_rollback_section,
            "enterprise": self._generate_enterprise_section,
            "appendix": self._generate_appendix_section,
        }

        # Documentation templates for different scenarios
        self.scenario_templates = {
            "simple": ["overview", "migration_steps", "validation", "troubleshooting"],
            "standard": [
                "overview",
                "prerequisites",
                "compatibility",
                "migration_steps",
                "configuration",
                "validation",
                "troubleshooting",
                "best_practices",
            ],
            "enterprise": [
                "overview",
                "prerequisites",
                "compatibility",
                "migration_steps",
                "configuration",
                "performance",
                "validation",
                "enterprise",
                "troubleshooting",
                "best_practices",
                "rollback",
                "appendix",
            ],
            "performance_critical": [
                "overview",
                "prerequisites",
                "performance",
                "migration_steps",
                "configuration",
                "validation",
                "troubleshooting",
                "rollback",
            ],
        }

    def generate_migration_guide(
        self,
        analysis_result: Optional[AnalysisResult] = None,
        migration_plan: Optional[MigrationPlan] = None,
        migration_result: Optional[MigrationResult] = None,
        performance_report: Optional[PerformanceReport] = None,
        validation_result: Optional[ValidationResult] = None,
        scenario: str = "standard",
        audience: str = "developer",
    ) -> MigrationGuide:
        """Generate a comprehensive migration guide.

        Args:
            analysis_result: Compatibility analysis results
            migration_plan: Migration execution plan
            migration_result: Migration execution results
            performance_report: Performance comparison results
            validation_result: Configuration validation results
            scenario: Documentation scenario template
            audience: Target audience

        Returns:
            Complete migration guide
        """
        guide = MigrationGuide(title="LocalRuntime Migration Guide")
        guide.metadata = {
            "scenario": scenario,
            "audience": audience,
            "has_analysis": analysis_result is not None,
            "has_migration_plan": migration_plan is not None,
            "has_migration_result": migration_result is not None,
            "has_performance_report": performance_report is not None,
            "has_validation_result": validation_result is not None,
        }

        # Get template sections for the scenario
        sections_to_generate = self.scenario_templates.get(
            scenario, self.scenario_templates["standard"]
        )

        # Generate each section
        for order, section_name in enumerate(sections_to_generate, 1):
            if section_name in self.template_sections:
                section = self.template_sections[section_name](
                    order,
                    audience,
                    analysis_result,
                    migration_plan,
                    migration_result,
                    performance_report,
                    validation_result,
                )
                if section:  # Only add non-empty sections
                    guide.add_section(section)

        return guide

    def _generate_overview_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate overview section."""
        content = []
        content.append("# Migration Overview")
        content.append("")
        content.append(
            "This guide provides comprehensive instructions for migrating to the enhanced LocalRuntime."
        )
        content.append(
            "The enhanced LocalRuntime offers improved performance, enterprise features, and better"
        )
        content.append("resource management while maintaining backward compatibility.")
        content.append("")

        # Add scenario-specific information
        if analysis_result:
            complexity = analysis_result.migration_complexity
            effort_days = analysis_result.estimated_effort_days

            content.append("## Migration Complexity Assessment")
            content.append("")
            content.append(f"- **Complexity Level**: {complexity.title()}")
            content.append(f"- **Estimated Effort**: {effort_days} days")
            content.append(
                f"- **Files to Modify**: {analysis_result.total_files_analyzed}"
            )
            content.append(
                f"- **Issues Identified**: {analysis_result.summary.get('total_issues', 0)}"
            )
            content.append("")

        # Add performance overview
        if performance_report:
            overall_change = performance_report.overall_change_percentage
            status = (
                "improvement"
                if performance_report.overall_improvement
                else "regression"
            )

            content.append("## Performance Impact")
            content.append("")
            content.append(f"- **Overall Performance Change**: {overall_change:+.1f}%")
            content.append(f"- **Performance Assessment**: {status.title()}")
            content.append(
                f"- **Risk Level**: {performance_report.risk_assessment.title()}"
            )
            content.append("")

        content.append("## Key Benefits")
        content.append("")
        content.append(
            "- **Enhanced Performance**: Optimized execution engine with better resource management"
        )
        content.append(
            "- **Enterprise Features**: Advanced monitoring, security, and audit capabilities"
        )
        content.append(
            "- **Improved Reliability**: Circuit breakers, retry policies, and error handling"
        )
        content.append(
            "- **Better Observability**: Comprehensive metrics and monitoring"
        )
        content.append(
            "- **Backward Compatibility**: Existing workflows continue to work with minimal changes"
        )

        return DocumentationSection(
            title="Overview",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="critical",
        )

    def _generate_prerequisites_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate prerequisites section."""
        content = []
        content.append("# Prerequisites")
        content.append("")
        content.append(
            "Before beginning the migration, ensure you have completed the following prerequisites:"
        )
        content.append("")

        content.append("## System Requirements")
        content.append("")
        content.append("- Python 3.8 or higher")
        content.append("- Kailash SDK version 0.9.15 or higher")
        content.append("- Sufficient system resources (RAM: 2GB+, CPU: 2 cores+)")
        content.append("- Network access for package installation")
        content.append("")

        content.append("## Preparation Steps")
        content.append("")
        content.append("1. **Backup Your Codebase**")
        content.append("   ```bash")
        content.append("   git checkout -b pre-migration-backup")
        content.append("   git push origin pre-migration-backup")
        content.append("   ```")
        content.append("")
        content.append("2. **Verify Current Installation**")
        content.append("   ```python")
        content.append("   import kailash")
        content.append("   print(kailash.__version__)")
        content.append("   ```")
        content.append("")
        content.append("3. **Run Existing Tests**")
        content.append("   ```bash")
        content.append("   python -m pytest tests/")
        content.append("   ```")
        content.append("")

        # Add specific prerequisites based on analysis
        if migration_plan and migration_plan.prerequisites:
            content.append("## Project-Specific Prerequisites")
            content.append("")
            for prereq in migration_plan.prerequisites:
                content.append(f"- {prereq}")
            content.append("")

        content.append("## Knowledge Requirements")
        content.append("")
        if audience == "developer":
            content.append("- Familiarity with Kailash SDK and workflow concepts")
            content.append("- Understanding of LocalRuntime configuration")
            content.append("- Basic knowledge of Python async/await patterns")
        elif audience == "admin":
            content.append("- System administration experience")
            content.append("- Understanding of resource management and monitoring")
            content.append("- Knowledge of security and compliance requirements")
        else:
            content.append(
                "- Basic understanding of the current Kailash implementation"
            )
            content.append("- Familiarity with workflow automation concepts")

        return DocumentationSection(
            title="Prerequisites",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="high",
        )

    def _generate_compatibility_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> Optional[DocumentationSection]:
        """Generate compatibility analysis section."""
        if not analysis_result:
            return None

        content = []
        content.append("# Compatibility Analysis")
        content.append("")
        content.append(
            "This section details the compatibility issues identified in your codebase"
        )
        content.append("and provides specific guidance for addressing them.")
        content.append("")

        # Summary
        content.append("## Summary")
        content.append("")
        content.append(
            f"- **Total Issues**: {analysis_result.summary.get('total_issues', 0)}"
        )
        content.append(
            f"- **Critical Issues**: {analysis_result.summary.get('critical_issues', 0)}"
        )
        content.append(
            f"- **Breaking Changes**: {analysis_result.summary.get('breaking_changes', 0)}"
        )
        content.append(
            f"- **Automated Fixes**: {analysis_result.summary.get('automated_fixes', 0)}"
        )
        content.append("")

        # Critical issues that must be addressed
        critical_issues = [
            i for i in analysis_result.issues if i.severity == IssueSeverity.CRITICAL
        ]
        if critical_issues:
            content.append("## Critical Issues (Must Fix)")
            content.append("")
            content.append(
                "These issues will prevent the migration from succeeding and must be resolved:"
            )
            content.append("")

            for issue in critical_issues:
                content.append(f"### {issue.description}")
                content.append("")
                content.append(f"**File**: `{issue.file_path}:{issue.line_number}`")
                content.append("")
                if issue.code_snippet:
                    content.append("**Current Code**:")
                    content.append("```python")
                    content.append(issue.code_snippet)
                    content.append("```")
                    content.append("")
                content.append(f"**Solution**: {issue.recommendation}")
                content.append("")

        # Breaking changes
        breaking_changes = [i for i in analysis_result.issues if i.breaking_change]
        if breaking_changes:
            content.append("## Breaking Changes")
            content.append("")
            content.append("The following changes require code modifications:")
            content.append("")

            for issue in breaking_changes:
                content.append(f"- **{issue.description}**: {issue.recommendation}")
            content.append("")

        # Automated fixes
        auto_fixable = [i for i in analysis_result.issues if i.automated_fix]
        if auto_fixable:
            content.append("## Automated Fixes Available")
            content.append("")
            content.append(
                "These issues can be automatically resolved by the migration tool:"
            )
            content.append("")

            for issue in auto_fixable:
                content.append(f"- {issue.description}")
            content.append("")

        # Enterprise opportunities
        if analysis_result.enterprise_opportunities:
            content.append("## Enterprise Feature Opportunities")
            content.append("")
            content.append("Consider upgrading to these enterprise features:")
            content.append("")
            for opportunity in analysis_result.enterprise_opportunities:
                content.append(f"- {opportunity}")
            content.append("")

        return DocumentationSection(
            title="Compatibility Analysis",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="high",
        )

    def _generate_migration_steps_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate detailed migration steps section."""
        content = []
        content.append("# Migration Steps")
        content.append("")

        if migration_plan:
            content.append("## Automated Migration Plan")
            content.append("")
            content.append(
                f"**Estimated Duration**: {migration_plan.estimated_duration_minutes} minutes"
            )
            content.append(f"**Risk Level**: {migration_plan.risk_level.title()}")
            content.append("")

            content.append("### Step-by-Step Process")
            content.append("")

            for i, step in enumerate(migration_plan.steps, 1):
                content.append(f"{i}. **{step.description}**")
                content.append(f"   - File: `{step.file_path}`")
                content.append(f"   - Automated: {'Yes' if step.automated else 'No'}")
                if step.validation_required:
                    content.append(
                        "   - **Note**: Manual validation required after this step"
                    )
                content.append("")
        else:
            content.append("## Manual Migration Process")
            content.append("")

        content.append("### 1. Install Enhanced LocalRuntime")
        content.append("")
        content.append("```bash")
        content.append("pip install --upgrade kailash")
        content.append("```")
        content.append("")

        content.append("### 2. Update Import Statements")
        content.append("")
        content.append("Ensure you're importing from the correct modules:")
        content.append("")
        content.append("```python")
        content.append("from kailash.runtime.local import LocalRuntime")
        content.append("from kailash.workflow.builder import WorkflowBuilder")
        content.append("```")
        content.append("")

        content.append("### 3. Update LocalRuntime Configuration")
        content.append("")
        content.append("**Before (Legacy)**:")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_parallel=True,")
        content.append("    thread_pool_size=5,")
        content.append("    debug_mode=True")
        content.append(")")
        content.append("```")
        content.append("")
        content.append("**After (Enhanced)**:")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    max_concurrency=5,")
        content.append("    debug=True,")
        content.append("    enable_monitoring=True")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### 4. Update Execution Patterns")
        content.append("")
        content.append("**Before**:")
        content.append("```python")
        content.append("runtime.execute_sync(workflow)")
        content.append("results = runtime.get_results()")
        content.append("```")
        content.append("")
        content.append("**After**:")
        content.append("```python")
        content.append("results, run_id = runtime.execute(workflow)")
        content.append("```")
        content.append("")

        content.append("### 5. Test Migration")
        content.append("")
        content.append("After making changes, test your workflows:")
        content.append("")
        content.append("```python")
        content.append("# Test basic functionality")
        content.append("from kailash.workflow.builder import WorkflowBuilder")
        content.append("from kailash.runtime.local import LocalRuntime")
        content.append("")
        content.append("workflow = WorkflowBuilder()")
        content.append("workflow.add_node('PythonCodeNode', 'test', {")
        content.append("    'code': 'result = \"Migration successful!\"',")
        content.append("    'output_key': 'message'")
        content.append("})")
        content.append("")
        content.append("runtime = LocalRuntime(debug=True)")
        content.append("results, run_id = runtime.execute(workflow.build())")
        content.append("print(results)")
        content.append("```")

        return DocumentationSection(
            title="Migration Steps",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="critical",
        )

    def _generate_configuration_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate configuration reference section."""
        content = []
        content.append("# Configuration Reference")
        content.append("")
        content.append(
            "This section provides comprehensive configuration options for the enhanced LocalRuntime."
        )
        content.append("")

        # Configuration validation results
        if validation_result:
            content.append("## Configuration Validation Results")
            content.append("")
            content.append(f"- **Valid**: {'Yes' if validation_result.valid else 'No'}")
            content.append(
                f"- **Security Score**: {validation_result.security_score}/100"
            )
            content.append(
                f"- **Performance Score**: {validation_result.performance_score}/100"
            )
            content.append(
                f"- **Enterprise Readiness**: {validation_result.enterprise_readiness}/100"
            )
            content.append("")

            if validation_result.optimized_config:
                content.append("### Optimized Configuration")
                content.append("")
                content.append(
                    "Based on validation results, here's an optimized configuration:"
                )
                content.append("")
                content.append("```python")
                content.append("runtime = LocalRuntime(")
                for key, value in validation_result.optimized_config.items():
                    if isinstance(value, str):
                        content.append(f'    {key}="{value}",')
                    else:
                        content.append(f"    {key}={value},")
                content.append(")")
                content.append("```")
                content.append("")

        content.append("## Core Parameters")
        content.append("")
        content.append("### Basic Configuration")
        content.append("")
        content.append("| Parameter | Type | Default | Description |")
        content.append("|-----------|------|---------|-------------|")
        content.append("| `debug` | bool | False | Enable debug logging |")
        content.append(
            "| `enable_cycles` | bool | True | Enable cyclic workflow support |"
        )
        content.append("| `enable_async` | bool | True | Enable async node execution |")
        content.append(
            "| `max_concurrency` | int | 10 | Maximum concurrent operations |"
        )
        content.append("")

        content.append("### Performance Configuration")
        content.append("")
        content.append("| Parameter | Type | Default | Description |")
        content.append("|-----------|------|---------|-------------|")
        content.append(
            "| `persistent_mode` | bool | False | Enable persistent resource mode |"
        )
        content.append(
            "| `enable_connection_sharing` | bool | True | Enable connection pooling |"
        )
        content.append(
            "| `max_concurrent_workflows` | int | 10 | Max concurrent workflows |"
        )
        content.append("| `connection_pool_size` | int | 20 | Connection pool size |")
        content.append("")

        content.append("### Enterprise Configuration")
        content.append("")
        content.append("| Parameter | Type | Default | Description |")
        content.append("|-----------|------|---------|-------------|")
        content.append(
            "| `enable_monitoring` | bool | True | Enable performance monitoring |"
        )
        content.append(
            "| `enable_security` | bool | False | Enable security features |"
        )
        content.append("| `enable_audit` | bool | False | Enable audit logging |")
        content.append(
            "| `user_context` | UserContext | None | User authentication context |"
        )
        content.append("")

        content.append("## Configuration Examples")
        content.append("")

        content.append("### Development Configuration")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    debug=True,")
        content.append("    max_concurrency=2,")
        content.append("    enable_monitoring=True")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Production Configuration")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    debug=False,")
        content.append("    max_concurrency=20,")
        content.append("    persistent_mode=True,")
        content.append("    enable_monitoring=True,")
        content.append("    enable_security=True,")
        content.append("    resource_limits={")
        content.append("        'memory_mb': 2048,")
        content.append("        'timeout_seconds': 300")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Enterprise Configuration")
        content.append("```python")
        content.append("from kailash.access_control import UserContext")
        content.append("")
        content.append(
            "user_context = UserContext(user_id='user123', roles=['analyst'])"
        )
        content.append("")
        content.append("runtime = LocalRuntime(")
        content.append("    max_concurrency=50,")
        content.append("    persistent_mode=True,")
        content.append("    enable_monitoring=True,")
        content.append("    enable_security=True,")
        content.append("    enable_audit=True,")
        content.append("    enable_enterprise_monitoring=True,")
        content.append("    user_context=user_context,")
        content.append("    circuit_breaker_config={")
        content.append("        'failure_threshold': 5,")
        content.append("        'recovery_timeout': 60")
        content.append("    }")
        content.append(")")
        content.append("```")

        return DocumentationSection(
            title="Configuration Reference",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="high",
        )

    def _generate_performance_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> Optional[DocumentationSection]:
        """Generate performance analysis section."""
        if not performance_report:
            return None

        content = []
        content.append("# Performance Analysis")
        content.append("")
        content.append(
            "This section details the performance impact of migrating to the enhanced LocalRuntime."
        )
        content.append("")

        # Executive summary
        content.append("## Performance Summary")
        content.append("")
        content.append(
            f"- **Overall Performance Change**: {performance_report.overall_change_percentage:+.1f}%"
        )
        content.append(
            f"- **Performance Status**: {'Improvement' if performance_report.overall_improvement else 'Regression'}"
        )
        content.append(
            f"- **Risk Assessment**: {performance_report.risk_assessment.title()}"
        )
        content.append("")

        # Detailed metrics
        content.append("## Detailed Performance Metrics")
        content.append("")
        content.append("| Metric | Before | After | Change | Status |")
        content.append("|--------|---------|--------|---------|---------|")

        for comparison in performance_report.comparisons:
            status = "✅ Better" if comparison.improvement else "❌ Worse"
            if comparison.significance == "negligible":
                status = "➡️ Same"

            content.append(
                f"| {comparison.metric_name.replace('_', ' ').title()} | "
                f"{comparison.before_value:.2f} {comparison.unit} | "
                f"{comparison.after_value:.2f} {comparison.unit} | "
                f"{comparison.change_percentage:+.1f}% | "
                f"{status} |"
            )
        content.append("")

        # Performance recommendations
        if performance_report.recommendations:
            content.append("## Performance Recommendations")
            content.append("")
            for i, rec in enumerate(performance_report.recommendations, 1):
                content.append(f"{i}. {rec}")
            content.append("")

        # Optimization tips
        content.append("## Performance Optimization Tips")
        content.append("")
        content.append("### General Optimizations")
        content.append(
            "- **Connection Pooling**: Enable `enable_connection_sharing=True`"
        )
        content.append(
            "- **Persistent Mode**: Use `persistent_mode=True` for long-running applications"
        )
        content.append(
            "- **Concurrency Tuning**: Adjust `max_concurrency` based on your workload"
        )
        content.append(
            "- **Resource Limits**: Set appropriate `resource_limits` to prevent resource exhaustion"
        )
        content.append("")

        content.append("### Monitoring Performance")
        content.append("```python")
        content.append("# Enable performance monitoring")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_monitoring=True,")
        content.append("    enable_enterprise_monitoring=True")
        content.append(")")
        content.append("")
        content.append("# Access performance metrics")
        content.append("results, run_id = runtime.execute(workflow)")
        content.append(
            "# Metrics are automatically collected and available via monitoring nodes"
        )
        content.append("```")

        return DocumentationSection(
            title="Performance Analysis",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="high",
        )

    def _generate_validation_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate validation and testing section."""
        content = []
        content.append("# Validation and Testing")
        content.append("")
        content.append(
            "This section provides comprehensive testing strategies to validate your migration."
        )
        content.append("")

        # Migration validation results
        if migration_result:
            content.append("## Migration Results")
            content.append("")
            content.append(
                f"- **Migration Success**: {'Yes' if migration_result.success else 'No'}"
            )
            content.append(f"- **Steps Completed**: {migration_result.steps_completed}")
            content.append(f"- **Steps Failed**: {migration_result.steps_failed}")

            if migration_result.backup_path:
                content.append(
                    f"- **Backup Location**: `{migration_result.backup_path}`"
                )

            if migration_result.errors:
                content.append("")
                content.append("### Migration Errors")
                for error in migration_result.errors:
                    content.append(f"- {error}")

            content.append("")

        content.append("## Validation Checklist")
        content.append("")
        content.append("### Basic Functionality")
        content.append("- [ ] LocalRuntime imports successfully")
        content.append("- [ ] Basic workflow executes without errors")
        content.append("- [ ] Results are returned correctly")
        content.append("- [ ] No syntax errors in modified files")
        content.append("")

        content.append("### Integration Testing")
        content.append("- [ ] All existing tests pass")
        content.append("- [ ] Workflow parameters work correctly")
        content.append("- [ ] Node connections function properly")
        content.append("- [ ] Error handling works as expected")
        content.append("")

        content.append("### Performance Testing")
        content.append("- [ ] Execution times are acceptable")
        content.append("- [ ] Memory usage is within limits")
        content.append("- [ ] Concurrent execution works properly")
        content.append("- [ ] Resource cleanup functions correctly")
        content.append("")

        # Test scripts
        content.append("## Test Scripts")
        content.append("")

        content.append("### Basic Validation Test")
        content.append("```python")
        content.append("#!/usr/bin/env python3")
        content.append('"""Basic validation test for LocalRuntime migration."""')
        content.append("")
        content.append("from kailash.workflow.builder import WorkflowBuilder")
        content.append("from kailash.runtime.local import LocalRuntime")
        content.append("")
        content.append("def test_basic_functionality():")
        content.append('    """Test basic LocalRuntime functionality."""')
        content.append("    # Create a simple workflow")
        content.append("    workflow = WorkflowBuilder()")
        content.append("    workflow.add_node('PythonCodeNode', 'test_node', {")
        content.append("        'code': 'result = 42',")
        content.append("        'output_key': 'answer'")
        content.append("    })")
        content.append("")
        content.append("    # Execute with enhanced runtime")
        content.append("    runtime = LocalRuntime(debug=True)")
        content.append("    results, run_id = runtime.execute(workflow.build())")
        content.append("")
        content.append("    # Validate results")
        content.append("    assert results is not None")
        content.append("    assert 'test_node' in results")
        content.append("    assert results['test_node']['answer'] == 42")
        content.append('    print("✅ Basic functionality test passed")')
        content.append("")
        content.append("if __name__ == '__main__':")
        content.append("    test_basic_functionality()")
        content.append("```")
        content.append("")

        content.append("### Performance Validation Test")
        content.append("```python")
        content.append("#!/usr/bin/env python3")
        content.append('"""Performance validation test for LocalRuntime migration."""')
        content.append("")
        content.append("import time")
        content.append("from kailash.workflow.builder import WorkflowBuilder")
        content.append("from kailash.runtime.local import LocalRuntime")
        content.append("")
        content.append("def test_performance():")
        content.append('    """Test performance characteristics."""')
        content.append("    workflow = WorkflowBuilder()")
        content.append("    workflow.add_node('PythonCodeNode', 'perf_test', {")
        content.append("        'code': 'result = sum(range(10000))',")
        content.append("        'output_key': 'sum_result'")
        content.append("    })")
        content.append("")
        content.append("    runtime = LocalRuntime(")
        content.append("        max_concurrency=5,")
        content.append("        enable_monitoring=True")
        content.append("    )")
        content.append("")
        content.append("    # Time the execution")
        content.append("    start_time = time.time()")
        content.append("    results, run_id = runtime.execute(workflow.build())")
        content.append("    execution_time = time.time() - start_time")
        content.append("")
        content.append("    print(f'Execution time: {execution_time:.2f} seconds')")
        content.append(
            "    assert execution_time < 5.0  # Should complete in under 5 seconds"
        )
        content.append('    print("✅ Performance test passed")')
        content.append("")
        content.append("if __name__ == '__main__':")
        content.append("    test_performance()")
        content.append("```")

        return DocumentationSection(
            title="Validation and Testing",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="high",
        )

    def _generate_troubleshooting_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate troubleshooting section."""
        content = []
        content.append("# Troubleshooting")
        content.append("")
        content.append("This section provides solutions to common migration issues.")
        content.append("")

        content.append("## Common Issues")
        content.append("")

        content.append("### ImportError: LocalRuntime Not Found")
        content.append("")
        content.append("**Problem**: Import errors when trying to use LocalRuntime")
        content.append("")
        content.append("**Solution**:")
        content.append("```bash")
        content.append("# Ensure latest version is installed")
        content.append("pip install --upgrade kailash")
        content.append("")
        content.append("# Verify installation")
        content.append(
            "python -c \"from kailash.runtime.local import LocalRuntime; print('Success')\""
        )
        content.append("```")
        content.append("")

        content.append("### Configuration Parameter Errors")
        content.append("")
        content.append("**Problem**: Errors about unknown or deprecated parameters")
        content.append("")
        content.append(
            "**Solution**: Update parameter names according to the migration guide:"
        )
        content.append("- `enable_parallel` → `max_concurrency`")
        content.append("- `thread_pool_size` → `max_concurrency`")
        content.append("- `debug_mode` → `debug`")
        content.append("- `memory_limit` → `resource_limits`")
        content.append("")

        content.append("### Execution Method Errors")
        content.append("")
        content.append("**Problem**: Methods like `execute_sync()` not found")
        content.append("")
        content.append("**Solution**: Use the unified `execute()` method:")
        content.append("```python")
        content.append("# Old way")
        content.append("# runtime.execute_sync(workflow)")
        content.append("# results = runtime.get_results()")
        content.append("")
        content.append("# New way")
        content.append("results, run_id = runtime.execute(workflow)")
        content.append("```")
        content.append("")

        content.append("### Performance Issues")
        content.append("")
        content.append("**Problem**: Slower execution after migration")
        content.append("")
        content.append("**Solutions**:")
        content.append("1. **Adjust Concurrency Settings**:")
        content.append("   ```python")
        content.append(
            "   runtime = LocalRuntime(max_concurrency=20)  # Increase if needed"
        )
        content.append("   ```")
        content.append("")
        content.append("2. **Enable Connection Pooling**:")
        content.append("   ```python")
        content.append("   runtime = LocalRuntime(")
        content.append("       enable_connection_sharing=True,")
        content.append("       persistent_mode=True")
        content.append("   )")
        content.append("   ```")
        content.append("")

        content.append("### Memory Issues")
        content.append("")
        content.append("**Problem**: High memory usage or out-of-memory errors")
        content.append("")
        content.append("**Solution**: Configure resource limits:")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    resource_limits={")
        content.append("        'memory_mb': 1024,  # Limit to 1GB")
        content.append("        'timeout_seconds': 300")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Security Conflicts")
        content.append("")
        content.append("**Problem**: Security-related errors or warnings")
        content.append("")
        content.append("**Solution**: Properly configure security features:")
        content.append("```python")
        content.append("from kailash.access_control import UserContext")
        content.append("")
        content.append("user_context = UserContext(user_id='user123')")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_security=True,")
        content.append("    user_context=user_context,")
        content.append("    debug=False  # Don't enable debug with security")
        content.append(")")
        content.append("```")
        content.append("")

        # Add specific troubleshooting based on results
        if migration_result and migration_result.errors:
            content.append("## Project-Specific Issues")
            content.append("")
            for error in migration_result.errors:
                content.append(f"- **Error**: {error}")
                content.append(
                    "  **Solution**: Review the specific error and check configuration parameters"
                )
                content.append("")

        content.append("## Getting Help")
        content.append("")
        content.append("If you continue to experience issues:")
        content.append("")
        content.append(
            "1. **Check Documentation**: Review the complete Kailash SDK documentation"
        )
        content.append("2. **Enable Debug Logging**:")
        content.append("   ```python")
        content.append("   import logging")
        content.append("   logging.basicConfig(level=logging.DEBUG)")
        content.append("   runtime = LocalRuntime(debug=True)")
        content.append("   ```")
        content.append(
            "3. **Create Minimal Reproduction**: Isolate the issue in a simple test case"
        )
        content.append(
            "4. **Contact Support**: Provide debug logs and configuration details"
        )

        return DocumentationSection(
            title="Troubleshooting",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="high",
        )

    def _generate_best_practices_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate best practices section."""
        content = []
        content.append("# Best Practices")
        content.append("")
        content.append(
            "This section outlines best practices for using the enhanced LocalRuntime effectively."
        )
        content.append("")

        content.append("## Configuration Best Practices")
        content.append("")
        content.append("### Environment-Specific Configuration")
        content.append("")
        content.append("**Development**:")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    debug=True,")
        content.append("    max_concurrency=2,  # Lower for easier debugging")
        content.append("    enable_monitoring=True")
        content.append(")")
        content.append("```")
        content.append("")
        content.append("**Production**:")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    debug=False,")
        content.append("    max_concurrency=20,")
        content.append("    persistent_mode=True,")
        content.append("    enable_monitoring=True,")
        content.append("    enable_security=True")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Resource Management")
        content.append("")
        content.append(
            "- **Set Resource Limits**: Always configure appropriate resource limits"
        )
        content.append(
            "- **Monitor Memory Usage**: Use monitoring features to track resource consumption"
        )
        content.append(
            "- **Connection Pooling**: Enable connection sharing for better performance"
        )
        content.append("- **Cleanup**: Properly dispose of resources when done")
        content.append("")

        content.append("## Security Best Practices")
        content.append("")
        content.append("### Authentication and Authorization")
        content.append("```python")
        content.append("from kailash.access_control import UserContext")
        content.append("")
        content.append("# Always use proper user context in production")
        content.append("user_context = UserContext(")
        content.append("    user_id='authenticated_user',")
        content.append("    roles=['workflow_executor'],")
        content.append("    permissions=['execute', 'read']")
        content.append(")")
        content.append("")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_security=True,")
        content.append("    enable_audit=True,")
        content.append("    user_context=user_context")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Audit and Compliance")
        content.append("- **Enable Audit Logging**: Track all workflow executions")
        content.append("- **Secure Credentials**: Use proper secret management")
        content.append("- **Access Control**: Implement role-based access control")
        content.append("- **Monitoring**: Monitor for security events and anomalies")
        content.append("")

        content.append("## Performance Best Practices")
        content.append("")
        content.append("### Concurrency Optimization")
        content.append("```python")
        content.append("# Optimize based on your workload")
        content.append("runtime = LocalRuntime(")
        content.append("    max_concurrency=min(cpu_count() * 2, 50),")
        content.append("    max_concurrent_workflows=10,")
        content.append("    connection_pool_size=100")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Monitoring and Observability")
        content.append("- **Enable Monitoring**: Use built-in performance monitoring")
        content.append(
            "- **Collect Metrics**: Implement comprehensive metrics collection"
        )
        content.append("- **Set Alerts**: Configure alerts for performance thresholds")
        content.append("- **Regular Reviews**: Periodically review performance metrics")
        content.append("")

        content.append("## Enterprise Features")
        content.append("")
        content.append("### Advanced Monitoring")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_monitoring=True,")
        content.append("    enable_enterprise_monitoring=True,")
        content.append("    enable_health_monitoring=True")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Resilience and Reliability")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    circuit_breaker_config={")
        content.append("        'failure_threshold': 5,")
        content.append("        'recovery_timeout': 60")
        content.append("    },")
        content.append("    retry_policy_config={")
        content.append("        'max_retries': 3,")
        content.append("        'backoff_factor': 2.0")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("## Code Organization")
        content.append("")
        content.append("### Configuration Management")
        content.append("```python")
        content.append("# config.py")
        content.append("import os")
        content.append("from kailash.access_control import UserContext")
        content.append("")
        content.append("def get_runtime_config():")
        content.append("    env = os.getenv('ENVIRONMENT', 'development')")
        content.append("    ")
        content.append("    base_config = {")
        content.append("        'enable_monitoring': True,")
        content.append("        'enable_connection_sharing': True")
        content.append("    }")
        content.append("    ")
        content.append("    if env == 'production':")
        content.append("        base_config.update({")
        content.append("            'debug': False,")
        content.append("            'max_concurrency': 20,")
        content.append("            'enable_security': True,")
        content.append("            'persistent_mode': True")
        content.append("        })")
        content.append("    else:")
        content.append("        base_config.update({")
        content.append("            'debug': True,")
        content.append("            'max_concurrency': 2")
        content.append("        })")
        content.append("    ")
        content.append("    return base_config")
        content.append("```")

        return DocumentationSection(
            title="Best Practices",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="medium",
        )

    def _generate_rollback_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate rollback procedures section."""
        content = []
        content.append("# Rollback Procedures")
        content.append("")
        content.append(
            "This section provides procedures for rolling back the migration if issues occur."
        )
        content.append("")

        if migration_result and migration_result.backup_path:
            content.append("## Automated Rollback")
            content.append("")
            content.append(
                f"A backup was created during migration at: `{migration_result.backup_path}`"
            )
            content.append("")
            content.append("### Quick Rollback")
            content.append("```bash")
            content.append("# Use the migration assistant to rollback")
            content.append('python -c "')
            content.append("from kailash.migration import MigrationAssistant")
            content.append("assistant = MigrationAssistant()")
            content.append("# Rollback using stored results")
            content.append('"')
            content.append("```")
            content.append("")

        content.append("## Manual Rollback")
        content.append("")
        content.append("### Git-based Rollback")
        content.append("")
        content.append("If you created a Git backup branch:")
        content.append("")
        content.append("```bash")
        content.append("# Rollback to pre-migration state")
        content.append("git checkout pre-migration-backup")
        content.append("git checkout -b rollback-$(date +%Y%m%d)")
        content.append("git merge main  # Resolve any conflicts")
        content.append("```")
        content.append("")

        content.append("### Package Rollback")
        content.append("")
        content.append("If you need to rollback to a previous SDK version:")
        content.append("")
        content.append("```bash")
        content.append("# Install specific version")
        content.append("pip install kailash==0.9.14  # Replace with desired version")
        content.append("")
        content.append("# Verify installation")
        content.append('python -c "import kailash; print(kailash.__version__)"')
        content.append("```")
        content.append("")

        content.append("## Rollback Checklist")
        content.append("")
        content.append("### Pre-Rollback")
        content.append("- [ ] Document the issues that prompted rollback")
        content.append("- [ ] Backup current state (even if problematic)")
        content.append("- [ ] Notify team members of rollback")
        content.append("- [ ] Prepare test plan for post-rollback validation")
        content.append("")

        content.append("### During Rollback")
        content.append("- [ ] Restore code to previous working state")
        content.append("- [ ] Restore configuration files")
        content.append("- [ ] Downgrade packages if necessary")
        content.append("- [ ] Clear any cached data or temporary files")
        content.append("")

        content.append("### Post-Rollback")
        content.append("- [ ] Run full test suite")
        content.append("- [ ] Verify all workflows execute correctly")
        content.append("- [ ] Check performance metrics")
        content.append("- [ ] Document lessons learned")
        content.append("- [ ] Plan remediation for next migration attempt")
        content.append("")

        content.append("## Prevention Strategies")
        content.append("")
        content.append("To avoid needing rollbacks in the future:")
        content.append("")
        content.append("### Staged Migration")
        content.append("1. **Develop**: Test migration on development environment")
        content.append("2. **Staging**: Full migration test on staging environment")
        content.append("3. **Canary**: Deploy to small subset of production")
        content.append("4. **Full Production**: Complete production deployment")
        content.append("")

        content.append("### Monitoring and Alerts")
        content.append("- Set up monitoring for key metrics before migration")
        content.append("- Configure alerts for performance regressions")
        content.append("- Implement automated health checks")
        content.append("- Plan rollback triggers and thresholds")
        content.append("")

        content.append("## Support and Recovery")
        content.append("")
        content.append("If rollback doesn't resolve all issues:")
        content.append("")
        content.append(
            "1. **Isolate the Problem**: Identify specific failing components"
        )
        content.append("2. **Minimal Reproduction**: Create simple test case")
        content.append(
            "3. **Documentation**: Gather logs, configurations, and error messages"
        )
        content.append(
            "4. **Expert Consultation**: Contact Kailash support with details"
        )

        return DocumentationSection(
            title="Rollback Procedures",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="medium",
        )

    def _generate_enterprise_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate enterprise features section."""
        content = []
        content.append("# Enterprise Features Guide")
        content.append("")
        content.append(
            "This section covers advanced enterprise features available in the enhanced LocalRuntime."
        )
        content.append("")

        content.append("## Security and Access Control")
        content.append("")
        content.append("### User Authentication")
        content.append("```python")
        content.append("from kailash.access_control import UserContext")
        content.append("")
        content.append("# Create user context with roles and permissions")
        content.append("user_context = UserContext(")
        content.append("    user_id='john.doe@company.com',")
        content.append("    roles=['data_analyst', 'workflow_admin'],")
        content.append("    permissions=['execute', 'read', 'write'],")
        content.append(
            "    metadata={'department': 'analytics', 'clearance': 'confidential'}"
        )
        content.append(")")
        content.append("")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_security=True,")
        content.append("    user_context=user_context")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Audit Logging")
        content.append("```python")
        content.append("# Enable comprehensive audit logging")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_security=True,")
        content.append("    enable_audit=True,")
        content.append("    user_context=user_context")
        content.append(")")
        content.append("")
        content.append("# All workflow executions are now logged with:")
        content.append("# - User identity and roles")
        content.append("# - Execution timestamps")
        content.append("# - Resource access patterns")
        content.append("# - Security events and violations")
        content.append("```")
        content.append("")

        content.append("## Advanced Monitoring")
        content.append("")
        content.append("### Enterprise Monitoring")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_monitoring=True,")
        content.append("    enable_enterprise_monitoring=True,")
        content.append("    enable_health_monitoring=True")
        content.append(")")
        content.append("")
        content.append("# Provides advanced metrics:")
        content.append("# - Real-time performance analytics")
        content.append("# - Resource utilization trends")
        content.append("# - Predictive failure detection")
        content.append("# - Business-level KPIs")
        content.append("```")
        content.append("")

        content.append("### Custom Metrics")
        content.append("```python")
        content.append("from kailash.nodes.monitoring import MetricsCollectorNode")
        content.append("")
        content.append("# Add custom metrics collection to workflows")
        content.append("workflow.add_node('MetricsCollectorNode', 'metrics', {")
        content.append("    'metrics': {")
        content.append("        'business_value': 'calculate_roi',")
        content.append("        'data_quality': 'check_quality_score',")
        content.append("        'processing_speed': 'measure_throughput'")
        content.append("    }")
        content.append("})")
        content.append("```")
        content.append("")

        content.append("## Reliability and Resilience")
        content.append("")
        content.append("### Circuit Breaker Pattern")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_resource_coordination=True,")
        content.append("    circuit_breaker_config={")
        content.append("        'failure_threshold': 5,     # Failures before opening")
        content.append("        'recovery_timeout': 60,     # Seconds in open state")
        content.append("        'success_threshold': 3,     # Successes to close")
        content.append("        'timeout': 30               # Request timeout")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Retry Policies")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_resource_coordination=True,")
        content.append("    retry_policy_config={")
        content.append("        'max_retries': 3,")
        content.append("        'backoff_factor': 2.0,      # Exponential backoff")
        content.append("        'max_backoff': 300,         # Max wait time")
        content.append("        'retry_on': ['timeout', 'connection_error']")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("## Resource Management")
        content.append("")
        content.append("### Advanced Resource Limits")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    resource_limits={")
        content.append("        'memory_mb': 4096,")
        content.append("        'cpu_percent': 80,")
        content.append("        'timeout_seconds': 1800,")
        content.append("        'max_files_open': 1000,")
        content.append("        'max_network_connections': 100")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("### Connection Pool Management")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    persistent_mode=True,")
        content.append("    enable_connection_sharing=True,")
        content.append("    connection_pool_config={")
        content.append("        'min_connections': 10,")
        content.append("        'max_connections': 100,")
        content.append("        'connection_timeout': 30,")
        content.append("        'idle_timeout': 300,")
        content.append("        'health_check_interval': 60")
        content.append("    }")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("## Integration Features")
        content.append("")
        content.append("### Custom Secret Providers")
        content.append("```python")
        content.append("from kailash.runtime.secret_provider import SecretProvider")
        content.append("")
        content.append("class EnterpriseSecretProvider(SecretProvider):")
        content.append("    def get_secret(self, key: str) -> str:")
        content.append("        # Integrate with enterprise secret management")
        content.append("        return vault_client.get_secret(key)")
        content.append("")
        content.append("runtime = LocalRuntime(")
        content.append("    secret_provider=EnterpriseSecretProvider()")
        content.append(")")
        content.append("```")
        content.append("")

        content.append("## Compliance and Governance")
        content.append("")
        content.append("### Data Governance")
        content.append("```python")
        content.append("from kailash.nodes.compliance import DataRetentionNode")
        content.append("")
        content.append("# Add data governance to workflows")
        content.append("workflow.add_node('DataRetentionNode', 'governance', {")
        content.append("    'retention_policy': 'gdpr',")
        content.append("    'classification': 'sensitive',")
        content.append("    'audit_trail': True")
        content.append("})")
        content.append("```")
        content.append("")

        content.append("### Regulatory Compliance")
        content.append("```python")
        content.append("runtime = LocalRuntime(")
        content.append("    enable_security=True,")
        content.append("    enable_audit=True,")
        content.append("    compliance_mode='strict',  # GDPR, HIPAA, SOX compliance")
        content.append("    data_classification_required=True")
        content.append(")")
        content.append("```")

        return DocumentationSection(
            title="Enterprise Features",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="medium",
        )

    def _generate_appendix_section(
        self,
        order: int,
        audience: str,
        analysis_result: Optional[AnalysisResult],
        migration_plan: Optional[MigrationPlan],
        migration_result: Optional[MigrationResult],
        performance_report: Optional[PerformanceReport],
        validation_result: Optional[ValidationResult],
    ) -> DocumentationSection:
        """Generate appendix section."""
        content = []
        content.append("# Appendix")
        content.append("")

        content.append("## Migration Tool Reference")
        content.append("")
        content.append("### Command Line Usage")
        content.append("```bash")
        content.append("# Analyze codebase for compatibility")
        content.append('python -c "')
        content.append("from kailash.migration import CompatibilityChecker")
        content.append("checker = CompatibilityChecker()")
        content.append("result = checker.analyze_codebase('/path/to/project')")
        content.append("print(checker.generate_report(result))")
        content.append('"')
        content.append("")
        content.append("# Generate migration plan")
        content.append('python -c "')
        content.append("from kailash.migration import MigrationAssistant")
        content.append("assistant = MigrationAssistant()")
        content.append("plan = assistant.create_migration_plan('/path/to/project')")
        content.append("print(assistant.generate_migration_report(plan))")
        content.append('"')
        content.append("```")
        content.append("")

        content.append("## Parameter Migration Map")
        content.append("")
        content.append("| Legacy Parameter | New Parameter | Notes |")
        content.append("|------------------|---------------|-------|")
        content.append("| `enable_parallel` | `max_concurrency` | Boolean → Integer |")
        content.append("| `thread_pool_size` | `max_concurrency` | Direct mapping |")
        content.append("| `debug_mode` | `debug` | Parameter rename |")
        content.append(
            "| `memory_limit` | `resource_limits['memory_mb']` | Move to dict |"
        )
        content.append(
            "| `timeout` | `resource_limits['timeout_seconds']` | Move to dict |"
        )
        content.append(
            "| `retry_count` | `retry_policy_config['max_retries']` | Move to dict |"
        )
        content.append("| `log_level` | Use logging config | Removed |")
        content.append("| `cache_enabled` | Use CacheNode | Use nodes instead |")
        content.append("")

        content.append("## Method Migration Map")
        content.append("")
        content.append("| Legacy Method | New Method | Notes |")
        content.append("|---------------|------------|-------|")
        content.append(
            "| `execute_sync(workflow)` | `execute(workflow)` | Unified method |"
        )
        content.append(
            "| `execute_async(workflow)` | `execute(workflow)` | Use `enable_async=True` |"
        )
        content.append("| `get_results()` | Return from `execute()` | Direct return |")
        content.append(
            "| `set_context(ctx)` | Constructor param | Use `user_context` |"
        )
        content.append(
            "| `configure(config)` | Constructor params | Use named params |"
        )
        content.append("")

        content.append("## Enterprise Feature Matrix")
        content.append("")
        content.append("| Feature | Parameter | Dependency | Description |")
        content.append("|---------|-----------|------------|-------------|")
        content.append(
            "| Security | `enable_security=True` | `user_context` | Access control |"
        )
        content.append(
            "| Audit | `enable_audit=True` | `enable_security` | Compliance logging |"
        )
        content.append(
            "| Advanced Monitoring | `enable_enterprise_monitoring=True` | `enable_monitoring` | Business metrics |"
        )
        content.append(
            "| Health Monitoring | `enable_health_monitoring=True` | None | System health |"
        )
        content.append(
            "| Circuit Breaker | `circuit_breaker_config` | `enable_resource_coordination` | Resilience |"
        )
        content.append(
            "| Retry Policy | `retry_policy_config` | `enable_resource_coordination` | Reliability |"
        )
        content.append("")

        content.append("## Common Error Codes")
        content.append("")
        content.append("### Configuration Errors")
        content.append("- `RUNTIME_CONFIG_001`: Unknown parameter")
        content.append("- `RUNTIME_CONFIG_002`: Invalid parameter type")
        content.append("- `RUNTIME_CONFIG_003`: Parameter value out of range")
        content.append("- `RUNTIME_CONFIG_004`: Missing required dependency")
        content.append("- `RUNTIME_CONFIG_005`: Parameter conflict")
        content.append("")

        content.append("### Execution Errors")
        content.append("- `RUNTIME_EXEC_001`: Method not found")
        content.append("- `RUNTIME_EXEC_002`: Invalid workflow format")
        content.append("- `RUNTIME_EXEC_003`: Resource limit exceeded")
        content.append("- `RUNTIME_EXEC_004`: Security violation")
        content.append("- `RUNTIME_EXEC_005`: Timeout exceeded")
        content.append("")

        content.append("## Support Resources")
        content.append("")
        content.append("- **Documentation**: https://kailash-sdk.readthedocs.io/")
        content.append("- **API Reference**: https://api.kailash-sdk.com/")
        content.append("- **Migration Tools**: `kailash.migration` module")
        content.append("- **Community Forum**: https://community.kailash-sdk.com/")
        content.append("- **Issue Tracker**: https://github.com/kailash-sdk/issues/")

        return DocumentationSection(
            title="Appendix",
            content="\n".join(content),
            order=order,
            audience=audience,
            importance="low",
        )

    def export_guide(
        self,
        guide: MigrationGuide,
        file_path: Union[str, Path],
        format: str = "markdown",
    ) -> None:
        """Export migration guide to file.

        Args:
            guide: Migration guide to export
            file_path: Output file path
            format: Export format ("markdown", "html", "pdf")
        """
        file_path = Path(file_path)

        if format == "markdown":
            content = self._export_markdown(guide)
        elif format == "html":
            content = self._export_html(guide)
        else:
            content = self._export_markdown(guide)  # Default to markdown

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _export_markdown(self, guide: MigrationGuide) -> str:
        """Export guide as markdown."""
        content = []

        # Title and metadata
        content.append(f"# {guide.title}")
        content.append("")
        content.append(
            f"*Generated: {guide.generated_at.strftime('%Y-%m-%d %H:%M:%S')}*"
        )
        content.append("")

        # Table of contents
        content.append("## Table of Contents")
        content.append("")
        for section in guide.sections:
            content.append(
                f"- [{section.title}](#{section.title.lower().replace(' ', '-')})"
            )
        content.append("")

        # Sections
        for section in guide.sections:
            content.append(section.content)
            content.append("")

        return "\n".join(content)

    def _export_html(self, guide: MigrationGuide) -> str:
        """Export guide as HTML."""
        # This would require a markdown-to-HTML converter
        # For now, return markdown format
        return self._export_markdown(guide)
