"""
Conversational RAG Implementation

Implements RAG with conversation context and memory management:
- Multi-turn conversation support
- Context window management
- Conversation memory and summarization
- Coreference resolution
- Topic tracking and switching
- Personalization based on conversation history

Based on conversational AI and dialogue systems research.
"""

import logging
import os
import secrets
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node

# Registering imports (mirrors realtime.py #1120): wired by STRING via
# `builder.add_node("PythonCodeNode" / "LLMAgentNode", ...)`; importing runs the
# `@register_node` side effect that populates the registry. Do NOT drop to satisfy
# an unused-import linter.
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
# Messages-composer functions (L3 fix — reference template for the program).
#
# LLMAgentNode consumes context EXCLUSIVELY through its `messages` param (the
# OpenAI chat format: a list of {"role","content"} dicts) plus `system_prompt`.
# Any other wired port (`retrieval_results`, `conversation_context`,
# `conversation_history`, `context`, ...) is read via `kwargs.get` and SILENTLY
# DROPPED. The prior wiring fed these phantom ports, so the LLM never saw the
# retrieved documents or the conversation history — it answered from its
# system_prompt alone (the L3 "LLM ignores context" defect).
#
# The fix routes every LLM stage's context through a `PythonCodeNode`
# `.from_function`-wrapped composer that RENDERS the retrieved docs + history +
# query into a real `messages` list wired to the VALID `messages` port. These
# are real module-level functions (real imports, real `return` → `result`,
# statically checkable, no f-string brace-escaping) per the program's reference
# template — NOT inline `code=` codegen blocks.
#
# Each composer is defensive about the wrapped shapes its upstream producers
# publish: PythonCodeNode producers publish a single `result` port carrying
# their whole module-scope dict, so a wrapper like {"session_context": {...}}
# or {"contextual_retrieval": {...}} arrives and must be unwrapped. The
# coreference_resolver / context_summarizer LLM stages publish a `response`
# port whose value is an inner message dict keyed by "content".
# ---------------------------------------------------------------------------


def _render_history(conversation_context: Any) -> str:
    """Render the recent conversation turns into a plain-text transcript.

    `conversation_context` is the context_loader `result` port value, i.e. the
    {"session_context": {...}} wrapper. Returns "" when no prior turns exist.
    """
    if isinstance(conversation_context, dict):
        inner = conversation_context.get("session_context", conversation_context)
    else:
        inner = {}
    if not isinstance(inner, dict):
        return ""
    # context_loader already formats the sliding-window transcript; prefer it.
    text = inner.get("context_text") or ""
    if text:
        return text.strip()
    # Fall back to rendering recent_turns if context_text is absent.
    rendered = []
    for turn in inner.get("recent_turns", []) or []:
        if isinstance(turn, dict):
            rendered.append(f"User: {turn.get('query', '')}")
            rendered.append(f"Assistant: {turn.get('response', '')}")
    return "\n".join(rendered).strip()


def _render_documents(contextual_retrieval: Any) -> str:
    """Render the retrieved documents into a plain-text context block.

    `contextual_retrieval` is the context_retriever `result` port value, i.e.
    the {"contextual_retrieval": {...}} wrapper carrying `documents`.
    """
    if isinstance(contextual_retrieval, dict):
        inner = contextual_retrieval.get("contextual_retrieval", contextual_retrieval)
    else:
        inner = {}
    documents = inner.get("documents", []) if isinstance(inner, dict) else []
    blocks = []
    for i, doc in enumerate(documents):
        if not isinstance(doc, dict):
            continue
        # doc.get("content") may be present-with-None; the `or ""` covers it.
        content = (doc.get("content") or "").strip()
        if content:
            blocks.append(f"[Document {i + 1}] {content}")
    return "\n\n".join(blocks)


def _query_from_retrieval(contextual_retrieval: Any) -> str:
    """Extract the (enhanced) query the retriever computed from the wrapper.

    `context_retriever` publishes {"contextual_retrieval": {"enhanced_query":
    ...}}. The enhanced_query embeds the original user query (the retriever
    builds it as `f"{query} ..."` / `f"{topic} context: {query}"`), so it is a
    faithful in-graph source of the user's question — no separate external
    input is needed for the response composer.
    """
    if isinstance(contextual_retrieval, dict):
        inner = contextual_retrieval.get("contextual_retrieval", contextual_retrieval)
        if isinstance(inner, dict):
            return inner.get("enhanced_query", "") or ""
    return ""


def compose_response_messages(
    contextual_retrieval=None,
    conversation_context=None,
    query="",
):
    """Compose the OpenAI-format ``messages`` list for the response_generator.

    Embeds the retrieved documents + the conversation history + the user query
    so the LLM's answer is GROUNDED in the retrieved context — not produced
    from system_prompt alone. Returns ``{"messages": [...]}`` wired to the
    LLMAgentNode ``messages`` port.

    The query is taken from the retriever's ``enhanced_query`` (an in-graph
    source embedding the original question) unless an explicit ``query`` is
    wired — so no extra external input is required for this composer.
    """
    effective_query = query or _query_from_retrieval(contextual_retrieval)
    history = _render_history(conversation_context)
    documents = _render_documents(contextual_retrieval)

    parts = []
    if documents:
        parts.append("Retrieved context:\n" + documents)
    if history:
        parts.append("Conversation so far:\n" + history)
    parts.append("Current question:\n" + effective_query)
    user_content = "\n\n".join(parts)

    return {"messages": [{"role": "user", "content": user_content}]}


def compose_coreference_messages(current_query="", conversation_context=None):
    """Compose the ``messages`` list for the coreference_resolver LLM stage.

    Embeds the conversation history (the antecedent source) + the user query so
    the resolver can replace pronouns with their specific antecedents. Returns
    ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.

    The coreference stage runs BEFORE retrieval (its output feeds the
    retriever's ``resolved_query``), so the raw user query is taken from the
    ``current_query`` external input — the same input the topic_tracker reads.
    """
    history = _render_history(conversation_context)
    parts = []
    if history:
        parts.append("Conversation so far:\n" + history)
    parts.append("Query to resolve:\n" + (current_query or ""))
    return {"messages": [{"role": "user", "content": "\n\n".join(parts)}]}


def compose_summary_messages(conversation_context=None):
    """Compose the ``messages`` list for the context_summarizer LLM stage.

    Embeds the conversation history to be summarized. Returns
    ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port. When
    no history exists yet, the user message is an explicit empty-history note
    so the stage still receives a well-formed (non-empty) messages list.
    """
    history = _render_history(conversation_context)
    content = (
        "Summarize this conversation:\n" + history
        if history
        else "No conversation history yet."
    )
    return {"messages": [{"role": "user", "content": content}]}


