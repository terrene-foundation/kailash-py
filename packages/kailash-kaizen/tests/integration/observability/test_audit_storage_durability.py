"""
Tier 2 integration tests for ``FileAuditStorage`` durability (#2109, #2110).

Real concurrency against a real filesystem -- NO MOCKS (``rules/testing.md``).
The failure these pin is a TORN JSONL line: an audit record split across two
interleaved writes is unrecoverable, and (before #2109) vanished from every
query without a signal.

Payloads are deliberately larger than the stdlib IO buffer
(``io.DEFAULT_BUFFER_SIZE`` == 8192). A single-``write()`` line under that
size is atomic on an ``O_APPEND`` fd and would NOT discriminate between a
locked and an unlocked writer -- the test would pass either way and report
nothing (``rules/instrument-discipline.md`` MUST-1).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import anyio
import pytest

from kaizen.core.autonomy.observability import audit as audit_module
from kaizen.core.autonomy.observability.audit import FileAuditStorage
from kaizen.core.autonomy.observability.types import AuditEntry

# Each record is ~64 KiB -- 8x the stdlib buffer, so a buffered writer MUST
# issue several underlying write() calls per line and two concurrent writers
# can interleave mid-line.
PAYLOAD = "x" * 64_000
RECORDS_PER_WRITER = 40


def _entry(writer: str, index: int) -> AuditEntry:
    return AuditEntry(
        timestamp=datetime.now(timezone.utc),
        agent_id=f"writer-{writer}",
        action="tool_execute",
        details={"seq": index, "padding": PAYLOAD},
        result="success",
    )


def _read_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text().split("\n") if ln]


def _assert_no_torn_lines(path: Path, expected: int) -> None:
    """Every line parses as JSON, and the count is exact."""
    lines = _read_lines(path)
    torn = []
    for lineno, line in enumerate(lines, start=1):
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            torn.append((lineno, len(line), str(exc)))
    assert not torn, (
        f"{len(torn)} torn JSONL line(s) in {path} "
        f"(first: line {torn[0][0]}, {torn[0][1]} bytes, {torn[0][2]})"
    )
    assert len(lines) == expected, f"expected {expected} records, found {len(lines)}"


class TestConcurrentAppendDoesNotTear:
    """#2109 item 2 -- concurrent appends must not produce a torn line."""

    @pytest.mark.asyncio
    async def test_two_tasks_in_one_process(self, tmp_path):
        """Two anyio tasks sharing ONE storage instance."""
        path = tmp_path / "audit.jsonl"
        storage = FileAuditStorage(str(path))

        async def writer(name: str) -> None:
            for i in range(RECORDS_PER_WRITER):
                await storage.append(_entry(name, i))

        async with anyio.create_task_group() as tg:
            tg.start_soon(writer, "a")
            tg.start_soon(writer, "b")

        _assert_no_torn_lines(path, RECORDS_PER_WRITER * 2)

    @pytest.mark.asyncio
    async def test_two_tasks_separate_instances(self, tmp_path):
        """Two anyio tasks with SEPARATE storage instances on one path.

        Distinct from the test above: an instance-attribute lock would pass
        that one and fail this one, so this is what pins the lock to the
        resolved PATH rather than to the object.
        """
        path = tmp_path / "audit.jsonl"

        async def writer(name: str) -> None:
            storage = FileAuditStorage(str(path))
            for i in range(RECORDS_PER_WRITER):
                await storage.append(_entry(name, i))

        async with anyio.create_task_group() as tg:
            tg.start_soon(writer, "a")
            tg.start_soon(writer, "b")

        _assert_no_torn_lines(path, RECORDS_PER_WRITER * 2)

    def test_two_separate_processes(self, tmp_path):
        """Two OS processes appending to one path (cross-process flock).

        An in-process ``anyio.Lock`` alone passes the two tests above and
        FAILS this one, which is why all three are here.
        """
        path = tmp_path / "audit.jsonl"

        # Pin the child's import path to THIS checkout by deriving it from the
        # module under test, never a hard-coded worktree path. The child
        # asserts it resolved the same file the parent did.
        expected_module = str(Path(audit_module.__file__).resolve())
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))

        worker = f"""
import anyio, sys
from datetime import datetime, timezone
from kaizen.core.autonomy.observability import audit as m
from kaizen.core.autonomy.observability.audit import FileAuditStorage
from kaizen.core.autonomy.observability.types import AuditEntry

resolved = str(__import__("pathlib").Path(m.__file__).resolve())
assert resolved == {expected_module!r}, "child imported " + resolved

async def main():
    storage = FileAuditStorage({str(path)!r})
    for i in range({RECORDS_PER_WRITER}):
        await storage.append(AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id="writer-" + sys.argv[1],
            action="tool_execute",
            details={{"seq": i, "padding": "x" * 64_000}},
            result="success",
        ))

anyio.run(main)
"""
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", worker, name],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for name in ("a", "b")
        ]
        for proc in procs:
            _, err = proc.communicate(timeout=180)
            assert proc.returncode == 0, err.decode()

        _assert_no_torn_lines(path, RECORDS_PER_WRITER * 2)


