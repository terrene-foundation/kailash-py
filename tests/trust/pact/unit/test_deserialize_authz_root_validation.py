# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression tests for issue #1480 -- persisted PACT authorization root re-validation.

A ``CompiledOrg`` reconstructed from stored JSON is the authorization root
consumed by ``pact.access.can_access``. Before the fix, ``_deserialize_org``
rebuilt nodes from raw strings WITHOUT re-running the grammar/structural
validation that ``Address.parse`` / ``compile_org`` enforce at build time --
so a tampered persisted org became an unvalidated authorization root.

Covers:
- Address / AddressSegment ``__post_init__`` validators (every construction
  path, including the dataclass ``__init__`` the deserializer uses).
- ``SqliteOrgStore._deserialize_org`` fails closed on grammar-invalid AND
  structurally-inconsistent persisted nodes.
- A legitimate save -> load round-trip still succeeds.
"""

from __future__ import annotations

import json

import pytest

from kailash.trust.pact.addressing import (
    Address,
    AddressError,
    AddressSegment,
    GrammarError,
    NodeType,
    parse_structural_address,
)
from kailash.trust.pact.compilation import CompiledOrg, OrgNode
from kailash.trust.pact.exceptions import DeserializationError, PactError
from kailash.trust.pact.stores.sqlite import SqliteOrgStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "authz-org") -> CompiledOrg:
    """A minimal but grammar-valid compiled org: D1 / D1-R1 / D1-R1-T1 / -R1."""
    org = CompiledOrg(org_id=org_id)
    org.nodes["D1"] = OrgNode(
        address="D1",
        node_type=NodeType.DEPARTMENT,
        name="Engineering",
        node_id="eng",
    )
    org.nodes["D1-R1"] = OrgNode(
        address="D1-R1",
        node_type=NodeType.ROLE,
        name="VP Eng",
        node_id="vp-eng",
        parent_address="D1",
    )
    org.nodes["D1-R1-T1"] = OrgNode(
        address="D1-R1-T1",
        node_type=NodeType.TEAM,
        name="Backend",
        node_id="backend",
        parent_address="D1-R1",
    )
    org.nodes["D1-R1-T1-R1"] = OrgNode(
        address="D1-R1-T1-R1",
        node_type=NodeType.ROLE,
        name="Backend Lead",
        node_id="backend-lead",
        parent_address="D1-R1-T1",
    )
    return org


def _overwrite_persisted_json(store: SqliteOrgStore, org_id: str, data: dict) -> None:
    """Test fixture: overwrite an already-saved org's compiled_json with tampered bytes.

    Mirrors an attacker (or corruption) editing the persisted blob after a
    legitimate save, which is exactly the load-path ``load_org`` exercises.
    """
    conn = store._get_connection()
    with conn:
        conn.execute(
            "UPDATE pact_orgs SET compiled_json = ? WHERE org_id = ?",
            (json.dumps(data), org_id),
        )


# ---------------------------------------------------------------------------
# AC#3 -- __post_init__ validators fire on EVERY construction path
# ---------------------------------------------------------------------------


class TestAddressSegmentPostInit:
    """AddressSegment validates via __init__, not only via parse."""

    def test_direct_construction_rejects_zero_sequence(self) -> None:
        with pytest.raises(AddressError, match="Sequence must be >= 1"):
            AddressSegment(node_type=NodeType.ROLE, sequence=0)

    def test_direct_construction_rejects_negative_sequence(self) -> None:
        with pytest.raises(AddressError, match="Sequence must be >= 1"):
            AddressSegment(node_type=NodeType.ROLE, sequence=-3)

    def test_direct_construction_rejects_non_nodetype(self) -> None:
        with pytest.raises(AddressError, match="node_type must be a NodeType"):
            AddressSegment(node_type="R", sequence=1)  # type: ignore[arg-type]

    def test_direct_construction_rejects_bool_sequence(self) -> None:
        # bool is a subclass of int -- must be rejected explicitly.
        with pytest.raises(AddressError, match="sequence must be an int"):
            AddressSegment(node_type=NodeType.ROLE, sequence=True)  # type: ignore[arg-type]

    def test_valid_direct_construction_still_works(self) -> None:
        seg = AddressSegment(node_type=NodeType.DEPARTMENT, sequence=2)
        assert str(seg) == "D2"


class TestAddressPostInit:
    """Address validates the adjacency grammar via __init__, not only via parse."""

    def test_direct_construction_rejects_adjacency_violation(self) -> None:
        # D immediately followed by D -- adjacency grammar violation.
        with pytest.raises(GrammarError, match="must be immediately followed by R"):
            Address(
                segments=(
                    AddressSegment(NodeType.DEPARTMENT, 1),
                    AddressSegment(NodeType.DEPARTMENT, 2),
                )
            )

    def test_direct_construction_rejects_empty(self) -> None:
        with pytest.raises(AddressError, match="at least one segment"):
            Address(segments=())

    def test_direct_construction_allows_structural_prefix(self) -> None:
        # 'D1' is a valid structural unit reference (Department node address);
        # it is NOT a complete address (Address.parse would reject it) but the
        # dataflow-internal parent/ancestors helpers construct exactly this.
        addr = Address(segments=(AddressSegment(NodeType.DEPARTMENT, 1),))
        assert str(addr) == "D1"

    def test_parent_still_builds_structural_prefix(self) -> None:
        # Regression guard: __post_init__ must NOT break the structural parent.
        parent = Address.parse("D1-R1").parent
        assert parent is not None
        assert str(parent) == "D1"


class TestParseStructuralAddress:
    """parse_structural_address accepts D/T-terminal unit prefixes, rejects bad grammar."""

    @pytest.mark.parametrize("addr", ["D1", "T1", "D1-R1", "D1-R1-T1", "D1-R1-D2"])
    def test_accepts_valid_unit_prefixes(self, addr: str) -> None:
        assert str(parse_structural_address(addr)) == addr

    @pytest.mark.parametrize("addr", ["D1-D2-R1", "D1-T1", "T1-T2"])
    def test_rejects_adjacency_violations(self, addr: str) -> None:
        with pytest.raises(GrammarError):
            parse_structural_address(addr)

    def test_rejects_empty(self) -> None:
        with pytest.raises(AddressError, match="empty"):
            parse_structural_address("")


# ---------------------------------------------------------------------------
# AC#1/#2/#4 -- _deserialize_org re-validates the authorization root
# ---------------------------------------------------------------------------


class TestDeserializeOrgValidation:
    """A tampered persisted org fails closed; a legitimate round-trip succeeds."""

    def test_legitimate_round_trip_succeeds(self) -> None:
        # AC#4: save -> load of a valid org still works.
        store = SqliteOrgStore(":memory:")
        org = _make_compiled_org("authz-org")
        store.save_org(org)

        loaded = store.load_org("authz-org")
        assert loaded is not None
        assert loaded.org_id == "authz-org"
        assert len(loaded.nodes) == 4
        assert loaded.nodes["D1"].node_type == NodeType.DEPARTMENT
        assert loaded.nodes["D1-R1-T1-R1"].node_type == NodeType.ROLE

    def test_grammar_invalid_address_fails_closed(self) -> None:
        # AC#1/#4: a node whose address violates the D/T/R adjacency grammar
        # (D followed by D) must reject the load.
        tampered = {
            "org_id": "authz-org",
            "nodes": {
                "D1-D2-R1": {
                    "address": "D1-D2-R1",
                    "node_type": "R",
                    "name": "Injected",
                    "node_id": "inj",
                    "parent_address": None,
                    "children_addresses": [],
                    "is_vacant": False,
                    "is_external": False,
                }
            },
        }
        with pytest.raises(DeserializationError, match="grammar-invalid address"):
            SqliteOrgStore._deserialize_org(tampered)

    def test_structurally_inconsistent_terminal_type_fails_closed(self) -> None:
        # AC#2/#4: a node whose declared node_type disagrees with the terminal
        # segment of its address (address ends in R but declared DEPARTMENT).
        tampered = {
            "org_id": "authz-org",
            "nodes": {
                "D1-R1": {
                    "address": "D1-R1",
                    "node_type": "D",  # lies: this address terminates in R
                    "name": "Role masquerading as Dept",
                    "node_id": "x",
                    "parent_address": "D1",
                    "children_addresses": [],
                    "is_vacant": False,
                    "is_external": False,
                }
            },
        }
        with pytest.raises(DeserializationError, match="terminates in"):
            SqliteOrgStore._deserialize_org(tampered)

    def test_node_keyed_by_foreign_address_fails_closed(self) -> None:
        # AC#2/#4: the dict key must equal the node's own address.
        tampered = {
            "org_id": "authz-org",
            "nodes": {
                "D1-R1": {
                    "address": "D1-R1-T1-R1",  # key != address
                    "node_type": "R",
                    "name": "Displaced",
                    "node_id": "x",
                    "parent_address": None,
                    "children_addresses": [],
                    "is_vacant": False,
                    "is_external": False,
                }
            },
        }
        with pytest.raises(DeserializationError, match="does not match"):
            SqliteOrgStore._deserialize_org(tampered)

    def test_tampered_load_through_load_org_fails_closed(self) -> None:
        # AC#4 end-to-end: save a valid org, corrupt the persisted blob, then
        # load_org must fail closed rather than return an unvalidated root.
        store = SqliteOrgStore(":memory:")
        store.save_org(_make_compiled_org("authz-org"))

        tampered = {
            "org_id": "authz-org",
            "nodes": {
                "D1-D2-R1": {
                    "address": "D1-D2-R1",
                    "node_type": "R",
                    "name": "Injected",
                    "node_id": "inj",
                    "parent_address": None,
                    "children_addresses": [],
                    "is_vacant": False,
                    "is_external": False,
                }
            },
        }
        _overwrite_persisted_json(store, "authz-org", tampered)

        with pytest.raises(DeserializationError):
            store.load_org("authz-org")

    def test_deserialization_error_is_pact_error(self) -> None:
        # Fail-closed callers catching PactError get the deserialization failure.
        assert issubclass(DeserializationError, PactError)


class TestMalformedBlobFailsClosedWithTypedError:
    """A tampered blob that DROPS a required key or replaces a mapping with a
    non-object MUST fail closed with a typed ``DeserializationError`` (+ .details
    for triage) -- never a bare ``KeyError``/``TypeError`` (consistent taxonomy).
    """

    @pytest.mark.parametrize(
        "blob, detail_key, detail_val",
        [
            ({}, "missing_key", "org_id"),
            ({"org_id": "o1", "nodes": [1, 2]}, "type", "list"),
            ({"org_id": "o1", "nodes": {"D1-R1": "x"}}, "type", "str"),
            (
                {"org_id": "o1", "nodes": {"D1-R1": {"node_type": "R"}}},
                "missing_key",
                "address",
            ),
            (
                {"org_id": "o1", "nodes": {"D1-R1": {"address": "D1-R1"}}},
                "missing_key",
                "node_type",
            ),
            (
                {
                    "org_id": "o1",
                    "nodes": {"D1-R1": {"address": "D1-R1", "node_type": "R"}},
                },
                "missing_key",
                "name",
            ),
            (
                {
                    "org_id": "o1",
                    "nodes": {
                        "D1-R1": {"address": "D1-R1", "node_type": "R", "name": "n"}
                    },
                },
                "missing_key",
                "node_id",
            ),
        ],
    )
    def test_malformed_blob_raises_deserialization_error(
        self, blob: dict, detail_key: str, detail_val: str
    ) -> None:
        with pytest.raises(DeserializationError) as excinfo:
            SqliteOrgStore._deserialize_org(blob)
        assert excinfo.value.details.get(detail_key) == detail_val

    def test_empty_org_with_no_nodes_key_still_loads(self) -> None:
        # "nodes" is optional -- an empty org (no nodes key) is valid, not tampered.
        org = SqliteOrgStore._deserialize_org({"org_id": "empty-org"})
        assert org.org_id == "empty-org"
        assert org.nodes == {}
