"""
Agentic RAG Implementation

Implements RAG with autonomous agent capabilities:
- Tool use for dynamic information retrieval
- Multi-step reasoning with planning
- Self-directed exploration
- Action-observation loops
- Dynamic strategy selection

Based on ReAct, Toolformer, and agent research from 2024.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node

# PythonCodeNode is imported for its @register_node side effect: the
# sub-workflows below reference it by the string "PythonCodeNode", so its
# class must be registered before _create_workflow() runs.
from kailash.nodes.code.python import PythonCodeNode  # noqa: F401
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

# LLMAgentNode is imported for its @register_node side effect: the
# sub-workflows reference it by the string "LLMAgentNode".
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
# conversational.py lines 45-199 and query_processing.py lines 54-212).
#
# LLMAgentNode consumes context EXCLUSIVELY through its `messages` param (the
# OpenAI chat format: a list of {"role","content"} dicts) plus `system_prompt`.
# `LLMAgentNode.run` reads `messages = kwargs["messages"]`; ANY OTHER wired port
# name (`additional_context`, `answer_to_verify`, `reasoning_plan`,
# `reasoning_to_verify`, ...) is read via `kwargs.get` and SILENTLY DROPPED. The
# prior wiring in BOTH agentic WorkflowNodes fed those phantom ports, so every
# LLM stage answered from its `system_prompt` alone — the planner never saw the
# user's query, the ReAct agent never saw the tool observations, the verifier
# never saw the answer it was meant to check, and the reasoning chain never
# reached the step-reasoner or logic-verifier (the L3 "LLM ignores its input"
# defect).
#
# The context contract is HETEROGENEOUS per stage: each composer renders the
# REAL inputs that stage must reason over (the user query and/or the genuine
# upstream node output) into a `messages` list wired to the stage's VALID
# `messages` port. These are real module-level functions (real `return`→
# `result`, type-checkable, no f-string brace-escaping) per the program's
# reference template — NOT inline `code=` codegen blocks. Each is pure data
# rendering (the permitted output-formatting exception per
# rules/agent-reasoning.md) — NO if-else routing / keyword classification on
# content, and NO NEW deterministic agent-loop logic (agentic.py legitimately
# owns ReAct/agent-loop orchestration; these composers only render context).
#
# IN-GRAPH HONESTY (zero-tolerance Rule 2): each composer renders only inputs a
# real upstream node publishes. Where a stage's genuinely-needed input is the
# output of an UPSTREAM LLM stage, that output is only available on the
# upstream's `response` port (a PythonCodeNode consumer between them publishes
# its `result`); the composer renders the REAL available port. No input is
# invented — the ReAct loop's first-pass observations are empty in-graph (the
# state_manager's `context_for_agent` is "" until a tool has executed), which
# the composer renders honestly as a "no observations yet" note rather than
# fabricating tool output.
# ---------------------------------------------------------------------------


def _coerce_text(value: Any) -> str:
    """Coerce a wired input to a clean string.

    The parameter injector delivers top-level inputs as plain strings; wired
    upstream ports may arrive None on an unwired optional branch. PythonCodeNode
    producers may also publish their value pre-stringified.
    """
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _render_reasoning_state(reasoning_state: Any) -> str:
    """Render the state_manager's `reasoning_state` into a readable transcript.

    `reasoning_state` is the state_manager `reasoning_state` port value — the
    dict carrying `steps` (each with thought/action/observation) and
    `final_answer`. Returns the step-by-step trace + the final answer so a
    verifier sees both the answer AND the supporting evidence (the observations).
    Returns "" when no steps exist yet.
    """
    if not isinstance(reasoning_state, dict):
        return ""
    lines: List[str] = []
    for step in reasoning_state.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if step.get("thought"):
            lines.append(f"Thought: {step['thought']}")
        if step.get("action"):
            lines.append(f"Action: {step['action']}")
        if step.get("observation") is not None:
            lines.append(f"Observation: {step['observation']}")
    final = reasoning_state.get("final_answer")
    if final:
        lines.append(f"Answer: {final}")
    return "\n".join(lines).strip()


def compose_planner_messages(query=""):
    """Compose the ``messages`` list for the AgenticRAGNode planner_agent.

    Embeds the REAL user query so the planner builds a step-by-step plan FOR THE
    QUERY — not from its ``system_prompt`` alone. The available tools are already
    rendered into the planner's ``system_prompt`` by the constructor, so the
    query is the only per-request input this stage needs. Returns
    ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.
    """
    q = _coerce_text(query)
    content = (
        "Create a step-by-step research plan for the following query:\n" + q
        if q
        else "No query was provided to plan."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_react_messages(query="", context_for_agent=None):
    """Compose the ``messages`` list for the AgenticRAGNode react_agent.

    Embeds the REAL user query AND the real observations/tool-execution
    transcript the state_manager publishes (``context_for_agent``), so the ReAct
    agent reasons over the query plus what the tools have actually returned so
    far — not from its ``system_prompt`` alone. Returns ``{"messages": [...]}``
    wired to the LLMAgentNode ``messages`` port.

    IN-GRAPH HONESTY: ``context_for_agent`` is the genuine accumulated
    Thought/Action/Observation transcript the state_manager builds from real
    tool_executor output. On the FIRST ReAct pass no tool has executed yet, so
    the state_manager's transcript is empty — rendered here as an explicit
    "no observations yet" note rather than fabricating tool results.
    """
    q = _coerce_text(query)
    observations = _coerce_text(context_for_agent)
    parts = ["Question:\n" + (q or "(empty)")]
    if observations:
        parts.append("Reasoning and observations so far:\n" + observations)
    else:
        parts.append("No observations gathered yet — begin reasoning.")
    return {"messages": [{"role": "user", "content": "\n\n".join(parts)}]}


def compose_verifier_messages(reasoning_state=None):
    """Compose the ``messages`` list for the AgenticRAGNode verifier_agent.

    Embeds the generated answer AND the supporting evidence (the observations
    accumulated across the reasoning steps) the state_manager publishes in
    ``reasoning_state``, so the verifier fact-checks the answer AGAINST its
    evidence — not from its ``system_prompt`` alone. Returns
    ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.
    """
    transcript = _render_reasoning_state(reasoning_state)
    content = (
        "Verify the accuracy of this answer and its supporting evidence:\n" + transcript
        if transcript
        else "No answer or evidence was provided to verify."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_decomposer_messages(query=""):
    """Compose the ``messages`` list for the ReasoningRAGNode problem_decomposer.

    Embeds the REAL problem statement (the user query) so the decomposer breaks
    THE PROBLEM into reasoning steps — not from its ``system_prompt`` alone.
    Returns ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.
    """
    q = _coerce_text(query)
    content = (
        "Break down the following problem into reasoning steps:\n" + q
        if q
        else "No problem was provided to decompose."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_step_reasoner_messages(query="", reasoning_plan=None):
    """Compose the ``messages`` list for the ReasoningRAGNode step_reasoner.

    Embeds the REAL problem (query) AND the upstream problem_decomposer output
    (``reasoning_plan`` — the decomposer's ``response`` carrying the steps +
    assumptions), so the reasoner executes the current step guided by the prior
    decomposition — not from its ``system_prompt`` alone. Returns
    ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.

    ``reasoning_plan`` is the problem_decomposer LLMAgentNode's ``response``
    port value (the parsed decomposition the decomposer's ``system_prompt``
    advertises: ``{"steps": [...], "assumptions": [...], ...}``). It is rendered
    as readable text so the reasoner genuinely sees the plan it must follow.
    """
    q = _coerce_text(query)
    parts = ["Problem:\n" + (q or "(empty)")]
    plan_text = _render_reasoning_plan(reasoning_plan)
    if plan_text:
        parts.append("Decomposition (steps to reason through):\n" + plan_text)
    parts.append("Execute the next reasoning step.")
    return {"messages": [{"role": "user", "content": "\n\n".join(parts)}]}


def compose_logic_verifier_messages(reasoning_to_verify=None):
    """Compose the ``messages`` list for the ReasoningRAGNode logic_verifier.

    Embeds the REAL reasoning chain the upstream step_reasoner produced
    (``reasoning_to_verify`` — the step_reasoner's ``response``), so the verifier
    checks the LOGICAL CONSISTENCY of the actual reasoning — not from its
    ``system_prompt`` alone. Returns ``{"messages": [...]}`` wired to the
    LLMAgentNode ``messages`` port.
    """
    chain = _render_reasoning_plan(reasoning_to_verify)
    content = (
        "Verify the logical consistency of this reasoning:\n" + chain
        if chain
        else "No reasoning chain was provided to verify."
    )
    return {"messages": [{"role": "user", "content": content}]}


def _render_reasoning_plan(value: Any) -> str:
    """Render an upstream LLM stage's ``response`` (decomposition / reasoning
    chain) into readable text.

    The upstream LLMAgentNode publishes its parsed output on the ``response``
    port. It may arrive as a dict (the JSON the ``system_prompt`` advertises) or
    as a plain string. Render whichever shape is present without fabricating.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        lines: List[str] = []
        steps = value.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    goal = step.get("goal") or step.get("question") or ""
                    approach = step.get("approach") or step.get("contribution") or ""
                    num = step.get("step", "")
                    lines.append(
                        f"Step {num}: {goal}" + (f" — {approach}" if approach else "")
                    )
                else:
                    lines.append(str(step))
        assumptions = value.get("assumptions")
        if isinstance(assumptions, list) and assumptions:
            lines.append("Assumptions: " + ", ".join(str(a) for a in assumptions))
        if not lines:
            # No recognized structured keys — render the dict faithfully rather
            # than dropping the real upstream output.
            return _coerce_text(value)
        return "\n".join(lines).strip()
    return _coerce_text(value)


