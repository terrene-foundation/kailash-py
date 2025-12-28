#!/usr/bin/env python3
"""
Kailash Performance Test Runner

Comprehensive test orchestration and execution system for load testing the
LocalRuntime with real infrastructure. This script coordinates test execution,
monitors resources, and generates detailed reports.

Usage:
    python performance_test_runner.py --scenario baseline --concurrency 1000
    python performance_test_runner.py --scenario endurance --duration 24
    python performance_test_runner.py --scenario regression --baseline results/baseline.json
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import docker
import yaml
from load_test_framework import (
    LoadTestConfig,
    LoadTestFramework,
    PerformanceMetrics,
    run_full_performance_suite,
    run_quick_performance_test,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("performance_test.log"),
    ],
)
logger = logging.getLogger(__name__)


class PerformanceTestRunner:
    """Orchestrates comprehensive performance testing campaigns."""

    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)

        # Docker client for infrastructure management
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            sys.exit(1)

        # Test state
        self.current_test_run = None
        self.interrupted = False

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle interruption signals gracefully."""
        logger.warning(f"Received signal {signum}, stopping tests gracefully...")
        self.interrupted = True

        if self.current_test_run:
            logger.info("Saving partial results...")
            self._save_partial_results()

    def _save_partial_results(self):
        """Save partial results when interrupted."""
        if hasattr(self, "partial_metrics") and self.partial_metrics:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            partial_file = self.results_dir / f"partial_results_{timestamp}.json"

            with open(partial_file, "w") as f:
                json.dump([m.to_dict() for m in self.partial_metrics], f, indent=2)

            logger.info(f"Partial results saved to {partial_file}")

    def verify_infrastructure(self) -> bool:
        """Verify that performance testing infrastructure is available."""
        logger.info("Verifying performance testing infrastructure...")

        required_services = [
            "kailash_perf_postgres",
            "kailash_perf_redis",
            "kailash_perf_mysql",
            "kailash_perf_prometheus",
            "kailash_perf_grafana",
        ]

        all_running = True
        for service_name in required_services:
            try:
                container = self.docker_client.containers.get(service_name)
                if container.status != "running":
                    logger.error(
                        f"Service {service_name} is not running (status: {container.status})"
                    )
                    all_running = False
                else:
                    logger.info(f"✓ {service_name} is running")
            except docker.errors.NotFound:
                logger.error(f"Service {service_name} not found")
                all_running = False

        if not all_running:
            logger.error("Some required services are not available")
            logger.info("Start the performance infrastructure with:")
            logger.info("  cd tests/performance")
            logger.info("  docker-compose -f docker-compose.performance.yml up -d")
            return False

        logger.info("✓ All required services are running")
        return True

    def run_baseline_scenario(
        self, concurrency_levels: List[int]
    ) -> Dict[str, PerformanceMetrics]:
        """Run baseline performance testing scenario."""
        logger.info(
            f"Running baseline scenario with concurrency levels: {concurrency_levels}"
        )

        results = {}

        for level in concurrency_levels:
            if self.interrupted:
                break

            logger.info(f"Testing baseline performance at {level} concurrent workflows")

            config = LoadTestConfig(
                concurrent_workflows=level,
                workflow_complexity="medium",
                test_duration=300,  # 5 minutes
            )

            framework = LoadTestFramework(config)

            try:
                with framework.test_infrastructure():
                    metrics = framework.run_baseline_performance_test(level)
                    results[f"baseline_{level}"] = metrics

                    # Save intermediate results
                    self._save_metrics(f"baseline_{level}", metrics)

                    logger.info(
                        f"Baseline {level}: {metrics.throughput:.2f} workflows/sec, "
                        f"{metrics.avg_latency:.3f}s avg latency"
                    )

            except Exception as e:
                logger.error(f"Baseline test at {level} failed: {e}")
                results[f"baseline_{level}_error"] = str(e)

        return results

    def run_stress_scenario(
        self, max_concurrency: int = 2000
    ) -> Dict[str, PerformanceMetrics]:
        """Run stress testing scenario with increasing load."""
        logger.info(
            f"Running stress scenario up to {max_concurrency} concurrent workflows"
        )

        results = {}
        stress_levels = [500, 1000, 1500, max_concurrency]

        for level in stress_levels:
            if self.interrupted:
                break

            logger.info(f"Stress testing at {level} concurrent workflows")

            config = LoadTestConfig(
                concurrent_workflows=level,
                workflow_complexity="complex",
                enable_database_stress=True,
                enable_failure_injection=True,
                failure_rate=0.02,  # 2% failure injection
            )

            framework = LoadTestFramework(config)

            try:
                with framework.test_infrastructure():
                    if level <= 1000:
                        metrics = framework.run_baseline_performance_test(level)
                    else:
                        # Use resource pressure test for high concurrency
                        metrics = framework.run_resource_pressure_test()

                    results[f"stress_{level}"] = metrics
                    self._save_metrics(f"stress_{level}", metrics)

                    logger.info(
                        f"Stress {level}: {metrics.successful_workflows}/{metrics.total_workflows} "
                        f"success, {metrics.error_rate:.1f}% error rate"
                    )

                    # Check if system is failing significantly
                    if metrics.error_rate > 50:
                        logger.warning(
                            f"High error rate at {level}, stopping stress test"
                        )
                        break

            except Exception as e:
                logger.error(f"Stress test at {level} failed: {e}")
                results[f"stress_{level}_error"] = str(e)

        return results

    def run_endurance_scenario(
        self, duration_hours: int = 24
    ) -> List[PerformanceMetrics]:
        """Run long-running endurance test."""
        logger.info(f"Running {duration_hours}-hour endurance test")

        config = LoadTestConfig(
            concurrent_workflows=200,  # Conservative load for endurance
            workflow_complexity="medium",
            metrics_collection_interval=10,  # More frequent monitoring
        )

        framework = LoadTestFramework(config)

        try:
            with framework.test_infrastructure():
                results = framework.run_endurance_test(duration_hours)

                # Save endurance results
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                endurance_file = (
                    self.results_dir / f"endurance_{duration_hours}h_{timestamp}.json"
                )

                with open(endurance_file, "w") as f:
                    json.dump([m.to_dict() for m in results], f, indent=2)

                logger.info(f"Endurance test results saved to {endurance_file}")
                return results

        except Exception as e:
            logger.error(f"Endurance test failed: {e}")
            return []

    def run_regression_scenario(self, baseline_file: str) -> Dict[str, any]:
        """Run regression testing against baseline."""
        logger.info(f"Running regression test against baseline: {baseline_file}")

        # Load baseline metrics
        try:
            with open(baseline_file, "r") as f:
                baseline_data = json.load(f)

            if isinstance(baseline_data, list) and len(baseline_data) > 0:
                baseline_dict = baseline_data[0]
            elif isinstance(baseline_data, dict):
                baseline_dict = baseline_data
            else:
                raise ValueError("Invalid baseline file format")

            baseline_metrics = PerformanceMetrics(**baseline_dict)

        except Exception as e:
            logger.error(f"Failed to load baseline metrics: {e}")
            return {"error": f"Failed to load baseline: {e}"}

        # Run current test with same parameters
        config = LoadTestConfig(
            concurrent_workflows=baseline_metrics.total_workflows,
            workflow_complexity="medium",
        )

        framework = LoadTestFramework(config)

        try:
            with framework.test_infrastructure():
                current_metrics = framework.run_baseline_performance_test(
                    baseline_metrics.total_workflows
                )

                # Analyze regression
                regression_analysis = framework.analyze_performance_regression(
                    baseline_metrics, current_metrics
                )

                # Save regression results
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                regression_file = (
                    self.results_dir / f"regression_analysis_{timestamp}.json"
                )

                regression_data = {
                    "baseline_metrics": baseline_metrics.to_dict(),
                    "current_metrics": current_metrics.to_dict(),
                    "regression_analysis": regression_analysis,
                    "timestamp": timestamp,
                }

                with open(regression_file, "w") as f:
                    json.dump(regression_data, f, indent=2)

                logger.info(f"Regression analysis saved to {regression_file}")

                # Log key findings
                if regression_analysis["performance_regression_detected"]:
                    logger.warning(
                        f"Performance regression detected: {regression_analysis['regression_severity']}"
                    )
                    for recommendation in regression_analysis["recommendations"]:
                        logger.warning(f"  - {recommendation}")
                else:
                    logger.info("No significant performance regression detected")

                return regression_data

        except Exception as e:
            logger.error(f"Regression test failed: {e}")
            return {"error": f"Regression test failed: {e}"}

    def run_database_scenario(self) -> Dict[str, PerformanceMetrics]:
        """Run comprehensive database stress testing."""
        logger.info("Running database stress testing scenario")

        results = {}

        # Test different database loads
        database_configs = [
            {"name": "light_db_load", "concurrent": 100, "db_stress": False},
            {"name": "medium_db_load", "concurrent": 300, "db_stress": True},
            {"name": "heavy_db_load", "concurrent": 500, "db_stress": True},
            {
                "name": "connection_exhaustion",
                "concurrent": 200,
                "db_stress": True,
                "max_connections": 50,
            },
        ]

        for db_config in database_configs:
            if self.interrupted:
                break

            logger.info(f"Testing database scenario: {db_config['name']}")

            config = LoadTestConfig(
                concurrent_workflows=db_config["concurrent"],
                enable_database_stress=db_config["db_stress"],
                max_db_connections=db_config.get("max_connections", 100),
                workflow_types=["analytics", "data_processing"],  # Database-heavy
            )

            framework = LoadTestFramework(config)

            try:
                with framework.test_infrastructure():
                    if "connection_exhaustion" in db_config["name"]:
                        metrics = framework.run_database_stress_test()
                    else:
                        metrics = framework.run_baseline_performance_test(
                            db_config["concurrent"]
                        )

                    results[db_config["name"]] = metrics
                    self._save_metrics(db_config["name"], metrics)

                    logger.info(
                        f"DB scenario {db_config['name']}: "
                        f"{metrics.peak_connections} peak connections, "
                        f"{metrics.connection_errors} connection errors"
                    )

            except Exception as e:
                logger.error(f"Database scenario {db_config['name']} failed: {e}")
                results[f"{db_config['name']}_error"] = str(e)

        return results

    def _save_metrics(self, test_name: str, metrics: PerformanceMetrics):
        """Save metrics to individual file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = self.results_dir / f"{test_name}_{timestamp}.json"

        with open(metrics_file, "w") as f:
            json.dump(metrics.to_dict(), f, indent=2)

        logger.debug(f"Metrics saved to {metrics_file}")

    def generate_comprehensive_report(self, results: Dict) -> str:
        """Generate comprehensive test campaign report."""
        logger.info("Generating comprehensive performance report")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.results_dir / f"comprehensive_report_{timestamp}.md"

        report = f"""# Kailash LocalRuntime Performance Test Campaign Report

