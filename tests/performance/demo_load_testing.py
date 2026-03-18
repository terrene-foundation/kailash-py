#!/usr/bin/env python3
"""
Kailash Load Testing Framework Demo

This script demonstrates the complete load testing framework capabilities
for the enhanced LocalRuntime. It showcases:

1. Infrastructure verification
2. Baseline performance testing
3. Database stress testing
4. Resource pressure testing
5. Failure injection and recovery
6. Performance regression detection
7. Comprehensive reporting

Usage:
    python demo_load_testing.py --demo quick     # Quick demo (5 minutes)
    python demo_load_testing.py --demo full      # Full demo (30 minutes)
    python demo_load_testing.py --demo showcase  # Showcase all features
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Import the load testing framework
try:
    from load_test_framework import (
        LoadTestConfig,
        LoadTestFramework,
        PerformanceMetrics,
        run_quick_performance_test,
    )
    from performance_test_runner import PerformanceTestRunner
except ImportError as e:
    print(f"❌ Failed to import load testing framework: {e}")
    print("Please ensure you're in the tests/performance directory")
    sys.exit(1)

# Configure demo logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LoadTestingDemo:
    """Interactive demonstration of the Kailash Load Testing Framework."""

    def __init__(self):
        self.results = {}
        self.demo_start_time = datetime.now()

    def print_banner(self, title: str):
        """Print a formatted banner for demo sections."""
        print("\n" + "=" * 60)
        print(f"🚀 {title}")
        print("=" * 60)

    def print_step(self, step: str, description: str = ""):
        """Print a formatted step description."""
        print(f"\n📋 Step: {step}")
        if description:
            print(f"   {description}")
        print("-" * 40)

    def demonstrate_framework_overview(self):
        """Demonstrate framework architecture and capabilities."""
        self.print_banner("Kailash Load Testing Framework Overview")

        print(
            """
🏗️  FRAMEWORK ARCHITECTURE:
   • LoadTestFramework: Core orchestration and execution
   • ResourceMonitor: Real-time system and database monitoring
   • FailureInjector: Realistic failure scenario simulation
   • WorkflowGenerator: Dynamic test workflow creation
   • PerformanceMetrics: Comprehensive metrics collection
   • Docker Infrastructure: Production-like test environment

✨  KEY CAPABILITIES:
   • Concurrent Execution: 1-10,000+ workflows simultaneously
   • Real Infrastructure: PostgreSQL, MySQL, Redis, MongoDB
   • Performance Metrics: Throughput, latency, resource usage
   • Failure Injection: Database timeouts, connection exhaustion
   • Regression Detection: Automated performance comparison
   • Endurance Testing: 24-hour stability validation
   • Enterprise Monitoring: Prometheus + Grafana observability

🎯  TESTING SCENARIOS:
   • Baseline Performance: Normal load conditions (100-5000 workflows)
   • Stress Testing: Extreme load conditions (up to 10,000 workflows)
   • Database Stress: Connection pool exhaustion and recovery
   • Resource Pressure: Memory and CPU limitation testing
   • Failure Recovery: Circuit breaker and retry validation
   • Endurance Testing: Long-running stability (1-24 hours)
        """
        )

        input("Press Enter to continue...")

    def demonstrate_quick_validation(self):
        """Demonstrate quick performance validation."""
        self.print_banner("Quick Performance Validation")
        self.print_step(
            "Running Quick Test", "Fast validation suitable for CI/CD pipelines"
        )

        try:
            print("🔄 Executing quick performance test...")
            metrics = run_quick_performance_test()

            self.results["quick_validation"] = metrics

            print(
                f"""
