# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""In-worktree Verifier stub for Shard X tests pending Shard Y merge.

Shard Y owns the canonical ``kailash.delegate.verifier`` module
(:class:`Verifier` Protocol + :class:`NullVerifier` fail-closed default).
Shard X runs in parallel and cannot see Shard Y's branch from this
worktree, so this stub provides the minimal Protocol-satisfying contract
Shard X needs to exercise verifier wiring in :class:`DispatchSurface`.

After Shard X + Shard Y + Shard Z merge, integration callers replace
this stub with the real :class:`kailash.delegate.verifier.Verifier` and
:class:`kailash.delegate.verifier.NullVerifier` imports. The stub is
test-only and lives under ``tests/unit/delegate/`` (NOT
``src/kailash/delegate/``) so the production surface never depends on it.

Per ``rules/testing.md`` § "Protocol-Satisfying Deterministic Adapters",
these are NOT mocks — they are real Protocol-satisfying classes with
deterministic behavior. AcceptAllVerifier returns True for any input
(success-path tests); RejectAllVerifier returns False (forgery-path tests);
RaisingVerifier raises (error-path tests).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VerifierStub(Protocol):
    """In-worktree mirror of Shard Y's Verifier Protocol."""

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool:  # pragma: no cover (Protocol)
        ...


class AcceptAllVerifierStub:
    """Permissive verifier — returns True for every input (success-path tests)."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, bytes, str]] = []

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool:
        self.calls.append((message, signature, signer_delegate_id))
        return True


class RejectAllVerifierStub:
    """Fail-closed verifier — returns False for every input (forgery-path tests).

    Mirrors :class:`kailash.delegate.verifier.NullVerifier` semantics.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, bytes, str]] = []

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool:
        self.calls.append((message, signature, signer_delegate_id))
        return False


class RaisingVerifierStub:
    """Verifier that raises — tests the dispatch-time error-handling path."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or RuntimeError("verifier-stub-exception")

    def verify(
        self,
        message: bytes,
        signature: bytes,
        signer_delegate_id: str,
    ) -> bool:
        raise self._exc
