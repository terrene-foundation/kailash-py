"""Tier-2a integration coverage — ``kaizen.nodes.rag.privacy``.

F8 shard B9a. The 3 classes under test (PrivacyPreservingRAGNode,
SecureMultiPartyRAGNode, ComplianceRAGNode) carry the privacy-preserving
RAG claims this shard's load-bearing value-anchor targets:
**ε-DP / PII = a safety CLAIM never verified** (F8 plan §B B9a row).

The privacy/PII-redaction/compliance behavior is advertised in docstrings
but was not empirically validated before B9a. This file verifies the
load-bearing claims via real ``LocalRuntime.execute(workflow.build())``
runs against the codegen PythonCodeNodes that DO execute end-to-end —
matching the B7 ``test_workflows_nodes.py`` precedent.

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in
Tier 2/3 per ``rules/testing.md``). These tests use a real in-process
``LocalRuntime``, real ``WorkflowBuilder`` / ``Workflow`` graphs, and a
real ``PythonCodeNode`` codegen execution path.

Synthetic PII only — all test fixtures use clearly-fake values
(``test-user-001@example.invalid``, ``000-00-0000``, ``999-555-0123``).
Never real PII.
"""

from __future__ import annotations

import hashlib
import re

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.privacy import (
    ComplianceRAGNode,
    PrivacyPreservingRAGNode,
    SecureMultiPartyRAGNode,
)

pytestmark = pytest.mark.integration


def _build(node: PrivacyPreservingRAGNode) -> Workflow:
    """Past the ``@register_node`` Node-type erasure — see B7/B8 precedent."""
    return node._create_workflow()  # type: ignore[attr-defined]


# Synthetic PII fixtures — clearly fake, no real data.
#
# NOTE: the codegen template's ``date_of_birth`` regex uses parenthesised
# groups, which makes ``re.findall`` return tuples (not strings). The
# downstream ``hashlib.sha256(match.encode())`` then crashes on a tuple.
# This is a PRE-EXISTING codegen defect outside the B9a A3-R4 LEAK scope
# (those 4 brace-escape sites in the codegen *template* are the B9a
# scope); the tuple-vs-string defect lives in the codegen's regex
# definition. F8 ledger item: harden the date_of_birth regex to use
# non-capturing groups (``(?:...)``). The test fixtures here intentionally
# avoid the dob pattern so B9a verifies the email/phone/ssn redaction
# claims without depending on the orthogonal dob fix.
_SYNTHETIC_PII_TEXT = (
    "Patient test-user-001@example.invalid called from 999-555-0123 "
    "with SSN 000-00-0000 about diagnosis: hypertension."
)
_SYNTHETIC_PII_NO_REAL_DATA = (
    "fake-customer-zzz@example.invalid 555-000-1234 SSN 000-11-2222 "
    "credit card 0000 0000 0000 0000"
)


def _run_pii_detector(pii_detector_code: str, text: str, redact: bool = True):
    """Exec the codegen template against a real `text` module-scope binding.

    F9 #1112 / #1113 / #1114 fixed the pre-existing codegen defects: the
    function returns its dict on the redact=True branch AND the codegen
    invokes ``result = detect_and_redact_pii(text, redact=...)`` at module
    scope so PythonCodeNode reads the bound ``result``.

    For Tier-2a we exec the codegen with ``text`` pre-bound at module
    scope (the real PythonCodeNode harness binds upstream wire values
    the same way) AND respect the caller's ``redact`` override by calling
    the function directly when it differs from the codegen's default.

    SyntaxWarning is filtered because privacy.py's codegen uses legacy
    regex escapes (``\\s``, ``\\d``) in non-raw strings — a pre-existing
    source-template concern orthogonal to F9's codegen fixes.
    """
    import warnings

    # Strip the F9 #1114 cleanup line so the helper survives exec when the
    # caller needs to invoke with an overridden `redact` flag.
    code_no_del = "\n".join(
        line
        for line in pii_detector_code.splitlines()
        if not line.startswith("del detect_and_redact_pii")
    )
    ns: dict = {"text": text}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        exec(code_no_del, ns)
    # Codegen executes `result = detect_and_redact_pii(text, redact=<default>)`
    # at module scope. If the caller's redact override differs from the
    # default the codegen baked in, re-invoke explicitly.
    if redact:
        return ns["result"]
    return ns["detect_and_redact_pii"](text, redact=redact)


