# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""F10 Defect 2, SIBLING SITE: `HookManager._run_single` killed without reaping.

Found by the same-class sweep that followed the `ClaudeCodeAdapter.stream()`
fix (`test_f10_claude_code_stream_reaps_child.py`). Identical defect, in a
timeout handler this time::

    except TimeoutError:
        proc.kill()          # signal delivered, exit status never collected
        return HookResult(...)

`proc` is a local, so once `_run_single` returns there is no handle left and the
child can never be reaped — one zombie per hook timeout, in a runner that fires
on six lifecycle events per tool call.

Of the four `kill()` sites swept, this was the only remaining unpaired one:
`delegate/mcp.py` and `_run_claude_code`'s own timeout handler already pair
`kill()` with `await wait()`, and `ClaudeCodeAdapter.interrupt()` deliberately
does not, because the owning coroutine is still awaiting the child and reaps
it there.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from kaizen_agents.delegate.hooks import HookEvent, HookManager

pytestmark = [
    pytest.mark.regression,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX process reaping semantics",
    ),
]


@pytest.mark.asyncio
async def test_a_timed_out_hook_child_is_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED against the unfixed handler: `kill()` with no `await wait()`.

    The child is captured through a wrapper around the REAL
    `create_subprocess_exec` — the subprocess is genuine, only the handle is
    observed, because `_run_single` keeps `proc` local and the whole defect is
    that the handle is dropped.
    """
    script = tmp_path / "pre-tool-use.py"
    # Sleeps far past the runner's timeout, so the timeout branch is the one
    # under test and a collected exit status cannot be the child exiting early.
    script.write_text("import time\ntime.sleep(30)\n")

    captured: list[asyncio.subprocess.Process] = []
    real_exec = asyncio.create_subprocess_exec

    async def _capturing_exec(*args, **kwargs):
        proc = await real_exec(*args, **kwargs)
        captured.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _capturing_exec)

    runner = HookManager(tmp_path, timeout=0.3)
    result = await runner._run_single(HookEvent.PRE_TOOL_USE, script, b"{}")

    assert "Timed out" in result.stderr, (
        "the hook did not actually time out, so the timeout handler under "
        "test never ran and this probe measures nothing"
    )
    assert captured, "no subprocess was spawned; the probe measures nothing"

    child = captured[0]
    assert child.returncode is not None, (
        "the hook manager killed a timed-out child but never reaped it — "
        "`kill()` only delivers SIGKILL, and `proc` is a local that is gone "
        "the moment this returns, so nothing can ever collect the exit "
        "status. Pair the kill with `await proc.wait()`."
    )
