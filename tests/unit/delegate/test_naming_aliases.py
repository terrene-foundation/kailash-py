"""Verify #1035 acceptance-gate naming aliases.

Per /redteam Round 1 CRITICAL-1 disposition: the shipped class names
(DelegateRuntime, DelegateConstraintEnvelope, DelegateGenesisRecord,
Posture, AuditChainEngine) are deliberate disambiguation per the
``kailash.delegate`` module docstring (NOT
``kaizen_agents.delegate.Delegate`` LLM facade).

The #1035 issue body specifies an import line using the unprefixed names:

    from kailash.delegate import (
        Delegate, ConstraintEnvelope, PrincipalDirectory,
        GenesisRecord, PostureState, AuditChain, Connector,
    )

These tests lock in BOTH the import-line success AND the is-identity
relationship between the unprefixed aliases and their canonical
prefixed classes.
"""

from __future__ import annotations


def test_1035_issue_body_import_line_works() -> None:
    """The literal #1035 issue body import line MUST succeed."""
    from kailash.delegate import (
        AuditChain,
        Connector,
        ConstraintEnvelope,
        Delegate,
        GenesisRecord,
        PostureState,
        PrincipalDirectory,
    )

    assert Delegate is not None
    assert ConstraintEnvelope is not None
    assert PrincipalDirectory is not None
    assert GenesisRecord is not None
    assert PostureState is not None
    assert AuditChain is not None
    assert Connector is not None


def test_aliases_resolve_to_canonical_classes() -> None:
    """Aliases MUST be the same class object (is-identity), not copies."""
    from kailash.delegate import (
        AuditChain,
        AuditChainEngine,
        ConstraintEnvelope,
        Delegate,
        DelegateConstraintEnvelope,
        DelegateGenesisRecord,
        DelegateRuntime,
        GenesisRecord,
        Posture,
        PostureState,
    )

    assert Delegate is DelegateRuntime
    assert ConstraintEnvelope is DelegateConstraintEnvelope
    assert GenesisRecord is DelegateGenesisRecord
    assert PostureState is Posture
    assert AuditChain is AuditChainEngine


def test_aliases_in_all() -> None:
    """All 5 aliases MUST be in __all__ (per orphan-detection.md Rule 6)."""
    import kailash.delegate as pkg

    for alias in (
        "Delegate",
        "ConstraintEnvelope",
        "GenesisRecord",
        "PostureState",
        "AuditChain",
    ):
        assert alias in pkg.__all__, f"{alias} missing from __all__"
