# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for #1035 M1 — _consumed check-and-set TOCTOU.

The prior session's R1 security review surfaced a Time-Of-Check /
Time-Of-Use window in :meth:`DelegateRuntime.execute`: the
``_consumed`` flag was checked OUTSIDE any asyncio lock at ~line 1278,
and set inside a finally block at ~line 1293. Two concurrent
``execute()`` calls on the same runtime instance both observed
``_consumed=False``, both passed the §7 single-shot guard, both
attempted the full TAOD lifecycle on the same single-shot substrate.
The §7 TAOD phase monotonicity invariant ("runtime is single-shot per
receipt") was silently violated under concurrency — the second call's
audit chain segment wrote against state the first call was mid-mutating.

The fix wraps the check-and-set in ``async with self._consume_lock:``
so the test of ``_consumed`` AND the finally-block set become atomic
under concurrent ``execute()`` callers. The lock is per-runtime
(no cross-runtime contention) and :meth:`with_posture` returns a fresh
runtime via the constructor, so each posture rotation yields a fresh
substrate AND a fresh lock — Invariant 5 (per-rotation substrate
freshness) preserved.

This is a Tier-2 behavioral regression test per
``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep":
it constructs a REAL :class:`DelegateRuntime` against the same fixture
substrate as :file:`tests/integration/delegate/test_runtime_wiring.py`,
launches N=10 concurrent ``execute()`` calls via :func:`asyncio.gather`,
and asserts that EXACTLY ONE proceeds to a non-FAILED result while
the remaining (N-1) are blocked by the single-shot guard (either
raising :class:`RuntimePhaseError` directly OR returning a FAILED
:class:`RuntimeExecutionResult` if the lock was acquired but the
``_consumed=True`` state was already set on entry).

Without the fix, this test fails because multiple calls land
non-FAILED results (each one passing the racy guard).
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.runtime import (
    DelegateRuntime,
    Posture,
    RuntimeExecutionResult,
    RuntimePhaseError,
)
from kailash.delegate.trust import TenantScope, TenantScopedCascade
from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    Role,
    RoleLifecycleState,
    RoleScope,
)
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint
from tests.unit.delegate._verifier_helpers import AcceptAnyVerifier

# ---------------------------------------------------------------------------
# Protocol-Satisfying Deterministic Adapter wiring
# ---------------------------------------------------------------------------
#
# Per ``rules/testing.md`` § "3-Tier Testing" → "Protocol Adapters": a
# class satisfying a ``typing.Protocol`` at runtime with deterministic
# output is NOT a mock. The AcceptAnyVerifier monkeypatch mirrors the
# Tier-2 conftest at ``tests/integration/delegate/conftest.py`` so this
# regression test asserts the §7 single-shot wiring contract under
# concurrency — NOT the cryptographic verifier gate, which is exercised
# in the dedicated Ed25519 wiring test.


