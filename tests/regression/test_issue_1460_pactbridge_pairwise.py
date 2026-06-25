# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression: PactBridge is strictly pairwise; bridge_type is a descriptive
``str``, not a ``BridgeType`` enum (issue #1460, cross-SDK twin of
``terrene-foundation/kailash-rs#1409``).

Issue #1460 clarified the docs that a "scoped" bridge is role-PAIRWISE, not an
N-party participant group. Per ``cross-sdk-inspection.md`` Rule 3a (structural
API-divergence disposition), these structural-invariant tests pin the contract
the doc clarification now asserts so a future refactor toward the sibling SDK's
shape -- an N-party participant list, OR a ``BridgeType`` enum -- fails loudly
and forces a docstring + ``specs/pact-envelopes.md`` §6.6 + cross-SDK re-audit.

This is a documentation-clarity issue at a partially-divergent surface: the
``BridgeType`` enum named in the issue's precondition does NOT exist on
kailash-py (``bridge_type`` is a plain ``str``), so the only durable guard is
the structural invariant, not a behavioral repro.
"""

from __future__ import annotations

import dataclasses

import pytest

import kailash.trust.pact.access as access_mod
from kailash.trust.pact.access import PactBridge


@pytest.mark.regression
def test_issue_1460_pactbridge_has_exactly_two_role_endpoints() -> None:
    """PactBridge connects exactly two roles -- ``role_a_address`` +
    ``role_b_address`` -- with no N-party participant-list field."""
    field_names = {f.name for f in dataclasses.fields(PactBridge)}
    assert "role_a_address" in field_names
    assert "role_b_address" in field_names

    # No participant-list / N-party-shaped field: a bridge is strictly pairwise.
    nparty_markers = ("participant", "member", "roles", "addresses", "endpoints")
    nparty_fields = sorted(
        n for n in field_names if any(m in n.lower() for m in nparty_markers)
    )
    assert nparty_fields == [], (
        f"PactBridge grew an N-party-shaped field {nparty_fields}; bridges are "
        f"strictly pairwise (issue #1460). If multi-party support is intended, "
        f"re-audit the PactBridge docstring + specs/pact-envelopes.md §6.6 + "
        f"cross-SDK parity with kailash-rs#1409 before adding it."
    )


@pytest.mark.regression
def test_issue_1460_bridge_type_is_descriptive_str_not_enum() -> None:
    """``bridge_type`` is a plain ``str`` on kailash-py (no ``BridgeType``
    enum) -- the documented cross-SDK divergence from kailash-rs's enum."""
    bridge_type_field = {f.name: f for f in dataclasses.fields(PactBridge)}[
        "bridge_type"
    ]
    # ``from __future__ import annotations`` makes the annotation a string;
    # accept both the str type and the "str" forward-ref for robustness.
    assert bridge_type_field.type in (str, "str"), (
        f"bridge_type annotation drifted to {bridge_type_field.type!r}; "
        f"kailash-py models it as a descriptive str (issue #1460)."
    )

    # No BridgeType enum is exported from the access module. The Rust SDK
    # exposes a BridgeType enum; kailash-py deliberately uses a str field, and
    # issue #1460's precondition ("if kailash-py exposes a BridgeType enum")
    # resolved to N/A precisely because none exists.
    assert not hasattr(access_mod, "BridgeType"), (
        "A BridgeType enum appeared on kailash-py's pact.access module; issue "
        "#1460's no-enum precondition no longer holds -- re-audit cross-SDK "
        "parity with kailash-rs#1409 and the PactBridge docstring."
    )