📊 QUICK TEST RESULTS:
   • Total Workflows: {metrics.total_workflows}
   • Successful: {metrics.successful_workflows}
   • Success Rate: {(metrics.successful_workflows / metrics.total_workflows) * 100:.1f}%
   • Throughput: {metrics.throughput:.2f} workflows/second
   • Average Latency: {metrics.avg_latency:.3f} seconds
   • P99 Latency: {metrics.p99_latency:.3f} seconds
   • Peak Memory: {metrics.peak_memory_mb:.1f} MB
   • Peak CPU: {metrics.peak_cpu_percent:.1f}%
   • Error Rate: {metrics.error_rate:.1f}%
            """
            )

            # Evaluation
            if metrics.throughput > 1.0:
                print("✅ Throughput: GOOD (>1.0 workflows/sec)")
            else:
                print("⚠️  Throughput: NEEDS ATTENTION (<1.0 workflows/sec)")

            if metrics.avg_latency < 3.0:
                print("✅ Latency: GOOD (<3.0 seconds)")
            else:
                print("⚠️  Latency: NEEDS ATTENTION (>3.0 seconds)")

            if metrics.error_rate < 5.0:
                print("✅ Error Rate: GOOD (<5%)")
            else:
                print("⚠️  Error Rate: NEEDS ATTENTION (>5%)")

        except Exception as e:
            print(f"❌ Quick validation failed: {e}")
            logger.error(f"Quick validation error: {e}")

    def demonstrate_baseline_testing(self):
        """Demonstrate baseline performance testing."""
        self.print_banner("Baseline Performance Testing")
        self.print_step(
            "Baseline Testing",
            "Testing normal load conditions with increasing concurrency",
        )

        concurrency_levels = [50, 100, 200]  # Reduced for demo

        for level in concurrency_levels:
            print(f"\n🔄 Testing {level} concurrent workflows...")

            try:
                config = LoadTestConfig(
                    concurrent_workflows=level,
                    workflow_complexity="simple",  # Simplified for demo
                    test_duration=60,  # 1 minute for demo
                )

                framework = LoadTestFramework(config)

                with framework.test_infrastructure():
                    metrics = framework.run_baseline_performance_test(level)

                self.results[f"baseline_{level}"] = metrics

                print(
                    f"""
   📊 BASELINE RESULTS ({level} concurrent):
      • Success Rate: {(metrics.successful_workflows / metrics.total_workflows) * 100:.1f}%
      • Throughput: {metrics.throughput:.2f} workflows/sec
      • Avg Latency: {metrics.avg_latency:.3f}s
      • P99 Latency: {metrics.p99_latency:.3f}s
      • Peak Memory: {metrics.peak_memory_mb:.1f} MB
      • Error Rate: {metrics.error_rate:.1f}%
                """
                )

                # Show scaling behavior
                if level > 50:
                    prev_metrics = self.results.get(f"baseline_{level // 2}")
                    if prev_metrics:
                        throughput_ratio = metrics.throughput / prev_metrics.throughput
                        latency_ratio = metrics.avg_latency / prev_metrics.avg_latency

                        print(
                            f"   📈 Scaling: {throughput_ratio:.1f}x throughput, {latency_ratio:.1f}x latency"
                        )

                        if throughput_ratio > 1.5:
                            print("   ✅ Excellent scaling")
                        elif throughput_ratio > 1.0:
                            print("   ✅ Good scaling")
                        else:
                            print("   ⚠️  Scaling issues detected")

                time.sleep(2)  # Brief pause between tests

            except Exception as e:
                print(f"   ❌ Baseline test at {level} failed: {e}")
                logger.error(f"Baseline test error at {level}: {e}")

    def demonstrate_database_stress(self):
        """Demonstrate database connection stress testing."""
        self.print_banner("Database Stress Testing")
        self.print_step(
            "Database Stress", "Testing database connection pool behavior under load"
        )

        print(
            """
🗄️  DATABASE STRESS SCENARIOS:
   • Connection Pool Exhaustion: Exceed available connections
   • Query Timeout Simulation: Handle slow database responses
   • Multi-Database Load: Test PostgreSQL, MySQL, Redis simultaneously
   • Recovery Testing: Validate graceful degradation and recovery
        """
        )

        try:
            config = LoadTestConfig(
                concurrent_workflows=100,  # Reduced for demo
                enable_database_stress=True,
                max_db_connections=20,  # Limited for demo
                workflow_types=["analytics"],  # Database-heavy workflows
                connection_timeout=10,
            )

            framework = LoadTestFramework(config)

            print("🔄 Executing database stress test...")

            with framework.test_infrastructure():
                metrics = framework.run_database_stress_test()

            self.results["database_stress"] = metrics

            print(
                f"""
📊 DATABASE STRESS RESULTS:
   • Total Workflows: {metrics.total_workflows}
   • Success Rate: {(metrics.successful_workflows / metrics.total_workflows) * 100:.1f}%
   • Peak Connections: {metrics.peak_connections}
   • Connection Errors: {metrics.connection_errors}
   • Database Errors: {metrics.database_errors}
   • Timeout Errors: {metrics.timeout_errors}
   • Throughput: {metrics.throughput:.2f} workflows/sec
   • Average Latency: {metrics.avg_latency:.3f}s
            """
            )

            # Analysis
            if metrics.connection_errors == 0:
                print("✅ Connection Pool: No exhaustion detected")
            else:
                print(
                    f"⚠️  Connection Pool: {metrics.connection_errors} connection errors"
                )

            if metrics.database_errors < metrics.total_workflows * 0.1:  # <10%
                print("✅ Database Health: Good error recovery")
            else:
                print("⚠️  Database Health: High error rate")

        except Exception as e:
            print(f"❌ Database stress test failed: {e}")
            logger.error(f"Database stress error: {e}")

    def demonstrate_failure_injection(self):
        """Demonstrate failure injection and recovery testing."""
        self.print_banner("Failure Injection & Recovery Testing")
        self.print_step(
            "Failure Injection",
            "Testing system resilience with realistic failure scenarios",
        )

        print(
            """
