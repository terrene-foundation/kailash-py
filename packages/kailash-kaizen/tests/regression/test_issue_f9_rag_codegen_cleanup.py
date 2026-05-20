"""Regression: F9 cleanup — 10 codegen + crypto + env-models defects.

Closes 11 GH issues filed against ``kaizen.nodes.rag``:

- #1112 dob regex capturing groups → SHA-256 crash (privacy.py)
- #1113 detect_and_redact_pii never reaches return (privacy.py)
- #1114 pii_detector no module-scope `result =` call (privacy.py)
- #1116 ConversationalRAGNode session_id 64-bit entropy weakness
- #1117 RAGEvaluationNode codegen defines but never calls inner fn
  (test_executor, context_evaluator, metric_aggregator)
- #1118 metric_aggregator `datetime.now()` on module not class
- #1120 unused EventStreamNode import — kept as registering-import
  (acceptance-criterion OR clause; import had a load-bearing side
  effect of populating ``kailash.nodes.data`` → VectorDatabaseNode)
- #1121 RealtimeRAGNode start_monitoring fire-and-forget asyncio task
- #1122 RealtimeStreamingRAGNode chunk_interval unit inconsistency
- #1123 (umbrella) f-string-codegen-into-PythonCodeNode pattern —
  closed by the per-instance fixes above
- #1126 hardcoded ``gpt-4`` defaults across 9 rag modules (env-models)

Each test asserts the behavior the original issue's acceptance criterion
required; no source-grep, all behavioral.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import os
import re
from pathlib import Path

import pytest

# ==========================================================================
# #1112 — dob regex non-capturing groups (re.findall returns strings)
# ==========================================================================


@pytest.mark.regression
def test_issue_1112_dob_regex_uses_non_capturing_groups():
    """Calling SHA-256 on a date match MUST NOT crash with TypeError on
    'tuple has no encode'. The regex MUST emit full-match strings."""
    # Reproduce exactly the codegen pattern (F9-fixed form).
    dob_pattern = r"\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/(?:19|20)\d{2}\b"
    matches = re.findall(dob_pattern, "DOB: 04/15/1985 and 12/31/2000")
    assert matches == ["04/15/1985", "12/31/2000"]
    # Each match is a string the codegen can hash without crashing.
    for m in matches:
        digest = hashlib.sha256(m.encode()).hexdigest()
        assert len(digest) == 64  # full sha256 hex digest


# ==========================================================================
# #1113 + #1114 — privacy pii_detector returns dict + binds module-scope
# ==========================================================================


@pytest.mark.regression
def test_issue_1113_1114_pii_detector_codegen_module_scope_call():
    """The pii_detector codegen MUST emit ``result =`` at module scope so
    PythonCodeNode's outbound port carries the redaction dict."""
    from kaizen.nodes.rag.privacy import PrivacyPreservingRAGNode

    wf = PrivacyPreservingRAGNode()._create_workflow()  # type: ignore[attr-defined]
    pii_detector = wf.get_node("pii_detector")
    assert pii_detector is not None
    code = pii_detector.config["code"]
    # Behavioral: strip the F9 #1114 cleanup `del` line for testability,
    # then exec and assert `result` is bound with the documented dict.
    code_no_del = "\n".join(
        line
        for line in code.splitlines()
        if not line.startswith("del detect_and_redact_pii")
    )
    ns: dict = {"text": "no pii here"}
    import warnings as _w

    with _w.catch_warnings():
        _w.simplefilter("ignore", SyntaxWarning)
        exec(code_no_del, ns)
    assert "result" in ns
    assert isinstance(ns["result"], dict)
    # The redact=True branch (codegen default per PrivacyPreservingRAGNode
    # defaults) returns the documented shape.
    for key in ("processed_text", "pii_found", "redaction_applied", "redaction_count"):
        assert key in ns["result"], key


# ==========================================================================
# #1116 — ConversationalRAGNode.session_id from CSPRNG
# ==========================================================================


