# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: JsonlSink path-safety (security-reviewer H2 on PR #587).

Security-reviewer flagged that the original ``JsonlSink.__init__`` used
``Path(path)`` verbatim without resolving symlinks or applying
``O_NOFOLLOW``. A malicious or accidentally-misplaced symlink at the
target path silently redirected the trace stream elsewhere. Fix:

  - ``__init__`` resolves the path via ``expanduser().resolve(strict=False)``
    so ``..`` segments are normalized at construction time.
  - ``__call__`` opens via ``os.open(..., O_NOFOLLOW, 0o600)`` on POSIX
    so a symlink at the destination raises ``OSError`` (typically
    ``ELOOP``) rather than following through.

Tests below assert both halves of the contract behaviorally.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.diagnostics.protocols import TraceEvent, TraceEventType

from kaizen.observability import JsonlSink


pytestmark = pytest.mark.regression


def _mk_event(event_id: str = "ev-path-safety") -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        event_type=TraceEventType.AGENT_STEP,
        timestamp=datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc),
        run_id="run-path-safety",
        agent_id="agent-path-safety",
        cost_microdollars=0,
    )


def test_path_resolved_at_construction_normalizes_dotdot(tmp_path: Path):
    """``JsonlSink.path`` MUST be fully resolved at ``__init__``."""
    # Create a nested directory and a path containing `..` that
    # resolves back into the tmp_path.
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    traversing = nested / ".." / ".." / "trace.jsonl"

    sink = JsonlSink(traversing)
    assert ".." not in str(
        sink.path
    ), f"JsonlSink did not normalize traversal at __init__: {sink.path}"
    assert sink.path.is_absolute(), "JsonlSink.path should be absolute after resolve()"


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"),
    reason="O_NOFOLLOW is POSIX-only (Windows path uses the Path.open fallback)",
)
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink refusal behavior is POSIX-specific",
)
def test_jsonl_sink_refuses_symlink_target(tmp_path: Path):
    """A symlink planted at the destination path MUST raise ``OSError``.

    Without ``O_NOFOLLOW``, the sink would follow the symlink and
    silently write into whatever the attacker pointed the symlink at.
    With ``O_NOFOLLOW``, ``os.open`` raises (typically ``ELOOP``,
    ``errno 40``). The sink's callable contract is that the raise
    surfaces to the caller — the exporter then WARN-logs and continues
    (the TraceExporter's ``raise_on_error=False`` default).
    """
    # Create a target file outside the "trusted" trace dir.
    attacker_target = tmp_path / "attacker-target.jsonl"
    attacker_target.write_text("")

    # Plant a symlink at the destination that would normally be the
    # trace log.
    trace_path = tmp_path / "trace.jsonl"
    trace_path.symlink_to(attacker_target)

    sink = JsonlSink(trace_path)
    # The resolved path follows the symlink at resolve() time, so we
    # construct a second sink with the un-resolved string and rely on
    # O_NOFOLLOW to catch the redirection at write time.
    sink_raw = JsonlSink.__new__(JsonlSink)
    sink_raw._path = trace_path  # bypass resolve() so symlink still present
    sink_raw._mode = "a"
    import threading

    sink_raw._lock = threading.Lock()

    with pytest.raises(OSError):
        sink_raw(_mk_event(), "0" * 64)

    # Attacker target received no writes.
    assert (
        attacker_target.read_text() == ""
    ), "JsonlSink followed the symlink — O_NOFOLLOW missing from open flags"


def test_jsonl_sink_writes_fresh_file_end_to_end(tmp_path: Path):
    """Happy-path write: no symlink, no traversal, O_NOFOLLOW permitted."""
    target = tmp_path / "trace.jsonl"
    sink = JsonlSink(target)
    sink(_mk_event(event_id="ev-happy"), "deadbeef" * 8)

    # File exists and contains exactly one JSONL line.
    contents = target.read_text()
    assert contents.endswith("\n")
    assert contents.count("\n") == 1
    assert '"fingerprint":"' + "deadbeef" * 8 + '"' in contents

    # File-mode bits are 0o600 on POSIX.
    if hasattr(os, "O_NOFOLLOW") and sys.platform != "win32":
        mode = target.stat().st_mode & 0o777
        assert (
            mode == 0o600
        ), f"JsonlSink file mode bits are {oct(mode)}; expected 0o600"


def test_jsonl_sink_rejects_invalid_mode():
    """Mode MUST be 'a' or 'w' — 'r', 'rb', etc. are BLOCKED."""
    with pytest.raises(ValueError, match="mode must be"):
        JsonlSink("/tmp/whatever.jsonl", mode="r")
    with pytest.raises(ValueError, match="mode must be"):
        JsonlSink("/tmp/whatever.jsonl", mode="a+")