**Test Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Test Duration:** {len(results)} scenarios executed
**Infrastructure:** Docker-based real services

## Executive Summary

"""

        # Analyze results for summary
        total_tests = len([k for k in results.keys() if not k.endswith("_error")])
        failed_tests = len([k for k in results.keys() if k.endswith("_error")])
        success_rate = (
            ((total_tests - failed_tests) / total_tests * 100) if total_tests > 0 else 0
        )

        report += f"""
- **Total Test Scenarios:** {total_tests}
- **Successful Scenarios:** {total_tests - failed_tests}
- **Failed Scenarios:** {failed_tests}
- **Overall Success Rate:** {success_rate:.1f}%

"""

        # Performance highlights
        best_throughput = 0
        worst_latency = 0
        highest_concurrency = 0

        for test_name, result in results.items():
            if isinstance(result, PerformanceMetrics):
                best_throughput = max(best_throughput, result.throughput)
                worst_latency = max(worst_latency, result.avg_latency)
                highest_concurrency = max(highest_concurrency, result.total_workflows)

        report += f"""
## Performance Highlights

- **Best Throughput Achieved:** {best_throughput:.2f} workflows/second
- **Highest Concurrency Tested:** {highest_concurrency} concurrent workflows
- **Maximum Latency Observed:** {worst_latency:.3f} seconds

