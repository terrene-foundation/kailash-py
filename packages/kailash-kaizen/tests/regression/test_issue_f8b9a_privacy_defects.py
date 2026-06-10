"""Regression: latent ``kaizen.nodes.rag.privacy`` defects (F8 B9a).

F8 shard B9a owns the A3-triage-gated fixes for ``privacy.py``:

R4 LEAK — single-brace f-string substitutions in codegen templates.
  PrivacyPreservingRAGNode._create_workflow() embedded 4 single-brace
  f-string substitutions inside the outer f-string-wrapped PythonCodeNode
  `code=` templates. The outer f-string tried to interpolate them at
  compile time and raised NameError on `pii_type` / `hash_value` /
  `pattern` / `replacement` (runtime-only variables of the inner
  PythonCodeNode codegen). The construction was blocked entirely; the
  resurrection xfail in test_rag_resurrection_import_smoke.py was the
  only signal.

  Sites fixed (privacy.py):
    - line 152: `{hash_value}` + `{pii_type.upper()}` in pii_detector
    - line 221: `{pattern}` + `{replacement}` in query_anonymizer
  Each escape doubles the braces in the outer f-string so the inner
  Python code keeps the single-brace form the framework resolves at
  runtime.

Pyright cleanup — audit_logger_id unbound + Workflow return-type.
  ``audit_logger_id`` was bound only inside ``if self.audit_logging:`` yet
  referenced unconditionally on later lines (5 sites). Fix: initialize to
  None at function entry; narrow with assert when the audit branch fires.

  ``_create_workflow`` was annotated ``-> Node`` but builder.build() returns
  ``Workflow`` (same register_node type-erasure precedent fixed in B7/B8).
  Fix: import kailash.workflow.graph.Workflow + update annotation.

  ``parties: List[str] = None`` + ``regulations: List[str] = None`` —
  default None is not assignable to List[str]. Fix: Optional[List[str]].

Tests are behavioral: import / construct / introspect the workflow graph;
never source-grep.
"""

from __future__ import annotations

import inspect
import typing

import pytest

from kaizen.nodes.rag.privacy import (
    ComplianceRAGNode,
    PrivacyPreservingRAGNode,
    SecureMultiPartyRAGNode,
)

pytestmark = pytest.mark.regression


# ==========================================================================
# R4 LEAK — codegen template brace escapes
# ==========================================================================


class TestR4LeakBraceEscapes:
    """PrivacyPreservingRAGNode construction MUST NOT raise NameError.

    Pre-B9a, ``_create_workflow``'s outer f-string contained 4 single-brace
    substitutions referencing names defined only inside the inner
    PythonCodeNode codegen (`pii_type`, `hash_value`, `pattern`,
    `replacement`). The outer f-string raised NameError at the
    ``super().__init__(workflow=self._create_workflow(), name=name)`` call
    — the construction was blocked entirely on every PrivacyPreservingRAGNode
    instantiation.
    """

    def test_privacy_node_constructs_without_nameerror(self):
        """The pre-B9a failure raised NameError: name 'pii_type' is not defined."""
        node = PrivacyPreservingRAGNode()
        assert node is not None

    def test_privacy_node_constructs_with_all_kwargs(self):
        """Custom kwargs MUST also construct cleanly (no kwarg drops the fix)."""
        node = PrivacyPreservingRAGNode(
            score_noise=0.1,
            redact_pii=True,
            anonymize_queries=True,
            audit_logging=True,
        )
        assert node is not None

    def test_pii_detector_template_uses_double_brace_escape(self):
        """Inner codegen must contain `{pii_type.upper()}_{hash_value}` runtime form.

        The double-brace escape in the source f-string survives the outer
        f-string evaluation and lands as a single-brace runtime form in
        the generated Python source — that IS the codegen output the
        framework's PythonCodeNode resolves at exec time.
        """
        node = PrivacyPreservingRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        pii_detector = wf.get_node("pii_detector")
        assert pii_detector is not None
        code = pii_detector.config["code"]
        # Double-brace in source → single-brace in generated code.
        assert "{pii_type.upper()}_{hash_value}" in code

    def test_query_anonymizer_template_uses_double_brace_escape(self):
        """Inner codegen must contain `{pattern}->{replacement}` runtime form."""
        node = PrivacyPreservingRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        anonymizer = wf.get_node("query_anonymizer")
        assert anonymizer is not None
        code = anonymizer.config["code"]
        assert "{pattern}->{replacement}" in code


