# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tier-2 tests for the YAML -> runtime governance-spec engine-application layer.

Issue #1386 disposition (X): governance specs authored in a unified YAML org
file (clearances / envelopes / bridges / ksps) MUST take effect at enforcement
when an engine is built from that YAML. These tests author real YAML, build a
real GovernanceEngine (memory store backend -- the real engine, no mocking per
testing.md Tier 2/3), and assert enforcement via ``check_access`` /
``compute_envelope``. Fail-closed cases assert that a misauthored spec aborts
engine construction rather than silently under-enforcing.

PACT access model note: ``check_access`` step 1 requires the REQUESTING role to
hold a clearance at or above the item's classification, independent of any
KSP/bridge that grants the cross-unit path. The base org below therefore grants
the reading roles a RESTRICTED clearance so the KSP/bridge/deny-precedence tests
exercise the cross-unit path (not the step-1 clearance gate); the clearance test
uses its own org to isolate clearance level as the deciding factor.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from kailash.trust.pact.config import ConfidentialityLevel, TrustPostureLevel
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import MonotonicTighteningError
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.knowledge import KnowledgeItem
from kailash.trust.pact.yaml_loader import ClearanceSpec, ConfigurationError, KspSpec
from kailash.trust.pact.yaml_resolvers import resolve_clearance, resolve_ksp
from pact.engine import PactEngine

# A 3-level org: CEO -> {Eng head (heads d-eng), Fin head (heads d-fin)};
# Eng head -> Eng junior. Eng and Fin are sibling units that cannot read each
# other's data without an explicit KSP or bridge. Reading roles carry a
# RESTRICTED clearance so the step-1 clearance gate passes for RESTRICTED items.
_BASE_ORG = """
org_id: apply-test
name: Apply Test Org
departments:
  - id: d-eng
  - id: d-fin
roles:
  - id: r-ceo
  - id: r-eng-head
    heads: d-eng
    reports_to: r-ceo
  - id: r-eng-junior
    reports_to: r-eng-head
  - id: r-fin-head
    heads: d-fin
    reports_to: r-ceo
clearances:
  - role: r-eng-head
    level: restricted
  - role: r-eng-junior
    level: restricted
  - role: r-fin-head
    level: restricted
"""


def _build_from_yaml(yaml_text: str, tmp_path: Path) -> GovernanceEngine:
    """Write YAML to a file and build a runtime GovernanceEngine from it."""
    org_file = tmp_path / "org.yaml"
    org_file.write_text(textwrap.dedent(yaml_text))
    return PactEngine._create_governance_engine(str(org_file), "memory")


def _role(engine: GovernanceEngine, role_id: str) -> str:
    node = engine.get_org().get_node_by_role_id(role_id)
    assert node is not None, f"role {role_id} not found"
    return node.address


def _unit(engine: GovernanceEngine, unit_id: str) -> str:
    node = engine.get_org().get_node_by_unit_id(unit_id)
    assert node is not None, f"unit {unit_id} not found"
    return node.address


def _can_read(
    engine: GovernanceEngine,
    role_id: str,
    unit_id: str,
    *,
    classification: ConfidentialityLevel = ConfidentialityLevel.RESTRICTED,
    path: str | None = None,
    item_id: str = "i",
) -> bool:
    item = KnowledgeItem(
        item_id=item_id,
        classification=classification,
        owning_unit_address=_unit(engine, unit_id),
        path=path,
        description="",
    )
    return engine.check_access(
        role_address=_role(engine, role_id),
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
    ).allowed


# ---------------------------------------------------------------------------
# KSP applied: grants + shared_paths narrows
# ---------------------------------------------------------------------------


class TestYamlKspApplied:
    def test_yaml_ksp_grants_and_shared_paths_narrows(self, tmp_path: Path) -> None:
        engine = _build_from_yaml(
            _BASE_ORG
            + """
ksps:
  - id: k-eng-to-fin
    source: d-eng
    target: d-fin
    max_classification: confidential
    shared_paths: ["public/*"]
""",
            tmp_path,
        )
        # KSP applied -> Finance can read the path-matching item ...
        assert _can_read(engine, "r-fin-head", "d-eng", path="public/report") is True
        # ... but the shared_paths filter narrows: the non-matching path is denied.
        assert _can_read(engine, "r-fin-head", "d-eng", path="internal/report") is False

    def test_no_ksp_means_cross_unit_denied(self, tmp_path: Path) -> None:
        """Baseline: without a KSP, cross-unit access is denied (no path)."""
        engine = _build_from_yaml(_BASE_ORG, tmp_path)
        assert _can_read(engine, "r-fin-head", "d-eng", path="public/report") is False