# ---------------------------------------------------------------------------
# Response parsers (O5 output-side fix — same reference template as
# evaluation.py `_unwrap_response_content`/`parse_*_response`, workflows.py,
# graph.py, query_processing.py).
#
# LLMAgentNode publishes its `response` port as `{"content": "<text-or-JSON>",
# ...}` (mock + real providers both — `_mock_llm_response` returns a dict whose
# `content` is a string; JSON-output stages carry a `json.dumps(...)` string).
# The runtime delivers `source_outputs["response"]` for a wired `response` port,
# i.e. the inner `{"content": ...}` dict — NOT a `{"response": ...}` wrapper.
#
# The prior consumers read a NON-EXISTENT `.get("response")` key off that inner
# dict (the planner/react `plan`/`reasoning_response` reads in state_manager,
# the `verification.get("response")` read in result_synthesizer) and the
# reasoning composers rendered the raw `{"content": ...}` wrapper via
# `_render_reasoning_plan` instead of its content. So under the production wire
# shape the ReAct answer was dropped (state_manager crashed on `None.strip()`),
# the verifier verdict was silently skipped (confidence never adjusted), and the
# decomposition/reasoning chains reached their next stage as a stringified dict.
#
# These parsers sit between each LLM stage's `response` port and its consumer.
# They unwrap `response -> .content`, `json.loads` the JSON-output stages, and
# flag malformed output with a typed `parse_error` sentinel (NEVER a fabricated
# parse — zero-tolerance Rule 2). They are real module-level functions (real
# `return` -> `result`, type-checkable) per the program's reference template —
# pure tool-result parsing (the permitted exception per rules/agent-reasoning.md:
# no agent decisions, no content classification, just shape extraction).
# ---------------------------------------------------------------------------


def _unwrap_response_content(response: Any) -> Any:
    """Unwrap the LLMAgentNode ``response`` port into the model's text payload.

    ``LLMAgentNode`` publishes ``response`` as ``{"content": "<text>", ...}``
    (mock + real providers both). A defensive caller may also pass the bare
    string or a pre-parsed structure. Mirrors evaluation.py /
    conversational.py's ``response.get("content", ...)`` unwrap.
    """
    if isinstance(response, dict):
        return response.get("content")
    return response


def parse_reasoning_response(response=None):
    """Parse the react_agent ``response`` into the ReAct prose string.

    The react_agent is a PROSE stage (Thought/Action/Observation/Answer lines),
    so its ``.content`` is used directly as the string the state_manager's line
    parser consumes. Returns ``{"reasoning_text": "<str>"}`` wired to the
    state_manager ``reasoning_response`` input. An empty / missing content
    yields ``""`` (an honest "no reasoning yet"), never a fabricated answer.
    """
    content = _unwrap_response_content(response)
    if content is None:
        return {"reasoning_text": ""}
    if isinstance(content, str):
        return {"reasoning_text": content}
    # A pre-parsed dict/list from some providers — coerce to text faithfully.
    return {"reasoning_text": _coerce_text(content)}


