# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Filesystem-based TrustStore implementation.

Provides a persistent implementation that stores trust chains as JSON files
on the local filesystem. Supports soft-delete, atomic writes, and filtering.

Features:
- Each chain stored as {agent_id}.json
- Soft-delete support (marks inactive rather than removing)
- Thread-safe atomic writes via write-to-temp-then-rename
- Filtering by authority_id and active_only
- Pagination support (limit/offset)
- Configurable directory (default: ~/.eatp/chains/)
"""

import fcntl
import hashlib
import json
import logging
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from eatp.chain import TrustLineageChain
from eatp.exceptions import TrustChainNotFoundError
from eatp.store import TrustStore

logger = logging.getLogger(__name__)


@contextmanager
def file_lock(path: str, exclusive: bool = True) -> Generator[None, None, None]:
    """
    Cross-process file lock using ``fcntl.flock``.

    Acquires a file lock on a ``.lock`` sidecar file next to the target
    path. The lock is automatically released when the context exits or
    the process crashes (``flock`` releases on file descriptor close).

    Args:
        path: Path to the file being protected. A ``.lock`` sidecar is
            created next to it.
        exclusive: If True (default), acquire an exclusive (write) lock.
            If False, acquire a shared (read) lock.

    Yields:
        None — the lock is held for the duration of the context.

    Note:
        Uses ``fcntl.flock`` which is Unix-only. On platforms without
        ``fcntl`` (e.g. Windows), this will raise ``ImportError`` at
        module load time.
    """
    lock_path = f"{path}.lock"
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd.fileno(), mode)
        yield
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
        try:
            os.unlink(lock_path)
        except OSError:
            pass  # Another process may have already removed it


def validate_id(id_value: str, id_name: str = "id") -> str:
    """
    Validate an identifier to prevent path traversal attacks.

    Rejects IDs that could be used for directory traversal, null byte
    injection, or absolute path manipulation. IDs with special characters
    (colons, dots) are allowed here — ``_safe_filename()`` handles the
    filesystem-safe encoding separately.

    Args:
        id_value: The raw identifier to validate.
        id_name: Human-readable name for error messages (default: "id").

    Returns:
        The stripped, validated identifier.

    Raises:
        ValueError: If the ID is empty, contains null bytes, or contains
            path traversal components.
    """
    stripped = id_value.strip()
    if not stripped:
        raise ValueError(f"Invalid {id_name}: must not be empty")

    if len(stripped) > 1024:
        raise ValueError(
            f"Invalid {id_name}: exceeds maximum length of 1024 characters "
            f"(got {len(stripped)})"
        )

    if "\x00" in stripped:
        raise ValueError(
            f"Invalid {id_name}: must not contain null bytes, got: {id_value!r}"
        )

    # Check for path traversal components by splitting on path separators
    parts = stripped.replace("\\", "/").split("/")
    for part in parts:
        if part in (".", ".."):
            raise ValueError(
                f"Invalid {id_name}: path traversal detected in {id_value!r}"
            )

    # Reject absolute paths
    if stripped.startswith("/") or (len(stripped) >= 2 and stripped[1] == ":"):
        raise ValueError(f"Invalid {id_name}: path traversal detected in {id_value!r}")

    return stripped


def _safe_filename(agent_id: str) -> str:
    """
    Convert an agent_id into a safe filesystem name.

    Uses a SHA-256 hex digest when the agent_id contains characters that are
    unsafe for filenames (slashes, colons, NUL, etc.), while preserving
    human-readable names for simple identifiers.

    Args:
        agent_id: The raw agent identifier.

    Returns:
        A string safe for use as a filename (without extension).
    """
    unsafe_chars = set('/\\:*?"<>|\x00')
    if any(ch in unsafe_chars for ch in agent_id):
        return hashlib.sha256(agent_id.encode("utf-8")).hexdigest()
    return agent_id


class FilesystemStore(TrustStore):
    """
    Filesystem-backed trust store for persistent local storage.

    Stores each TrustLineageChain as a JSON file named ``{agent_id}.json``
    inside a configurable base directory (default ``~/.eatp/chains/``).

    The on-disk format is a JSON envelope::

        {
            "agent_id": "<original agent_id>",
            "active": true,
            "stored_at": "<ISO-8601>",
            "updated_at": null,
            "deleted_at": null,
            "expires_at": null,
            "chain": { ... TrustLineageChain.to_dict() with signature ... }
        }

    Thread safety is achieved through a reentrant lock and atomic
    write-to-temp-then-rename operations, so readers never see
    partially-written files.

    Example::

        store = FilesystemStore("/var/lib/eatp/chains")
        await store.initialize()
        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize the filesystem trust store.

        Args:
            base_dir: Directory where chain JSON files are stored.
                      Defaults to ``~/.eatp/chains/``.
        """
        if base_dir is None:
            base_dir = os.path.join(os.path.expanduser("~"), ".eatp", "chains")
        self._base_dir = Path(base_dir)
        self._initialized = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_initialized(self) -> None:
        """Raise RuntimeError if the store has not been initialized."""
        if not self._initialized:
            raise RuntimeError(
                "FilesystemStore is not initialized. "
                "Call await store.initialize() before performing operations."
            )

    def _chain_path(self, agent_id: str) -> Path:
        """Return the filesystem path for a given agent_id.

        Validates the agent_id against path traversal before computing
        the filesystem path.
        """
        validated = validate_id(agent_id, id_name="agent_id")
        filename = _safe_filename(validated) + ".json"
        return self._base_dir / filename

    def _serialize_chain(self, chain: TrustLineageChain) -> Dict[str, Any]:
        """
        Serialize a TrustLineageChain to a dict that preserves all fields.

        The standard ``to_dict()`` omits some fields (e.g., genesis.signature,
        capability signatures). This method uses ``to_dict()`` as a base and
        patches in the missing fields so round-trip fidelity is maintained.

        Args:
            chain: The chain to serialize.

        Returns:
            A dictionary suitable for JSON encoding.
        """
        data = chain.to_dict()

        # Patch in genesis.signature (not included by to_dict)
        data["genesis"]["signature"] = chain.genesis.signature

        # Patch in capability signatures (not included by to_dict)
        for i, cap in enumerate(chain.capabilities):
            data["capabilities"][i]["signature"] = cap.signature

        # Patch in delegation signatures (not included by to_dict for inline dicts)
        for i, deleg in enumerate(chain.delegations):
            data["delegations"][i]["signature"] = deleg.signature

        return data

    def _write_envelope(
        self,
        agent_id: str,
        envelope: Dict[str, Any],
    ) -> None:
        """
        Atomically write an envelope to disk.

        Writes to a temporary file in the same directory and then renames
        to the target path. On POSIX systems ``os.replace`` is atomic.

        Args:
            agent_id: The agent whose file is being written.
            envelope: The full JSON envelope to write.
        """
        target = self._chain_path(agent_id)
        content = json.dumps(envelope, indent=2, sort_keys=False, default=str)

        # Write to a temp file in the same directory so rename is atomic
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._base_dir), suffix=".tmp", prefix=".chain_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(target))
        except BaseException:
            # Clean up the temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _read_envelope(self, agent_id: str) -> Dict[str, Any]:
        """
        Read and parse the JSON envelope for a given agent_id.

        Args:
            agent_id: The agent whose file to read.

        Returns:
            Parsed JSON envelope dictionary.

        Raises:
            TrustChainNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is corrupted.
        """
        path = self._chain_path(agent_id)
        if not path.exists():
            raise TrustChainNotFoundError(agent_id)
        text = path.read_text(encoding="utf-8")
        return json.loads(text)

    def _deserialize_chain(self, chain_data: Dict[str, Any]) -> TrustLineageChain:
        """
        Deserialize a chain dict back to a TrustLineageChain.

        Uses ``TrustLineageChain.from_dict()`` which handles all nested
        deserialization including enums, datetimes, and constraint envelopes.

        Args:
            chain_data: The ``chain`` sub-dict from the envelope.

        Returns:
            A fully-reconstructed TrustLineageChain.
        """
        return TrustLineageChain.from_dict(chain_data)

    def _iter_envelopes(self) -> List[Dict[str, Any]]:
        """
        Iterate over all valid JSON envelope files in the base directory.

        Skips non-JSON files, temp files, and files that fail to parse.

        Returns:
            List of (envelope_dict) for each valid chain file.
        """
        envelopes: List[Dict[str, Any]] = []
        if not self._base_dir.exists():
            return envelopes

        for path in sorted(self._base_dir.iterdir()):
            if not path.is_file():
                continue
            if not path.name.endswith(".json"):
                continue
            if path.name.startswith("."):
                continue
            try:
                text = path.read_text(encoding="utf-8")
                envelope = json.loads(text)
                envelopes.append(envelope)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Skipping corrupted chain file %s: %s",
                    path,
                    exc,
                )
        return envelopes

    # ------------------------------------------------------------------
    # TrustStore ABC implementation
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Initialize the filesystem store.

        Creates the base directory (and all parent directories) if they
        do not already exist. This method is idempotent.
        """
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info("FilesystemStore initialized at %s", self._base_dir)

    async def store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Store a trust lineage chain as a JSON file.

        Creates or overwrites ``{agent_id}.json`` in the base directory.

        Args:
            chain: The TrustLineageChain to store.
            expires_at: Optional expiration datetime for the stored entry.

        Returns:
            The agent_id of the stored chain.
        """
        self._require_initialized()
        agent_id = chain.genesis.agent_id

        envelope = {
            "agent_id": agent_id,
            "active": True,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
            "deleted_at": None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "chain": self._serialize_chain(chain),
        }

        target = self._chain_path(agent_id)
        with file_lock(str(target)):
            with self._lock:
                self._write_envelope(agent_id, envelope)

        logger.debug("Stored chain for agent %s", agent_id)
        return agent_id

    async def get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """
        Retrieve a trust lineage chain by agent_id.

        Args:
            agent_id: The agent ID to retrieve.
            include_inactive: If True, return soft-deleted chains as well.

        Returns:
            The TrustLineageChain for the agent.

        Raises:
            TrustChainNotFoundError: If the chain file does not exist or
                the chain is inactive and include_inactive is False.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()

        target = self._chain_path(agent_id)
        with file_lock(str(target), exclusive=False):
            with self._lock:
                envelope = self._read_envelope(agent_id)

        if not envelope.get("active", True) and not include_inactive:
            raise TrustChainNotFoundError(agent_id)

        return self._deserialize_chain(envelope["chain"])

    async def update_chain(
        self,
        agent_id: str,
        chain: TrustLineageChain,
    ) -> None:
        """
        Update an existing trust lineage chain.

        Preserves the original ``stored_at`` timestamp and ``active`` flag.

        Args:
            agent_id: The agent ID to update.
            chain: The new TrustLineageChain data.

        Raises:
            TrustChainNotFoundError: If the chain file does not exist.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()

        target = self._chain_path(agent_id)
        with file_lock(str(target)):
            with self._lock:
                # Read existing envelope (raises TrustChainNotFoundError if missing)
                existing = self._read_envelope(agent_id)

                existing["chain"] = self._serialize_chain(chain)
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()

                self._write_envelope(agent_id, existing)

        logger.debug("Updated chain for agent %s", agent_id)

    async def delete_chain(
        self,
        agent_id: str,
        soft_delete: bool = True,
    ) -> None:
        """
        Delete a trust lineage chain.

        Soft delete marks the chain as inactive in the JSON file.
        Hard delete removes the file from disk entirely.

        Args:
            agent_id: The agent ID to delete.
            soft_delete: If True, mark inactive; if False, remove the file.

        Raises:
            TrustChainNotFoundError: If the chain file does not exist.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()

        target = self._chain_path(agent_id)
        with file_lock(str(target)):
            with self._lock:
                if soft_delete:
                    envelope = self._read_envelope(agent_id)
                    envelope["active"] = False
                    envelope["deleted_at"] = datetime.now(timezone.utc).isoformat()
                    self._write_envelope(agent_id, envelope)
                    logger.debug("Soft-deleted chain for agent %s", agent_id)
                else:
                    path = self._chain_path(agent_id)
                    if not path.exists():
                        raise TrustChainNotFoundError(agent_id)
                    path.unlink()
                    logger.debug("Hard-deleted chain for agent %s", agent_id)

    async def list_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TrustLineageChain]:
        """
        List trust lineage chains with filtering and pagination.

        Reads all JSON files in the base directory, applies filters,
        and returns the requested page.

        Args:
            authority_id: Filter by authority ID (optional).
            active_only: If True, exclude soft-deleted chains.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of TrustLineageChain objects.

        Raises:
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()

        with self._lock:
            envelopes = self._iter_envelopes()

        # Filter by active status
        if active_only:
            envelopes = [e for e in envelopes if e.get("active", True)]

        # Deserialize chains
        chains = [self._deserialize_chain(e["chain"]) for e in envelopes]

        # Filter by authority_id
        if authority_id is not None:
            chains = [c for c in chains if c.genesis.authority_id == authority_id]

        # Apply pagination
        return chains[offset : offset + limit]

    async def count_chains(
        self,
        authority_id: Optional[str] = None,
        active_only: bool = True,
    ) -> int:
        """
        Count trust lineage chains with filtering.

        Args:
            authority_id: Filter by authority ID (optional).
            active_only: If True, exclude soft-deleted chains.

        Returns:
            Number of matching chains.

        Raises:
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()

        with self._lock:
            envelopes = self._iter_envelopes()

        # Filter by active status
        if active_only:
            envelopes = [e for e in envelopes if e.get("active", True)]

        if authority_id is not None:
            count = 0
            for e in envelopes:
                chain = self._deserialize_chain(e["chain"])
                if chain.genesis.authority_id == authority_id:
                    count += 1
            return count

        return len(envelopes)

    async def get_chains_missing_reasoning(self) -> List[str]:
        """Return agent IDs whose chains have delegations or audit anchors missing reasoning traces."""
        all_chains = await self.list_chains(limit=100000)
        missing = []
        for chain in all_chains:
            has_items = False
            has_missing = False
            for delegation in chain.delegations:
                has_items = True
                if delegation.reasoning_trace is None:
                    has_missing = True
                    break
            if not has_missing:
                for anchor in chain.audit_anchors:
                    has_items = True
                    if anchor.reasoning_trace is None:
                        has_missing = True
                        break
            if has_items and has_missing:
                missing.append(chain.genesis.agent_id)
        return missing

    async def close(self) -> None:
        """
        Close and cleanup resources.

        Resets the initialized flag. The filesystem does not require
        connection cleanup, so this is effectively a state reset.
        """
        self._initialized = False
        logger.info("FilesystemStore closed")


__all__ = [
    "FilesystemStore",
    "file_lock",
    "validate_id",
]
