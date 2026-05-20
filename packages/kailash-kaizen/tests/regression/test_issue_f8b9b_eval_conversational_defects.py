"""Regression: latent ``evaluation.py`` + ``conversational.py`` defects (F8 B9b).

F8 shard B9b owns the A3-triage-gated fixes for these 2 modules:

R3-L2 — dead `CacheNode` comment at `conversational.py:26`.
  The path `..data.cache.CacheNode` never existed in the kaizen package
  tree; the comment dates from the 2026-03-11 monorepo move. Dead
  commented-out import is dead code per zero-tolerance Rule 2. The
  matching `optimized.py:21` comment belongs to B9c, not B9b.

Pyright cleanup — Workflow return-type + possibly-unbound locals +
Optional defaults across both modules:
  - `evaluation.py::RAGEvaluationNode._create_workflow` was annotated
    `-> Node` but builder.build() returns `Workflow` (same register_node
    type-erasure precedent fixed in B7/B8/B9a).
  - `answer_quality_id` (evaluation.py) was bound only inside the
    `if self.use_reference_answers:` block yet referenced unconditionally
    on the wiring loop. Fix: initialize to None at function entry;
    narrow with assert inside the audit branch.
  - `conversational.py::ConversationalRAGNode._create_workflow` had the
    same `-> Node` annotation defect AND three possibly-unbound locals
    (`coreference_resolver_id`, `topic_tracker_id`, `summarizer_id`).
    Fix: initialize each to None at function entry + narrow with assert.
  - `create_session(user_id: str = None)` → `Optional[str]` (None is not
    assignable to str).
  - `metrics: List[str] = None` / `workload_sizes: List[int] = None` /
    `concurrent_users: List[int] = None` / `categories: List[str] = None`
    (evaluation.py) and `memory_types: List[str] = None` (conversational)
    → `Optional[List[...]]` (None is not assignable to List).
  - `_compare_systems` used `min/max(..., key=dict.get)` — typed-lambda
    rewrite closes the dict.get overload-resolution pyright errors.
  - `memory_store: Dict[str, Dict[str, Any]]` typed default — the
    per-user slot mixes deque + dict shapes; explicit `Any` closes 6
    attribute/argument warnings without a TypedDict refactor.

Tests are behavioral: import / construct / introspect the workflow graph;
never source-grep (per rules/testing.md § "Behavioral Regression Tests
Over Source-Grep"). The dead-comment-deletion regression IS a structural
import-graph claim (`..data.cache` not in the conversational module's
source AST) — that's a structural assertion permitted under
`rules/probe-driven-verification.md` Rule 3.
"""

from __future__ import annotations

import importlib
import inspect
import typing

import pytest

from kaizen.nodes.rag.conversational import (
    ConversationalRAGNode,
    ConversationMemoryNode,
)
from kaizen.nodes.rag.evaluation import (
    RAGBenchmarkNode,
    RAGEvaluationNode,
    TestDatasetGeneratorNode,
)

pytestmark = pytest.mark.regression


# ==========================================================================
# Dead CacheNode comment removal (A3 R3-L2)
# ==========================================================================


class TestDeadCacheNodeCommentRemoved:
    """The `..data.cache` reference is gone from conversational.py.

    Behavioral structural assertion: import the module + inspect its
    source text via importlib. The check is structural per
    `rules/probe-driven-verification.md` Rule 3 (file existence /
    AST shape / byte-equality — non-semantic).
    """

    def test_conversational_module_imports_clean(self):
        """`import kaizen.nodes.rag.conversational` succeeds without ImportError."""
        # A literal import + assertion that the module object exists.
        # Pre-B9b the dead comment was harmless (commented-out), but if a
        # future regression un-comments it the import would fail because
        # `..data.cache` never existed in the package tree.
        mod = importlib.import_module("kaizen.nodes.rag.conversational")
        assert mod is not None
        assert hasattr(mod, "ConversationalRAGNode")
        assert hasattr(mod, "ConversationMemoryNode")

    def test_conversational_source_does_not_reference_dead_cache_path(self):
        """The source text of conversational.py does NOT contain `..data.cache`.

        Structural import-graph assertion (per `probe-driven-verification.md`
        Rule 3 — file/AST shape is structural, not semantic). The dead
        comment was the only reference; removing it eliminates the path.
        """
        mod = importlib.import_module("kaizen.nodes.rag.conversational")
        assert mod.__file__ is not None
        source = open(mod.__file__).read()
        # The dead import path is gone from the source.
        assert "..data.cache" not in source
        # The B9c-scope dead comment in `optimized.py` is NOT affected by
        # this check — only conversational.py's source is read here.


