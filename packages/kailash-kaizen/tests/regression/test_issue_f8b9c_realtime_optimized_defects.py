"""Regression: latent kaizen.nodes.rag realtime + optimized defects (F8 B9c).

F8 shard B9c owns the A3-triage-gated fixes for realtime.py and optimized.py:

R3-L2 — CacheNode unregistered node-type.
  optimized.py referenced "CacheNode" as a string node-type at 2 sites but
  never imported the module that registers it. CacheOptimizedRAGNode()
  construction blocked at _create_workflow() with NameError on CacheNode.
  Fix: added "from kailash.nodes.cache import cache  # noqa: F401" at
  module scope so the @register_node decoration runs at import time.

R3-L2 — dead CacheNode comment removed.
  The dead "# from ..data.cache import CacheNode  # TODO" comment at
  optimized.py:21 referenced a non-existent path (..data.cache) and was
  removed per zero-tolerance Rule 2 (no stubs / TODO markers in
  production code).

Pyright cleanup — chunk_idx possibly unbound + Workflow return-type.
  realtime.py:551 referenced chunk_idx without a binding when the prior
  for-loop did not execute (empty result set); narrowed via init + assert.
  Multiple _create_workflow methods declared -> Node but returned a
  Workflow (same class as B7/B8/B9a/B9b register_node type-erasure);
  signatures corrected.

xfail un-mark — optimized.CacheOptimizedRAGNode.
  test_rag_resurrection_import_smoke.py carried xfail(strict=True) on the
  CacheOptimizedRAGNode entry citing the _A3_CACHE_NODE NameError reason.
  Once the R3-L2 registering import landed, the smoke test XPASSed; B9c
  removed the marker. With B9a's privacy un-mark + B9c's optimized
  un-mark, the resurrection smoke test now carries ZERO xfail markers
  on the WorkflowNode-subclass parameter set.

This file lifts each defect into a behavioral regression test per
``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression


# ==========================================================================
# R3-L2 — CacheNode registering import in optimized.py
# ==========================================================================


class TestCacheOptimizedConstructsWithRegisteringImport:
    """CacheOptimizedRAGNode no longer raises NameError on CacheNode.

    Pre-B9c: `_create_workflow()` referenced "CacheNode" as a string
    node-type but the kailash.nodes.cache module that registers it was
    never imported, so `WorkflowBuilder.add_node("CacheNode", ...)`
    raised NameError at construction time.

    Post-B9c: optimized.py adds `from kailash.nodes.cache import cache`
    at module scope; the @register_node decoration runs at import,
    making "CacheNode" resolvable to the registered class.
    """

    def test_cache_optimized_constructs_without_nameerror(self):
        from kaizen.nodes.rag.optimized import CacheOptimizedRAGNode

        # Construction MUST NOT raise — the R3-L2 fix lifts this from
        # NameError-blocked to running.
        node = CacheOptimizedRAGNode(name="b9c_regression_cache")
        assert node is not None

    def test_cache_node_type_is_registered_at_optimized_import(self):
        """Importing kaizen.nodes.rag.optimized MUST cause CacheNode to be
        registered in the kailash NodeRegistry — the R3-L2 fix's purpose."""
        # Force a fresh import path: import the optimized module first.
        importlib.import_module("kaizen.nodes.rag.optimized")
        # Now the CacheNode string node-type MUST resolve via the registry.
        from kailash.nodes.base import NodeRegistry

        # Per the framework's registry API, the registered name resolves
        # to the class.
        assert NodeRegistry.get("CacheNode") is not None


# ==========================================================================
# R3-L2 — dead CacheNode comment removed from optimized.py:21
# ==========================================================================


class TestDeadCacheNodeCommentRemoved:
    """The dead `# from ..data.cache import CacheNode  # TODO` comment
    referenced a non-existent path and is removed per zero-tolerance
    Rule 2. Behavioral: the module's source MUST NOT contain the
    `..data.cache` path."""

    def test_optimized_module_source_no_longer_references_dead_path(self):
        import kaizen.nodes.rag.optimized as _opt

        source = Path(_opt.__file__).read_text()
        assert (
            "..data.cache" not in source
        ), "Dead `..data.cache` comment should have been removed by B9c."


# ==========================================================================
# Pyright cleanup — chunk_idx + Workflow return-type
# ==========================================================================


