"""Regression: F8 shard B10 — router + registry behavioral coverage.

Locks two defects/contracts the B10 shard closed against
``kaizen.nodes.rag.router`` and ``…rag.registry``:

1. **router.py:110 — `self.name` AttributeError** (A3-triage finding,
   listed at "router.py:102" in the F8 plan): the @register_node Node
   subclass did NOT store ``self.name`` directly; the canonical access
   is ``self.metadata.name``. Before B10, every call to
   ``RAGStrategyRouterNode.run()`` raised AttributeError at
   ``f"{self.name}_llm"`` — the resurrection false-floor pattern (the
   class imports clean and the @register_node decorator runs without
   ever calling ``__init__`` or ``run``). The B10 fix replaces
   ``self.name`` with ``self.metadata.name``; this regression locks
   that fix behaviorally (no source-grep — calls run() and asserts the
   AttributeError no longer fires).

2. **router.py:527 — documented `expected_results` kwarg silent
   drop** (Rule 3c violation, same bug class as the F9 cleanup
   issues): the kwarg was declared in get_parameters() but read into
   a local variable that the function body never used. The B10 fix
   wires consumption: when `expected_results` is provided, the
   `quality_analysis` output dict surfaces `expected_result_count` and
   `expected_recall_ratio`. This regression test locks the consumption
   contract.

3. **Smoke-set zero-xfail invariant** (B9c carried this assertion via
   ``test_smoke_test_workflownode_params_have_zero_xfails``). B10
   touches none of the WorkflowNode subclasses in the smoke set, but
   re-asserts the invariant here so a B10 follow-up edit that
   accidentally reintroduces an xfail param fails LOUDLY in B10's
   regression file, not silently elsewhere.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.regression
class TestRouterSelfNameBugClosed:
    """F8 B10 — router.py:110 self.name → self.metadata.name."""

    def test_router_run_no_longer_raises_attribute_error_on_self_name(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Before B10, ``run()`` raised AttributeError accessing self.name on
        the LLMAgentNode init line. The B10 fix routes through
        self.metadata.name. Behavioral assertion: a single ``run()`` call
        completes (the deterministic-LLM-fails fallback branch keeps the
        test offline)."""
        import kaizen.nodes.rag.router as router_mod
        from kaizen.nodes.rag.router import RAGStrategyRouterNode

        class _RaisingLLM:
            def __init__(self, *args, **kwargs):  # noqa: ARG002
                _ = (args, kwargs)

            def execute(self, **kwargs):  # noqa: ARG002
                _ = kwargs
                raise RuntimeError("simulated LLM failure for fallback test")

        monkeypatch.setattr(router_mod, "LLMAgentNode", _RaisingLLM)
        node = RAGStrategyRouterNode(name="regression_router")
        # The pre-B10 bug raised AttributeError here. Post-B10 fix routes
        # through self.metadata.name → reaches LLM init → catches the
        # simulated failure → falls back. No exception escapes.
        out = node.run(documents=[{"content": "test"}], query="test")
        # Output-shape contract honored on the fallback branch.
        assert "strategy" in out
        assert "fallback_strategy" in out


@pytest.mark.regression
class TestQualityAnalyzerExpectedResultsConsumed:
    """F8 B10 — Rule 3c: documented kwarg `expected_results` MUST be
    consumed by ≥1 branch of the function body."""

    def test_expected_results_surfaces_recall_fields(self):
        from kaizen.nodes.rag.router import RAGQualityAnalyzerNode

        node = RAGQualityAnalyzerNode(name="rule_3c_check")
        out = node.run(
            rag_results={
                "results": [{"content": f"d{i}"} for i in range(2)],
                "scores": [0.7, 0.8],
            },
            query="d",
            expected_results=[{"content": f"d{i}"} for i in range(4)],
        )
        qa = out["quality_analysis"]
        # Documented kwarg → measurable effect on output (Rule 3c).
        assert qa["expected_result_count"] == 4
        assert qa["expected_recall_ratio"] == pytest.approx(0.5, rel=1e-9)

    def test_expected_results_absent_does_not_add_recall_fields(self):
        """Backwards-compatibility: callers not supplying
        ``expected_results`` get the historical output shape unchanged."""
        from kaizen.nodes.rag.router import RAGQualityAnalyzerNode

        node = RAGQualityAnalyzerNode(name="rule_3c_backcompat")
        out = node.run(
            rag_results={
                "results": [{"content": "d"}],
                "scores": [0.8],
            },
            query="d",
        )
        qa = out["quality_analysis"]
        assert "expected_result_count" not in qa
        assert "expected_recall_ratio" not in qa


@pytest.mark.regression
class TestB10SmokeInvariants:
    """B10 leaves the smoke-set zero-xfail invariant intact (B9c added the
    assertion). B10 also leaves the registry / router smoke entries in
    place — assert their presence here so a B10 follow-up edit that drops
    them fails LOUDLY at the regression layer."""

    def _load_smoke(self):
        smoke_path = Path(__file__).parent / "test_rag_resurrection_import_smoke.py"
        spec = importlib.util.spec_from_file_location(
            "_f8b10_smoke_for_behavioral_check", smoke_path
        )
        assert spec is not None and spec.loader is not None
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        return smoke

    def test_smoke_workflownode_params_still_zero_xfails(self):
        smoke = self._load_smoke()
        params = smoke.RAG_WORKFLOWNODE_SUBCLASSES
        entries_with_marks = [p for p in params if list(getattr(p, "marks", ()))]
        assert entries_with_marks == [], (
            f"B10 MUST NOT reintroduce xfails on WorkflowNode-subclass "
            f"smoke entries; found: "
            f"{[getattr(p, 'values', None) for p in entries_with_marks]}"
        )

    def test_smoke_includes_router_and_registry_representatives(self):
        smoke = self._load_smoke()
        reps = smoke.RAG_NODE_REPRESENTATIVES
        names = {(m, cls) for m, cls, _ in reps}
        assert ("router", "RAGStrategyRouterNode") in names
        assert ("registry", "RAGWorkflowRegistry") in names