def parse_plan_response(response=None):
    """Parse the planner_agent ``response`` (a JSON plan) into a dict.

    The planner is a JSON-output stage; its ``.content`` is a JSON string
    (``{"plan": [...], "complexity": ...}``). Returns ``{"plan": <dict>}`` wired
    to the state_manager ``plan`` input. Malformed / non-JSON content is FLAGGED
    with a typed sentinel (``{"plan": {"parse_error": "<reason>"}}``) — never a
    fabricated plan (zero-tolerance Rule 2).
    """
    import json

    content = _unwrap_response_content(response)
    if content is None or (isinstance(content, str) and not content.strip()):
        return {"plan": {}}
    if isinstance(content, dict):
        return {"plan": content}
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"plan": {"parse_error": "non-json-response"}}
        if isinstance(parsed, dict):
            return {"plan": parsed}
        return {"plan": {"parse_error": "non-object-json"}}
    return {"plan": {"parse_error": "unexpected-content-type"}}


def parse_verification_response(response=None):
    """Parse the verifier_agent ``response`` (a JSON verdict) into a dict.

    The verifier is a JSON-output stage; its ``.content`` is a JSON string
    (``{"verified": ..., "confidence": ..., "issues": [...]}``). Returns
    ``{"verification": <dict>}`` wired to the result_synthesizer ``verification``
    input. Malformed / non-JSON content is FLAGGED with a typed sentinel
    (``{"verification": {"parse_error": "<reason>"}}``) — never a fabricated
    verdict that would silently inflate or deflate the confidence
    (zero-tolerance Rule 2).
    """
    import json

    content = _unwrap_response_content(response)
    if content is None or (isinstance(content, str) and not content.strip()):
        return {"verification": {}}
    if isinstance(content, dict):
        return {"verification": content}
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"verification": {"parse_error": "non-json-response"}}
        if isinstance(parsed, dict):
            return {"verification": parsed}
        return {"verification": {"parse_error": "non-object-json"}}
    return {"verification": {"parse_error": "unexpected-content-type"}}


def parse_decomposition_response(response=None):
    """Parse the problem_decomposer ``response`` into the decomposition dict.

    The decomposer is a JSON-output stage; its ``.content`` is a JSON string
    (``{"steps": [...], "assumptions": [...], ...}``). Returns
    ``{"reasoning_plan": <dict-or-str>}`` wired to the step_reasoner composer's
    ``reasoning_plan`` input, where ``_render_reasoning_plan`` extracts the
    steps. On non-JSON content the raw text is forwarded as-is (the composer
    renders the prose faithfully) — honest, not fabricated.
    """
    import json

    content = _unwrap_response_content(response)
    if content is None:
        return {"reasoning_plan": ""}
    if isinstance(content, dict):
        return {"reasoning_plan": content}
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # Non-JSON prose: forward the real text so the composer renders it.
            return {"reasoning_plan": content}
        return {"reasoning_plan": parsed}
    return {"reasoning_plan": _coerce_text(content)}


def parse_reasoning_chain_response(response=None):
    """Parse the step_reasoner ``response`` into the reasoning chain.

    The step_reasoner is a PROSE stage; its ``.content`` is the reasoning text
    the logic_verifier checks. Returns ``{"reasoning_to_verify": <dict-or-str>}``
    wired to the logic_verifier composer's ``reasoning_to_verify`` input, where
    ``_render_reasoning_plan`` renders it. A pre-parsed dict (some providers)
    is forwarded as-is; otherwise the raw text is forwarded faithfully.
    """
    import json

    content = _unwrap_response_content(response)
    if content is None:
        return {"reasoning_to_verify": ""}
    if isinstance(content, dict):
        return {"reasoning_to_verify": content}
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"reasoning_to_verify": content}
        return {"reasoning_to_verify": parsed}
    return {"reasoning_to_verify": _coerce_text(content)}


# ---------------------------------------------------------------------------
# COMPUTE-stage functions (#1117 / #1123 / #1118 root-cause fix — same
# reference template as optimized.py / graph.py / query_processing.py).
#
# The AgenticRAGNode sub-workflow's three PythonCodeNode COMPUTE stages
# (tool_executor / state_manager / result_synthesizer) were previously inline
# `code=` codegen blocks. An inline `code=` PythonCodeNode publishes ONLY a flat
# `result` port (the module-scope `result = {...}` dict is wrapped as
# `{"result": {...}}` — its keys are NOT promoted to top-level ports), so every
# downstream edge reading a top-level key (`tool_result`, `reasoning_state`,
# `context_for_agent`, `continue_reasoning`) was a PHANTOM port the runtime
# silently dropped (#1117 publish-nothing). The state_manager block was further
# an f-string carrying doubled `{{ }}` literal braces (#1123 brace-escape) and
# the tool_executor block carried a raw-string regex (escape-trap risk).
#
# These functions lift each block to a real module-level `def` with a `return`
# (the structural successor of the codegen's module-scope `result =`). Wired via
# `PythonCodeNode.from_function`, each publishes the SAME flat `result` port; the
# downstream edges are rewritten to `result.<key>` so the previously-phantom
# ports resolve. They are pure tool-result computation (the permitted exception
# per rules/agent-reasoning.md — no agent decisions, no content classification:
# the ReAct/agent-loop orchestration semantics live UNCHANGED in the line-parser
# and the cyclic graph wiring).
# ---------------------------------------------------------------------------