class TestRealtimeStreamingChunkIdxInitialized:
    """`chunk_idx` MUST be initialized before any post-loop reference.

    Pre-B9c: the for-loop bound `chunk_idx` only when results existed;
    the post-loop reference fell through to UnboundLocalError when the
    result set was empty.

    Post-B9c: `chunk_idx = 0` initialized before the loop; the post-loop
    reference is structurally safe.
    """

    def test_stream_with_empty_results_does_not_raise_unboundlocal(self):
        """An empty result set MUST NOT raise UnboundLocalError on
        chunk_idx in the stream completion path."""
        import asyncio

        from kaizen.nodes.rag.realtime import RealtimeStreamingRAGNode

        node = RealtimeStreamingRAGNode(chunk_size=5, chunk_interval=0)

        async def _drain():
            results = []
            async for chunk in node.stream(  # type: ignore[attr-defined]
                query="no_match_token",
                documents=[{"content": "no token in this doc"}],
                max_chunks=10,
            ):
                results.append(chunk)
            return results

        chunks = asyncio.run(_drain())
        # No exception means chunk_idx was initialized — the regression
        # is closed. We don't pin a specific chunk count; the load-bearing
        # claim is "no UnboundLocalError when results are empty".
        assert isinstance(chunks, list)


class TestRealtimeCreateWorkflowReturnType:
    """`_create_workflow` annotates `-> Workflow` (not `-> Node`).

    Pre-B9c: the annotation was incorrect; Pyright surfaced it. Post-B9c
    correctness ensures static-analyzer trust matches the runtime
    semantics.
    """

    def test_realtime_rag_create_workflow_annotated_workflow(self):
        from kaizen.nodes.rag.realtime import RealtimeRAGNode

        sig = inspect.signature(RealtimeRAGNode._create_workflow)  # type: ignore[attr-defined]
        ann = sig.return_annotation
        annotation_name = ann.__name__ if hasattr(ann, "__name__") else str(ann)
        assert "Workflow" in annotation_name, (
            f"RealtimeRAGNode._create_workflow MUST be annotated -> Workflow; "
            f"got {annotation_name!r}"
        )


# ==========================================================================
# xfail un-mark — optimized.CacheOptimizedRAGNode (LAST remaining xfail)
# ==========================================================================


class TestResurrectionXfailUnmarkedOptimized:
    """The optimized.CacheOptimizedRAGNode xfail in the smoke test MUST be
    un-marked by B9c — the registering-import fix makes the entry pass,
    so the strict marker would XPASS-fail otherwise.

    With B7 un-marking workflows + B9a un-marking privacy + B9c un-marking
    optimized, the WorkflowNode-subclass parametrize entries in the smoke
    test MUST carry ZERO xfail markers — the resurrection signal is
    fully closed.
    """

    def _load_smoke(self):
        smoke_path = Path(__file__).parent / "test_rag_resurrection_import_smoke.py"
        spec = importlib.util.spec_from_file_location(
            "_f8b9c_smoke_for_behavioral_check", smoke_path
        )
        assert spec is not None and spec.loader is not None
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        return smoke

    def test_optimized_cache_entry_no_longer_xfailed(self):
        smoke = self._load_smoke()
        params = smoke.RAG_WORKFLOWNODE_SUBCLASSES
        optimized_entries = [
            p
            for p in params
            if getattr(p, "values", (None, None))[1] == "CacheOptimizedRAGNode"
        ]
        assert (
            len(optimized_entries) == 1
        ), "CacheOptimizedRAGNode entry not found in the smoke parametrize"
        entry = optimized_entries[0]
        marks = list(getattr(entry, "marks", ()))
        assert marks == [], (
            f"CacheOptimizedRAGNode still carries marks: {marks}. "
            "B9c R3-L2 fix should have un-marked the xfail."
        )

    def test_smoke_test_workflownode_params_have_zero_xfails(self):
        """After B7 + B9a + B9c un-marks, the WorkflowNode-subclass set
        MUST carry zero xfail markers — the resurrection signal closed."""
        smoke = self._load_smoke()
        params = smoke.RAG_WORKFLOWNODE_SUBCLASSES
        entries_with_marks = [p for p in params if list(getattr(p, "marks", ()))]
        assert entries_with_marks == [], (
            f"Expected zero xfail markers across WorkflowNode-subclass "
            f"parametrize entries; found marks on: "
            f"{[getattr(p, 'values', None) for p in entries_with_marks]}"
        )