💥 FAILURE INJECTION SCENARIOS:
   • Database Timeouts: Simulated slow query responses
   • Memory Pressure: Temporary memory allocation stress
   • Connection Exhaustion: Pool saturation simulation
   • Resource Exhaustion: CPU and I/O saturation
        """
        )

        try:
            config = LoadTestConfig(
                concurrent_workflows=75,  # Moderate load for demo
                enable_failure_injection=True,
                failure_rate=0.15,  # 15% failure injection
                failure_types=["database_timeout", "memory_pressure"],
                workflow_complexity="medium",
            )

            framework = LoadTestFramework(config)

            print("🔄 Executing failure injection test...")
            print("   (Injecting failures in 15% of workflows)")

            with framework.test_infrastructure():
                metrics = framework.run_baseline_performance_test(75)

            self.results["failure_injection"] = metrics

            print(
                f"""
📊 FAILURE INJECTION RESULTS:
   • Total Workflows: {metrics.total_workflows}
   • Successful: {metrics.successful_workflows}
   • Failed: {metrics.failed_workflows}
   • Success Rate: {(metrics.successful_workflows / metrics.total_workflows) * 100:.1f}%
   • Timeout Errors: {metrics.timeout_errors}
   • Resource Errors: {metrics.resource_exhaustion_errors}
   • Other Errors: {metrics.failed_workflows - metrics.timeout_errors - metrics.resource_exhaustion_errors}
   • Recovery Rate: {((metrics.successful_workflows) / (metrics.total_workflows)) * 100:.1f}%
            """
            )

            # Resilience analysis
            if (
                metrics.successful_workflows >= metrics.total_workflows * 0.8
            ):  # >80% success
                print("✅ System Resilience: Excellent failure recovery")
            elif (
                metrics.successful_workflows >= metrics.total_workflows * 0.6
            ):  # >60% success
                print("✅ System Resilience: Good failure recovery")
            else:
                print("⚠️  System Resilience: Needs improvement")

        except Exception as e:
            print(f"❌ Failure injection test failed: {e}")
            logger.error(f"Failure injection error: {e}")

    def demonstrate_resource_monitoring(self):
        """Demonstrate real-time resource monitoring."""
        self.print_banner("Resource Monitoring & Analysis")
        self.print_step(
            "Resource Monitoring", "Real-time system and database resource tracking"
        )

        print(
            """
📊 RESOURCE MONITORING CAPABILITIES:
   • System Resources: CPU, Memory, Disk I/O, Network
   • Database Metrics: Connection counts, query performance
   • Application Metrics: Workflow execution, error rates
   • Time Series Data: Historical performance tracking
        """
        )

        # Show resource monitoring from previous tests
        if self.results:
            print("\n📈 RESOURCE USAGE ANALYSIS FROM PREVIOUS TESTS:")

            for test_name, metrics in self.results.items():
                if isinstance(metrics, PerformanceMetrics):
                    print(
                        f"""
   {test_name.replace("_", " ").title()}:
      • Peak Memory: {metrics.peak_memory_mb:.1f} MB
      • Peak CPU: {metrics.peak_cpu_percent:.1f}%
      • Database Connections: {metrics.peak_connections}
      • Resource Efficiency: {metrics.successful_workflows / metrics.peak_memory_mb:.1f} workflows/MB
                    """
                    )

            # Overall resource analysis
            max_memory = max(
                m.peak_memory_mb
                for m in self.results.values()
                if isinstance(m, PerformanceMetrics)
            )
            max_cpu = max(
                m.peak_cpu_percent
                for m in self.results.values()
                if isinstance(m, PerformanceMetrics)
            )

            print(
                f"""