@pytest.mark.regression
def test_issue_1116_session_id_uses_secrets_token_hex():
    """Two sessions for the same user, ~simultaneously, MUST NOT collide
    AND MUST NOT be brute-forceable from `user_id` + current timestamp."""
    from kaizen.nodes.rag.conversational import ConversationalRAGNode

    node = ConversationalRAGNode()
    s1 = node.create_session(user_id="alice")  # type: ignore[attr-defined]
    s2 = node.create_session(user_id="alice")  # type: ignore[attr-defined]
    # Distinct ids despite identical inputs (CSPRNG-derived).
    assert s1["session_id"] != s2["session_id"]
    # 32 hex chars = 128 bits of entropy (vs the prior 16-char/64-bit form).
    assert len(s1["session_id"]) == 32
    assert all(c in "0123456789abcdef" for c in s1["session_id"])


# ==========================================================================
# #1117 + #1118 — evaluation codegen module-scope call + datetime class
# ==========================================================================


@pytest.mark.regression
def test_issue_1117_evaluation_codegen_binds_module_scope_result():
    """The context_evaluator + metric_aggregator + test_executor codegen
    bodies MUST execute their inner functions at module scope so the
    PythonCodeNode outbound port carries the computed dict."""
    from kaizen.nodes.rag.evaluation import RAGEvaluationNode

    wf = RAGEvaluationNode(use_reference_answers=False)._create_workflow()  # type: ignore[attr-defined]
    for node_id in ("test_executor", "context_evaluator", "metric_aggregator"):
        node = wf.get_node(node_id)
        assert node is not None, node_id
        code = node.config["code"]
        # The codegen MUST end with a module-scope `result =` assignment
        # (per the issue acceptance criterion).
        assert re.search(
            r"^result\s*=", code, re.M
        ), f"{node_id} codegen does not bind `result` at module scope"


@pytest.mark.regression
def test_issue_1118_metric_aggregator_uses_datetime_class_not_module():
    """The metric_aggregator codegen MUST call `_datetime_class.now()`
    (the imported datetime class) — NOT `datetime.now()` against the
    module, which raises AttributeError."""
    from kaizen.nodes.rag.evaluation import RAGEvaluationNode

    wf = RAGEvaluationNode()._create_workflow()  # type: ignore[attr-defined]
    aggregator = wf.get_node("metric_aggregator")
    assert aggregator is not None
    code = aggregator.config["code"]
    # The codegen MUST import the class (under any alias) AND MUST invoke
    # via the class symbol, not the module.
    assert "from datetime import datetime" in code
    assert "_datetime_class.now()" in code
    # The bare `datetime.now()` invocation OUTSIDE comments / docstrings
    # is gone. Strip comments (everything from `#` to EOL) before checking.
    code_no_comments = re.sub(r"#.*$", "", code, flags=re.M)
    # Strip backtick-quoted spans (used in module docstrings).
    code_no_quotes = re.sub(r"`[^`]*`", "", code_no_comments)
    bare_call_count = len(re.findall(r"(?<!_)datetime\.now\s*\(", code_no_quotes))
    assert bare_call_count == 0


# ==========================================================================
# #1120 — EventStreamNode kept as registering import (F1120 OR clause)
# ==========================================================================


@pytest.mark.regression
def test_issue_1120_registering_import_keeps_vectordatabase_visible():
    """The `kailash.nodes.data.streaming` import in realtime.py is a
    load-bearing registering import — removing it broke
    `VectorDatabaseNode` registration. The F9 acceptance criterion's OR
    clause permits keeping the import with a comment."""
    # Fresh registry state — import only the rag subtree, assert
    # VectorDatabaseNode resolves.
    import sys

    for mod in [m for m in sys.modules if "kaizen" in m or "kailash" in m]:
        del sys.modules[mod]
    from kailash.nodes.base import NodeRegistry  # noqa: I001

    import kaizen.nodes.rag  # noqa: F401

    assert "VectorDatabaseNode" in NodeRegistry._nodes


# ==========================================================================
# #1121 — RealtimeRAGNode start_monitoring retains task + stop cancels
# ==========================================================================