# ---------------------------------------------------------------------------
# COMPUTE-stage functions (S6a — root-cause fix for #1117 publish-nothing /
# #1123 brace-escape / #1118 import-trap).
#
# The five COMPUTE stages of the ConversationalRAGNode workflow were inline
# `code=` PythonCodeNode codegen blocks. They are now module-level functions
# wired via `PythonCodeNode.from_function`, the same reference template as the
# composers above and as optimized.py / evaluation.py / query_processing.py.
#
# A `from_function` node publishes its `return` value on the FLAT `result`
# port — the structural successor of the prior codegen's module-scope
# `result =` assignment. Each downstream edge reads `result` and the consumer
# unwraps the nested key it needs (`session_context` / `topic_analysis` /
# `contextual_retrieval` / `session_update`), so the wiring is unchanged.
#
# `from_function` removes the three defect classes the inline codegen carried:
#   - #1117 publish-nothing: the prior inner `def ...(): result = {...}` bound
#     a FUNCTION-LOCAL `result` that was never returned, so the module-scope
#     output port saw nothing. A real `return` publishes on `result`.
#   - #1123 brace-escape: the f-string `code=` form doubled every literal
#     brace (`{{...}}`), an error-prone hand-escape. Real functions carry
#     real dict literals.
#   - #1118 import-trap: `PythonCodeNode` passes separate (globals, locals) to
#     `exec()`, so a module-scope import bound into the LOCAL namespace and was
#     invisible to a nested function's closure (`datetime.now()` raised
#     AttributeError). A real module-level function closes over real
#     module-scope imports (`datetime`) natively.
#
# Build-time config (`max_context_turns` + the result-formatter flags) is bound
# through thin closure factories below (mirrors optimized.py's
# `_decide_cache_use_bound`) so the lifted functions stay pure + testable while
# the per-instance config interpolates at workflow-construction time.
# ---------------------------------------------------------------------------


def _load_conversation_context(
    session_id, sessions_store=None, max_context_turns: int = 10
) -> dict:
    """Load conversation context for a session (lifted context_loader stage).

    Returns ``{"session_context": {...}}`` on the flat ``result`` port that
    ``context_retriever`` / ``topic_tracker`` / the composers unwrap.
    `session_id` is an external workflow input; `sessions_store` is an internal
    per-run store defaulted to an empty dict when the caller does not wire one.
    """
    if sessions_store is None:
        sessions_store = {}

    if session_id not in sessions_store:
        # Create new session.
        session = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "turns": [],
            "summary": "",
            "current_topic": None,
            "user_preferences": {},
            "metrics": {
                "turn_count": 0,
                "topics_discussed": [],
                "avg_response_length": 0,
            },
        }
        sessions_store[session_id] = session

    session = sessions_store[session_id]

    # Get recent context (sliding window).
    recent_turns = session["turns"][-max_context_turns:]

    # Format context for processing.
    context_text = ""
    for turn in recent_turns:
        context_text += f"User: {turn['query']}\n"
        context_text += f"Assistant: {turn['response']}\n\n"

    return {
        "session_context": {
            "session_id": session_id,
            "recent_turns": recent_turns,
            "context_text": context_text,
            "summary": session.get("summary", ""),
            "current_topic": session.get("current_topic"),
            "turn_count": len(session["turns"]),
            "user_preferences": session.get("user_preferences", {}),
        }
    }


def _track_conversation_topic(current_query="", session_context=None) -> dict:
    """Track and identify topic changes (lifted topic_tracker stage).

    Returns ``{"topic_analysis": {...}}`` on the flat ``result`` port that
    `context_retriever` / `session_updater` / `result_formatter` unwrap.
    `current_query` is an external workflow input; `session_context` is wired
    from `context_loader`'s `result` port (the whole ``{"session_context":
    ...}`` dict) and unwrapped to the inner dict here.
    """
    inner = {}
    if isinstance(session_context, dict):
        inner = session_context.get("session_context", session_context)
    if not isinstance(inner, dict):
        inner = {}

    current_topic = inner.get("current_topic")

    # Extract key terms from current query.
    query_terms = set((current_query or "").lower().split())

    # Define topic keywords (simplified - use NER/classification in production).
    topics = {
        "transformers": [
            "transformer",
            "attention",
            "self-attention",
            "encoder",
            "decoder",
        ],
        "bert": ["bert", "bidirectional", "masked", "mlm", "pretraining"],
        "gpt": ["gpt", "generative", "autoregressive", "language model"],
        "training": ["training", "optimization", "learning rate", "batch", "epoch"],
        "architecture": ["architecture", "layer", "network", "model", "structure"],
    }

    # Identify current query topic.
    query_topics = []
    for topic, keywords in topics.items():
        if any(keyword in query_terms for keyword in keywords):
            query_topics.append(topic)

    # Determine if topic changed.
    topic_changed = False
    transition_type = "continuation"

    if not current_topic and query_topics:
        # First topic.
        new_topic = query_topics[0]
        transition_type = "new_conversation"
    elif query_topics and query_topics[0] != current_topic:
        # Topic switch.
        new_topic = query_topics[0]
        topic_changed = True
        transition_type = "topic_switch"
    elif query_topics:
        # Same topic.
        new_topic = query_topics[0]
        transition_type = "deep_dive"
    else:
        # No clear topic.
        new_topic = current_topic or "general"
        transition_type = "clarification"

    # Check for explicit transitions.
    transition_phrases = {
        "now tell me about": "explicit_switch",
        "switching to": "explicit_switch",
        "different topic": "explicit_switch",
        "another question": "soft_switch",
        "related to this": "expansion",
        "furthermore": "continuation",
        "however": "contrast",
    }

    for phrase, trans_type in transition_phrases.items():
        if phrase in (current_query or "").lower():
            transition_type = trans_type
            break

    return {
        "topic_analysis": {
            "current_topic": new_topic,
            "previous_topic": current_topic,
            "topic_changed": topic_changed,
            "transition_type": transition_type,
            "identified_topics": query_topics,
            "confidence": 0.8 if query_topics else 0.3,
        }
    }