# ---------------------------------------------------------------------------
# Clearance applied: enables an access that fails without it (level is the gate)
# ---------------------------------------------------------------------------


class TestYamlClearanceApplied:
    _ORG = """
org_id: clearance-test
name: Clearance Test Org
departments:
  - id: d-fin
roles:
  - id: r-ceo
  - id: r-fin-head
    heads: d-fin
    reports_to: r-ceo
clearances:
  - role: r-fin-head
    level: %s
"""

    def test_yaml_clearance_level_is_the_gate(self, tmp_path: Path) -> None:
        # Sequential builds: each engine is constructed before the next write,
        # so reusing tmp_path (overwriting org.yaml) is safe.
        insufficient = _build_from_yaml(self._ORG % "restricted", tmp_path)
        sufficient = _build_from_yaml(self._ORG % "confidential", tmp_path)

        # CONFIDENTIAL own-unit item: RESTRICTED clearance denies, CONFIDENTIAL allows.
        assert (
            _can_read(
                insufficient,
                "r-fin-head",
                "d-fin",
                classification=ConfidentialityLevel.CONFIDENTIAL,
            )
            is False
        )
        assert (
            _can_read(
                sufficient,
                "r-fin-head",
                "d-fin",
                classification=ConfidentialityLevel.CONFIDENTIAL,
            )
            is True
        )


# ---------------------------------------------------------------------------
# Envelope applied: tightens; widening fails closed; parent-before-child order
# ---------------------------------------------------------------------------


class TestYamlEnvelopeApplied:
    def test_yaml_envelope_tightens(self, tmp_path: Path) -> None:
        engine = _build_from_yaml(
            _BASE_ORG
            + """
envelopes:
  - target: r-eng-head
    defined_by: r-ceo
    financial:
      max_spend_usd: 100.0
""",
            tmp_path,
        )
        effective = engine.compute_envelope(_role(engine, "r-eng-head"))
        assert effective is not None
        assert effective.financial is not None
        assert effective.financial.max_spend_usd == 100.0

    def test_yaml_envelope_parent_before_child_ordering(self, tmp_path: Path) -> None:
        """A child envelope whose defining role also has a YAML envelope is
        applied after its parent (topological order) and tightens correctly."""
        engine = _build_from_yaml(
            _BASE_ORG
            + """
envelopes:
  - target: r-eng-junior
    defined_by: r-eng-head
    financial:
      max_spend_usd: 50.0
  - target: r-eng-head
    defined_by: r-ceo
    financial:
      max_spend_usd: 100.0
""",
            tmp_path,
        )
        head_env = engine.compute_envelope(_role(engine, "r-eng-head"))
        junior_env = engine.compute_envelope(_role(engine, "r-eng-junior"))
        assert head_env is not None and head_env.financial is not None
        assert junior_env is not None and junior_env.financial is not None
        assert head_env.financial.max_spend_usd == 100.0
        assert junior_env.financial.max_spend_usd == 50.0

    def test_yaml_envelope_widening_fails_closed(self, tmp_path: Path) -> None:
        """A child envelope wider than its YAML parent aborts construction."""
        with pytest.raises((MonotonicTighteningError, PactError)):
            _build_from_yaml(
                _BASE_ORG
                + """
envelopes:
  - target: r-eng-head
    defined_by: r-ceo
    financial:
      max_spend_usd: 100.0
  - target: r-eng-junior
    defined_by: r-eng-head
    financial:
      max_spend_usd: 1000.0
""",
                tmp_path,
            )


# ---------------------------------------------------------------------------
# Bridge applied: grants cross-unit access (LCA-approved from YAML)
# ---------------------------------------------------------------------------


class TestYamlBridgeApplied:
    def test_yaml_bridge_grants_cross_unit_access(self, tmp_path: Path) -> None:
        engine = _build_from_yaml(
            _BASE_ORG
            + """
bridges:
  - id: b-eng-fin
    role_a: r-eng-head
    role_b: r-fin-head
    type: standing
    max_classification: restricted
""",
            tmp_path,
        )
        # Without the bridge eng-head cannot read d-fin; with it, it can.
        assert _can_read(engine, "r-eng-head", "d-fin") is True

    def test_no_bridge_means_cross_unit_denied(self, tmp_path: Path) -> None:
        engine = _build_from_yaml(_BASE_ORG, tmp_path)
        assert _can_read(engine, "r-eng-head", "d-fin") is False


# ---------------------------------------------------------------------------
# Deny-precedence: a denying KSP suppresses a permissive bridge (YAML path)
# ---------------------------------------------------------------------------


