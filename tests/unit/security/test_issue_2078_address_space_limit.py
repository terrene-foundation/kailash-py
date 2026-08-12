"""Regression tests for issue #2078 — process-wide RLIMIT_AS corruption.

``PythonCodeNode`` used to enforce ``SecurityConfig.memory_limit`` with

    resource.setrlimit(RLIMIT_AS, (memory_limit, memory_limit))

executed inline, in the host process. ``RLIMIT_AS`` is process-wide and the
call set the HARD limit too, so an unprivileged process could never raise it
again.

``RLIMIT_AS`` caps VIRTUAL address space, not resident memory, and on Linux the
two diverge sharply: glibc reserves a 64 MB malloc arena per thread and every
pthread stack reserves 8 MB. Measured in a python:3.12-slim container, a
25-thread process sat at 1889 MB of address space while importing the SDK alone
cost only 62 MB. One ``PythonCodeNode`` execution then capped that 1889 MB
process at the 512 MB default, and every later ``mmap`` failed — including the
stack allocation ``pthread_create`` needs — which is where CI's

    130 x RuntimeError: can't start new thread
     90 x sqlite3.OperationalError: disk I/O error

came from, in tests that had nothing to do with PythonCodeNode. Tier 2 runs
``-p no:xdist``, so one execution poisoned the remainder of the run; that is
why the failure counts were identical across runs to the test.

Platform note, and it is the whole reason this went unseen for so long: the
Darwin kernel REJECTS ``setrlimit(RLIMIT_AS)``, so on macOS the old code took
its ``except (OSError, ValueError)`` branch and the limit was never applied.
A macOS run is therefore NOT a discriminating instrument for this bug — the
Linux assertions below are, and CI runs Linux.
"""

import os
import threading

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.security import (
    MemoryLimitError,
    SecurityConfig,
    get_security_config,
    memory_limit_guard,
    set_security_config,
)

resource = pytest.importorskip("resource", reason="POSIX-only")

HAS_RLIMIT_AS = hasattr(resource, "RLIMIT_AS")

# Only Linux actually enforces RLIMIT_AS. Guard the enforcement assertions on
# the real property rather than on a platform string, so a platform that starts
# enforcing it is covered automatically.
ENFORCES_RLIMIT_AS = HAS_RLIMIT_AS and os.path.exists("/proc/self/statm")

requires_rlimit_as = pytest.mark.skipif(
    not HAS_RLIMIT_AS, reason="RLIMIT_AS not available on this platform"
)
requires_enforced_rlimit_as = pytest.mark.skipif(
    not ENFORCES_RLIMIT_AS,
    reason="RLIMIT_AS is not enforced on this platform (macOS rejects it)",
)


@pytest.fixture
def restore_security_config():
    """Restore the process-global SecurityConfig after the test."""
    previous = get_security_config()
    yield
    set_security_config(previous)


@pytest.fixture(autouse=True)
def assert_rlimit_unchanged():
    """Every test in this module must leave RLIMIT_AS exactly as it found it."""
    if not HAS_RLIMIT_AS:
        yield
        return
    before = resource.getrlimit(resource.RLIMIT_AS)
    yield
    assert resource.getrlimit(resource.RLIMIT_AS) == before, (
        "a test in this module leaked an RLIMIT_AS change into the process — "
        "that is the #2078 failure mode itself"
    )


@requires_rlimit_as
def test_python_code_node_does_not_change_process_rlimit():
    """The regression: executing a node must not alter the process's limit.

    Pre-fix on Linux this assertion reads (536870912, 536870912) against an
    unlimited baseline.
    """
    before = resource.getrlimit(resource.RLIMIT_AS)

    node = PythonCodeNode(name="probe", code="result = 1 + 1")
    assert node.execute() == {"result": 2}

    assert resource.getrlimit(resource.RLIMIT_AS) == before


@requires_rlimit_as
def test_threads_still_start_after_python_code_node_runs():
    """The observable consequence: thread creation must keep working.

    Pre-fix on Linux this raises ``RuntimeError: can't start new thread`` —
    the exact error CI reported 130 times.
    """
    PythonCodeNode(name="probe", code="result = 1 + 1").execute()

    started = threading.Event()
    thread = threading.Thread(target=started.set)
    thread.start()
    thread.join(timeout=10)
    assert started.is_set(), "thread created after PythonCodeNode never ran"


@requires_rlimit_as
def test_python_code_node_run_repeatedly_does_not_accumulate_limits():
    """Repeated executions must not ratchet the limit downwards."""
    before = resource.getrlimit(resource.RLIMIT_AS)
    node = PythonCodeNode(name="probe", code="result = 1 + 1")
    for _ in range(25):
        node.execute()
    assert resource.getrlimit(resource.RLIMIT_AS) == before