def execute_tool_action(reasoning_state=None, documents=None) -> dict:
    """Execute the current ReAct action against the documents.

    Parses ``reasoning_state["current_action"]`` (e.g. ``search("query")``) and
    dispatches to the matching tool (search / calculate / database / verify),
    returning ``{"tool_result": <observation>, "timestamp": <iso>}``. This is the
    lifted ``tool_executor`` COMPUTE block — the regex action-parser and the
    AST-walked safe arithmetic evaluator (no eval/exec) are preserved verbatim.
    """
    import re
    from datetime import datetime

    def _execute_tool(action_string, documents, context):
        """Execute tool based on action string"""
        # Parse action
        match = re.match(r"(\w+)\((.*)\)", action_string.strip())
        if not match:
            return {"error": "Invalid action format"}

        tool_name = match.group(1)
        params = match.group(2).strip("\"'")

        results = {}

        if tool_name == "search":
            # Search through documents
            query_words = set(params.lower().split())
            search_results = []

            for doc in documents[:50]:  # Limit for performance
                if not isinstance(doc, dict):
                    continue  # skip malformed non-dict document elements
                # `.get("content", "")` only defaults a MISSING key; a present
                # key with a None value would still yield None, so coerce.
                content = (doc.get("content") or "").lower()
                title = (doc.get("title") or "").lower()

                # Score based on word overlap
                doc_words = set(content.split())
                title_words = set(title.split())

                content_score = (
                    len(query_words & doc_words) / len(query_words)
                    if query_words
                    else 0
                )
                title_score = (
                    len(query_words & title_words) / len(query_words)
                    if query_words
                    else 0
                )

                total_score = content_score + (
                    title_score * 2
                )  # Title matches weighted higher

                if total_score > 0:
                    search_results.append(
                        {
                            "title": doc.get("title", "Untitled"),
                            "excerpt": content[:200] + "...",
                            "score": total_score,
                            "id": doc.get("id", "unknown"),
                        }
                    )

            # Sort by score
            search_results.sort(key=lambda x: x["score"], reverse=True)
            results = {
                "tool": "search",
                "query": params,
                "results": search_results[:5],
                "count": len(search_results),
            }

        elif tool_name == "calculate":
            # Safe calculation — AST-walked arithmetic only. `params` is
            # LLM-generated; eval()/regex-substitution sandboxes are bypassable,
            # so this whitelists ast node types instead (no eval, no exec, no
            # regex).
            import ast
            import math
            import operator

            _BINOPS = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.Mod: operator.mod,
                ast.FloorDiv: operator.floordiv,
            }
            _UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
            _FUNCS = {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "pow": pow,
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "log": math.log,
                "exp": math.exp,
            }
            _CONSTS = {"pi": math.pi, "e": math.e}

            def _safe_arith(node):
                if isinstance(node, ast.Expression):
                    return _safe_arith(node.body)
                if isinstance(node, ast.Constant):
                    if isinstance(node.value, (int, float)) and not isinstance(
                        node.value, bool
                    ):
                        return node.value
                    raise ValueError("non-numeric constant")
                if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
                    return _BINOPS[type(node.op)](
                        _safe_arith(node.left), _safe_arith(node.right)
                    )
                if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
                    return _UNARYOPS[type(node.op)](_safe_arith(node.operand))
                if isinstance(node, ast.Name) and node.id in _CONSTS:
                    return _CONSTS[node.id]
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in _FUNCS
                    and not node.keywords
                ):
                    return _FUNCS[node.func.id](*[_safe_arith(a) for a in node.args])
                raise ValueError("disallowed expression element")

            try:
                try:
                    calc_result = ast.literal_eval(params)
                except (ValueError, SyntaxError):
                    calc_result = _safe_arith(ast.parse(params, mode="eval"))
                results = {
                    "tool": "calculate",
                    "expression": params,
                    "result": calc_result,
                }
            except Exception:
                results = {
                    "tool": "calculate",
                    "error": f"Cannot evaluate expression: {params}",
                }

        elif tool_name == "database":
            # Simulated database query
            if "revenue" in params.lower():
                # Mock financial data
                results = {
                    "tool": "database",
                    "query": params,
                    "results": [
                        {
                            "company": "TechCorp",
                            "revenue_2022": 100,
                            "revenue_2023": 120,
                        },
                        {"company": "DataInc", "revenue_2022": 80, "revenue_2023": 95},
                        {"company": "CloudCo", "revenue_2022": 60, "revenue_2023": 85},
                    ],
                }
            else:
                results = {"tool": "database", "query": params, "results": []}

        elif tool_name == "verify":
            # Fact verification (simplified)
            confidence = 0.85 if "true" not in params.lower() else 0.95
            results = {
                "tool": "verify",
                "claim": params,
                "verified": confidence > 0.8,
                "confidence": confidence,
                "sources": ["Document analysis", "Cross-reference check"],
            }

        else:
            results = {"error": f"Unknown tool: {tool_name}"}

        return results

    # Execute current action
    state = reasoning_state if isinstance(reasoning_state, dict) else {}
    docs = documents if isinstance(documents, list) else []

    current_action = state.get("current_action", "")
    if current_action:
        observation = _execute_tool(current_action, docs, state)
    else:
        observation = {"error": "No action specified"}

    return {
        "tool_result": observation,
        "timestamp": datetime.now().isoformat(),
    }


def _make_state_manager(max_reasoning_steps: int):
    """Build a from_function-compatible state-manager bound to the step cap.

    The build-time ``max_reasoning_steps`` is bound through a thin closure (the
    f-string's only interpolation), keeping ``plan`` / ``reasoning_response`` /
    ``tool_result`` as the declared inputs the parser/loop ports wire to. The
    returned function manages the ReAct reasoning state across iterations and
    publishes ``{"reasoning_state", "context_for_agent", "continue_reasoning"}``
    on the flat ``result`` port — the doubled-brace f-string codegen (#1123) is
    eliminated; the line-parser semantics are preserved verbatim.
    """

    def update_reasoning_state(plan=None, reasoning_response=None, tool_result=None):
        """Update the ReAct reasoning state with the latest LLM response."""

        def _update(state, new_response, tool_res=None):
            if not state:
                state = {
                    "steps": [],
                    "current_step": 0,
                    "completed": False,
                    "final_answer": None,
                }

            # Parse response for thought/action/answer
            lines = new_response.strip().split("\n")
            current_thought = None
            current_action = None
            final_answer = None

            for line in lines:
                if line.startswith("Thought:"):
                    current_thought = line[8:].strip()
                elif line.startswith("Action:"):
                    current_action = line[7:].strip()
                elif line.startswith("Answer:"):
                    final_answer = line[7:].strip()
                    state["completed"] = True

            # Add step
            step = {
                "step_number": state["current_step"] + 1,
                "thought": current_thought,
                "action": current_action,
                "observation": tool_res.get("tool_result") if tool_res else None,
            }

            state["steps"].append(step)
            state["current_step"] += 1
            state["current_action"] = current_action
            state["final_answer"] = final_answer

            # Check if we've reached max steps
            if state["current_step"] >= max_reasoning_steps:
                state["completed"] = True
                if not state["final_answer"]:
                    state["final_answer"] = (
                        "Reached maximum reasoning steps. "
                        "Based on gathered information..."
                    )

            return state

        # Process current iteration. `plan` arrives from the plan parser as the
        # parsed planner dict; `reasoning_response` arrives from the reasoning
        # parser as the ReAct prose STRING (the parsers already unwrapped
        # `response.content` upstream, so NO further `.get("response")` unwrap is
        # needed). `reasoning_response` may still be a non-str on a defensive
        # path; coerce so the line parser never crashes.
        if not isinstance(reasoning_response, str):
            reasoning_response = (
                "" if reasoning_response is None else str(reasoning_response)
            )

        state = _update(None, reasoning_response, tool_result)

        # Record the planner's parsed plan onto the reasoning state so it is
        # surfaced downstream (the planner → plan_parser → state_manager `plan`
        # edge is the Wave-2.5 O5 wiring; the prior codegen accepted `plan` but
        # dropped it — recording it here consumes the input honestly per
        # zero-tolerance Rule 3c without inventing agent-decision logic).
        if plan is not None:
            state["plan"] = plan

        # Prepare context for next iteration
        context_for_agent = ""
        for step in state["steps"]:
            if step["thought"]:
                context_for_agent += f"\nThought: {step['thought']}"
            if step["action"]:
                context_for_agent += f"\nAction: {step['action']}"
            if step["observation"]:
                context_for_agent += f"\nObservation: {step['observation']}"

        return {
            "reasoning_state": state,
            "context_for_agent": context_for_agent,
            "continue_reasoning": not state["completed"],
        }

    return update_reasoning_state