# ==========================================================================
# Pyright cleanup — audit_logger_id unbound + Workflow return-type
# ==========================================================================


class TestPyrightCleanup:
    """The 6 pre-existing pyright defects in privacy.py are resolved."""

    def test_audit_logger_id_runtime_safe_when_audit_logging_true(self):
        """audit_logger_id is bound before the connection wiring loop fires.

        Pre-B9a pyright flagged audit_logger_id as reportPossiblyUnbound at
        5 sites because the variable was bound only inside the
        `if self.audit_logging:` block but used unconditionally on lines
        564-588. The B9a fix initializes audit_logger_id to None at
        function entry; the typed narrow asserts non-None inside the
        audit_logging branch.

        Behavioral guard: construction with audit_logging=True MUST land
        the audit_logger node + 5 wiring connections (no AttributeError on
        the wiring loop's audit_logger_id reference).
        """
        node = PrivacyPreservingRAGNode(audit_logging=True)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert wf.get_node("audit_logger") is not None
        # 5 connections that name audit_logger as source/target.
        audit_connections = [
            c
            for c in wf.connections
            if c.source_node == "audit_logger" or c.target_node == "audit_logger"
        ]
        assert len(audit_connections) == 5

    def test_audit_logger_id_runtime_safe_when_audit_logging_false(self):
        """With audit_logging=False the audit_logger branch never fires.

        Pre-B9a, with audit_logging=False, ``audit_logger_id`` would be
        REFERENCED unbound — pyright surfaced this as a strict failure. The
        B9a fix initializes to None at entry; the if-branch is skipped
        when audit_logging is False, so the unbound state never lands in
        an ``add_connection`` argument.
        """
        node = PrivacyPreservingRAGNode(audit_logging=False)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert wf.get_node("audit_logger") is None
        # No connections reference audit_logger when the branch is skipped.
        audit_connections = [
            c
            for c in wf.connections
            if c.source_node == "audit_logger" or c.target_node == "audit_logger"
        ]
        assert audit_connections == []

    def test_create_workflow_return_type_is_workflow(self):
        """``_create_workflow`` returns a Workflow, not a Node.

        Pre-B9a the annotation was ``-> Node`` but builder.build() returns
        a Workflow (same register_node type-erasure precedent fixed in B7
        PR #1108 + B8 PR #1110). Behavioral assertion: the annotation
        matches the runtime return type.
        """
        # Introspect the annotation.
        ann = inspect.signature(
            PrivacyPreservingRAGNode._create_workflow  # type: ignore[attr-defined]
        ).return_annotation
        # Annotation may resolve as a class or a string under
        # `from __future__ import annotations`; accept both.
        annotation_name = ann.__name__ if hasattr(ann, "__name__") else str(ann)
        assert "Workflow" in annotation_name

        # Runtime check: the value is actually a Workflow. Compare by
        # module + qualified name rather than `isinstance` — a sibling
        # regression test (test_issue_f9_rag_codegen_cleanup) clears
        # `sys.modules` to reset the node registry, after which the freshly
        # re-imported `kailash.workflow.graph.Workflow` is a DIFFERENT class
        # object than the one the node's own (also re-imported) module built
        # `wf` from, so `isinstance` is order-dependently False. The
        # module+qualname identity is reload-stable and asserts the same
        # contract.
        node = PrivacyPreservingRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        wf_cls = type(wf)
        assert (wf_cls.__module__, wf_cls.__qualname__) == (
            "kailash.workflow.graph",
            "Workflow",
        )

    def test_secure_multiparty_emits_deprecation_warning(self):
        """SecureMultiPartyRAGNode is a non-functional simulation deprecated for
        removal (zero-tolerance Rule 6a). Instantiating it MUST emit a
        DeprecationWarning naming the non-functional-simulation reason and the
        removal plan."""
        with pytest.warns(DeprecationWarning, match="non-functional simulation"):
            SecureMultiPartyRAGNode()
        # The warning also fires when kwargs are supplied (no path skips it).
        with pytest.warns(DeprecationWarning, match="REMOVED in a future"):
            SecureMultiPartyRAGNode(
                parties=["a", "b"], protocol="homomorphic", threshold=1
            )

    def test_secure_multiparty_parties_signature_is_optional(self):
        """SecureMultiPartyRAGNode.parties is typed Optional[List[str]].

        Pre-B9a ``parties: List[str] = None`` was a type mismatch (None is
        not assignable to List[str]). Fix: Optional[List[str]] = None.
        """
        sig = inspect.signature(SecureMultiPartyRAGNode.__init__)
        parties_param = sig.parameters["parties"]
        # The annotation accepts None; default is None.
        ann = parties_param.annotation
        # Optional[List[str]] resolves to Union[List[str], None] under typing.
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        assert origin is typing.Union or origin is type(None)
        # NoneType is one of the union members.
        assert type(None) in args
        assert parties_param.default is None

    def test_compliance_regulations_signature_is_optional(self):
        """ComplianceRAGNode.regulations is typed Optional[List[str]]."""
        sig = inspect.signature(ComplianceRAGNode.__init__)
        regs_param = sig.parameters["regulations"]
        ann = regs_param.annotation
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        assert origin is typing.Union or origin is type(None)
        assert type(None) in args
        assert regs_param.default is None

    def test_secure_multiparty_constructs_with_default_none_parties(self):
        """Default ``parties=None`` resolves to an empty list at construction."""
        node = SecureMultiPartyRAGNode()
        # The constructor resolves None to [] (see resolved_parties or []).
        assert node.parties == []  # type: ignore[attr-defined]

    def test_compliance_constructs_with_default_none_regulations(self):
        """Default ``regulations=None`` resolves to the documented (gdpr, ccpa)."""
        node = ComplianceRAGNode()
        assert node.regulations == ["gdpr", "ccpa"]  # type: ignore[attr-defined]


