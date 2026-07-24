"""
RAG Evaluation and Benchmarking Framework

Implements comprehensive evaluation metrics and benchmarking:
- Retrieval quality metrics (precision, recall, MRR)
- Generation quality assessment
- End-to-end RAG evaluation
- A/B testing framework
- Performance benchmarking
- Dataset generation for testing

Based on RAGAS, BEIR, and evaluation research from 2024.
"""

import logging
import os
import random
import secrets
import statistics
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from kailash.nodes.base import Node, NodeParameter, register_node

# Registering imports (mirrors realtime.py #1120): `_create_workflow` wires these
# node types by STRING — `builder.add_node("PythonCodeNode" / "LLMAgentNode", ...)`
# — so the symbols are never referenced directly, but importing the modules runs
# their `@register_node` side effect that populates the registry the string lookup
# resolves against. Do NOT drop these to satisfy an unused-import linter.
from kailash.nodes.code.python import PythonCodeNode  # noqa: F401
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

from ..ai.llm_agent import LLMAgentNode  # noqa: F401
from kaizen.core._provider_env import detect_provider_from_env

logger = logging.getLogger(__name__)


# F9 #1126: env-loaded default LLM model. Mirrors the router.py precedent
# (F8 B10). May be None when neither env var is set — that is
# env-models-compliant; do NOT fall back to a hardcoded model name.
_DEFAULT_LLM_MODEL = os.environ.get(
    "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
)


# ---------------------------------------------------------------------------
# Messages-composer functions (L3 fix — same reference template as
# conversational.py lines 45-199).
#
# LLMAgentNode consumes context EXCLUSIVELY through its `messages` param (the
# OpenAI chat format: a list of {"role","content"} dicts) plus `system_prompt`.
# `LLMAgentNode.run` reads `messages = kwargs["messages"]`; ANY other wired
# port name (`test_data`, `retrieval_results`, ...) is read via `kwargs.get`
# and SILENTLY DROPPED. The prior wiring fed every judge `test_executor`'s
# `test_results` on the PHANTOM `test_data` port, so each judge scored from its
# `system_prompt` alone — never seeing the query, the retrieved contexts, the
# generated answer, or the reference answer (the L3 "judge ignores the data it
# is supposed to judge" defect). The aggregator then computed statistics over
# fabricated scores.
#
# The fix routes each judge's context through a `PythonCodeNode`
# `.from_function`-wrapped composer that RENDERS the REAL fields into a
# `messages` list wired to the VALID `messages` port. These are real
# module-level functions (real `return`→`result`, type-checkable, no f-string
# brace-escaping) per the program's reference template — NOT inline `code=`
# codegen blocks.
#
# ── OUTPUT-SIDE FIX (this shard): close the parse-gap AND the batch-vs-per-test
# limitation, honestly ───────────────────────────────────────────────────────
# `test_executor.test_results` is a LIST of per-query result dicts, but a
# SINGLE LLMAgentNode invocation publishes ONE `response` port (a dict shaped
# `{"content": "<the model's text, a JSON string for these judges>", ...}`).
# LLMAgentNode does NOT parse the model's JSON into top-level ports — the score
# lives INSIDE `response["content"]` as a JSON string, never parsed.
#
# Two defects flow from that, both closed here:
#
#   (1) PARSE-GAP (Class-B): the prior `metric_aggregator` read
#       `faithfulness_scores[i].get("response", {}).get("faithfulness_score", 0)`
#       — reading the raw `response` dict then `.get("faithfulness_score")`,
#       which is ALWAYS absent (the score is inside `response["content"]`'s JSON
#       string). Every score defaulted to a fabricated 0. The fix routes each
#       judge's `response` through a dedicated `from_function` response-parser
#       (below) that reads `response` -> `.get("content")` -> `json.loads`, with
#       a TYPED fallback that FLAGS malformed/non-JSON output (NOT a silent 0
#       that masquerades as a real score — zero-tolerance Rule 2).
#
#   (2) BATCH-VS-PER-TEST: a single judge call publishes ONE `response`, but the
#       aggregator indexes `faithfulness_scores[i]` PER TEST. Closed via the
#       judge-returns-ARRAY architecture (Option b): each judge's system_prompt
#       asks for a JSON ARRAY (one object per explicitly-numbered test), the
#       composers number the tests 1..N so the array aligns 1:1, and the
#       response-parser `json.loads` the array into the per-test list shape the
#       aggregator indexes. No per-test score is fabricated to force the split.
#
# The composers below render EVERY test as an explicitly-numbered block
# (Test 1 / Test 2 / ...) so the judge sees all the real data AND the returned
# array aligns positionally with `test_results`.
# ---------------------------------------------------------------------------


def _render_contexts(retrieved_contexts: Any) -> str:
    """Render the retrieved contexts of a single test into a text block.

    `retrieved_contexts` is the caller-provided list of
    ``{"content": str, "score": float}`` dicts (the real RAG retrieval output
    the evaluator judges). Returns "" when no contexts exist.
    """
    blocks = []
    if isinstance(retrieved_contexts, list):
        for i, ctx in enumerate(retrieved_contexts):
            if not isinstance(ctx, dict):
                continue
            # ctx.get("content") may be present-with-None; the `or ""` covers it.
            content = (ctx.get("content") or "").strip()
            if not content:
                continue
            score = ctx.get("score")
            label = f"[Context {i + 1}"
            if isinstance(score, (int, float)):
                label += f", score={score:.2f}"
            label += "]"
            blocks.append(f"{label} {content}")
    return "\n".join(blocks)


def _render_test_block(test_result: Any, index: int, include_reference: bool) -> str:
    """Render a single test_result dict into a numbered judging block.

    Embeds the REAL query + retrieved contexts + generated answer (and the
    reference answer when ``include_reference``) so the judge sees exactly the
    data it must score — not the system_prompt alone.
    """
    if not isinstance(test_result, dict):
        return f"Test {index + 1}:\n(no data)"
    query = (test_result.get("query") or "").strip()
    generated = (test_result.get("generated_answer") or "").strip()
    contexts = _render_contexts(test_result.get("retrieved_contexts"))

    parts = [f"Test {index + 1}:"]
    parts.append("Query:\n" + (query or "(empty)"))
    parts.append("Retrieved contexts:\n" + (contexts or "(none)"))
    parts.append("Generated answer:\n" + (generated or "(empty)"))
    if include_reference:
        reference = (test_result.get("reference_answer") or "").strip()
        parts.append("Reference answer:\n" + (reference or "(none provided)"))
    return "\n".join(parts)


def _normalize_test_results(test_results: Any) -> list:
    """Coerce the test_executor `test_results` wire into a list of dicts.

    Mirrors the ``context_evaluator`` defensive shape-handling: the wire is a
    LIST of per-query result dicts, but a single-test call may arrive as a bare
    dict.
    """
    if isinstance(test_results, list):
        return test_results
    if isinstance(test_results, dict):
        return [test_results]
    return []


def compose_faithfulness_messages(test_results=None):
    """Compose the ``messages`` list for the faithfulness_evaluator judge.

    Embeds, per test, the REAL retrieved contexts + generated answer so the
    judge scores whether each answer is grounded in its contexts — NOT from the
    system_prompt alone. Returns ``{"messages": [...]}`` wired to the
    LLMAgentNode ``messages`` port.

    Faithfulness does not need the reference answer (it scores grounding in the
    retrieved contexts), so ``include_reference`` is False here.
    """
    tests = _normalize_test_results(test_results)
    blocks = [
        _render_test_block(t, i, include_reference=False) for i, t in enumerate(tests)
    ]
    body = (
        "\n\n".join(blocks) if blocks else "No test results were provided to evaluate."
    )
    user_content = (
        "Evaluate the faithfulness of each generated answer to its retrieved "
        "contexts. The tests are numbered (Test 1, Test 2, ...). Return a JSON "
        "ARRAY with exactly one object per test, in the SAME numbered order. "
        "Each array element MUST be a JSON object with a numeric "
        '"faithfulness_score" between 0.0 and 1.0.\n\n' + body
    )
    return {"messages": [{"role": "user", "content": user_content}]}


