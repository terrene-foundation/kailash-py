# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Structural serializer-set-parity regression for the #1912 capability version.

#1912 Wave 1 added ``signing_payload_version`` to ``CapabilityAttestation`` and
made a v1 cap's signature bind the holder subject. That field must survive
EVERY capability serializer, or a v1 cap reloads as legacy → the legacy verify
recomputes WITHOUT the subject → the v1 signature fails
(``security.md`` § "Multi-Site Kwarg Plumbing"; ``cross-sdk-inspection.md``
Rule 4e). This module is the mechanical backstop that a serializer cannot drop
the field.

Mirrors ``test_delegation_serializer_set_parity.py`` with a NON-CIRCULAR
discovery predicate (AST signature/body shape, NEVER "does it import the
serde"), adapted for two capability-specific realities:

  * the serializer set is ASYMMETRIC — SD-JWT is export-only (no capability
    reconstruction), so serialize and deserialize candidate counts differ; and
  * a PUBLIC wrapper (``export_capability_as_vc``) DELEGATES capability
    serialization to the private ``_serialize_capability`` rather than calling
    the shared serde itself — so compliance is "routes through the serde
    DIRECTLY, or delegates to another discovered capability serializer".

Checks:

1. **Authoritative field set** — derived from ``_CapabilityFoldSource`` (the
   shared serde's OWN structural input-contract), cross-validated against the
   ``CapabilityAttestation`` dataclass. Never from a serializer's output.
2. **Structural discovery** — every function taking a ``CapabilityAttestation``
   and returning a dict (serialize) / constructing a ``CapabilityAttestation``
   (deserialize), by AST shape.
3. **Compliance** — every discovered candidate routes through the shared serde
   directly OR delegates to another discovered candidate; a re-implementing
   dropper is caught by name.
4. **Behavioral positive round-trip** — a v1 cap through every round-trippable
   pair preserves ``signing_payload_version``; a legacy cap emits NO version key
   (prune-when-unset, byte-identical to pre-#1912).
5. **Negative pole** — stripping the version key from real wire output yields a
   reloaded cap whose (legacy) pre-image no longer verifies against the original
   v1 signature.

Tier-2 style: real Ed25519, real chain / interop serializers, NO mocking.
"""

from __future__ import annotations

import ast
import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Tuple

import pytest

from kailash.trust.chain import (
    CAPABILITY_SIGNING_VERSION_LEGACY,
    CAPABILITY_SIGNING_VERSION_V1,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.interop import jwt as jwt_interop
from kailash.trust.interop import sd_jwt as sd_jwt_interop
from kailash.trust.interop import w3c_vc
from kailash.trust.signing.capability_fold_serde import _CapabilityFoldSource
from kailash.trust.signing.crypto import generate_keypair, sign, verify_signature

pytestmark = pytest.mark.regression

FIXED_TS = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
SUBJECT = "agent-holder"


# =============================================================================
# 1. AUTHORITATIVE FOLD-FIELD SET
# =============================================================================


def _authoritative_fields() -> Tuple[str, ...]:
    protocol_fields = tuple(_CapabilityFoldSource.__annotations__.keys())
    dataclass_names = {f.name for f in dataclasses.fields(CapabilityAttestation)}
    missing = [f for f in protocol_fields if f not in dataclass_names]
    assert not missing, (
        f"_CapabilityFoldSource declares field(s) {missing!r} not on "
        f"CapabilityAttestation — the serde's input contract drifted from the "
        f"signed model."
    )
    assert protocol_fields, "_CapabilityFoldSource declared ZERO fields"
    return protocol_fields


FOLD_FIELDS: Tuple[str, ...] = _authoritative_fields()


def test_authoritative_field_set_is_signing_payload_version() -> None:
    """Human-legible pin of the structurally-derived field set."""
    assert set(FOLD_FIELDS) == {"signing_payload_version"}


# =============================================================================
# 2. STRUCTURAL SERIALIZER-SET DISCOVERY
# =============================================================================

# The scanned module set is CODEBASE-DERIVED, never a hardcoded allowlist
# (#1912 RT-sec INVEST-NOW). Every ``.py`` under ``src/kailash/trust/`` is
# scanned, so a capability serializer added in any module UNDER THAT TREE —
# a new interop format or a new subpackage — is discovered automatically and
# trips ``test_discovered_serializer_set_matches_expected`` loudly, rather than
# silently escaping a 4-module allowlist. The shape-based ``_discover``
# predicate returns [] for the vast majority of files (no cap-serializing
# function), so the discovered set stays exactly the real serializers.
# Scope: the trust plane is the sole owner of CapabilityAttestation signing;
# a cap serializer elsewhere (e.g. under packages/*/src) would NOT be scanned —
# no such site exists today, and one would be a cross-package layering break to
# review on its own. Widen _TRUST_ROOT_REL if that ever changes.
_TRUST_ROOT_REL = "src/kailash/trust"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _all_trust_modules() -> List[Tuple[str, str]]:
    """(module_label, rel_path) for every ``.py`` under the trust package.

    Returned as a LIST (not a dict) so duplicate file stems — every
    ``__init__.py`` shares the stem ``__init__`` — are each scanned
    independently instead of colliding on a dict key and dropping a module
    from the sweep. ``module_label`` is the file stem (matching the short keys
    the expected-set assertions pin: ``chain`` / ``w3c_vc`` / ``jwt`` /
    ``sd_jwt``).
    """
    root = _repo_root() / _TRUST_ROOT_REL
    mods: List[Tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(_repo_root()).as_posix()
        mods.append((path.stem, rel))
    return mods


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _called_names(node: ast.AST) -> FrozenSet[str]:
    """Every function name called anywhere in `node`'s subtree (bare + attr)."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return frozenset(names)


def _local_capability_aliases(tree: ast.Module) -> FrozenSet[str]:
    aliases = {"CapabilityAttestation"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("trust.chain")
        ):
            for alias in node.names:
                if alias.name == "CapabilityAttestation":
                    aliases.add(alias.asname or alias.name)
    return frozenset(aliases)


@dataclasses.dataclass(frozen=True)
class _Candidate:
    module: str
    qualname: str
    func_name: str
    # "serialize" (cap -> dict) | "construct" (builds a CapabilityAttestation:
    # a round-trip DESERIALIZER, a fresh MINT, or an UNSIGNED emission).
    kind: str
    called_names: FrozenSet[str]
    # For a "construct" candidate:
    #   sets_version  — EVERY signed (non-UNSIGNED) construction sets
    #                   signing_payload_version=V1 (a mint that originates a
    #                   transplant-resistant cap). A function that mints even ONE
    #                   signed cap without V1 is NOT compliant on this flag.
    #   all_unsigned  — ALL constructions are signature="UNSIGNED" (a non-verify
    #                   emission — the fold field is irrelevant).
    # Both default False.
    sets_version: bool = False
    all_unsigned: bool = False


def _cap_construction_flags(
    node: ast.AST, cap_aliases: FrozenSet[str]
) -> Tuple[bool, bool]:
    """Inspect every ``CapabilityAttestation(...)`` call inside ``node``.

    Returns ``(sets_version, all_unsigned)``:
      * ``sets_version`` — there is ≥1 SIGNED construction AND **EVERY** signed
        (non-``signature="UNSIGNED"``) construction passes
        ``signing_payload_version=`` bound to the **V1 (subject-bound)** constant.
        Requiring EVERY signed construction (not just one) closes the mixed-mint
        hole: a function that mints one V1 cap AND one legacy cap ships a
        transplantable legacy cap and MUST still be flagged. Setting a version to
        LEGACY, or omitting it, on any signed construction fails this flag.
      * ``all_unsigned`` — EVERY construction passes ``signature="UNSIGNED"``
        (an emission that never enters the Ed25519 verify path, so the fold
        field is irrelevant — e.g. PACT ``grant_clearance``).
    """
    constructions: List[ast.Call] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        name = (
            fn.id
            if isinstance(fn, ast.Name)
            else (fn.attr if isinstance(fn, ast.Attribute) else "")
        )
        if name in cap_aliases:
            constructions.append(sub)
    if not constructions:
        return False, False

    def _is_unsigned(call: ast.Call) -> bool:
        return any(
            kw.arg == "signature"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value == "UNSIGNED"
            for kw in call.keywords
        )

    def _sets_v1(call: ast.Call) -> bool:
        return any(
            kw.arg == "signing_payload_version"
            and "CAPABILITY_SIGNING_VERSION_V1" in _unparse(kw.value)
            for kw in call.keywords
        )

    signed = [c for c in constructions if not _is_unsigned(c)]
    sets_version = bool(signed) and all(_sets_v1(c) for c in signed)
    all_unsigned = all(_is_unsigned(c) for c in constructions)
    return sets_version, all_unsigned


def _discover(module_key: str, rel_path: str) -> List[_Candidate]:
    path = _repo_root() / rel_path
    return _discover_tree(module_key, ast.parse(path.read_text(), filename=str(path)))


def _discover_tree(module_key: str, tree: ast.Module) -> List[_Candidate]:
    cap_aliases = _local_capability_aliases(tree)
    out: List[_Candidate] = []

    class _V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def _fn(self, node: Any) -> None:
            qualname = ".".join(self.stack + [node.name])
            called = _called_names(node)

            # SERIALIZE-shaped: a CapabilityAttestation-annotated param with a
            # dict-ish (or unannotated) return. Discovery is by SHAPE — it finds
            # a re-implementing dropper as readily as a compliant serializer.
            # ``to_signing_payload`` (param ``self``/``subject_agent_id``) is NOT
            # matched (no CapabilityAttestation-annotated param) — it is the
            # signing pre-image, whose SHAPE encodes the version, not a wire dict.
            is_serialize = False
            for arg in list(node.args.args) + list(node.args.kwonlyargs):
                if arg.arg in ("self", "cls"):
                    continue
                if "CapabilityAttestation" in _unparse(arg.annotation):
                    ret = _unparse(node.returns)
                    if ret == "" or "Dict" in ret or "dict" in ret:
                        is_serialize = True
            if is_serialize:
                out.append(
                    _Candidate(module_key, qualname, node.name, "serialize", called)
                )

            # CONSTRUCT-shaped: builds a CapabilityAttestation somewhere in its
            # body (by any resolved local alias). This covers a round-trip
            # DESERIALIZER (must route the fold field back through the serde), a
            # fresh MINT (must SET the version at construction), and an UNSIGNED
            # emission (exempt — never verified). The producer-compliance rule
            # below distinguishes them; a signed cap produced with neither a
            # serde route nor an explicit version is the transplant-bug class.
            if called & cap_aliases:
                sets_version, all_unsigned = _cap_construction_flags(node, cap_aliases)
                out.append(
                    _Candidate(
                        module_key,
                        qualname,
                        node.name,
                        "construct",
                        called,
                        sets_version=sets_version,
                        all_unsigned=all_unsigned,
                    )
                )

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._fn(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._fn(node)
            self.generic_visit(node)

    _V().visit(tree)
    return out


def _discover_all() -> List[_Candidate]:
    out: List[_Candidate] = []
    for module_label, rel_path in _all_trust_modules():
        out.extend(_discover(module_label, rel_path))
    return out


_EXPECTED_SERIALIZE = {
    ("chain", "TrustLineageChain._serialize_capability"),
    ("w3c_vc", "_serialize_capability"),
    ("w3c_vc", "export_capability_as_vc"),
    ("jwt", "_serialize_capability"),
    ("sd_jwt", "_serialize_capability_claims"),
}
_EXPECTED_CONSTRUCT = {
    # Round-trip DESERIALIZERS (route the fold field back through the serde).
    ("chain", "TrustLineageChain._deserialize_capability"),
    ("w3c_vc", "import_from_verifiable_credential"),
    ("jwt", "_deserialize_capability"),
    # Fresh MINTS (originate the fold field: signing_payload_version=V1).
    ("__init__", "TrustOperations._create_capability_attestation"),
    ("__init__", "TrustOperations._build_signed_derived_caps"),
    ("commands", "establish_cmd"),
    ("commands", "delegate_cmd"),
    # UNSIGNED emissions (signature="UNSIGNED"; never reach the verify path).
    ("engine", "GovernanceEngine.grant_clearance"),
    ("engine", "GovernanceEngine.transition_clearance"),
}


def test_discovered_serializer_set_matches_expected() -> None:
    """Pin the discovered set so a NEW capability serializer fails loudly here.

    Guards every downstream assertion against a vacuous AST scan (a path typo /
    predicate drift making "assert all compliant" pass on an empty set), and
    forces a new serializer to add matching behavioral coverage below.
    """
    cands = _discover_all()
    serialize = {(c.module, c.qualname) for c in cands if c.kind == "serialize"}
    construct = {(c.module, c.qualname) for c in cands if c.kind == "construct"}
    assert serialize == _EXPECTED_SERIALIZE, (
        f"discovered capability serialize set changed:\n"
        f"  unexpected: {serialize - _EXPECTED_SERIALIZE}\n"
        f"  missing:    {_EXPECTED_SERIALIZE - serialize}"
    )
    assert construct == _EXPECTED_CONSTRUCT, (
        f"discovered capability CONSTRUCT set changed — a new function builds a "
        f"CapabilityAttestation. Add it to _EXPECTED_CONSTRUCT and ensure it is "
        f"producer-compliant (routes the serde, sets signing_payload_version=, "
        f"or is an UNSIGNED emission):\n"
        f"  unexpected: {construct - _EXPECTED_CONSTRUCT}\n"
        f"  missing:    {_EXPECTED_CONSTRUCT - construct}"
    )


def _producer_compliant(
    c: _Candidate, serialize_names: FrozenSet[str], construct_names: FrozenSet[str]
) -> bool:
    """The producer-compliance rule (cross-sdk-inspection.md Rule 4e), by kind.

    * ``serialize`` — routes the fold field OUT through the shared serde, OR
      delegates to another discovered serializer.
    * ``construct`` — routes the field back through the serde (a round-trip
      DESERIALIZER), OR delegates, OR SETS ``signing_payload_version=V1`` at the
      construction (a fresh MINT that originates a subject-bound cap), OR builds
      only UNSIGNED caps (an emission that never reaches the Ed25519 verify path).

    The load-bearing case: a SIGNED cap produced with neither a serde route nor a
    V1 version is NON-compliant — the exact transplant-bug class the CLI sign
    sites shipped (a mint that defaulted to legacy → transplantable).
    """
    if c.kind == "serialize":
        direct = "serialize_capability_fold_fields" in c.called_names
        delegates = bool(c.called_names & (serialize_names - {c.func_name}))
        return direct or delegates
    direct = "deserialize_capability_fold_fields" in c.called_names
    delegates = bool(c.called_names & (construct_names - {c.func_name}))
    return direct or delegates or c.sets_version or c.all_unsigned


def test_every_producer_handles_the_fold_field() -> None:
    cands = _discover_all()
    serialize_names = frozenset(c.func_name for c in cands if c.kind == "serialize")
    construct_names = frozenset(c.func_name for c in cands if c.kind == "construct")

    non_compliant = [
        f"  - {c.module}.{c.qualname} ({c.kind}) — a SIGNED cap produced with no "
        f"serde route AND no signing_payload_version=V1 (transplant-bug class, "
        f"cross-sdk-inspection.md Rule 4e)"
        for c in cands
        if not _producer_compliant(c, serialize_names, construct_names)
    ]
    assert not non_compliant, (
        "the following capability producer(s) do not handle the "
        "signing_payload_version fold field:\n" + "\n".join(non_compliant)
    )


def test_producer_compliance_rule_fires_on_the_bug_class() -> None:
    """NEGATIVE POLE: the compliance rule MUST flag a signed mint that omits the
    version or sets it to legacy, and MUST accept the V1/unsigned/serde forms.

    Without this, the rule could be silently vacuous (always-pass) and give false
    convergence. Synthetic source is fed through the SAME discovery + compliance
    predicate the real sweep uses (cross-sdk-inspection.md Rule 4e negative pole).
    """
    src = (
        "from kailash.trust.chain import CapabilityAttestation\n"
        "def mint_no_version():\n"
        "    return CapabilityAttestation(id='x', signature='sig')\n"
        "def mint_legacy():\n"
        "    return CapabilityAttestation(\n"
        "        id='x', signature='sig',\n"
        "        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY)\n"
        "def mint_v1():\n"
        "    return CapabilityAttestation(\n"
        "        id='x', signature='sig',\n"
        "        signing_payload_version=CAPABILITY_SIGNING_VERSION_V1)\n"
        "def emit_unsigned():\n"
        "    return CapabilityAttestation(id='x', signature='UNSIGNED')\n"
        "def mint_mixed():\n"
        "    a = CapabilityAttestation(\n"
        "        id='x', signature='sig',\n"
        "        signing_payload_version=CAPABILITY_SIGNING_VERSION_V1)\n"
        "    b = CapabilityAttestation(id='y', signature='sig2')\n"
        "    return a, b\n"
        "def deser(d):\n"
        "    v = deserialize_capability_fold_fields(d)\n"
        "    return CapabilityAttestation(id=d['id'], signature=d['sig'], **v)\n"
    )
    cands = _discover_tree("synthetic", ast.parse(src))
    by_name = {c.func_name: c for c in cands}
    construct_names = frozenset(c.func_name for c in cands if c.kind == "construct")
    empty: FrozenSet[str] = frozenset()

    # The bug class MUST be flagged:
    assert not _producer_compliant(by_name["mint_no_version"], empty, construct_names)
    assert not _producer_compliant(by_name["mint_legacy"], empty, construct_names)
    # MIXED mint (one V1 + one legacy SIGNED cap) MUST be flagged — a single
    # V1 construction does not excuse a sibling legacy (transplantable) cap.
    assert not _producer_compliant(by_name["mint_mixed"], empty, construct_names)
    # The correct forms MUST pass:
    assert _producer_compliant(by_name["mint_v1"], empty, construct_names)
    assert _producer_compliant(by_name["emit_unsigned"], empty, construct_names)
    assert _producer_compliant(by_name["deser"], empty, construct_names)


# =============================================================================
# 3. FIXTURES
# =============================================================================


def _v1_cap(**overrides: Any) -> CapabilityAttestation:
    kwargs: Dict[str, Any] = dict(
        id="cap-1912-parity",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only", "no_pii"],
        attester_id="org-acme",
        attested_at=FIXED_TS,
        signature="",
        scope={"tables": ["transactions"]},
        signing_payload_version=CAPABILITY_SIGNING_VERSION_V1,
    )
    kwargs.update(overrides)
    return CapabilityAttestation(**kwargs)


def _legacy_cap() -> CapabilityAttestation:
    return _v1_cap(
        id="cap-legacy", signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY
    )


def _genesis() -> GenesisRecord:
    return GenesisRecord(
        id="gen-parity",
        agent_id=SUBJECT,
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature="gs",
    )


def _chain_with(cap: CapabilityAttestation) -> TrustLineageChain:
    return TrustLineageChain(genesis=_genesis(), capabilities=[cap])


# =============================================================================
# 4. BEHAVIORAL POSITIVE ROUND-TRIP + PRUNE-WHEN-UNSET
# =============================================================================


def _rt_chain(cap: CapabilityAttestation) -> CapabilityAttestation:
    restored = TrustLineageChain.from_dict(_chain_with(cap).to_dict())
    (out,) = restored.capabilities
    return out


def _rt_jwt(cap: CapabilityAttestation) -> CapabilityAttestation:
    return jwt_interop._deserialize_capability(jwt_interop._serialize_capability(cap))


def _rt_w3c(cap: CapabilityAttestation) -> CapabilityAttestation:
    private_key, public_key = generate_keypair()
    vc = w3c_vc.export_as_verifiable_credential(
        _chain_with(cap), issuer_did="did:eatp:org:acme", signing_key=private_key
    )
    restored = w3c_vc.import_from_verifiable_credential(vc, public_key=public_key)
    (out,) = restored.capabilities
    return out


_RT_PAIRS: Tuple[
    Tuple[str, Callable[[CapabilityAttestation], CapabilityAttestation]], ...
] = (
    ("chain._serialize_/_deserialize_capability", _rt_chain),
    ("jwt._serialize_/_deserialize_capability", _rt_jwt),
    ("w3c_vc.export/import_verifiable_credential", _rt_w3c),
)


@pytest.mark.parametrize("label,rt", _RT_PAIRS, ids=[p[0] for p in _RT_PAIRS])
def test_v1_version_survives_every_roundtrippable_serializer(
    label: str, rt: Callable[[CapabilityAttestation], CapabilityAttestation]
) -> None:
    restored = rt(_v1_cap())
    assert restored.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1, (
        f"{label}: signing_payload_version did NOT survive round-trip "
        f"(got {restored.signing_payload_version!r}) — this serializer dropped "
        f"the #1912 subject-binding discriminator."
    )


@pytest.mark.parametrize("label,rt", _RT_PAIRS, ids=[p[0] for p in _RT_PAIRS])
def test_legacy_version_roundtrips_as_legacy(
    label: str, rt: Callable[[CapabilityAttestation], CapabilityAttestation]
) -> None:
    restored = rt(_legacy_cap())
    assert restored.signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY


def test_prune_when_unset_no_version_key_for_legacy_cap() -> None:
    """A legacy cap emits NO version key across EVERY serializer (byte-identical
    to a pre-#1912 dict); a v1 cap emits it."""
    legacy, v1 = _legacy_cap(), _v1_cap()

    # chain-level
    lc = TrustLineageChain._serialize_capability(legacy)
    vc = TrustLineageChain._serialize_capability(v1)
    assert "signing_payload_version" not in lc
    assert vc["signing_payload_version"] == CAPABILITY_SIGNING_VERSION_V1

    # jwt (snake)
    assert "signing_payload_version" not in jwt_interop._serialize_capability(legacy)
    assert (
        jwt_interop._serialize_capability(v1)["signing_payload_version"]
        == CAPABILITY_SIGNING_VERSION_V1
    )

    # w3c_vc (camel)
    assert "signingPayloadVersion" not in w3c_vc._serialize_capability(legacy)
    assert (
        w3c_vc._serialize_capability(v1)["signingPayloadVersion"]
        == CAPABILITY_SIGNING_VERSION_V1
    )

    # sd_jwt (export-only, snake)
    assert "signing_payload_version" not in sd_jwt_interop._serialize_capability_claims(
        legacy
    )
    assert (
        sd_jwt_interop._serialize_capability_claims(v1)["signing_payload_version"]
        == CAPABILITY_SIGNING_VERSION_V1
    )


def test_legacy_chain_cap_dict_is_byte_identical_to_pre_1912() -> None:
    """Empirical byte-identity: a legacy cap's chain-level dict carries EXACTLY
    the pre-#1912 8 keys — no null version key (cross-sdk-inspection.md Rule 4d)."""
    d = TrustLineageChain._serialize_capability(_legacy_cap())
    assert set(d.keys()) == {
        "id",
        "capability",
        "capability_type",
        "constraints",
        "attester_id",
        "attested_at",
        "expires_at",
        "scope",
    }


# =============================================================================
# 5. NEGATIVE POLE — strip the version, the reloaded cap no longer verifies
# =============================================================================


def _strip_chain(cap: CapabilityAttestation) -> CapabilityAttestation:
    d = TrustLineageChain._serialize_capability(cap)
    d.pop("signing_payload_version", None)
    return TrustLineageChain._deserialize_capability(d)


def _strip_jwt(cap: CapabilityAttestation) -> CapabilityAttestation:
    d = jwt_interop._serialize_capability(cap)
    d.pop("signing_payload_version", None)
    return jwt_interop._deserialize_capability(d)


def _strip_w3c(cap: CapabilityAttestation) -> CapabilityAttestation:
    private_key, _ = generate_keypair()
    vc = w3c_vc.export_as_verifiable_credential(
        _chain_with(cap), issuer_did="did:eatp:org:acme", signing_key=private_key
    )
    (cap_dict,) = vc["credentialSubject"]["capabilities"]
    cap_dict.pop("signingPayloadVersion", None)
    # public_key=None skips the VC's OWN proof (a separate concern), leaving the
    # EATP capability signature this test probes.
    restored = w3c_vc.import_from_verifiable_credential(vc, public_key=None)
    (out,) = restored.capabilities
    return out


_STRIP_FNS: Tuple[
    Tuple[str, Callable[[CapabilityAttestation], CapabilityAttestation]], ...
] = (
    ("chain._serialize_/_deserialize_capability", _strip_chain),
    ("jwt._serialize_/_deserialize_capability", _strip_jwt),
    ("w3c_vc.export/import_verifiable_credential", _strip_w3c),
)


@pytest.mark.parametrize("label,strip", _STRIP_FNS, ids=[p[0] for p in _STRIP_FNS])
def test_stripped_version_fails_closed_through_every_serializer(
    label: str, strip: Callable[[CapabilityAttestation], CapabilityAttestation]
) -> None:
    """Strip the version from real wire output; the reloaded (legacy) cap's
    pre-image no longer verifies against the original v1 signature."""
    from kailash.trust.signing.crypto import serialize_for_signing

    private_key, public_key = generate_keypair()
    cap = _v1_cap()
    # Sign over the v1 (subject-bound) pre-image.
    cap.signature = sign(
        serialize_for_signing(cap.to_signing_payload(subject_agent_id=SUBJECT)),
        private_key,
    )

    stripped = strip(cap)
    assert stripped.signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY, (
        f"{label}: fixture bug — stripping the version key should default the "
        f"reloaded cap to legacy"
    )
    # The reloaded legacy cap recomputes WITHOUT the subject; its pre-image no
    # longer matches the v1 signature.
    recomputed = serialize_for_signing(
        stripped.to_signing_payload(subject_agent_id=SUBJECT)
    )
    assert not verify_signature(recomputed, cap.signature, public_key), (
        f"{label}: stripping signing_payload_version from the real wire output "
        f"did NOT invalidate the v1 signature — a downgrade-to-legacy still "
        f"verifies (subject-binding negative pole violated)."
    )


def test_roundtrip_and_strip_pair_counts_match() -> None:
    """Behavioral coverage ties to the round-trippable subset of the discovered
    set (chain + jwt + w3c_vc; sd_jwt is export-only, covered by the
    prune-when-unset emit test)."""
    assert len(_RT_PAIRS) == len(_STRIP_FNS) == 3