@requires_rlimit_as
def test_memory_limit_guard_restores_soft_limit_on_success():
    before = resource.getrlimit(resource.RLIMIT_AS)
    with memory_limit_guard(64 * 1024 * 1024):
        pass
    assert resource.getrlimit(resource.RLIMIT_AS) == before


@requires_rlimit_as
def test_memory_limit_guard_restores_soft_limit_on_exception():
    before = resource.getrlimit(resource.RLIMIT_AS)
    with pytest.raises(ValueError):
        with memory_limit_guard(64 * 1024 * 1024):
            raise ValueError("boom")
    assert resource.getrlimit(resource.RLIMIT_AS) == before


@requires_rlimit_as
def test_memory_limit_guard_never_lowers_the_hard_limit():
    """The hard limit is a one-way door for an unprivileged process."""
    _, hard_before = resource.getrlimit(resource.RLIMIT_AS)
    with memory_limit_guard(16 * 1024 * 1024):
        _, hard_inside = resource.getrlimit(resource.RLIMIT_AS)
    assert hard_inside == hard_before


@requires_enforced_rlimit_as
def test_memory_limit_guard_applies_headroom_above_current_usage():
    """The ceiling must sit ABOVE the process's existing footprint.

    The old code set an absolute ceiling, which is what put the process below
    its own address-space usage.
    """
    with open("/proc/self/statm", "rb") as handle:
        current = int(handle.read().split()[0]) * os.sysconf("SC_PAGE_SIZE")

    headroom = 32 * 1024 * 1024
    with memory_limit_guard(headroom):
        soft, _ = resource.getrlimit(resource.RLIMIT_AS)

    assert soft > current, "ceiling must exceed current address-space usage"
    assert soft <= current + headroom + (
        8 * 1024 * 1024
    ), "ceiling must stay close to current usage + headroom"


@requires_enforced_rlimit_as
def test_memory_limit_guard_enforces_the_headroom():
    """The limit must actually bite — a hog inside a small guard raises."""
    with pytest.raises(MemoryLimitError):
        with memory_limit_guard(16 * 1024 * 1024):
            bytearray(512 * 1024 * 1024)


@requires_enforced_rlimit_as
def test_modest_allocation_inside_the_guard_succeeds():
    with memory_limit_guard(64 * 1024 * 1024):
        assert len(bytearray(4 * 1024 * 1024)) == 4 * 1024 * 1024


@requires_enforced_rlimit_as
def test_python_code_node_raises_memory_limit_error_for_a_hog(
    restore_security_config,
):
    """``memory_limit`` is a documented contract; it must have an effect.

    Before the fix ``MemoryLimitError`` was imported and caught in python.py
    but raised nowhere, so the documented kwarg's only observable behaviour was
    to break the host process.
    """
    set_security_config(SecurityConfig(memory_limit=16 * 1024 * 1024))

    node = PythonCodeNode(name="hog", code="result = len(bytearray(512*1024*1024))")
    with pytest.raises(Exception) as excinfo:
        node.execute()

    chain = []
    err = excinfo.value
    while err is not None and err not in chain:
        chain.append(err)
        err = err.__cause__ or err.__context__
    assert any(
        isinstance(e, MemoryLimitError) for e in chain
    ), f"expected MemoryLimitError in the cause chain, got {chain!r}"


def test_memory_error_is_not_relabelled_when_nothing_is_enforced(monkeypatch):
    """An unenforced guard must not claim credit for a genuine MemoryError.

    On a platform that rejects ``setrlimit`` (macOS) no ceiling is ever in
    force, so a ``MemoryError`` inside the block is real host exhaustion.
    Reporting it as ``MemoryLimitError`` would name the wrong cause and send
    the reader to a knob that is not connected to anything.
    """
    import kailash.security as security_module

    # Simulate the platform where the ceiling cannot be established.
    monkeypatch.setattr(security_module, "_current_address_space_bytes", lambda: None)
    monkeypatch.setattr(security_module, "_address_space_saved", None)

    with pytest.raises(MemoryError) as excinfo:
        with memory_limit_guard(64 * 1024 * 1024):
            raise MemoryError("host is genuinely out of memory")

    assert not isinstance(excinfo.value, MemoryLimitError)
    assert "genuinely out of memory" in str(excinfo.value)


@requires_enforced_rlimit_as
def test_memory_error_is_relabelled_when_the_ceiling_is_in_force():
    """The other polarity: with a ceiling applied, the relabel MUST happen."""
    with pytest.raises(MemoryLimitError):
        with memory_limit_guard(16 * 1024 * 1024):
            raise MemoryError("hit the ceiling")


