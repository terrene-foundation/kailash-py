"""Tier 1 unit coverage — ``kaizen.nodes.rag.privacy``.

F8 shard B9a. The 3 classes under test (PrivacyPreservingRAGNode,
SecureMultiPartyRAGNode, ComplianceRAGNode) are the documented
privacy-preserving / multi-party / compliance-aware RAG surface.

Tier 1 scope:

- Construction with default + custom kwargs across all 3 classes.
- ``get_parameters()`` contracts for the 2 direct-``Node`` subclasses.
- The inner workflow GRAPH SHAPE produced by
  ``PrivacyPreservingRAGNode._create_workflow``.
- The deterministic ``run()`` paths on SecureMultiPartyRAGNode +
  ComplianceRAGNode (insufficient-parties / consent-denied / valid).
- Regression coverage for the B9a A3-R4 LEAK fix: PrivacyPreservingRAGNode
  construction MUST NOT raise NameError on the codegen template braces.

Pre-B9a, ``PrivacyPreservingRAGNode()`` raised NameError on `pii_type`,
`hash_value`, `pattern`, `replacement` (the 4 R4 LEAK sites) because the
outer f-string of ``_create_workflow`` tried to interpolate runtime-only
codegen variables. B9a escaped them with double-brace; construction is
now clean. This file is the structural floor that catches a regression.
"""

from __future__ import annotations

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.privacy import (
    ComplianceRAGNode,
    PrivacyPreservingRAGNode,
    SecureMultiPartyRAGNode,
)

pytestmark = pytest.mark.unit


def _build(node: PrivacyPreservingRAGNode) -> Workflow:
    """Call ``node._create_workflow()`` past the ``@register_node`` Node-type erasure.

    Mirrors the B7/B8 ``_build`` precedent: ``@register_node()`` erases the
    concrete subclass to ``Node`` for static checkers, so ``_create_workflow``
    becomes invisible to pyright. The single suppression lets every call site
    stay clean.
    """
    return node._create_workflow()  # type: ignore[attr-defined]


# ==========================================================================
# Construction floor — all three classes
# ==========================================================================


class TestAllThreeConstruct:
    def test_privacy_preserving_constructs_default(self):
        """The R4 LEAK fix is the construction-time regression: a single-brace
        in the outer f-string raised NameError on `pii_type` etc. at the
        ``super().__init__(workflow=self._create_workflow(), name=name)`` call.
        Default construction MUST succeed without raising.
        """
        node = PrivacyPreservingRAGNode()
        assert node is not None
        assert node.metadata.name == "privacy_preserving_rag"

    def test_privacy_preserving_constructs_with_custom_kwargs(self):
        node = PrivacyPreservingRAGNode(
            name="custom_privacy",
            score_noise=0.5,
            redact_pii=False,
            anonymize_queries=False,
            audit_logging=False,
        )
        assert node.metadata.name == "custom_privacy"
        # @register_node erases PrivacyPreservingRAGNode→Node for static
        # checkers; the attrs below are real instance state.
        # score_noise is the honest name for the optional retrieval-score
        # perturbation scale — NOT a differential-privacy epsilon.
        assert node.score_noise == 0.5  # type: ignore[attr-defined]
        assert node.redact_pii is False  # type: ignore[attr-defined]
        assert node.anonymize_queries is False  # type: ignore[attr-defined]
        assert node.audit_logging is False  # type: ignore[attr-defined]

    def test_secure_multiparty_constructs_default(self):
        node = SecureMultiPartyRAGNode()
        assert node is not None
        assert node.metadata.name == "secure_multiparty_rag"
        assert node.parties == []  # type: ignore[attr-defined]
        assert node.protocol == "secret_sharing"  # type: ignore[attr-defined]
        assert node.threshold == 2  # type: ignore[attr-defined]

    def test_secure_multiparty_constructs_with_custom_kwargs(self):
        node = SecureMultiPartyRAGNode(
            name="custom_mpc",
            parties=["site_a", "site_b", "site_c"],
            protocol="homomorphic",
            threshold=3,
        )
        assert node.metadata.name == "custom_mpc"
        assert node.parties == ["site_a", "site_b", "site_c"]  # type: ignore[attr-defined]
        assert node.protocol == "homomorphic"  # type: ignore[attr-defined]
        assert node.threshold == 3  # type: ignore[attr-defined]

    def test_compliance_constructs_default(self):
        node = ComplianceRAGNode()
        assert node is not None
        assert node.metadata.name == "compliance_rag"
        # Default regulations is the documented (gdpr, ccpa) tuple.
        assert node.regulations == ["gdpr", "ccpa"]  # type: ignore[attr-defined]
        assert node.default_retention_days == 30  # type: ignore[attr-defined]
        assert node.require_explicit_consent is True  # type: ignore[attr-defined]

    def test_compliance_constructs_with_custom_kwargs(self):
        node = ComplianceRAGNode(
            name="custom_compliance",
            regulations=["hipaa"],
            default_retention_days=7,
            require_explicit_consent=False,
        )
        assert node.metadata.name == "custom_compliance"
        assert node.regulations == ["hipaa"]  # type: ignore[attr-defined]
        assert node.default_retention_days == 7  # type: ignore[attr-defined]
        assert node.require_explicit_consent is False  # type: ignore[attr-defined]