def _retrieve_with_context(
    query="", documents=None, session_context=None, topic_info=None, resolved_query=None
) -> dict:
    """Retrieve documents considering conversation context (lifted
    context_retriever stage).

    Returns ``{"contextual_retrieval": {...}}`` on the flat ``result`` port
    that `response_messages_composer` / `result_formatter` unwrap.

    Wiring shapes the inputs receive:
      - `query` + `documents` are external workflow inputs.
      - `session_context` is wired from `context_loader`'s `result` port (the
        whole ``{"session_context": ...}`` dict) and unwrapped to the inner
        dict here.
      - `topic_info` is wired from `topic_tracker`'s `result` port (already the
        ``{"topic_analysis": ...}`` shape) — passed through WITHOUT unwrap.
      - `resolved_query` (optional) is the coreference_resolver (LLMAgentNode)
        `response` port value — an inner message dict keyed by "content"; when
        present its content overrides the raw query string.
    """
    if documents is None:
        documents = []

    inner_context = {}
    if isinstance(session_context, dict):
        inner_context = session_context.get("session_context", session_context)
    if not isinstance(inner_context, dict):
        inner_context = {}

    # The resolved query (from the coreference stage) overrides the raw query.
    effective_query = query
    if isinstance(resolved_query, dict) and resolved_query.get("content"):
        effective_query = resolved_query["content"]
    elif isinstance(resolved_query, str) and resolved_query:
        effective_query = resolved_query

    # Combine current query with context.
    recent_context = inner_context.get("context_text", "")

    # Build enhanced query.
    enhanced_query = effective_query
    current_topic = None

    # Add topic context if available.
    if topic_info and topic_info.get("topic_analysis"):
        current_topic = topic_info["topic_analysis"].get("current_topic")
        if current_topic:
            enhanced_query = f"{current_topic} context: {effective_query}"

    # Add conversation context keywords.
    if recent_context:
        # Extract key terms from recent context.
        context_words = set(recent_context.lower().split())
        important_words = [w for w in context_words if len(w) > 4][:5]
        enhanced_query += " " + " ".join(important_words)

    # Score documents with context awareness.
    scored_docs = []
    query_words = set(enhanced_query.lower().split())

    for doc in documents:
        content = doc.get("content", "").lower()
        doc_words = set(content.split())

        # Base relevance score.
        if query_words:
            relevance = len(query_words & doc_words) / len(query_words)
        else:
            relevance = 0

        # Boost score for topic-relevant documents.
        if topic_info and current_topic in content:
            relevance *= 1.3

        # Boost for documents related to recent context.
        if recent_context and any(
            turn.get("response", "") in content
            for turn in inner_context.get("recent_turns", [])
        ):
            relevance *= 1.2

        scored_docs.append(
            {
                "document": doc,
                "score": min(1.0, relevance),
                "context_boosted": (
                    relevance > len(query_words & doc_words) / len(query_words)
                    if query_words
                    else False
                ),
            }
        )

    # Sort by score.
    scored_docs.sort(key=lambda x: x["score"], reverse=True)

    return {
        "contextual_retrieval": {
            "documents": [d["document"] for d in scored_docs[:10]],
            "scores": [d["score"] for d in scored_docs[:10]],
            "enhanced_query": enhanced_query,
            "context_influence": (
                sum(1 for d in scored_docs[:10] if d["context_boosted"])
                / min(10, len(scored_docs))
                if scored_docs
                else 0
            ),
        }
    }


def _update_session(
    session_id,
    query="",
    response=None,
    topic_info=None,
    summary=None,
    sessions_store=None,
    max_context_turns: int = 10,
) -> dict:
    """Update the session with a new turn (lifted session_updater stage).

    Returns ``{"session_update": {...}}`` on the flat ``result`` port that
    `result_formatter` unwraps.

    Wiring shapes the inputs receive:
      - `session_id` + `query` are external workflow inputs.
      - `response` is the response_generator (LLMAgentNode) `response` port
        value — an inner message dict keyed by "content".
      - `topic_info` is the topic_tracker `result` port (``{"topic_analysis":
        ...}``); absent on a False optional-branch.
      - `summary` is the context_summarizer `response` port value (inner
        message dict keyed by "content") when summarization is enabled.
      - `sessions_store` is the internal per-run store (defaulted empty).

    PythonCodeNode runs each node with an independent copy of its inputs, so the
    `sessions_store` mutation context_loader performed is NOT visible here. Seed
    the session if absent (same shape context_loader creates) so this turn is
    recorded against a real session record rather than crashing with KeyError.
    Cross-execution persistence is owned by the WorkflowNode's own
    `self.sessions` store (see create_session), not this per-run store.
    """
    if sessions_store is None:
        sessions_store = {}

    if session_id not in sessions_store:
        sessions_store[session_id] = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "turns": [],
            "summary": "",
            "current_topic": None,
            "user_preferences": {},
            "metrics": {
                "turn_count": 0,
                "topics_discussed": [],
                "avg_response_length": 0,
            },
        }

    session = sessions_store[session_id]

    # Add new turn. `response` is the LLMAgentNode `response` port value — an
    # inner message dict keyed by "content" (NOT "response").
    new_turn = {
        "turn_number": len(session["turns"]) + 1,
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "response": (
            response.get("content", "")
            if isinstance(response, dict)
            else (response or "")
        ),
        "topic": (
            topic_info.get("topic_analysis", {}).get("current_topic")
            if isinstance(topic_info, dict)
            else None
        ),
    }

    session["turns"].append(new_turn)

    # Update summary if provided. `summary` is the context_summarizer
    # (LLMAgentNode) `response` port value — an inner message dict keyed by
    # "content" (NOT "response").
    if isinstance(summary, dict) and summary.get("content"):
        session["summary"] = summary["content"]

    # Update current topic.
    if topic_info and topic_info.get("topic_analysis"):
        session["current_topic"] = topic_info["topic_analysis"]["current_topic"]

        # Track topics discussed.
        topic = topic_info["topic_analysis"]["current_topic"]
        if topic and topic not in session["metrics"]["topics_discussed"]:
            session["metrics"]["topics_discussed"].append(topic)

    # Update metrics.
    session["metrics"]["turn_count"] = len(session["turns"])
    total_response_length = sum(
        len(turn.get("response", "")) for turn in session["turns"]
    )
    session["metrics"]["avg_response_length"] = (
        total_response_length / len(session["turns"]) if session["turns"] else 0
    )

    # Trim old turns if exceeds max + buffer for summarization.
    if len(session["turns"]) > max_context_turns * 1.5:
        # Keep recent turns and rely on summary for older context.
        session["turns"] = session["turns"][-max_context_turns:]

    # Coherence proxy: topic consistency. Fewer DISTINCT topics across the turns
    # => the conversation stayed on-topic => more coherent. Derived from the
    # real session signal (NOT a hardcoded score); single-topic = 1.0.
    _distinct_topics = len(session["metrics"]["topics_discussed"])
    _coherence_turns = max(1, session["metrics"]["turn_count"])
    coherence_score = max(
        0.0, min(1.0, 1.0 - (max(0, _distinct_topics - 1) / _coherence_turns))
    )

    # Calculate conversation health metrics.
    conversation_metrics = {
        "coherence_score": coherence_score,  # derived from topic consistency
        "engagement_level": min(1.0, len(session["turns"]) / 10),  # higher w/ turns
        "topic_diversity": (
            len(session["metrics"]["topics_discussed"])
            / max(1, session["metrics"]["turn_count"])
        ),
        "avg_turn_length": session["metrics"]["avg_response_length"],
    }

    return {
        "session_update": {
            "session_id": session_id,
            "turn_added": new_turn["turn_number"],
            "total_turns": len(session["turns"]),
            "current_topic": session["current_topic"],
            "conversation_metrics": conversation_metrics,
        }
    }


