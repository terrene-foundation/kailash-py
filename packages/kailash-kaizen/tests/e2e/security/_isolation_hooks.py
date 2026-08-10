"""Module-scope hook handlers for the isolation E2E tests (issue #2014).

Every handler an isolating ``IsolatedHookManager`` runs MUST be picklable,
because the ``spawn`` start method transfers it to a fresh interpreter by
pickle. Pickle stores a function by its ``module.qualname``, so a hook defined
inside a test body cannot be transferred and cannot be isolated.

Before #2014 that did not appear to matter: isolation failed and the manager
silently ran the hook in the agent's own process instead, so tests that defined
their hooks locally passed while exercising nothing. They now fail loudly, which
is the point. Handlers therefore live here, at module scope, where the child can
import them.
"""

import functools
import json
import os
import subprocess
import sys
import tempfile

from kaizen.core.autonomy.hooks.types import HookContext, HookResult


@functools.lru_cache(maxsize=1)
def unenforceable_limits() -> frozenset[str]:
    """Which resource limits this platform refuses to enforce.

    Probed in a SUBPROCESS, never in the test process. ``ResourceLimits.apply()``
    sets the hard limit as well as the soft one, and lowering a hard limit is
    irreversible for the process that does it -- calling it here would cap the
    pytest process itself and make every later test in the session fail while
    trying to set a higher limit.
    """
    probe = (
        "import json, sys;"
        "sys.path.insert(0, %r);"
        "from kaizen.core.autonomy.hooks.security.isolation import ResourceLimits;"
        "print(json.dumps(ResourceLimits("
        "max_memory_mb=64, max_cpu_seconds=3600, max_file_size_mb=1"
        ").apply()))" % (_src_root(),)
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"resource-limit capability probe failed: {completed.stderr[-2000:]}"
        )
    return frozenset(json.loads(completed.stdout.strip().splitlines()[-1]))


def _src_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", "src"))


class SuccessHook:
    """Minimal successful hook, for overhead measurement and ordering checks."""

    name = "success-hook"

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"pid": os.getpid()})


class CrashingHook:
    """Raises in the child, to prove a hook crash cannot take the parent down."""

    name = "crashing-hook"

    async def handle(self, context: HookContext) -> HookResult:
        raise RuntimeError("simulated hook crash")


class MemoryHogHook:
    """Allocates far more memory than the configured cap allows.

    Reports what actually happened rather than asserting, so the caller can hold
    the platform-specific expectation: Linux enforces ``RLIMIT_AS`` and this
    raises ``MemoryError``; macOS refuses to set ``RLIMIT_AS`` at all and the
    allocation succeeds.
    """

    name = "memory-hog-hook"

    def __init__(self, allocate_mb: int = 512):
        self.allocate_mb = allocate_mb

    async def handle(self, context: HookContext) -> HookResult:
        try:
            # bytearray allocates real address space immediately.
            blob = bytearray(self.allocate_mb * 1024 * 1024)
            return HookResult(success=True, data={"allocated": len(blob)})
        except MemoryError:
            return HookResult(success=False, error="MemoryError: allocation refused")


class CpuHogHook:
    """Burns CPU well past the configured CPU-seconds cap."""

    name = "cpu-hog-hook"

    async def handle(self, context: HookContext) -> HookResult:
        total = 0
        for i in range(1_000_000_000):
            total += i
        return HookResult(success=True, data={"total": total})


class FileWriterHook:
    """Writes far more than the configured file-size cap allows."""

    name = "file-writer-hook"

    def __init__(self, write_mb: int = 10):
        self.write_mb = write_mb

    async def handle(self, context: HookContext) -> HookResult:
        try:
            with tempfile.NamedTemporaryFile(mode="wb", delete=True) as handle:
                handle.write(b"0" * (self.write_mb * 1024 * 1024))
                handle.flush()
            return HookResult(success=True, data={"written_mb": self.write_mb})
        except OSError as exc:
            return HookResult(success=False, error=f"file size limit: {exc}")


class MutatingHook:
    """Mutates a process-global, to show the mutation cannot escape the child.

    A hook that runs in the agent's own process can corrupt the agent's state.
    One that is genuinely isolated cannot: the mutation dies with the child.
    """

    name = "mutating-hook"

    async def handle(self, context: HookContext) -> HookResult:
        global LEAKED_STATE
        LEAKED_STATE = "written-by-hook"
        return HookResult(success=True, data={"pid": os.getpid()})


#: Stays at its import-time value in the PARENT for as long as hooks really are
#: isolated. ``MutatingHook`` overwrites it only inside its own process.
LEAKED_STATE = "clean"