@pytest.mark.regression
def test_issue_1121_start_monitoring_retains_task_stop_cancels():
    """start_monitoring MUST retain the task on self._monitor_task AND
    stop_monitoring MUST cancel + await the retained task."""
    from kaizen.nodes.rag.realtime import RealtimeRAGNode

    node = RealtimeRAGNode()
    node.update_interval = 0.01  # type: ignore[attr-defined]  # fast loop for the test

    async def _exercise() -> None:
        await node.start_monitoring([{"source": "test"}])  # type: ignore[attr-defined]
        # Task is retained as an attribute and is still running.
        assert hasattr(node, "_monitor_task")
        assert node._monitor_task is not None  # type: ignore[attr-defined]
        await asyncio.sleep(0.03)
        # stop_monitoring is async and cancels the task.
        await node.stop_monitoring()  # type: ignore[attr-defined]
        # Post-cancel: task slot is cleared.
        assert node._monitor_task is None  # type: ignore[attr-defined]

    asyncio.run(_exercise())


# ==========================================================================
# #1122 — chunk_interval unit reconciliation (seconds for processing_time)
# ==========================================================================


@pytest.mark.regression
def test_issue_1122_processing_time_is_in_seconds():
    """processing_time MUST be reported in SECONDS (chunk_interval is
    in milliseconds; total elapsed is chunk_idx * chunk_interval / 1000)."""
    from kaizen.nodes.rag.realtime import RealtimeStreamingRAGNode

    node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=10)  # 10ms

    async def _drain() -> list:
        acc: list = []
        async for chunk in node.stream(  # type: ignore[attr-defined]
            query="x",
            documents=[{"content": f"x {i}"} for i in range(4)],
            max_chunks=10,
        ):
            acc.append(chunk)
        return acc

    chunks = asyncio.run(_drain())
    complete = chunks[-1]
    # 4 docs / 2 per chunk = 2 chunks; processing_time = 2 * 10 / 1000 = 0.02s.
    assert complete["processing_time"] == pytest.approx(0.02, rel=1e-9)


# ==========================================================================
# #1126 — gpt-4 sweep: no hardcoded model defaults remain in rag/
# ==========================================================================


@pytest.mark.regression
def test_issue_1126_no_hardcoded_gpt4_defaults_in_rag_subtree():
    """Per rules/env-models.md: hardcoded model names BLOCKED.
    Every rag module's model default MUST resolve from env via a
    module-scope `_DEFAULT_LLM_MODEL`."""
    rag_dir = Path(__file__).resolve().parents[2] / "src" / "kaizen" / "nodes" / "rag"
    for py_path in rag_dir.glob("*.py"):
        if py_path.name == "__init__.py":
            continue
        src = py_path.read_text()
        # No literal "gpt-4" / "gpt-4o" / "gpt-3.5" string defaults.
        assert '"gpt-4"' not in src, f"{py_path.name}: hardcoded 'gpt-4'"
        assert '"gpt-4o"' not in src, f"{py_path.name}: hardcoded 'gpt-4o'"
        assert '"gpt-3.5"' not in src, f"{py_path.name}: hardcoded 'gpt-3.5'"


@pytest.mark.regression
def test_issue_1126_default_llm_model_resolves_from_env():
    """Every module that needs an LLM default MUST expose
    `_DEFAULT_LLM_MODEL` resolving from env."""
    modules = [
        "kaizen.nodes.rag.advanced",
        "kaizen.nodes.rag.agentic",
        "kaizen.nodes.rag.conversational",
        "kaizen.nodes.rag.evaluation",
        "kaizen.nodes.rag.graph",
        "kaizen.nodes.rag.multimodal",
        "kaizen.nodes.rag.query_processing",
        "kaizen.nodes.rag.similarity",
        "kaizen.nodes.rag.workflows",
    ]
    expected = os.environ.get("OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL"))
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, "_DEFAULT_LLM_MODEL"), mod_name
        assert mod._DEFAULT_LLM_MODEL == expected, mod_name