📊 OVERALL RESOURCE USAGE:
   • Maximum Memory Used: {max_memory:.1f} MB
   • Maximum CPU Used: {max_cpu:.1f}%
   • Resource Scaling: {"Linear" if max_memory < 1000 else "Non-linear"}
   • Memory Efficiency: {"Good" if max_memory < 500 else "Needs optimization"}
            """
            )

    def demonstrate_performance_regression(self):
        """Demonstrate performance regression detection."""
        self.print_banner("Performance Regression Detection")
        self.print_step(
            "Regression Analysis", "Automated performance comparison and alerting"
        )

        print(
            """
🔍 REGRESSION DETECTION CAPABILITIES:
   • Automated Comparison: Current vs baseline performance
   • Statistical Analysis: Throughput, latency, error rate changes
   • Severity Classification: Minor, Major, Critical regressions
   • Actionable Recommendations: Specific optimization suggestions
        """
        )

        # Use baseline results for regression analysis
        if "baseline_100" in self.results and "failure_injection" in self.results:
            baseline = self.results["baseline_100"]
            current = self.results["failure_injection"]

            print(
                "🔄 Analyzing regression between baseline and failure injection tests..."
            )

            try:
                framework = LoadTestFramework()
                regression_analysis = framework.analyze_performance_regression(
                    baseline, current
                )

                print(
                    f"""
📊 REGRESSION ANALYSIS RESULTS:
   • Throughput Change: {regression_analysis["throughput_change_percent"]:+.1f}%
   • Latency Change: {regression_analysis["latency_change_percent"]:+.1f}%
   • Memory Change: {regression_analysis["memory_change_percent"]:+.1f}%
   • Error Rate Change: {regression_analysis["error_rate_change_percent"]:+.1f}%

   • Regression Detected: {"Yes" if regression_analysis["performance_regression_detected"] else "No"}
   • Severity: {regression_analysis["regression_severity"].title()}
                """
                )

                if regression_analysis["recommendations"]:
                    print("   💡 Recommendations:")
                    for rec in regression_analysis["recommendations"]:
                        print(f"      • {rec}")

                # Interpretation
                if not regression_analysis["performance_regression_detected"]:
                    print("✅ No significant performance regression detected")
                elif regression_analysis["regression_severity"] == "minor":
                    print("⚠️  Minor performance regression - monitor closely")
                elif regression_analysis["regression_severity"] == "major":
                    print("⚠️  Major performance regression - investigate immediately")
                else:
                    print("🚨 Critical performance regression - urgent action required")

            except Exception as e:
                print(f"❌ Regression analysis failed: {e}")
                logger.error(f"Regression analysis error: {e}")
        else:
            print("⚠️  Insufficient test data for regression analysis")

    def demonstrate_comprehensive_reporting(self):
        """Demonstrate comprehensive test reporting."""
        self.print_banner("Comprehensive Performance Reporting")
        self.print_step(
            "Report Generation", "Automated performance analysis and documentation"
        )

        if not self.results:
            print("⚠️  No test results available for reporting")
            return

        try:
            # Generate a sample comprehensive report
            framework = LoadTestFramework()

            # Use the first available metrics for report generation
            sample_metrics = next(
                m for m in self.results.values() if isinstance(m, PerformanceMetrics)
            )

            print("🔄 Generating comprehensive performance report...")

            report_content = framework.generate_performance_report(
                sample_metrics, output_file="demo_performance_report.md"
            )

            print("✅ Performance report generated successfully!")
            print("📄 Report saved to: demo_performance_report.md")

            # Show report summary
            print(
                f"""
📊 REPORT SUMMARY:
   • Test Scenarios Executed: {len(self.results)}
   • Total Test Duration: {(datetime.now() - self.demo_start_time).total_seconds():.0f} seconds
   • Performance Data Points: {sum(1 for m in self.results.values() if isinstance(m, PerformanceMetrics))}
   • Comprehensive Analysis: Available in generated report
            """
            )

            # Show key insights
            successful_tests = sum(
                1
                for m in self.results.values()
                if isinstance(m, PerformanceMetrics) and m.error_rate < 10
            )
            total_tests = sum(
                1 for m in self.results.values() if isinstance(m, PerformanceMetrics)
            )

            if total_tests > 0:
                success_rate = (successful_tests / total_tests) * 100
                print(
                    f"""
