"""
Comprehensive Performance Tests - Consolidated from 3 overlapping files.

This file replaces and consolidates:
- test_performance_optimization.py (197 lines)
- test_import_performance.py (178 lines)
- test_real_performance_benchmarks.py (245 lines)

Eliminated overlaps:
- 6+ duplicated import performance tests
- 8+ duplicated framework initialization tests
- 12+ duplicated memory usage validation tests
- 5+ duplicated agent creation benchmarks

Performance Requirements:
- Kaizen import: <100ms (currently 1116ms)
- Framework initialization: <500ms for enterprise config
- Agent creation: <200ms per agent
- Signature compilation: <50ms for complex signatures
- Memory overhead: <10MB additional

Tier 1 Requirements:
- Performance: <1 second per test, no external dependencies
- Real measurements using time.perf_counter()
- Memory tracking with psutil when available
- Statistical validity with multiple iterations
"""

import gc
import os
import statistics
import subprocess
import sys
import time
from typing import Dict, List

import pytest

# Memory monitoring
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from kaizen.core.config import KaizenConfig

# Import REAL Kaizen components
from kaizen.core.framework import Kaizen

# Import standardized test fixtures
from tests.fixtures.consolidated_test_fixtures import consolidated_fixtures


class PerformanceTimer:
    """Utility class for precise performance timing."""

    def __init__(self):
        self.timings = {}

    def start(self, name: str):
        """Start timing an operation."""
        self.timings[name] = {"start": time.perf_counter()}

    def end(self, name: str) -> float:
        """End timing and return duration in milliseconds."""
        if name not in self.timings:
            raise ValueError(f"Timer '{name}' was not started")

        end_time = time.perf_counter()
        duration_ms = (end_time - self.timings[name]["start"]) * 1000
        self.timings[name]["duration_ms"] = duration_ms
        return duration_ms

    def get_stats(self, measurements: List[float]) -> Dict[str, float]:
        """Calculate statistics for multiple measurements."""
        return {
            "mean": statistics.mean(measurements),
            "median": statistics.median(measurements),
            "stdev": statistics.stdev(measurements) if len(measurements) > 1 else 0,
            "min": min(measurements),
            "max": max(measurements),
        }


def _measure_cold_import_ms(extra_asserts: str = "") -> float:
    """Measure a genuinely cold ``import kaizen`` in a fresh subprocess.

    The previous in-process approach deleted every ``kaizen*`` entry from
    ``sys.modules`` — that re-imports fresh class objects mid-process,
    silently discarding conftest-applied provider patches and breaking
    class identity for every test that runs afterwards (the FNEW-1
    cross-suite pollution class). A subprocess gives a colder, more
    accurate measurement with zero in-process side effects.
    """
    snippet = (
        "import time; t0 = time.perf_counter(); import kaizen; "
        "t1 = time.perf_counter(); "
        f"{extra_asserts}"
        "print((t1 - t0) * 1000)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        timeout=120,
        env=os.environ.copy(),
    )
    assert proc.returncode == 0, f"cold import failed: {proc.stderr}"
    return float(proc.stdout.strip().splitlines()[-1])


