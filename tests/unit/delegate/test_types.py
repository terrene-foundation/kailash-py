# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 tests for the canonical Delegate type substrate (S2 of #1035).

Mirrors invariants surfaced in the kailash-rs reference extraction report at
``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-
extraction.md`` §1 (kailash-delegate-types).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from kailash.delegate.types import (
    GenesisRecord,
    Identity,
    LifecycleError,
    LifecycleState,
    PrincipalDirectory,
    Role,
)
from kailash.trust._json import canonical_json_dumps

# ---------------------------------------------------------------------------
# LifecycleState — D3 linear chain
# ---------------------------------------------------------------------------


def test_lifecycle_state_chain_exhaustive() -> None:
    """The 6-state chain mirrors rs ``LifecycleState`` exactly."""
    members = list(LifecycleState)
    assert len(members) == 6
    assert [m.value for m in members] == [
        "proposed",
        "instantiated",
        "posture_graded",
        "active",
        "retired",
        "archived",
    ]


def test_lifecycle_state_wire_format_is_lowercase_string() -> None:
    """Cross-SDK canonical wire format: lowercase string value."""
    assert LifecycleState.POSTURE_GRADED.value == "posture_graded"
    # str-backed Enum allows direct comparison with string literals so wire
    # payloads round-trip without explicit coercion.
    assert LifecycleState.ACTIVE == "active"


# ---------------------------------------------------------------------------
# LifecycleError — typed exception with named-successor message
# ---------------------------------------------------------------------------


def test_lifecycle_error_typed() -> None:
    """``LifecycleError`` is an Exception with a useful named-successor msg."""
    err = LifecycleError(
        from_state=LifecycleState.PROPOSED,
        to_state=LifecycleState.ACTIVE,
        expected=LifecycleState.INSTANTIATED,
    )
    assert isinstance(err, Exception)
    msg = str(err)
    assert "proposed" in msg
    assert "active" in msg
    assert "instantiated" in msg


def test_lifecycle_error_without_expected_successor() -> None:
    """When the from-state has no legal successor, message says so."""
    err = LifecycleError(
        from_state=LifecycleState.ARCHIVED,
        to_state=LifecycleState.ACTIVE,
    )
    assert "no legal successor" in str(err)


# ---------------------------------------------------------------------------
# Identity — frozen, slots, post-init guards
# ---------------------------------------------------------------------------


def test_identity_frozen() -> None:
    ident = Identity(tenant_id="t1", principal_id="p1")
    with pytest.raises(FrozenInstanceError):
        ident.tenant_id = "t2"  # type: ignore[misc]


def test_identity_post_init_rejects_empty_tenant_id() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        Identity(tenant_id="", principal_id="p")


def test_identity_post_init_rejects_empty_principal_id() -> None:
    with pytest.raises(ValueError, match="principal_id"):
        Identity(tenant_id="t", principal_id="")


def test_identity_display_name_optional() -> None:
    ident = Identity(tenant_id="t1", principal_id="p1")
    assert ident.display_name is None
    named = Identity(tenant_id="t1", principal_id="p1", display_name="Alice")
    assert named.display_name == "Alice"


# ---------------------------------------------------------------------------
# Role — frozen, scope is frozenset, post-init guards
# ---------------------------------------------------------------------------


def test_role_frozen_scope_is_frozenset() -> None:
    """``Role.scope`` is a ``frozenset`` (immutable per rs convention)."""
    role = Role(role_id="r1", tenant_id="t1", scope={"read", "write"})
    assert isinstance(role.scope, frozenset)
    assert role.scope == frozenset({"read", "write"})


def test_role_scope_coerces_list_to_frozenset() -> None:
    role = Role(role_id="r1", tenant_id="t1", scope=["a", "b", "a"])  # type: ignore[arg-type]
    assert role.scope == frozenset({"a", "b"})


def test_role_post_init_rejects_empty_ids() -> None:
    with pytest.raises(ValueError, match="role_id"):
        Role(role_id="", tenant_id="t1")
    with pytest.raises(ValueError, match="tenant_id"):
        Role(role_id="r1", tenant_id="")


# ---------------------------------------------------------------------------
# GenesisRecord — frozen, post-init guards, canonical-dict byte stability
# ---------------------------------------------------------------------------


def _make_genesis(**overrides: object) -> GenesisRecord:
    defaults: dict[str, object] = {
        "genesis_id": "g-0001",
        "created_at": datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        "principal_directory_anchor": "a" * 64,
        "initial_envelope_hash": "b" * 64,
        "delegation_proof": "c" * 128,
        "signature": "d" * 128,
        "spec_version": "1",
        "capabilities": ("read", "write"),
    }
    defaults.update(overrides)
    return GenesisRecord(**defaults)  # type: ignore[arg-type]


def test_genesis_record_frozen() -> None:
    g = _make_genesis()
    with pytest.raises(FrozenInstanceError):
        g.genesis_id = "g-9999"  # type: ignore[misc]


def test_genesis_record_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _make_genesis(created_at=datetime(2026, 5, 21, 12, 0, 0))


def test_genesis_record_rejects_empty_required_fields() -> None:
    for field_name in (
        "genesis_id",
        "principal_directory_anchor",
        "initial_envelope_hash",
        "delegation_proof",
        "signature",
        "spec_version",
    ):
        with pytest.raises(ValueError, match=field_name):
            _make_genesis(**{field_name: ""})


def test_genesis_record_to_canonical_dict_byte_canonical() -> None:
    """``to_canonical_dict()`` → ``canonical_json_dumps`` is deterministic.

    Two calls with the same input produce byte-identical JSON, which is the
    cross-SDK parity contract for rs ↔ py reference fixtures.
    """
    g1 = _make_genesis()
    g2 = _make_genesis()
    json1 = canonical_json_dumps(g1.to_canonical_dict())
    json2 = canonical_json_dumps(g2.to_canonical_dict())
    assert json1 == json2
    # The canonical encoder sorts keys; the resulting string contains every
    # named field so cross-SDK parity is grep-able post-incident.
    for field_name in (
        "genesis_id",
        "created_at",
        "principal_directory_anchor",
        "initial_envelope_hash",
        "delegation_proof",
        "signature",
        "spec_version",
        "capabilities",
    ):
        assert f'"{field_name}"' in json1


def test_genesis_record_capabilities_coerced_to_tuple() -> None:
    """Iterables passed to ``capabilities`` are coerced to a tuple."""
    g = _make_genesis(capabilities=["read", "write"])
    assert g.capabilities == ("read", "write")


# ---------------------------------------------------------------------------
# PrincipalDirectory — frozen, deterministic lookup, duplicate rejection
# ---------------------------------------------------------------------------


def test_principal_directory_resolve_hit_miss() -> None:
    alice = Identity(tenant_id="t1", principal_id="alice")
    bob = Identity(tenant_id="t1", principal_id="bob")
    directory = PrincipalDirectory(identities=(alice, bob))
    assert directory.resolve("alice") == alice
    assert directory.resolve("bob") == bob
    assert directory.resolve("eve") is None


def test_principal_directory_rejects_duplicate_identity() -> None:
    alice1 = Identity(tenant_id="t1", principal_id="alice")
    alice2 = Identity(tenant_id="t1", principal_id="alice", display_name="A")
    with pytest.raises(ValueError, match="duplicate identity"):
        PrincipalDirectory(identities=(alice1, alice2))


def test_principal_directory_frozen() -> None:
    directory = PrincipalDirectory()
    with pytest.raises(FrozenInstanceError):
        directory.identities = ()  # type: ignore[misc]
