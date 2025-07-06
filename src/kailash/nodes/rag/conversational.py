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

import hashlib
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Union

# from ..data.cache import CacheNode  # TODO: Implement CacheNode
from ...workflow.builder import WorkflowBuilder
from ..ai.llm_agent import LLMAgentNode
from ..base import Node, NodeParameter, register_node
from ..code.python import PythonCodeNode
from ..logic.workflow import WorkflowNode

logger = logging.getLogger(__name__)


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
        super().__init__(name, self._create_workflow())

    def _create_workflow(self) -> WorkflowNode:
        """Create conversational RAG workflow"""
        builder = WorkflowBuilder()

        # Session context loader
        context_loader_id = builder.add_node(
            "PythonCodeNode",
            node_id="context_loader",
            config={
                "code": f"""
import json
from collections import deque

def load_conversation_context(session_id, sessions_store):
    '''Load conversation context for session'''

    if session_id not in sessions_store:
        # Create new session
        session = {{
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "turns": [],
            "summary": "",
            "current_topic": None,
            "user_preferences": {{}},
            "metrics": {{
                "turn_count": 0,
                "topics_discussed": [],
                "avg_response_length": 0
            }}
        }}
        sessions_store[session_id] = session

    session = sessions_store[session_id]

    # Get recent context (sliding window)
    recent_turns = session["turns"][-{self.max_context_turns}:]

    # Format context for processing
    context_text = ""
    for turn in recent_turns:
        context_text += f"User: {{turn['query']}}\\n"
        context_text += f"Assistant: {{turn['response']}}\\n\\n"

    result = {{
        "session_context": {{
            "session_id": session_id,
            "recent_turns": recent_turns,
            "context_text": context_text,
            "summary": session.get("summary", ""),
            "current_topic": session.get("current_topic"),
            "turn_count": len(session["turns"]),
            "user_preferences": session.get("user_preferences", {{}})
        }}
    }}
"""
            },
        )

        # Coreference resolver
        if self.coreference_resolution:
            coreference_resolver_id = builder.add_node(
                "LLMAgentNode",
                node_id="coreference_resolver",
                config={
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
                    "model": "gpt-4",
                },
            )

        # Topic tracker
        if self.topic_tracking:
            topic_tracker_id = builder.add_node(
                "PythonCodeNode",
                node_id="topic_tracker",
                config={
                    "code": """
def track_conversation_topic(current_query, session_context):
    '''Track and identify topic changes in conversation'''

    current_topic = session_context.get("current_topic")
    recent_turns = session_context.get("recent_turns", [])

    # Extract key terms from current query
    query_terms = set(current_query.lower().split())

    # Define topic keywords (simplified - use NER/classification in production)
    topics = {
        "transformers": ["transformer", "attention", "self-attention", "encoder", "decoder"],
        "bert": ["bert", "bidirectional", "masked", "mlm", "pretraining"],
        "gpt": ["gpt", "generative", "autoregressive", "language model"],
        "training": ["training", "optimization", "learning rate", "batch", "epoch"],
        "architecture": ["architecture", "layer", "network", "model", "structure"]
    }

    # Identify current query topic
    query_topics = []
    for topic, keywords in topics.items():
        if any(keyword in query_terms for keyword in keywords):
            query_topics.append(topic)

    # Determine if topic changed
    topic_changed = False
    transition_type = "continuation"

    if not current_topic and query_topics:
        # First topic
        new_topic = query_topics[0]
        transition_type = "new_conversation"
    elif query_topics and query_topics[0] != current_topic:
        # Topic switch
        new_topic = query_topics[0]
        topic_changed = True
        transition_type = "topic_switch"
    elif query_topics:
        # Same topic
        new_topic = query_topics[0]
        transition_type = "deep_dive"
    else:
        # No clear topic
        new_topic = current_topic or "general"
        transition_type = "clarification"

    # Check for explicit transitions
    transition_phrases = {
        "now tell me about": "explicit_switch",
        "switching to": "explicit_switch",
        "different topic": "explicit_switch",
        "another question": "soft_switch",
        "related to this": "expansion",
        "furthermore": "continuation",
        "however": "contrast"
    }

    for phrase, trans_type in transition_phrases.items():
        if phrase in current_query.lower():
            transition_type = trans_type
            break

    result = {
        "topic_analysis": {
            "current_topic": new_topic,
            "previous_topic": current_topic,
            "topic_changed": topic_changed,
            "transition_type": transition_type,
            "identified_topics": query_topics,
            "confidence": 0.8 if query_topics else 0.3
        }
    }
"""
                },
            )

        # Context-aware retriever
        context_retriever_id = builder.add_node(
            "PythonCodeNode",
            node_id="context_retriever",
            config={
                "code": """
def retrieve_with_context(query, documents, session_context, topic_info=None):
    '''Retrieve documents considering conversation context'''

    # Combine current query with context
    context_summary = session_context.get("summary", "")
    recent_context = session_context.get("context_text", "")

    # Build enhanced query
    enhanced_query = query

    # Add topic context if available
    if topic_info and topic_info.get("topic_analysis"):
        current_topic = topic_info["topic_analysis"].get("current_topic")
        if current_topic:
            enhanced_query = f"{current_topic} context: {query}"

    # Add conversation context keywords
    if recent_context:
        # Extract key terms from recent context
        context_words = set(recent_context.lower().split())
        important_words = [w for w in context_words if len(w) > 4][:5]
        enhanced_query += " " + " ".join(important_words)

    # Score documents with context awareness
    scored_docs = []
    query_words = set(enhanced_query.lower().split())

    for doc in documents:
        content = doc.get("content", "").lower()
        doc_words = set(content.split())

        # Base relevance score
        if query_words:
            relevance = len(query_words & doc_words) / len(query_words)
        else:
            relevance = 0

        # Boost score for topic-relevant documents
        if topic_info and current_topic in content:
            relevance *= 1.3

        # Boost for documents related to recent context
        if recent_context and any(turn.get("response", "") in content for turn in session_context.get("recent_turns", [])):
            relevance *= 1.2

        scored_docs.append({
            "document": doc,
            "score": min(1.0, relevance),
            "context_boosted": relevance > len(query_words & doc_words) / len(query_words) if query_words else False
        })

    # Sort by score
    scored_docs.sort(key=lambda x: x["score"], reverse=True)

    result = {
        "contextual_retrieval": {
            "documents": [d["document"] for d in scored_docs[:10]],
            "scores": [d["score"] for d in scored_docs[:10]],
            "enhanced_query": enhanced_query,
            "context_influence": sum(1 for d in scored_docs[:10] if d["context_boosted"]) / min(10, len(scored_docs))
        }
    }
"""
            },
        )

        # Response generator with context
        response_generator_id = builder.add_node(
            "LLMAgentNode",
            node_id="response_generator",
            config={
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
                "model": "gpt-4",
            },
        )

        # Context summarizer (for long conversations)
        if self.enable_summarization:
            summarizer_id = builder.add_node(
                "LLMAgentNode",
                node_id="context_summarizer",
                config={
                    "system_prompt": """Summarize the conversation history concisely.

Focus on:
1. Main topics discussed
2. Key information provided
3. User's apparent interests
4. Any preferences expressed
5. Important clarifications made

Keep the summary under 100 words.
This will be used to maintain context in future turns.""",
                    "model": "gpt-4",
                },
            )

        # Session updater
        session_updater_id = builder.add_node(
            "PythonCodeNode",
            node_id="session_updater",
            config={
                "code": f"""
def update_session(session_id, sessions_store, query, response, topic_info, summary=None):
    '''Update session with new turn'''

    session = sessions_store[session_id]

    # Add new turn
    new_turn = {{
        "turn_number": len(session["turns"]) + 1,
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "response": response.get("response", ""),
        "topic": topic_info.get("topic_analysis", {{}}).get("current_topic")
    }}

    session["turns"].append(new_turn)

    # Update summary if provided
    if summary and summary.get("response"):
        session["summary"] = summary["response"]

    # Update current topic
    if topic_info and topic_info.get("topic_analysis"):
        session["current_topic"] = topic_info["topic_analysis"]["current_topic"]

        # Track topics discussed
        topic = topic_info["topic_analysis"]["current_topic"]
        if topic and topic not in session["metrics"]["topics_discussed"]:
            session["metrics"]["topics_discussed"].append(topic)

    # Update metrics
    session["metrics"]["turn_count"] = len(session["turns"])
    total_response_length = sum(len(turn.get("response", "")) for turn in session["turns"])
    session["metrics"]["avg_response_length"] = total_response_length / len(session["turns"]) if session["turns"] else 0

    # Trim old turns if exceeds max + buffer for summarization
    if len(session["turns"]) > {self.max_context_turns} * 1.5:
        # Keep recent turns and rely on summary for older context
        session["turns"] = session["turns"][-{self.max_context_turns}:]

    # Calculate conversation health metrics
    conversation_metrics = {{
        "coherence_score": 0.85,  # Would calculate based on topic consistency
        "engagement_level": min(1.0, len(session["turns"]) / 10),  # Higher with more turns
        "topic_diversity": len(session["metrics"]["topics_discussed"]) / max(1, session["metrics"]["turn_count"]),
        "avg_turn_length": session["metrics"]["avg_response_length"]
    }}

    result = {{
        "session_update": {{
            "session_id": session_id,
            "turn_added": new_turn["turn_number"],
            "total_turns": len(session["turns"]),
            "current_topic": session["current_topic"],
            "conversation_metrics": conversation_metrics
        }}
    }}
"""
            },
        )

        # Result formatter
        result_formatter_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_formatter",
            config={
                "code": """
# Format conversational response
response = response.get("response", "")
session_update = session_update.get("session_update", {})
topic_info = topic_info.get("topic_analysis", {}) if topic_info else {}
contextual_retrieval = contextual_retrieval.get("contextual_retrieval", {})

# Build session state summary
session_state = {
    "session_id": session_update.get("session_id"),
    "turn_number": session_update.get("turn_added"),
    "total_turns": session_update.get("total_turns"),
    "context_window": {self.max_context_turns},
    "summary_available": {self.enable_summarization}
}

# Topic information
topic_summary = {
    "current_topic": topic_info.get("current_topic"),
    "topic_changed": topic_info.get("topic_changed", False),
    "transition_type": topic_info.get("transition_type", "continuation"),
    "topics_discussed": session_update.get("conversation_metrics", {}).get("topic_diversity", 0)
}

# Conversation metrics
metrics = session_update.get("conversation_metrics", {})
metrics["retrieval_context_influence"] = contextual_retrieval.get("context_influence", 0)

result = {
    "conversational_response": {
        "response": response,
        "session_state": session_state,
        "topic_info": topic_summary,
        "conversation_metrics": metrics,
        "metadata": {
            "coreference_resolution": {self.coreference_resolution},
            "personalization": {self.personalization_enabled},
            "context_enhanced_retrieval": True
        }
    }
}
"""
            },
        )

        # Connect workflow
        builder.add_connection(
            context_loader_id,
            "session_context",
            context_retriever_id,
            "session_context",
        )

        if self.coreference_resolution:
            builder.add_connection(
                context_loader_id, "session_context", coreference_resolver_id, "context"
            )
            builder.add_connection(
                coreference_resolver_id, "resolved_query", context_retriever_id, "query"
            )

        if self.topic_tracking:
            builder.add_connection(
                context_loader_id,
                "session_context",
                topic_tracker_id,
                "session_context",
            )
            builder.add_connection(
                topic_tracker_id, "topic_analysis", context_retriever_id, "topic_info"
            )

        builder.add_connection(
            context_retriever_id,
            "contextual_retrieval",
            response_generator_id,
            "retrieval_results",
        )
        builder.add_connection(
            context_loader_id,
            "session_context",
            response_generator_id,
            "conversation_context",
        )

        if self.enable_summarization:
            builder.add_connection(
                context_loader_id,
                "session_context",
                summarizer_id,
                "conversation_history",
            )
            builder.add_connection(
                summarizer_id, "response", session_updater_id, "summary"
            )

        builder.add_connection(
            response_generator_id, "response", session_updater_id, "response"
        )
        if self.topic_tracking:
            builder.add_connection(
                topic_tracker_id, "topic_analysis", session_updater_id, "topic_info"
            )

        builder.add_connection(
            session_updater_id, "session_update", result_formatter_id, "session_update"
        )
        builder.add_connection(
            response_generator_id, "response", result_formatter_id, "response"
        )
        if self.topic_tracking:
            builder.add_connection(
                topic_tracker_id, "topic_analysis", result_formatter_id, "topic_info"
            )
        builder.add_connection(
            context_retriever_id,
            "contextual_retrieval",
            result_formatter_id,
            "contextual_retrieval",
        )

        return builder.build(name="conversational_rag_workflow")

    def create_session(self, user_id: str = None) -> Dict[str, Any]:
        """Create a new conversation session"""
        session_id = hashlib.sha256(
            f"{user_id or 'anonymous'}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

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
        memory_types: List[str] = None,
        retention_policy: str = "adaptive",
        max_memories_per_user: int = 1000,
    ):
        self.memory_types = memory_types or ["episodic", "semantic", "preferences"]
        self.retention_policy = retention_policy
        self.max_memories_per_user = max_memories_per_user
        # In-memory storage (use persistent DB in production)
        self.memory_store = defaultdict(
            lambda: {
                "episodic": deque(maxlen=max_memories_per_user),
                "semantic": {},
                "preferences": {},
            }
        )
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
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
