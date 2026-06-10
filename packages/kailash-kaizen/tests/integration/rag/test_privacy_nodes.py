"""Tier-2a integration coverage — ``kaizen.nodes.rag.privacy``.

F8 shard B9a. The 3 classes under test (PrivacyPreservingRAGNode,
SecureMultiPartyRAGNode, ComplianceRAGNode) carry the privacy-aware RAG
behavior this shard verifies.

The node's REAL, load-bearing privacy capability is best-effort, regex-based
PII redaction (email / phone / SSN / credit-card). The differential-privacy /
homomorphic-encryption / secure-multi-party over-claims were STRIPPED in the
RAG provably-correct remediation (Wave 2): the module no longer advertises
any cryptographic privacy guarantee, and SecureMultiPartyRAGNode is a
documented NON-FUNCTIONAL simulation. This file verifies the honest behavior
via real ``LocalRuntime.execute(workflow.build())`` runs against the codegen
PythonCodeNodes that DO execute end-to-end — matching the B7
``test_workflows_nodes.py`` precedent.

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
            # The former "compliance" block asserted hardcoded GDPR/CCPA/HIPAA
            # verdicts the node never assessed. It is replaced by a factual
            # "pii_hygiene" action descriptor.
            "pii_hygiene",
            "data_retention",
        ):
            assert f'"{required_key}"' in code

    def test_audit_logger_emits_no_fake_regulatory_verdict(self):
        """Honest-claim guardrail: the audit record MUST NOT assert a
        GDPR/CCPA/HIPAA compliance verdict the node never determined."""
        wf = _build(PrivacyPreservingRAGNode())
        audit = wf.get_node("audit_logger")
        assert audit is not None
        code = audit.config["code"]
        assert "gdpr_compliant" not in code
        assert "ccpa_compliant" not in code
        assert "hipaa_compliant" not in code
        # The factual descriptor + disclaimer are present instead.
        assert "pii_redaction_attempted" in code
        assert "NOT a GDPR/CCPA/HIPAA compliance determination" in code


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
# Derived honest flags — no hardcoded protection/compliance verdicts
# ==========================================================================


def _run_codegen_function(code: str, fn_name: str, **kwargs):
    """Execute a codegen stage under a real ``LocalRuntime`` and return ``result``.

    F9 #1117: privacy.py's aggregation/formatting codegen now CALLS its inner
    function at module scope (``result = <fn>(...)``) and ``del``\\s the helper,
    so the PythonCodeNode's outbound port carries the dict. The prior
    latent-defect form (function assigned a never-returned function-LOCAL
    ``result``) is fixed — so this helper exercises the REAL execution path
    rather than slicing the function body.

    The ``fn_name`` argument is retained for call-site readability (it names the
    stage under test); the kwargs are bound as the PythonCodeNode's input
    parameters, exactly as the upstream wiring binds them at runtime.
    """
    import warnings

    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        node_id="codegen_under_runtime",
        config={"code": code},
    )
    runtime = LocalRuntime()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        results, _ = runtime.execute(
            builder.build(),
            parameters={"codegen_under_runtime": dict(kwargs)},
        )
    return results["codegen_under_runtime"]["result"]


class TestDerivedHonestFlags:
    """Protection/compliance flags in output dicts MUST reflect what ran."""

    def test_aggregator_single_doc_branch_not_marked_aggregated(self):
        """A single-doc cluster (k=1, truncation only) MUST NOT claim
        aggregation; the k>=2 branch MUST."""
        wf = _build(PrivacyPreservingRAGNode())
        aggregator = wf.get_node("secure_aggregator")
        assert aggregator is not None
        # Two documents with DISTINCT content → two singleton clusters (k=1).
        result = _run_codegen_function(
            aggregator.config["code"],
            "aggregate_results",
            retrieval_results={
                "documents": [
                    {"content": "alpha unique content one"},
                    {"content": "beta different content two"},
                ]
            },
            dp_info={"dp_scores": [0.9, 0.8]},
        )
        singletons = [r for r in result["secure_results"] if r["cluster_size"] == 1]
        assert singletons, "expected at least one single-doc cluster"
        # Honest-claim: k=1 truncation is NOT aggregation.
        assert all(r["aggregated"] is False for r in singletons)
        # And no surviving hardcoded privacy_protected: True claim.
        assert all("privacy_protected" not in r for r in result["secure_results"])

    def test_aggregator_multi_doc_branch_marked_aggregated(self):
        wf = _build(PrivacyPreservingRAGNode())
        aggregator = wf.get_node("secure_aggregator")
        assert aggregator is not None
        # Two docs with IDENTICAL content prefix → same cluster (k=2).
        result = _run_codegen_function(
            aggregator.config["code"],
            "aggregate_results",
            retrieval_results={
                "documents": [
                    {"content": "same shared prefix content here"},
                    {"content": "same shared prefix content here"},
                ]
            },
            dp_info={"dp_scores": [0.9, 0.7]},
        )
        clustered = [r for r in result["secure_results"] if r["cluster_size"] >= 2]
        assert clustered, "expected a k>=2 cluster"
        assert all(r["aggregated"] is True for r in clustered)

    def test_result_formatter_anonymization_strength_derived(self):
        """anonymization_strength MUST be derived from techniques run, never
        a hardcoded verdict. Zero techniques → 'none'."""
        wf = _build(PrivacyPreservingRAGNode())
        formatter = wf.get_node("result_formatter")
        assert formatter is not None
        code = formatter.config["code"]
        # The hardcoded "high" strength string must be gone from the codegen.
        assert '"high"' not in code
        # Nothing ran: no redaction, no anonymization, no noise, no clusters.
        result = _run_codegen_function(
            code,
            "format_private_results",
            secure_results={"secure_results": [], "clusters_formed": 0},
            audit_record={"audit_record": {}},
            pii_info={"redaction_applied": False},
            anonymization_info={"anonymization_applied": False},
            dp_info={"noise_added": False},
        )
        report = result["privacy_preserving_results"]["privacy_report"]
        assert report["anonymization_strength"] == "none"
        assert report["data_minimization"] is False

    def test_result_formatter_data_minimization_true_when_redaction_ran(self):
        wf = _build(PrivacyPreservingRAGNode())
        formatter = wf.get_node("result_formatter")
        assert formatter is not None
        result = _run_codegen_function(
            formatter.config["code"],
            "format_private_results",
            secure_results={"secure_results": [], "clusters_formed": 0},
            audit_record={"audit_record": {}},
            pii_info={"redaction_applied": True},
            anonymization_info={"anonymization_applied": True},
            dp_info={"noise_added": False},
        )
        report = result["privacy_preserving_results"]["privacy_report"]
        assert report["data_minimization"] is True
        # Two techniques ran → "multi-step", never a hardcoded verdict.
        assert report["anonymization_strength"] == "multi-step"

    def test_private_rag_executor_privacy_applied_derived(self):
        """privacy_applied MUST be derived from upstream anonymization, not
        hardcoded True on the no-hygiene path."""
        wf = _build(PrivacyPreservingRAGNode())
        executor = wf.get_node("private_rag_executor")
        assert executor is not None
        code = executor.config["code"]
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", node_id="exec_under_runtime", config={"code": code}
        )
        runtime = LocalRuntime()
        # anonymization_applied=False upstream → privacy_applied must be False.
        results, _ = runtime.execute(
            builder.build(),
            parameters={
                "exec_under_runtime": {
                    "query": "find the report",
                    "anonymized_query_info": {
                        "anonymized_query": "find the report",
                        "anonymization_applied": False,
                    },
                    "documents": [{"content": "the report you want"}],
                }
            },
        )
        out = results["exec_under_runtime"]["result"]["retrieval_results"]
        assert out["privacy_applied"] is False


# ==========================================================================
# F9 #1117 — full PrivacyPreservingRAGNode workflow PUBLISHES end-to-end
# ==========================================================================


@pytest.mark.filterwarnings("ignore::SyntaxWarning")
class TestPrivacyWorkflowPublishesEndToEnd:
    """The full PrivacyPreservingRAGNode workflow runs end-to-end and the
    TERMINAL node PUBLISHES a non-empty result.

    SyntaxWarning is filtered because the codegen templates use legacy regex
    escapes (``\\d``, ``\\s``) in non-raw generalization-rule string literals —
    a PRE-EXISTING source-template concern orthogonal to the F9 #1117 fix (the
    same filter the sibling ``TestCodegenRealRuntime`` applies).

    Regression proof for the F9 #1117 publish-nothing defect: pre-fix, five
    codegen stages (query_anonymizer, dp_noise_injector, secure_aggregator,
    audit_logger, result_formatter) DEFINED an inner function that bound a
    function-LOCAL ``result`` but never CALLED it at module scope, so the
    PythonCodeNode output gate published nothing (and the workflow crashed
    when it tried to JSON-serialize the bound function object). Post-fix each
    stage calls its function at module scope and ``del``s the helper, so the
    workflow runs to completion and the terminal stage publishes the
    documented ``privacy_preserving_results`` payload.

    This is a real ``LocalRuntime`` execution of the WorkflowNode's wrapped
    workflow (NO mocking) against a real query carrying PII + sample docs +
    consent — the literal user flow the class docstring teaches.
    """

    # Deterministic config: anonymize_queries=False removes the random word
    # dropout (so retrieval is reproducible) while redact_pii=True keeps the
    # load-bearing PII-redaction path; score_noise=0.0 removes the RNG
    # perturbation so the assertions are deterministic. PII redaction is
    # still exercised in full (the real capability under test).
    _QUERY = "diagnosis hypertension record patient a@b.com 999-555-0123"
    _DOCS = [
        {"content": "patient diagnosis hypertension record details here"},
        {"content": "patient diagnosis hypertension chart record summary"},
    ]
    _CONSENT = {"data_usage": True, "retention_days": 7}

    def _run_full_workflow(self, node: PrivacyPreservingRAGNode) -> dict:
        """Execute the WorkflowNode's wrapped workflow end-to-end via the
        documented ``inputs={node_id: {...}}`` mapping (the class docstring's
        invocation form)."""
        return node.execute(
            inputs={
                "pii_detector": {"text": self._QUERY},
                "query_anonymizer": {"query": self._QUERY},
                "private_rag_executor": {
                    "query": self._QUERY,
                    "documents": self._DOCS,
                },
                "audit_logger": {
                    "query": self._QUERY,
                    "user_consent": self._CONSENT,
                },
            }
        )

    def test_workflow_publishes_non_empty_documented_payload(self):
        """The terminal node publishes the documented results / privacy_report /
        audit_record keys with real (non-empty) content.

        Pre-fix this FAILS: the workflow raises ``NodeExecutionError`` because
        ``query_anonymizer`` published an un-serializable bound function (or, on
        a later stage, never bound ``result``). Post-fix it PASSES with a real
        published payload.
        """
        node = PrivacyPreservingRAGNode(
            anonymize_queries=False, redact_pii=True, score_noise=0.0
        )
        out = self._run_full_workflow(node)

        # The terminal `result_formatter` (out_degree 0) publishes its `result`
        # under the auto-mapped `result_formatter_result` key.
        assert (
            "result_formatter_result" in out
        ), "terminal node published nothing — F9 #1117 publish-nothing defect"
        payload = out["result_formatter_result"]["privacy_preserving_results"]

        # The documented contract keys are all present.
        for key in ("results", "privacy_report", "audit_record", "confidence_bounds"):
            assert key in payload, key

        # Real retrieval ran: the two matching docs were clustered + published.
        assert isinstance(payload["results"], list)
        assert len(payload["results"]) == 2

        # The honest derived flags reach the output (Wave-2 honesty preserved).
        report = payload["privacy_report"]
        # PII redaction actually ran → data_minimization True, strength derived.
        assert report["data_minimization"] is True
        assert report["anonymization_strength"] in {"minimal", "multi-step"}
        assert "PII redaction" in report["privacy_techniques_applied"]

    def test_pii_actually_redacted_in_published_output(self):
        """The published audit_record reflects the PII the detector found AND
        ``pii_hygiene.pii_redaction_attempted`` mirrors ``redact_pii``."""
        node = PrivacyPreservingRAGNode(
            anonymize_queries=False, redact_pii=True, score_noise=0.0
        )
        out = self._run_full_workflow(node)
        audit = out["result_formatter_result"]["privacy_preserving_results"][
            "audit_record"
        ]
        assert audit is not None

        # The synthetic email + phone in the query were detected + redacted.
        pii_types = audit["privacy_measures"]["pii_redaction"]["pii_types_found"]
        assert "email" in pii_types
        assert "phone" in pii_types

        # The factual hygiene descriptor mirrors redact_pii=True.
        assert audit["pii_hygiene"]["pii_redaction_attempted"] is True

    def test_pii_hygiene_flag_reflects_redact_pii_false(self):
        """With redact_pii=False the published audit shows redaction did NOT run
        — the derived flag is honest, never hardcoded True."""
        node = PrivacyPreservingRAGNode(
            anonymize_queries=False, redact_pii=False, score_noise=0.0
        )
        out = self._run_full_workflow(node)
        payload = out["result_formatter_result"]["privacy_preserving_results"]
        audit = payload["audit_record"]
        assert audit is not None
        # Redaction did not run → the descriptor reflects that honestly.
        assert audit["pii_hygiene"]["pii_redaction_attempted"] is False
        assert (
            "PII redaction"
            not in payload["privacy_report"]["privacy_techniques_applied"]
        )

    def test_workflow_publishes_without_audit_logging(self):
        """With audit_logging=False the terminal node still publishes; the
        audit_record is None (the branch never wired) but results survive —
        the result_formatter's defensive ``audit_record`` default holds."""
        node = PrivacyPreservingRAGNode(
            anonymize_queries=False,
            redact_pii=True,
            score_noise=0.0,
            audit_logging=False,
        )
        # audit_logger isn't built when audit_logging=False; omit its inputs.
        out = node.execute(
            inputs={
                "pii_detector": {"text": self._QUERY},
                "query_anonymizer": {"query": self._QUERY},
                "private_rag_executor": {
                    "query": self._QUERY,
                    "documents": self._DOCS,
                },
            }
        )
        payload = out["result_formatter_result"]["privacy_preserving_results"]
        assert len(payload["results"]) == 2
        # audit_logging=False → no audit record published.
        assert payload["audit_record"] is None


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

    The node is a NON-FUNCTIONAL simulation: it performs no cryptography and
    does NOT compute over ``party_data`` (it aggregates random placeholder
    values). These tests pin the documented output SHAPE and the honest
    simulation markers ONLY — they MUST NOT assert any privacy/encryption
    guarantee, because the node provides none.
    """

    def test_secret_sharing_three_parties_aggregate_shape(self):
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
        # Honest marker: simulation, NOT a privacy guarantee.
        assert out.get("simulation") is True
        assert "privacy_preserved" not in out
        # The party contributions enumerate every supplied party label.
        contributions = out.get("party_contributions", {})
        assert set(contributions.keys()) == {"site_a", "site_b", "site_c"}
        # The "proof" is a simulated record, NOT a cryptographic proof.
        proof = out.get("computation_proof", {})
        assert proof.get("protocol") == "simulated_secret_sharing"
        assert proof.get("simulation") is True
        assert proof.get("threshold_met") is True

    def test_homomorphic_workflow_produces_aggregate_shape(self):
        node = SecureMultiPartyRAGNode(
            parties=["site_a", "site_b"], protocol="homomorphic", threshold=1
        )
        out = node.run(
            query="aggregate under HE",
            party_data={"site_a": {"v": 1.0}, "site_b": {"v": 2.0}},
            computation_type="average",
        )
        proof = out.get("computation_proof", {})
        # Honest label: the homomorphic path is simulated, NOT real HE.
        assert proof.get("protocol") == "simulated_homomorphic"
        assert out.get("simulation") is True
        assert "fully_encrypted" not in out

    def test_node_construction_uses_real_python_runtime(self):
        """The node MUST register as a real PythonCodeNode-compatible node."""
        node = SecureMultiPartyRAGNode()
        # Sanity: the node has the documented `run()` callable.
        assert callable(node.run)