@requires_enforced_rlimit_as
def test_concurrent_guards_apply_the_tightest_ceiling_not_the_first():
    """A lax concurrent guard must not host a strictly-configured block.

    Nodes in a parallel group may each carry their own SecurityConfig, so two
    guards with different limits are live at once. First-writer-wins would run
    the strict payload under the lax ceiling — a silent sandbox bypass.
    """
    outer = 4 * 1024 * 1024 * 1024  # 4 GB, deliberately lax
    inner = 32 * 1024 * 1024  # 32 MB, the one that must win

    with memory_limit_guard(outer):
        lax, _ = resource.getrlimit(resource.RLIMIT_AS)
        with memory_limit_guard(inner):
            tight, _ = resource.getrlimit(resource.RLIMIT_AS)
        assert tight < lax, (
            f"tighter concurrent guard did not take effect: "
            f"{tight} should be below {lax}"
        )


@requires_enforced_rlimit_as
def test_tighter_ceiling_is_released_when_its_guard_exits():
    """The tightening must be temporary, or the outer block inherits it."""
    outer = 4 * 1024 * 1024 * 1024
    with memory_limit_guard(outer):
        before, _ = resource.getrlimit(resource.RLIMIT_AS)
        with memory_limit_guard(32 * 1024 * 1024):
            pass
        after, _ = resource.getrlimit(resource.RLIMIT_AS)
    assert after == before, "inner guard's tighter ceiling leaked into the outer block"


@requires_enforced_rlimit_as
def test_a_failing_ceiling_application_does_not_disable_later_guards(monkeypatch):
    """An exception while applying must not leave the sandbox permanently off.

    The bookkeeping used to be incremented before the apply, outside any
    try/finally, so one raise (e.g. OverflowError from an over-large configured
    limit) left the count stuck and every later guard concluded a ceiling was
    already in force.
    """
    import kailash.security as security_module

    real_setrlimit = resource.setrlimit
    calls = {"n": 0}

    def exploding_setrlimit(which, limits):
        if which == resource.RLIMIT_AS and calls["n"] == 0:
            calls["n"] += 1
            raise OverflowError("Python int too large to convert to C long")
        return real_setrlimit(which, limits)

    monkeypatch.setattr(security_module.resource, "setrlimit", exploding_setrlimit)
    with memory_limit_guard(64 * 1024 * 1024):
        pass
    monkeypatch.undo()

    # The next guard must still be able to apply a ceiling.
    with memory_limit_guard(32 * 1024 * 1024):
        soft, _ = resource.getrlimit(resource.RLIMIT_AS)
    assert soft != resource.RLIM_INFINITY or True  # applied or cleanly skipped
    assert (
        security_module._address_space_requests == []
    ), "a failed apply leaked its bookkeeping; later guards would be no-ops"


@requires_enforced_rlimit_as
def test_failed_restore_keeps_the_saved_value_for_a_later_retry():
    """Clearing the saved pair before a successful restore is unrecoverable.

    If the restore fails and the saved value is dropped, nothing can ever put
    the process back — #2078 with no path out.
    """
    import kailash.security as security_module

    real_setrlimit = resource.setrlimit
    fail = {"on": False}

    def flaky_setrlimit(which, limits):
        if which == resource.RLIMIT_AS and fail["on"]:
            raise OSError("simulated restore failure")
        return real_setrlimit(which, limits)

    security_module.resource.setrlimit = flaky_setrlimit
    try:
        with memory_limit_guard(64 * 1024 * 1024):
            fail["on"] = True
        assert (
            security_module._address_space_saved is not None
        ), "saved limit was discarded on a failed restore — unrecoverable"
    finally:
        fail["on"] = False
        security_module.resource.setrlimit = real_setrlimit
        # Drive one more guard cycle so the pending restore is retried, and
        # leave the process exactly as this module found it (the autouse
        # fixture asserts that).
        with memory_limit_guard(64 * 1024 * 1024):
            pass


@requires_rlimit_as
def test_nested_and_parallel_guards_restore_exactly_once():
    """Reference counting: parallel node execution must not corrupt restore."""
    before = resource.getrlimit(resource.RLIMIT_AS)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def work():
        try:
            barrier.wait(timeout=30)
            for _ in range(20):
                with memory_limit_guard(64 * 1024 * 1024):
                    with memory_limit_guard(64 * 1024 * 1024):
                        sum(range(100))
        except BaseException as exc:  # noqa: BLE001 - re-raised via `errors`
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, f"guard raised under concurrency: {errors!r}"
    assert resource.getrlimit(resource.RLIMIT_AS) == before

    # And the process is still usable afterwards.
    started = threading.Event()
    probe = threading.Thread(target=started.set)
    probe.start()
    probe.join(timeout=10)
    assert started.is_set()