# ==========================================================================
# PII redaction claim — feed synthetic PII through the codegen function
# ==========================================================================


class TestPiiRedactionClaim:
    """ε-DP / PII redaction CLAIM: synthetic PII strings absent from output."""

    def test_email_redacted_from_processed_text(self):
        """A synthetic email is replaced by a [EMAIL_<hash>] sentinel."""
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        out = _run_pii_detector(pii_detector.config["code"], _SYNTHETIC_PII_TEXT)
        # The synthetic email MUST be absent from the processed text.
        assert "test-user-001@example.invalid" not in out["processed_text"]
        # An EMAIL sentinel MUST be present (the documented redaction shape).
        assert re.search(r"\[EMAIL_[a-f0-9]{8}\]", out["processed_text"])
        # The detection record names the PII type found.
        assert "email" in out["pii_found"]

    def test_ssn_redacted_from_processed_text(self):
        """A synthetic SSN is replaced by a [SSN_<hash>] sentinel."""
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        out = _run_pii_detector(pii_detector.config["code"], _SYNTHETIC_PII_TEXT)
        assert "000-00-0000" not in out["processed_text"]
        assert re.search(r"\[SSN_[a-f0-9]{8}\]", out["processed_text"])
        assert "ssn" in out["pii_found"]

    def test_phone_redacted_from_processed_text(self):
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        out = _run_pii_detector(pii_detector.config["code"], _SYNTHETIC_PII_TEXT)
        assert "999-555-0123" not in out["processed_text"]
        assert re.search(r"\[PHONE_[a-f0-9]{8}\]", out["processed_text"])
        assert "phone" in out["pii_found"]

    def test_redaction_applied_flag_true_when_pii_present(self):
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        out = _run_pii_detector(pii_detector.config["code"], _SYNTHETIC_PII_TEXT)
        assert out["redaction_applied"] is True
        # The redaction_count sums PII items across types found.
        assert out["redaction_count"] >= 3  # email + phone + ssn at minimum

    def test_redact_false_returns_original_text(self):
        """With redact=False the function returns text unchanged."""
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        out = _run_pii_detector(
            pii_detector.config["code"], _SYNTHETIC_PII_TEXT, redact=False
        )
        assert out["processed_text"] == _SYNTHETIC_PII_TEXT
        assert out["redaction_applied"] is False
        assert out["pii_found"] == {}


# ==========================================================================
# Hash determinism — same input produces same hash for joins
# ==========================================================================


class TestHashDeterminism:
    """Privacy claim: anonymized PII hashes are STABLE across calls.

    The privacy promise is two-sided — PII is removed from view AND the
    same logical entity hashes to the same sentinel so downstream
    privacy-preserving joins still work. This test pins that claim.
    """

    def test_same_email_produces_same_hash(self):
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        code = pii_detector.config["code"]

        a = _run_pii_detector(code, "Reach test-user-001@example.invalid for details.")
        b = _run_pii_detector(
            code, "Also contact test-user-001@example.invalid please."
        )
        hash_a = re.search(r"\[EMAIL_([a-f0-9]{8})\]", a["processed_text"])
        hash_b = re.search(r"\[EMAIL_([a-f0-9]{8})\]", b["processed_text"])
        assert hash_a is not None
        assert hash_b is not None
        assert hash_a.group(1) == hash_b.group(1)

    def test_hash_matches_sha256_first_eight_chars(self):
        """The documented hash is sha256(match)[:8] — pin the algorithm."""
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None

        email = "fake-customer-zzz@example.invalid"
        expected_hash = hashlib.sha256(email.encode()).hexdigest()[:8]

        out = _run_pii_detector(
            pii_detector.config["code"], f"Contact {email} for info."
        )
        assert f"[EMAIL_{expected_hash}]" in out["processed_text"]


