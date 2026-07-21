# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Structural serializer-set-parity regression for cross-sdk-inspection.md Rule 4e.

Rule 4e ("Existing Fold Fields On A Cross-SDK Signed Model MUST Round-Trip
Through EVERY Serializer Via One Shared Serde") mandates a STRUCTURAL
serializer-set-parity test with a NON-CIRCULAR discovery predicate: enumerate
the model's serializer set WITHOUT deriving the "expected field set" from any
one serializer's output, and WITHOUT discovering the serializer set merely by
"does it import the shared serde" (that predicate can only ever find
COMPLIANT functions — it can never find a re-implementing DROPPER, which is
the actual defect class #1841 shipped).

This module is the missing mechanical backstop named in workspace journal
0009 § "For Discussion" item 2 (F6): the #1841 arc already landed (1) the
shared serde (``delegation_fold_serde.py``) and (2) a DISCRIMINATING
both-polarity end-to-end round-trip regression
(``tests/regression/test_issue_1841_chain_serde_roundtrip.py``) — but NOT
this structural parity test. Complementary to, not a replacement for, that
e2e regression.

Two independent, non-circular checks:

1. **Authoritative field-set derivation** (§1 below) — the fold-field names
   are read from ``_FoldSourceRecord`` (the shared serde's OWN structural
   input-contract declaration, in ``delegation_fold_serde.py`` — a module
   that is NEITHER a serializer NOR derived from one) and cross-validated
   against ``DelegationRecord``'s real dataclass fields (the signed model
   itself). No serializer's *output* is ever consulted to build this set.

2. **Structural serializer-set discovery** (§2 below) — every function in
   the four canonical serializer modules (``chain.py`` +
   ``interop/{w3c_vc,jwt,ucan}.py``, the exact set named in
   ``delegation_fold_serde.py``'s own docstring) is discovered by AST
   SIGNATURE/BODY SHAPE (accepts-a-DelegationRecord-returns-a-dict on the
   serialize side; constructs-a-DelegationRecord-from-external-data on the
   deserialize side) — NEVER by "does it import the serde". A function that
   matches the shape but does NOT route through the shared serde is a
   dropper and MUST fail loudly, naming itself.

3. **Behavioral round-trip parity** (§3 below) — a FULLY-CONFIGURED v3
   multi-sig record (every fold-field type populated) is round-tripped
   through every discovered serializer pair; every field in the
   authoritative set MUST survive with equal value. This is what actually
   catches a serializer that calls the shared serde but then drops/mutates
   one field afterward (the AST check in §2 only proves the CALL exists, not
   that its output survives untouched).

4. **Non-collidability sanity** (§4 below) — two records differing in ONE
   fold field must not fold to indistinguishable serialized output; proves
   each field is load-bearing in the wire form, not silently ignored.

Tier-2 style: real Ed25519 (``kailash.trust.signing.crypto``), real chain /
interop serializers, NO mocking of the serde surface.
"""

from __future__ import annotations

import ast
import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Tuple

import pytest

from kailash.trust.chain import (
    DELEGATION_SIGNING_VERSION_V3,
    AuthorityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.interop import jwt as jwt_interop
from kailash.trust.interop import w3c_vc
from kailash.trust.interop.ucan import from_ucan, to_ucan
from kailash.trust.signing.crypto import generate_keypair
from kailash.trust.signing.delegation_fold_serde import _FoldSourceRecord
from kailash.trust.signing.delegation_payload import (
    ConstraintDimensions,
    DelegationScope,
    MultiSigSigningPolicy,
    ResourceLimits,
    TrustLevel,
)

pytestmark = pytest.mark.regression


# =============================================================================
# 1. AUTHORITATIVE FOLD-FIELD SET — derived from the SIGNED MODEL's field
#    declaration, NEVER from any serializer's output (the non-circular
#    predicate Rule 4e's field-set half mandates).
# =============================================================================


def _authoritative_fold_fields() -> Tuple[str, ...]:
    """The fold-field names, derived structurally from the signed model.

    Source of truth: ``_FoldSourceRecord`` — the Protocol
    ``delegation_fold_serde.py`` itself declares as "the structural type for
    the record fields ``serialize_fold_fields`` READS" (its docstring). This
    is the model's OWN input-contract declaration, not any serializer's
    emitted dict shape. Cross-validated against ``DelegationRecord``'s real
    dataclass fields so a Protocol/dataclass drift is caught, not silently
    trusted.
    """
    protocol_fields = tuple(_FoldSourceRecord.__annotations__.keys())
    dataclass_field_names = {f.name for f in dataclasses.fields(DelegationRecord)}
    missing = [f for f in protocol_fields if f not in dataclass_field_names]
    assert not missing, (
        f"_FoldSourceRecord declares field(s) {missing!r} that are NOT real "
        f"DelegationRecord dataclass fields — the shared serde's structural "
        f"input-contract has drifted from the signed model it claims to fold."
    )
    assert protocol_fields, (
        "_FoldSourceRecord declared ZERO fields — the authoritative "
        "fold-field derivation is vacuous (would make every downstream "
        "assertion in this file trivially pass on nothing)."
    )
    return protocol_fields


FOLD_FIELDS: Tuple[str, ...] = _authoritative_fold_fields()


def test_authoritative_fold_field_set_is_the_expected_five() -> None:
    """Human-readable pin: the STRUCTURALLY-derived set is #1841's 5 fields.

    This assertion is NOT the source of truth for the field set (the
    derivation in ``_authoritative_fold_fields`` above is) — it is a
    human-legible tripwire so a silent edit to ``_FoldSourceRecord`` shows up
    as a failing, named diff instead of silently rippling through every
    other assertion in this file.
    """
    assert set(FOLD_FIELDS) == {
        "constraints",
        "resource_limits",
        "scope",
        "multi_sig",
        "multi_sig_policy",
    }


# =============================================================================
# 2. STRUCTURAL SERIALIZER-SET DISCOVERY (non-circular) — AST signature/body
#    shape, never "does it import the serde".
# =============================================================================

# The exact module set delegation_fold_serde.py's own docstring names as
# "every delegation serializer": the chain-level path (DelegationRecord
# itself + TrustLineageChain, both in chain.py) + the three interop encoders.
_TARGET_MODULES: Dict[str, str] = {
    "chain": "src/kailash/trust/chain.py",
    "w3c_vc": "src/kailash/trust/interop/w3c_vc.py",
    "jwt": "src/kailash/trust/interop/jwt.py",
    "ucan": "src/kailash/trust/interop/ucan.py",
}


def _repo_root() -> Path:
    # tests/regression/test_delegation_serializer_set_parity.py -> repo root
    return Path(__file__).resolve().parents[2]


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _calls_any(node: ast.AST, target_names: FrozenSet[str]) -> bool:
    """True if `node`'s subtree contains a Call resolving to a target name.

    Matches both bare-name calls (``serialize_fold_fields(...)``) and
    attribute calls (``mod.serialize_fold_fields(...)``).
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in target_names:
                return True
    return False


def _local_delegation_record_aliases(tree: ast.Module) -> FrozenSet[str]:
    """Every local name this module binds to kailash.trust.chain.DelegationRecord.

    Resolved from the AST's own import statements (module-level AND
    function-nested — ``ast.walk`` finds both), so an aliased import
    (``ucan.py``'s deferred ``DelegationRecord as _DelegationRecord``) is
    still correctly attributed. ``chain.py`` itself defines the class under
    the bare name, so "DelegationRecord" is always a valid alias.
    """
    aliases = {"DelegationRecord"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("trust.chain")
        ):
            for alias in node.names:
                if alias.name == "DelegationRecord":
                    aliases.add(alias.asname or alias.name)
    return frozenset(aliases)


@dataclasses.dataclass(frozen=True)
class _Candidate:
    module: str
    qualname: str
    kind: str  # "serialize" | "deserialize"
    calls_shared_serde: bool


def _discover_candidates(module_key: str, rel_path: str) -> List[_Candidate]:
    path = _repo_root() / rel_path
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    record_aliases = _local_delegation_record_aliases(tree)
    candidates: List[_Candidate] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def _visit_function(self, node: Any) -> None:
            qualname = ".".join(self.class_stack + [node.name])
            in_delegation_record_class = bool(
                self.class_stack and self.class_stack[-1] == "DelegationRecord"
            )

            # --- SERIALIZE-shaped: a DelegationRecord-typed parameter with a
            #     dict-ish (or unannotated) return, OR DelegationRecord's OWN
            #     to_dict method. Discovery is by SIGNATURE SHAPE — it finds
            #     a re-implementing dropper exactly as readily as a
            #     compliant serializer; whether it imports the serde is
            #     checked SEPARATELY, never as part of discovery. ---
            is_serialize_candidate = False
            for arg in list(node.args.args) + list(node.args.kwonlyargs):
                if arg.arg in ("self", "cls"):
                    continue
                ann_src = _unparse(arg.annotation)
                if "DelegationRecord" in ann_src:
                    ret_src = _unparse(node.returns)
                    if ret_src == "" or "Dict" in ret_src or "dict" in ret_src:
                        is_serialize_candidate = True
            if in_delegation_record_class and node.name == "to_dict":
                is_serialize_candidate = True

            if is_serialize_candidate:
                candidates.append(
                    _Candidate(
                        module=module_key,
                        qualname=qualname,
                        kind="serialize",
                        calls_shared_serde=_calls_any(
                            node, frozenset({"serialize_fold_fields"})
                        ),
                    )
                )

            # --- DESERIALIZE-shaped: constructs a DelegationRecord (by any
            #     resolved local import alias, OR `cls(...)` inside
            #     DelegationRecord's OWN classmethod) somewhere in its body.
            #     Scoped to these 4 canonical files, where every such
            #     construction reconstructs a record from PERSISTED/wire
            #     data (chain dict / VC / JWT claims / UCAN facts) — never a
            #     fresh in-process delegation (those live in application
            #     code outside this file set: cli/commands.py,
            #     operations/__init__.py, pact/engine.py). ---
            construct_names = set(record_aliases)
            if in_delegation_record_class:
                construct_names.add("cls")
            if _calls_any(node, frozenset(construct_names)):
                candidates.append(
                    _Candidate(
                        module=module_key,
                        qualname=qualname,
                        kind="deserialize",
                        calls_shared_serde=_calls_any(
                            node, frozenset({"deserialize_fold_fields"})
                        ),
                    )
                )

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)
            self.generic_visit(node)

    _Visitor().visit(tree)
    return candidates


def _discover_all_candidates() -> List[_Candidate]:
    all_candidates: List[_Candidate] = []
    for module_key, rel_path in _TARGET_MODULES.items():
        all_candidates.extend(_discover_candidates(module_key, rel_path))
    return all_candidates


def test_serializer_set_discovery_is_nonempty_and_pairs_five_and_five() -> None:
    """Guard the discovery mechanism itself against vacuous / broken AST scan.

    Every downstream assertion in §2/§3 is meaningless if the AST scan
    silently found nothing (a path typo, a parse error swallowed elsewhere,
    a signature-shape predicate that stopped matching after a refactor)
    would make "assert every candidate complies" trivially pass on an empty
    set. Pin the expected shape: exactly 5 serialize-shaped + 5
    deserialize-shaped candidates, one pair per canonical serializing path
    (DelegationRecord.to_dict/from_dict, TrustLineageChain._serialize_/
    _deserialize_delegation, w3c_vc, jwt, ucan).
    """
    candidates = _discover_all_candidates()
    serialize_candidates = [c for c in candidates if c.kind == "serialize"]
    deserialize_candidates = [c for c in candidates if c.kind == "deserialize"]

    assert len(serialize_candidates) == 5, (
        f"expected 5 serialize-shaped candidates, found "
        f"{len(serialize_candidates)}: "
        f"{[(c.module, c.qualname) for c in serialize_candidates]}"
    )
    assert len(deserialize_candidates) == 5, (
        f"expected 5 deserialize-shaped candidates, found "
        f"{len(deserialize_candidates)}: "
        f"{[(c.module, c.qualname) for c in deserialize_candidates]}"
    )


def test_every_discovered_serializer_routes_through_the_shared_serde() -> None:
    """STRUCTURAL parity backstop: every discovered function calls the serde.

    Discovery (§2 above) finds candidates by SIGNATURE/BODY SHAPE — a
    predicate that would find a re-implementing dropper exactly as readily
    as a compliant serializer. This assertion is the parity check itself:
    every discovered candidate MUST route through
    ``serialize_fold_fields``/``deserialize_fold_fields``. A serializer that
    carries only ``signing_payload_version`` and re-implements the rest
    (Rule 4e's named DO-NOT shape) fails HERE, by name.
    """
    candidates = _discover_all_candidates()
    non_compliant = [c for c in candidates if not c.calls_shared_serde]
    assert not non_compliant, (
        "the following delegation-serializing function(s) do NOT route "
        "through the shared delegation_fold_serde helpers — each is a "
        "re-implementing dropper candidate (Rule 4e):\n"
        + "\n".join(f"  - {c.module}.{c.qualname} ({c.kind})" for c in non_compliant)
    )


# =============================================================================
# 3. BEHAVIORAL ROUND-TRIP PARITY — every discovered serializer PAIR
#    round-trips a FULLY-CONFIGURED record without losing any authoritative
#    fold field. Catches a serializer that calls the shared serde but then
#    drops/mutates a field afterward (invisible to the AST check above).
# =============================================================================


def _key(n: int) -> bytes:
    return bytes([n]) * 32


def _fully_configured_v3_record(**overrides: Any) -> DelegationRecord:
    """A record with EVERY fold-field type populated (non-default values).

    Mirrors the sibling e2e regression's ``_v3_record`` fixture
    (``test_issue_1841_chain_serde_roundtrip.py``) — a legacy/all-unset
    record would round-trip an EMPTY fold dict and assert nothing (an inert
    tripwire); only a fully-configured record makes the pin discriminating.
    """
    kwargs: Dict[str, Any] = dict(
        id="00000000-0000-4000-8000-0000000000f6",
        delegator_id="alice",
        delegatee_id="bob",
        task_id="task-f6-parity",
        capabilities_delegated=["LlmCall"],
        constraint_subset=[],
        delegated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="",
        constraints=ConstraintDimensions.for_level(TrustLevel.SUPERVISED),
        resource_limits=ResourceLimits.for_level(TrustLevel.SUPERVISED),
        scope=DelegationScope.new("engineering").with_operation("read"),
        multi_sig=True,
        multi_sig_policy=MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)]),
        signing_payload_version=DELEGATION_SIGNING_VERSION_V3,
    )
    kwargs.update(overrides)
    return DelegationRecord(**kwargs)


