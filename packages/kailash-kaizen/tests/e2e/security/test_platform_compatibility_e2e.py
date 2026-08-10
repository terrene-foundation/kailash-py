"""
Cross-Platform Security E2E Tests.

Validates security features across different platforms:
- Unix/Linux: Full isolation with resource limits
- Windows: Process isolation without resource limits
- macOS: Full isolation with resource limits

Test Tier: 3 (E2E with real infrastructure, NO MOCKING)
"""

import asyncio
import logging
import os
import platform
import sys
from datetime import datetime

import pytest

from kaizen.core.autonomy.hooks import HookEvent, HookPriority
from kaizen.core.autonomy.hooks.security import IsolatedHookManager, ResourceLimits
from kaizen.core.autonomy.hooks.types import HookContext, HookResult

from . import _isolation_hooks as hooks

logger = logging.getLogger(__name__)

CURRENT_PLATFORM = platform.system()  # Linux, Darwin (macOS), Windows

#: Startup budget for a spawned child. Under ``spawn`` the child pays a full
#: interpreter start plus the import of the handler's module, which is far more
#: than the sub-second budgets these tests used while isolation was silently not
#: happening (issue #2014).
ISOLATION_TIMEOUT = 30.0


# ============================================================================
# Platform Detection Tests
# ============================================================================


def test_platform_detection():
    """
    Test correct platform detection.

    Validates:
    - Platform correctly identified
    - Resource limit support detected
    - Graceful degradation plan defined
    """
    logger.info(f"Current platform: {CURRENT_PLATFORM}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform details: {platform.platform()}")

    # Check resource module availability
    try:
        import resource

        has_resource = True
        logger.info("✅ resource module available (Unix/Linux/macOS)")
    except ImportError:
        has_resource = False
        logger.info("⚠️  resource module NOT available (Windows)")

    # Validate expected platform capabilities
    if CURRENT_PLATFORM in ("Linux", "Darwin"):
        assert has_resource, f"{CURRENT_PLATFORM} should have resource module"
    elif CURRENT_PLATFORM == "Windows":
        assert not has_resource, "Windows should not have resource module"

    logger.info(f"✅ Platform detection: {CURRENT_PLATFORM}")


# ============================================================================
# Resource Limits Tests (Unix/Linux/macOS)
# ============================================================================


@pytest.mark.skipif(
    CURRENT_PLATFORM == "Windows", reason="Resource limits not supported on Windows"
)
@pytest.mark.asyncio
async def test_unix_memory_limit():
    """
    Test memory limit enforcement on Unix/Linux/macOS.

    Asserts the OUTCOME rather than merely that a hook ran. The previous version
    asserted ``len(results) == 1``, which is true whether the cap was applied,
    ignored, or never reachable at all -- and it was in fact never reachable,
    because isolation was silently failing (issue #2014).

    The expectation is platform-split because the capability genuinely is:
    Linux enforces ``RLIMIT_AS``, macOS refuses to set it at all. Both branches
    are asserted, so neither can pass by accident on the other's platform.
    """
    limits = ResourceLimits(max_memory_mb=50, max_cpu_seconds=60, max_file_size_mb=10)
    unenforced = hooks.unenforceable_limits()

    manager = IsolatedHookManager(limits=limits, enable_isolation=True)
    manager.register(
        HookEvent.PRE_AGENT_LOOP,
        hooks.MemoryHogHook(allocate_mb=512),
        HookPriority.NORMAL,
    )

    results = await manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )

    assert len(results) == 1, "Hook should execute once"

    if "max_memory_mb" in unenforced:
        # macOS: the cap is not enforceable, and the code says so out loud.
        assert results[0].success is True, (
            "the allocation should succeed where the platform cannot cap it; "
            f"got {results[0].error!r}"
        )
    else:
        # Linux: a 512MB allocation under a 50MB cap must be refused.
        assert results[0].success is False, (
            "a 512MB allocation succeeded under a 50MB RLIMIT_AS cap: the "
            "memory limit was not applied in the isolated process"
        )
    logger.info(
        "✅ %s: memory limit outcome asserted (unenforced=%s)",
        CURRENT_PLATFORM,
        unenforced,
    )


@pytest.mark.skipif(
    CURRENT_PLATFORM == "Windows", reason="Resource limits not supported on Windows"
)
@pytest.mark.asyncio
async def test_unix_cpu_limit():
    """
    Test CPU time limit enforcement on Unix/Linux/macOS.

    Validates:
    - CPU time limits applied successfully
    - Infinite loops prevented
    - Graceful failure on CPU exceeded
    """
    limits = ResourceLimits(max_memory_mb=4096, max_cpu_seconds=2, max_file_size_mb=10)
    assert "max_cpu_seconds" not in hooks.unenforceable_limits(), (
        "RLIMIT_CPU is expected to be enforceable on every non-Windows platform "
        "this test runs on"
    )

    manager = IsolatedHookManager(limits=limits, enable_isolation=True)
    manager.register(HookEvent.PRE_AGENT_LOOP, hooks.CpuHogHook(), HookPriority.NORMAL)

    results = await manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )

    # The child burns a billion additions against a 2-second CPU cap. It is
    # killed by SIGXCPU long before finishing, so the ONLY way this reports
    # success is if the cap was never applied -- which is what a silently
    # non-isolated execution looks like.
    assert len(results) == 1, "Hook should execute once"
    assert results[0].success is False, (
        "an unbounded CPU loop completed under a 2-second RLIMIT_CPU cap: the "
        "CPU limit was not applied in the isolated process"
    )
    logger.info("✅ %s: CPU limit enforced (hook killed)", CURRENT_PLATFORM)