def compose_relevance_messages(test_results=None):
    """Compose the ``messages`` list for the relevance_evaluator judge.

    Embeds, per test, the REAL query + generated answer so the judge scores
    whether each answer is relevant to its query — NOT from the system_prompt
    alone. Returns ``{"messages": [...]}`` wired to the LLMAgentNode
    ``messages`` port.

    Relevance scores answer-to-query, so the retrieved contexts are still
    rendered for context but the reference answer is not needed.
    """
    tests = _normalize_test_results(test_results)
    blocks = [
        _render_test_block(t, i, include_reference=False) for i, t in enumerate(tests)
    ]
    body = (
        "\n\n".join(blocks) if blocks else "No test results were provided to evaluate."
    )
    user_content = (
        "Evaluate the relevance of each generated answer to its query. The "
        "tests are numbered (Test 1, Test 2, ...). Return a JSON ARRAY with "
        "exactly one object per test, in the SAME numbered order. Each array "
        'element MUST be a JSON object with a numeric "relevance_score" between '
        "0.0 and 1.0.\n\n" + body
    )
    return {"messages": [{"role": "user", "content": user_content}]}


def compose_answer_quality_messages(test_results=None):
    """Compose the ``messages`` list for the answer_quality_evaluator judge.

    Embeds, per test, the REAL generated answer AND reference answer (plus the
    query + retrieved contexts for context) so the judge compares the generated
    answer against the ground-truth reference — NOT from the system_prompt
    alone. Returns ``{"messages": [...]}`` wired to the LLMAgentNode
    ``messages`` port.

    This composer is wired only when ``use_reference_answers=True``; it renders
    the reference answer that comparison requires.
    """
    tests = _normalize_test_results(test_results)
    blocks = [
        _render_test_block(t, i, include_reference=True) for i, t in enumerate(tests)
    ]
    body = (
        "\n\n".join(blocks) if blocks else "No test results were provided to evaluate."
    )
    user_content = (
        "Compare each generated answer with its reference answer. The tests are "
        "numbered (Test 1, Test 2, ...). Return a JSON ARRAY with exactly one "
        "object per test, in the SAME numbered order. Each array element MUST be "
        'a JSON object with a numeric "overall_quality" between 0.0 and 1.0.\n\n' + body
    )
    return {"messages": [{"role": "user", "content": user_content}]}


# ---------------------------------------------------------------------------
# Response-parser functions (OUTPUT-side fix — this shard).
#
# `LLMAgentNode.run()` publishes the judge's answer on the `response` port as a
# dict shaped `{"content": "<the model's text, a JSON string>", ...}`. It does
# NOT parse that JSON into top-level ports, so the real score lives INSIDE
# `response["content"]` and is never available to a `.get("faithfulness_score")`
# off the raw `response` dict (the parse-gap defect).
#
# Each parser below is a PURE DATA TRANSFORM (the permitted tool-result-parsing
# exception in `rules/agent-reasoning.md` § Permitted Deterministic Logic item
# 6 — extracting structured data, NOT agent decision logic):
#   1. read `response`, unwrap `.get("content")` (the model's JSON-string text),
#   2. `json.loads` it,
#   3. normalize to a LIST of per-test score dicts (the judge returns a JSON
#      ARRAY, one element per numbered test) so the aggregator can index
#      `faithfulness_scores[i]` per test, and
#   4. on malformed / non-JSON / wrong-shape output, emit a TYPED FLAGGED
#      sentinel (`{"<score_key>": None, "parse_error": "<reason>"}`) — NOT a
#      fabricated 0 that the aggregator would treat as a real score
#      (zero-tolerance Rule 2). The flagged sentinel is grep-able
#      (`parse_error`) and the aggregator skips it from the numeric mean rather
#      than counting an invented zero.
#
# `from_function` is the correct primitive (real module-level functions: real
# imports, real `return`->`result`, type-checkable, no f-string brace-escaping),
# mirroring the L3 composer pattern + agentic.py's `response`->`json.loads`
# downstream + conversational.py's `response.get("content")` unwrap.
# ---------------------------------------------------------------------------


def _unwrap_response_content(response: Any) -> Any:
    """Unwrap the LLMAgentNode `response` port into the model's text payload.

    `LLMAgentNode` publishes `response` as `{"content": "<text>", ...}` (mock +
    real providers both). A defensive caller may also pass the bare string. This
    mirrors conversational.py's ``response.get("content", "")`` unwrap.
    """
    if isinstance(response, dict):
        return response.get("content")
    return response


def _parse_score_array(response: Any, score_key: str) -> list:
    """Parse a judge `response` into a per-test list of score dicts.

    Reads `response` -> `.content` (a JSON string) -> ``json.loads`` -> a LIST
    aligned 1:1 with the numbered tests. Each element is normalized to a dict
    carrying ``score_key``. Malformed / non-JSON / wrong-shape output is FLAGGED
    with a typed sentinel (``{"<score_key>": None, "parse_error": "<reason>"}``)
    — never a fabricated 0 (zero-tolerance Rule 2).

    Returns an empty list when the judge produced no content at all (an honest
    "nothing to score" — the aggregator treats a missing per-test entry as a
    flagged gap, not a real zero).
    """
    import json

    content = _unwrap_response_content(response)

    # Honest empty: the judge published nothing parseable. Surface, don't invent.
    if content is None or (isinstance(content, str) and not content.strip()):
        return []

    # The judge may already have emitted a parsed structure (some providers do).
    parsed: Any
    if isinstance(content, (list, dict)):
        parsed = content
    elif isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # FLAGGED, not fabricated: the judge returned non-JSON text. The
            # whole batch is unparseable; surface a single flagged sentinel so
            # the aggregator records a parse gap instead of inventing zeros.
            return [
                {
                    score_key: None,
                    "parse_error": "non-json-response",
                }
            ]
    else:
        return [
            {
                score_key: None,
                "parse_error": "unexpected-content-type",
            }
        ]

    # The judge-returns-array contract: a JSON list, one element per test.
    if isinstance(parsed, list):
        out = []
        for elem in parsed:
            if isinstance(elem, dict):
                out.append(elem)
            else:
                out.append({score_key: None, "parse_error": "non-object-array-element"})
        return out

    # A single object (degenerate batch of one) is honest for a 1-test eval.
    if isinstance(parsed, dict):
        return [parsed]

    # A bare scalar (e.g. the judge returned just `0.8`) — flag the shape gap.
    return [{score_key: None, "parse_error": "non-array-non-object-json"}]


def parse_faithfulness_response(response=None):
    """Parse the faithfulness judge `response` into per-test score dicts."""
    return {"scores": _parse_score_array(response, "faithfulness_score")}


def parse_relevance_response(response=None):
    """Parse the relevance judge `response` into per-test score dicts."""
    return {"scores": _parse_score_array(response, "relevance_score")}


def parse_answer_quality_response(response=None):
    """Parse the answer-quality judge `response` into per-test score dicts."""
    return {"scores": _parse_score_array(response, "overall_quality")}


# ---------------------------------------------------------------------------
# Deterministic COMPUTE functions (#1117/#1123/#1118 root-cause fix — Wave 3
# Shard S3). These replace the prior code-string PythonCodeNode codegen the
# RAGEvaluationNode inlined for test_executor / context_evaluator /
# metric_aggregator. Each is a real module-level function wired via
# `PythonCodeNode.from_function(...)`: the node publishes its `return` value on
# the FLAT `result` port (the runtime resolves dotted downstream reads like
# `result.test_results` into the published dict), so:
#
#   - #1117 (publish-nothing): a real `return {...}` always binds the published
#     `result` port — no module-scope-assignment + `del` gymnastics.
#   - #1123 (f-string brace-escape): no `{{ }}` escaping; real dict literals.
#   - #1118 (import-trap): `from datetime import datetime` / `import statistics`
#     run as REAL imports inside the function body — no separate-(globals,locals)
#     exec() namespace split that hid module-scope imports from the closure.
#
# These are deterministic metric computation + honest pass-through (NOT agent
# decision-making per rules/agent-reasoning.md): no LLM reasoning, no if-else
# intent routing. The LLM judges score; these helpers aggregate the parsed
# scores. Missing inputs resolve to HONEST raises / empty defaults
# (zero-tolerance Rule 2) — never fabricated answers or scores.
# ---------------------------------------------------------------------------