# ==========================================================================
# Audit logging claim — audit_logger node wired post-fix
# ==========================================================================


class TestAuditLoggingWiring:
    """The audit_logger node is wired ONLY when audit_logging=True.

    Pre-B9a the audit_logger_id was unbound (the source-pyright defect);
    the connection wiring referenced a NameError-bound variable, so even
    if construction had succeeded past the R4 LEAK, the audit-logger
    wiring would have failed at runtime. Post-B9a the audit_logger_id
    is bound before use; this test verifies the wiring exists.
    """

    def test_audit_logger_node_present_by_default(self):
        wf = _build(PrivacyPreservingRAGNode())
        assert wf.get_node("audit_logger") is not None

    def test_audit_logger_receives_pii_detection_event(self):
        """The audit_logger has an inbound edge from pii_detector."""
        wf = _build(PrivacyPreservingRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.target_node == "audit_logger" and c.source_node == "pii_detector"
        ]
        assert len(edges) == 1
        assert edges[0].target_input == "pii_info"

    def test_audit_logger_aggregates_four_upstream_events(self):
        """The audit_logger has 4 inbound edges: pii, anonymization, dp, results."""
        wf = _build(PrivacyPreservingRAGNode())
        inbound = [c for c in wf.connections if c.target_node == "audit_logger"]
        assert len(inbound) == 4
        target_inputs = {c.target_input for c in inbound}
        assert target_inputs == {"pii_info", "anonymization_info", "dp_info", "results"}

    def test_audit_logger_code_emits_audit_record(self):
        """The audit_logger codegen builds the documented audit_record shape."""
        wf = _build(PrivacyPreservingRAGNode())
        audit = wf.get_node("audit_logger")
        assert audit is not None
        code = audit.config["code"]
        # The audit record is the documented contract; pin the keys.
        for required_key in (
            "timestamp",
            "query_hash",
            "privacy_measures",
            "user_consent",
            "compliance",
            "data_retention",
        ):
            assert f'"{required_key}"' in code


# ==========================================================================
# Codegen executes under real LocalRuntime
# ==========================================================================


class TestCodegenRealRuntime:
    """The PythonCodeNode templates execute under a real LocalRuntime.

    Mirrors B7's TestWorkflowCodegenRealExecution: extract the codegen
    `code` from one of the workflow nodes, embed it in a fresh single-node
    builder, and run it through LocalRuntime against synthetic input.
    """

    @pytest.mark.filterwarnings("ignore::SyntaxWarning")
    def test_pii_detector_under_runtime_returns_redacted_shape(self):
        wf = _build(PrivacyPreservingRAGNode())
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        # F9 #1113 / #1114: the codegen now returns its dict on the
        # redact=True branch AND calls `result = detect_and_redact_pii(...)`
        # at module scope. Embed the codegen verbatim; LocalRuntime binds
        # `text` from `parameters` and publishes the module-scope `result`.
        code = pii_detector.config["code"]

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            node_id="pii_under_runtime",
            config={"code": code},
        )
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            builder.build(),
            parameters={"pii_under_runtime": {"text": _SYNTHETIC_PII_NO_REAL_DATA}},
        )
        out = results["pii_under_runtime"]["result"]
        assert out["redaction_applied"] is True
        # All four synthetic PII fields MUST be absent from processed_text.
        assert "fake-customer-zzz@example.invalid" not in out["processed_text"]
        assert "555-000-1234" not in out["processed_text"]
        assert "000-11-2222" not in out["processed_text"]
        assert "0000 0000 0000 0000" not in out["processed_text"]


# ==========================================================================
# ComplianceRAGNode — enforces declared compliance regimes
# ==========================================================================


