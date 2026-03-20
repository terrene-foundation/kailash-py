# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Runtime Credential Store for BYOK (Bring Your Own Key) workflows.

Provides a non-serializable, thread-safe credential store that separates
API keys and other secrets from serializable workflow configuration.
Credentials are registered before execution and resolved during execution.

See ADR-001 (workspaces/byok-hardening/02-plans/01-adr-credential-flow.md)
for the architectural decision behind this module.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "Credential",
    "CredentialStore",
    "get_credential_store",
]

# Fields that are considered sensitive and must not be serialized
SENSITIVE_KEYS: frozenset = frozenset(
    {
        "api_key",
        "api_secret",
        "base_url",
        "token",
        "password",
        "credential",
        "auth",
        "secret",
    }
)


@dataclass(frozen=True)
class Credential:
    """Immutable credential bundle for a single node execution."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def __repr__(self) -> str:
        """Redact credentials in repr to prevent leakage in logs/tracebacks."""
        return "Credential(api_key=***, base_url=***)"


class CredentialStore:
    """Thread-safe, non-serializable credential store for workflow execution.

    Credentials are registered before execution and resolved during execution.
    The store is request-scoped — cleared after each workflow run.

    Usage:
        store = get_credential_store()
        ref = store.register(api_key="sk-tenant-123", base_url="https://proxy.example.com")
        # ... later, during node execution:
        cred = store.resolve(ref)
        provider.chat(messages, api_key=cred.api_key, base_url=cred.base_url)
        # ... after execution:
        store.clear()
    """

    _SENSITIVE_KEYS: ClassVar[frozenset] = SENSITIVE_KEYS

    def __init__(self) -> None:
        self._store: Dict[str, Credential] = {}
        self._lock = threading.Lock()

    def register(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> str:
        """Register credentials and return a safe reference ID.

        The reference ID is safe to store in node_config and serialize.

        Args:
            api_key: API key for the LLM provider.
            base_url: Base URL override for the LLM provider.

        Returns:
            A credential reference string (e.g., "cred_a1b2c3d4e5f6").
        """
        ref_id = f"cred_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._store[ref_id] = Credential(api_key=api_key, base_url=base_url)
        logger.debug("Registered credential ref %s", ref_id)
        return ref_id

    def resolve(self, ref_id: str) -> Optional[Credential]:
        """Resolve a credential reference to actual credentials.

        Args:
            ref_id: The reference ID returned by register().

        Returns:
            The Credential object, or None if not found.
        """
        with self._lock:
            return self._store.get(ref_id)

    def clear(self, ref_id: Optional[str] = None) -> None:
        """Clear credentials after execution completes.

        Args:
            ref_id: If provided, clear only this credential.
                    If None, clear all credentials.
        """
        with self._lock:
            if ref_id:
                self._store.pop(ref_id, None)
                logger.debug("Cleared credential ref %s", ref_id)
            else:
                count = len(self._store)
                self._store.clear()
                if count > 0:
                    logger.debug("Cleared %d credentials from store", count)

    @classmethod
    def extract_sensitive(cls, config: Dict[str, Any]) -> tuple:
        """Split config into (safe_config, sensitive_values).

        Returns a config dict with sensitive keys removed,
        and a dict of the extracted sensitive values.

        Args:
            config: A node configuration dictionary.

        Returns:
            Tuple of (safe_config, sensitive_values).
        """
        safe: Dict[str, Any] = {}
        sensitive: Dict[str, Any] = {}
        for k, v in config.items():
            if k in cls._SENSITIVE_KEYS:
                sensitive[k] = v
            else:
                safe[k] = v
        return safe, sensitive

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:
        with self._lock:
            return f"CredentialStore({len(self._store)} credentials)"


# Module-level singleton
_credential_store = CredentialStore()


def get_credential_store() -> CredentialStore:
    """Get the global credential store singleton."""
    return _credential_store