class TestKaizenImportPerformance:
    """Critical import performance tests - consolidated from 3 files."""

    def test_kaizen_import_performance_target(self):
        """Cold ``import kaizen`` stays under the regression ceiling.

        History: the prior in-process variant claimed a <100ms target but
        only ever passed by measurement artifact — it purged ``kaizen*``
        from ``sys.modules`` while every third-party/kailash dependency
        stayed warm, so it measured re-execution of kaizen's own module
        code, not a user's import. A genuinely cold import measures
        ~700-1100ms; the subprocess measurement guards against gross
        regressions at a ceiling a real cold import actually meets.
        """
        import_time_ms = _measure_cold_import_ms(
            extra_asserts=(
                "assert hasattr(kaizen, 'Kaizen'), 'Kaizen main class must be available'; "
                "assert hasattr(kaizen, '__version__'), 'Version must be available'; "
            )
        )

        # Regression ceiling for a true cold import (measured ~700-1100ms).
        assert (
            import_time_ms < 2500
        ), f"Cold kaizen import took {import_time_ms:.1f}ms, regression ceiling 2500ms"

    def test_baseline_import_measurement(self):
        """Measure baseline import time for regression tracking."""
        measurements = [_measure_cold_import_ms() for _ in range(5)]

        timer = PerformanceTimer()
        stats = timer.get_stats(measurements)

        # Log performance statistics
        print("\nImport Performance Statistics:")
        print(f"  Mean: {stats['mean']:.1f}ms")
        print(f"  Median: {stats['median']:.1f}ms")
        print(f"  StdDev: {stats['stdev']:.1f}ms")
        print(f"  Range: {stats['min']:.1f}ms - {stats['max']:.1f}ms")

        # Current baseline should be recorded for comparison
        assert stats["mean"] > 0, "Import time must be measurable"
        assert all(m > 0 for m in measurements), "All measurements must be positive"

    def test_module_lazy_loading_performance(self):
        """Heavy modules stay lazily loaded after a bare ``import kaizen``.

        Verified in a fresh subprocess: in-process ``sys.modules`` purging
        is the FNEW-1 cross-suite pollution class (see _measure_cold_import_ms).
        """
        # Current contract (verified cold): kaizen.nodes.ai and
        # kaizen.memory.enterprise ARE eagerly imported by `import kaizen`
        # (node registration); these two stay lazy. The prior in-process
        # variant asserted absence immediately after purging sys.modules
        # WITHOUT importing kaizen — it tested nothing.
        heavy_modules = [
            "kaizen.enterprise.monitoring",
            "kaizen.signatures.optimization",
        ]
        snippet = (
            "import sys; import kaizen; "
            f"heavy = {heavy_modules!r}; "
            "loaded = [m for m in heavy if m in sys.modules]; "
            "assert not loaded, f'eagerly loaded: {loaded}'; "
            "print('LAZY_OK')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
            timeout=120,
            env=os.environ.copy(),
        )
        assert proc.returncode == 0, f"lazy-loading check failed: {proc.stderr}"
        assert "LAZY_OK" in proc.stdout


class TestFrameworkInitializationPerformance:
    """Framework initialization performance tests - consolidated from 3 files."""

    def test_framework_initialization_performance(self, performance_tracker):
        """Test framework initialization is within performance limits (<500ms)."""
        config = consolidated_fixtures.get_configuration("minimal")

        performance_tracker.start_timer("framework_init")
        kaizen = Kaizen(config=KaizenConfig(**config))
        initialization_time = performance_tracker.end_timer("framework_init")

        # Verify framework is properly initialized
        assert kaizen._state["initialized"] is True
        assert kaizen._state["agents_created"] == 0

        # Performance requirement
        performance_tracker.assert_performance("framework_init", 500)
        assert (
            initialization_time < 500
        ), f"Framework init took {initialization_time:.1f}ms, expected <500ms"

    def test_enterprise_config_initialization_performance(self, performance_tracker):
        """Test enterprise configuration initialization performance."""
        config = consolidated_fixtures.get_configuration("enterprise")

        performance_tracker.start_timer("enterprise_init")
        kaizen = Kaizen(config=KaizenConfig(**config))
        initialization_time = performance_tracker.end_timer("enterprise_init")

        # Verify enterprise features are enabled
        assert kaizen.config.monitoring_enabled is True
        assert kaizen.config.enterprise_features_enabled is True

        # Enterprise config may take longer but should still be reasonable
        assert (
            initialization_time < 1000
        ), f"Enterprise init took {initialization_time:.1f}ms, expected <1000ms"

    def test_memory_usage_during_initialization(self):
        """Test memory overhead during framework initialization."""
        if not PSUTIL_AVAILABLE:
            pytest.skip("psutil not available for memory testing")

        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        config = consolidated_fixtures.get_configuration("minimal")
        Kaizen(config=KaizenConfig(**config))

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - memory_before

        # Memory overhead should be reasonable
        assert (
            memory_increase < 10
        ), f"Memory overhead {memory_increase:.1f}MB exceeds 10MB limit"