class TestYamlDenyPrecedence:
    def test_denying_ksp_suppresses_permissive_bridge(self, tmp_path: Path) -> None:
        # Bridge would grant eng-head <-> fin-head; a KSP fin->eng that matches
        # the addressing but narrows by path is matching-but-denying for the
        # non-matching path, and suppresses the bridge fallback.
        engine = _build_from_yaml(
            _BASE_ORG
            + """
bridges:
  - id: b-eng-fin
    role_a: r-eng-head
    role_b: r-fin-head
    type: standing
    max_classification: secret
ksps:
  - id: k-fin-to-eng
    source: d-fin
    target: d-eng
    max_classification: secret
    shared_paths: ["allowed/*"]
""",
            tmp_path,
        )
        # Matching-but-denying KSP (path miss) suppresses the permissive bridge.
        assert _can_read(engine, "r-eng-head", "d-fin", path="confidential/x") is False
        # KSP grants the path-matching item.
        assert _can_read(engine, "r-eng-head", "d-fin", path="allowed/x") is True


# ---------------------------------------------------------------------------
# dict-path parity: specs applied from an in-memory dict too
# ---------------------------------------------------------------------------


class TestDictPathParity:
    def test_dict_path_applies_ksp(self) -> None:
        org = {
            "org_id": "apply-test",
            "name": "Apply Test Org",
            "departments": [{"id": "d-eng"}, {"id": "d-fin"}],
            "roles": [
                {"id": "r-ceo"},
                {"id": "r-eng-head", "heads": "d-eng", "reports_to": "r-ceo"},
                {"id": "r-fin-head", "heads": "d-fin", "reports_to": "r-ceo"},
            ],
            "clearances": [{"role": "r-fin-head", "level": "restricted"}],
            "ksps": [
                {
                    "id": "k-eng-to-fin",
                    "source": "d-eng",
                    "target": "d-fin",
                    "max_classification": "confidential",
                    "shared_paths": ["public/*"],
                }
            ],
        }
        engine = PactEngine._create_governance_engine(org, "memory")
        assert _can_read(engine, "r-fin-head", "d-eng", path="public/report") is True
        assert _can_read(engine, "r-fin-head", "d-eng", path="internal/report") is False


# ---------------------------------------------------------------------------
# Fail-closed: misauthored specs abort engine construction
# ---------------------------------------------------------------------------


class TestYamlApplyFailClosed:
    def test_ksp_unknown_source_unit_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            _build_from_yaml(
                _BASE_ORG
                + """
ksps:
  - id: k-bad
    source: d-nonexistent
    target: d-fin
    max_classification: confidential
""",
                tmp_path,
            )

    def test_clearance_unknown_role_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            _build_from_yaml(
                """
org_id: bad
name: Bad
departments:
  - id: d-fin
roles:
  - id: r-fin-head
    heads: d-fin
clearances:
  - role: r-nonexistent
    level: secret
""",
                tmp_path,
            )

    def test_ksp_invalid_classification_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            _build_from_yaml(
                _BASE_ORG
                + """
ksps:
  - id: k-bad-level
    source: d-eng
    target: d-fin
    max_classification: ultra-mega-secret
""",
                tmp_path,
            )

    def test_ksp_path_traversal_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            _build_from_yaml(
                _BASE_ORG
                + """
ksps:
  - id: k-traversal
    source: d-eng
    target: d-fin
    max_classification: confidential
    shared_paths: ["../secrets/*"]
""",
                tmp_path,
            )

    def test_envelope_nan_gradient_threshold_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            _build_from_yaml(
                _BASE_ORG
                + """
envelopes:
  - target: r-eng-head
    defined_by: r-ceo
    gradient_thresholds:
      financial:
        auto_approve_threshold: .nan
        flag_threshold: 10.0
        hold_threshold: 20.0
""",
                tmp_path,
            )


# ---------------------------------------------------------------------------
# Audit attribution: YAML-resolved specs name the org-definition authority
# ---------------------------------------------------------------------------


class TestYamlAuthorityAttribution:
    def test_resolved_specs_carry_yaml_authority_attribution(
        self, tmp_path: Path
    ) -> None:
        # A YAML-authored clearance/KSP records the org-definition author as the
        # grantor/creator (not an empty/anonymous string) for the audit trail.
        engine = _build_from_yaml(_BASE_ORG, tmp_path)
        compiled = engine.get_org()

        _, clearance = resolve_clearance(
            ClearanceSpec(role_id="r-fin-head", level="restricted"), compiled
        )
        assert clearance.granted_by_role_address == "yaml-org-definition"

        ksp = resolve_ksp(
            KspSpec(
                id="k",
                source="d-eng",
                target="d-fin",
                max_classification="confidential",
            ),
            compiled,
        )
        assert ksp.created_by_role_address == "yaml-org-definition"
