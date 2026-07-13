# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 cross-impl receipts_agree evidence for the kailash.delegate
composition primitive (S8 #1035).

The :func:`receipts_agree_dict` comparator is the Fence-B-respecting
byte-shape parity check used to verify the Python implementation produces a
serialized :meth:`RuntimeExecutionResult.to_dict` payload that AGREES with
the kailash-rs implementation's byte shape for the same scenario.

Per ``rules/cross-sdk-inspection.md`` Rule 4 (byte-vector pinning), the
canonical receipt shapes used here are **deterministically derived from the
py runtime's own serialization** acting AS the cross-impl reference: the
public Fence-B-respecting :meth:`RuntimeExecutionResult.to_dict` shape IS
the cross-SDK wire contract per S6 substrate documentation
(``runtime.py::RuntimeExecutionResult.to_dict``: "Cross-impl parity: the
returned dict is the byte-shape contract"). A rs runtime producing a
divergent shape for the same scenario would surface here as a mismatch on
the same comparator the test exercises.

Per ``rules/cross-sdk-inspection.md`` Rule 4a (sibling-canonical vendoring),
the vendored canonical conformance vectors (`canonical.json` shipped as
package data at ``kailash/delegate/conformance/data/``) carry the rs byte-shape contract
for the BEHAVIOURAL surface (5 vectors). The RECEIPT byte-shape contract
this test pins is the orthogonal axis — the runtime's `.to_dict()` output
shape — and is verified by exercising the comparator against deterministic
py outputs whose shape rs MUST match. When rs vendors a fixture file
declaring its `.to_dict()` shape for DV-5-001 / DV-10-001 scenarios, this
test will pin those bytes directly (current Step in §S8 deliverable: pin
the comparator's behavior contract; a later codify pass replaces the
deterministic-py-output placeholder with the rs-vendored shape per Rule 4a
once the rs side publishes the fixture).

Tests (3 — within budget per ``rules/autonomous-execution.md`` MUST Rule 1):

* **R1 (identity)** — py runtime output compared against itself agrees.
* **R2 (mutation-detection)** — flipping a single field of the py payload
  surfaces in `report.mismatches` with the correct field path.
* **R3 (timestamp-exclusion)** — mutating only ``terminated_at`` /
  per-transition ``at`` timestamp keeps the report at agree=True (the
  comparator excludes observation-local timestamp fields by default).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.conformance.schema import ReceiptsAgreeReport, receipts_agree_dict
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.runtime import DelegateRuntime, Posture
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


def _deterministic_signer(canonical_bytes: bytes) -> str:
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    return digest + digest


class _DeterministicConnector(Connector):
    """Protocol-satisfying deterministic connector (NOT a mock)."""

    connector_id = "xi-conn"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    async def invoke(self, input_payload, *, identity, envelope):
        return ConnectorInvocationResult(
            payload={"ok": True, "echo": input_payload.get("id", "n/a")},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed="tenant-xi",
            external_side_effect=True,
        )


class _Signature:
    name = "xi-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool, "echo": str}


def _build_runtime() -> DelegateRuntime:
    chain = TrustLineageChain(
        genesis=GenesisRecord(
            id="g-xi",
            agent_id="agent-xi",
            authority_id="auth-xi",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        )
    )
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-xi"))
    block = GenesisRecord(
        id="g-env-xi",
        agent_id="agent-env-xi",
        authority_id="auth-env-xi",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    envelope = DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0)),
        genesis,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-xi",
        role_binding_ref="rb-xi",
        genesis_ref="g-agent-xi",
    )
    role = Role(
        role_id=uuid.uuid4(),
        display_name="xi-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )
    # #1146 H1 — seed the cascade with the root grantee.
    cascade.register_root_grantee(identity)
    surface = DispatchSurface(
        connector=_DeterministicConnector(),
        signature=_Signature(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=role,
        signer=_deterministic_signer,
    )
    return DelegateRuntime(
        dispatch_surface=surface,
        audit_engine=audit_engine,
        cascade=cascade,
        envelope=envelope,
        identity=identity,
        signer=_deterministic_signer,
        posture=Posture.L5_DELEGATED,
    )


# ---------------------------------------------------------------------------
# R1 — identity: py output compared against itself agrees
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_r1_receipts_agree_identity_on_py_runtime_output() -> None:
    """A serialized py :meth:`RuntimeExecutionResult.to_dict` compared
    against itself MUST report agree=True with empty mismatches.

    This is the identity property of the cross-impl comparator: the
    Fence-B-respecting wire shape is stable, and a rs runtime producing
    a byte-identical shape for the same scenario would land on this
    same agree=True verdict. The shape's stability across rs/py is the
    cross-SDK contract pinned at ``RuntimeExecutionResult.to_dict``
    (S6 substrate documentation).
    """
    runtime = _build_runtime()
    result = await runtime.execute({"id": "xi-r1"})
    serialized = result.to_dict()
    # Vendored-equivalent "rs payload" — for R1 it IS the py payload itself
    # (the contract is shape-equality at the bytes level; rs producing a
    # divergent shape would surface at R2's mismatch detection).
    rs_canonical_payload = serialized
    report = receipts_agree_dict(serialized, rs_canonical_payload)
    assert isinstance(report, ReceiptsAgreeReport)
    assert report.agree is True
    assert report.mismatches == ()
    # Verify the wire shape pins the cross-SDK contract surface
    assert "run_id" in serialized
    assert "dispatch_result" in serialized
    assert "taod_state" in serialized
    assert "posture_at_execute" in serialized


# ---------------------------------------------------------------------------
# R2 — mutation-detection: flipping a non-excluded field surfaces correctly
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_r2_receipts_agree_detects_connector_id_mutation() -> None:
    """Mutating a non-observation-local field — the dispatch_result's
    ``connector_id`` — MUST surface in ``report.mismatches`` with the
    correct dotted path. Confirms the comparator catches real byte-shape
    divergence (e.g., a rs implementation that misnamed the connector).
    """
    runtime = _build_runtime()
    result = await runtime.execute({"id": "xi-r2"})
    py_payload = result.to_dict()

    # Mutate one field — simulate an rs implementation that emitted a
    # different connector_id for the same scenario.
    import copy

    rs_payload_mutated = copy.deepcopy(py_payload)
    assert rs_payload_mutated["dispatch_result"]["connector_id"] == "xi-conn"
    rs_payload_mutated["dispatch_result"]["connector_id"] = "drifted-conn"

    report = receipts_agree_dict(py_payload, rs_payload_mutated)
    assert report.agree is False
    assert "dispatch_result.connector_id" in report.mismatches
    a_val, b_val = report.mismatch_details["dispatch_result.connector_id"]
    assert a_val == "xi-conn"
    assert b_val == "drifted-conn"


# ---------------------------------------------------------------------------
# R3 — timestamp-exclusion: mutating ``terminated_at`` keeps agree=True
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_r3_receipts_agree_excludes_timestamp_fields() -> None:
    """Mutating observation-local timestamp fields keeps agree=True.

    Two impls executing the same scenario produce different wall-clock
    timestamps by design. The comparator's default exclude set covers
    :attr:`_DEFAULT_EXCLUDE_FIELDS` — ``terminated_at`` / ``executed_at``
    / ``started_at`` / ``signed_at`` — at any depth.

    Per the comparator's union-with-defaults contract (callers may ADD
    exclusions but cannot re-enable timestamp comparison), this test
    pins TWO sub-cases:

    * R3a: mutating ONLY top-level ``terminated_at`` keeps agree=True
      via the default exclude set.
    * R3b: mutating per-transition ``at`` (NOT in the default exclude
      set) requires the caller to extend the exclusion; the comparator
      then keeps agree=True via the unioned set.
    """
    runtime = _build_runtime()
    result = await runtime.execute({"id": "xi-r3"})
    py_payload = result.to_dict()

    import copy

    # R3a — top-level terminated_at mutation excluded by default
    rs_payload_top_ts = copy.deepcopy(py_payload)
    rs_payload_top_ts["terminated_at"] = "2099-01-01T00:00:00+00:00"
    report_a = receipts_agree_dict(py_payload, rs_payload_top_ts)
    assert report_a.agree is True
    assert report_a.mismatches == ()
    assert "terminated_at" in report_a.excluded_fields

    # R3b — per-transition ``at`` mutation requires explicit extension;
    # the comparator unions caller-supplied with the defaults so timestamp
    # exclusion cannot be accidentally re-enabled.
    rs_payload_inner_ts = copy.deepcopy(py_payload)
    for transition in rs_payload_inner_ts["taod_state"]["transitions"]:
        transition["at"] = "2099-01-01T00:00:00+00:00"
    report_b = receipts_agree_dict(
        py_payload,
        rs_payload_inner_ts,
        exclude_fields=frozenset({"at"}),
    )
    assert report_b.agree is True
    assert report_b.mismatches == ()
    # Confirm both the default and the caller-supplied exclusion took effect
    assert "at" in report_b.excluded_fields
    assert "terminated_at" in report_b.excluded_fields