def _make_result_synthesizer(planning_strategy: str, max_reasoning_steps: int):
    """Build a from_function-compatible synthesizer bound to the build config.

    The build-time ``planning_strategy`` / ``max_reasoning_steps`` (the only
    f-string interpolations in the original codegen) are bound through a thin
    closure, keeping ``reasoning_state`` / ``verification`` / ``query`` as the
    declared inputs. Returns the final ``{"agentic_rag_result": {...}}`` dict on
    the flat ``result`` port — the doubled-brace f-string codegen (#1123) is
    eliminated; the confidence/trace computation is preserved verbatim.
    """

    def synthesize_agentic_result(reasoning_state=None, verification=None, query=""):
        """Synthesize the final agentic-RAG result dict."""
        state = reasoning_state if isinstance(reasoning_state, dict) else {}
        steps = state.get("steps", []) if isinstance(state, dict) else []

        # Extract tool usage
        tools_used = []
        for step in steps:
            obs = step.get("observation") if isinstance(step, dict) else None
            if isinstance(obs, dict) and "tool" in obs:
                tools_used.append(obs["tool"])

        # Calculate confidence. `verification` arrives from the verification
        # parser as the PARSED verifier dict (or a parse-error sentinel carrying
        # `{"parse_error": ...}`) — already unwrapped from `response.content` +
        # json.loads upstream. A flagged parse-error sentinel carries no real
        # confidence, so it is treated as "no usable verdict" (NOT a fabricated
        # 0.8) and confidence is left unadjusted — honest, per zero-tolerance
        # Rule 2.
        base_confidence = 0.7
        confidence_boost = min(0.3, len(tools_used) * 0.1)
        _has_verdict = (
            isinstance(verification, dict)
            and "confidence" in verification
            and verification.get("parse_error") is None
        )
        if _has_verdict:
            verification_confidence = verification.get("confidence", 0.8)
            final_confidence = (
                base_confidence + confidence_boost
            ) * verification_confidence
        else:
            final_confidence = base_confidence + confidence_boost

        # Build reasoning trace
        reasoning_trace = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            reasoning_trace.append(
                {
                    "step": step.get("step_number"),
                    "thought": step.get("thought"),
                    "action": step.get("action"),
                    "observation": step.get("observation"),
                }
            )

        return {
            "agentic_rag_result": {
                "query": query,
                "answer": state.get("final_answer"),
                "reasoning_trace": reasoning_trace,
                "tools_used": list(set(tools_used)),
                "confidence": final_confidence,
                "total_steps": len(steps),
                "verification": verification if _has_verdict else None,
                "metadata": {
                    "planning_strategy": planning_strategy,
                    "max_steps": max_reasoning_steps,
                    "completed_successfully": state.get("completed", False),
                },
            }
        }

    return synthesize_agentic_result


@register_node()
class AgenticRAGNode(WorkflowNode):
    """
    Agentic RAG with Tool Use and Reasoning

    Implements autonomous agent capabilities for complex RAG tasks requiring
    multiple steps, external tools, and dynamic reasoning.

    When to use:
    - Best for: Complex research tasks, multi-source queries, dynamic exploration
    - Not ideal for: Simple lookups, static document sets
    - Performance: 3-10 seconds depending on reasoning steps
    - Quality improvement: 50-80% for complex analytical tasks

    Key features:
    - ReAct-style reasoning (Thought-Action-Observation loops)
    - Dynamic tool selection and use
    - Multi-step planning and execution
    - Self-directed information gathering
    - Verification and fact-checking

    Example:
        agentic_rag = AgenticRAGNode(
            tools=["search", "calculator", "database", "code_executor"],
            max_reasoning_steps=5
        )

        # Query: "Compare the revenue growth of tech companies in 2023 vs 2022"
        # Agent will:
        # 1. Plan the research approach
        # 2. Search for financial data
        # 3. Query databases for specific numbers
        # 4. Use calculator for growth calculations
        # 5. Synthesize findings with citations

        result = await agentic_rag.execute(
            documents=financial_docs,
            query="Compare the revenue growth of tech companies in 2023 vs 2022"
        )

    Parameters:
        tools: List of available tools (search, api, database, etc.)
        max_reasoning_steps: Maximum reasoning iterations
        planning_strategy: How to plan actions (react, tree-of-thought)
        verification_enabled: Whether to verify findings

    Returns:
        answer: Final synthesized answer
        reasoning_trace: Complete thought-action-observation history
        tools_used: Which tools were utilized
        confidence: Agent's confidence in the answer
    """

    def __init__(
        self,
        name: str = "agentic_rag",
        tools: Optional[List[str]] = None,
        max_reasoning_steps: int = 5,
        planning_strategy: str = "react",
        verification_enabled: bool = True,
    ):
        self.tools = tools or ["search", "calculator", "database"]
        self.max_reasoning_steps = max_reasoning_steps
        self.planning_strategy = planning_strategy
        self.verification_enabled = verification_enabled
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create agentic RAG workflow"""
        builder = WorkflowBuilder()

        # Planning agent
        planner_id = builder.add_node(
            "LLMAgentNode",
            node_id="planner_agent",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": f"""You are a research planning agent. Given a query, create a step-by-step plan.

Available tools: {", ".join(self.tools)}

For each step, specify:
1. What information is needed
2. Which tool to use
3. Expected outcome