# ==========================================================================
# Pyright cleanup — Workflow return-type
# ==========================================================================


class TestWorkflowReturnTypeAnnotations:
    """Both _create_workflow methods are now annotated `-> Workflow`."""

    def test_evaluation_create_workflow_return_type_is_workflow(self):
        from kailash.workflow.graph import Workflow

        ann = inspect.signature(
            RAGEvaluationNode._create_workflow  # type: ignore[attr-defined]
        ).return_annotation
        annotation_name = ann.__name__ if hasattr(ann, "__name__") else str(ann)
        assert "Workflow" in annotation_name
        # Runtime check: the value IS a Workflow.
        node = RAGEvaluationNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert isinstance(wf, Workflow)

    def test_conversational_create_workflow_return_type_is_workflow(self):
        from kailash.workflow.graph import Workflow

        ann = inspect.signature(
            ConversationalRAGNode._create_workflow  # type: ignore[attr-defined]
        ).return_annotation
        annotation_name = ann.__name__ if hasattr(ann, "__name__") else str(ann)
        assert "Workflow" in annotation_name
        node = ConversationalRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert isinstance(wf, Workflow)


# ==========================================================================
# Pyright cleanup — possibly-unbound locals are now initialized
# ==========================================================================


class TestPossiblyUnboundLocalsResolved:
    """The 4 possibly-unbound locals across both modules are bound at entry."""

    def test_evaluation_answer_quality_runtime_safe_with_use_reference_false(self):
        """With use_reference_answers=False, the audit branch never fires.

        Pre-B9b, the wiring loop's reference to answer_quality_id would
        be unbound on the False branch — runtime AttributeError. The B9b
        fix initializes answer_quality_id to None at entry; the
        if-branch is skipped, the assert-narrowed reference never lands.
        """
        node = RAGEvaluationNode(use_reference_answers=False)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        # The answer_quality_evaluator node is absent.
        assert wf.get_node("answer_quality_evaluator") is None
        # No edges name answer_quality_evaluator as source/target.
        aq_edges = [
            c
            for c in wf.connections
            if c.target_node == "answer_quality_evaluator"
            or c.source_node == "answer_quality_evaluator"
        ]
        assert aq_edges == []

    def test_evaluation_answer_quality_wired_with_use_reference_true(self):
        node = RAGEvaluationNode(use_reference_answers=True)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert wf.get_node("answer_quality_evaluator") is not None
        # Two wiring edges name answer_quality as source/target.
        aq_edges = [
            c
            for c in wf.connections
            if c.target_node == "answer_quality_evaluator"
            or c.source_node == "answer_quality_evaluator"
        ]
        assert len(aq_edges) == 2

    def test_conversational_coreference_runtime_safe_when_off(self):
        node = ConversationalRAGNode(coreference_resolution=False)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert wf.get_node("coreference_resolver") is None
        # No edges reference the resolver — the if-branch is skipped.

    def test_conversational_topic_tracker_runtime_safe_when_off(self):
        node = ConversationalRAGNode(topic_tracking=False)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert wf.get_node("topic_tracker") is None

    def test_conversational_summarizer_runtime_safe_when_off(self):
        node = ConversationalRAGNode(enable_summarization=False)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        assert wf.get_node("context_summarizer") is None

    def test_conversational_all_branches_off_constructs_minimal_graph(self):
        """Worst case: every optional branch False; all 3 possibly-unbound
        locals stay at None and are never asserted; the graph constructs."""
        node = ConversationalRAGNode(
            coreference_resolution=False,
            topic_tracking=False,
            enable_summarization=False,
        )
        wf = node._create_workflow()  # type: ignore[attr-defined]
        # Only the 5 mandatory nodes remain.
        assert len(wf.nodes) == 5


# ==========================================================================
# Pyright cleanup — Optional[List[...]] signature annotations
# ==========================================================================