def _format_conversational_result(
    response=None,
    session_update=None,
    topic_info=None,
    contextual_retrieval=None,
    max_context_turns: int = 10,
    enable_summarization: bool = True,
    coreference_resolution: bool = True,
    personalization_enabled: bool = True,
) -> dict:
    """Format the terminal conversational response (lifted result_formatter
    stage — publishes the WorkflowNode's documented
    ``conversational_response``).

    Every wired input arrives as its PRODUCER's published port value:
      - `response`             <- response_generator.response (LLMAgentNode
                                  port value = inner message dict keyed by
                                  "content")
      - `session_update`       <- session_updater.result ({"session_update"})
      - `topic_info`           <- topic_tracker.result ({"topic_analysis"})
      - `contextual_retrieval` <- context_retriever.result
                                  ({"contextual_retrieval"})
    so each is unwrapped to the nested shape this formatter consumes. Optional
    inputs may be unwired on a False optional-branch (topic_tracking off leaves
    `topic_info` unbound), so each is defaulted to a benign empty value.

    The per-instance config flags (`max_context_turns`, `enable_summarization`,
    `coreference_resolution`, `personalization_enabled`) are bound at
    workflow-construction time through the closure factory — the structural
    successor of the prior f-string `{self.*}` interpolation (#1123 fix).
    """
    if topic_info is None:
        topic_info = {}
    if session_update is None:
        session_update = {}
    if contextual_retrieval is None:
        contextual_retrieval = {}
    if response is None:
        response = {}

    # Format conversational response. `response` is the LLMAgentNode `response`
    # port value (inner message dict keyed by "content", NOT "response").
    response_text = (
        response.get("content", "") if isinstance(response, dict) else (response or "")
    )
    session_update = (
        session_update.get("session_update", {})
        if isinstance(session_update, dict)
        else {}
    )
    topic_info = (
        topic_info.get("topic_analysis", {}) if isinstance(topic_info, dict) else {}
    )
    contextual_retrieval = (
        contextual_retrieval.get("contextual_retrieval", {})
        if isinstance(contextual_retrieval, dict)
        else {}
    )

    # Build session state summary.
    session_state = {
        "session_id": session_update.get("session_id"),
        "turn_number": session_update.get("turn_added"),
        "total_turns": session_update.get("total_turns"),
        "context_window": max_context_turns,
        "summary_available": enable_summarization,
    }

    # Topic information.
    topic_summary = {
        "current_topic": topic_info.get("current_topic"),
        "topic_changed": topic_info.get("topic_changed", False),
        "transition_type": topic_info.get("transition_type", "continuation"),
        "topics_discussed": session_update.get("conversation_metrics", {}).get(
            "topic_diversity", 0
        ),
    }

    # Conversation metrics.
    metrics = session_update.get("conversation_metrics", {})
    metrics["retrieval_context_influence"] = contextual_retrieval.get(
        "context_influence", 0
    )

    return {
        "conversational_response": {
            "response": response_text,
            "session_state": session_state,
            "topic_info": topic_summary,
            "conversation_metrics": metrics,
            "metadata": {
                "coreference_resolution": coreference_resolution,
                "personalization": personalization_enabled,
                "context_enhanced_retrieval": True,
            },
        }
    }


@register_node()
class ConversationalRAGNode(WorkflowNode):
    """
    Conversational RAG with Context Management

    Implements RAG that maintains conversation context across multiple turns,
    enabling coherent multi-turn interactions with memory of previous exchanges.

    When to use:
    - Best for: Chatbots, virtual assistants, interactive help systems
    - Not ideal for: Single-turn queries, stateless interactions
    - Performance: 200-500ms per turn (with context loading)
    - Context quality: Maintains coherence across 10-20 turns

    Key features:
    - Conversation memory with sliding window
    - Automatic context summarization
    - Coreference resolution (it, they, this, etc.)
    - Topic tracking and smooth transitions
    - Personalization based on user history
    - Session management and persistence

    Example:
        conv_rag = ConversationalRAGNode(
            max_context_turns=10,
            enable_summarization=True,
            personalization_enabled=True
        )

        # Initialize conversation
        session = await conv_rag.create_session(user_id="user123")

        # First turn
        response1 = await conv_rag.execute(
            query="What is transformer architecture?",
            session_id=session.id
        )

        # Follow-up with context
        response2 = await conv_rag.execute(
            query="How does its attention mechanism work?",  # "its" refers to transformer
            session_id=session.id
        )

        # Topic switch with smooth transition
        response3 = await conv_rag.execute(
            query="Now tell me about BERT",
            session_id=session.id
        )

    Parameters:
        max_context_turns: Maximum conversation turns to maintain
        enable_summarization: Summarize old context when window exceeds
        personalization_enabled: Use user history for personalization
        coreference_resolution: Resolve pronouns and references
        topic_tracking: Track and manage topic changes

    Returns:
        response: Contextual response to current query
        session_state: Current conversation state
        topic_info: Current topic and transitions
        conversation_metrics: Engagement and coherence metrics
    """

    def __init__(
        self,
        name: str = "conversational_rag",
        max_context_turns: int = 10,
        enable_summarization: bool = True,
        personalization_enabled: bool = True,
        coreference_resolution: bool = True,
        topic_tracking: bool = True,
    ):
        self.max_context_turns = max_context_turns
        self.enable_summarization = enable_summarization
        self.personalization_enabled = personalization_enabled
        self.coreference_resolution = coreference_resolution
        self.topic_tracking = topic_tracking
        # In-memory session storage (use persistent storage in production)
        self.sessions = {}
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create conversational RAG workflow"""
        builder = WorkflowBuilder()

        # Bound only inside the optional-branches below; initialize at entry
        # so the wiring loop never sees an unbound name on a False branch.
        coreference_resolver_id: Optional[str] = None
        topic_tracker_id: Optional[str] = None
        summarizer_id: Optional[str] = None

        # Session context loader.
        #
        # S6a #1117/#1123/#1118 root-cause fix: lifted from the prior f-string
        # codegen to the module-level `_load_conversation_context` function
        # wired via `PythonCodeNode.from_function`. The build-time
        # `max_context_turns` is bound through a thin closure (keeps
        # `session_id` + `sessions_store` as the declared inputs). The node
        # publishes the SAME flat `result` port carrying
        # `{"session_context": {...}}`, so the downstream edges resolve
        # unchanged. `_internal=True` suppresses the consumer-facing
        # instance-API advisory (SDK-internal construction path, mirrors the
        # composers above + optimized.py).
        _max_context_turns = self.max_context_turns

        def _load_conversation_context_bound(session_id, sessions_store=None) -> dict:
            return _load_conversation_context(
                session_id=session_id,
                sessions_store=sessions_store,
                max_context_turns=_max_context_turns,
            )

        _load_conversation_context_bound.__name__ = "context_loader"
        _load_conversation_context_bound.__doc__ = _load_conversation_context.__doc__
        context_loader_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _load_conversation_context_bound,
                name="context_loader",
            ),
            node_id="context_loader",
            _internal=True,
        )

        # Coreference resolver
        if self.coreference_resolution:
            coreference_resolver_id = builder.add_node(
                "LLMAgentNode",
                node_id="coreference_resolver",
                config={
                    "provider": detect_provider_from_env(),
                    "system_prompt": """Resolve coreferences in the user query based on conversation context.