Return JSON:
{{
    "plan": [
        {{"step": 1, "action": "search", "query": "...", "purpose": "..."}},
        {{"step": 2, "action": "calculate", "expression": "...", "purpose": "..."}}
    ],
    "complexity": "simple|moderate|complex",
    "estimated_steps": 3
}}""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # ReAct reasoning loop
        react_agent_id = builder.add_node(
            "LLMAgentNode",
            node_id="react_agent",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": f"""You are a ReAct agent that reasons step-by-step and uses tools.

Available tools:
- search(query): Search documents or web
- calculate(expression): Perform calculations
- database(query): Query structured data
- verify(claim): Fact-check a claim

Format your response:
Thought: [reasoning about what to do next]
Action: [tool_name(parameters)]
Observation: [I'll fill this in]

Continue until you have enough information to answer.
End with:
Answer: [final comprehensive answer]

Maximum steps: {self.max_reasoning_steps}""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Tool executor
        tool_executor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                execute_tool_action,
                name="tool_executor",
            ),
            node_id="tool_executor",
            _internal=True,
        )

        # Reasoning state manager
        _state_manager_fn = _make_state_manager(self.max_reasoning_steps)
        state_manager_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _state_manager_fn,
                name="state_manager",
            ),
            node_id="state_manager",
            _internal=True,
        )

        # Verification agent (if enabled)
        verifier_id: Optional[str] = None
        if self.verification_enabled:
            verifier_id = builder.add_node(
                "LLMAgentNode",
                node_id="verifier_agent",
                config={
                    "provider": detect_provider_from_env(),
                    "system_prompt": """You are a fact-checking agent. Verify the accuracy of the answer.

Check for:
1. Factual accuracy
2. Logical consistency
3. Completeness
4. Source reliability

Return JSON:
{
    "verified": true/false,
    "confidence": 0.0-1.0,
    "issues": ["list of any issues found"],
    "suggestions": ["improvements if needed"]
}""",
                    "model": _DEFAULT_LLM_MODEL,
                },
            )

        # Result synthesizer (#1117/#1123 root-cause fix: lifted from the prior
        # doubled-brace f-string codegen to `_make_result_synthesizer`, with the
        # build-time planning_strategy / max_reasoning_steps bound through the
        # closure). Publishes the SAME flat `result` port carrying
        # `{"agentic_rag_result": {...}}` — it is the terminal synthesis node, so
        # the WorkflowNode surfaces its output unchanged.
        _result_synthesizer_fn = _make_result_synthesizer(
            self.planning_strategy, self.max_reasoning_steps
        )
        synthesizer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _result_synthesizer_fn,
                name="result_synthesizer",
            ),
            node_id="result_synthesizer",
            _internal=True,
        )

        # L3 messages-composers (reference template — conversational.py /
        # query_processing.py). Each LLM stage previously received NO real input
        # on a port LLMAgentNode reads (its `run` reads only `kwargs["messages"]`)
        # — the planner/react/verifier answered from their `system_prompt` alone.
        # Each composer renders the REAL inputs that stage must reason over into
        # a `messages` list wired to the VALID `messages` port. `from_function`
        # is the correct primitive (real module-level functions: real `return`→
        # `result`, type-checkable). The call is BARE (no `# type: ignore`): the
        # `from_function` unknown-attr pyright diagnostic is non-gating (gates =
        # ruff + pytest) and the suppression is normalized away across the rag
        # from_function sites. `_internal=True` suppresses the consumer-facing
        # instance-API advisory.
        planner_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_planner_messages,
                name="planner_messages_composer",
            ),
            node_id="planner_messages_composer",
            _internal=True,
        )
        react_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_react_messages,
                name="react_messages_composer",
            ),
            node_id="react_messages_composer",
            _internal=True,
        )
        verifier_messages_composer_id: Optional[str] = None
        if self.verification_enabled:
            verifier_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    compose_verifier_messages,
                    name="verifier_messages_composer",
                ),
                node_id="verifier_messages_composer",
                _internal=True,
            )

        # O5 output-side response parsers. Each sits between an LLM stage's
        # `response` port and its PythonCodeNode consumer, unwrapping
        # `response -> .content` (+ json.loads for JSON-output stages) so the
        # consumer reads PARSED fields — NOT the raw `{"content": ...}` wrapper
        # off which the prior `.get("response")` read a non-existent key.
        plan_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_plan_response,
                name="plan_parser",
            ),
            node_id="plan_parser",
            _internal=True,
        )
        reasoning_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_reasoning_response,
                name="reasoning_parser",
            ),
            node_id="reasoning_parser",
            _internal=True,
        )
        verification_parser_id: Optional[str] = None
        if self.verification_enabled:
            verification_parser_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    parse_verification_response,
                    name="verification_parser",
                ),
                node_id="verification_parser",
                _internal=True,
            )

        # Connect workflow
        # Planning phase. The planner composer renders the REAL top-level `query`
        # (the parameter injector delivers it) into the planner's `messages`
        # port; the planner's `response` is PARSED (response.content -> json) by
        # the plan_parser, whose `result.plan` feeds the state_manager `plan`.
        builder.add_connection(
            planner_messages_composer_id, "result.messages", planner_id, "messages"
        )
        builder.add_connection(planner_id, "response", plan_parser_id, "response")
        builder.add_connection(plan_parser_id, "result.plan", state_manager_id, "plan")

        # ReAct loop connections.
        # FIX: the prior `state_manager.context_for_agent ->
        # react_agent.additional_context` phantom edge fed the observations to a
        # port LLMAgentNode silently drops. The react composer now renders the
        # REAL `query` PLUS the real `state_manager.context_for_agent` (the
        # accumulated Thought/Action/Observation transcript) into the react
        # agent's `messages` port. The phantom `additional_context` edge is
        # REMOVED.
        # PHANTOM-PORT FIX: state_manager is now a `from_function` node, which
        # publishes ONLY a flat `result` port — `context_for_agent` is a KEY of
        # that dict, NOT a top-level port. The edge reads `result.context_for_agent`.
        builder.add_connection(
            state_manager_id,
            "result.context_for_agent",
            react_messages_composer_id,
            "context_for_agent",
        )
        builder.add_connection(
            react_messages_composer_id, "result.messages", react_agent_id, "messages"
        )
        # The react_agent `response` is PARSED (response.content -> prose string)
        # by the reasoning_parser; its `result.reasoning_text` feeds the
        # state_manager `reasoning_response` (the line parser consumes a string).
        builder.add_connection(
            react_agent_id, "response", reasoning_parser_id, "response"
        )
        builder.add_connection(
            reasoning_parser_id,
            "result.reasoning_text",
            state_manager_id,
            "reasoning_response",
        )
        # PHANTOM-PORT FIX (cyclic edges): both state_manager and tool_executor
        # are `from_function` nodes publishing a flat `result` port, so each
        # cycle edge reads `result.<key>`. `reasoning_state` / `tool_result` are
        # KEYS of the respective `result` dict, not top-level ports.
        builder.add_connection(
            state_manager_id,
            "result.reasoning_state",
            tool_executor_id,
            "reasoning_state",
        )
        builder.add_connection(
            tool_executor_id, "result.tool_result", state_manager_id, "tool_result"
        )

        # Loop control - continue if not completed. `continue_reasoning` is a KEY
        # of the state_manager `result` dict (from_function flat port), so the
        # loop-control edge reads `result.continue_reasoning`.
        builder.add_connection(
            state_manager_id,
            "result.continue_reasoning",
            react_agent_id,
            "_continue_if_true",
        )

        # Verification (if enabled).
        # FIX: the prior `state_manager.reasoning_state ->
        # verifier_agent.answer_to_verify` phantom edge fed the answer+evidence
        # to a dropped port. The verifier composer now renders the generated
        # answer AND its supporting evidence (the observations across the
        # reasoning steps, carried in `reasoning_state`) into the verifier's
        # `messages` port. The phantom `answer_to_verify` edge is REMOVED.
        if self.verification_enabled:
            # verifier_id + verifier_messages_composer_id were assigned in the
            # matching `if` blocks above; the asserts document that invariant
            # and narrow the type for pyright.
            assert verifier_id is not None
            assert verifier_messages_composer_id is not None
            assert verification_parser_id is not None
            builder.add_connection(
                state_manager_id,
                "result.reasoning_state",
                verifier_messages_composer_id,
                "reasoning_state",
            )
            builder.add_connection(
                verifier_messages_composer_id,
                "result.messages",
                verifier_id,
                "messages",
            )
            # The verifier_agent `response` is PARSED (response.content -> json)
            # by the verification_parser; its `result.verification` feeds the
            # result_synthesizer `verification` (the parsed verdict dict).
            builder.add_connection(
                verifier_id, "response", verification_parser_id, "response"
            )
            builder.add_connection(
                verification_parser_id,
                "result.verification",
                synthesizer_id,
                "verification",
            )

        # Final synthesis. `reasoning_state` is a KEY of the state_manager
        # `from_function` `result` dict, so the edge reads `result.reasoning_state`.
        builder.add_connection(
            state_manager_id,
            "result.reasoning_state",
            synthesizer_id,
            "reasoning_state",
        )

        return builder.build(name="agentic_rag_workflow")