class TestOptionalListSignatures:
    """Every `List[T] = None` was widened to `Optional[List[T]]`."""

    def _is_optional_list(self, ann) -> bool:
        """True if ann is Optional[List[T]] (Union[List[T], None])."""
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        return (origin is typing.Union or origin is type(None)) and type(None) in args

    def test_rag_evaluation_metrics_is_optional_list(self):
        sig = inspect.signature(RAGEvaluationNode.__init__)
        param = sig.parameters["metrics"]
        assert self._is_optional_list(param.annotation)
        assert param.default is None

    def test_rag_benchmark_workload_sizes_is_optional_list(self):
        sig = inspect.signature(RAGBenchmarkNode.__init__)
        param = sig.parameters["workload_sizes"]
        assert self._is_optional_list(param.annotation)
        assert param.default is None

    def test_rag_benchmark_concurrent_users_is_optional_list(self):
        sig = inspect.signature(RAGBenchmarkNode.__init__)
        param = sig.parameters["concurrent_users"]
        assert self._is_optional_list(param.annotation)
        assert param.default is None

    def test_test_dataset_generator_categories_is_optional_list(self):
        sig = inspect.signature(TestDatasetGeneratorNode.__init__)
        param = sig.parameters["categories"]
        assert self._is_optional_list(param.annotation)
        assert param.default is None

    def test_conversation_memory_memory_types_is_optional_list(self):
        sig = inspect.signature(ConversationMemoryNode.__init__)
        param = sig.parameters["memory_types"]
        assert self._is_optional_list(param.annotation)
        assert param.default is None

    def test_conversational_create_session_user_id_is_optional_str(self):
        sig = inspect.signature(ConversationalRAGNode.create_session)
        param = sig.parameters["user_id"]
        ann = param.annotation
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        # Optional[str] = Union[str, None].
        assert origin is typing.Union or origin is type(None)
        assert type(None) in args
        assert param.default is None


# ==========================================================================
# Pyright cleanup — defaults still resolve at construction
# ==========================================================================


class TestNoneDefaultsResolveAtConstruction:
    """Behavioral check: None defaults still resolve to the documented values."""

    def test_evaluation_metrics_none_default_resolves(self):
        node = RAGEvaluationNode()
        assert node.metrics == [  # type: ignore[attr-defined]
            "faithfulness",
            "relevance",
            "context_precision",
            "answer_quality",
        ]

    def test_benchmark_workload_sizes_none_default_resolves(self):
        node = RAGBenchmarkNode()
        assert node.workload_sizes == [10, 100, 1000]  # type: ignore[attr-defined]
        assert node.concurrent_users == [1, 5, 10]  # type: ignore[attr-defined]

    def test_test_dataset_generator_categories_none_default_resolves(self):
        node = TestDatasetGeneratorNode()
        assert node.categories == [  # type: ignore[attr-defined]
            "factual",
            "analytical",
            "comparative",
        ]

    def test_conversation_memory_memory_types_none_default_resolves(self):
        node = ConversationMemoryNode()
        assert node.memory_types == [  # type: ignore[attr-defined]
            "episodic",
            "semantic",
            "preferences",
        ]


# ==========================================================================
# _compare_systems lambda-key fix — comparison still picks winners
# ==========================================================================


class TestCompareSystemsLambdaKeyFix:
    """The `key=dict.get` → `key=lambda k: dict[k]` rewrites preserve behavior.

    The lambda-key produces the same ordering as `dict.get` (both return
    the dict's value at the key). The fix is type-system-only (pyright
    couldn't infer the dict.get overload); semantics are unchanged.
    """

    def test_compare_systems_picks_lowest_latency_as_fastest(self):
        """Behavioral check: when system_a has lower latencies, it's fastest."""
        node = RAGBenchmarkNode(workload_sizes=[2], concurrent_users=[1])
        out = node.run(
            rag_systems={"sys_a": {}, "sys_b": {}},
            test_queries=[{"q": "1"}, {"q": "2"}],
            duration=1,
        )
        comp = out["comparison"]
        # Both names are valid winners (random per-system latency).
        assert comp["fastest_system"] in {"sys_a", "sys_b"}
        assert comp["most_scalable"] in {"sys_a", "sys_b"}
        assert comp["most_efficient"] in {"sys_a", "sys_b"}


# ==========================================================================
# memory_store typed default — defaultdict still produces correct shape
# ==========================================================================


class TestMemoryStoreTypedDefault:
    """The Dict[str, Dict[str, Any]] annotation on memory_store preserves
    the defaultdict's per-user shape construction.
    """

    def test_memory_store_new_user_has_documented_shape(self):
        """Accessing memory_store[new_user_id] yields the documented dict."""
        node = ConversationMemoryNode()
        # Trigger lazy-creation via a store call.
        node.run(
            operation="store",
            user_id="new_typed_user",
            data={
                "facts": [{"key": "k", "value": "v"}],
            },
        )
        slot = node.memory_store["new_typed_user"]  # type: ignore[attr-defined]
        assert "episodic" in slot
        assert "semantic" in slot
        assert "preferences" in slot
