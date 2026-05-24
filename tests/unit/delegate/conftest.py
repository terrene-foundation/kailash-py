# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 conftest for ``kailash.delegate`` tests.

Patches the default :class:`AuditChainEngine` verifier from the
fail-closed :class:`NullVerifier` (production default) to the
deterministic :class:`AcceptAnyVerifier` (Tier-1 test default) so that
legacy unit tests asserting chain-linkage / monotonicity / sequencing
invariants do not need to construct an Ed25519 keypair to assert those
properties.

Per ``testing.md`` § "Tier-1 Conftest Stub for Newly-Side-Effecting
Internal Methods", this is the canonical pattern when a previously-
deterministic surface (the shape-only hex check) becomes side-effecting
(the real Ed25519 verify call) WITHOUT changing the public contract
(emit_event still accepts a 128-hex-char signature). The conftest scope
guarantees the stub does NOT leak to Tier-2 (``tests/integration/``)
or Tier-3 (``tests/e2e/``); siblings receive the production NullVerifier
default and MUST wire a real Ed25519Verifier explicitly.

Tests exercising the cryptographic contract itself — verifier behavior,
signature-tampering rejection, fail-closed posture under wrong signer —
MUST construct an explicit :class:`Ed25519Verifier` AND explicitly opt
out of this autouse fixture by passing the real verifier to the engine
under test. The fixture only affects engines constructed via the
``AuditChainEngine(chain=...)`` default — explicit ``verifier=...``
arguments take precedence.
"""

from __future__ import annotations

import pytest

from tests.unit.delegate._verifier_helpers import AcceptAnyVerifier


@pytest.fixture(autouse=True)
def _stub_audit_engine_default_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default the AuditChainEngine verifier to AcceptAnyVerifier in Tier-1.

    Per the Tier-1 conftest-stub pattern: patches the production
    fail-closed default (NullVerifier) to a deterministic-accept double
    so legacy chain-linkage tests assert chain properties, not crypto
    properties. The cryptographic gate is exercised by dedicated tests
    in ``test_verifier.py`` + Tier-2 wiring tests.
    """
    import kailash.delegate.audit as audit_mod

    monkeypatch.setattr(audit_mod, "NullVerifier", AcceptAnyVerifier)