Replace pronouns (it, they, this, that, these, those) and other references with their specific antecedents from the conversation history.

Given:
- Current query
- Recent conversation context

Return JSON:
{
    "resolved_query": "query with coreferences resolved",
    "replacements": [
        {"original": "it", "resolved": "transformer architecture"},
        {"original": "they", "resolved": "attention heads"}
    ],
    "confidence": 0.0-1.0
}

If no coreferences found, return the original query.""",
                    "model": _DEFAULT_LLM_MODEL,
                },
            )

        # Topic tracker.
        #
        # S6a #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_track_conversation_topic` function wired via
        # `PythonCodeNode.from_function` (BARE — no build-time config to bind).
        # `current_query` is an external workflow input; `session_context` is
        # wired from context_loader's `result` port (the whole
        # `{"session_context": ...}` dict) — the function unwraps the inner dict
        # internally (the prior codegen unwrapped at the module-scope call
        # site). The node publishes the SAME flat `result` port carrying
        # `{"topic_analysis": {...}}`.
        if self.topic_tracking:
            topic_tracker_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    _track_conversation_topic,
                    name="topic_tracker",
                ),
                node_id="topic_tracker",
                _internal=True,
            )

        # Context-aware retriever.
        #
        # S6a #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_retrieve_with_context` function wired via
        # `PythonCodeNode.from_function` (BARE — no build-time config to bind).
        # The function declares ALL of `query` / `documents` / `session_context`
        # / `topic_info` / `resolved_query` as explicit parameters so the
        # runtime injector + the wired edges deliver each. The function unwraps
        # `session_context` internally (the prior codegen unwrapped at the
        # module-scope call site) and folds the prior module-scope
        # `resolved_query` override logic into the function body — passing
        # through WITHOUT unwrap for `topic_info` (already the
        # `{"topic_analysis": ...}` shape). The node publishes the SAME flat
        # `result` port carrying `{"contextual_retrieval": {...}}`.
        context_retriever_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _retrieve_with_context,
                name="context_retriever",
            ),
            node_id="context_retriever",
            _internal=True,
        )

        # Response generator with context
        response_generator_id = builder.add_node(
            "LLMAgentNode",
            node_id="response_generator",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": f"""Generate a contextual response considering the conversation history.

Guidelines:
1. Reference previous conversation naturally
2. Use appropriate pronouns when context is clear
3. Handle topic transitions smoothly
4. Maintain consistent persona and tone
5. Build on previous explanations
6. Acknowledge when changing topics

For topic switches, use transitional phrases like:
- "Moving on to [new topic]..."
- "Regarding your question about [new topic]..."
- "That's a different but interesting topic..."

For continuations, reference previous context:
- "As I mentioned earlier..."
- "Building on what we discussed..."
- "To elaborate further..."

{"Personalize based on user preferences when available." if self.personalization_enabled else ""}