def collect_rag_results(test_queries=None):
    """Pass through the caller-provided RAG outputs for downstream judging.

    Provably-correct remediation: this JUDGES results the caller's RAG system
    already produced — it does NOT fabricate them. Each ``test_queries`` entry
    MUST carry the caller's real ``generated_answer`` + ``retrieved_contexts``
    (a sandboxed node cannot invoke an arbitrary passed RAG node; running the
    system-under-test is ``RAGBenchmarkNode``'s job). No fabricated answers, no
    fabricated contexts, no synthetic timings.

    Returns ``{"test_results", "total_tests", "avg_execution_time"}`` on the flat
    ``result`` port. Raises ``ValueError`` (does NOT fabricate) when a test entry
    is missing the real answer / contexts so incoherent input fails loudly.
    """
    from datetime import datetime as _datetime_class

    if not isinstance(test_queries, list):
        test_queries = []

    test_results = []
    missing = []

    for i, test_case in enumerate(test_queries):
        if not isinstance(test_case, dict):
            missing.append((i, "non-dict-test-case"))
            continue
        query = test_case.get("query", "")
        reference = test_case.get("reference", "")

        # Honest contract: the caller ran their RAG system and supplies the real
        # answer + contexts. Raise (not fabricate) when absent.
        if "generated_answer" not in test_case:
            missing.append((i, "generated_answer"))
            continue
        if "retrieved_contexts" not in test_case:
            missing.append((i, "retrieved_contexts"))
            continue

        generated_answer = test_case["generated_answer"]
        retrieved_contexts = test_case["retrieved_contexts"]
        execution_time = test_case.get("execution_time", 0.0)

        test_results.append(
            {
                "test_id": i,
                "query": query,
                "reference_answer": reference,
                "generated_answer": generated_answer,
                "retrieved_contexts": retrieved_contexts,
                "execution_time": execution_time,
                "timestamp": _datetime_class.now().isoformat(),
            }
        )

    if missing:
        raise ValueError(
            "RAGEvaluationNode judges already-run RAG results: each "
            "test_queries entry MUST carry 'generated_answer' and "
            "'retrieved_contexts'. Missing on entries: " + repr(missing) + ". "
            "Run your RAG system first (or use RAGBenchmarkNode to execute + "
            "measure the system)."
        )

    return {
        "test_results": test_results,
        "total_tests": len(test_queries),
        "avg_execution_time": (
            sum(r["execution_time"] for r in test_results) / len(test_results)
            if test_results
            else 0.0
        ),
    }


def _evaluate_context_precision(test_result: Any) -> dict:
    """Evaluate the precision of one test's retrieved contexts.

    Deterministic retrieval-quality heuristic over the caller's REAL retrieval
    scores (P@k, MRR, diversity, avg-relevance). NOT an LLM judgment — the
    LLM-based relevance judgment is the separate relevance_evaluator. Returns the
    per-test ``{"context_metrics": {...}}`` dict (or the zeroed early-exit shape
    when no contexts exist).
    """
    if not isinstance(test_result, dict):
        test_result = {}
    contexts = test_result.get("retrieved_contexts", []) or []
    if not isinstance(contexts, list):
        contexts = []

    if not contexts:
        return {
            "context_precision": 0.0,
            "context_recall": 0.0,
            "context_ranking_quality": 0.0,
        }

    # Deterministic relevance heuristic: a context counts as relevant at k when
    # its caller-provided retrieval score clears 0.7 (a real threshold over real
    # scores, NOT a fabricated judgment).
    precision_at_k = {}
    for k in [1, 3, 5, 10]:
        if k <= len(contexts):
            relevant_at_k = sum(
                1
                for c in contexts[:k]
                if isinstance(c, dict) and c.get("score", 0) > 0.7
            )
            precision_at_k[f"P@{k}"] = relevant_at_k / k

    # MRR (Mean Reciprocal Rank).
    first_relevant_rank = None
    for i, ctx in enumerate(contexts):
        if isinstance(ctx, dict) and ctx.get("score", 0) > 0.7:
            first_relevant_rank = i + 1
            break
    mrr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0

    # Context diversity.
    unique_terms: set = set()
    for ctx in contexts:
        if isinstance(ctx, dict):
            unique_terms.update((ctx.get("content") or "").lower().split()[:20])
    diversity_score = len(unique_terms) / (len(contexts) * 20) if contexts else 0

    avg_relevance_score = sum(
        c.get("score", 0) for c in contexts if isinstance(c, dict)
    ) / len(contexts)

    return {
        "context_metrics": {
            "precision_at_k": precision_at_k,
            "mrr": mrr,
            "diversity_score": diversity_score,
            "avg_relevance_score": avg_relevance_score,
            "context_count": len(contexts),
        }
    }


def evaluate_context_metrics(test_data=None):
    """Map ``_evaluate_context_precision`` over every test in ``test_data``.

    ``test_data`` is the ``test_executor`` ``result.test_results`` LIST. Returns
    ``{"context_metrics": [...]}`` on the flat ``result`` port — a LIST of per-test
    context-metric dicts the aggregator indexes positionally. A single-test
    arrival as a bare dict is normalized to a one-element list.
    """
    if isinstance(test_data, list):
        rows = test_data
    elif test_data is None:
        rows = []
    else:
        rows = [test_data]
    context_metrics = [
        _evaluate_context_precision(t).get("context_metrics", {}) for t in rows
    ]
    return {"context_metrics": context_metrics}


def aggregate_evaluation_metrics(
    test_results=None,
    faithfulness_scores=None,
    relevance_scores=None,
    context_metrics=None,
    answer_quality_scores=None,
    metrics=None,
):
    """Aggregate all evaluation metrics over the PARSED per-test score lists.

    The judge inputs are PARSED per-test score LISTS (the response-parser nodes
    did ``response -> .content -> json.loads -> list``). ``faithfulness_scores``
    is therefore a LIST of per-test dicts like ``[{"faithfulness_score": 0.8},
    ...]`` aligned 1:1 with ``test_results``. A flagged entry carries
    ``parse_error`` + ``<key>: None`` — that is NOT a real score, so it is
    EXCLUDED from the numeric mean (never counted as a fabricated 0 —
    zero-tolerance Rule 2). ``metrics`` is the build-time RAGEvaluationNode config
    bound through a thin closure. Returns ``{"evaluation_summary": {...}}``.
    """
    import statistics
    from datetime import datetime as _datetime_class

    if not isinstance(test_results, list):
        test_results = []
    if metrics is None:
        metrics = []

    def _score_at(score_list, idx, key):
        """Real per-test score, or None when missing / flagged / malformed."""
        if not isinstance(score_list, list) or idx >= len(score_list):
            return None
        entry = score_list[idx]
        if not isinstance(entry, dict):
            return None
        if entry.get("parse_error") is not None:
            return None  # flagged — honest gap, never a fabricated 0
        value = entry.get(key)
        return value if isinstance(value, (int, float)) else None

    per_test = {
        "faithfulness": [],
        "relevance": [],
        "context_precision": [],
        "answer_quality": [],
        "execution_time": [],
    }

    for i, test in enumerate(test_results):
        per_test["faithfulness"].append(
            _score_at(faithfulness_scores, i, "faithfulness_score")
        )
        per_test["relevance"].append(_score_at(relevance_scores, i, "relevance_score"))
        ctx_score = None
        if isinstance(context_metrics, list) and i < len(context_metrics):
            ctx_entry = context_metrics[i]
            if isinstance(ctx_entry, dict):
                ctx_score = ctx_entry.get("context_metrics", {}).get(
                    "avg_relevance_score"
                )
                if ctx_score is None:
                    # context_metrics may already be the inner dict (flat shape).
                    ctx_score = ctx_entry.get("avg_relevance_score")
        per_test["context_precision"].append(
            ctx_score if isinstance(ctx_score, (int, float)) else None
        )
        per_test["execution_time"].append(
            test.get("execution_time", 0) if isinstance(test, dict) else 0
        )

        if answer_quality_scores is not None:
            per_test["answer_quality"].append(
                _score_at(answer_quality_scores, i, "overall_quality")
            )

    # Aggregate statistics over the REAL (non-None) scores only — a flagged /
    # missing per-test entry is excluded from the mean rather than counted as a
    # fabricated zero. Surface the gap count for honesty.
    aggregate_stats = {}
    flagged_counts = {}
    for metric, raw in per_test.items():
        valid = [s for s in raw if s is not None]
        flagged = sum(1 for s in raw if s is None)
        if flagged:
            flagged_counts[metric] = flagged
        if valid:
            aggregate_stats[metric] = {
                "mean": statistics.mean(valid),
                "median": statistics.median(valid),
                "std_dev": statistics.stdev(valid) if len(valid) > 1 else 0,
                "min": min(valid),
                "max": max(valid),
                "scores": valid,
            }

    # Identify failure cases (None-safe).
    failure_threshold = 0.6
    failures = []
    for i, test in enumerate(test_results):
        components = [
            ("faithfulness", per_test["faithfulness"][i]),
            ("relevance", per_test["relevance"][i]),
            ("context_precision", per_test["context_precision"][i]),
        ]
        present = [(name, val) for name, val in components if val is not None]
        if not present:
            continue
        overall_score = sum(val for _, val in present) / len(present)
        if overall_score < failure_threshold:
            failures.append(
                {
                    "test_id": i,
                    "query": test.get("query") if isinstance(test, dict) else None,
                    "overall_score": overall_score,
                    "weakest_metric": min(present, key=lambda x: x[1])[0],
                }
            )

    # Recommendations.
    recommendations = []
    if aggregate_stats.get("faithfulness", {}).get("mean", 1) < 0.7:
        recommendations.append(
            "Improve grounding: Ensure answers strictly follow retrieved content"
        )
    if aggregate_stats.get("relevance", {}).get("mean", 1) < 0.7:
        recommendations.append(
            "Enhance relevance: Better query understanding and targeted responses"
        )
    if aggregate_stats.get("context_precision", {}).get("mean", 1) < 0.7:
        recommendations.append(
            "Optimize retrieval: Improve document ranking and selection"
        )
    if aggregate_stats.get("execution_time", {}).get("mean", 0) > 2.0:
        recommendations.append(
            "Reduce latency: Consider caching or parallel processing"
        )

    # Roll up overall_score over ONLY the metrics that produced a REAL aggregate
    # mean — a fully parse-gapped / absent metric is EXCLUDED (never counted as 0).
    _overall_component_means = [
        aggregate_stats[_m]["mean"]
        for _m in ("faithfulness", "relevance", "context_precision")
        if _m in aggregate_stats and aggregate_stats[_m].get("mean") is not None
    ]
    overall_score_value = (
        statistics.mean(_overall_component_means) if _overall_component_means else None
    )

    return {
        "evaluation_summary": {
            "aggregate_metrics": aggregate_stats,
            "overall_score": overall_score_value,
            "failure_analysis": {
                "failure_count": len(failures),
                "failure_rate": (
                    (len(failures) / len(test_results)) if test_results else 0.0
                ),
                "failed_queries": failures,
            },
            "recommendations": recommendations,
            # Honesty surface: per-metric count of per-test entries with NO real
            # score (judge produced fewer than N, or the parser FLAGGED malformed
            # output). Non-empty means some judge output could not be parsed —
            # those gaps were EXCLUDED from the means, never fabricated zeros.
            "parse_gaps": flagged_counts,
            "evaluation_config": {
                "metrics_used": metrics,
                "total_tests": len(test_results),
                "timestamp": _datetime_class.now().isoformat(),
            },
        }
    }