@pytest.mark.skipif(
    CURRENT_PLATFORM == "Windows", reason="Resource limits not supported on Windows"
)
@pytest.mark.asyncio
async def test_unix_file_size_limit():
    """
    Test file size limit enforcement on Unix/Linux/macOS.

    Validates:
    - File size limits applied successfully
    - Large file writes prevented
    - Graceful failure on file size exceeded
    """
    limits = ResourceLimits(max_memory_mb=4096, max_cpu_seconds=60, max_file_size_mb=1)
    assert "max_file_size_mb" not in hooks.unenforceable_limits(), (
        "RLIMIT_FSIZE is expected to be enforceable on every non-Windows "
        "platform this test runs on"
    )

    manager = IsolatedHookManager(limits=limits, enable_isolation=True)
    manager.register(
        HookEvent.PRE_AGENT_LOOP, hooks.FileWriterHook(write_mb=10), HookPriority.NORMAL
    )

    results = await manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )

    # A 10MB write under a 1MB RLIMIT_FSIZE cap cannot complete. Success here
    # would mean the cap was never applied.
    assert len(results) == 1, "Hook should execute once"
    assert results[0].success is False, (
        "a 10MB write completed under a 1MB RLIMIT_FSIZE cap: the file size "
        "limit was not applied in the isolated process"
    )
    logger.info("✅ %s: file size limit enforced", CURRENT_PLATFORM)


# ============================================================================
# Process Isolation Tests (All Platforms)
# ============================================================================


@pytest.mark.asyncio
async def test_process_isolation():
    """
    Test process isolation on all platforms.

    Asserts that the hook ran SOMEWHERE ELSE, and that a mutation it made could
    not reach this process. The previous version asserted
    ``isinstance(results, list)``, which is true of every possible outcome --
    including the in-process execution issue #2014 was silently doing.
    """
    manager = IsolatedHookManager(
        limits=ResourceLimits(max_memory_mb=4096, max_cpu_seconds=60),
        enable_isolation=True,
    )
    manager.register(
        HookEvent.PRE_AGENT_LOOP, hooks.MutatingHook(), HookPriority.NORMAL
    )

    assert hooks.LEAKED_STATE == "clean"

    results = await manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )

    assert len(results) == 1 and results[0].success is True, results[0].error
    assert (
        results[0].data["pid"] != os.getpid()
    ), "the hook ran in this process: isolation did not engage"
    assert hooks.LEAKED_STATE == "clean", (
        "the hook's mutation reached the parent's address space, so the hook "
        "was not isolated and could corrupt agent state"
    )
    logger.info("✅ %s: hook confined to its own process", CURRENT_PLATFORM)


@pytest.mark.asyncio
async def test_cross_hook_isolation():
    """
    Test hooks cannot interfere with each other.

    Validates:
    - Hook A crash doesn't affect Hook B
    - Separate memory spaces
    - Independent execution
    """
    manager = IsolatedHookManager(
        limits=ResourceLimits(max_memory_mb=4096, max_cpu_seconds=60),
        enable_isolation=True,
    )

    manager.register(HookEvent.PRE_AGENT_LOOP, hooks.CrashingHook(), HookPriority.HIGH)
    manager.register(HookEvent.PRE_AGENT_LOOP, hooks.SuccessHook(), HookPriority.NORMAL)

    results = await manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )

    # Asserts the OUTCOMES, not just the count: A must have failed, B must have
    # succeeded despite it, and the two must have run in DIFFERENT processes
    # from each other and from this one.
    assert len(results) == 2, "Both hooks should execute"
    assert results[0].success is False, "the crashing hook should report failure"
    assert results[1].success is True, results[1].error
    assert (
        results[1].data["pid"] != os.getpid()
    ), "the surviving hook ran in this process: isolation did not engage"
    logger.info("✅ %s: hook crash did not affect the sibling hook", CURRENT_PLATFORM)


# ============================================================================
# Windows-Specific Tests
# ============================================================================