def _genesis() -> GenesisRecord:
    return GenesisRecord(
        id="genesis-f6",
        agent_id="agent-bob",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="genesis-sig",
    )


def _chain_with(record: DelegationRecord) -> TrustLineageChain:
    return TrustLineageChain(genesis=_genesis(), delegations=[record])


def _roundtrip_record_to_dict(record: DelegationRecord) -> DelegationRecord:
    return DelegationRecord.from_dict(record.to_dict())


def _roundtrip_chain(record: DelegationRecord) -> DelegationRecord:
    chain_dict = _chain_with(record).to_dict()
    restored_chain = TrustLineageChain.from_dict(chain_dict)
    (restored,) = restored_chain.delegations
    return restored


def _roundtrip_w3c_vc(record: DelegationRecord) -> DelegationRecord:
    private_key, public_key = generate_keypair()
    vc = w3c_vc.export_as_verifiable_credential(
        _chain_with(record), issuer_did="did:eatp:org:acme", signing_key=private_key
    )
    restored_chain = w3c_vc.import_from_verifiable_credential(vc, public_key=public_key)
    (restored,) = restored_chain.delegations
    return restored


def _roundtrip_jwt(record: DelegationRecord) -> DelegationRecord:
    serialized = jwt_interop._serialize_delegation(record)
    return jwt_interop._deserialize_delegation(serialized)


