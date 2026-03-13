#!/usr/bin/env python3
"""
Fixture Validation Script for Kaizen Test Suite

Validates fixture reusability, performance characteristics, and compliance
with the 3-tier testing strategy. Ensures gold standard quality.

Features:
- Fixture import validation
- Performance benchmarking
- Memory usage analysis
- Cross-tier compatibility testing
- Infrastructure dependency checking
"""

import importlib
import importlib.util
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List

import psutil

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))


class ValidationResult:
    """Container for validation results."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.performance_data: Dict[str, float] = {}

    def add_pass(self, test_name: str):
        self.passed += 1
        print(f"✅ {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ {test_name}: {error}")

    def add_skip(self, test_name: str, reason: str):
        self.skipped += 1
        self.warnings.append(f"{test_name}: {reason}")
        print(f"⏸️  {test_name}: {reason}")

    def add_performance(self, operation: str, duration_ms: float):
        self.performance_data[operation] = duration_ms

    def get_summary(self) -> str:
        total = self.passed + self.failed + self.skipped
        success_rate = (self.passed / total * 100) if total > 0 else 0

        summary = f"""
=== Fixture Validation Summary ===
Total Tests: {total}
Passed: {self.passed}
Failed: {self.failed}
Skipped: {self.skipped}
Success Rate: {success_rate:.1f}%