# ==========================================================================
# get_parameters() contracts — SecureMultiPartyRAGNode + ComplianceRAGNode
# ==========================================================================


class TestSecureMultiPartyParameters:
    def test_required_parameters(self):
        params = SecureMultiPartyRAGNode().get_parameters()
        assert params["query"].required is True
        assert params["query"].type is str
        assert params["party_data"].required is True
        assert params["party_data"].type is dict

    def test_optional_parameters_with_defaults(self):
        params = SecureMultiPartyRAGNode().get_parameters()
        assert params["name"].required is False
        assert params["protocol"].default == "secret_sharing"
        assert params["threshold"].default == 2
        assert params["computation_type"].default == "average"

    def test_parties_parameter_declared(self):
        params = SecureMultiPartyRAGNode().get_parameters()
        assert "parties" in params
        assert params["parties"].type is list


class TestComplianceParameters:
    def test_required_parameters(self):
        params = ComplianceRAGNode().get_parameters()
        assert params["query"].required is True
        assert params["documents"].required is True
        assert params["user_consent"].required is True
        assert params["user_consent"].type is dict

    def test_optional_parameters_with_defaults(self):
        params = ComplianceRAGNode().get_parameters()
        assert params["name"].required is False
        assert params["default_retention_days"].default == 30
        assert params["require_explicit_consent"].default is True
        assert params["jurisdiction"].required is False


# ==========================================================================
# PrivacyPreservingRAGNode inner workflow — graph shape
# ==========================================================================