def _roundtrip_ucan(record: DelegationRecord) -> DelegationRecord:
    private_key, public_key = generate_keypair()
    token = to_ucan(record, private_key)
    return from_ucan(token, public_key)


_ROUNDTRIP_PAIRS: Tuple[
    Tuple[str, Callable[[DelegationRecord], DelegationRecord]], ...
] = (
    ("DelegationRecord.to_dict/from_dict", _roundtrip_record_to_dict),
    ("TrustLineageChain._serialize_/_deserialize_delegation", _roundtrip_chain),
    (
        "w3c_vc.export_as_verifiable_credential/import_from_verifiable_credential",
        _roundtrip_w3c_vc,
    ),
    ("jwt._serialize_delegation/_deserialize_delegation", _roundtrip_jwt),
    ("ucan.to_ucan/from_ucan", _roundtrip_ucan),
)


@pytest.mark.parametrize(
    "label,roundtrip", _ROUNDTRIP_PAIRS, ids=[p[0] for p in _ROUNDTRIP_PAIRS]
)
def test_every_serializer_preserves_every_authoritative_fold_field(
    label: str, roundtrip: Callable[[DelegationRecord], DelegationRecord]
) -> None:
    """Every serializer round-trips EVERY field in the authoritative set.

    A serializer that drops a folded field fails LOUDLY here, naming the
    serializer (via the parametrize id) AND the dropped field.
    """
    record = _fully_configured_v3_record()

    restored = roundtrip(record)

    for field_name in FOLD_FIELDS:
        original_value = getattr(record, field_name)
        restored_value = getattr(restored, field_name)
        assert restored_value == original_value, (
            f"{label}: fold field {field_name!r} did NOT survive round-trip "
            f"(original={original_value!r}, restored={restored_value!r}) — "
            f"this serializer dropped a field already folded into the "
            f"signed pre-image (cross-sdk-inspection.md Rule 4e)."
        )


