"""Tests for the hook system.

Covers:
- HookManager: discovery, execution, exit code handling
- HookEvent enum and HookResult properties
- Timeout handling and error cases
"""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap

import pytest

from kaizen_agents.delegate.hooks import HookEvent, HookManager, HookResult


# -----------------------------------------------------------------------
# HookEvent basics
# -----------------------------------------------------------------------


class TestHookEvent:
    def test_all_events_defined(self):
        expected = {
            "pre-tool-use",
            "post-tool-use",
            "pre-model",
            "post-model",
            "session-start",
            "session-end",
        }
        actual = {e.value for e in HookEvent}
        assert actual == expected


# -----------------------------------------------------------------------
# HookResult
# -----------------------------------------------------------------------


class TestHookResult:
    def test_allowed_on_exit_0(self, tmp_path):
        r = HookResult(event=HookEvent.PRE_MODEL, script=tmp_path / "x.js", exit_code=0)
        assert r.allowed is True
        assert r.blocked is False
        assert r.error is False

    def test_blocked_on_exit_2(self, tmp_path):
        r = HookResult(event=HookEvent.PRE_MODEL, script=tmp_path / "x.js", exit_code=2)
        assert r.allowed is False
        assert r.blocked is True
        assert r.error is False

    def test_error_on_exit_1(self, tmp_path):
        r = HookResult(event=HookEvent.PRE_MODEL, script=tmp_path / "x.js", exit_code=1)
        assert r.allowed is False
        assert r.blocked is False
        assert r.error is True

    def test_error_on_other_exit_codes(self, tmp_path):
        r = HookResult(event=HookEvent.PRE_MODEL, script=tmp_path / "x.js", exit_code=127)
        assert r.allowed is False
        assert r.blocked is False
        assert r.error is True


# -----------------------------------------------------------------------
# Helper to create hook scripts
# -----------------------------------------------------------------------


def _write_py_hook(hooks_dir, filename, code):
    """Write a Python hook script and make it executable."""
    script = hooks_dir / filename
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _write_js_hook(hooks_dir, filename, code):
    """Write a JavaScript hook script."""
    script = hooks_dir / filename
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


# -----------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------