Performance Data:
"""
        for operation, duration in self.performance_data.items():
            summary += f"  {operation}: {duration:.2f}ms\n"

        if self.errors:
            summary += "\nErrors:\n"
            for error in self.errors:
                summary += f"  - {error}\n"

        if self.warnings:
            summary += "\nWarnings:\n"
            for warning in self.warnings:
                summary += f"  - {warning}\n"

        return summary


class FixtureValidator:
    """Validates fixture system performance and reusability."""

    def __init__(self):
        self.result = ValidationResult()
        self.process = psutil.Process()

    @contextmanager
    def measure_performance(self, operation: str):
        """Context manager to measure operation performance."""
        start_time = time.perf_counter()
        start_memory = self.process.memory_info().rss / 1024 / 1024  # MB

        try:
            yield
        finally:
            end_time = time.perf_counter()
            end_memory = self.process.memory_info().rss / 1024 / 1024  # MB

            duration_ms = (end_time - start_time) * 1000
            memory_increase = end_memory - start_memory

            self.result.add_performance(operation, duration_ms)

            if memory_increase > 50:  # More than 50MB increase
                self.result.warnings.append(
                    f"{operation} used {memory_increase:.1f}MB memory"
                )

    def validate_imports(self) -> None:
        """Validate that all fixture modules can be imported."""
        modules_to_test = [
            "consolidated_test_fixtures",
            "tier_optimizations",
            "standardized_configs",
        ]

        for module_name in modules_to_test:
            try:
                with self.measure_performance(f"import_{module_name}"):
                    if module_name == "consolidated_test_fixtures":
                        # Import from fixtures directory
                        fixture_path = (
                            Path(__file__).parent.parent
                            / "fixtures"
                            / f"{module_name}.py"
                        )
                        spec = importlib.util.spec_from_file_location(
                            module_name, fixture_path
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                    else:
                        # Import from utils directory
                        utils_path = Path(__file__).parent / f"{module_name}.py"
                        spec = importlib.util.spec_from_file_location(
                            module_name, utils_path
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                # Validate expected exports
                expected_exports = {
                    "consolidated_test_fixtures": [
                        "ConsolidatedTestFixtures",
                        "TestScenario",
                        "consolidated_fixtures",
                    ],
                    "tier_optimizations": [
                        "TestTier",
                        "TierOptimizer",
                        "TierPerformanceMonitor",
                    ],
                    "standardized_configs": [
                        "StandardConfigurationManager",
                        "standard_config",
                    ],
                }

                for export in expected_exports.get(module_name, []):
                    if not hasattr(module, export):
                        self.result.add_fail(
                            f"import_{module_name}", f"Missing export: {export}"
                        )
                        return

                self.result.add_pass(f"import_{module_name}")

            except Exception as e:
                self.result.add_fail(f"import_{module_name}", str(e))

    def validate_conftest_fixtures(self) -> None:
        """Validate conftest.py fixtures."""
        try:
            with self.measure_performance("import_conftest"):
                # Import conftest from the tests directory
                conftest_path = Path(__file__).parent.parent / "conftest.py"
                if not conftest_path.exists():
                    self.result.add_fail("conftest_fixtures", "conftest.py not found")
                    return

                spec = importlib.util.spec_from_file_location("conftest", conftest_path)
                conftest = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(conftest)

                # Check for expected fixtures
                expected_fixtures = [
                    "postgres_connection_string",
                    "redis_connection_config",
                    "docker_services",
                    "performance_tracker",
                ]

                missing_fixtures = []
                for fixture_name in expected_fixtures:
                    if not hasattr(conftest, fixture_name):
                        missing_fixtures.append(fixture_name)

                if missing_fixtures:
                    self.result.add_fail(
                        "conftest_fixtures", f"Missing fixtures: {missing_fixtures}"
                    )
                else:
                    self.result.add_pass("conftest_fixtures")

        except Exception as e:
            self.result.add_fail("conftest_fixtures", str(e))

    def validate_tier_configurations(self) -> None:
        """Validate tier-specific configurations."""
        try:
            # Import standardized_configs directly
            configs_path = Path(__file__).parent / "standardized_configs.py"
            spec = importlib.util.spec_from_file_location(
                "standardized_configs", configs_path
            )
            configs_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(configs_module)

            ConfigurationTier = configs_module.ConfigurationTier
            standard_config = configs_module.standard_config

            tiers = [
                ConfigurationTier.UNIT,
                ConfigurationTier.INTEGRATION,
                ConfigurationTier.E2E,
            ]

            for tier in tiers:
                with self.measure_performance(f"tier_config_{tier.value}"):
                    config = standard_config.get_tier_configuration(tier)

                    # Validate required fields
                    required_fields = [
                        "tier",
                        "timeouts",
                        "memory_limits",
                        "agent_config",
                        "kaizen_config",
                    ]

                    missing_fields = []
                    for field in required_fields:
                        if field not in config:
                            missing_fields.append(field)

                    if missing_fields:
                        self.result.add_fail(
                            f"tier_config_{tier.value}",
                            f"Missing fields: {missing_fields}",
                        )
                    else:
                        # Validate timeout values are reasonable
                        timeouts = config["timeouts"]
                        if timeouts["max_test_time_ms"] <= 0:
                            self.result.add_fail(
                                f"tier_config_{tier.value}", "Invalid max test time"
                            )
                        elif timeouts["max_test_time_ms"] > 60000:  # More than 1 minute
                            self.result.warnings.append(
                                f"Tier {tier.value} has very high timeout: {timeouts['max_test_time_ms']}ms"
                            )
                        else:
                            self.result.add_pass(f"tier_config_{tier.value}")

        except Exception as e:
            self.result.add_fail("tier_configurations", str(e))

    def validate_performance_characteristics(self) -> None:
        """Validate performance characteristics of fixture system."""
        try:
            # Import consolidated_test_fixtures
            fixtures_path = (
                Path(__file__).parent.parent
                / "fixtures"
                / "consolidated_test_fixtures.py"
            )
            spec = importlib.util.spec_from_file_location(
                "consolidated_test_fixtures", fixtures_path
            )
            fixtures_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixtures_module)
            ConsolidatedTestFixtures = fixtures_module.ConsolidatedTestFixtures

            # Import tier_optimizations
            tier_path = Path(__file__).parent / "tier_optimizations.py"
            spec = importlib.util.spec_from_file_location(
                "tier_optimizations", tier_path
            )
            tier_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tier_module)
            TierOptimizer = tier_module.TierOptimizer

            # Test fixture creation performance
            with self.measure_performance("fixture_creation"):
                fixtures = ConsolidatedTestFixtures()
                optimizer = TierOptimizer()

            # Test configuration generation performance
            with self.measure_performance("config_generation"):
                TestTier = tier_module.TestTier
                for tier_name in ["unit", "integration", "e2e"]:
                    tier = (
                        TestTier.UNIT
                        if tier_name == "unit"
                        else (
                            TestTier.INTEGRATION
                            if tier_name == "integration"
                            else TestTier.E2E
                        )
                    )
                    optimizer.optimize_for_tier(tier)

            # Test cleanup performance
            with self.measure_performance("fixture_cleanup"):
                fixtures.cleanup()

            self.result.add_pass("performance_characteristics")

        except Exception as e:
            self.result.add_fail("performance_characteristics", str(e))

    def validate_infrastructure_integration(self) -> None:
        """Validate infrastructure integration capabilities."""
        try:
            # Test infrastructure availability checking
            with self.measure_performance("infrastructure_check"):
                try:
                    # Try to import docker_config from parent SDK
                    docker_config_path = Path(
                        ""
                    )
                    if docker_config_path.exists():
                        spec = importlib.util.spec_from_file_location(
                            "docker_config", docker_config_path
                        )
                        docker_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(docker_module)

                        is_postgres_available = docker_module.is_postgres_available
                        is_redis_available = docker_module.is_redis_available
                        is_ollama_available = docker_module.is_ollama_available
                    else:
                        raise ImportError("docker_config not found")

                    # Just check that functions are callable
                    postgres_available = is_postgres_available()
                    redis_available = is_redis_available()
                    ollama_available = is_ollama_available()

                    infrastructure_status = {
                        "postgres": postgres_available,
                        "redis": redis_available,
                        "ollama": ollama_available,
                    }

                    if not any(infrastructure_status.values()):
                        self.result.add_skip(
                            "infrastructure_integration",
                            "No infrastructure services available",
                        )
                    else:
                        available_services = [
                            service
                            for service, available in infrastructure_status.items()
                            if available
                        ]
                        self.result.add_pass("infrastructure_integration")
                        self.result.warnings.append(
                            f"Available services: {available_services}"
                        )

                except ImportError:
                    self.result.add_skip(
                        "infrastructure_integration",
                        "Infrastructure configuration not available",
                    )

        except Exception as e:
            self.result.add_fail("infrastructure_integration", str(e))

    def validate_cross_tier_compatibility(self) -> None:
        """Validate that fixtures work across different test tiers."""
        try:
            # Import consolidated_test_fixtures
            fixtures_path = (
                Path(__file__).parent.parent
                / "fixtures"
                / "consolidated_test_fixtures.py"
            )
            spec = importlib.util.spec_from_file_location(
                "consolidated_test_fixtures", fixtures_path
            )
            fixtures_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixtures_module)

            # Import standardized_configs
            configs_path = Path(__file__).parent / "standardized_configs.py"
            spec = importlib.util.spec_from_file_location(
                "standardized_configs", configs_path
            )
            configs_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(configs_module)
            ConfigurationTier = configs_module.ConfigurationTier
            standard_config = configs_module.standard_config

            # Test that we can generate configs for all tiers
            tiers = [
                ConfigurationTier.UNIT,
                ConfigurationTier.INTEGRATION,
                ConfigurationTier.E2E,
            ]

            for tier in tiers:
                with self.measure_performance(f"cross_tier_{tier.value}"):
                    config = standard_config.get_tier_configuration(tier)

                    # Validate tier-appropriate settings
                    kaizen_config = config["kaizen_config"]

                    if tier == ConfigurationTier.UNIT:
                        # Unit tests should have minimal config
                        if kaizen_config.get("memory_enabled", True):
                            self.result.warnings.append(
                                "Unit tier has memory enabled (should be disabled for performance)"
                            )
                    else:
                        # Integration/E2E should have fuller config
                        if not kaizen_config.get("memory_enabled", False):
                            self.result.add_fail(
                                f"cross_tier_{tier.value}",
                                "Non-unit tier missing memory_enabled",
                            )
                            continue

            self.result.add_pass("cross_tier_compatibility")

        except Exception as e:
            self.result.add_fail("cross_tier_compatibility", str(e))

    def validate_fixture_isolation(self) -> None:
        """Validate that fixtures properly isolate test state."""
        try:
            # Import consolidated_test_fixtures
            fixtures_path = (
                Path(__file__).parent.parent
                / "fixtures"
                / "consolidated_test_fixtures.py"
            )
            spec = importlib.util.spec_from_file_location(
                "consolidated_test_fixtures", fixtures_path
            )
            fixtures_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixtures_module)
            ConsolidatedTestFixtures = fixtures_module.ConsolidatedTestFixtures

            with self.measure_performance("fixture_isolation"):
                # Create multiple fixture instances
                fixtures1 = ConsolidatedTestFixtures()
                fixtures2 = ConsolidatedTestFixtures()

                # They should be independent
                if fixtures1 is fixtures2:
                    self.result.add_fail(
                        "fixture_isolation", "Fixture instances are not independent"
                    )
                    return

                # Test cleanup isolation
                fixtures1.cleanup()

                # fixtures2 should still be functional
                try:
                    scenario = fixtures2.get_scenario("unit_signature_creation")
                    if scenario is None:
                        self.result.warnings.append(
                            "Cleanup may have affected other instances"
                        )
                except Exception:
                    self.result.add_fail(
                        "fixture_isolation", "Cleanup affected other fixture instances"
                    )
                    return

                fixtures2.cleanup()

            self.result.add_pass("fixture_isolation")

        except Exception as e:
            self.result.add_fail("fixture_isolation", str(e))

    def run_all_validations(self) -> ValidationResult:
        """Run all validation tests."""
        print("🔍 Starting fixture validation...")
        print("=" * 50)

        self.validate_imports()
        self.validate_conftest_fixtures()
        self.validate_tier_configurations()
        self.validate_performance_characteristics()
        self.validate_infrastructure_integration()
        self.validate_cross_tier_compatibility()
        self.validate_fixture_isolation()

        print("\n" + "=" * 50)
        print(self.result.get_summary())

        return self.result


def main():
    """Main validation function."""
    validator = FixtureValidator()
    result = validator.run_all_validations()

    # Exit with appropriate code
    if result.failed > 0:
        print(f"\n❌ Validation failed with {result.failed} errors")
        sys.exit(1)
    elif result.skipped > 0:
        print(f"\n⚠️  Validation completed with {result.skipped} skipped tests")
        sys.exit(0)
    else:
        print("\n✅ All validations passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