"""

        # Detailed results
        report += "## Detailed Test Results\n\n"

        for test_name, result in results.items():
            report += f"### {test_name.replace('_', ' ').title()}\n\n"

            if isinstance(result, PerformanceMetrics):
                report += f"""
- **Total Workflows:** {result.total_workflows}
- **Success Rate:** {(result.successful_workflows / result.total_workflows) * 100:.2f}%
- **Throughput:** {result.throughput:.2f} workflows/second
- **Average Latency:** {result.avg_latency:.3f} seconds
- **P99 Latency:** {result.p99_latency:.3f} seconds
- **Peak Memory:** {result.peak_memory_mb:.1f} MB
- **Peak CPU:** {result.peak_cpu_percent:.1f}%
- **Error Rate:** {result.error_rate:.2f}%

"""
            else:
                report += f"**Result:** {result}\n\n"

        # Recommendations
        report += """## Recommendations

Based on the performance test results:

"""

        # Analyze for recommendations
        if best_throughput < 10:
            report += "- **Low Throughput:** Consider investigating bottlenecks in workflow execution\n"

        if worst_latency > 5.0:
            report += "- **High Latency:** Optimize workflow complexity or increase resources\n"

        if failed_tests > 0:
            report += f"- **Test Failures:** Investigate {failed_tests} failed scenarios for stability issues\n"

        report += "\n## Infrastructure Configuration\n\n"
        report += "- **PostgreSQL:** Performance-tuned with 500 max connections\n"
        report += "- **MySQL:** Optimized InnoDB configuration\n"
        report += "- **Redis:** 2GB memory limit, persistence disabled\n"
        report += "- **Monitoring:** Prometheus + Grafana stack\n"

        # Save report
        with open(report_file, "w") as f:
            f.write(report)

        logger.info(f"Comprehensive report saved to {report_file}")
        return str(report_file)


def main():
    parser = argparse.ArgumentParser(description="Kailash Performance Test Runner")

    parser.add_argument(
        "--scenario",
        required=True,
        choices=["baseline", "stress", "endurance", "regression", "database", "full"],
        help="Test scenario to run",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[100, 500, 1000],
        help="Concurrency levels for baseline testing",
    )

    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2000,
        help="Maximum concurrency for stress testing",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=1,
        help="Duration in hours for endurance testing",
    )

    parser.add_argument(
        "--baseline", type=str, help="Baseline file for regression testing"
    )

    parser.add_argument(
        "--results-dir", type=str, default="results", help="Directory to save results"
    )

    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify infrastructure, don't run tests",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize test runner
    runner = PerformanceTestRunner(args.results_dir)

    # Verify infrastructure
    if not runner.verify_infrastructure():
        logger.error("Infrastructure verification failed")
        sys.exit(1)

    if args.verify_only:
        logger.info("Infrastructure verification successful")
        sys.exit(0)

    # Run selected scenario
    results = {}

    try:
        if args.scenario == "baseline":
            results = runner.run_baseline_scenario(args.concurrency)

        elif args.scenario == "stress":
            results = runner.run_stress_scenario(args.max_concurrency)

        elif args.scenario == "endurance":
            endurance_results = runner.run_endurance_scenario(args.duration)
            results = {"endurance": endurance_results}

        elif args.scenario == "regression":
            if not args.baseline:
                logger.error("Baseline file required for regression testing")
                sys.exit(1)
            results = runner.run_regression_scenario(args.baseline)

        elif args.scenario == "database":
            results = runner.run_database_scenario()

        elif args.scenario == "full":
            logger.info("Running full performance test suite")
            results.update(runner.run_baseline_scenario([100, 500, 1000]))
            results.update(runner.run_stress_scenario(1500))
            results.update(runner.run_database_scenario())

        # Generate comprehensive report
        if results:
            report_file = runner.generate_comprehensive_report(results)
            logger.info("Test campaign completed successfully")
            logger.info(f"Comprehensive report: {report_file}")
        else:
            logger.warning("No test results generated")

    except KeyboardInterrupt:
        logger.info("Test campaign interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Test campaign failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