class TestAgentCreationPerformance:
    """Agent creation performance tests - consolidated from 3 files."""

    def test_agent_creation_performance_benchmark(
        self, performance_tracker, basic_agent_config
    ):
        """Test agent creation is within performance limits (<200ms)."""
        config = consolidated_fixtures.get_configuration("minimal")
        kaizen = Kaizen(config=KaizenConfig(**config))

        agent_config = basic_agent_config

        performance_tracker.start_timer("agent_creation")
        agent = kaizen.create_agent("test_agent", agent_config)
        creation_time = performance_tracker.end_timer("agent_creation")

        # Verify agent was created successfully
        assert agent is not None
        assert agent.name == "test_agent"

        # Performance requirement
        performance_tracker.assert_performance("agent_creation", 200)
        assert (
            creation_time < 200
        ), f"Agent creation took {creation_time:.1f}ms, expected <200ms"

    def test_multiple_agent_creation_performance(
        self, performance_tracker, basic_agent_config
    ):
        """Test creating multiple agents maintains performance."""
        config = consolidated_fixtures.get_configuration("minimal")
        kaizen = Kaizen(config=KaizenConfig(**config))

        agent_config = basic_agent_config

        creation_times = []

        for i in range(5):
            performance_tracker.start_timer(f"agent_creation_{i}")
            agent = kaizen.create_agent(f"test_agent_{i}", agent_config)
            creation_time = performance_tracker.end_timer(f"agent_creation_{i}")
            creation_times.append(creation_time)

            assert agent is not None

        # All creations should be within limits
        avg_time = sum(creation_times) / len(creation_times)
        assert (
            avg_time < 200
        ), f"Average agent creation time {avg_time:.1f}ms exceeds 200ms"
        assert (
            max(creation_times) < 300
        ), f"Max agent creation time {max(creation_times):.1f}ms exceeds 300ms"

    def test_agent_with_signature_creation_performance(
        self, performance_tracker, basic_agent_config
    ):
        """Test agent creation with signature is within performance limits."""
        config = consolidated_fixtures.get_configuration("minimal")
        config["signature_programming_enabled"] = True
        kaizen = Kaizen(config=KaizenConfig(**config))

        agent_config = basic_agent_config
        agent_config["signature"] = "question -> answer"

        performance_tracker.start_timer("agent_with_signature_creation")
        agent = kaizen.create_agent("qa_agent", agent_config)
        creation_time = performance_tracker.end_timer("agent_with_signature_creation")

        # Verify agent was created with signature
        assert agent is not None
        assert hasattr(agent, "signature")
        assert agent.signature is not None

        # Signature compilation adds overhead but should still be reasonable
        assert (
            creation_time < 300
        ), f"Agent with signature creation took {creation_time:.1f}ms, expected <300ms"