@register_node()
class ToolAugmentedRAGNode(Node):
    """
    Tool-Augmented RAG Node

    Enhances RAG with specific tool capabilities for specialized tasks.

    When to use:
    - Best for: Domain-specific queries requiring specialized tools
    - Not ideal for: General knowledge questions
    - Performance: 1-5 seconds depending on tools used
    - Accuracy: High for tool-supported domains

    Example:
        tool_rag = ToolAugmentedRAGNode(
            tool_registry={
                "calculator": calculate_func,
                "unit_converter": convert_units,
                "date_calculator": date_math
            }
        )

    Parameters:
        tool_registry: Dict of tool_name -> callable
        auto_detect_tools: Automatically detect needed tools
        fallback_strategy: What to do if tools fail

    Returns:
        answer: Tool-augmented response
        tools_invoked: List of tools used
        tool_outputs: Results from each tool
    """

    def __init__(
        self,
        name: str = "tool_augmented_rag",
        tool_registry: Optional[Dict[str, Callable]] = None,
        auto_detect_tools: bool = True,
    ):
        resolved_registry = tool_registry or {}
        super().__init__(
            name=name,
            tool_registry=resolved_registry,
            auto_detect_tools=auto_detect_tools,
        )
        self.tool_registry = resolved_registry
        self.auto_detect_tools = auto_detect_tools

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="tool_augmented_rag",
                description="Node instance name",
            ),
            "tool_registry": NodeParameter(
                name="tool_registry",
                type=dict,
                required=False,
                default=None,
                description="Mapping of tool name to callable",
            ),
            "auto_detect_tools": NodeParameter(
                name="auto_detect_tools",
                type=bool,
                required=False,
                default=True,
                description="Automatically detect which tools to invoke",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Query requiring tool augmentation",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=False,
                description="Reference documents",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                description="Additional context for tools",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute tool-augmented RAG"""
        query = kwargs.get("query", "")
        documents = kwargs.get("documents", [])
        context = kwargs.get("context", {})

        # Detect required tools
        required_tools = self._detect_required_tools(query)

        # Execute tools
        tool_outputs = {}
        for tool_name in required_tools:
            if tool_name in self.tool_registry:
                try:
                    tool_func = self.tool_registry[tool_name]
                    tool_outputs[tool_name] = tool_func(query, context)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    tool_outputs[tool_name] = {"error": str(e)}

        # Augment response with tool outputs
        augmented_answer = self._synthesize_with_tools(query, documents, tool_outputs)

        return {
            "answer": augmented_answer,
            "tools_invoked": list(required_tools),
            "tool_outputs": tool_outputs,
            "confidence": 0.9 if tool_outputs else 0.7,
        }

    def _detect_required_tools(self, query: str) -> List[str]:
        """Detect which tools are needed for the query"""
        required = []

        # `query` is declared required, but a caller may still pass it as
        # None explicitly; coerce so tool detection never crashes.
        query_lower = (query or "").lower()

        # Simple keyword detection (would use NER/classification in production)
        if any(
            word in query_lower for word in ["calculate", "compute", "sum", "average"]
        ):
            required.append("calculator")

        if any(word in query_lower for word in ["convert", "unit", "measurement"]):
            required.append("unit_converter")

        if any(word in query_lower for word in ["date", "days", "weeks", "months"]):
            required.append("date_calculator")

        return required

    def _synthesize_with_tools(
        self, query: str, documents: List[Dict], tool_outputs: Dict[str, Any]
    ) -> str:
        """Synthesize answer using tool outputs"""
        # In production, would use LLM for synthesis
        answer_parts = [f"Based on analysis of {len(documents)} documents"]

        if tool_outputs:
            answer_parts.append("and computational tools:")
            for tool, output in tool_outputs.items():
                # Registered tools are arbitrary user callables with no
                # return-shape contract; only dict outputs carry an "error"
                # key, so a non-dict return is treated as a successful result.
                if not isinstance(output, dict) or "error" not in output:
                    answer_parts.append(f"\n- {tool}: {output}")

        answer_parts.append(
            f"\nThe answer to '{query}' has been computed with tool assistance."
        )

        return " ".join(answer_parts)


@register_node()
class ReasoningRAGNode(WorkflowNode):
    """
    Multi-Step Reasoning RAG

    Implements complex reasoning chains for analytical queries.

    When to use:
    - Best for: Complex analytical questions, multi-step problems
    - Not ideal for: Simple factual queries
    - Performance: 2-8 seconds depending on reasoning depth
    - Quality: Superior for questions requiring logic and analysis

    Example:
        reasoning_rag = ReasoningRAGNode(
            reasoning_depth=3,
            strategy="chain_of_thought"
        )

        # Query: "If Company A grows 20% annually and Company B grows 15%,
        #         when will A's revenue exceed B's if B starts 50% larger?"
        # Will break down into steps and reason through the math

    Parameters:
        reasoning_depth: Maximum reasoning steps
        strategy: Reasoning strategy (chain_of_thought, tree_of_thought)
        verify_logic: Whether to verify logical consistency

    Returns:
        answer: Reasoned answer with steps
        reasoning_chain: Step-by-step logic
        assumptions: Assumptions made
        confidence: Confidence in reasoning
    """

    def __init__(
        self,
        name: str = "reasoning_rag",
        reasoning_depth: int = 3,
        strategy: str = "chain_of_thought",
    ):
        self.reasoning_depth = reasoning_depth
        self.strategy = strategy
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create reasoning RAG workflow"""
        builder = WorkflowBuilder()

        # Problem decomposer
        decomposer_id = builder.add_node(
            "LLMAgentNode",
            node_id="problem_decomposer",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": f"""Break down complex problems into reasoning steps.

Strategy: {self.strategy}
Max depth: {self.reasoning_depth}

For each step specify:
1. What to determine
2. Required information
3. Logic/calculation needed

Return JSON:
{{
    "steps": [
        {{"step": 1, "goal": "...", "requires": ["..."], "approach": "..."}}
    ],
    "assumptions": ["list assumptions"],
    "complexity": "low|medium|high"
}}""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Step-by-step reasoner
        step_reasoner_id = builder.add_node(
            "LLMAgentNode",
            node_id="step_reasoner",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Execute one reasoning step at a time.

Given:
- Current step goal
- Available information
- Previous steps' results

Provide:
- Logical reasoning
- Calculations if needed
- Conclusion for this step
- What's needed next

Be explicit about your logic.""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Logic verifier
        verifier_id = builder.add_node(
            "LLMAgentNode",
            node_id="logic_verifier",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Verify the logical consistency of reasoning.

Check:
1. Are all steps logically sound?
2. Do conclusions follow from premises?
3. Are calculations correct?
4. Are assumptions reasonable?

Rate confidence: 0.0-1.0""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # L3 messages-composers (reference template). Each LLM stage previously
        # received NO real input on a port LLMAgentNode reads (its `run` reads
        # only `kwargs["messages"]`): the decomposer never saw the problem, the
        # step_reasoner's `reasoning_plan` + the logic_verifier's
        # `reasoning_to_verify` were both phantom ports the node silently drops.
        # Each composer renders the REAL inputs (the query and/or the genuine
        # upstream LLM `response`) into the stage's VALID `messages` port.
        decomposer_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_decomposer_messages,
                name="decomposer_messages_composer",
            ),
            node_id="decomposer_messages_composer",
            _internal=True,
        )
        step_reasoner_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_step_reasoner_messages,
                name="step_reasoner_messages_composer",
            ),
            node_id="step_reasoner_messages_composer",
            _internal=True,
        )
        logic_verifier_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_logic_verifier_messages,
                name="logic_verifier_messages_composer",
            ),
            node_id="logic_verifier_messages_composer",
            _internal=True,
        )

        # O5 output-side response parsers. Each sits between an LLM stage's
        # `response` port and the downstream composer, unwrapping
        # `response -> .content` (+ json.loads for the decomposer's JSON output)
        # so the composer's `_render_reasoning_plan` receives the PARSED
        # decomposition / reasoning chain — NOT the raw `{"content": ...}`
        # wrapper, which `_render_reasoning_plan` would otherwise stringify
        # (the steps/assumptions never extracted).
        decomposition_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_decomposition_response,
                name="decomposition_parser",
            ),
            node_id="decomposition_parser",
            _internal=True,
        )
        reasoning_chain_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_reasoning_chain_response,
                name="reasoning_chain_parser",
            ),
            node_id="reasoning_chain_parser",
            _internal=True,
        )

        # Connect workflow.
        # Stage 1: the REAL top-level `query` (parameter injector) → decomposer
        # composer → decomposer.messages.
        builder.add_connection(
            decomposer_messages_composer_id,
            "result.messages",
            decomposer_id,
            "messages",
        )
        # Stage 2: the decomposer.response is PARSED (response.content -> json)
        # by the decomposition_parser; its `result.reasoning_plan` (the real
        # decomposition dict) feeds the step_reasoner composer's `reasoning_plan`
        # input, which `_render_reasoning_plan` renders into the reasoner's
        # `messages`. (`query` is the top-level injected input.)
        builder.add_connection(
            decomposer_id,
            "response",
            decomposition_parser_id,
            "response",
        )
        builder.add_connection(
            decomposition_parser_id,
            "result.reasoning_plan",
            step_reasoner_messages_composer_id,
            "reasoning_plan",
        )
        builder.add_connection(
            step_reasoner_messages_composer_id,
            "result.messages",
            step_reasoner_id,
            "messages",
        )
        # Stage 3: the step_reasoner.response (the reasoning chain) is PARSED
        # (response.content) by the reasoning_chain_parser; its
        # `result.reasoning_to_verify` feeds the logic_verifier composer, which
        # renders the real chain into the verifier's `messages`.
        builder.add_connection(
            step_reasoner_id,
            "response",
            reasoning_chain_parser_id,
            "response",
        )
        builder.add_connection(
            reasoning_chain_parser_id,
            "result.reasoning_to_verify",
            logic_verifier_messages_composer_id,
            "reasoning_to_verify",
        )
        builder.add_connection(
            logic_verifier_messages_composer_id,
            "result.messages",
            verifier_id,
            "messages",
        )

        return builder.build(name="reasoning_rag_workflow")


# Export all agentic nodes
__all__ = ["AgenticRAGNode", "ToolAugmentedRAGNode", "ReasoningRAGNode"]
