# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""F10 Defect 2: `ClaudeCodeAdapter.stream()` killed its child without reaping.

`_run_claude_code`'s timeout handler gets this right::

    except TimeoutError:
        process.kill()
        await process.wait()      # <-- reaps
        raise

`stream()`'s cancellation handler, in the SAME file, did not::

    except asyncio.CancelledError:
        if self._current_process:
            self._current_process.kill()     # signal sent, never awaited
        raise
    finally:
        self._current_process = None         # handle dropped

`kill()` only DELIVERS SIGKILL. Until someone waits on the pid the kernel
keeps the exit status, so the child sits as a zombie — and the `finally`
drops the only handle that could ever reap it. A long-lived process running
an agent loop accumulates one per cancelled stream.

THE SECOND PATH IS THE WORSE ONE, and it is the same defect one exception
type over. A consumer that `break`s out of `async for ... in adapter.stream()`
does not raise `CancelledError` at the yield point — it raises `GeneratorExit`,
which that handler does not catch. So the `finally` dropped the handle having
neither killed NOR reaped, leaving the CLI subprocess RUNNING with nothing
holding a reference to it. A zombie costs a pid table entry; this costs a live
process.

NO MOCKING OF THE CODE UNDER TEST. These drive the real `stream()` against a
real `/bin/sh` child; only `_build_command` is overridden, to point at a
sleeper instead of the Claude CLI (which is not the subject and is not
installed in CI).
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from kaizen.runtime.context import ExecutionContext
from kaizen_agents.runtime_adapters.claude_code import ClaudeCodeAdapter

pytestmark = [
    pytest.mark.regression,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX process reaping semantics; /bin/sh sleeper is not portable",
    ),
]

#: A TICKER, not a bare `sleep`, and the difference is what makes these probes
#: discriminating. `stream()` yields per line of child stdout, so a silent
#: child yields nothing: the `async for` blocks at EOF until the child exits,
#: the consumer's `break` never runs, and the generator completes down its
#: NORMAL path — measuring neither handler. (Observed: the first draft used
#: `sleep 30` and the GeneratorExit probe failed its own liveness guard.)
#:
#: Emitting forever also means the child is unambiguously alive when each test
#: acts on it, so a reaped `returncode` cannot be the child having exited by
#: itself.
_SLEEPER = ["/bin/sh", "-c", "while :; do echo tick; sleep 0.05; done"]


class _SleeperAdapter(ClaudeCodeAdapter):
    """Real adapter, real subprocess — only the command is swapped."""

    def _build_command(self, context: ExecutionContext) -> list[str]:
        return list(_SLEEPER)


def _adapter() -> _SleeperAdapter:
    adapter = _SleeperAdapter()
    # Skip `warmup()`'s CLI probe. The initialization handshake is not the
    # subject and requires the Claude CLI on PATH.
    adapter._is_initialized = True
    return adapter


async def _spawn_and_capture(adapter: _SleeperAdapter):
    """Start the stream and return (task, child) once the child is live.

    The adapter nulls `_current_process` in its `finally`, so the handle has
    to be captured while the stream is still running.
    """
    context = ExecutionContext(task="irrelevant — the sleeper ignores argv")

    async def _drain() -> None:
        async for _chunk in adapter.stream(context):
            pass

    task = asyncio.create_task(_drain())

    for _ in range(200):
        await asyncio.sleep(0.01)
        if adapter._current_process is not None:
            break
    else:  # pragma: no cover - the sleeper failed to start at all
        task.cancel()
        pytest.fail("child process never started; the probe measures nothing")

    child = adapter._current_process
    assert child.returncode is None, (
        "the child had already exited before the test acted on it, so neither "
        "assertion below would discriminate"
    )
    return task, child


@pytest.mark.asyncio
async def test_cancelling_the_stream_reaps_the_child() -> None:
    """RED against the unfixed handler: `kill()` with no `await wait()`.

    The falsifying result is named and mechanical: `returncode is None` means
    the exit status was never collected — the pid is still occupied and the
    handle that could have reaped it has just been dropped.
    """
    adapter = _adapter()
    task, child = await _spawn_and_capture(adapter)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert child.returncode is not None, (
        "stream() cancelled the child but never reaped it — `kill()` only "
        "delivers SIGKILL, and the `finally` has now dropped the only handle "
        "that could collect the exit status. Match the timeout handler in "
        "`_run_claude_code`: kill(), then `await process.wait()`."
    )


@pytest.mark.asyncio
async def test_breaking_out_of_the_stream_does_not_leave_the_child_running() -> None:
    """The GeneratorExit path — same defect, worse outcome.

    An early `break` is the ordinary way to stop consuming a stream. It closes
    the async generator with `GeneratorExit`, which the `except
    asyncio.CancelledError` handler does not catch, so the child was neither
    killed nor reaped and the handle was dropped while it was still RUNNING.
    """
    adapter = _adapter()
    context = ExecutionContext(task="irrelevant — the sleeper ignores argv")

    agen = adapter.stream(context)
    got_a_chunk = False
    async for _chunk in agen:
        got_a_chunk = True
        break

    assert got_a_chunk, (
        "the stream yielded nothing, so the `break` never ran and the "
        "generator was not closed at a yield point — this probe would be "
        "measuring the normal completion path, not GeneratorExit"
    )

    child = adapter._current_process
    assert child is not None and child.returncode is None, (
        "the child was not live at the point of the break, so this probe "
        "cannot discriminate"
    )

    # Closing the generator is what a `break` + scope exit does; do it
    # explicitly so the test does not depend on GC timing.
    await agen.aclose()

    assert child.returncode is not None, (
        "breaking out of stream() left the CLI subprocess RUNNING with no "
        "reference held — the GeneratorExit path must kill and reap the child "
        "exactly as the cancellation path does"
    )