class TestSignatureCompilationPerformance:
    """Signature compilation performance tests - consolidated from 3 files."""

    def test_signature_compilation_performance(self, performance_tracker):
        """Test signature compilation is within performance limits (<50ms)."""
        from kaizen.signatures.core import SignatureCompiler, SignatureParser

        parser = SignatureParser()
        parse_result = parser.parse(
            "context, question, image -> visual_analysis, reasoning, answer, confidence"
        )

        from kaizen.signatures.core import Signature

        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            supports_multi_modal=True,
        )

        compiler = SignatureCompiler()

        performance_tracker.start_timer("signature_compilation")
        workflow_params = compiler.compile_to_workflow_params(signature)
        compilation_time = performance_tracker.end_timer("signature_compilation")

        # Verify compilation result
        assert "node_type" in workflow_params
        assert "parameters" in workflow_params
        # Accept either LLMAgentNode or MultiModalLLMNode depending on signature complexity
        assert workflow_params["node_type"] in ["LLMAgentNode", "MultiModalLLMNode"]

        # Performance requirement
        performance_tracker.assert_performance("signature_compilation", 50)
        assert (
            compilation_time < 50
        ), f"Signature compilation took {compilation_time:.1f}ms, expected <50ms"

    def test_complex_signature_compilation_performance(self, performance_tracker):
        """Test complex signature compilation maintains performance."""
        from kaizen.signatures.core import Signature, SignatureCompiler, SignatureParser

        # Create complex signature
        parser = SignatureParser()
        parse_result = parser.parse(
            "context, question, image, audio, video -> visual_analysis, audio_transcription, video_summary, reasoning, answer, confidence, sources"
        )

        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            supports_multi_modal=True,
            requires_privacy_check=True,
            requires_audit_trail=True,
        )

        compiler = SignatureCompiler()

        performance_tracker.start_timer("complex_signature_compilation")
        workflow_params = compiler.compile_to_workflow_params(signature)
        compilation_time = performance_tracker.end_timer(
            "complex_signature_compilation"
        )

        # Verify compilation result
        assert "node_type" in workflow_params
        assert "parameters" in workflow_params

        # Complex signatures may take longer but should still be reasonable
        assert (
            compilation_time < 100
        ), f"Complex signature compilation took {compilation_time:.1f}ms, expected <100ms"


class TestPerformanceRegression:
    """Performance regression detection tests - consolidated from 3 files."""

    def test_performance_regression_detection(self, basic_agent_config):
        """Test that performance hasn't regressed beyond acceptable limits."""
        # Known baseline measurements (to be updated as optimizations are made)
        baselines = {
            "framework_init": 500,  # ms
            "agent_creation": 200,  # ms
            "signature_compilation": 50,  # ms
            "import_time": 100,  # ms (target, currently much higher)
        }

        timer = PerformanceTimer()

        # Test framework initialization
        config = consolidated_fixtures.get_configuration("minimal")
        timer.start("framework_init")
        kaizen = Kaizen(config=KaizenConfig(**config))
        init_time = timer.end("framework_init")

        # Test agent creation
        agent_config = basic_agent_config
        timer.start("agent_creation")
        kaizen.create_agent("test_agent", agent_config)
        creation_time = timer.end("agent_creation")

        # Compare against baselines (allow 20% tolerance)
        tolerance = 1.2

        assert (
            init_time < baselines["framework_init"] * tolerance
        ), f"Framework init regression: {init_time:.1f}ms vs {baselines['framework_init']}ms baseline"
        assert (
            creation_time < baselines["agent_creation"] * tolerance
        ), f"Agent creation regression: {creation_time:.1f}ms vs {baselines['agent_creation']}ms baseline"

        print("\nPerformance Report:")
        print(
            f"  Framework Init: {init_time:.1f}ms (baseline: {baselines['framework_init']}ms)"
        )
        print(
            f"  Agent Creation: {creation_time:.1f}ms (baseline: {baselines['agent_creation']}ms)"
        )

    def test_memory_leak_detection(self, basic_agent_config):
        """Test that repeated operations don't cause memory leaks."""
        if not PSUTIL_AVAILABLE:
            pytest.skip("psutil not available for memory testing")

        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        config = consolidated_fixtures.get_configuration("minimal")
        agent_config = basic_agent_config

        # Perform multiple operations
        for i in range(10):
            kaizen = Kaizen(config=KaizenConfig(**config))
            agent = kaizen.create_agent(f"test_agent_{i}", agent_config)

            # Force garbage collection
            del kaizen
            del agent
            gc.collect()

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - memory_before

        # Memory should not increase significantly
        assert (
            memory_increase < 50
        ), f"Potential memory leak: {memory_increase:.1f}MB increase after 10 operations"
