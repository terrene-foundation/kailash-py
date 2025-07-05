#!/usr/bin/env python3
"""
Comprehensive MCP Patterns Test Runner

Executes all MCP pattern tests and generates a comprehensive report:
- Basic patterns (1-5)
- Advanced patterns (6-10)
- Integration scenarios
- Real-world validation
- Performance metrics
- Compatibility matrix

Usage:
    python run_mcp_pattern_tests.py [--verbose] [--report-file output.json]
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add the test directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from test_mcp_patterns_advanced import AdvancedMCPPatternTests

# Import test suites
from test_mcp_patterns_comprehensive import MCPPatternTests
from test_mcp_patterns_integration import MCPPatternsIntegrationTest

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPPatternsTestRunner:
    """Comprehensive MCP Patterns Test Runner"""

    def __init__(self, verbose: bool = False, report_file: str = None):
        self.verbose = verbose
        self.report_file = report_file
        self.start_time = None
        self.end_time = None
        self.all_results = {}

        # Configure logging
        if self.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all MCP pattern tests"""
        logger.info("Starting comprehensive MCP patterns test suite...")
        self.start_time = datetime.now(timezone.utc)

        # Initialize test suites
        basic_tester = MCPPatternTests()
        advanced_tester = AdvancedMCPPatternTests()
        integration_tester = MCPPatternsIntegrationTest()

        # Run test suites
        test_suites = [
            ("Basic Patterns (1-5)", basic_tester.run_all_pattern_tests),
            (
                "Advanced Patterns (6-10)",
                advanced_tester.run_all_advanced_pattern_tests,
            ),
            ("Integration Scenarios", integration_tester.run_all_integration_tests),
        ]

        suite_results = {}
        overall_passed = 0
        overall_failed = 0
        overall_tests = 0

        for suite_name, test_method in test_suites:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running {suite_name}")
            logger.info(f"{'='*60}")

            suite_start = time.time()

            try:
                result = await test_method()
                suite_end = time.time()
                suite_duration = suite_end - suite_start

                # Add timing information
                result["execution_time_seconds"] = suite_duration

                suite_results[suite_name] = result

                # Update overall counts
                if "summary" in result:
                    overall_passed += result["summary"].get("passed", 0)
                    overall_failed += result["summary"].get("failed", 0)
                    overall_tests += result["summary"].get(
                        "total_patterns", 0
                    ) or result["summary"].get("total_scenarios", 0)

                # Log suite results
                status_icon = "✅" if result["summary"]["failed"] == 0 else "❌"
                logger.info(
                    f"{status_icon} {suite_name} completed in {suite_duration:.2f}s"
                )
                logger.info(f"   Passed: {result['summary']['passed']}")
                logger.info(f"   Failed: {result['summary']['failed']}")
                logger.info(f"   Success Rate: {result['summary']['success_rate']}")

            except Exception as e:
                suite_end = time.time()
                suite_duration = suite_end - suite_start

                logger.error(f"❌ {suite_name} failed with exception: {e}")

                suite_results[suite_name] = {
                    "test_suite": suite_name,
                    "status": "FAILED",
                    "error": str(e),
                    "execution_time_seconds": suite_duration,
                    "summary": {"passed": 0, "failed": 1, "success_rate": "0.0%"},
                }

                overall_failed += 1
                overall_tests += 1

        self.end_time = datetime.now(timezone.utc)
        total_duration = (self.end_time - self.start_time).total_seconds()

        # Compile comprehensive results
        self.all_results = {
            "test_execution": {
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "total_duration_seconds": total_duration,
                "test_runner_version": "1.0.0",
            },
            "overall_summary": {
                "total_test_suites": len(test_suites),
                "total_patterns_tested": overall_tests,
                "total_passed": overall_passed,
                "total_failed": overall_failed,
                "overall_success_rate": f"{(overall_passed / max(overall_tests, 1) * 100):.1f}%",
                "all_patterns_working": overall_failed == 0,
            },
            "test_suites": suite_results,
            "pattern_coverage": self._generate_pattern_coverage(suite_results),
            "compatibility_matrix": self._generate_compatibility_matrix(suite_results),
            "performance_metrics": self._generate_performance_metrics(suite_results),
            "recommendations": self._generate_recommendations(suite_results),
        }

        return self.all_results

    def _generate_pattern_coverage(
        self, suite_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate pattern coverage report"""
        patterns = {
            1: "Basic Server Pattern",
            2: "Authenticated Server Pattern",
            3: "Cached Tool Pattern",
            4: "Service Discovery Pattern",
            5: "Load Balanced Client Pattern",
            6: "Agent Integration Pattern",
            7: "Workflow Integration Pattern",
            8: "Error Handling Pattern",
            9: "Streaming Response Pattern",
            10: "Multi-Tenant Pattern",
        }

        coverage = {}

        for pattern_id, pattern_name in patterns.items():
            coverage[f"pattern_{pattern_id}"] = {
                "name": pattern_name,
                "tested": False,
                "passed": False,
                "test_details": None,
            }

        # Check basic patterns (1-5)
        basic_results = suite_results.get("Basic Patterns (1-5)", {})
        if "results" in basic_results:
            for i, result in enumerate(basic_results["results"], 1):
                if i <= 5:  # Basic patterns 1-5
                    coverage[f"pattern_{i}"]["tested"] = True
                    coverage[f"pattern_{i}"]["passed"] = result["status"] == "PASSED"
                    coverage[f"pattern_{i}"]["test_details"] = result.get("details", {})

        # Check advanced patterns (6-10)
        advanced_results = suite_results.get("Advanced Patterns (6-10)", {})
        if "results" in advanced_results:
            for i, result in enumerate(advanced_results["results"], 6):
                if i <= 10:  # Advanced patterns 6-10
                    coverage[f"pattern_{i}"]["tested"] = True
                    coverage[f"pattern_{i}"]["passed"] = result["status"] == "PASSED"
                    coverage[f"pattern_{i}"]["test_details"] = result.get("details", {})

        # Calculate coverage statistics
        total_patterns = len(patterns)
        tested_patterns = sum(1 for p in coverage.values() if p["tested"])
        passed_patterns = sum(1 for p in coverage.values() if p["passed"])

        coverage["summary"] = {
            "total_patterns": total_patterns,
            "patterns_tested": tested_patterns,
            "patterns_passed": passed_patterns,
            "coverage_percentage": f"{(tested_patterns / total_patterns * 100):.1f}%",
            "success_percentage": f"{(passed_patterns / total_patterns * 100):.1f}%",
        }

        return coverage

    def _generate_compatibility_matrix(
        self, suite_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate pattern compatibility matrix"""
        integration_results = suite_results.get("Integration Scenarios", {})

        matrix = {
            "pattern_interactions": {
                "auth_caching": False,
                "multitenant_streaming": False,
                "service_discovery_load_balancing": False,
                "error_handling_resilience": False,
                "agent_workflow_mcp": False,
                "all_patterns_together": False,
            },
            "real_world_scenarios": {
                "e2e_multi_pattern_workflow": False,
                "production_simulation": False,
                "cross_pattern_compatibility": False,
            },
        }

        if "results" in integration_results:
            for result in integration_results["results"]:
                scenario = result.get("scenario", "")
                passed = result.get("status") == "PASSED"

                if "E2E Multi-Pattern Workflow" in scenario:
                    matrix["real_world_scenarios"][
                        "e2e_multi_pattern_workflow"
                    ] = passed
                elif "Production Simulation" in scenario:
                    matrix["real_world_scenarios"]["production_simulation"] = passed
                elif "Cross-Pattern Compatibility" in scenario:
                    matrix["real_world_scenarios"][
                        "cross_pattern_compatibility"
                    ] = passed

                    # Check specific compatibility tests
                    if passed and "compatibility_tests" in result:
                        for test in result["compatibility_tests"]:
                            if "Authentication + Caching" in test:
                                matrix["pattern_interactions"]["auth_caching"] = True
                            elif "Multi-Tenant + Streaming" in test:
                                matrix["pattern_interactions"][
                                    "multitenant_streaming"
                                ] = True
                            elif "Service Discovery + Load Balancing" in test:
                                matrix["pattern_interactions"][
                                    "service_discovery_load_balancing"
                                ] = True
                            elif "Error Handling + Retry + Circuit Breaker" in test:
                                matrix["pattern_interactions"][
                                    "error_handling_resilience"
                                ] = True
                            elif "Agent Integration + Workflow + MCP Tools" in test:
                                matrix["pattern_interactions"][
                                    "agent_workflow_mcp"
                                ] = True
                            elif "All Patterns Integration" in test:
                                matrix["pattern_interactions"][
                                    "all_patterns_together"
                                ] = True

        # Calculate compatibility score
        interaction_score = sum(matrix["pattern_interactions"].values()) / len(
            matrix["pattern_interactions"]
        )
        scenario_score = sum(matrix["real_world_scenarios"].values()) / len(
            matrix["real_world_scenarios"]
        )

        matrix["compatibility_score"] = {
            "pattern_interactions": f"{(interaction_score * 100):.1f}%",
            "real_world_scenarios": f"{(scenario_score * 100):.1f}%",
            "overall": f"{((interaction_score + scenario_score) / 2 * 100):.1f}%",
        }

        return matrix

    def _generate_performance_metrics(
        self, suite_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate performance metrics"""
        metrics = {"execution_times": {}, "test_counts": {}, "performance_summary": {}}

        total_execution_time = 0
        total_tests = 0

        for suite_name, result in suite_results.items():
            execution_time = result.get("execution_time_seconds", 0)
            metrics["execution_times"][suite_name] = execution_time
            total_execution_time += execution_time

            if "summary" in result:
                test_count = result["summary"].get("total_patterns", 0) or result[
                    "summary"
                ].get("total_scenarios", 0)
                metrics["test_counts"][suite_name] = test_count
                total_tests += test_count

        # Calculate performance metrics
        avg_time_per_test = total_execution_time / max(total_tests, 1)

        metrics["performance_summary"] = {
            "total_execution_time_seconds": total_execution_time,
            "total_tests_executed": total_tests,
            "average_time_per_test_seconds": avg_time_per_test,
            "tests_per_second": total_tests / max(total_execution_time, 1),
            "performance_rating": self._rate_performance(
                avg_time_per_test, total_execution_time
            ),
        }

        return metrics

    def _rate_performance(self, avg_time_per_test: float, total_time: float) -> str:
        """Rate the performance of the test suite"""
        if avg_time_per_test < 1.0 and total_time < 30:
            return "Excellent"
        elif avg_time_per_test < 2.0 and total_time < 60:
            return "Good"
        elif avg_time_per_test < 5.0 and total_time < 120:
            return "Fair"
        else:
            return "Needs Improvement"

    def _generate_recommendations(self, suite_results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []

        # Check for failed tests
        for suite_name, result in suite_results.items():
            if "summary" in result and result["summary"]["failed"] > 0:
                recommendations.append(f"❌ Fix failing tests in {suite_name}")

        # Check coverage
        pattern_coverage = self._generate_pattern_coverage(suite_results)
        coverage_pct = float(
            pattern_coverage["summary"]["coverage_percentage"].rstrip("%")
        )

        if coverage_pct < 100:
            recommendations.append(
                f"📊 Improve pattern coverage (currently {coverage_pct}%)"
            )

        # Check compatibility
        compatibility_matrix = self._generate_compatibility_matrix(suite_results)
        overall_compatibility = float(
            compatibility_matrix["compatibility_score"]["overall"].rstrip("%")
        )

        if overall_compatibility < 100:
            recommendations.append(
                f"🔗 Improve pattern compatibility (currently {overall_compatibility}%)"
            )

        # Check performance
        performance_metrics = self._generate_performance_metrics(suite_results)
        performance_rating = performance_metrics["performance_summary"][
            "performance_rating"
        ]

        if performance_rating in ["Fair", "Needs Improvement"]:
            recommendations.append(
                f"⚡ Optimize test performance (currently {performance_rating})"
            )

        # Add positive recommendations
        if not recommendations:
            recommendations.append("✅ All MCP patterns are working correctly!")
            recommendations.append(
                "🚀 Consider adding more real-world integration scenarios"
            )
            recommendations.append("📈 Consider adding performance benchmarks")

        return recommendations

    def print_summary(self):
        """Print test summary to console"""
        if not self.all_results:
            print("No test results available")
            return

        print("\n" + "=" * 80)
        print("MCP PATTERNS COMPREHENSIVE TEST RESULTS")
        print("=" * 80)

        # Overall summary
        summary = self.all_results["overall_summary"]
        print("\nOverall Results:")
        print(f"  Total Patterns Tested: {summary['total_patterns_tested']}")
        print(f"  Total Passed: {summary['total_passed']}")
        print(f"  Total Failed: {summary['total_failed']}")
        print(f"  Success Rate: {summary['overall_success_rate']}")
        print(f"  All Patterns Working: {summary['all_patterns_working']}")

        # Execution info
        execution = self.all_results["test_execution"]
        print("\nExecution Info:")
        print(f"  Duration: {execution['total_duration_seconds']:.2f} seconds")
        print(f"  Start Time: {execution['start_time']}")
        print(f"  End Time: {execution['end_time']}")

        # Pattern coverage
        coverage = self.all_results["pattern_coverage"]
        print("\nPattern Coverage:")
        print(
            f"  Patterns Tested: {coverage['summary']['patterns_tested']}/{coverage['summary']['total_patterns']}"
        )
        print(f"  Coverage: {coverage['summary']['coverage_percentage']}")
        print(f"  Success: {coverage['summary']['success_percentage']}")

        # Pattern details
        print("\nPattern Details:")
        for i in range(1, 11):
            pattern = coverage[f"pattern_{i}"]
            status = (
                "✅ PASS"
                if pattern["passed"]
                else "❌ FAIL" if pattern["tested"] else "⏸️ SKIP"
            )
            print(f"  {i:2d}. {pattern['name']}: {status}")

        # Compatibility
        compatibility = self.all_results["compatibility_matrix"]
        print("\nCompatibility:")
        print(
            f"  Pattern Interactions: {compatibility['compatibility_score']['pattern_interactions']}"
        )
        print(
            f"  Real-world Scenarios: {compatibility['compatibility_score']['real_world_scenarios']}"
        )
        print(
            f"  Overall Compatibility: {compatibility['compatibility_score']['overall']}"
        )

        # Performance
        performance = self.all_results["performance_metrics"]
        perf_summary = performance["performance_summary"]
        print("\nPerformance:")
        print(f"  Total Tests: {perf_summary['total_tests_executed']}")
        print(f"  Execution Time: {perf_summary['total_execution_time_seconds']:.2f}s")
        print(f"  Avg Time/Test: {perf_summary['average_time_per_test_seconds']:.2f}s")
        print(f"  Performance Rating: {perf_summary['performance_rating']}")

        # Recommendations
        recommendations = self.all_results["recommendations"]
        print("\nRecommendations:")
        for rec in recommendations:
            print(f"  {rec}")

        print("\n" + "=" * 80)

    def save_report(self):
        """Save detailed report to file"""
        if self.report_file and self.all_results:
            report_path = Path(self.report_file)
            report_path.parent.mkdir(parents=True, exist_ok=True)

            with open(report_path, "w") as f:
                json.dump(self.all_results, f, indent=2, default=str)

            print(f"\nDetailed report saved to: {report_path}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run comprehensive MCP patterns test suite"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--report-file",
        "-r",
        type=str,
        default="mcp_patterns_test_report.json",
        help="Output file for detailed test report",
    )

    args = parser.parse_args()

    # Create and run test runner
    runner = MCPPatternsTestRunner(verbose=args.verbose, report_file=args.report_file)

    try:
        results = await runner.run_all_tests()

        # Print summary
        runner.print_summary()

        # Save report
        runner.save_report()

        # Exit with appropriate code
        all_passed = results["overall_summary"]["all_patterns_working"]
        sys.exit(0 if all_passed else 1)

    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
