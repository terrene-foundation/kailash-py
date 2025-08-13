"""Regression detection system for post-migration validation.

This module provides comprehensive regression detection capabilities to identify
issues that may have been introduced during LocalRuntime migration, including
performance regressions, functional regressions, and configuration issues.
"""

import hashlib
import json
import pickle
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class RegressionType(str, Enum):
    """Types of regressions that can be detected."""

    PERFORMANCE = "performance"
    FUNCTIONAL = "functional"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    RESOURCE = "resource"
    COMPATIBILITY = "compatibility"


class RegressionSeverity(str, Enum):
    """Severity levels for regression issues."""

    CRITICAL = "critical"  # System unusable
    HIGH = "high"  # Major functionality affected
    MEDIUM = "medium"  # Minor functionality affected
    LOW = "low"  # Cosmetic or edge case issues


@dataclass
class RegressionIssue:
    """Represents a detected regression."""

    regression_type: RegressionType
    severity: RegressionSeverity
    test_name: str
    description: str
    expected_value: Any
    actual_value: Any
    threshold: float
    deviation_percentage: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BaselineSnapshot:
    """Baseline snapshot for regression comparison."""

    test_name: str
    workflow_hash: str
    configuration: Dict[str, Any]
    results: Dict[str, Any]
    performance_metrics: Dict[str, float]
    resource_usage: Dict[str, float]
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegressionReport:
    """Comprehensive regression detection report."""

    total_tests: int
    passed_tests: int
    failed_tests: int
    regression_issues: List[RegressionIssue] = field(default_factory=list)
    baseline_missing: List[str] = field(default_factory=list)
    test_summary: Dict[str, Dict] = field(default_factory=dict)
    overall_status: str = "unknown"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RegressionDetector:
    """Comprehensive regression detection system."""

    def __init__(
        self,
        baseline_path: Union[str, Path] = "migration_baseline.json",
        performance_threshold: float = 10.0,  # % degradation threshold
        resource_threshold: float = 20.0,  # % resource increase threshold
        parallel_tests: bool = True,
        max_workers: int = 4,
    ):
        """Initialize the regression detector.

        Args:
            baseline_path: Path to store/load baseline data
            performance_threshold: Performance regression threshold (%)
            resource_threshold: Resource usage regression threshold (%)
            parallel_tests: Whether to run tests in parallel
            max_workers: Maximum number of parallel workers
        """
        self.baseline_path = Path(baseline_path)
        self.performance_threshold = performance_threshold
        self.resource_threshold = resource_threshold
        self.parallel_tests = parallel_tests
        self.max_workers = max_workers

        # Baseline data storage
        self.baselines: Dict[str, BaselineSnapshot] = {}
        self._load_baselines()

        # Test workflows for regression testing
        self.test_workflows = self._create_test_workflows()

        # Performance tracking
        self.performance_history: Dict[str, List[float]] = {}

        # Regression thresholds by type
        self.thresholds = {
            RegressionType.PERFORMANCE: performance_threshold,
            RegressionType.RESOURCE: resource_threshold,
            RegressionType.FUNCTIONAL: 0.0,  # Any functional change is a regression
            RegressionType.CONFIGURATION: 0.0,
            RegressionType.SECURITY: 0.0,
            RegressionType.COMPATIBILITY: 0.0,
        }

    def create_baseline(
        self,
        config: Dict[str, Any],
        custom_workflows: Optional[List[Tuple[str, Workflow]]] = None,
    ) -> Dict[str, BaselineSnapshot]:
        """Create baseline snapshots for regression detection.

        Args:
            config: LocalRuntime configuration to baseline
            custom_workflows: Optional custom workflows to include

        Returns:
            Dictionary of baseline snapshots
        """
        workflows = custom_workflows or self.test_workflows
        baselines = {}

        print(f"Creating baseline with {len(workflows)} test workflows...")

        for test_name, workflow in workflows:
            print(f"  Creating baseline for: {test_name}")
            baseline = self._create_baseline_snapshot(test_name, workflow, config)
            if baseline:
                baselines[test_name] = baseline
                self.baselines[test_name] = baseline

        # Save baselines to disk
        self._save_baselines()

        return baselines

    def detect_regressions(
        self,
        config: Dict[str, Any],
        custom_workflows: Optional[List[Tuple[str, Workflow]]] = None,
    ) -> RegressionReport:
        """Detect regressions by comparing against baseline.

        Args:
            config: Current LocalRuntime configuration
            custom_workflows: Optional custom workflows to test

        Returns:
            Comprehensive regression report
        """
        workflows = custom_workflows or self.test_workflows

        report = RegressionReport(
            total_tests=len(workflows), passed_tests=0, failed_tests=0
        )

        # Run tests and detect regressions
        if self.parallel_tests:
            self._run_parallel_regression_tests(workflows, config, report)
        else:
            self._run_sequential_regression_tests(workflows, config, report)

        # Analyze overall status
        report.overall_status = self._determine_overall_status(report)

        return report

    def _create_test_workflows(self) -> List[Tuple[str, Workflow]]:
        """Create standard test workflows for regression testing."""
        workflows = []

        # Simple execution test
        simple_builder = WorkflowBuilder()
        simple_builder.add_node(
            "PythonCodeNode",
            "simple",
            {"code": "result = 'hello_world'", "output_key": "message"},
        )
        workflows.append(("simple_execution", simple_builder.build()))

        # Performance test
        perf_builder = WorkflowBuilder()
        perf_builder.add_node(
            "PythonCodeNode",
            "performance",
            {
                "code": """
import time
start = time.time()
# Simulate work
result = sum(i*i for i in range(10000))
duration = time.time() - start
""",
                "output_key": "calculation_result",
            },
        )
        workflows.append(("performance_test", perf_builder.build()))

        # Memory test
        memory_builder = WorkflowBuilder()
        memory_builder.add_node(
            "PythonCodeNode",
            "memory",
            {
                "code": """
import gc
# Create and cleanup large object
large_data = [list(range(1000)) for _ in range(100)]
result = len(large_data)
del large_data
gc.collect()
""",
                "output_key": "memory_result",
            },
        )
        workflows.append(("memory_test", memory_builder.build()))

        # Error handling test
        error_builder = WorkflowBuilder()
        error_builder.add_node(
            "PythonCodeNode",
            "error_handling",
            {
                "code": """
try:
    result = 1 / 0
except ZeroDivisionError:
    result = "error_handled_correctly"
""",
                "output_key": "error_result",
            },
        )
        workflows.append(("error_handling_test", error_builder.build()))

        # Multi-node workflow test
        multi_builder = WorkflowBuilder()
        multi_builder.add_node(
            "PythonCodeNode",
            "step1",
            {"code": "result = [1, 2, 3, 4, 5]", "output_key": "numbers"},
        )
        multi_builder.add_node(
            "PythonCodeNode",
            "step2",
            {
                "code": "result = [x * 2 for x in numbers]",
                "input_mapping": {"numbers": "step1.numbers"},
                "output_key": "doubled",
            },
        )
        multi_builder.add_node(
            "PythonCodeNode",
            "step3",
            {
                "code": "result = sum(doubled)",
                "input_mapping": {"doubled": "step2.doubled"},
                "output_key": "sum_result",
            },
        )
        workflows.append(("multi_node_test", multi_builder.build()))

        # Configuration sensitivity test
        config_builder = WorkflowBuilder()
        config_builder.add_node(
            "PythonCodeNode",
            "config_test",
            {
                "code": """
import os
import threading
# Test configuration-sensitive operations
result = {
    'thread_id': threading.get_ident(),
    'process_id': os.getpid(),
    'environment_ready': True
}
""",
                "output_key": "config_result",
            },
        )
        workflows.append(("configuration_test", config_builder.build()))

        return workflows

    def _create_baseline_snapshot(
        self, test_name: str, workflow: Workflow, config: Dict[str, Any]
    ) -> Optional[BaselineSnapshot]:
        """Create a baseline snapshot for a single test."""
        try:
            # Create workflow hash for change detection
            workflow_hash = self._hash_workflow(workflow)

            # Run test multiple times for stable metrics
            runtime = LocalRuntime(**config)
            execution_times = []
            memory_usages = []
            results_history = []

            for _ in range(3):  # 3 runs for stability
                import psutil

                process = psutil.Process()

                # Measure before execution
                memory_before = process.memory_info().rss / 1024 / 1024  # MB

                # Execute workflow
                start_time = time.perf_counter()
                results, run_id = runtime.execute(workflow)
                end_time = time.perf_counter()

                # Measure after execution
                memory_after = process.memory_info().rss / 1024 / 1024  # MB

                execution_times.append((end_time - start_time) * 1000)  # ms
                memory_usages.append(memory_after - memory_before)
                results_history.append(results)

            # Calculate stable metrics
            avg_execution_time = statistics.mean(execution_times)
            avg_memory_usage = statistics.mean(memory_usages)

            # Use first result as baseline (assuming deterministic workflows)
            baseline_results = results_history[0]

            # Create snapshot
            snapshot = BaselineSnapshot(
                test_name=test_name,
                workflow_hash=workflow_hash,
                configuration=config.copy(),
                results=baseline_results,
                performance_metrics={
                    "execution_time_ms": avg_execution_time,
                    "execution_time_stddev": (
                        statistics.stdev(execution_times)
                        if len(execution_times) > 1
                        else 0.0
                    ),
                },
                resource_usage={
                    "memory_usage_mb": avg_memory_usage,
                    "memory_stddev": (
                        statistics.stdev(memory_usages)
                        if len(memory_usages) > 1
                        else 0.0
                    ),
                },
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "runs": len(execution_times),
                    "config_hash": self._hash_config(config),
                },
            )

            return snapshot

        except Exception as e:
            print(f"Failed to create baseline for {test_name}: {str(e)}")
            return None

    def _run_parallel_regression_tests(
        self,
        workflows: List[Tuple[str, Workflow]],
        config: Dict[str, Any],
        report: RegressionReport,
    ) -> None:
        """Run regression tests in parallel."""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all test jobs
            future_to_test = {
                executor.submit(
                    self._run_single_regression_test, test_name, workflow, config
                ): test_name
                for test_name, workflow in workflows
            }

            # Collect results
            for future in as_completed(future_to_test):
                test_name = future_to_test[future]
                try:
                    test_result = future.result()
                    self._process_test_result(test_name, test_result, report)
                except Exception as e:
                    # Add test failure
                    report.failed_tests += 1
                    report.test_summary[test_name] = {
                        "status": "error",
                        "error": str(e),
                    }

    def _run_sequential_regression_tests(
        self,
        workflows: List[Tuple[str, Workflow]],
        config: Dict[str, Any],
        report: RegressionReport,
    ) -> None:
        """Run regression tests sequentially."""
        for test_name, workflow in workflows:
            try:
                test_result = self._run_single_regression_test(
                    test_name, workflow, config
                )
                self._process_test_result(test_name, test_result, report)
            except Exception as e:
                report.failed_tests += 1
                report.test_summary[test_name] = {"status": "error", "error": str(e)}

    def _run_single_regression_test(
        self, test_name: str, workflow: Workflow, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a single regression test and return results."""
        # Get baseline for comparison
        baseline = self.baselines.get(test_name)
        if not baseline:
            return {
                "status": "no_baseline",
                "message": f"No baseline found for test {test_name}",
            }

        # Check workflow consistency
        current_hash = self._hash_workflow(workflow)
        if current_hash != baseline.workflow_hash:
            return {
                "status": "workflow_changed",
                "message": "Workflow has changed since baseline creation",
                "baseline_hash": baseline.workflow_hash,
                "current_hash": current_hash,
            }

        # Run test
        runtime = LocalRuntime(**config)

        # Performance measurement
        import psutil

        process = psutil.Process()

        # Multiple runs for stability
        execution_times = []
        memory_usages = []
        results_history = []

        for _ in range(3):
            memory_before = process.memory_info().rss / 1024 / 1024

            start_time = time.perf_counter()
            results, run_id = runtime.execute(workflow)
            end_time = time.perf_counter()

            memory_after = process.memory_info().rss / 1024 / 1024

            execution_times.append((end_time - start_time) * 1000)
            memory_usages.append(memory_after - memory_before)
            results_history.append(results)

        # Calculate current metrics
        current_metrics = {
            "execution_time_ms": statistics.mean(execution_times),
            "memory_usage_mb": statistics.mean(memory_usages),
            "results": results_history[0],  # Use first result for consistency
        }

        return {
            "status": "completed",
            "baseline": baseline,
            "current": current_metrics,
            "runs": len(execution_times),
        }

    def _process_test_result(
        self, test_name: str, test_result: Dict[str, Any], report: RegressionReport
    ) -> None:
        """Process a single test result and detect regressions."""
        if test_result["status"] == "no_baseline":
            report.baseline_missing.append(test_name)
            report.test_summary[test_name] = test_result
            return

        if test_result["status"] != "completed":
            report.failed_tests += 1
            report.test_summary[test_name] = test_result
            return

        baseline = test_result["baseline"]
        current = test_result["current"]

        # Detect performance regressions
        performance_issues = self._detect_performance_regressions(
            test_name, baseline, current
        )
        report.regression_issues.extend(performance_issues)

        # Detect functional regressions
        functional_issues = self._detect_functional_regressions(
            test_name, baseline, current
        )
        report.regression_issues.extend(functional_issues)

        # Detect resource regressions
        resource_issues = self._detect_resource_regressions(
            test_name, baseline, current
        )
        report.regression_issues.extend(resource_issues)

        # Determine test status
        has_critical = any(
            issue.severity == RegressionSeverity.CRITICAL
            for issue in performance_issues + functional_issues + resource_issues
        )
        has_high = any(
            issue.severity == RegressionSeverity.HIGH
            for issue in performance_issues + functional_issues + resource_issues
        )

        if has_critical:
            test_status = "critical_regression"
            report.failed_tests += 1
        elif has_high:
            test_status = "high_regression"
            report.failed_tests += 1
        elif performance_issues or functional_issues or resource_issues:
            test_status = "minor_regression"
            report.passed_tests += 1
        else:
            test_status = "passed"
            report.passed_tests += 1

        report.test_summary[test_name] = {
            "status": test_status,
            "issues_found": len(
                performance_issues + functional_issues + resource_issues
            ),
            "execution_time_change": self._calculate_percentage_change(
                baseline.performance_metrics.get("execution_time_ms", 0),
                current["execution_time_ms"],
            ),
            "memory_change": self._calculate_percentage_change(
                baseline.resource_usage.get("memory_usage_mb", 0),
                current["memory_usage_mb"],
            ),
        }

    def _detect_performance_regressions(
        self, test_name: str, baseline: BaselineSnapshot, current: Dict[str, Any]
    ) -> List[RegressionIssue]:
        """Detect performance regressions."""
        issues = []

        # Execution time regression
        baseline_time = baseline.performance_metrics.get("execution_time_ms", 0)
        current_time = current["execution_time_ms"]
        time_change = self._calculate_percentage_change(baseline_time, current_time)

        if time_change > self.performance_threshold:
            severity = self._determine_severity(time_change, self.performance_threshold)
            issues.append(
                RegressionIssue(
                    regression_type=RegressionType.PERFORMANCE,
                    severity=severity,
                    test_name=test_name,
                    description=f"Execution time increased by {time_change:.1f}%",
                    expected_value=baseline_time,
                    actual_value=current_time,
                    threshold=self.performance_threshold,
                    deviation_percentage=time_change,
                    metadata={"metric": "execution_time_ms"},
                )
            )

        return issues

    def _detect_functional_regressions(
        self, test_name: str, baseline: BaselineSnapshot, current: Dict[str, Any]
    ) -> List[RegressionIssue]:
        """Detect functional regressions."""
        issues = []

        baseline_results = baseline.results
        current_results = current["results"]

        # Deep comparison of results
        differences = self._deep_compare_results(baseline_results, current_results)

        for diff in differences:
            # Any functional change is considered a regression
            severity = (
                RegressionSeverity.HIGH
                if diff["critical"]
                else RegressionSeverity.MEDIUM
            )

            issues.append(
                RegressionIssue(
                    regression_type=RegressionType.FUNCTIONAL,
                    severity=severity,
                    test_name=test_name,
                    description=f"Functional change detected: {diff['description']}",
                    expected_value=diff["expected"],
                    actual_value=diff["actual"],
                    threshold=0.0,
                    deviation_percentage=100.0,  # Functional changes are 100% different
                    metadata={"path": diff["path"], "change_type": diff["type"]},
                )
            )

        return issues

    def _detect_resource_regressions(
        self, test_name: str, baseline: BaselineSnapshot, current: Dict[str, Any]
    ) -> List[RegressionIssue]:
        """Detect resource usage regressions."""
        issues = []

        # Memory usage regression
        baseline_memory = baseline.resource_usage.get("memory_usage_mb", 0)
        current_memory = current["memory_usage_mb"]
        memory_change = self._calculate_percentage_change(
            baseline_memory, current_memory
        )

        if memory_change > self.resource_threshold:
            severity = self._determine_severity(memory_change, self.resource_threshold)
            issues.append(
                RegressionIssue(
                    regression_type=RegressionType.RESOURCE,
                    severity=severity,
                    test_name=test_name,
                    description=f"Memory usage increased by {memory_change:.1f}%",
                    expected_value=baseline_memory,
                    actual_value=current_memory,
                    threshold=self.resource_threshold,
                    deviation_percentage=memory_change,
                    metadata={"metric": "memory_usage_mb"},
                )
            )

        return issues

    def _calculate_percentage_change(self, baseline: float, current: float) -> float:
        """Calculate percentage change from baseline."""
        if baseline == 0:
            return 0.0 if current == 0 else float("inf")
        return ((current - baseline) / baseline) * 100

    def _determine_severity(
        self, change_percentage: float, threshold: float
    ) -> RegressionSeverity:
        """Determine severity based on change percentage."""
        if change_percentage >= threshold * 4:
            return RegressionSeverity.CRITICAL
        elif change_percentage >= threshold * 2:
            return RegressionSeverity.HIGH
        elif change_percentage >= threshold:
            return RegressionSeverity.MEDIUM
        else:
            return RegressionSeverity.LOW

    def _deep_compare_results(
        self, baseline: Dict, current: Dict
    ) -> List[Dict[str, Any]]:
        """Deep comparison of result dictionaries."""
        differences = []

        def compare_recursive(base_obj, curr_obj, path=""):
            if type(base_obj) != type(curr_obj):
                differences.append(
                    {
                        "path": path,
                        "type": "type_change",
                        "description": f"Type changed from {type(base_obj).__name__} to {type(curr_obj).__name__}",
                        "expected": type(base_obj).__name__,
                        "actual": type(curr_obj).__name__,
                        "critical": True,
                    }
                )
                return

            if isinstance(base_obj, dict):
                # Check for missing keys
                base_keys = set(base_obj.keys())
                curr_keys = set(curr_obj.keys())

                missing_keys = base_keys - curr_keys
                new_keys = curr_keys - base_keys

                for key in missing_keys:
                    differences.append(
                        {
                            "path": f"{path}.{key}" if path else key,
                            "type": "missing_key",
                            "description": f'Key "{key}" missing from results',
                            "expected": base_obj[key],
                            "actual": None,
                            "critical": True,
                        }
                    )

                for key in new_keys:
                    differences.append(
                        {
                            "path": f"{path}.{key}" if path else key,
                            "type": "new_key",
                            "description": f'Unexpected key "{key}" in results',
                            "expected": None,
                            "actual": curr_obj[key],
                            "critical": False,
                        }
                    )

                # Compare common keys
                for key in base_keys & curr_keys:
                    new_path = f"{path}.{key}" if path else key
                    compare_recursive(base_obj[key], curr_obj[key], new_path)

            elif isinstance(base_obj, list):
                if len(base_obj) != len(curr_obj):
                    differences.append(
                        {
                            "path": path,
                            "type": "length_change",
                            "description": f"List length changed from {len(base_obj)} to {len(curr_obj)}",
                            "expected": len(base_obj),
                            "actual": len(curr_obj),
                            "critical": True,
                        }
                    )
                    return

                for i, (base_item, curr_item) in enumerate(zip(base_obj, curr_obj)):
                    compare_recursive(base_item, curr_item, f"{path}[{i}]")

            else:
                # Compare primitive values
                if base_obj != curr_obj:
                    differences.append(
                        {
                            "path": path,
                            "type": "value_change",
                            "description": f'Value changed from "{base_obj}" to "{curr_obj}"',
                            "expected": base_obj,
                            "actual": curr_obj,
                            "critical": False,
                        }
                    )

        compare_recursive(baseline, current)
        return differences

    def _determine_overall_status(self, report: RegressionReport) -> str:
        """Determine overall status from report."""
        critical_issues = len(
            [
                i
                for i in report.regression_issues
                if i.severity == RegressionSeverity.CRITICAL
            ]
        )
        high_issues = len(
            [
                i
                for i in report.regression_issues
                if i.severity == RegressionSeverity.HIGH
            ]
        )

        if critical_issues > 0:
            return "critical_regressions"
        elif high_issues > 0:
            return "high_regressions"
        elif len(report.regression_issues) > 0:
            return "minor_regressions"
        elif report.failed_tests > 0:
            return "test_failures"
        elif len(report.baseline_missing) > 0:
            return "missing_baselines"
        else:
            return "all_passed"

    def _hash_workflow(self, workflow: Workflow) -> str:
        """Create a hash of the workflow for change detection."""
        # Convert workflow to a deterministic string representation
        workflow_str = json.dumps(workflow.to_dict(), sort_keys=True)
        return hashlib.sha256(workflow_str.encode()).hexdigest()[:16]

    def _hash_config(self, config: Dict[str, Any]) -> str:
        """Create a hash of the configuration."""
        config_str = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def _save_baselines(self) -> None:
        """Save baselines to disk."""
        baseline_data = {}
        for test_name, baseline in self.baselines.items():
            baseline_data[test_name] = {
                "test_name": baseline.test_name,
                "workflow_hash": baseline.workflow_hash,
                "configuration": baseline.configuration,
                "results": baseline.results,
                "performance_metrics": baseline.performance_metrics,
                "resource_usage": baseline.resource_usage,
                "timestamp": baseline.timestamp.isoformat(),
                "metadata": baseline.metadata,
            }

        with open(self.baseline_path, "w") as f:
            json.dump(baseline_data, f, indent=2, default=str)

    def _load_baselines(self) -> None:
        """Load baselines from disk."""
        if not self.baseline_path.exists():
            return

        try:
            with open(self.baseline_path, "r") as f:
                baseline_data = json.load(f)

            for test_name, data in baseline_data.items():
                baseline = BaselineSnapshot(
                    test_name=data["test_name"],
                    workflow_hash=data["workflow_hash"],
                    configuration=data["configuration"],
                    results=data["results"],
                    performance_metrics=data["performance_metrics"],
                    resource_usage=data["resource_usage"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    metadata=data["metadata"],
                )
                self.baselines[test_name] = baseline

        except Exception as e:
            print(f"Failed to load baselines: {str(e)}")

    def generate_regression_report(
        self, report: RegressionReport, format: str = "text"
    ) -> str:
        """Generate a comprehensive regression report.

        Args:
            report: Regression detection report
            format: Report format ("text", "json", "markdown")

        Returns:
            Formatted regression report
        """
        if format == "json":
            return self._generate_json_report(report)
        elif format == "markdown":
            return self._generate_markdown_report(report)
        else:
            return self._generate_text_report(report)

    def _generate_text_report(self, report: RegressionReport) -> str:
        """Generate text format regression report."""
        lines = []
        lines.append("=" * 60)
        lines.append("LocalRuntime Regression Detection Report")
        lines.append("=" * 60)
        lines.append("")

        # Executive summary
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 20)
        lines.append(
            f"Overall Status: {report.overall_status.upper().replace('_', ' ')}"
        )
        lines.append(f"Total Tests: {report.total_tests}")
        lines.append(f"Passed: {report.passed_tests}")
        lines.append(f"Failed: {report.failed_tests}")
        lines.append(f"Missing Baselines: {len(report.baseline_missing)}")
        lines.append(f"Regression Issues: {len(report.regression_issues)}")
        lines.append("")

        # Regression issues by severity
        if report.regression_issues:
            lines.append("REGRESSION ISSUES")
            lines.append("-" * 20)

            for severity in RegressionSeverity:
                severity_issues = [
                    i for i in report.regression_issues if i.severity == severity
                ]
                if severity_issues:
                    lines.append(
                        f"\n{severity.value.upper()} ISSUES ({len(severity_issues)}):"
                    )
                    for issue in severity_issues:
                        lines.append(f"  • {issue.test_name}: {issue.description}")
                        lines.append(f"    Expected: {issue.expected_value}")
                        lines.append(f"    Actual: {issue.actual_value}")
                        lines.append(
                            f"    Deviation: {issue.deviation_percentage:.1f}%"
                        )
                        lines.append("")

        # Test summary
        lines.append("TEST SUMMARY")
        lines.append("-" * 15)
        for test_name, summary in report.test_summary.items():
            status_icon = {
                "passed": "✅",
                "critical_regression": "🚨",
                "high_regression": "⚠️",
                "minor_regression": "⚠️",
                "error": "❌",
                "no_baseline": "❓",
            }.get(summary["status"], "❓")

            lines.append(
                f"{status_icon} {test_name}: {summary['status'].replace('_', ' ').title()}"
            )

            if "execution_time_change" in summary:
                lines.append(
                    f"    Performance: {summary['execution_time_change']:+.1f}%"
                )
            if "memory_change" in summary:
                lines.append(f"    Memory: {summary['memory_change']:+.1f}%")
            if "issues_found" in summary:
                lines.append(f"    Issues: {summary['issues_found']}")
            lines.append("")

        # Recommendations
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 18)

        critical_issues = len(
            [
                i
                for i in report.regression_issues
                if i.severity == RegressionSeverity.CRITICAL
            ]
        )
        high_issues = len(
            [
                i
                for i in report.regression_issues
                if i.severity == RegressionSeverity.HIGH
            ]
        )

        if critical_issues > 0:
            lines.append("🚨 CRITICAL: Migration should be rolled back immediately")
            lines.append(
                "   - Critical regressions detected that affect system functionality"
            )
            lines.append(
                "   - Investigate and resolve issues before retrying migration"
            )
        elif high_issues > 0:
            lines.append(
                "⚠️  HIGH PRIORITY: Address high-severity issues before production"
            )
            lines.append("   - Significant regressions detected")
            lines.append("   - Consider additional testing and optimization")
        elif len(report.regression_issues) > 0:
            lines.append("ℹ️  MINOR: Migration successful with minor regressions")
            lines.append("   - Monitor system behavior in production")
            lines.append("   - Consider performance optimizations")
        else:
            lines.append("✅ SUCCESS: Migration completed without regressions")
            lines.append("   - System is performing as expected")
            lines.append("   - Safe to proceed with production deployment")

        return "\n".join(lines)

    def _generate_json_report(self, report: RegressionReport) -> str:
        """Generate JSON format regression report."""
        data = {
            "summary": {
                "overall_status": report.overall_status,
                "total_tests": report.total_tests,
                "passed_tests": report.passed_tests,
                "failed_tests": report.failed_tests,
                "baseline_missing": len(report.baseline_missing),
                "regression_issues": len(report.regression_issues),
                "generated_at": report.generated_at.isoformat(),
            },
            "regression_issues": [
                {
                    "type": issue.regression_type,
                    "severity": issue.severity,
                    "test_name": issue.test_name,
                    "description": issue.description,
                    "expected_value": issue.expected_value,
                    "actual_value": issue.actual_value,
                    "threshold": issue.threshold,
                    "deviation_percentage": issue.deviation_percentage,
                    "metadata": issue.metadata,
                }
                for issue in report.regression_issues
            ],
            "test_summary": report.test_summary,
            "baseline_missing": report.baseline_missing,
        }

        return json.dumps(data, indent=2, default=str)

    def _generate_markdown_report(self, report: RegressionReport) -> str:
        """Generate markdown format regression report."""
        lines = []
        lines.append("# LocalRuntime Regression Detection Report")
        lines.append("")

        # Status badge
        status_emoji = {
            "all_passed": "🟢",
            "minor_regressions": "🟡",
            "high_regressions": "🟠",
            "critical_regressions": "🔴",
            "test_failures": "🔴",
            "missing_baselines": "⚪",
        }

        emoji = status_emoji.get(report.overall_status, "⚪")
        lines.append(
            f"## {emoji} Status: {report.overall_status.replace('_', ' ').title()}"
        )
        lines.append("")

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Tests | {report.total_tests} |")
        lines.append(f"| Passed | {report.passed_tests} |")
        lines.append(f"| Failed | {report.failed_tests} |")
        lines.append(f"| Missing Baselines | {len(report.baseline_missing)} |")
        lines.append(f"| Regression Issues | {len(report.regression_issues)} |")
        lines.append("")

        # Regression issues
        if report.regression_issues:
            lines.append("## Regression Issues")
            lines.append("")

            for severity in RegressionSeverity:
                severity_issues = [
                    i for i in report.regression_issues if i.severity == severity
                ]
                if severity_issues:
                    severity_emoji = {
                        RegressionSeverity.CRITICAL: "🚨",
                        RegressionSeverity.HIGH: "⚠️",
                        RegressionSeverity.MEDIUM: "⚠️",
                        RegressionSeverity.LOW: "ℹ️",
                    }[severity]

                    lines.append(
                        f"### {severity_emoji} {severity.value.title()} Issues"
                    )
                    lines.append("")

                    for issue in severity_issues:
                        lines.append(f"**{issue.test_name}**: {issue.description}")
                        lines.append("")
                        lines.append(f"- **Expected**: {issue.expected_value}")
                        lines.append(f"- **Actual**: {issue.actual_value}")
                        lines.append(
                            f"- **Deviation**: {issue.deviation_percentage:.1f}%"
                        )
                        lines.append(f"- **Type**: {issue.regression_type}")
                        lines.append("")

        # Test results
        lines.append("## Test Results")
        lines.append("")
        lines.append("| Test | Status | Performance Change | Memory Change |")
        lines.append("|------|--------|-------------------|---------------|")

        for test_name, summary in report.test_summary.items():
            status_icon = {
                "passed": "✅",
                "critical_regression": "🚨",
                "high_regression": "⚠️",
                "minor_regression": "⚠️",
                "error": "❌",
                "no_baseline": "❓",
            }.get(summary["status"], "❓")

            perf_change = summary.get("execution_time_change", "N/A")
            memory_change = summary.get("memory_change", "N/A")

            if isinstance(perf_change, (int, float)):
                perf_change = f"{perf_change:+.1f}%"
            if isinstance(memory_change, (int, float)):
                memory_change = f"{memory_change:+.1f}%"

            lines.append(
                f"| {test_name} | {status_icon} {summary['status'].replace('_', ' ').title()} | {perf_change} | {memory_change} |"
            )

        return "\n".join(lines)

    def save_report(
        self,
        report: RegressionReport,
        file_path: Union[str, Path],
        format: str = "json",
    ) -> None:
        """Save regression report to file.

        Args:
            report: Regression report to save
            file_path: Output file path
            format: Report format ("text", "json", "markdown")
        """
        content = self.generate_regression_report(report, format)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