class TestHookDiscovery:
    def test_empty_directory(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        mgr = HookManager(hooks_dir)
        assert mgr.get_hooks(HookEvent.PRE_TOOL_USE) == []

    def test_nonexistent_directory(self, tmp_path):
        mgr = HookManager(tmp_path / "nonexistent")
        assert mgr.get_hooks(HookEvent.PRE_MODEL) == []

    def test_discovers_py_hooks(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(hooks_dir, "pre-tool-use.py", "import sys; sys.exit(0)")

        mgr = HookManager(hooks_dir)
        hooks = mgr.get_hooks(HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].name == "pre-tool-use.py"

    def test_discovers_js_hooks(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_js_hook(hooks_dir, "session-start.js", "process.exit(0);")

        mgr = HookManager(hooks_dir)
        hooks = mgr.get_hooks(HookEvent.SESSION_START)
        assert len(hooks) == 1

    def test_discovers_named_hooks(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(hooks_dir, "pre-tool-use-validate.py", "import sys; sys.exit(0)")

        mgr = HookManager(hooks_dir)
        hooks = mgr.get_hooks(HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1

    def test_ignores_unrecognised_files(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "readme.txt").write_text("not a hook")
        (hooks_dir / "random.sh").write_text("#!/bin/bash\nexit 0")

        mgr = HookManager(hooks_dir)
        for event in HookEvent:
            assert mgr.get_hooks(event) == []

    def test_multiple_hooks_same_event(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(hooks_dir, "post-model.py", "import sys; sys.exit(0)")
        _write_py_hook(hooks_dir, "post-model-log.py", "import sys; sys.exit(0)")

        mgr = HookManager(hooks_dir)
        hooks = mgr.get_hooks(HookEvent.POST_MODEL)
        assert len(hooks) == 2

    def test_refresh_picks_up_new_hooks(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        mgr = HookManager(hooks_dir)

        assert mgr.get_hooks(HookEvent.SESSION_END) == []

        _write_py_hook(hooks_dir, "session-end.py", "import sys; sys.exit(0)")
        mgr.refresh()

        assert len(mgr.get_hooks(HookEvent.SESSION_END)) == 1


# -----------------------------------------------------------------------
# Execution
# -----------------------------------------------------------------------


class TestHookExecution:
    @pytest.mark.asyncio
    async def test_exit_0_allows(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(
            hooks_dir,
            "pre-tool-use.py",
            """\
            import sys
            sys.exit(0)
            """,
        )

        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.PRE_TOOL_USE, {"tool": "bash"})
        assert len(results) == 1
        assert results[0].allowed is True

    @pytest.mark.asyncio
    async def test_exit_1_errors(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(
            hooks_dir,
            "pre-model.py",
            """\
            import sys
            print("error info", file=sys.stderr)
            sys.exit(1)
            """,
        )

        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.PRE_MODEL, {})
        assert len(results) == 1
        assert results[0].error is True
        assert "error info" in results[0].stderr

    @pytest.mark.asyncio
    async def test_exit_2_blocks(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(
            hooks_dir,
            "pre-tool-use.py",
            """\
            import sys
            sys.exit(2)
            """,
        )

        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.PRE_TOOL_USE, {"tool": "write"})
        assert len(results) == 1
        assert results[0].blocked is True

    @pytest.mark.asyncio
    async def test_stdout_json_parsed(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(
            hooks_dir,
            "pre-tool-use.py",
            """\
            import json, sys
            data = json.load(sys.stdin)
            data["injected"] = True
            print(json.dumps(data))
            sys.exit(0)
            """,
        )

        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.PRE_TOOL_USE, {"tool": "bash"})
        assert len(results) == 1
        assert results[0].stdout is not None
        assert results[0].stdout["tool"] == "bash"
        assert results[0].stdout["injected"] is True

    @pytest.mark.asyncio
    async def test_payload_received_on_stdin(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        marker = tmp_path / "marker.json"
        _write_py_hook(
            hooks_dir,
            "post-tool-use.py",
            f"""\
            import json, sys
            data = json.load(sys.stdin)
            with open("{marker}", "w") as f:
                json.dump(data, f)
            sys.exit(0)
            """,
        )

        mgr = HookManager(hooks_dir)
        await mgr.run_hooks(HookEvent.POST_TOOL_USE, {"result": "ok", "tool": "read"})

        assert marker.exists()
        written = json.loads(marker.read_text())
        assert written["result"] == "ok"
        assert written["tool"] == "read"

    @pytest.mark.asyncio
    async def test_blocking_hook_stops_chain(self, tmp_path):
        """When a hook returns exit 2, subsequent hooks should NOT run."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        marker = tmp_path / "second_ran.txt"

        # First hook blocks
        _write_py_hook(
            hooks_dir,
            "pre-tool-use-01-block.py",
            """\
            import sys
            sys.exit(2)
            """,
        )
        # Second hook writes a marker file (should not run)
        _write_py_hook(
            hooks_dir,
            "pre-tool-use-02-marker.py",
            f"""\
            import sys
            with open("{marker}", "w") as f:
                f.write("ran")
            sys.exit(0)
            """,
        )

        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.PRE_TOOL_USE, {})

        assert len(results) == 1  # Only the blocking hook
        assert results[0].blocked is True
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_no_hooks_returns_empty(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.SESSION_START, {})
        assert results == []

    @pytest.mark.asyncio
    async def test_non_json_stdout_handled(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(
            hooks_dir,
            "post-model.py",
            """\
            print("not json output")
            import sys; sys.exit(0)
            """,
        )

        mgr = HookManager(hooks_dir)
        results = await mgr.run_hooks(HookEvent.POST_MODEL, {})
        assert len(results) == 1
        assert results[0].allowed is True
        assert results[0].stdout is None  # Could not parse as JSON

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _write_py_hook(
            hooks_dir,
            "pre-model.py",
            """\
            import time
            time.sleep(30)
            """,
        )

        mgr = HookManager(hooks_dir, timeout=0.5)
        results = await mgr.run_hooks(HookEvent.PRE_MODEL, {})
        assert len(results) == 1
        assert results[0].error is True
        assert "Timed out" in results[0].stderr

    @pytest.mark.asyncio
    async def test_hook_env_contains_event(self, tmp_path):
        """The KZ_HOOK_EVENT environment variable should be set."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        marker = tmp_path / "env_event.txt"
        _write_py_hook(
            hooks_dir,
            "session-start.py",
            f"""\
            import os, sys
            with open("{marker}", "w") as f:
                f.write(os.environ.get("KZ_HOOK_EVENT", "MISSING"))
            sys.exit(0)
            """,
        )

        mgr = HookManager(hooks_dir)
        await mgr.run_hooks(HookEvent.SESSION_START, {})

        assert marker.exists()
        assert marker.read_text() == "session-start"