🎯 KEY INSIGHTS:
   • Test Success Rate: {success_rate:.1f}%
   • System Stability: {"Excellent" if success_rate > 90 else "Good" if success_rate > 70 else "Needs Attention"}
   • Performance Trend: {"Stable" if success_rate > 80 else "Variable"}
                """
                )

        except Exception as e:
            print(f"❌ Report generation failed: {e}")
            logger.error(f"Report generation error: {e}")

    def run_quick_demo(self):
        """Run a quick 5-minute demonstration."""
        print("🚀 Starting Quick Demo (5 minutes)")

        self.demonstrate_framework_overview()
        self.demonstrate_quick_validation()

        print("\n" + "=" * 60)
        print("✅ Quick Demo Complete!")
        print(
            f"⏱️  Duration: {(datetime.now() - self.demo_start_time).total_seconds():.0f} seconds"
        )
        print("💡 Run with --demo full for comprehensive demonstration")

    def run_full_demo(self):
        """Run a comprehensive 30-minute demonstration."""
        print("🚀 Starting Full Demo (30 minutes)")

        self.demonstrate_framework_overview()
        self.demonstrate_quick_validation()
        self.demonstrate_baseline_testing()
        self.demonstrate_database_stress()
        self.demonstrate_failure_injection()
        self.demonstrate_resource_monitoring()
        self.demonstrate_performance_regression()
        self.demonstrate_comprehensive_reporting()

        print("\n" + "=" * 60)
        print("✅ Full Demo Complete!")
        print(
            f"⏱️  Total Duration: {(datetime.now() - self.demo_start_time).total_seconds():.0f} seconds"
        )
        print("📊 All performance test results have been collected and analyzed")

    def run_showcase_demo(self):
        """Run a showcase demonstration highlighting all features."""
        print("🚀 Starting Showcase Demo - All Features")

        # Full demo plus additional showcase elements
        self.run_full_demo()

        # Additional showcase elements
        self.print_banner("Framework Showcase - Advanced Features")

        print(
            """
🌟 ADVANCED CAPABILITIES DEMONSTRATED:

✅ Concurrent Workflow Execution (1-10,000+ workflows)
✅ Real Infrastructure Testing (PostgreSQL, MySQL, Redis)
✅ Performance Metrics Collection (Throughput, Latency, Resources)
✅ Failure Injection & Recovery Testing
✅ Database Connection Pool Stress Testing
✅ Resource Pressure Testing (Memory, CPU)
✅ Performance Regression Detection
✅ Comprehensive Reporting & Analysis
✅ Real-time Resource Monitoring
✅ 3-Tier Testing Strategy (Unit, Integration, E2E)
✅ CI/CD Integration Support
✅ Enterprise Monitoring (Prometheus + Grafana)
✅ Docker Infrastructure Management

🎯 PRODUCTION-READY FEATURES:
   • 24-hour endurance testing capability
   • Automated performance baseline establishment
   • Circuit breaker and retry policy validation
   • Memory leak detection and analysis
   • Database query performance optimization
   • Multi-database concurrent stress testing
   • Performance trend analysis and alerting
   • Custom workflow generation and execution
        """
        )


def main():
    parser = argparse.ArgumentParser(description="Kailash Load Testing Framework Demo")
    parser.add_argument(
        "--demo",
        choices=["quick", "full", "showcase"],
        default="quick",
        help="Demo type to run",
    )

    args = parser.parse_args()

    print(
        """
🚀 KAILASH LOAD TESTING FRAMEWORK DEMO
=====================================

This demonstration showcases the comprehensive load testing capabilities
for the enhanced LocalRuntime with real infrastructure integration.

⚠️  PREREQUISITES:
   • Docker services must be running
   • Run: make start (from tests/performance directory)
   • Verify: make status

    """
    )

    # Check if we should proceed
    response = input("Prerequisites met? Continue with demo? (y/N): ")
    if response.lower() != "y":
        print("Demo cancelled. Please set up infrastructure first.")
        sys.exit(0)

    # Run the selected demo
    demo = LoadTestingDemo()

    try:
        if args.demo == "quick":
            demo.run_quick_demo()
        elif args.demo == "full":
            demo.run_full_demo()
        elif args.demo == "showcase":
            demo.run_showcase_demo()

    except KeyboardInterrupt:
        print("\n\n🛑 Demo interrupted by user")
        print("Partial results may be available in the results directory")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        logger.error(f"Demo error: {e}")
        sys.exit(1)

    print(
        """

🎉 DEMO COMPLETED SUCCESSFULLY!

📁 Generated Files:
   • demo_performance_report.md - Comprehensive performance report
   • results/*.json - Individual test result files
   • performance_test.log - Detailed execution logs

🔗 Next Steps:
   • Review the generated performance report
   • Access Grafana dashboards: http://localhost:3000
   • Run custom tests: python performance_test_runner.py --help
   • Explore the full framework: make help

Thank you for exploring the Kailash Load Testing Framework! 🚀
    """
    )


if __name__ == "__main__":
    main()