class TestConcurrentRotationDoesNotDestroyRecords:
    """#2109 item 2 x #2110 item 1 -- where the lock is actually load-bearing.

    A bare ``O_APPEND`` write of one line is already atomic (measured: CPython
    issues exactly ONE ``write(2)`` per line at every size tested, including
    multi-megabyte lines, because ``BufferedWriter`` bypasses its buffer for
    writes larger than it). So the unlocked writer did NOT tear lines, and the
    tests above pass with or without the lock -- they are regression pins, not
    the evidence.

    ROTATION is the multi-step critical section: stat -> unlink -> rename
    chain -> rename active -> write. Two processes interleaving there
    genuinely DESTROY records, because one rename lands on top of a segment
    the other just moved. That is what this test pins, and it is why the
    lock is required rather than merely prudent.
    """

    def test_two_processes_rotating_lose_no_records(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        records_each = 150
        # Small segments so the run forces ~20+ rotations; retention high
        # enough that NOTHING is legitimately aged out, so any missing
        # record is a race, not policy.
        max_bytes = 4096
        retention = 80

        expected_module = str(Path(audit_module.__file__).resolve())
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))

        worker = f"""
import anyio, sys, pathlib
from datetime import datetime, timezone
from kaizen.core.autonomy.observability import audit as m
from kaizen.core.autonomy.observability.audit import FileAuditStorage
from kaizen.core.autonomy.observability.types import AuditEntry

resolved = str(pathlib.Path(m.__file__).resolve())
assert resolved == {expected_module!r}, "child imported " + resolved

async def main():
    storage = FileAuditStorage(
        {str(path)!r},
        max_bytes={max_bytes},
        retention_count={retention},
        fsync=False,
    )
    for i in range({records_each}):
        await storage.append(AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id="writer-" + sys.argv[1],
            action="tool_execute",
            details={{"seq": i}},
            result="success",
        ))

anyio.run(main)
"""
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", worker, name],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for name in ("a", "b")
        ]
        for proc in procs:
            _, err = proc.communicate(timeout=300)
            assert proc.returncode == 0, err.decode()

        storage = FileAuditStorage(
            str(path), max_bytes=max_bytes, retention_count=retention
        )
        segments = storage.segments()
        assert len(segments) > 2, (
            f"expected the run to force rotations, got {len(segments)} segment(s) "
            "-- the test would not exercise the rotation race"
        )

        seen: set[tuple[str, int]] = set()
        torn = []
        for segment in segments:
            for lineno, line in enumerate(_read_lines(segment), start=1):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    torn.append((segment.name, lineno, str(exc)))
                    continue
                if rec["action"] == "tool_execute":
                    seen.add((rec["agent_id"], rec["details"]["seq"]))

        assert not torn, f"{len(torn)} torn line(s): {torn[:3]}"

        expected = {
            (f"writer-{name}", i) for name in ("a", "b") for i in range(records_each)
        }
        missing = expected - seen
        assert not missing, (
            f"{len(missing)} audit record(s) DESTROYED by a concurrent "
            f"rotation (retention was {retention}, so none should age out); "
            f"examples: {sorted(missing)[:5]}"
        )