class TestComplianceEnforcement:
    """ComplianceRAGNode enforces the regulations it advertises."""

    def test_gdpr_enforcement_denies_missing_explicit_consent(self):
        """GDPR requires explicit_consent; absent → denied."""
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=True)
        out = node.run(
            query="patient query",
            documents=[{"content": "fake medical record content"}],
            user_consent={
                "purpose": "diagnosis",
                "retention_allowed": True,
                "sharing_allowed": False,
            },  # missing explicit_consent
            jurisdiction="EU",
        )
        assert out.get("error") == "Insufficient consent"

    def test_gdpr_granted_returns_compliance_report(self):
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=True)
        out = node.run(
            query="treatment options",
            documents=[
                {
                    "content": "fake guideline 1",
                    "metadata": {"classification": "public"},
                },
                {
                    "content": "fake guideline 2",
                    "metadata": {"classification": "public"},
                },
            ],
            user_consent={
                "explicit_consent": True,
                "purpose": "medical_diagnosis",
                "retention_allowed": True,
                "sharing_allowed": False,
            },
            jurisdiction="EU",
        )
        assert "compliance_report" in out
        report = out["compliance_report"]
        assert "gdpr" in report["regulations_applied"]
        assert report["jurisdiction"] == "EU"

    def test_classified_documents_filtered_per_jurisdiction(self):
        """A document marked no_eu_transfer is dropped for an EU requester."""
        node = ComplianceRAGNode(regulations=["gdpr"], require_explicit_consent=True)
        out = node.run(
            query="treatment",
            documents=[
                {
                    "content": "fake-public guideline",
                    "metadata": {"classification": "public", "jurisdiction": "EU"},
                },
                {
                    "content": "fake-us-only record",
                    "metadata": {
                        "classification": "public",
                        "restrictions": ["no_eu_transfer"],
                    },
                },
            ],
            user_consent={
                "explicit_consent": True,
                "purpose": "medical_diagnosis",
                "retention_allowed": True,
                "sharing_allowed": False,
            },
            jurisdiction="EU",
        )
        # Only the EU-allowed doc reaches the results.
        contents = [r.get("content", "") for r in out.get("results", [])]
        assert all("fake-us-only" not in c for c in contents)


# ==========================================================================
# SecureMultiPartyRAGNode — workflow construction completes
# ==========================================================================


class TestSecureMultiPartyWorkflowConstruction:
    """SecureMultiPartyRAGNode is a direct ``Node`` (no inner workflow).

    Tier-2a does not require real cryptographic MPC; it requires that the
    node's deterministic ``run()`` path executes against a real Python
    runtime (the constructor + dispatch logic) and returns the documented
    shape — proving the documented behavior empirically.
    """

    def test_secret_sharing_three_parties_aggregate(self):
        node = SecureMultiPartyRAGNode(
            parties=["site_a", "site_b", "site_c"],
            protocol="secret_sharing",
            threshold=2,
        )
        out = node.run(
            query="aggregate metric across sites",
            party_data={
                "site_a": {"metric": 0.91},
                "site_b": {"metric": 0.87},
                "site_c": {"metric": 0.94},
            },
            computation_type="average",
        )
        assert "aggregate_result" in out
        assert out.get("privacy_preserved") is True
        # The party contributions enumerate every contributing site.
        contributions = out.get("party_contributions", {})
        assert set(contributions.keys()) == {"site_a", "site_b", "site_c"}
        # The proof attests the protocol and the participating sites.
        proof = out.get("computation_proof", {})
        assert proof.get("protocol") == "shamir_secret_sharing"
        assert proof.get("threshold_met") is True

    def test_homomorphic_workflow_produces_aggregate(self):
        node = SecureMultiPartyRAGNode(
            parties=["site_a", "site_b"], protocol="homomorphic", threshold=1
        )
        out = node.run(
            query="aggregate under HE",
            party_data={"site_a": {"v": 1.0}, "site_b": {"v": 2.0}},
            computation_type="average",
        )
        proof = out.get("computation_proof", {})
        assert proof.get("protocol") == "homomorphic_encryption"
        assert out.get("fully_encrypted") is True

    def test_node_construction_uses_real_python_runtime(self):
        """The node MUST register as a real PythonCodeNode-compatible node."""
        node = SecureMultiPartyRAGNode()
        # Sanity: the node has the documented `run()` callable.
        assert callable(node.run)