Keep responses conversational and engaging.""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Context summarizer (for long conversations)
        if self.enable_summarization:
            summarizer_id = builder.add_node(
                "LLMAgentNode",
                node_id="context_summarizer",
                config={
                    "provider": detect_provider_from_env(),
                    "system_prompt": """Summarize the conversation history concisely.

Focus on:
1. Main topics discussed
2. Key information provided
3. User's apparent interests
4. Any preferences expressed
5. Important clarifications made

Keep the summary under 100 words.
This will be used to maintain context in future turns.""",
                    "model": _DEFAULT_LLM_MODEL,
                },
            )

        # Session updater.
        #
        # S6a #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_update_session` function wired via `PythonCodeNode.from_function`.
        # The build-time `max_context_turns` is bound through a thin closure
        # (keeps `session_id` / `query` / `response` / `topic_info` / `summary`
        # as the declared inputs the wired edges + injector deliver). Optional
        # inputs (`topic_info` / `summary`) default to None inside the function
        # so a False optional-branch leaves the call well-formed. The node
        # publishes the SAME flat `result` port carrying
        # `{"session_update": {...}}`.
        def _update_session_bound(
            session_id,
            query="",
            response=None,
            topic_info=None,
            summary=None,
            sessions_store=None,
        ) -> dict:
            return _update_session(
                session_id=session_id,
                query=query,
                response=response,
                topic_info=topic_info,
                summary=summary,
                sessions_store=sessions_store,
                max_context_turns=_max_context_turns,
            )

        _update_session_bound.__name__ = "session_updater"
        _update_session_bound.__doc__ = _update_session.__doc__
        session_updater_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _update_session_bound,
                name="session_updater",
            ),
            node_id="session_updater",
            _internal=True,
        )

        # Result formatter (TERMINAL node — publishes the WorkflowNode's
        # documented `conversational_response` output).
        #
        # S6a #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_format_conversational_result` function wired via
        # `PythonCodeNode.from_function`. The four build-time config flags
        # (`max_context_turns`, `enable_summarization`, `coreference_resolution`,
        # `personalization_enabled`) are bound through a thin closure — the
        # structural successor of the prior f-string `{self.*}` interpolation
        # (#1123 fix). The function declares `response` / `session_update` /
        # `topic_info` / `contextual_retrieval` as the explicit inputs the wired
        # edges deliver, defaulting each to a benign empty value so a False
        # optional-branch leaves the TERMINAL node well-formed. The node
        # publishes the SAME flat `result` port carrying
        # `{"conversational_response": {...}}`.
        #
        # Every wired input arrives as its PRODUCER's published port value:
        #   - `response`             <- response_generator.response (LLMAgentNode
        #                               port value = inner message dict keyed by
        #                               "content")
        #   - `session_update`       <- session_updater.result ({"session_update"})
        #   - `topic_info`           <- topic_tracker.result ({"topic_analysis"})
        #   - `contextual_retrieval` <- context_retriever.result
        #                               ({"contextual_retrieval"})
        # so the function unwraps each to the nested shape it consumes.
        _enable_summarization = self.enable_summarization
        _coreference_resolution = self.coreference_resolution
        _personalization_enabled = self.personalization_enabled

        def _format_conversational_result_bound(
            response=None,
            session_update=None,
            topic_info=None,
            contextual_retrieval=None,
        ) -> dict:
            return _format_conversational_result(
                response=response,
                session_update=session_update,
                topic_info=topic_info,
                contextual_retrieval=contextual_retrieval,
                max_context_turns=_max_context_turns,
                enable_summarization=_enable_summarization,
                coreference_resolution=_coreference_resolution,
                personalization_enabled=_personalization_enabled,
            )

        _format_conversational_result_bound.__name__ = "result_formatter"
        _format_conversational_result_bound.__doc__ = (
            _format_conversational_result.__doc__
        )
        result_formatter_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _format_conversational_result_bound,
                name="result_formatter",
            ),
            node_id="result_formatter",
            _internal=True,
        )

        # Messages-composer nodes (L3 fix). Each LLM stage's context is routed
        # through a `PythonCodeNode.from_function` composer that RENDERS the
        # retrieved docs + history + query into a real OpenAI-format `messages`
        # list wired to the LLMAgentNode `messages` port — the ONLY port through
        # which LLMAgentNode consumes context. The prior wiring fed phantom
        # ports (`retrieval_results` / `conversation_context` / `context` /
        # `conversation_history`) that the node silently drops.
        #
        # `.from_function` is the correct primitive here (real module-level
        # functions get real imports, real `return`→`result`, type-checkable, no
        # brace-escaping). Instances are added via `add_node_instance(...,
        # _internal=True)` — this IS an SDK-internal node-construction path
        # (mirrors Nexus's `@app.handler()`), so the consumer-facing instance-API
        # advisory `UserWarning` is correctly suppressed (zero-tolerance Rule 1:
        # no spurious runtime warnings).
        response_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_response_messages,
                name="response_messages_composer",
            ),
            node_id="response_messages_composer",
            _internal=True,
        )

        coreference_messages_composer_id: Optional[str] = None
        if self.coreference_resolution:
            coreference_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    compose_coreference_messages,
                    name="coreference_messages_composer",
                ),
                node_id="coreference_messages_composer",
                _internal=True,
            )

        summary_messages_composer_id: Optional[str] = None
        if self.enable_summarization:
            summary_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    compose_summary_messages,
                    name="summary_messages_composer",
                ),
                node_id="summary_messages_composer",
                _internal=True,
            )

        # Connect workflow.
        #
        # F9 #1117/#1123 wiring fix: a PythonCodeNode publishes a SINGLE `result`
        # output port carrying its whole module-scope `result` dict — the nested
        # keys ("session_context", "topic_analysis", "contextual_retrieval",
        # "session_update") are NOT individual ports. The prior edges read those
        # non-existent nested ports, so every downstream input silently bound to
        # nothing. Every PythonCodeNode source edge now reads `result`; the
        # consumer's module-scope wrapper unwraps the nested key it needs.
        # LLMAgentNode publishes each top-level result key as a real port, so
        # `response` (NOT the non-existent `resolved_query`) is the correct read
        # for the coreference_resolver and summarizer.
        builder.add_connection(
            context_loader_id,
            "result",
            context_retriever_id,
            "session_context",
        )

        if self.coreference_resolution:
            assert (
                coreference_resolver_id is not None
            )  # narrowed: bound in optional block above
            assert coreference_messages_composer_id is not None
            # L3 fix: feed conversation history into the composer (NOT the
            # phantom `context` port on the LLM stage). The composer renders the
            # history + query into a `messages` list on the VALID port.
            builder.add_connection(
                context_loader_id,
                "result",
                coreference_messages_composer_id,
                "conversation_context",
            )
            # MED-1 fix: the coreference stage runs BEFORE retrieval, so there
            # is NO in-graph query source (unlike response_generator, which
            # recovers the query from contextual_retrieval.enhanced_query). The
            # composer declares `current_query` as a function parameter, so the
            # runtime's parameter injector delivers the caller-supplied
            # top-level `current_query` workflow input to it (the same external
            # input the topic_tracker reads) — embedding the user's query in the
            # `messages` list the pronoun-resolver consumes. Without the query,
            # the composer would publish an EMPTY "Query to resolve:" message
            # and the resolver — whose entire job is resolving pronouns in the
            # user's query — would never see the query.
            builder.add_connection(
                coreference_messages_composer_id,
                "result.messages",
                coreference_resolver_id,
                "messages",
            )
            # LLMAgentNode publishes `response` (not `resolved_query`); the
            # retriever's wrapper extracts the resolved-query string from it.
            builder.add_connection(
                coreference_resolver_id,
                "response",
                context_retriever_id,
                "resolved_query",
            )

        if self.topic_tracking:
            assert (
                topic_tracker_id is not None
            )  # narrowed: bound in optional block above
            builder.add_connection(
                context_loader_id,
                "result",
                topic_tracker_id,
                "session_context",
            )
            builder.add_connection(
                topic_tracker_id, "result", context_retriever_id, "topic_info"
            )

        # L3 fix: route the response_generator's context through its composer.
        # The retrieved docs (context_retriever.result → contextual_retrieval)
        # and the conversation history (context_loader.result →
        # conversation_context) feed the COMPOSER, which renders them into a
        # `messages` list on the VALID `messages` port — NOT the phantom
        # `retrieval_results` / `conversation_context` ports the LLM drops.
        builder.add_connection(
            context_retriever_id,
            "result",
            response_messages_composer_id,
            "contextual_retrieval",
        )
        builder.add_connection(
            context_loader_id,
            "result",
            response_messages_composer_id,
            "conversation_context",
        )
        builder.add_connection(
            response_messages_composer_id,
            "result.messages",
            response_generator_id,
            "messages",
        )

        if self.enable_summarization:
            assert summarizer_id is not None  # narrowed: bound in optional block above
            assert summary_messages_composer_id is not None
            # L3 fix: feed history into the summary composer (NOT the phantom
            # `conversation_history` port). The composer renders the history
            # into a `messages` list on the VALID `messages` port.
            builder.add_connection(
                context_loader_id,
                "result",
                summary_messages_composer_id,
                "conversation_context",
            )
            builder.add_connection(
                summary_messages_composer_id,
                "result.messages",
                summarizer_id,
                "messages",
            )
            builder.add_connection(
                summarizer_id, "response", session_updater_id, "summary"
            )

        builder.add_connection(
            response_generator_id, "response", session_updater_id, "response"
        )
        if self.topic_tracking:
            assert (
                topic_tracker_id is not None
            )  # narrowed: bound in optional block above
            builder.add_connection(
                topic_tracker_id, "result", session_updater_id, "topic_info"
            )

        builder.add_connection(
            session_updater_id, "result", result_formatter_id, "session_update"
        )
        builder.add_connection(
            response_generator_id, "response", result_formatter_id, "response"
        )
        if self.topic_tracking:
            assert (
                topic_tracker_id is not None
            )  # narrowed: bound in optional block above
            builder.add_connection(
                topic_tracker_id, "result", result_formatter_id, "topic_info"
            )
        builder.add_connection(
            context_retriever_id,
            "result",
            result_formatter_id,
            "contextual_retrieval",
        )

        return builder.build(name="conversational_rag_workflow")

    def create_session(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new conversation session"""
        # F9 #1116: session_id MUST come from a cryptographically-strong
        # source — the prior `sha256(f"{user_or_anon}_{datetime}")[:16]`
        # form admitted ~10⁶ brute-force ops within a 1-second window on
        # the anonymous flow because the input space was enumerable.
        # `secrets.token_hex(16)` emits 32 hex chars of CSPRNG output.
        session_id = secrets.token_hex(16)

        session = {
            "id": session_id,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "turns": [],
            "summary": "",
            "current_topic": None,
            "user_preferences": {},
            "metrics": {
                "turn_count": 0,
                "topics_discussed": [],
                "avg_response_length": 0,
            },
        }

        self.sessions[session_id] = session

        return {
            "session_id": session_id,
            "created": True,
            "expires_in": 3600,  # 1 hour default expiry
        }


@register_node()
class ConversationMemoryNode(Node):
    """
    Long-term Conversation Memory Management

    Manages persistent conversation memory across sessions.

    When to use:
    - Best for: Virtual assistants, customer support, personalized systems
    - Memory types: Episodic, semantic, user preferences
    - Retention: Configurable from hours to permanent

    Example:
        memory = ConversationMemoryNode(
            memory_types=["episodic", "semantic", "preferences"],
            retention_policy="adaptive"
        )

        # Store conversation insights
        await memory.store(
            user_id="user123",
            conversation_id="conv456",
            insights={
                "topics": ["machine learning", "python"],
                "preferences": {"explanation_style": "detailed"},
                "key_facts": ["user is a beginner", "interested in NLP"]
            }
        )

        # Retrieve relevant memories
        memories = await memory.retrieve(
            user_id="user123",
            context="python programming question"
        )

    Parameters:
        memory_types: Types of memory to maintain
        retention_policy: How long to retain memories
        max_memories_per_user: Memory limit per user

    Returns:
        relevant_memories: Memories relevant to current context
        memory_summary: Aggregated user knowledge
        personalization_hints: Suggestions for personalization
    """

    def __init__(
        self,
        name: str = "conversation_memory",
        memory_types: Optional[List[str]] = None,
        retention_policy: str = "adaptive",
        max_memories_per_user: int = 1000,
    ):
        resolved_memory_types = memory_types or [
            "episodic",
            "semantic",
            "preferences",
        ]
        super().__init__(
            name=name,
            memory_types=resolved_memory_types,
            retention_policy=retention_policy,
            max_memories_per_user=max_memories_per_user,
        )
        self.memory_types = resolved_memory_types
        self.retention_policy = retention_policy
        self.max_memories_per_user = max_memories_per_user
        # In-memory storage (use persistent DB in production). The per-user
        # value is a dict with mixed-typed slots (`episodic` → deque,
        # `semantic` / `preferences` → dict); typed Any because each key
        # carries a distinct narrowed shape used at access sites.
        self.memory_store: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "episodic": deque(maxlen=max_memories_per_user),
                "semantic": {},
                "preferences": {},
            }
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="conversation_memory",
                description="Node instance name",
            ),
            "memory_types": NodeParameter(
                name="memory_types",
                type=list,
                required=False,
                default=None,
                description="Memory categories (episodic, semantic, preferences)",
            ),
            "retention_policy": NodeParameter(
                name="retention_policy",
                type=str,
                required=False,
                default="adaptive",
                description="Memory retention strategy",
            ),
            "max_memories_per_user": NodeParameter(
                name="max_memories_per_user",
                type=int,
                required=False,
                default=1000,
                description="Per-user episodic memory cap",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation: store, retrieve, update, forget",
            ),
            "user_id": NodeParameter(
                name="user_id", type=str, required=True, description="User identifier"
            ),
            "data": NodeParameter(
                name="data",
                type=dict,
                required=False,
                description="Data to store or update",
            ),
            "context": NodeParameter(
                name="context",
                type=str,
                required=False,
                description="Context for retrieval",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute memory operation"""
        operation = kwargs.get("operation", "retrieve")
        user_id = kwargs.get("user_id", "")

        if operation == "store":
            return self._store_memory(user_id, kwargs.get("data", {}))
        elif operation == "retrieve":
            return self._retrieve_memories(user_id, kwargs.get("context", ""))
        elif operation == "update":
            return self._update_memory(user_id, kwargs.get("data", {}))
        elif operation == "forget":
            return self._forget_memories(user_id, kwargs.get("data", {}))
        else:
            return {"error": f"Unknown operation: {operation}"}

    def _store_memory(self, user_id: str, data: Dict) -> Dict[str, Any]:
        """Store new memories"""
        user_memory = self.memory_store[user_id]
        stored = defaultdict(int)

        # Store episodic memory (specific interactions)
        if "episodic" in self.memory_types and "conversation" in data:
            episode = {
                "timestamp": datetime.now().isoformat(),
                "conversation_id": data.get("conversation_id"),
                "summary": data["conversation"].get("summary", ""),
                "topics": data["conversation"].get("topics", []),
                "sentiment": data["conversation"].get("sentiment", "neutral"),
                "importance": data["conversation"].get("importance", 0.5),
            }
            user_memory["episodic"].append(episode)
            stored["episodic"] += 1

        # Store semantic memory (facts and knowledge)
        if "semantic" in self.memory_types and "facts" in data:
            for fact in data["facts"]:
                fact_key = fact.get("key", "")
                if fact_key:
                    user_memory["semantic"][fact_key] = {
                        "value": fact.get("value"),
                        "confidence": fact.get("confidence", 0.8),
                        "source": fact.get("source", "conversation"),
                        "timestamp": datetime.now().isoformat(),
                    }
                    stored["semantic"] += 1

        # Store preferences
        if "preferences" in self.memory_types and "preferences" in data:
            user_memory["preferences"].update(data["preferences"])
            stored["preferences"] += len(data["preferences"])

        # Apply retention policy
        self._apply_retention_policy(user_id)

        return {
            "stored": dict(stored),
            "total_memories": {
                "episodic": len(user_memory["episodic"]),
                "semantic": len(user_memory["semantic"]),
                "preferences": len(user_memory["preferences"]),
            },
            "storage_status": "success",
        }

    def _retrieve_memories(self, user_id: str, context: str) -> Dict[str, Any]:
        """Retrieve relevant memories"""
        if user_id not in self.memory_store:
            return {
                "relevant_memories": [],
                "memory_summary": "No memories found",
                "personalization_hints": {},
            }

        user_memory = self.memory_store[user_id]
        relevant_memories = []

        # Search episodic memories
        context_words = set(context.lower().split())
        for episode in user_memory["episodic"]:
            # Check topic overlap
            episode_topics = set(topic.lower() for topic in episode.get("topics", []))
            if context_words & episode_topics:
                relevant_memories.append(
                    {
                        "type": "episodic",
                        "content": episode,
                        "relevance": (
                            len(context_words & episode_topics) / len(context_words)
                            if context_words
                            else 0
                        ),
                    }
                )

        # Search semantic memories
        for key, fact in user_memory["semantic"].items():
            if any(word in key.lower() for word in context_words):
                relevant_memories.append(
                    {
                        "type": "semantic",
                        "content": {"key": key, **fact},
                        "relevance": fact.get("confidence", 0.5),
                    }
                )

        # Sort by relevance
        relevant_memories.sort(key=lambda x: x["relevance"], reverse=True)

        # Generate memory summary
        memory_summary = self._generate_memory_summary(user_memory)

        # Extract personalization hints
        personalization_hints = {
            "preferences": dict(user_memory["preferences"]),
            "frequent_topics": self._extract_frequent_topics(user_memory["episodic"]),
            "interaction_style": self._infer_interaction_style(user_memory["episodic"]),
        }

        return {
            "relevant_memories": relevant_memories[:10],
            "memory_summary": memory_summary,
            "personalization_hints": personalization_hints,
        }

    def _update_memory(self, user_id: str, data: Dict) -> Dict[str, Any]:
        """Update existing memories"""
        if user_id not in self.memory_store:
            return {"error": "No memories found for user"}

        user_memory = self.memory_store[user_id]
        updated = defaultdict(int)

        # Update semantic facts
        if "facts_update" in data:
            for fact_update in data["facts_update"]:
                key = fact_update.get("key")
                if key in user_memory["semantic"]:
                    user_memory["semantic"][key].update(fact_update.get("updates", {}))
                    user_memory["semantic"][key][
                        "timestamp"
                    ] = datetime.now().isoformat()
                    updated["semantic"] += 1

        # Update preferences
        if "preferences_update" in data:
            user_memory["preferences"].update(data["preferences_update"])
            updated["preferences"] += len(data["preferences_update"])

        return {"updated": dict(updated), "update_status": "success"}

    def _forget_memories(self, user_id: str, data: Dict) -> Dict[str, Any]:
        """Forget specific memories (GDPR compliance)"""
        if user_id not in self.memory_store:
            return {"error": "No memories found for user"}

        forgotten = defaultdict(int)

        if data.get("forget_all"):
            # Complete memory wipe
            del self.memory_store[user_id]
            return {"forgotten": "all", "status": "complete"}

        user_memory = self.memory_store[user_id]

        # Forget specific types
        if "forget_types" in data:
            for memory_type in data["forget_types"]:
                if memory_type == "episodic":
                    forgotten["episodic"] = len(user_memory["episodic"])
                    user_memory["episodic"].clear()
                elif memory_type == "semantic":
                    forgotten["semantic"] = len(user_memory["semantic"])
                    user_memory["semantic"].clear()
                elif memory_type == "preferences":
                    forgotten["preferences"] = len(user_memory["preferences"])
                    user_memory["preferences"].clear()

        # Forget specific items
        if "forget_items" in data:
            for item in data["forget_items"]:
                if (
                    item["type"] == "semantic"
                    and item["key"] in user_memory["semantic"]
                ):
                    del user_memory["semantic"][item["key"]]
                    forgotten["semantic"] += 1

        return {"forgotten": dict(forgotten), "forget_status": "success"}

    def _apply_retention_policy(self, user_id: str):
        """Apply retention policy to memories"""
        if self.retention_policy == "adaptive":
            # Keep important and recent memories
            user_memory = self.memory_store[user_id]

            # Remove old low-importance episodic memories
            if len(user_memory["episodic"]) > self.max_memories_per_user * 0.8:
                # Keep high importance memories
                important_episodes = [
                    ep
                    for ep in user_memory["episodic"]
                    if ep.get("importance", 0.5) > 0.7
                ]
                recent_episodes = list(user_memory["episodic"])[-100:]

                # Combine and deduplicate
                kept_episodes = []
                seen = set()
                for ep in important_episodes + recent_episodes:
                    ep_key = f"{ep.get('conversation_id')}_{ep.get('timestamp')}"
                    if ep_key not in seen:
                        kept_episodes.append(ep)
                        seen.add(ep_key)

                user_memory["episodic"] = deque(
                    kept_episodes, maxlen=self.max_memories_per_user
                )

    def _generate_memory_summary(self, user_memory: Dict) -> str:
        """Generate a summary of user's memories"""
        num_episodes = len(user_memory["episodic"])
        num_facts = len(user_memory["semantic"])
        num_preferences = len(user_memory["preferences"])

        topics = []
        for episode in user_memory["episodic"]:
            topics.extend(episode.get("topics", []))

        unique_topics = list(set(topics))[:5]

        summary = f"User has {num_episodes} conversation memories covering topics like {', '.join(unique_topics)}. "
        summary += (
            f"Knows {num_facts} facts about the user and {num_preferences} preferences."
        )

        return summary

    def _extract_frequent_topics(self, episodes: Deque) -> List[str]:
        """Extract frequently discussed topics"""
        topic_counts = defaultdict(int)

        for episode in episodes:
            for topic in episode.get("topics", []):
                topic_counts[topic] += 1

        # Sort by frequency
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        return [topic for topic, _ in sorted_topics[:10]]

    def _infer_interaction_style(self, episodes: Deque) -> Dict[str, Any]:
        """Infer user's preferred interaction style"""
        if not episodes:
            return {"style": "unknown", "confidence": 0}

        # Analyze recent interactions
        recent_episodes = list(episodes)[-20:]

        # Simple heuristics (would use ML in production)
        avg_importance = sum(ep.get("importance", 0.5) for ep in recent_episodes) / len(
            recent_episodes
        )

        if avg_importance > 0.7:
            style = "detailed"
        elif avg_importance < 0.3:
            style = "concise"
        else:
            style = "balanced"

        return {"style": style, "confidence": 0.8, "avg_importance": avg_importance}


# Export all conversational nodes
__all__ = ["ConversationalRAGNode", "ConversationMemoryNode"]