@register_node()
class RAGEvaluationNode(WorkflowNode):
    """
    Comprehensive RAG Evaluation Framework

    Evaluates RAG systems across multiple dimensions including retrieval
    quality, generation accuracy, and end-to-end performance.

    When to use:
    - Best for: System optimization, quality assurance, model selection
    - Not ideal for: Real-time evaluation during inference
    - Performance: 5-30 seconds per evaluation (depends on metrics)
    - Insights: Detailed breakdown of strengths and weaknesses

    Key features:
    - RAGAS-based evaluation metrics
    - Retrieval and generation quality assessment
    - Faithfulness and relevance scoring
    - Comparative analysis across strategies
    - Automated test dataset generation

    Contract — judge already-run results (honest by construction):
        A sandboxed ``PythonCodeNode`` (the inner ``test_executor``) cannot
        invoke an arbitrary passed RAG node, so this evaluator does NOT run
        a system-under-test. Instead each ``test_queries`` entry MUST carry
        the RESULTS the caller already produced by running their RAG system:
        the ``generated_answer`` string and the ``retrieved_contexts`` list.
        The evaluator passes those real outputs through to the LLM judges
        (faithfulness / relevance / answer-quality) and the context-precision
        metric, which score the caller's REAL outputs. Nothing is fabricated.

        To run-the-system end-to-end (execute the RAG node + measure latency
        + throughput), use ``RAGBenchmarkNode`` — it executes the node and
        measures real wall-clock metrics.

    Example:
        evaluator = RAGEvaluationNode(
            metrics=["faithfulness", "relevance", "context_precision", "answer_quality"],
            use_reference_answers=True
        )

        # First run YOUR rag system to produce answer + contexts, then
        # pass those real results in for judging:
        rag_out = my_rag_node.execute(query="What is transformer architecture?")
        results = await evaluator.execute(
            test_queries=[
                {"query": "What is transformer architecture?",
                 "reference": "Transformers use self-attention...",
                 "generated_answer": rag_out["answer"],
                 "retrieved_contexts": rag_out["retrieved_contexts"]},
            ],
        )

        # Results include:
        # - Per-query scores
        # - Aggregate metrics
        # - Failure analysis
        # - Improvement recommendations

    Parameters:
        metrics: List of evaluation metrics to compute
        use_reference_answers: Whether to use ground truth
        llm_judge_model: Model for LLM-based evaluation
        confidence_threshold: Minimum acceptable score

    Each test_queries entry:
        query: The question that was asked (str, required)
        generated_answer: The answer the caller's RAG system produced (str)
        retrieved_contexts: The contexts the caller's RAG system retrieved
            (list of {"content": str, "score": float})
        reference: Ground-truth answer (str, optional; used when
            use_reference_answers=True)

    Returns:
        scores: Detailed scores per metric
        aggregate_metrics: Overall system performance
        failure_analysis: Queries that performed poorly
        recommendations: Suggested improvements
    """

    def __init__(
        self,
        name: str = "rag_evaluation",
        metrics: Optional[List[str]] = None,
        use_reference_answers: bool = True,
        llm_judge_model: Optional[str] = _DEFAULT_LLM_MODEL,
    ):
        self.metrics = metrics or [
            "faithfulness",
            "relevance",
            "context_precision",
            "answer_quality",
        ]
        self.use_reference_answers = use_reference_answers
        self.llm_judge_model = llm_judge_model
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create RAG evaluation workflow"""
        builder = WorkflowBuilder()

        # Bound only inside the optional-branch below; initialize at entry so
        # the later wiring loop's reference never sees an unbound name.
        answer_quality_id: Optional[str] = None

        # Test executor - runs RAG on test queries
        # Test executor — passes through caller-provided RAG results for judging.
        #
        # Wave-3 #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `collect_rag_results` function wired via `PythonCodeNode.from_function`.
        # No build-time config to bind (no closure needed). `from datetime import
        # datetime` runs as a real import inside the function body. The function
        # returns `{"test_results", "total_tests", "avg_execution_time"}`, so the
        # downstream `result.test_results` edges resolve unchanged. It RAISES (does
        # NOT fabricate) when a test entry lacks the caller's real answer/contexts.
        test_executor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                collect_rag_results,
                name="test_executor",
            ),
            node_id="test_executor",
            _internal=True,
        )

        # Faithfulness evaluator
        faithfulness_evaluator_id = builder.add_node(
            "LLMAgentNode",
            node_id="faithfulness_evaluator",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Evaluate the faithfulness of each generated answer to its retrieved contexts.

Faithfulness measures whether the answer is grounded in the retrieved information.

The user message contains one or more numbered tests (Test 1, Test 2, ...). For
EACH test, check whether each statement in the answer is supported by that test's
contexts, identify hallucinations, and rate overall faithfulness.

Return a JSON ARRAY with exactly one object per test, in the SAME numbered order:
[
  {
    "faithfulness_score": 0.0-1.0,
    "supported_statements": ["list of supported claims"],
    "unsupported_statements": ["list of unsupported claims"],
    "hallucinations": ["list of hallucinated information"],
    "reasoning": "explanation"
  }
]""",
                "model": self.llm_judge_model,
            },
        )

        # Relevance evaluator
        relevance_evaluator_id = builder.add_node(
            "LLMAgentNode",
            node_id="relevance_evaluator",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Evaluate the relevance of each answer to its query.

The user message contains one or more numbered tests (Test 1, Test 2, ...). For
EACH test consider:
1. Does the answer address the query?
2. Is it complete?
3. Is it focused without irrelevant information?

Return a JSON ARRAY with exactly one object per test, in the SAME numbered order:
[
  {
    "relevance_score": 0.0-1.0,
    "addresses_query": true/false,
    "completeness": 0.0-1.0,
    "focus": 0.0-1.0,
    "missing_aspects": ["list of missing elements"],
    "irrelevant_content": ["list of irrelevant parts"]
  }
]""",
                "model": self.llm_judge_model,
            },
        )

        # Context precision evaluator
        # Context precision evaluator.
        #
        # Wave-3 #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `evaluate_context_metrics` function wired via
        # `PythonCodeNode.from_function`. It maps `_evaluate_context_precision`
        # over the `test_data` LIST (the test_executor `result.test_results`) and
        # returns `{"context_metrics": [...]}` (a per-test list) on the flat
        # `result` port, so the downstream `result.context_metrics` edge resolves
        # unchanged. No build-time config to bind. This is a PythonCodeNode (not an
        # LLMAgentNode); it reads `test_data` directly via its declared param.
        context_evaluator_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                evaluate_context_metrics,
                name="context_evaluator",
            ),
            node_id="context_evaluator",
            _internal=True,
        )

        # Answer quality evaluator (if reference available)
        if self.use_reference_answers:
            answer_quality_id = builder.add_node(
                "LLMAgentNode",
                node_id="answer_quality_evaluator",
                config={
                    "provider": detect_provider_from_env(),
                    "system_prompt": """Compare each generated answer with its reference answer.

The user message contains one or more numbered tests (Test 1, Test 2, ...). For
EACH test evaluate:
1. Factual accuracy
2. Completeness
3. Clarity and coherence
4. Additional valuable information

Return a JSON ARRAY with exactly one object per test, in the SAME numbered order:
[
  {
    "accuracy_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "clarity_score": 0.0-1.0,
    "additional_value": 0.0-1.0,
    "overall_quality": 0.0-1.0,
    "key_differences": ["list of major differences"],
    "improvements_needed": ["list of improvements"]
  }
]""",
                    "model": self.llm_judge_model,
                },
            )

        # Metric aggregator
        # Metric aggregator.
        #
        # Wave-3 #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `aggregate_evaluation_metrics` function wired via
        # `PythonCodeNode.from_function`. The build-time `metrics` list is bound
        # through a thin closure (keeps test_results / faithfulness_scores /
        # relevance_scores / context_metrics / answer_quality_scores as the
        # declared inputs). `import statistics` + `from datetime import datetime`
        # run as real imports inside the function body. `answer_quality_scores`
        # has a `None` default so the from_function node is valid in BOTH
        # use_reference_answers configurations — on the disabled path that input is
        # never wired and the default applies (no NameError, unlike the prior
        # exec-namespace try/except). Returns `{"evaluation_summary": {...}}`.
        _metrics = self.metrics

        def _aggregate_evaluation_metrics_bound(
            test_results=None,
            faithfulness_scores=None,
            relevance_scores=None,
            context_metrics=None,
            answer_quality_scores=None,
        ) -> dict:
            return aggregate_evaluation_metrics(
                test_results=test_results,
                faithfulness_scores=faithfulness_scores,
                relevance_scores=relevance_scores,
                context_metrics=context_metrics,
                answer_quality_scores=answer_quality_scores,
                metrics=_metrics,
            )

        _aggregate_evaluation_metrics_bound.__name__ = "metric_aggregator"
        _aggregate_evaluation_metrics_bound.__doc__ = (
            aggregate_evaluation_metrics.__doc__
        )
        aggregator_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _aggregate_evaluation_metrics_bound,
                name="metric_aggregator",
            ),
            node_id="metric_aggregator",
            _internal=True,
        )

        # Messages-composer nodes (L3 fix). Each LLM judge's context is routed
        # through a `PythonCodeNode.from_function` composer that RENDERS the real
        # query + retrieved contexts + generated answer (+ reference answer for
        # the answer-quality judge) into an OpenAI-format `messages` list wired
        # to the LLMAgentNode `messages` port — the ONLY port through which
        # LLMAgentNode consumes context (its `run` reads `kwargs["messages"]`).
        # The prior wiring fed the phantom `test_data` port the node silently
        # drops, so each judge scored from its `system_prompt` alone.
        #
        # `.from_function` is the correct primitive (real module-level
        # functions: real imports, real `return`→`result`, type-checkable, no
        # brace-escaping). Instances are added via `add_node_instance(...,
        # _internal=True)` — the SDK-internal node-construction path (mirrors
        # conversational.py's L3 fix), so the consumer-facing instance-API
        # advisory `UserWarning` is correctly suppressed (zero-tolerance Rule 1:
        # no spurious runtime warnings).
        #
        # type: ignore[attr-defined] — `from_function` is a classmethod on the
        # concrete PythonCodeNode, but `@register_node` erases the subtype to
        # `type[Node]` for static checkers (mirrors conversational.py).
        faithfulness_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_faithfulness_messages,
                name="faithfulness_messages_composer",
            ),
            node_id="faithfulness_messages_composer",
            _internal=True,
        )
        relevance_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_relevance_messages,
                name="relevance_messages_composer",
            ),
            node_id="relevance_messages_composer",
            _internal=True,
        )
        answer_quality_messages_composer_id: Optional[str] = None
        if self.use_reference_answers:
            answer_quality_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    compose_answer_quality_messages,
                    name="answer_quality_messages_composer",
                ),
                node_id="answer_quality_messages_composer",
                _internal=True,
            )

        # Response-parser nodes (OUTPUT-side fix). Each judge's `response` port
        # (a dict `{"content": "<JSON string>", ...}`) is routed through a
        # `from_function` parser that reads `response` -> `.content` ->
        # `json.loads` -> a per-test list of score dicts (the judge returns a
        # JSON ARRAY, one element per numbered test). The aggregator then indexes
        # the real parsed `faithfulness_score` / `relevance_score` /
        # `overall_quality` per test, instead of `.get()`-ing off the raw
        # `response` dict (the parse-gap that defaulted every score to a
        # fabricated 0). Malformed / non-JSON output is FLAGGED by the parser, not
        # silently zeroed (zero-tolerance Rule 2). Same `from_function` +
        # `add_node_instance(_internal=True)` primitive as the composers.
        faithfulness_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_faithfulness_response,
                name="faithfulness_response_parser",
            ),
            node_id="faithfulness_response_parser",
            _internal=True,
        )
        relevance_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_relevance_response,
                name="relevance_response_parser",
            ),
            node_id="relevance_response_parser",
            _internal=True,
        )
        answer_quality_parser_id: Optional[str] = None
        if self.use_reference_answers:
            answer_quality_parser_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    parse_answer_quality_response,
                    name="answer_quality_response_parser",
                ),
                node_id="answer_quality_response_parser",
                _internal=True,
            )

        # Connect workflow.
        #
        # L3 wiring-correctness: a PythonCodeNode publishes a SINGLE `result`
        # output port carrying its whole module-scope `result` dict — the nested
        # keys ("test_results", "context_metrics") are NOT individual ports
        # (mirrors conversational.py's #1117/#1123 fix). The prior edges read
        # `test_executor."test_results"` / `context_evaluator."context_metrics"`
        # as if they were top-level ports, so every downstream input silently
        # bound to nothing. Every PythonCodeNode source edge now reads the nested
        # path `result.<key>`. LLMAgentNode publishes each top-level result key
        # as a real port, so `response` is read directly.
        #
        # L3 context fix: feed `test_executor.result.test_results` (a LIST of
        # per-query result dicts) INTO each judge's composer (NOT the phantom
        # `test_data` port on the LLM stage). The composer renders the real
        # query/contexts/answer into a `messages` list on the VALID `messages`
        # port. `context_evaluator` is a PythonCodeNode (not an LLMAgentNode)
        # that reads `test_data` via its module-scope code, so it consumes the
        # same `result.test_results` source on its `test_data` input.
        #
        # OUTPUT-side fix (this shard): the single-`response`->list-indexed
        # mismatch IS now closed. Each judge returns a JSON ARRAY (one element
        # per numbered test); the response-parser nodes `json.loads` the array
        # into the per-test list shape the aggregator indexes. The judge's
        # `response` flows judge -> response-parser -> aggregator (NOT judge ->
        # aggregator directly), so the aggregator reads REAL parsed per-test
        # scores. No per-test score is fabricated.
        builder.add_connection(
            test_executor_id,
            "result.test_results",
            faithfulness_messages_composer_id,
            "test_results",
        )
        builder.add_connection(
            faithfulness_messages_composer_id,
            "result.messages",
            faithfulness_evaluator_id,
            "messages",
        )
        builder.add_connection(
            test_executor_id,
            "result.test_results",
            relevance_messages_composer_id,
            "test_results",
        )
        builder.add_connection(
            relevance_messages_composer_id,
            "result.messages",
            relevance_evaluator_id,
            "messages",
        )
        builder.add_connection(
            test_executor_id, "result.test_results", context_evaluator_id, "test_data"
        )

        if self.use_reference_answers:
            assert answer_quality_id is not None  # narrowed: bound in the branch above
            assert answer_quality_messages_composer_id is not None
            builder.add_connection(
                test_executor_id,
                "result.test_results",
                answer_quality_messages_composer_id,
                "test_results",
            )
            builder.add_connection(
                answer_quality_messages_composer_id,
                "result.messages",
                answer_quality_id,
                "messages",
            )
            assert answer_quality_parser_id is not None
            # judge -> response-parser -> aggregator (parsed per-test list).
            builder.add_connection(
                answer_quality_id, "response", answer_quality_parser_id, "response"
            )
            builder.add_connection(
                answer_quality_parser_id,
                "result.scores",
                aggregator_id,
                "answer_quality_scores",
            )

        builder.add_connection(
            test_executor_id, "result.test_results", aggregator_id, "test_results"
        )
        # judge -> response-parser -> aggregator (parsed per-test score list).
        builder.add_connection(
            faithfulness_evaluator_id, "response", faithfulness_parser_id, "response"
        )
        builder.add_connection(
            faithfulness_parser_id,
            "result.scores",
            aggregator_id,
            "faithfulness_scores",
        )
        builder.add_connection(
            relevance_evaluator_id, "response", relevance_parser_id, "response"
        )
        builder.add_connection(
            relevance_parser_id, "result.scores", aggregator_id, "relevance_scores"
        )
        builder.add_connection(
            context_evaluator_id,
            "result.context_metrics",
            aggregator_id,
            "context_metrics",
        )

        return builder.build(name="rag_evaluation_workflow")


@register_node()
class RAGBenchmarkNode(Node):
    """
    RAG Performance Benchmarking Node

    Benchmarks RAG systems for performance characteristics.

    When to use:
    - Best for: System comparison, optimization, capacity planning
    - Not ideal for: Quality evaluation (use RAGEvaluationNode)
    - Metrics: Latency, throughput, resource usage, scalability

    Provably-correct measurement (no synthetic timings):
        Each provided system is EXECUTED against the test queries via the
        Core SDK node-execution path (``system.execute(query=...)``) and
        every metric is MEASURED from the real run:
        - latency: ``time.perf_counter()`` around each real query execution
        - throughput: real queries / real elapsed wall-clock
        - memory: ``tracemalloc`` peak across the workload
        - concurrency: real concurrent execution via a thread pool
        No ``time.sleep`` / ``random`` stand-ins. A provided "system" that
        cannot be executed (no ``execute`` / not callable) raises a typed
        error rather than falling back to fabricated numbers.

    Example:
        benchmark = RAGBenchmarkNode(
            workload_sizes=[10, 100, 1000],
            concurrent_users=[1, 5, 10]
        )

        # rag_a / rag_b are runnable RAG nodes (Core SDK Node / WorkflowNode)
        # or any callable accepting a query and returning a result dict.
        results = await benchmark.execute(
            rag_systems={"system_a": rag_a, "system_b": rag_b},
            test_queries=queries
        )

    Parameters:
        workload_sizes: Different dataset sizes to test
        concurrent_users: Concurrency levels to test
        metrics_interval: How often to collect metrics

    Each rag_systems value MUST be runnable, one of:
        - a Core SDK Node / WorkflowNode (executed via ``.execute(query=...)``)
        - a plain callable ``fn(query=...) -> result`` (executed directly)

    Each test_queries entry: a dict carrying the query under a ``"query"``
    key (or ``"q"``); the dict is forwarded to the system's execute path.

    Returns:
        latency_profiles: Response time distributions (measured)
        throughput_curves: Requests/second at different loads (measured)
        resource_usage: Peak memory utilization (measured via tracemalloc)
        scalability_analysis: How performance scales under real concurrency
    """

    def __init__(
        self,
        name: str = "rag_benchmark",
        workload_sizes: Optional[List[int]] = None,
        concurrent_users: Optional[List[int]] = None,
    ):
        resolved_workload_sizes = workload_sizes or [10, 100, 1000]
        resolved_concurrent_users = concurrent_users or [1, 5, 10]
        super().__init__(
            name=name,
            workload_sizes=resolved_workload_sizes,
            concurrent_users=resolved_concurrent_users,
        )
        self.workload_sizes = resolved_workload_sizes
        self.concurrent_users = resolved_concurrent_users

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="rag_benchmark",
                description="Node instance name",
            ),
            "workload_sizes": NodeParameter(
                name="workload_sizes",
                type=list,
                required=False,
                default=None,
                description="Document-count workloads to benchmark",
            ),
            "concurrent_users": NodeParameter(
                name="concurrent_users",
                type=list,
                required=False,
                default=None,
                description="Concurrency levels to benchmark",
            ),
            "rag_systems": NodeParameter(
                name="rag_systems",
                type=dict,
                required=True,
                description="RAG systems to benchmark",
            ),
            "test_queries": NodeParameter(
                name="test_queries",
                type=list,
                required=True,
                description="Queries for benchmarking",
            ),
            "duration": NodeParameter(
                name="duration",
                type=int,
                required=False,
                default=60,
                description="Test duration in seconds",
            ),
        }

    @staticmethod
    def _resolve_runner(system_name: str, system: Any) -> Callable[[dict], Any]:
        """Return a callable that EXECUTES the provided system on one query.

        Accepts a Core SDK Node / WorkflowNode (run via ``.execute(**query)``)
        or a plain callable ``fn(**query)``. Raises a typed error for any
        shape that cannot be executed — there is NO fabrication fallback.
        """
        execute = getattr(system, "execute", None)
        if callable(execute):
            return lambda query: execute(**query)
        if callable(system):
            return lambda query: system(**query)
        raise TypeError(
            f"RAGBenchmarkNode cannot execute system '{system_name}': "
            f"expected a Core SDK Node/WorkflowNode with .execute(...) or a "
            f"callable, got {type(system).__name__}. Benchmarking measures a "
            f"REAL system run — no synthetic-metric fallback is provided."
        )

    @staticmethod
    def _query_payload(query: Any) -> dict:
        """Normalize a test-query entry into kwargs for the system runner."""
        if isinstance(query, dict):
            # Forward the dict as-is so node-declared params bind by name.
            # A bare {"q": ...} convenience key maps to the canonical query.
            if "query" not in query and "q" in query:
                payload = dict(query)
                payload["query"] = payload.pop("q")
                return payload
            return dict(query)
        # A bare string/other → the canonical `query` kwarg.
        return {"query": query}

    @staticmethod
    def _timed_call(runner: Callable[[dict], Any], payload: dict) -> float:
        """Execute one real query and return its measured wall-clock latency."""
        q_start = time.perf_counter()
        runner(payload)  # real execution; raises propagate (no swallow)
        return time.perf_counter() - q_start

    def _measure_workload(
        self,
        runner: Callable[[dict], Any],
        workload: List[Any],
        timeout: Optional[float] = None,
    ) -> Tuple[List[float], float, bool]:
        """Run each query sequentially under a real wall-clock budget.

        Each query runs in a worker future bounded by the remaining ``timeout``
        so a single wedged provided system cannot hang the benchmark — the
        ``duration`` budget is a TRUE wall-clock cap on this path too, not only
        the concurrent one. Returns (per-query latencies that completed,
        wall-clock elapsed, ``timed_out``).
        """
        latencies: List[float] = []
        timed_out = False
        deadline = (time.perf_counter() + timeout) if timeout is not None else None
        start = time.perf_counter()
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            for query in workload:
                remaining = (
                    None
                    if deadline is None
                    else max(0.0, deadline - time.perf_counter())
                )
                if remaining is not None and remaining <= 0:
                    timed_out = True
                    break
                payload = self._query_payload(query)
                fut = pool.submit(self._timed_call, runner, payload)
                try:
                    latencies.append(fut.result(timeout=remaining))
                except FuturesTimeoutError:
                    timed_out = True
                    break
        finally:
            # Don't block on a wedged thread: cancel queued work, don't wait
            # for an in-flight one. The bound is real even though Python cannot
            # kill the running thread.
            pool.shutdown(wait=False, cancel_futures=True)
        elapsed = time.perf_counter() - start
        return latencies, elapsed, timed_out

    def _measure_concurrent(
        self,
        runner: Callable[[dict], Any],
        workload: List[Any],
        users: int,
        timeout: Optional[float] = None,
    ) -> Tuple[List[float], float, bool]:
        """Run the workload across `users` real concurrent threads.

        Core SDK Nodes expose only a sync ``execute``; real concurrency uses
        a thread pool rather than ``asyncio.gather``. ``timeout`` bounds the
        TOTAL wall-clock wait for the concurrent batch — a wedged provided
        system cannot hang the benchmark past it. Returns (per-query
        latencies collected so far, wall-clock elapsed, ``timed_out``).
        """
        payloads = [self._query_payload(q) for q in workload]

        latencies: List[float] = []
        timed_out = False
        start = time.perf_counter()
        pool = ThreadPoolExecutor(max_workers=max(1, users))
        try:
            futures = [pool.submit(self._timed_call, runner, p) for p in payloads]
            try:
                # as_completed appends each result as it finishes; on timeout
                # `latencies` already holds exactly the queries that completed
                # within the budget — no fabrication, no indefinite hang.
                for fut in as_completed(futures, timeout=timeout):
                    latencies.append(fut.result())  # propagate real errors
            except FuturesTimeoutError:
                timed_out = True
        finally:
            # wait=False so a wedged thread cannot block run() past the budget;
            # cancel_futures drops queries that never started.
            pool.shutdown(wait=False, cancel_futures=True)
        elapsed = time.perf_counter() - start
        return latencies, elapsed, timed_out

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run performance benchmarks by EXECUTING each provided system."""
        rag_systems = kwargs.get("rag_systems", {})
        test_queries = kwargs.get("test_queries", [])
        duration = kwargs.get("duration", 60)

        # Correlation id binds every log line of this benchmark run together
        # (observability.md Rule 2). `duration` is a REAL total wall-clock
        # budget: a wedged provided system cannot hang `run()` past it.
        bench_run_id = secrets.token_hex(8)
        deadline = time.perf_counter() + max(1, int(duration))

        def _remaining() -> float:
            return max(0.0, deadline - time.perf_counter())

        logger.info(
            "rag_benchmark.start",
            extra={
                "run_id": bench_run_id,
                "systems": list(rag_systems.keys()),
                "num_queries": len(test_queries),
                "workload_sizes": self.workload_sizes,
                "concurrent_users": self.concurrent_users,
                "duration_budget_s": duration,
            },
        )

        benchmark_results = {}
        duration_exceeded = False

        for system_name, system in rag_systems.items():
            if _remaining() <= 0:
                duration_exceeded = True
                logger.warning(
                    "rag_benchmark.duration_exceeded",
                    extra={
                        "run_id": bench_run_id,
                        "benchmarked": len(benchmark_results),
                        "total_systems": len(rag_systems),
                    },
                )
                break

            # Resolve the real runner up front — typed error if not runnable.
            runner = self._resolve_runner(system_name, system)

            system_results: Dict[str, Any] = {
                "latency_profiles": {},
                "throughput_curves": {},
                "resource_usage": {},
                "scalability_analysis": {},
            }

            logger.info(
                "rag_benchmark.system.start",
                extra={"run_id": bench_run_id, "system": system_name},
            )

            # Measure real memory across the full system run via tracemalloc.
            # try/finally guarantees we stop tracing even if a provided system
            # raises mid-benchmark — otherwise process-global tracing leaks.
            tracing_already_on = tracemalloc.is_tracing()
            if not tracing_already_on:
                tracemalloc.start()
            else:
                tracemalloc.reset_peak()
            try:
                # Test different workload sizes — REAL execution + measurement.
                for size in self.workload_sizes:
                    if _remaining() <= 0:
                        duration_exceeded = True
                        break
                    workload = test_queries[:size]
                    if not workload:
                        continue

                    latencies, elapsed, wl_timed_out = self._measure_workload(
                        runner, workload, timeout=_remaining()
                    )
                    if wl_timed_out:
                        duration_exceeded = True
                        logger.warning(
                            "rag_benchmark.workload_timeout",
                            extra={
                                "run_id": bench_run_id,
                                "system": system_name,
                                "size": size,
                                "completed": len(latencies),
                                "requested": len(workload),
                            },
                        )
                    if not latencies:
                        # Nothing completed within the budget — record nothing
                        # rather than fabricate, and stop escalating workload size.
                        break

                    ordered = sorted(latencies)
                    # Clamp percentile indices into range (small workloads).
                    p95_idx = min(int(len(ordered) * 0.95), len(ordered) - 1)
                    p99_idx = min(int(len(ordered) * 0.99), len(ordered) - 1)
                    system_results["latency_profiles"][f"size_{size}"] = {
                        "p50": statistics.median(latencies),
                        "p95": ordered[p95_idx],
                        "p99": ordered[p99_idx],
                        "mean": statistics.mean(latencies),
                        "std_dev": (
                            statistics.stdev(latencies) if len(latencies) > 1 else 0.0
                        ),
                    }

                    # Real throughput = queries actually completed / real elapsed.
                    throughput = len(latencies) / elapsed if elapsed > 0 else 0.0
                    system_results["throughput_curves"][f"size_{size}"] = throughput
                    if wl_timed_out:
                        break

                # Test concurrency — REAL concurrent execution via thread pool.
                # Use the largest available workload (capped at the largest
                # configured workload size) so concurrency exercises real load.
                concurrency_workload = test_queries[: max(self.workload_sizes)]
                for users in self.concurrent_users:
                    if not concurrency_workload:
                        continue
                    if _remaining() <= 0:
                        duration_exceeded = True
                        break
                    conc_latencies, conc_elapsed, conc_timed_out = (
                        self._measure_concurrent(
                            runner,
                            concurrency_workload,
                            users,
                            timeout=_remaining(),
                        )
                    )
                    if conc_timed_out:
                        duration_exceeded = True
                        logger.warning(
                            "rag_benchmark.concurrent_timeout",
                            extra={
                                "run_id": bench_run_id,
                                "system": system_name,
                                "users": users,
                                "completed": len(conc_latencies),
                                "requested": len(concurrency_workload),
                            },
                        )
                    if not conc_latencies:
                        # Nothing completed within the budget — record an honest
                        # empty entry (no fabricated numbers) and stop escalating
                        # concurrency for this system.
                        system_results["scalability_analysis"][f"users_{users}"] = {
                            "avg_latency": 0.0,
                            "concurrent_throughput": 0.0,
                            "parallel_speedup": 0.0,
                            "timed_out": True,
                        }
                        break
                    concurrent_throughput = (
                        len(conc_latencies) / conc_elapsed if conc_elapsed > 0 else 0.0
                    )
                    system_results["scalability_analysis"][f"users_{users}"] = {
                        "avg_latency": statistics.mean(conc_latencies),
                        "concurrent_throughput": concurrent_throughput,
                        # parallel_speedup: mean per-query compute time divided by
                        # the amortized wall-clock per query. ~N under N-way
                        # parallelism, ~1.0 when serial. HIGHER = scales better.
                        # Measured from real timings (no synthetic stand-in).
                        "parallel_speedup": (
                            statistics.mean(conc_latencies)
                            / (conc_elapsed / len(conc_latencies))
                            if conc_elapsed > 0
                            else 0.0
                        ),
                        "timed_out": conc_timed_out,
                    }
                    if conc_timed_out:
                        break

                # Real peak memory for this system's run (tracemalloc).
                _, peak = tracemalloc.get_traced_memory()
                system_results["resource_usage"] = {
                    "memory_mb": peak / (1024 * 1024),
                }
            finally:
                if not tracing_already_on:
                    tracemalloc.stop()

            logger.info(
                "rag_benchmark.system.ok",
                extra={
                    "run_id": bench_run_id,
                    "system": system_name,
                    "peak_memory_mb": system_results["resource_usage"].get(
                        "memory_mb", 0.0
                    ),
                },
            )

            benchmark_results[system_name] = system_results

        # Comparative analysis over REAL measured numbers.
        comparison = self._compare_systems(benchmark_results)

        logger.info(
            "rag_benchmark.ok",
            extra={
                "run_id": bench_run_id,
                "systems_benchmarked": len(benchmark_results),
                "duration_exceeded": duration_exceeded,
            },
        )

        return {
            "benchmark_results": benchmark_results,
            "comparison": comparison,
            "test_configuration": {
                "workload_sizes": self.workload_sizes,
                "concurrent_users": self.concurrent_users,
                "duration": duration,
                "num_queries": len(test_queries),
                "duration_exceeded": duration_exceeded,
            },
        }

    def _compare_systems(self, results: Dict) -> Dict[str, Any]:
        """Compare benchmark results across systems (real measured numbers)."""
        comparison: Dict[str, Any] = {
            "fastest_system": None,
            "most_scalable": None,
            "most_efficient": None,
            "recommendations": [],
        }

        # No systems benchmarked → nothing to rank (e.g. empty rag_systems
        # or all workloads empty). Return the null-winner shape honestly
        # rather than crashing min/max on an empty mapping.
        if not results:
            return comparison

        # Find fastest system — lowest mean per-query latency.
        avg_latencies = {}
        for system, data in results.items():
            latencies = [v["mean"] for v in data["latency_profiles"].values()]
            avg_latencies[system] = (
                statistics.mean(latencies) if latencies else float("inf")
            )

        comparison["fastest_system"] = min(
            avg_latencies, key=lambda k: avg_latencies[k]
        )

        # Find most scalable — HIGHEST parallel-speedup factor (best effective
        # concurrency under real load). parallel_speedup is measured per-query
        # mean latency over amortized wall-clock per query (~N under N-way
        # parallelism, ~1.0 serial); HIGHER is better, so rank with max. A
        # system with no concurrency data defaults to 0.0 (worst) so it cannot
        # spuriously win.
        scalability_scores = {}
        for system, data in results.items():
            speedups = [
                v["parallel_speedup"] for v in data["scalability_analysis"].values()
            ]
            scalability_scores[system] = statistics.mean(speedups) if speedups else 0.0

        comparison["most_scalable"] = max(
            scalability_scores, key=lambda k: scalability_scores[k]
        )

        # Find most efficient — highest throughput per MB of peak memory.
        efficiency_scores = {}
        for system, data in results.items():
            throughput = (
                statistics.mean(data["throughput_curves"].values())
                if data["throughput_curves"]
                else 0.0
            )
            memory = data["resource_usage"]["memory_mb"]
            # Guard against a near-zero tracemalloc reading on a trivial
            # deterministic system: fall back to raw throughput so the
            # ranking stays meaningful instead of dividing by ~0.
            if memory > 0:
                efficiency_scores[system] = throughput / memory * 1000
            else:
                efficiency_scores[system] = throughput

        comparison["most_efficient"] = max(
            efficiency_scores, key=lambda k: efficiency_scores[k]
        )

        # Generate recommendations
        comparison["recommendations"] = [
            f"Use {comparison['fastest_system']} for latency-critical applications",
            f"Use {comparison['most_scalable']} for high-concurrency scenarios",
            f"Use {comparison['most_efficient']} for resource-constrained environments",
        ]

        return comparison


@register_node()
class TestDatasetGeneratorNode(Node):
    """
    RAG Test Dataset Generator

    Generates synthetic test datasets for RAG evaluation.

    When to use:
    - Best for: Creating evaluation benchmarks, testing edge cases
    - Not ideal for: Production data generation
    - Output: Queries with ground truth answers and contexts

    Example:
        generator = TestDatasetGeneratorNode(
            categories=["factual", "analytical", "comparative"],
            difficulty_levels=["easy", "medium", "hard"]
        )

        dataset = generator.execute(
            num_samples=100,
            domain="machine learning"
        )

    Parameters:
        categories: Types of questions to generate
        difficulty_levels: Complexity levels
        include_adversarial: Generate tricky cases

    Returns:
        test_queries: Generated queries with metadata
        reference_answers: Ground truth answers
        test_contexts: Relevant documents
    """

    def __init__(
        self,
        name: str = "test_dataset_generator",
        categories: Optional[List[str]] = None,
        include_adversarial: bool = True,
    ):
        resolved_categories = categories or [
            "factual",
            "analytical",
            "comparative",
        ]
        super().__init__(
            name=name,
            categories=resolved_categories,
            include_adversarial=include_adversarial,
        )
        self.categories = resolved_categories
        self.include_adversarial = include_adversarial

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="test_dataset_generator",
                description="Node instance name",
            ),
            "categories": NodeParameter(
                name="categories",
                type=list,
                required=False,
                default=None,
                description="Question categories to generate",
            ),
            "include_adversarial": NodeParameter(
                name="include_adversarial",
                type=bool,
                required=False,
                default=True,
                description="Include adversarial test cases",
            ),
            "num_samples": NodeParameter(
                name="num_samples",
                type=int,
                required=True,
                description="Number of test samples",
            ),
            "domain": NodeParameter(
                name="domain",
                type=str,
                required=False,
                default="general",
                description="Domain for questions",
            ),
            "seed": NodeParameter(
                name="seed",
                type=int,
                required=False,
                description="Random seed for reproducibility",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Generate test dataset"""
        num_samples = kwargs.get("num_samples", 10)
        domain = kwargs.get("domain", "general")
        seed = kwargs.get("seed")

        if seed:
            random.seed(seed)

        test_dataset = []

        # Templates for different categories
        templates = {
            "factual": [
                ("What is {concept}?", "Definition and explanation of {concept}"),
                (
                    "When was {event} discovered?",
                    "Discovery date and context of {event}",
                ),
                ("Who invented {invention}?", "Inventor and history of {invention}"),
            ],
            "analytical": [
                (
                    "How does {system} work?",
                    "Detailed explanation of {system} mechanics",
                ),
                (
                    "What are the advantages of {method}?",
                    "Benefits and strengths of {method}",
                ),
                (
                    "Why is {principle} important?",
                    "Significance and applications of {principle}",
                ),
            ],
            "comparative": [
                (
                    "Compare {option1} and {option2}",
                    "Comparison of {option1} vs {option2}",
                ),
                (
                    "What's the difference between {concept1} and {concept2}?",
                    "Distinctions between concepts",
                ),
                (
                    "Which is better: {choice1} or {choice2}?",
                    "Trade-offs and recommendations",
                ),
            ],
        }

        # Domain-specific concepts
        domain_concepts = {
            "machine learning": [
                "neural networks",
                "transformers",
                "BERT",
                "attention mechanism",
                "backpropagation",
            ],
            "general": [
                "democracy",
                "photosynthesis",
                "gravity",
                "internet",
                "climate change",
            ],
        }

        concepts = domain_concepts.get(domain, domain_concepts["general"])

        for i in range(num_samples):
            category = random.choice(self.categories)
            template_q, template_a = random.choice(templates[category])

            # Generate specific question
            if "{concept}" in template_q:
                concept = random.choice(concepts)
                query = template_q.format(concept=concept)
                answer = template_a.format(concept=concept)
            else:
                # Handle other placeholders
                query = template_q
                answer = template_a

            # Generate contexts
            contexts = []
            for j in range(3):
                contexts.append(
                    {
                        "id": f"ctx_{i}_{j}",
                        "content": f"Context {j + 1} about {query}: {answer}",
                        "relevance": 0.9 - j * 0.1,
                    }
                )

            # Add adversarial examples if enabled
            metadata = {"category": category, "difficulty": "medium"}

            if self.include_adversarial and random.random() < 0.2:
                # Make it adversarial
                if random.random() < 0.5:
                    # Negation
                    query = f"Is it true that {query.lower()}"
                    metadata["adversarial_type"] = "negation"
                else:
                    # Misleading context
                    contexts.append(
                        {
                            "id": f"ctx_{i}_misleading",
                            "content": f"Incorrect information: {query} is actually false because...",
                            "relevance": 0.7,
                        }
                    )
                    metadata["adversarial_type"] = "misleading_context"

            test_dataset.append(
                {
                    "id": f"test_{i}",
                    "query": query,
                    "reference_answer": answer,
                    "contexts": contexts,
                    "metadata": metadata,
                }
            )

        return {
            "test_dataset": test_dataset,
            "statistics": {
                "total_samples": len(test_dataset),
                "category_distribution": {
                    cat: sum(
                        1 for t in test_dataset if t["metadata"]["category"] == cat
                    )
                    for cat in self.categories
                },
                "adversarial_count": sum(
                    1 for t in test_dataset if "adversarial_type" in t["metadata"]
                ),
            },
            "generation_config": {
                "domain": domain,
                "categories": self.categories,
                "seed": seed,
            },
        }


# Export all evaluation nodes
__all__ = ["RAGEvaluationNode", "RAGBenchmarkNode", "TestDatasetGeneratorNode"]