def test_roundtrip_pair_count_matches_discovered_serialize_candidate_count() -> None:
    """The behavioral round-trip pairs above cover the FULL discovered set.

    Ties §2's structural discovery to §3's behavioral coverage: if a future
    serializer is added and discovered by the AST scan, this assertion fails
    until a matching round-trip pair is added to ``_ROUNDTRIP_PAIRS`` —
    closing the gap where the structural parity check (§2) passes on a new
    compliant serializer that the behavioral check (§3) never actually
    exercises.
    """
    serialize_candidates = [
        c for c in _discover_all_candidates() if c.kind == "serialize"
    ]
    assert len(_ROUNDTRIP_PAIRS) == len(serialize_candidates), (
        f"{len(serialize_candidates)} serialize-shaped candidates discovered "
        f"structurally, but only {len(_ROUNDTRIP_PAIRS)} behavioral "
        f"round-trip pairs are wired in this file — a new serializer landed "
        f"without a matching round-trip pin."
    )


# =============================================================================
# 4. NON-COLLIDABILITY SANITY — two records differing in ONE fold field MUST
#    NOT fold to indistinguishable serialized output.
# =============================================================================


def test_fold_fields_are_load_bearing_not_collided_in_chain_serialization() -> None:
    """Two records differing in one fold field serialize to DIFFERENT dicts.

    Proves each authoritative field actually contributes distinguishing
    bytes to the serialized form (necessary for the round-trip equality
    check in §3 to mean anything beyond "both sides share one default") —
    a serializer that silently ignored a field's actual content while still
    emitting SOME placeholder value would pass a naive equality check only
    when both records happen to share that placeholder; this test uses two
    DISTINCT configured values per field so a collision is directly visible.
    """
    base = _fully_configured_v3_record()
    varied = _fully_configured_v3_record(
        scope=DelegationScope.new("finance").with_operation("write")
    )
    assert base.scope != varied.scope  # sanity: the fixture actually varies

    base_dict = TrustLineageChain._serialize_delegation(base)
    varied_dict = TrustLineageChain._serialize_delegation(varied)

    assert base_dict["scope"] != varied_dict["scope"], (
        "two DelegationRecords with DISTINCT `scope` values folded to the "
        "SAME serialized `scope` bytes — the field is not load-bearing in "
        "the chain-level wire form (non-collidability violated)."
    )

    # Round-tripping each separately must keep them distinguishable.
    restored_base = _roundtrip_chain(base)
    restored_varied = _roundtrip_chain(varied)
    assert restored_base.scope == base.scope
    assert restored_varied.scope == varied.scope
    assert restored_base.scope != restored_varied.scope, (
        "two distinct records collapsed to the SAME reconstructed `scope` "
        "after an independent chain round-trip each — non-collidability "
        "violated post-reconstruction."
    )
