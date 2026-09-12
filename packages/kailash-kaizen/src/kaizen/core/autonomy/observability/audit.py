"""
Audit trail storage and querying for compliance logging.

This module provides immutable audit trail capabilities for enterprise compliance:
- AuditStorage protocol: Interface for audit backends
- FileAuditStorage: JSONL file-based storage (append-only, locked, rotated)
- AuditTrailManager: High-level audit trail management

Audit trails are immutable and append-only to meet compliance requirements
(SOC2, GDPR, HIPAA). All critical actions are recorded with timestamps,
agent IDs, user IDs, and action details.

Durability posture (#2109, #2110)
---------------------------------
The governing principle is that a trail which silently drops a record is
worse than one that loudly fails: a loud failure is an incident someone
handles, a silent gap is a clean-looking record that is wrong. So every
write path here either completes or RAISES ``AuditWriteError``; none of them
swallow.

What this storage backend CAN claim:

- Appends are serialized by a per-path ``anyio.Lock`` (in-process) AND an
  ``fcntl.flock`` on a dedicated sidecar lock file (cross-process, and also
  cross-thread/cross-event-loop, since the lock is held on a distinct open
  file description). The sidecar is locked rather than the log itself
  because rotation RENAMES the log, and a lock held on a renamed inode
  stops excluding anyone.
- The append critical section is lock -> maybe-rotate -> write -> optional
  fsync -> unlock, so a rotation can never interleave with another writer's
  append. This is what makes the lock load-bearing: a bare O_APPEND write
  was already atomic, rotation is NOT.
- With ``fsync=True`` (the default) a returned ``append`` has reached the
  storage device, not merely the page cache.

What it CANNOT claim, stated explicitly so no caller infers it:

- ``fcntl.flock`` is ADVISORY and is not reliable over NFS (on many NFS
  mounts it is emulated locally, so two clients on two hosts do not
  exclude each other). A network filesystem needs a real backend.
- On a platform without ``fcntl`` the cross-process layer is unavailable;
  that case emits a one-time WARNING naming the lost protection rather than
  degrading quietly.
- ``fsync`` covers the file's data, not a parent-directory rename entry on
  every filesystem, so a crash in the microseconds around a rotation may
  leave a segment visible under either name.
- Nothing here defends against a writer with write access deliberately
  editing or truncating the file. Immutability is a contract, not enforcement.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

import json
import logging
import os
import stat
import threading
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import anyio

from kaizen.core.autonomy.observability.audit_paths import default_audit_path
from kaizen.core.autonomy.observability.types import AuditEntry, AuditResult
from kaizen.utils.credential_scrub import scrub_remote_error

try:  # pragma: no cover - exercised by platform, not by branch
    import fcntl

    _HAVE_FLOCK = True
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]
    _HAVE_FLOCK = False

logger = logging.getLogger(__name__)

#: Size at which the active segment is rotated. 32 MiB holds a large number
#: of entries while staying small enough that a full-segment scan is a
#: bounded cost.
DEFAULT_MAX_BYTES = 32 * 1024 * 1024

#: Rotated segments retained. With the default size cap this bounds total
#: audit storage at roughly 288 MiB (8 rotated + 1 active), which is the
#: point of #2110: the default path can no longer fill a volume.
DEFAULT_RETENTION_COUNT = 8

#: Suggested per-append timeout for callers that impose one (the hook layer
#: does). Exported as the storage layer's CONTRACT: an append may legitimately
#: take this long on a contended volume, and cutting it shorter converts a
#: slow write into a lost compliance record. The audit path is not the
#: metrics path -- a dropped metrics sample is a gap in a graph.
AUDIT_APPEND_BUDGET_SECONDS = 5.0

#: Action recorded when the active segment is rotated.
ROTATION_ACTION = "audit_log_rotated"

#: Action recorded when retention DESTROYS a rotated segment.
SEGMENT_DROPPED_ACTION = "audit_log_segment_dropped"

#: ``agent_id`` used for records the storage layer writes about itself.
STORAGE_AGENT_ID = "kaizen.audit_storage"

#: Bytes of a malformed line retained for diagnosis. Bounded so one torn
#: multi-megabyte line cannot be re-materialized in full by a query.
_MALFORMED_EXCERPT_BYTES = 512

# Per-resolved-path async locks. Keyed by path (NOT held on the instance) so
# two FileAuditStorage objects addressing one file still serialize; the guard
# protects registry mutation from threads, since the registry itself is read
# from worker threads as well as the event loop.
_PATH_LOCKS: dict[str, anyio.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_NO_FLOCK_WARNED = False


class AuditWriteError(OSError):
    """
    An audit record could not be durably written.

    Subclasses ``OSError`` deliberately: ``append``'s documented contract has
    always been that it raises ``IOError`` (an alias of ``OSError``) on write
    failure, so existing handlers keep working while gaining a specific type
    to match on.
    """


class AuditIntegrityError(RuntimeError):
    """
    The audit trail on disk contains lines that are not valid records.

    Raised only by ``query(strict=True)``. The default is NOT strict, because
    one torn line must not make every INTACT record unreadable -- that would
    convert a partial loss into a total one. The malformed lines are reported
    through ``AuditQueryResult.malformed`` instead.
    """


@dataclass(frozen=True)
class MalformedAuditLine:
    """
    A line that is present in the trail but is not a readable record.

    This type exists so that "the record isn't there" and "the record was
    DESTROYED" can never be returned as the same answer (#2109 item 3).

    Attributes:
        source: Segment file the line was read from.
        line_number: 1-based line number WITHIN that segment.
        error: Why it could not be parsed.
        excerpt: First ``_MALFORMED_EXCERPT_BYTES`` characters of the raw
            line, for diagnosis. Returned to the caller but NEVER logged --
            a malformed audit line still contains audit payload, and the log
            stream is not held to the 0o600 the trail itself is.
        length: Full length of the raw line, which ``excerpt`` may truncate.
    """

    source: Path
    line_number: int
    error: str
    excerpt: str
    length: int


class AuditQueryResult(list[AuditEntry]):
    """
    Query results, plus the integrity signal for the lines that failed.

    Subclasses ``list`` so that every existing caller -- ``len(entries)``,
    ``entries[0]``, iteration, truthiness -- keeps working unchanged. The
    integrity signal is ADDITIVE:

        >>> result = await storage.query(agent_id="qa-agent")
        >>> len(result)              # entries, exactly as before
        12
        >>> result.malformed_count   # new: lines that could not be read
        0

    A caller that checks nothing gets the previous behaviour; a caller that
    cares about completeness can now tell an empty result apart from a
    destroyed one.
    """

    def __init__(
        self,
        entries: Iterable[AuditEntry] = (),
        malformed: Sequence[MalformedAuditLine] = (),
    ) -> None:
        super().__init__(entries)
        self.malformed: tuple[MalformedAuditLine, ...] = tuple(malformed)

    @property
    def malformed_count(self) -> int:
        """Number of unreadable lines encountered while producing this result."""
        return len(self.malformed)

    @property
    def is_complete(self) -> bool:
        """True when every line scanned was a readable record."""
        return not self.malformed


class AuditStorage(Protocol):
    """
    Protocol for audit trail storage backends.

    All implementations must provide:
    - append(): Immutable append operation
    - query(): Query with filtering support

    Storage backends must be:
    - Append-only (no updates or deletes)
    - Persistent (survive process restarts)
    - Queryable (support filtering by time, agent, action)

    Example implementations:
    - FileAuditStorage: JSONL file-based storage
    - DatabaseAuditStorage: PostgreSQL/MySQL storage
    - S3AuditStorage: AWS S3 storage
    """

    async def append(self, entry: AuditEntry) -> None:
        """
        Append immutable audit entry.

        Entries are never modified or deleted after append.

        Implementations MUST NOT swallow a write failure. A backend that
        cannot record an entry raises; it does not return successfully having
        dropped it.

        Args:
            entry: AuditEntry to append

        Raises:
            IOError: If storage operation fails
        """
        pass

    async def query(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        action: str | None = None,
        user_id: str | None = None,
        result: AuditResult | None = None,
    ) -> list[AuditEntry]:
        """
        Query audit entries with filtering.

        All filters are optional and combined with AND logic.
        If no filters provided, returns all entries.

        Args:
            agent_id: Filter by agent ID
            start_time: Filter entries >= start_time
            end_time: Filter entries <= end_time
            action: Filter by action type
            user_id: Filter by user ID
            result: Filter by result (success, failure, denied)

        Returns:
            List of matching AuditEntry objects, oldest first. Backends that
            can detect unreadable records SHOULD return an
            ``AuditQueryResult``, which is a ``list`` carrying that signal.
        """
        pass


def _lock_for(resolved_path: str) -> anyio.Lock:
    """Get (or create) the process-wide async lock for one resolved path."""
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(resolved_path)
        if lock is None:
            lock = anyio.Lock()
            _PATH_LOCKS[resolved_path] = lock
        return lock


def _warn_once_no_flock() -> None:
    """
    Announce, exactly once, that cross-process locking is unavailable.

    Degrading silently here would leave an operator believing two processes
    sharing one audit path are serialized when they are not -- the precise
    class of quiet fallback this module exists to remove.
    """
    global _NO_FLOCK_WARNED
    if _NO_FLOCK_WARNED:
        return
    _NO_FLOCK_WARNED = True
    logger.warning(
        "audit.flock_unavailable platform=%s -- fcntl is not importable, so "
        "audit appends are serialized WITHIN this process only. Two processes "
        "sharing one audit path can interleave a rotation with an append and "
        "lose records. Give each process its own audit_log_path, or use a "
        "database-backed AuditStorage.",
        os.name,
    )


def _write_all(fd: int, data: bytes) -> None:
    """
    Write every byte of ``data`` to ``fd``, looping over partial writes.

    ``os.write`` is permitted to write fewer bytes than requested. On an
    O_APPEND descriptor each retry lands at the CURRENT end of file, so a
    partial write followed by another writer's append is exactly how a JSONL
    line gets torn. This loop is only safe because the caller holds the
    exclusive lock for its whole duration.
    """
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:  # pragma: no cover - os.write raises instead
            raise AuditWriteError(
                f"audit write made no progress ({written} bytes written, "
                f"{len(view)} remaining)"
            )
        view = view[written:]


class FileAuditStorage:
    """
    File-based audit storage using JSONL format (JSON Lines).

    Each line is a complete JSON object representing one AuditEntry.
    Format is compatible with log aggregation tools (Logstash, Fluentd).

    Storage is append-only for immutability and compliance.
    Performance target: <10ms per append (ADR-017).

    Growth is BOUNDED (#2110): the active segment is rotated at
    ``max_bytes`` and ``retention_count`` rotated segments are kept. Rotated
    segments stay queryable -- ``query`` and ``count`` span all of them,
    oldest first -- and both the rotation and any retention-driven
    destruction of a segment are themselves recorded as audit entries.

    Example:
        >>> storage = FileAuditStorage()           # XDG state dir, not CWD
        >>> entry = AuditEntry(
        ...     timestamp=datetime.now(timezone.utc),
        ...     agent_id="qa-agent",
        ...     action="tool_execute",
        ...     details={"tool_name": "bash_command"},
        ...     result="success"
        ... )
        >>> await storage.append(entry)
        >>>
        >>> entries = await storage.query(agent_id="qa-agent")
        >>> entries.malformed_count
        0
    """

    # Owner-only. An audit trail records which agent did what, when, and the
    # SHAPE of every payload involved; 0o644 would make that world-readable
    # to every local account.
    _FILE_MODE = 0o600
    _DIR_MODE = 0o700

    def __init__(
        self,
        file_path: str | Path | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        retention_count: int = DEFAULT_RETENTION_COUNT,
        fsync: bool = True,
    ):
        """
        Initialize file-based audit storage.

        The FILE is owner-only (0o600), including one created BEFORE this
        behaviour existed -- an audit trail any local account can read is a
        weak compliance artifact, and leaving upgraded installs on 0o644 would
        mean the fix never reaches them, since the file is created once and
        reused forever. Every mode change is announced rather than silent,
        naming the path and the mode it had, because re-permissioning a file
        the operator may have configured deliberately is not something to do
        quietly.

        The DIRECTORY is pinned to 0o700 only when this class CREATES it. See
        the comment in the body: the parent may be a location shared with
        other services, and that is not this class's to re-permission.

        Args:
            file_path: Path to the active JSONL segment (created if absent).
                Defaults to ``default_audit_path()`` -- an ABSOLUTE path under
                the XDG state directory. It is deliberately not relative to
                the working directory: a library does not get to choose the
                operator's CWD, and a CWD-relative default fragments the trail
                across every directory an agent is launched from (#2110).
            max_bytes: Rotate the active segment once a write would carry it
                past this size. Must be positive.
            retention_count: Number of rotated segments to keep. ``0`` keeps
                none, meaning each rotation destroys the segment it displaces.
            fsync: Flush to the storage DEVICE on every append, not merely to
                the page cache. Defaults True: without it a crash loses
                records that ``append`` already reported as written, which is
                the silent-gap failure the audit trail exists to preclude.
                Turning it off trades crash-durability for throughput.

        Raises:
            ValueError: If ``max_bytes`` or ``retention_count`` is invalid.
            OSError: If the path cannot be created (read-only filesystem,
                permissions). Callers wiring this on a default-on path must
                handle it -- see ``SmartDefaultsManager.create_observability``.
        """
        if max_bytes <= 0:
            raise ValueError(f"max_bytes must be positive, got {max_bytes}")
        if retention_count < 0:
            raise ValueError(f"retention_count must be >= 0, got {retention_count}")

        self.file_path = (
            Path(file_path) if file_path is not None else default_audit_path()
        )
        self.max_bytes = max_bytes
        self.retention_count = retention_count
        self.fsync = fsync

        # The lock is held on a SIDECAR, never on the log itself: rotation
        # renames the log, and a flock held on the renamed inode no longer
        # excludes a process that opens the path afresh.
        self._lock_path = self.file_path.with_name(self.file_path.name + ".lock")

        # The DIRECTORY is tightened only if this class created it. The
        # asymmetry with the file below is deliberate: `file_path.parent` may
        # be a shared location like `/var/log/kaizen` that other services also
        # write to. Chmodding it to 0o700 is a surprise well outside this
        # class's remit -- and it is not what protects the record. The FILE
        # mode is. `mkdir(mode=...)` is masked by umask, so when we do create
        # it, set the mode explicitly rather than trusting the create call.
        parent = self.file_path.parent
        parent_existed = parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        if not parent_existed:
            self._enforce_mode(parent, self._DIR_MODE)

        # Create file if not exists
        if not self.file_path.exists():
            # `touch(mode=...)` is also umask-masked, and a umask of 0 would
            # leave the file group/world readable, so chmod unconditionally
            # below rather than trusting the create mode.
            self.file_path.touch(mode=self._FILE_MODE)
            logger.info(f"Created audit file: {self.file_path}")
        self._enforce_mode(self.file_path, self._FILE_MODE)

        if not _HAVE_FLOCK:
            _warn_once_no_flock()

        logger.debug(f"FileAuditStorage initialized: {self.file_path}")

    @staticmethod
    def _enforce_mode(path: Path, mode: int) -> None:
        """
        Pin ``path`` to ``mode``, announcing EVERY mode it changes.

        Compares the REAL mode after the fact rather than trusting the create
        call: a mode requested at creation and stripped by umask is
        indistinguishable from one never requested.

        Both directions are announced, not just the group/world-accessible
        one. Pinning is not always a tightening: an operator-set ``0o400``
        becomes ``0o600``, which ADDS write. Warning only on the loose case
        would leave that particular change -- the one an operator is most
        likely to have made deliberately -- silent.
        """
        current = stat.S_IMODE(path.stat().st_mode)
        if current == mode:
            return
        if current & 0o077:
            logger.warning(
                "Audit path %s was %s (group/world accessible); tightening to "
                "%s. An audit trail readable by other local accounts is not a "
                "compliance artifact.",
                path,
                oct(current),
                oct(mode),
            )
        else:
            logger.warning(
                "Audit path %s was %s; setting %s, which the append-only "
                "trail requires. No other local account gains access.",
                path,
                oct(current),
                oct(mode),
            )
        path.chmod(mode)

    # ------------------------------------------------------------------
    # Segment layout
    # ------------------------------------------------------------------

    def segment_path(self, index: int) -> Path:
        """
        Path of rotated segment ``index``.

        ``1`` is the most recently rotated segment; higher indices are older.
        ``0`` is the active segment.
        """
        if index == 0:
            return self.file_path
        return self.file_path.with_name(f"{self.file_path.name}.{index}")

    def segments(self) -> list[Path]:
        """
        Every existing segment, OLDEST first, active segment last.

        This is the read order for ``query`` and ``count``: because each
        segment is append-only and rotation preserves order, reading in this
        sequence yields entries chronologically without needing a sort.
        """
        found = [
            self.segment_path(i)
            for i in range(self.retention_count, 0, -1)
            if self.segment_path(i).exists()
        ]
        if self.file_path.exists():
            found.append(self.file_path)
        return found

    # ------------------------------------------------------------------
    # Append path
    # ------------------------------------------------------------------

    @staticmethod
    def _encode(entry: AuditEntry) -> bytes:
        entry_dict = asdict(entry)
        entry_dict["timestamp"] = entry.timestamp.isoformat()
        return (json.dumps(entry_dict) + "\n").encode("utf-8")

    @staticmethod
    def _storage_entry(action: str, details: dict) -> AuditEntry:
        """Build a record the storage layer writes ABOUT ITSELF."""
        return AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id=STORAGE_AGENT_ID,
            action=action,
            details=details,
            result="success",
            metadata={"component": "FileAuditStorage"},
        )

    async def append(self, entry: AuditEntry) -> None:
        """
        Append audit entry to the active JSONL segment.

        The whole critical section -- decide-rotation, rotate, write, fsync --
        runs while holding both the in-process lock for this path and an
        exclusive ``flock`` on the sidecar, so no other appender or rotator
        can interleave with any part of it.

        The blocking file work runs in a worker thread rather than on the
        event loop, because ``flock`` and ``fsync`` both block and doing them
        inline would stall every other task in the process.

        Args:
            entry: AuditEntry to append

        Raises:
            AuditWriteError: If the entry could not be durably written. This
                is an ``OSError``, so callers already handling ``IOError``
                from this method keep working. It is RAISED rather than
                logged: a dropped audit record must be an incident, not a
                line in a log nobody reads.
        """
        data = self._encode(entry)
        resolved = str(self.file_path.resolve())

        async with _lock_for(resolved):
            await anyio.to_thread.run_sync(self._locked_append, data)

        logger.debug(f"Audit entry appended: {entry.agent_id} - {entry.action}")

    def _locked_append(self, data: bytes) -> None:
        """
        Rotate-if-needed then append, holding the cross-process lock.

        Runs in a worker thread. Every failure path raises; none returns
        having silently skipped the write.
        """
        try:
            lock_fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, self._FILE_MODE)
        except OSError as exc:
            raise AuditWriteError(
                f"could not open audit lock file {self._lock_path}: {exc}"
            ) from exc

        try:
            if _HAVE_FLOCK:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                pending = self._rotate_if_needed(len(data))
                pending.append(data)
                self._append_raw(pending)
            finally:
                if _HAVE_FLOCK:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

    def _append_raw(self, chunks: list[bytes]) -> None:
        """Write every chunk to the active segment. Caller holds the lock."""
        try:
            fd = os.open(
                self.file_path,
                os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                self._FILE_MODE,
            )
        except OSError as exc:
            raise AuditWriteError(
                f"could not open audit segment {self.file_path}: {exc}"
            ) from exc

        try:
            for chunk in chunks:
                _write_all(fd, chunk)
            if self.fsync:
                os.fsync(fd)
        except OSError as exc:
            raise AuditWriteError(
                f"audit append to {self.file_path} failed: {exc}"
            ) from exc
        finally:
            os.close(fd)

    def _rotate_if_needed(self, incoming: int) -> list[bytes]:
        """
        Rotate the active segment if ``incoming`` bytes would overflow it.

        Returns the encoded records DESCRIBING the rotation, to be written
        into the new active segment ahead of the caller's entry. Rotation of
        a compliance artifact is itself an auditable event, and a segment
        destroyed by retention is the destruction of records -- both are
        recorded rather than inferred from file mtimes.

        Caller holds the exclusive lock; this renames files.
        """
        try:
            size = self.file_path.stat().st_size
        except FileNotFoundError:
            return []

        # An entry larger than the whole cap must still be written -- refusing
        # it would drop a record. Rotating an EMPTY segment would merely
        # produce empty files, so require existing content.
        if size == 0 or size + incoming <= self.max_bytes:
            return []

        dropped: Path | None = None
        dropped_bytes = 0
        dropped_records = 0

        # Whichever segment is about to fall off the end is DESTROYED, so
        # measure it before it goes -- afterwards there is nothing left to
        # count, and "some records were discarded" is not an audit record.
        # With retention_count == 0 nothing is kept, so the segment that
        # falls off is the active one itself.
        evicted = (
            self.segment_path(self.retention_count)
            if self.retention_count
            else self.file_path
        )
        if evicted.exists():
            dropped = evicted
            dropped_bytes = evicted.stat().st_size
            dropped_records = _count_lines(evicted)
            evicted.unlink()

        if self.retention_count:
            # Shift the survivors down one slot, oldest first so no rename
            # overwrites a segment that has not moved yet.
            for index in range(self.retention_count - 1, 0, -1):
                src = self.segment_path(index)
                if src.exists():
                    src.rename(self.segment_path(index + 1))
            self.file_path.rename(self.segment_path(1))

        records: list[bytes] = [
            self._encode(
                self._storage_entry(
                    ROTATION_ACTION,
                    {
                        "rotated_from": str(self.file_path),
                        "rotated_to": (
                            str(self.segment_path(1)) if self.retention_count else None
                        ),
                        "segment_bytes": size,
                        "max_bytes": self.max_bytes,
                        "retention_count": self.retention_count,
                    },
                )
            )
        ]
        if dropped is not None:
            logger.warning(
                "audit.segment_dropped path=%s bytes=%d records=%d "
                "retention_count=%d -- audit records were DESTROYED by the "
                "retention policy. Raise retention_count or ship segments "
                "off-host to keep them.",
                dropped,
                dropped_bytes,
                dropped_records,
                self.retention_count,
            )
            records.append(
                self._encode(
                    self._storage_entry(
                        SEGMENT_DROPPED_ACTION,
                        {
                            "dropped_segment": str(dropped),
                            "dropped_bytes": dropped_bytes,
                            "dropped_records": dropped_records,
                            "retention_count": self.retention_count,
                        },
                    )
                )
            )
        return records

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def iter_entries(
        self,
    ) -> AsyncIterator[tuple[AuditEntry | None, MalformedAuditLine | None]]:
        """
        Stream every segment, oldest first, one line at a time.

        Yields ``(entry, None)`` for a readable record and
        ``(None, malformed)`` for a line that is present but unreadable.

        Segments are read lazily rather than slurped, so peak memory is one
        line -- not one segment, and not the whole retained trail. Callers
        that do not need every match materialized should prefer this over
        ``query``, whose result list necessarily grows with the match count.
        """
        for segment in self.segments():
            async with await anyio.open_file(segment, "r") as handle:
                lineno = 0
                async for raw_line in handle:
                    lineno += 1
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry_dict = json.loads(line)
                        entry_dict["timestamp"] = datetime.fromisoformat(
                            entry_dict["timestamp"]
                        )
                        yield AuditEntry(**entry_dict), None
                    except (
                        json.JSONDecodeError,
                        KeyError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        yield None, MalformedAuditLine(
                            source=segment,
                            line_number=lineno,
                            error=f"{type(exc).__name__}: {exc}",
                            excerpt=line[:_MALFORMED_EXCERPT_BYTES],
                            length=len(line),
                        )

    async def query(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        action: str | None = None,
        user_id: str | None = None,
        result: AuditResult | None = None,
        *,
        strict: bool = False,
    ) -> AuditQueryResult:
        """
        Query audit entries across ALL segments with filtering.

        Segments are streamed oldest-first, one line at a time; only MATCHING
        entries are retained, so memory tracks the result rather than the
        trail.

        Unreadable lines are reported, never dropped (#2109 item 3). A torn
        line is corruption, and a query that silently skipped it would answer
        "that record isn't there" to a question whose true answer is "that
        record was destroyed" -- the one confusion an audit must not make.
        They arrive on ``AuditQueryResult.malformed``; because the result is
        a ``list`` subclass, callers that ignore it see exactly the previous
        shape.

        Note that filters apply to ENTRIES only. Malformed lines are reported
        whenever they are scanned, since an unreadable line cannot be shown
        not to match.

        Args:
            agent_id: Filter by agent ID
            start_time: Filter entries >= start_time
            end_time: Filter entries <= end_time
            action: Filter by action type
            user_id: Filter by user ID
            result: Filter by result (success, failure, denied)
            strict: Raise ``AuditIntegrityError`` if any unreadable line was
                scanned. Off by default so that one torn line cannot make
                every intact record unreadable.

        Returns:
            AuditQueryResult: matching entries, oldest first, carrying the
            malformed-line report.

        Raises:
            AuditIntegrityError: If ``strict`` and any line was unreadable.
        """
        entries: list[AuditEntry] = []
        malformed: list[MalformedAuditLine] = []

        async for entry, bad in self.iter_entries():
            if bad is not None:
                malformed.append(bad)
                continue
            assert entry is not None  # iter_entries yields exactly one of the two
            if agent_id and entry.agent_id != agent_id:
                continue
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue
            if action and entry.action != action:
                continue
            if user_id and entry.user_id != user_id:
                continue
            if result and entry.result != result:
                continue
            entries.append(entry)

        if malformed:
            # ERROR, with structured fields an alert can key on -- this is
            # corruption of a compliance artifact, not a parsing nuisance.
            # The raw line is deliberately NOT logged: it still holds audit
            # payload, and the log stream is not protected to 0o600 the way
            # the trail is. The excerpt travels on the returned object.
            logger.error(
                "audit.malformed_lines count=%d segments=%s first_source=%s "
                "first_line=%d first_error=%s -- audit records are CORRUPT "
                "and unrecoverable; investigate the writer.",
                len(malformed),
                sorted({str(m.source) for m in malformed}),
                malformed[0].source,
                malformed[0].line_number,
                malformed[0].error,
                extra={
                    "audit_malformed_count": len(malformed),
                    "audit_malformed_sources": sorted(
                        {str(m.source) for m in malformed}
                    ),
                },
            )
            if strict:
                raise AuditIntegrityError(
                    f"{len(malformed)} unreadable line(s) in the audit trail; "
                    f"first at {malformed[0].source}:{malformed[0].line_number} "
                    f"({malformed[0].error})"
                )

        logger.debug(
            f"Query returned {len(entries)} audit entries "
            f"({len(malformed)} malformed)"
        )
        return AuditQueryResult(entries, malformed)

    async def count(self) -> int:
        """
        Total count of audit lines across all retained segments.

        Counts LINES, including any that are unreadable: the count answers
        "how much is in the trail", and silently omitting corrupt lines would
        make the count disagree with the file for no visible reason. Use
        ``query()`` when the readable/unreadable split matters.

        Returns:
            Total number of non-empty lines across every segment.
        """
        total = 0
        for segment in self.segments():
            async with await anyio.open_file(segment, "r") as handle:
                async for line in handle:
                    if line.strip():
                        total += 1
        return total

    def get_file_path(self) -> Path:
        """
        Get the ACTIVE audit segment path.

        Returns:
            Path to the active audit file. Rotated segments are available via
            ``segment_path`` / ``segments``.
        """
        return self.file_path


def _count_lines(path: Path) -> int:
    """Count non-empty lines in ``path`` without holding it in memory."""
    total = 0
    with open(path, "rb") as handle:
        trailing_data = False
        while chunk := handle.read(1024 * 1024):
            total += chunk.count(b"\n")
            trailing_data = not chunk.endswith(b"\n")
        if trailing_data:
            total += 1
    return total


class AuditTrailManager:
    """
    Manages audit trail recording and querying.

    Provides high-level interface for audit operations with:
    - Automatic timestamp generation
    - Validation of required fields
    - Convenient query methods

    Example:
        >>> manager = AuditTrailManager()
        >>> await manager.record(
        ...     agent_id="qa-agent",
        ...     action="tool_execute",
        ...     details={"tool_name": "bash_command", "command": "ls -la"},
        ...     result="success",
        ...     user_id="user@example.com"
        ... )
        >>>
        >>> # Query all entries for agent
        >>> entries = await manager.query_by_agent("qa-agent")
        >>>
        >>> # Query failed operations
        >>> failures = await manager.query_by_result("failure")
    """

    def __init__(
        self,
        storage: AuditStorage | None = None,
        canonical_store: object | None = None,
    ):
        """
        Initialize audit trail manager.

        Args:
            storage: AuditStorage backend (defaults to FileAuditStorage)
            canonical_store: Optional canonical ``kailash.trust.audit_store``
                instance. When provided, all events are also forwarded to
                the canonical store for unified audit trail querying
                (SPEC-08 convergence).
        """
        self.storage = storage or FileAuditStorage()
        self._canonical_store = canonical_store
        logger.debug("AuditTrailManager initialized")

    async def record(
        self,
        agent_id: str,
        action: str,
        details: dict,
        result: AuditResult,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """
        Record audit entry.

        Automatically adds timestamp and validates required fields.

        Args:
            agent_id: Agent performing the action
            action: Action identifier (e.g., "tool_execute", "permission_grant")
            details: Action-specific details (must be JSON-serializable)
            result: Action result (success, failure, denied)
            user_id: User who triggered the action (optional)
            metadata: Additional metadata (optional)

        Example:
            >>> await manager.record(
            ...     agent_id="qa-agent",
            ...     action="tool_execute",
            ...     details={"tool_name": "bash", "command": "ls"},
            ...     result="success",
            ...     user_id="user@example.com",
            ...     metadata={"danger_level": "MODERATE"}
            ... )
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            action=action,
            details=details,
            result=result,
            user_id=user_id,
            metadata=metadata or {},
        )

        await self.storage.append(entry)

        # Forward to canonical audit store (SPEC-08 convergence)
        if self._canonical_store is not None:
            try:
                self._canonical_store.append_sync(
                    actor=agent_id,
                    action=action,
                    resource=f"kaizen.observability:{agent_id}",
                    details={"result": str(result), **details, **(metadata or {})},
                )
            except Exception as exc:
                # ``exc_info`` DROPPED, scrubbed detail added in its place --
                # sibling of the identical forward sink in
                # ``kaizen/security/audit.py``; see that site for the full
                # rationale. Both audit forwards are fixed in one change so the
                # pair cannot drift (security.md § Multi-Site Kwarg Plumbing).
                logger.warning(
                    "audit.canonical_forward_failed agent_id=%s action=%s "
                    "error=%s error_type=%s",
                    agent_id,
                    action,
                    scrub_remote_error(exc),
                    type(exc).__name__,
                )

        logger.info(
            f"Audit recorded: {agent_id} - {action} - {result}",
            extra={"agent_id": agent_id, "action": action, "result": result},
        )

    async def query_by_agent(self, agent_id: str) -> list[AuditEntry]:
        """
        Get all audit entries for an agent.

        Args:
            agent_id: Agent ID to query

        Returns:
            List of audit entries (sorted by timestamp)
        """
        return await self.storage.query(agent_id=agent_id)

    async def query_by_action(self, action: str) -> list[AuditEntry]:
        """
        Get all audit entries for a specific action.

        Args:
            action: Action type to query (e.g., "tool_execute")

        Returns:
            List of audit entries (sorted by timestamp)
        """
        return await self.storage.query(action=action)

    async def query_by_user(self, user_id: str) -> list[AuditEntry]:
        """
        Get all audit entries for a user.

        Args:
            user_id: User ID to query

        Returns:
            List of audit entries (sorted by timestamp)
        """
        return await self.storage.query(user_id=user_id)

    async def query_by_result(self, result: AuditResult) -> list[AuditEntry]:
        """
        Get all audit entries with specific result.

        Useful for finding failures or denied operations.

        Args:
            result: Result to query (success, failure, denied)

        Returns:
            List of audit entries (sorted by timestamp)

        Example:
            >>> failures = await manager.query_by_result("failure")
            >>> denied = await manager.query_by_result("denied")
        """
        return await self.storage.query(result=result)

    async def query_by_timerange(
        self, start_time: datetime, end_time: datetime
    ) -> list[AuditEntry]:
        """
        Get all audit entries within time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)

        Returns:
            List of audit entries (sorted by timestamp)

        Example:
            >>> from datetime import timedelta
            >>> now = datetime.now(timezone.utc)
            >>> last_hour = now - timedelta(hours=1)
            >>> entries = await manager.query_by_timerange(last_hour, now)
        """
        return await self.storage.query(start_time=start_time, end_time=end_time)

    async def query_all(self) -> list[AuditEntry]:
        """
        Get all audit entries (no filtering).

        WARNING: Can be slow for large audit logs.

        Returns:
            List of all audit entries (sorted by timestamp)
        """
        return await self.storage.query()


__all__ = [
    "AUDIT_APPEND_BUDGET_SECONDS",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_RETENTION_COUNT",
    "ROTATION_ACTION",
    "SEGMENT_DROPPED_ACTION",
    "STORAGE_AGENT_ID",
    "AuditIntegrityError",
    "AuditQueryResult",
    "AuditStorage",
    "AuditTrailManager",
    "AuditWriteError",
    "FileAuditStorage",
    "MalformedAuditLine",
]