class TestPrivacyPreservingGraphShape:
    """The _create_workflow inner graph holds the documented 7-node pipeline."""

    def test_default_graph_has_seven_nodes_including_audit_logger(self):
        """With default audit_logging=True the workflow has all 7 nodes."""
        wf = _build(PrivacyPreservingRAGNode())
        assert set(wf.nodes.keys()) == {
            "pii_detector",
            "query_anonymizer",
            "dp_noise_injector",
            "secure_aggregator",
            "private_rag_executor",
            "audit_logger",
            "result_formatter",
        }

    def test_audit_logging_false_omits_audit_logger_node(self):
        """With audit_logging=False the audit_logger node is not built."""
        wf = _build(PrivacyPreservingRAGNode(audit_logging=False))
        assert "audit_logger" not in wf.nodes
        assert {
            "pii_detector",
            "query_anonymizer",
            "dp_noise_injector",
            "secure_aggregator",
            "private_rag_executor",
            "result_formatter",
        }.issubset(set(wf.nodes.keys()))

    def test_audit_logging_false_drops_audit_connections(self):
        """Audit-only connections are not present when audit_logging=False."""
        wf = _build(PrivacyPreservingRAGNode(audit_logging=False))
        audit_edges = [
            c
            for c in wf.connections
            if c.target_node == "audit_logger" or c.source_node == "audit_logger"
        ]
        assert audit_edges == []

    def test_pii_detector_feeds_query_anonymizer(self):
        wf = _build(PrivacyPreservingRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "pii_detector" and c.target_node == "query_anonymizer"
        ]
        assert len(edges) == 1
        assert edges[0].source_output == "result"
        assert edges[0].target_input == "pii_info"

    def test_result_formatter_is_final_sink(self):
        """result_formatter has no outbound edges; it is the final sink."""
        wf = _build(PrivacyPreservingRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_formatter"]
        assert outbound == []
        # It has multiple inbound edges from upstream nodes.
        inbound = [c for c in wf.connections if c.target_node == "result_formatter"]
        assert len(inbound) >= 4  # secure_aggregator, pii_detector, anon, dp_noise

    def test_score_noise_baked_into_perturbation_code(self):
        """The score_noise kwarg flows into the perturbation node code.

        The node perturbs retrieval scores with random noise — this is NOT
        differential privacy and the code MUST NOT claim any DP guarantee.
        """
        wf = _build(PrivacyPreservingRAGNode(score_noise=0.25))
        dp_noise = wf.get_node("dp_noise_injector")
        assert dp_noise is not None
        code = dp_noise.config.get("code", "")
        assert "0.25" in code, "score_noise=0.25 must be baked into perturbation code"
        # Honest-claim guardrail: no differential-privacy guarantee language
        # survives in the generated perturbation code.
        assert "differential privacy" not in code.lower()
        assert "privacy_guarantee" not in code
        assert "actual_epsilon" not in code

    def test_redact_pii_false_baked_into_pii_detector_code(self):
        """redact_pii=False flows into the pii_detector code template."""
        wf = _build(PrivacyPreservingRAGNode(redact_pii=False))
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        code = pii_detector.config.get("code", "")
        # the function signature `detect_and_redact_pii(text, redact=False)`
        assert "redact=False" in code


# ==========================================================================
# PrivacyPreservingRAGNode codegen — outer-template brace handling
# ==========================================================================


class TestCodegenBraceHandling:
    """The R4 LEAK fix: double-brace escapes that survive outer f-string.

    Pre-B9a, the outer f-string interpolated runtime-only variables
    (`pii_type`, `hash_value`, `pattern`, `replacement`) and raised NameError
    before the workflow could even be constructed. Post-B9a, the braces are
    doubled so the inner Python code (run by PythonCodeNode at exec time)
    keeps them as `{pii_type.upper()}` literals — valid f-string syntax that
    the framework resolves at exec time.
    """

    def test_pii_detector_code_contains_runtime_brace_form(self):
        """Inner code must contain {pii_type.upper()}_{hash_value} after escape."""
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        code = pii_detector.config["code"]
        # The double-brace escape produces a single-brace runtime form in the
        # generated Python source — that IS the codegen output the runtime sees.
        assert "{pii_type.upper()}_{hash_value}" in code

    def test_query_anonymizer_code_contains_runtime_brace_form(self):
        """Inner code must contain {pattern}->{replacement} after escape."""
        wf = _build(PrivacyPreservingRAGNode())
        anonymizer = wf.get_node("query_anonymizer")
        assert anonymizer is not None
        code = anonymizer.config["code"]
        assert "{pattern}->{replacement}" in code

    @pytest.mark.filterwarnings("ignore::SyntaxWarning")
    def test_pii_detector_code_parses_as_python(self):
        """The codegen template MUST be syntactically valid Python source.

        A surviving single-brace would crash the outer f-string at workflow
        construction time (the pre-B9a failure mode); a syntax error in the
        inner code would crash ast.parse(). Both are caught.

        SyntaxWarning is filtered because privacy.py's codegen uses legacy
        regex escape sequences (`\\s`, `\\d`) in non-raw strings — a
        pre-existing source-template concern Python 3.12+ surfaces as a
        SyntaxWarning. Orthogonal to the B9a brace-escape fix this test
        verifies; an F9 ledger item to migrate the codegen to raw strings.
        """
        import ast

        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        ast.parse(pii_detector.config["code"], "pii_detector.py", "exec")

    @pytest.mark.filterwarnings("ignore::SyntaxWarning")
    def test_query_anonymizer_code_parses_as_python(self):
        import ast

        wf = _build(PrivacyPreservingRAGNode())
        anonymizer = wf.get_node("query_anonymizer")
        assert anonymizer is not None
        ast.parse(anonymizer.config["code"], "query_anonymizer.py", "exec")


# ==========================================================================
# SecureMultiPartyRAGNode.run() deterministic paths
# ==========================================================================


class TestSecureMultiPartyRun:
    """SecureMultiPartyRAGNode is a NON-FUNCTIONAL simulation (no crypto).

    These tests pin the documented output SHAPE and the honest
    simulation markers — they MUST NOT assert any privacy/encryption
    guarantee, because none is provided.
    """

    def test_run_with_quorum_returns_aggregate_shape(self):
        node = SecureMultiPartyRAGNode(
            parties=["a", "b", "c"], protocol="secret_sharing", threshold=2
        )
        out = node.run(
            query="success rate",
            party_data={"a": {"v": 1}, "b": {"v": 2}, "c": {"v": 3}},
            computation_type="average",
        )
        assert "aggregate_result" in out
        assert "computation_proof" in out
        assert "party_contributions" in out
        # Honest marker: the node self-identifies as a simulation. It MUST NOT
        # claim privacy_preserved / no_raw_data_exposed (no crypto runs).
        assert out.get("simulation") is True
        assert "privacy_preserved" not in out
        assert "no_raw_data_exposed" not in out
        # The "proof" is a simulated record, not a cryptographic proof.
        assert out["computation_proof"].get("protocol") == "simulated_secret_sharing"
        assert out["computation_proof"].get("simulation") is True

    def test_run_insufficient_parties_returns_error(self):
        node = SecureMultiPartyRAGNode(
            parties=["a", "b", "c"], protocol="secret_sharing", threshold=3
        )
        out = node.run(query="x", party_data={"a": 1}, computation_type="sum")
        assert "error" in out
        assert out["required_parties"] == 3

    def test_run_homomorphic_protocol_is_simulated(self):
        node = SecureMultiPartyRAGNode(protocol="homomorphic", threshold=1)
        out = node.run(
            query="x",
            party_data={"a": {"v": 1}, "b": {"v": 2}},
            computation_type="sum",
        )
        proof = out.get("computation_proof", {})
        # Honest label: the homomorphic path is simulated, NOT real HE.
        assert proof.get("protocol") == "simulated_homomorphic"
        assert out.get("simulation") is True
        assert "fully_encrypted" not in out

    def test_run_unknown_protocol_returns_error(self):
        node = SecureMultiPartyRAGNode(protocol="bogus", threshold=1)
        out = node.run(query="x", party_data={"a": 1}, computation_type="average")
        assert "error" in out


# ==========================================================================
# ComplianceRAGNode.run() deterministic paths
# ==========================================================================


class TestComplianceRun:
    def test_run_missing_explicit_consent_denies(self):
        """With require_explicit_consent=True and no explicit_consent: denied."""
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=True)
        out = node.run(
            query="x",
            documents=[],
            user_consent={
                "purpose": "test",
                "retention_allowed": True,
                "sharing_allowed": False,
            },
        )
        assert out.get("error") == "Insufficient consent"
        assert "user_rights" in out

    def test_run_with_explicit_consent_returns_results(self):
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=True)
        out = node.run(
            query="x",
            documents=[],
            user_consent={
                "explicit_consent": True,
                "purpose": "research",
                "retention_allowed": True,
                "sharing_allowed": False,
            },
        )
        assert "results" in out
        assert "compliance_report" in out
        assert "retention_policy" in out
        assert "user_rights" in out

    def test_run_gdpr_user_rights_include_erasure(self):
        """GDPR includes the right to erasure."""
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=False)
        out = node.run(query="x", documents=[], user_consent={}, jurisdiction="EU")
        rights = out.get("user_rights", {})
        # Erasure is the GDPR Article 17 right.
        assert rights.get("erasure") is True

    def test_run_ccpa_user_rights_include_opt_out(self):
        node = ComplianceRAGNode(regulations=["ccpa"], require_explicit_consent=False)
        out = node.run(query="x", documents=[], user_consent={}, jurisdiction="US")
        rights = out.get("user_rights", {})
        assert rights.get("opt_out") is True

    def test_run_compliance_report_carries_regulations_applied(self):
        node = ComplianceRAGNode(
            regulations=["gdpr", "ccpa"], require_explicit_consent=False
        )
        # gdpr+ccpa require all named fields per _validate_consent's
        # required_fields table; supply them so consent is valid.
        out = node.run(
            query="x",
            documents=[],
            user_consent={
                "purpose": "research",
                "retention_allowed": True,
                "sharing_allowed": False,
                "explicit_consent": True,
                "opt_out_option": True,
                "data_categories": ["analytics"],
            },
            jurisdiction="EU",
        )
        report = out.get("compliance_report", {})
        assert set(report.get("regulations_applied", [])) == {"gdpr", "ccpa"}
        assert report.get("jurisdiction") == "EU"

    # GDPR _validate_consent requires all four fields present for a VALID
    # consent (the success path that emits compliance_report). The
    # explicit_consent VALUE then drives the lawful-basis + score derivation.
    _GDPR_WEAK_CONSENT = {
        "purpose": "research",
        "retention_allowed": True,
        "sharing_allowed": False,
        "explicit_consent": False,  # valid shape, but weak (fallback lawful basis)
    }
    _GDPR_STRONG_CONSENT = {
        "purpose": "research",
        "retention_allowed": True,
        "sharing_allowed": False,
        "explicit_consent": True,  # strong: consent-based lawful basis
    }

    def test_data_minimization_false_when_nothing_filtered(self):
        """Honest-claim: data_minimization.applied MUST be False when no
        document was actually redacted/truncated (no classified docs)."""
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=False)
        out = node.run(
            query="x",
            documents=[
                {
                    "content": "fully public doc",
                    "metadata": {"classification": "public"},
                },
            ],
            user_consent=self._GDPR_STRONG_CONSENT,
            jurisdiction="US",
        )
        report = out["compliance_report"]
        # Public-only docs → nothing redacted → minimization did NOT run.
        assert report["data_minimization"]["fields_redacted"] == 0
        assert report["data_minimization"]["applied"] is False

    def test_data_minimization_true_when_classified_docs_filtered(self):
        """data_minimization.applied is True only when filtering actually
        redacted/truncated at least one result."""
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=False)
        out = node.run(
            query="x",
            documents=[
                {"content": "secret", "metadata": {"classification": "confidential"}},
            ],
            user_consent=self._GDPR_STRONG_CONSENT,
            jurisdiction="US",
        )
        report = out["compliance_report"]
        assert report["data_minimization"]["fields_redacted"] >= 1
        assert report["data_minimization"]["applied"] is True

    def test_compliance_score_is_derived_not_hardcoded(self):
        """Honest-claim: compliance_score MUST be derived from real signals,
        not the former magic 0.95. A weak-consent + no-filtering request
        scores strictly below a full-consent + filtering request."""
        weak = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=False)
        weak_out = weak.run(
            query="x",
            documents=[
                {"content": "public", "metadata": {"classification": "public"}},
            ],
            user_consent=self._GDPR_WEAK_CONSENT,  # no explicit consent, no filtering
            jurisdiction="US",
        )
        strong = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=False)
        strong_out = strong.run(
            query="x",
            documents=[
                {"content": "secret", "metadata": {"classification": "confidential"}},
            ],
            user_consent=self._GDPR_STRONG_CONSENT,  # explicit consent + filtering
            jurisdiction="US",
        )
        weak_score = weak_out["compliance_report"]["compliance_score"]
        strong_score = strong_out["compliance_report"]["compliance_score"]
        # Both are real fractions in [0, 1] and the stronger request scores higher.
        assert 0.0 <= weak_score <= 1.0
        assert 0.0 <= strong_score <= 1.0
        assert strong_score > weak_score
        assert weak_score != 0.95 or strong_score != 0.95  # not the old constant


# ==========================================================================
# Module-level __all__ contract
# ==========================================================================


def test_module_all_exports_three_classes():
    """The module exports exactly the 3 documented classes."""
    from kaizen.nodes.rag import privacy

    assert set(privacy.__all__) == {
        "PrivacyPreservingRAGNode",
        "SecureMultiPartyRAGNode",
        "ComplianceRAGNode",
    }