# ==========================================================================
# Resurrection xfail un-mark — PrivacyPreservingRAGNode xpasses post-B9a
# ==========================================================================


class TestResurrectionXfailUnmarked:
    """The PrivacyPreservingRAGNode xfail in test_rag_resurrection_import_smoke
    MUST be un-marked by B9a — the smoke test now XPASSes.

    The strict-xfail marker would surface this as a FAILURE if the un-mark
    is forgotten; this test is the structural cross-check that the un-mark
    landed in the same shard as the R4 LEAK fix.
    """

    def test_resurrection_smoke_module_no_longer_xfails_privacy_class(self):
        """The privacy entry MUST no longer carry an xfail marker.

        Behavioral check (per ``testing.md`` "Behavioral Regression Tests Over
        Source-Grep"): import the smoke module, locate the parametrize entry
        for ``PrivacyPreservingRAGNode``, and assert its marks list is empty.
        """
        import importlib.util
        from pathlib import Path

        smoke_path = Path(__file__).parent / "test_rag_resurrection_import_smoke.py"
        spec = importlib.util.spec_from_file_location(
            "_f8b9a_smoke_for_behavioral_check", smoke_path
        )
        assert spec is not None and spec.loader is not None
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        params = smoke.RAG_WORKFLOWNODE_SUBCLASSES
        privacy_entries = [
            p
            for p in params
            if getattr(p, "values", (None, None))[1] == "PrivacyPreservingRAGNode"
        ]
        assert len(privacy_entries) == 1, "PrivacyPreservingRAGNode entry not found"
        entry = privacy_entries[0]
        # pytest.param's `marks` is an iterable; an empty tuple means no xfail.
        marks = list(getattr(entry, "marks", ()))
        assert marks == [], (
            f"PrivacyPreservingRAGNode still carries marks: {marks}. "
            "B9a R4 LEAK fix should have un-marked the xfail."
        )
