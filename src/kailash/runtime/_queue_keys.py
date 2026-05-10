"""Canonical Redis-list-key helpers for distributed task queues.

Producer (``DistributedRuntime``) and consumer (``Worker``) MUST share a
single source of truth for queue-name → Redis-list-key translation, so a
producer that enqueues for queue ``"fast"`` and a worker dequeuing from
``Worker(queues={"fast": 1})`` resolve to byte-identical Redis keys.

Same structural defense as ``kailash.utils.url_credentials`` (one helper
module, both directions): drift between two open-coded copies silently
strands tasks on a queue no worker reads.

Issue #911 Shard 1.
"""

from __future__ import annotations

import re

# Base Redis list key for queued tasks. The "default" queue MUST resolve
# to this exact byte string (NOT ``"kailash:tasks:pending:default"``) so
# existing single-queue deployments do not orphan in-flight tasks on
# their first deploy of the multi-queue SDK. Same back-compat-window
# semantics as a ``zero-tolerance.md`` Rule 6a public-API rename.
_QUEUE_KEY_BASE = "kailash:tasks:pending"
_PROCESSING_KEY_BASE = "kailash:tasks:processing"

DEFAULT_QUEUE_NAME = "default"

_QUEUE_NAME_MAX_LEN = 64
_QUEUE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")


def validate_queue_name(name: str) -> None:
    """Raise ``ValueError`` if ``name`` is not a safe queue name.

    Allowed: 1–64 chars, ASCII letters / digits / hyphen / underscore.
    Rejected: empty, > 64 chars, control chars, colons (Redis key
    separator), slashes, whitespace, null bytes — anything that could
    break the Redis-key shape or smuggle a different namespace prefix.

    Issue #911 failure-point #8.
    """
    if not isinstance(name, str):
        raise ValueError(f"queue name must be str, got {type(name).__name__}")
    if not name:
        raise ValueError("queue name must not be empty")
    if len(name) > _QUEUE_NAME_MAX_LEN:
        raise ValueError(
            f"queue name too long: {len(name)} > {_QUEUE_NAME_MAX_LEN} chars"
        )
    if not _QUEUE_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "queue name must match [A-Za-z0-9_-]+ "
            "(no colons, slashes, whitespace, control chars, or null bytes); "
            f"got {name!r}"
        )


def make_queue_key(name: str = DEFAULT_QUEUE_NAME) -> str:
    """Return the canonical Redis list key for ``name``.

    The ``"default"`` queue maps to the legacy key ``"kailash:tasks:pending"``
    (NO suffix) — load-bearing back-compat with single-queue deployments
    that already have tasks enqueued under that exact byte string.

    Non-default queues map to ``"kailash:tasks:pending:<name>"``.

    Issue #911 failure-point #1, #2 (default-queue back-compat).
    """
    validate_queue_name(name)
    if name == DEFAULT_QUEUE_NAME:
        return _QUEUE_KEY_BASE
    return f"{_QUEUE_KEY_BASE}:{name}"


def make_processing_key(name: str = DEFAULT_QUEUE_NAME) -> str:
    """Return the canonical Redis processing-list key for ``name``.

    Mirrors :func:`make_queue_key` for the in-flight side of the BLMOVE
    pattern. Without per-queue processing keys, every named queue would
    share the legacy ``"kailash:tasks:processing"`` list — defeating
    per-queue stale-recovery (one queue's stuck tasks would re-queue
    everywhere) and making per-queue processing-count observability
    return identical aggregates for every queue.

    The ``"default"`` queue maps to the legacy key
    ``"kailash:tasks:processing"`` (NO suffix) — load-bearing back-compat
    with single-queue deployments that already have in-flight tasks
    under that exact byte string.

    Non-default queues map to ``"kailash:tasks:processing:<name>"``.

    Issue #911 Shard 2 followup — R1-001/R1-002 redteam findings.
    """
    validate_queue_name(name)
    if name == DEFAULT_QUEUE_NAME:
        return _PROCESSING_KEY_BASE
    return f"{_PROCESSING_KEY_BASE}:{name}"


__all__ = [
    "DEFAULT_QUEUE_NAME",
    "make_processing_key",
    "make_queue_key",
    "validate_queue_name",
]