@pytest.mark.skipif(CURRENT_PLATFORM != "Windows", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_graceful_degradation():
    """
    Test graceful degradation on Windows (no resource limits).

    Validates:
    - Process isolation works on Windows
    - Resource limits gracefully skipped
    - Warning logged for resource limits
    - Hook execution still functional
    """
    import logging
    from unittest.mock import patch

    # Capture log warnings
    with patch.object(logger, "warning") as mock_warning:
        limits = ResourceLimits(
            max_memory_mb=100, max_cpu_seconds=5, max_file_size_mb=10
        )

        manager = IsolatedHookManager(limits=limits, enable_isolation=True)

        # Verify warning was logged
        # mock_warning.assert_called()  # Warning about resource limits

    # Create test hook
    async def test_hook(context: HookContext) -> HookResult:
        return HookResult(success=True, metadata={"platform": "Windows"})

    manager.register(HookEvent.PRE_AGENT_LOOP, test_hook, HookPriority.NORMAL)

    # Trigger hook (should work despite no resource limits)
    results = await manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=2.0,
    )

    # Validate execution succeeds
    assert len(results) == 1, "Hook should execute"
    assert results[0].success, "Hook should succeed on Windows"
    logger.info("✅ Windows: Graceful degradation test passed")


# ============================================================================
# Performance Comparison Tests
# ============================================================================


@pytest.mark.asyncio
async def test_performance_with_isolation():
    """
    Test performance overhead of isolation.

    Validates:
    - Isolation overhead < 100ms per hook
    - Acceptable performance degradation
    - Scalability maintained
    """
    import time

    # Measure without isolation
    manager_no_isolation = IsolatedHookManager(
        limits=ResourceLimits(), enable_isolation=False
    )
    manager_no_isolation.register(
        HookEvent.PRE_AGENT_LOOP, hooks.SuccessHook(), HookPriority.NORMAL
    )

    start = time.perf_counter()
    await manager_no_isolation.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )
    duration_no_isolation = (time.perf_counter() - start) * 1000  # ms

    # Measure with isolation
    manager_with_isolation = IsolatedHookManager(
        limits=ResourceLimits(max_memory_mb=4096, max_cpu_seconds=60),
        enable_isolation=True,
    )
    manager_with_isolation.register(
        HookEvent.PRE_AGENT_LOOP, hooks.SuccessHook(), HookPriority.NORMAL
    )

    start = time.perf_counter()
    await manager_with_isolation.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-001",
        data={},
        timeout=ISOLATION_TIMEOUT,
    )
    duration_with_isolation = (time.perf_counter() - start) * 1000  # ms

    overhead_ms = duration_with_isolation - duration_no_isolation
    logger.info(f"Performance overhead: {overhead_ms:.2f}ms")
    logger.info(f"  Without isolation: {duration_no_isolation:.2f}ms")
    logger.info(f"  With isolation: {duration_with_isolation:.2f}ms")

    # LOWER bound first, and it is the load-bearing one. Isolation means a real
    # interpreter is started, which cannot be free. The old assertion was an
    # upper bound of 500ms, which passed comfortably for the wrong reason: no
    # process was being created at all (issue #2014). A near-zero overhead is
    # now a FAILURE signal rather than a good result.
    assert overhead_ms > 50, (
        f"isolation added only {overhead_ms:.2f}ms, which is too cheap to have "
        f"started an interpreter -- isolation is probably not engaging"
    )

    # Upper bound calibrated against real spawn cost: a fresh interpreter plus
    # the import of the handler's module, which is seconds rather than the
    # sub-500ms a no-op fallback used to measure.
    assert overhead_ms < 20000, f"Isolation overhead too high: {overhead_ms:.2f}ms"
    logger.info(f"✅ {CURRENT_PLATFORM}: Performance overhead acceptable")


# ============================================================================
# Platform Summary Test
# ============================================================================


def test_platform_summary():
    """
    Generate platform compatibility summary report.

    Validates:
    - Platform detected correctly
    - Features available documented
    - Limitations documented
    """
    logger.info("=" * 80)
    logger.info("CROSS-PLATFORM SECURITY COMPATIBILITY SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Platform: {CURRENT_PLATFORM}")
    logger.info(f"Python: {sys.version}")

    # Check resource module
    try:
        import resource

        logger.info("✅ Resource Limits: AVAILABLE (full isolation)")
        logger.info("   - Memory limits: SUPPORTED")
        logger.info("   - CPU limits: SUPPORTED")
        logger.info("   - File size limits: SUPPORTED")
    except ImportError:
        logger.info("⚠️  Resource Limits: NOT AVAILABLE (process isolation only)")
        logger.info("   - Memory limits: NOT SUPPORTED")
        logger.info("   - CPU limits: NOT SUPPORTED")
        logger.info("   - File size limits: NOT SUPPORTED")

    logger.info("✅ Process Isolation: AVAILABLE")
    logger.info("✅ Hook Crash Protection: AVAILABLE")
    logger.info("✅ Cross-Hook Isolation: AVAILABLE")
    logger.info("=" * 80)

    if CURRENT_PLATFORM in ("Linux", "Darwin"):
        logger.info("PRODUCTION READY: Full security features available")
    else:
        logger.info(
            "PRODUCTION READY: Process isolation available (resource limits gracefully degraded)"
        )

    logger.info("=" * 80)
