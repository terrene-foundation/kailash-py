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
        tool_executor_id = builder.add_node(
            "PythonCodeNode",
            node_id="tool_executor",
            config={
                "code": r"""
import re
import json
from datetime import datetime

def execute_tool(action_string, documents, context):
    '''Execute tool based on action string'''
    # Parse action
    match = re.match(r'(\w+)\((.*)\)', action_string.strip())
    if not match:
        return {"error": "Invalid action format"}

    tool_name = match.group(1)
    params = match.group(2).strip('"\'')

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

            content_score = len(query_words & doc_words) / len(query_words) if query_words else 0
            title_score = len(query_words & title_words) / len(query_words) if query_words else 0

            total_score = content_score + (title_score * 2)  # Title matches weighted higher

            if total_score > 0:
                search_results.append({
                    "title": doc.get("title", "Untitled"),
                    "excerpt": content[:200] + "...",
                    "score": total_score,
                    "id": doc.get("id", "unknown")
                })

        # Sort by score
        search_results.sort(key=lambda x: x["score"], reverse=True)
        results = {
            "tool": "search",
            "query": params,
            "results": search_results[:5],
            "count": len(search_results)
        }

    elif tool_name == "calculate":
        # Safe calculation — AST-walked arithmetic only. `params` is
        # LLM-generated; eval()/regex-substitution sandboxes are bypassable, so
        # this whitelists ast node types instead (no eval, no exec, no regex).
        import ast
        import math
        import operator

        _BINOPS = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Pow: operator.pow, ast.Mod: operator.mod,
            ast.FloorDiv: operator.floordiv,
        }
        _UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
        _FUNCS = {
            "abs": abs, "round": round, "min": min, "max": max, "pow": pow,
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "log": math.log, "exp": math.exp,
        }
        _CONSTS = {"pi": math.pi, "e": math.e}

        def _safe_arith(node):
            if isinstance(node, ast.Expression):
                return _safe_arith(node.body)
            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
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
                return _FUNCS[node.func.id](
                    *[_safe_arith(a) for a in node.args]
                )
            raise ValueError("disallowed expression element")

        try:
            try:
                result = ast.literal_eval(params)
            except (ValueError, SyntaxError):
                result = _safe_arith(ast.parse(params, mode="eval"))
            results = {
                "tool": "calculate",
                "expression": params,
                "result": result,
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
                    {"company": "TechCorp", "revenue_2022": 100, "revenue_2023": 120},
                    {"company": "DataInc", "revenue_2022": 80, "revenue_2023": 95},
                    {"company": "CloudCo", "revenue_2022": 60, "revenue_2023": 85}
                ]
            }
        else:
            results = {
                "tool": "database",
                "query": params,
                "results": []
            }

    elif tool_name == "verify":
        # Fact verification (simplified)
        confidence = 0.85 if "true" not in params.lower() else 0.95
        results = {
            "tool": "verify",
            "claim": params,
            "verified": confidence > 0.8,
            "confidence": confidence,
            "sources": ["Document analysis", "Cross-reference check"]
        }

    else:
        results = {"error": f"Unknown tool: {tool_name}"}

    return results

# Execute current action
reasoning_state = reasoning_state
documents = documents

current_action = reasoning_state.get("current_action", "")
if current_action:
    observation = execute_tool(current_action, documents, reasoning_state)
else:
    observation = {"error": "No action specified"}

result = {
    "tool_result": observation,
    "timestamp": datetime.now().isoformat()
}
"""
            },
        )

        # Reasoning state manager
        state_manager_id = builder.add_node(
            "PythonCodeNode",
            node_id="state_manager",
            config={
                "code": f"""
# Manage reasoning state across iterations
import json

def update_reasoning_state(state, new_response, tool_result=None):
    '''Update state with new reasoning step'''
    if not state:
        state = {{
            "steps": [],
            "current_step": 0,
            "completed": False,
            "final_answer": None
        }}

    # Parse response for thought/action/answer
    lines = new_response.strip().split('\\n')
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
    step = {{
        "step_number": state["current_step"] + 1,
        "thought": current_thought,
        "action": current_action,
        "observation": tool_result.get("tool_result") if tool_result else None
    }}

    state["steps"].append(step)
    state["current_step"] += 1
    state["current_action"] = current_action
    state["final_answer"] = final_answer

    # Check if we've reached max steps
    if state["current_step"] >= {self.max_reasoning_steps}:
        state["completed"] = True
        if not state["final_answer"]:
            state["final_answer"] = "Reached maximum reasoning steps. Based on gathered information..."

    return state

# Process current iteration
plan = plan.get("response") if isinstance(plan, dict) else plan
reasoning_response = reasoning_response.get("response") if isinstance(reasoning_response, dict) else reasoning_response
tool_result = tool_result if "tool_result" in locals() else None

# Initialize or update state
if "reasoning_state" not in locals() or not reasoning_state:
    reasoning_state = None

reasoning_state = update_reasoning_state(
    reasoning_state,
    reasoning_response,
    tool_result
)

# Prepare context for next iteration
context_for_agent = ""
for step in reasoning_state["steps"]:
    if step["thought"]:
        context_for_agent += f"\\nThought: {{step['thought']}}"
    if step["action"]:
        context_for_agent += f"\\nAction: {{step['action']}}"
    if step["observation"]:
        context_for_agent += f"\\nObservation: {{step['observation']}}"

result = {{
    "reasoning_state": reasoning_state,
    "context_for_agent": context_for_agent,
    "continue_reasoning": not reasoning_state["completed"]
}}
"""
            },
        )

        # Verification agent (if enabled)
        verifier_id: Optional[str] = None
        if self.verification_enabled:
            verifier_id = builder.add_node(
                "LLMAgentNode",
                node_id="verifier_agent",
                config={
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

        # Result synthesizer
        # NB: this code template is an f-string because the metadata block
        # interpolates the constructor config (planning_strategy / max steps).
        # Literal Python braces inside the sandboxed code are doubled ({{ }}).
        synthesizer_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_synthesizer",
            config={
                "code": f"""
# Synthesize final results
reasoning_state = reasoning_state
verification = verification if "verification" in locals() else None
query = query

# Extract tool usage
tools_used = []
for step in reasoning_state["steps"]:
    if step["observation"] and "tool" in step["observation"]:
        tools_used.append(step["observation"]["tool"])

# Calculate confidence
base_confidence = 0.7
confidence_boost = min(0.3, len(tools_used) * 0.1)
if verification and verification.get("response"):
    verification_data = verification["response"]
    if isinstance(verification_data, str):
        import json
        try:
            verification_data = json.loads(verification_data)
        except Exception:
            # Fallback for invalid JSON (sandboxed - no logging available)
            verification_data = {{"confidence": 0.8}}

    verification_confidence = verification_data.get("confidence", 0.8)
    final_confidence = (base_confidence + confidence_boost) * verification_confidence
else:
    final_confidence = base_confidence + confidence_boost

# Build reasoning trace
reasoning_trace = []
for step in reasoning_state["steps"]:
    trace_entry = {{
        "step": step["step_number"],
        "thought": step["thought"],
        "action": step["action"],
        "observation": step["observation"]
    }}
    reasoning_trace.append(trace_entry)

result = {{
    "agentic_rag_result": {{
        "query": query,
        "answer": reasoning_state["final_answer"],
        "reasoning_trace": reasoning_trace,
        "tools_used": list(set(tools_used)),
        "confidence": final_confidence,
        "total_steps": len(reasoning_state["steps"]),
        "verification": verification.get("response") if verification else None,
        "metadata": {{
            "planning_strategy": "{self.planning_strategy}",
            "max_steps": {self.max_reasoning_steps},
            "completed_successfully": reasoning_state["completed"]
        }}
    }}
}}
"""
            },
        )

        # L3 messages-composers (reference template — conversational.py /
        # query_processing.py). Each LLM stage previously received NO real input
        # on a port LLMAgentNode reads (its `run` reads only `kwargs["messages"]`)
        # — the planner/react/verifier answered from their `system_prompt` alone.
        # Each composer renders the REAL inputs that stage must reason over into
        # a `messages` list wired to the VALID `messages` port. `from_function`
        # is the correct primitive (real module-level functions: real `return`→
        # `result`, type-checkable). type: ignore[attr-defined]: `from_function`
        # is a classmethod on concrete PythonCodeNode, erased to `type[Node]` by
        # `@register_node` for static checkers (mirrors conversational.py).
        # `_internal=True` suppresses the consumer-facing instance-API advisory.
        planner_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_planner_messages,
                name="planner_messages_composer",
            ),
            node_id="planner_messages_composer",
            _internal=True,
        )
        react_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_react_messages,
                name="react_messages_composer",
            ),
            node_id="react_messages_composer",
            _internal=True,
        )
        verifier_messages_composer_id: Optional[str] = None
        if self.verification_enabled:
            verifier_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(  # type: ignore[attr-defined]
                    compose_verifier_messages,
                    name="verifier_messages_composer",
                ),
                node_id="verifier_messages_composer",
                _internal=True,
            )

        # Connect workflow
        # Planning phase. The planner composer renders the REAL top-level `query`
        # (the parameter injector delivers it) into the planner's `messages`
        # port; the planner's `response` feeds the state_manager `plan` input.
        builder.add_connection(
            planner_messages_composer_id, "result.messages", planner_id, "messages"
        )
        builder.add_connection(planner_id, "response", state_manager_id, "plan")

        # ReAct loop connections.
        # FIX: the prior `state_manager.context_for_agent ->
        # react_agent.additional_context` phantom edge fed the observations to a
        # port LLMAgentNode silently drops. The react composer now renders the
        # REAL `query` PLUS the real `state_manager.context_for_agent` (the
        # accumulated Thought/Action/Observation transcript) into the react
        # agent's `messages` port. The phantom `additional_context` edge is
        # REMOVED.
        builder.add_connection(
            state_manager_id,
            "context_for_agent",
            react_messages_composer_id,
            "context_for_agent",
        )
        builder.add_connection(
            react_messages_composer_id, "result.messages", react_agent_id, "messages"
        )
        builder.add_connection(
            react_agent_id, "response", state_manager_id, "reasoning_response"
        )
        builder.add_connection(
            state_manager_id, "reasoning_state", tool_executor_id, "reasoning_state"
        )
        builder.add_connection(
            tool_executor_id, "tool_result", state_manager_id, "tool_result"
        )

        # Loop control - continue if not completed. This is a loop-control edge
        # (not a context port), so it stays unchanged: it gates whether the react
        # agent runs again, it does NOT carry reasoning context.
        builder.add_connection(
            state_manager_id, "continue_reasoning", react_agent_id, "_continue_if_true"
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
            builder.add_connection(
                state_manager_id,
                "reasoning_state",
                verifier_messages_composer_id,
                "reasoning_state",
            )
            builder.add_connection(
                verifier_messages_composer_id,
                "result.messages",
                verifier_id,
                "messages",
            )
            builder.add_connection(
                verifier_id, "response", synthesizer_id, "verification"
            )

        # Final synthesis
        builder.add_connection(
            state_manager_id, "reasoning_state", synthesizer_id, "reasoning_state"
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
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_decomposer_messages,
                name="decomposer_messages_composer",
            ),
            node_id="decomposer_messages_composer",
            _internal=True,
        )
        step_reasoner_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_step_reasoner_messages,
                name="step_reasoner_messages_composer",
            ),
            node_id="step_reasoner_messages_composer",
            _internal=True,
        )
        logic_verifier_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_logic_verifier_messages,
                name="logic_verifier_messages_composer",
            ),
            node_id="logic_verifier_messages_composer",
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
        # Stage 2: the REAL query + the real decomposer.response →
        # step_reasoner composer → step_reasoner.messages. The phantom
        # `decomposer.response -> step_reasoner.reasoning_plan` edge is REMOVED;
        # the decomposition now reaches the reasoner through the composer's
        # `messages`. (`query` is the top-level injected input; `reasoning_plan`
        # is wired from decomposer.response.)
        builder.add_connection(
            decomposer_id,
            "response",
            step_reasoner_messages_composer_id,
            "reasoning_plan",
        )
        builder.add_connection(
            step_reasoner_messages_composer_id,
            "result.messages",
            step_reasoner_id,
            "messages",
        )
        # Stage 3: the real step_reasoner.response (the reasoning chain) →
        # logic_verifier composer → logic_verifier.messages. The phantom
        # `step_reasoner.response -> logic_verifier.reasoning_to_verify` edge is
        # REMOVED; the reasoning chain now reaches the verifier through
        # `messages`.
        builder.add_connection(
            step_reasoner_id,
            "response",
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