@pytest.fixture(autouse=True)
def _stub_audit_engine_default_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default AuditChainEngine + TenantScopedCascade verifier to AcceptAnyVerifier."""
    import kailash.delegate.audit as audit_mod
    import kailash.delegate.trust as trust_mod

    monkeypatch.setattr(audit_mod, "NullVerifier", AcceptAnyVerifier)
    monkeypatch.setattr(trust_mod, "NullVerifier", AcceptAnyVerifier)
    # TenantScopedCascade uses dataclass field(default_factory=NullVerifier)
    # which compiles the factory reference into the generated __init__ at
    # class-definition time — patching the module binding does not reach
    # the compiled __init__. Wrap the generated __init__ so the verifier
    # kwarg defaults to the adapter when not supplied; explicit
    # ``verifier=`` args pass through. Mirrors the Tier-2 conftest at
    # ``tests/integration/delegate/conftest.py``.
    _original_init = trust_mod.TenantScopedCascade.__init__

    def _patched_init(self, tenant, verifier=None):
        if verifier is None:
            verifier = AcceptAnyVerifier()
        _original_init(self, tenant=tenant, verifier=verifier)

    monkeypatch.setattr(trust_mod.TenantScopedCascade, "__init__", _patched_init)


# ---------------------------------------------------------------------------
# Substrate builders (real, no mocks — same pattern as
# tests/integration/delegate/test_runtime_wiring.py)
# ---------------------------------------------------------------------------


def _test_signer(canonical_bytes: bytes) -> str:
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h


def _build_chain(agent_id: str = "agent-m1-toctou") -> TrustLineageChain:
    return TrustLineageChain(
        genesis=GenesisRecord(
            id=f"g-{agent_id}",
            agent_id=agent_id,
            authority_id=f"auth-{agent_id}",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        )
    )


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-m1-toctou",
        role_binding_ref="rb-m1-toctou",
        genesis_ref="g-agent-m1-toctou",
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-m1-toctou",
        agent_id="agent-env-m1-toctou",
        authority_id="auth-env-m1-toctou",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    return DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0)),
        genesis,
    )


def _build_role() -> Role:
    return Role(
        role_id=uuid.uuid4(),
        display_name="m1-toctou-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


class _SlowConnector(Connector):
    """Connector that yields control to the event loop before returning.

    The ``await asyncio.sleep(0)`` is the key mechanism: it surrenders
    the event loop mid-invoke so sibling concurrent ``execute()`` calls
    can interleave. Without the yield, the first call's TAOD lifecycle
    completes uninterrupted on a single-threaded event loop and the
    sibling calls only run after ``_consumed=True`` is set — the TOCTOU
    window never opens. The yield reproduces the contended state the
    fix is designed to defend.
    """

    connector_id = "m1-toctou-conn"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    def __init__(self, *, tenant_id_observed: str = "tenant-m1-toctou") -> None:
        self.tenant_id_observed = tenant_id_observed
        self.invocations: list[dict] = []

    async def invoke(self, input_payload, *, identity, envelope):
        # Yield the loop so concurrent execute() callers can interleave
        # at the §7 check-and-set boundary.
        await asyncio.sleep(0)
        self.invocations.append({"input_payload": dict(input_payload)})
        return ConnectorInvocationResult(
            payload={"ok": True, "echo": input_payload.get("id", "n/a")},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=True,
        )


class _M1Sig:
    name = "m1-toctou-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool, "echo": str}


def _build_runtime() -> DelegateRuntime:
    chain = _build_chain()
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-m1-toctou"))
    envelope = _build_envelope()
    identity = _build_identity()
    role = _build_role()
    cascade.register_root_grantee(identity)
    connector = _SlowConnector()
    surface = DispatchSurface(
        connector=connector,
        signature=_M1Sig(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=role,
        signer=_test_signer,
    )
    return DelegateRuntime(
        dispatch_surface=surface,
        audit_engine=audit_engine,
        cascade=cascade,
        envelope=envelope,
        identity=identity,
        signer=_test_signer,
        posture=Posture.L5_DELEGATED,
    )


# ---------------------------------------------------------------------------
# Regression test
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1035_concurrent_execute_serialized_by_consume_lock() -> None:
    """Concurrent execute() on one runtime MUST serialize; only one succeeds.

    Behavioral assertion: N=10 concurrent ``await runtime.execute(...)``
    calls land on the same single-shot runtime instance. The fix's
    ``async with self._consume_lock:`` MUST make the check-and-set of
    ``_consumed`` atomic, so exactly ONE call proceeds to a non-FAILED
    :class:`RuntimeExecutionResult` and the remaining nine are blocked
    by the §7 single-shot guard (either raising
    :class:`RuntimePhaseError` directly OR — if the lock admitted them
    AFTER the first call set ``_consumed=True`` in its finally block —
    raising the same exception on the next acquisition attempt).

    Without the fix, multiple concurrent callers each pass the racy
    ``if self._consumed:`` check and reach :meth:`_execute_impl`,
    producing multiple non-FAILED results AND corrupting the shared
    audit-chain substrate the §7 invariant exists to protect.
    """
    runtime = _build_runtime()

    N = 10
    payloads = [{"id": f"concurrent-{i}"} for i in range(N)]

    # Launch N concurrent calls; gather exceptions so we can classify
    # each return as (result | RuntimePhaseError | unexpected).
    results = await asyncio.gather(
        *(runtime.execute(p) for p in payloads),
        return_exceptions=True,
    )

    # Classify outcomes: a "successful" execute returns a
    # RuntimeExecutionResult whose phase is "completed" (NOT "failed").
    # A "blocked" execute raises RuntimePhaseError OR returns a
    # FAILED-phase RuntimeExecutionResult (defense-in-depth on the
    # exit path; either is acceptable proof of single-shot enforcement).
    successful = []
    blocked_by_phase_error = []
    blocked_by_failed_result = []
    unexpected = []

    for r in results:
        if isinstance(r, RuntimePhaseError):
            blocked_by_phase_error.append(r)
        elif isinstance(r, RuntimeExecutionResult):
            if r.taod_state.phase == "completed":
                successful.append(r)
            elif r.taod_state.phase == "failed":
                blocked_by_failed_result.append(r)
            else:
                unexpected.append(r)
        else:
            unexpected.append(r)

    # Structural assertion 1: exactly ONE non-FAILED outcome.
    # Without the lock, two or more concurrent callers can both pass
    # the §7 guard and reach a completed phase; with the lock, the
    # check-and-set is atomic and only the first caller can proceed.
    assert len(successful) == 1, (
        f"Expected exactly 1 successful execute(), got {len(successful)}. "
        f"This is the M1 TOCTOU regression: multiple concurrent callers "
        f"both passed the §7 _consumed check before either set it to True. "
        f"phase_error={len(blocked_by_phase_error)}, "
        f"failed_result={len(blocked_by_failed_result)}, "
        f"unexpected={len(unexpected)}"
    )

    # Structural assertion 2: every other outcome MUST be a clean
    # single-shot refusal (phase-error OR failed-result), never an
    # unexpected exception/return.
    assert len(unexpected) == 0, (
        f"Unexpected outcomes from concurrent execute(): {unexpected}. "
        f"Every blocked call MUST be RuntimePhaseError or a FAILED result."
    )
    assert len(blocked_by_phase_error) + len(blocked_by_failed_result) == N - 1, (
        f"Expected exactly {N - 1} blocked calls, got "
        f"phase_error={len(blocked_by_phase_error)} + "
        f"failed_result={len(blocked_by_failed_result)}"
    )

    # Structural assertion 3: every RuntimePhaseError carries the
    # canonical single-shot message — the §7 monotonicity citation
    # is the load-bearing audit trail for the refusal class.
    for exc in blocked_by_phase_error:
        msg = str(exc)
        assert (
            "single-shot" in msg
        ), f"RuntimePhaseError missing single-shot citation: {msg!r}"
        assert "§7" in msg or "TAOD" in msg, (
            f"RuntimePhaseError missing §7/TAOD phase-monotonicity "
            f"citation: {msg!r}"
        )

    # Structural assertion 4: the runtime MUST be marked consumed after
    # gather completes. The fix preserves the original semantics — every
    # exit path (success, FAILED return, exceptional bubble-up) sets
    # _consumed=True via the finally block — and the lock additionally
    # ensures the set is observed atomically.
    assert runtime._consumed is True, (
        "Runtime._consumed MUST be True after any execute() exit path; "
        "the finally-block consumption is the defense-in-depth against "
        "retry-until-success on a runtime."
    )


# ---------------------------------------------------------------------------
# R1-followup — with_posture() returns runtime with fresh substrate
#
# The §7 phase-monotonicity invariant ("runtime is single-shot per receipt")
# requires that every posture rotation produces a runtime with a fresh lock
# and an un-consumed flag. If with_posture() shared the originating
# runtime's _consume_lock, a consumed runtime could block the rotated one
# (or vice versa); if it carried over _consumed, the rotated runtime would
# refuse the first call.
#
# The concurrent-execute test above proves the lock SERIALIZES within one
# runtime instance. This structural test proves the lock ROTATES across
# with_posture() — both halves of Invariant 5 (per-rotation substrate
# freshness) are then pinned by the regression suite.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_with_posture_returns_runtime_with_fresh_consume_lock() -> None:
    """Invariant 5: ``with_posture()`` rotates to a fresh runtime + fresh lock.

    A rotated runtime MUST own a DISTINCT ``asyncio.Lock`` instance —
    sharing the lock with the originating runtime would let a consumed
    runtime block the rotated one (or vice versa). Per §7 phase
    monotonicity, each runtime instance is single-shot per receipt; the
    lock is the enforcement primitive AND MUST rotate with the runtime.

    Same-posture rotation (no upgrade nonce required) is used here so the
    test exercises only the substrate-freshness contract, not the upgrade
    gate. A regression that aliased ``_consume_lock`` across rotation (or
    that carried over ``_consumed=True``) would fail this test loudly.
    """
    runtime = _build_runtime()
    rotated = runtime.with_posture(runtime.posture)  # rotate to same posture

    assert rotated._consume_lock is not runtime._consume_lock, (
        "with_posture() returned a runtime sharing the originating "
        "runtime's _consume_lock — Invariant 5 (per-rotation substrate "
        "freshness) violated; a consumed runtime could block the rotated "
        "one (or vice versa) on the shared lock."
    )
    assert rotated._consumed is False, (
        "with_posture() returned a runtime with carried-over _consumed "
        "state — single-shot guarantee violated; the rotated runtime "
        "MUST start with a fresh substrate, not inherit the consumed "
        "flag of its originator."
    )
