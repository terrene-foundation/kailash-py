# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration conftest for ``kailash.delegate`` tests.

Wires a Protocol-Satisfying Deterministic Adapter
(:class:`AcceptAnyVerifier`) as the default
:class:`~kailash.delegate.audit.AuditChainEngine` verifier for Tier-2
wiring tests that assert chain-linkage / cascade / dispatch composition
properties — NOT the cryptographic gate itself.

Per ``testing.md`` § "3-Tier Testing" → "Protocol Adapters": a class
satisfying a ``typing.Protocol`` at runtime with deterministic output
is NOT a mock. The verifier under test is exercised end-to-end against
a real Ed25519 keypair in the dedicated
:mod:`tests.integration.delegate.test_signature_verification_wiring`
suite, which constructs an explicit
:class:`kailash.delegate.verifier.Ed25519Verifier` and asserts
fail-closed behavior under tampered signatures + unknown signers.

This split keeps the Tier-2 contract clean:

- Wiring tests (cascade composition, dispatch path, runtime spine) use
  the deterministic adapter so they assert wiring properties, not
  crypto properties.
- The dedicated wiring test for the verifier exercises the real
  cryptographic gate against real Ed25519 vectors.

Without the adapter, every wiring test would need to construct an
Ed25519 keypair + directory + signer triple — ceremony that obscures
the property under test (wiring) with crypto setup that's already
covered by the dedicated suite.
"""

from __future__ import annotations

import pytest

from tests.unit.delegate._verifier_helpers import AcceptAnyVerifier


@pytest.fixture(autouse=True)
def _stub_audit_engine_default_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default the Tier-2 AuditChainEngine verifier to AcceptAnyVerifier.

    Mirrors the Tier-1 conftest stub at
    ``tests/unit/delegate/conftest.py`` — same Protocol-adapter shape
    so legacy wiring tests do not need to construct an Ed25519 keypair
    to assert chain-linkage / cascade / dispatch composition
    invariants. The dedicated cryptographic gate is exercised in
    :mod:`test_signature_verification_wiring` with an explicit
    Ed25519Verifier; that test opts out of this stub by passing the
    real verifier directly to engine construction (the explicit
    ``verifier=...`` argument takes precedence over the default).
    """
    import kailash.delegate.audit as audit_mod
    import kailash.delegate.trust as trust_mod

    monkeypatch.setattr(audit_mod, "NullVerifier", AcceptAnyVerifier)
    monkeypatch.setattr(trust_mod, "NullVerifier", AcceptAnyVerifier)
    # TenantScopedCascade uses dataclass field(default_factory=NullVerifier)
    # which compiles the factory reference into the generated __init__ at
    # class-definition time — patching the module binding or the field
    # object's default_factory doesn't reach the compiled __init__. Wrap
    # the generated __init__ so the verifier kwarg defaults to the
    # adapter when not supplied; explicit verifier= args pass through.
    _original_init = trust_mod.TenantScopedCascade.__init__

    def _patched_init(self, tenant, verifier=None):
        if verifier is None:
            verifier = AcceptAnyVerifier()
        _original_init(self, tenant=tenant, verifier=verifier)

    monkeypatch.setattr(trust_mod.TenantScopedCascade, "__init__", _patched_init)
