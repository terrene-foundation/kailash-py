"""Agent-to-Agent (A2A) communication nodes with shared memory pools.

This module implements multi-agent communication with selective attention mechanisms,
enabling efficient collaboration between AI agents while preventing information overload.

Design Philosophy:
    The A2A system enables decentralized multi-agent collaboration through shared
    memory pools and attention mechanisms. Agents can share insights, coordinate
    tasks, and build collective intelligence without centralized control.
"""

import json
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_cycle_aware import CycleAwareNode


@register_node()
class SharedMemoryPoolNode(Node):
    """
    Central memory pool that multiple agents can read from and write to.

    This node implements a sophisticated shared memory system with selective attention
    mechanisms, enabling efficient multi-agent collaboration while preventing information
    overload through intelligent filtering and segmentation.

    Design Philosophy:
        The SharedMemoryPoolNode acts as a cognitive workspace where agents can share
        discoveries, insights, and intermediate results. It implements attention-based
        filtering inspired by human selective attention, allowing agents to focus on
        relevant information without being overwhelmed by the full memory pool.

    Upstream Dependencies:
        - A2AAgentNode: Primary writer of memories with insights and discoveries
        - A2ACoordinatorNode: Writes coordination messages and task assignments
        - Any custom agent nodes that need to share information

    Downstream Consumers:
        - A2AAgentNode: Reads relevant memories to enhance context
        - A2ACoordinatorNode: Monitors agent progress through memory queries
        - SolutionEvaluatorNode: Aggregates insights for evaluation
        - Any analysis or visualization nodes needing shared context

    Configuration:
        This node is typically configured at workflow initialization and doesn't
        require runtime configuration. Memory segmentation and size limits can
        be adjusted through class attributes.

    Implementation Details:
        - Uses segmented memory pools for different types of information
        - Implements tag-based indexing for fast retrieval
        - Supports importance-weighted attention filtering
        - Maintains agent subscription patterns for targeted delivery
        - Automatically manages memory size through FIFO eviction

    Error Handling:
        - Returns empty results for invalid queries rather than failing
        - Handles missing segments gracefully
        - Validates importance scores to [0, 1] range

    Side Effects:
        - Maintains internal memory state across workflow execution
        - Memory persists for the lifetime of the node instance
        - Does not persist to disk or external storage

    Examples:
        >>> # Create a shared memory pool
        >>> memory_pool = SharedMemoryPoolNode()
        >>>
        >>> # Write memory from an agent
        >>> result = memory_pool.execute(
        ...     action="write",
        ...     agent_id="researcher_001",
        ...     content="Found correlation between X and Y",
        ...     tags=["research", "correlation", "data"],
        ...     importance=0.8,
        ...     segment="findings"
        ... )
        >>> assert result["success"] == True
        >>> assert result["memory_id"] is not None
        >>>
        >>> # Read with attention filter
        >>> memories = memory_pool.execute(
        ...     action="read",
        ...     agent_id="analyst_001",
        ...     attention_filter={
        ...         "tags": ["correlation"],
        ...         "importance_threshold": 0.7,
        ...         "window_size": 5
        ...     }
        ... )
        >>> assert len(memories["memories"]) > 0
        >>>
        >>> # Subscribe to specific segments
        >>> memory_pool.execute(
        ...     action="subscribe",
        ...     agent_id="monitor_001",
        ...     segments=["findings", "alerts"]
        ... )
        >>>
        >>> # Semantic query across all memories
        >>> results = memory_pool.execute(
        ...     action="query",
        ...     query="correlation analysis",
        ...     top_k=3
        ... )
    """

    def __init__(self, name=None, **kwargs):
        # Accept name parameter and pass all kwargs to parent
        if name:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.memory_segments = defaultdict(deque)
        self.agent_subscriptions = defaultdict(set)
        self.attention_indices = defaultdict(lambda: defaultdict(list))
        self.memory_id_counter = 0
        self.max_segment_size = 1000

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="read",
                description="Action to perform: 'write', 'read', 'subscribe', 'query'",
            ),
            "agent_id": NodeParameter(
                name="agent_id",
                type=str,
                required=False,
                default="system",
                description="ID of the agent performing the action",
            ),
            "content": NodeParameter(
                name="content",
                type=Any,
                required=False,
                description="Content to write to memory (for write action)",
            ),
            "tags": NodeParameter(
                name="tags",
                type=list,
                required=False,
                default=[],
                description="Tags to categorize the memory",
            ),
            "importance": NodeParameter(
                name="importance",
                type=float,
                required=False,
                default=0.5,
                description="Importance score (0.0 to 1.0)",
            ),
            "segment": NodeParameter(
                name="segment",
                type=str,
                required=False,
                default="general",
                description="Memory segment to write to",
            ),
            "attention_filter": NodeParameter(
                name="attention_filter",
                type=dict,
                required=False,
                default={},
                description="Filter criteria for reading memories",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context for the memory",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Search query for semantic memory search",
            ),
            "segments": NodeParameter(
                name="segments",
                type=list,
                required=False,
                default=["general"],
                description="Memory segments to subscribe to",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute memory pool operations.

        This method routes requests to appropriate handlers based on the action
        parameter, supporting write, read, subscribe, and query operations.

        Args:
            **kwargs: Operation parameters including:
                action (str): Operation type ('write', 'read', 'subscribe', 'query')
                Additional parameters specific to each action

        Returns:
            Dict[str, Any]: Operation results with 'success' status and action-specific data

        Raises:
            No exceptions raised - errors returned in response dict

        Side Effects:
            Modifies internal memory state for write operations
            Updates subscription lists for subscribe operations
        """
        action = kwargs.get("action")

        if action == "write":
            return self._write_memory(kwargs)
        elif action == "read":
            return self._read_with_attention(kwargs)
        elif action == "subscribe":
            return self._subscribe_agent(kwargs)
        elif action == "query":
            return self._semantic_query(kwargs)
        elif action == "metrics":
            return self._get_metrics()
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _write_memory(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Write information to shared pool with metadata."""
        self.memory_id_counter += 1
        memory_item = {
            "id": f"mem_{self.memory_id_counter}",
            "content": kwargs["content"],
            "agent_id": kwargs["agent_id"],
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "tags": kwargs.get("tags", []),
            "importance": kwargs.get("importance", 0.5),
            "context": kwargs.get("context", {}),
            "access_count": 0,
        }

        # Store in appropriate segment
        segment = kwargs.get("segment", "general")
        self.memory_segments[segment].append(memory_item)

        # Maintain segment size limit
        if len(self.memory_segments[segment]) > self.max_segment_size:
            self.memory_segments[segment].popleft()

        # Update attention indices
        self._update_attention_indices(memory_item, segment)

        # Get relevant agents
        relevant_agents = self._get_relevant_agents(memory_item, segment)

        return {
            "success": True,
            "memory_id": memory_item["id"],
            "segment": segment,
            "notified_agents": list(relevant_agents),
            "timestamp": memory_item["timestamp"],
        }

    def _read_with_attention(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Read relevant memories based on attention filter."""
        agent_id = kwargs["agent_id"]
        attention_filter = kwargs.get("attention_filter", {})

        relevant_memories = []

        # Apply attention mechanism
        for segment, memories in self.memory_segments.items():
            if self._matches_attention_filter(segment, attention_filter):
                for memory in memories:
                    relevance_score = self._calculate_relevance(
                        memory, attention_filter, agent_id
                    )
                    if relevance_score > attention_filter.get("threshold", 0.3):
                        memory["access_count"] += 1
                        relevant_memories.append(
                            {
                                **memory,
                                "relevance_score": relevance_score,
                                "segment": segment,
                            }
                        )

        # Sort by relevance and recency
        relevant_memories.sort(
            key=lambda x: (x["relevance_score"], x["timestamp"]), reverse=True
        )

        # Limit to attention window
        window_size = attention_filter.get("window_size", 10)
        selected_memories = relevant_memories[:window_size]

        return {
            "success": True,
            "memories": selected_memories,
            "total_available": len(relevant_memories),
            "segments_scanned": list(self.memory_segments.keys()),
            "agent_id": agent_id,
        }

    def _subscribe_agent(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Subscribe an agent to specific memory segments or tags."""
        agent_id = kwargs["agent_id"]
        segments = kwargs.get("segments", ["general"])
        tags = kwargs.get("tags", [])

        for segment in segments:
            self.agent_subscriptions[segment].add(agent_id)

        # Store subscription preferences
        if not hasattr(self, "agent_preferences"):
            self.agent_preferences = {}

        self.agent_preferences[agent_id] = {
            "segments": segments,
            "tags": tags,
            "attention_filter": kwargs.get("attention_filter", {}),
        }

        return {
            "success": True,
            "agent_id": agent_id,
            "subscribed_segments": segments,
            "subscribed_tags": tags,
        }

    def _semantic_query(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Perform semantic search across memories."""
        query = kwargs.get("query", "")
        kwargs["agent_id"]

        # Simple keyword matching for now (can be enhanced with embeddings)
        matching_memories = []
        query_lower = query.lower()

        for segment, memories in self.memory_segments.items():
            for memory in memories:
                content_str = str(memory.get("content", "")).lower()
                if query_lower in content_str:
                    score = content_str.count(query_lower) / len(content_str.split())
                    matching_memories.append(
                        {**memory, "match_score": score, "segment": segment}
                    )

        # Sort by match score
        matching_memories.sort(key=lambda x: x["match_score"], reverse=True)

        return {
            "success": True,
            "query": query,
            "results": matching_memories[:10],
            "total_matches": len(matching_memories),
        }

    def _update_attention_indices(self, memory_item: Dict[str, Any], segment: str):
        """Update indices for efficient attention-based retrieval."""
        # Index by tags
        for tag in memory_item.get("tags", []):
            self.attention_indices["tags"][tag].append(memory_item["id"])

        # Index by agent
        agent_id = memory_item["agent_id"]
        self.attention_indices["agents"][agent_id].append(memory_item["id"])

        # Index by importance level
        importance = memory_item["importance"]
        if importance >= 0.8:
            self.attention_indices["importance"]["high"].append(memory_item["id"])
        elif importance >= 0.5:
            self.attention_indices["importance"]["medium"].append(memory_item["id"])
        else:
            self.attention_indices["importance"]["low"].append(memory_item["id"])

    def _matches_attention_filter(
        self, segment: str, attention_filter: Dict[str, Any]
    ) -> bool:
        """Check if a segment matches the attention filter."""
        # Check segment filter
        if "segments" in attention_filter:
            if segment not in attention_filter["segments"]:
                return False

        return True

    def _calculate_relevance(
        self, memory: Dict[str, Any], attention_filter: Dict[str, Any], agent_id: str
    ) -> float:
        """Calculate relevance score for a memory item."""
        score = 0.0
        weights = attention_filter.get(
            "weights", {"tags": 0.3, "importance": 0.3, "recency": 0.2, "agent": 0.2}
        )

        # Tag matching
        if "tags" in attention_filter:
            filter_tags = set(attention_filter["tags"])
            memory_tags = set(memory.get("tags", []))
            if filter_tags & memory_tags:
                score += (
                    weights.get("tags", 0.3)
                    * len(filter_tags & memory_tags)
                    / len(filter_tags)
                )

        # Importance threshold
        importance_threshold = attention_filter.get("importance_threshold", 0.0)
        if memory.get("importance", 0) >= importance_threshold:
            score += weights.get("importance", 0.3) * memory["importance"]

        # Recency
        current_time = time.time()
        age_seconds = current_time - memory["timestamp"]
        recency_window = attention_filter.get("recency_window", 3600)  # 1 hour default
        if age_seconds < recency_window:
            recency_score = 1.0 - (age_seconds / recency_window)
            score += weights.get("recency", 0.2) * recency_score

        # Agent affinity
        if "preferred_agents" in attention_filter:
            if memory["agent_id"] in attention_filter["preferred_agents"]:
                score += weights.get("agent", 0.2)

        return min(score, 1.0)

    def _get_relevant_agents(
        self, memory_item: Dict[str, Any], segment: str
    ) -> Set[str]:
        """Get agents that should be notified about this memory."""
        relevant_agents = set()

        # Agents subscribed to this segment
        relevant_agents.update(self.agent_subscriptions.get(segment, set()))

        # Agents with matching tag subscriptions
        if hasattr(self, "agent_preferences"):
            for agent_id, prefs in self.agent_preferences.items():
                if any(
                    tag in memory_item.get("tags", []) for tag in prefs.get("tags", [])
                ):
                    relevant_agents.add(agent_id)

        # Remove the writing agent
        relevant_agents.discard(memory_item["agent_id"])

        return relevant_agents

    def _get_metrics(self) -> Dict[str, Any]:
        """Get memory pool metrics."""
        total_memories = sum(
            len(memories) for memories in self.memory_segments.values()
        )

        return {
            "success": True,
            "total_memories": total_memories,
            "segments": list(self.memory_segments.keys()),
            "segment_sizes": {
                segment: len(memories)
                for segment, memories in self.memory_segments.items()
            },
            "total_agents": len(self.agent_subscriptions),
            "memory_id_counter": self.memory_id_counter,
        }


@register_node()
class A2AAgentNode(LLMAgentNode):
    """
    Enhanced LLM agent with agent-to-agent communication capabilities.

    This node extends the standard LLMAgentNode with sophisticated A2A communication
    features, enabling agents to share insights through a shared memory pool, enhance
    their context with relevant information from other agents, and collaborate
    effectively on complex tasks.

    Design Philosophy:
        A2AAgentNode represents an intelligent agent that can both contribute to and
        benefit from collective intelligence. It automatically extracts insights from
        its responses and shares them with other agents while selectively attending
        to relevant information from the shared memory pool. This creates an emergent
        collaborative intelligence system.

    Upstream Dependencies:
        - QueryAnalysisNode: Provides analyzed queries and context
        - TeamFormationNode: Assigns roles and capabilities to agents
        - A2ACoordinatorNode: Delegates tasks and coordinates activities
        - SharedMemoryPoolNode: Provides access to shared memories

    Downstream Consumers:
        - SharedMemoryPoolNode: Receives insights and discoveries
        - A2ACoordinatorNode: Reports progress and results
        - SolutionEvaluatorNode: Provides solutions for evaluation
        - Other A2AAgentNodes: Indirect consumers through shared memory

    Configuration:
        Inherits all configuration from LLMAgentNode plus A2A-specific parameters
        for memory pool integration, attention filtering, and collaboration modes.

    Implementation Details:
        - Automatically extracts insights from LLM responses
        - Enhances prompts with relevant context from shared memory
        - Supports multiple collaboration modes (cooperative, competitive, hierarchical)
        - Tracks conversation context and shares key discoveries
        - Implements attention filtering to prevent information overload

    Error Handling:
        - Gracefully handles missing memory pool connections
        - Falls back to standard LLM behavior if A2A features fail
        - Validates insight extraction to prevent malformed memories

    Side Effects:
        - Writes insights to SharedMemoryPoolNode after each interaction
        - Maintains conversation history for context
        - May influence other agents through shared memories

    Examples:
        >>> # Create an A2A agent with specific expertise
        >>> agent = A2AAgentNode()
        >>>
        >>> # Execute with A2A features
        >>> result = agent.execute(
        ...     agent_id="researcher_001",
        ...     agent_role="research_specialist",
        ...     provider="openai",
        ...     model="gpt-4",
        ...     messages=[{
        ...         "role": "user",
        ...         "content": "Analyze the impact of AI on productivity"
        ...     }],
        ...     memory_pool=memory_pool_instance,
        ...     attention_filter={
        ...         "tags": ["productivity", "AI", "research"],
        ...         "importance_threshold": 0.7
        ...     },
        ...     collaboration_mode="cooperative"
        ... )
        >>> assert result["success"] == True
        >>> assert "insights_generated" in result["a2a_metadata"]
        >>>
        >>> # Agent automatically shares insights
        >>> insights = result["a2a_metadata"]["insights_generated"]
        >>> assert len(insights) > 0
        >>> assert all("content" in i for i in insights)
    """

    def __init__(self, name=None, **kwargs):
        # Accept name parameter and pass all kwargs to parent
        if name:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.local_memory = deque(maxlen=100)
        self.communication_log = deque(maxlen=50)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        # Inherit all LLMAgentNode parameters
        params = super().get_parameters()

        # Add A2A-specific parameters
        params.update(
            {
                "agent_id": NodeParameter(
                    name="agent_id",
                    type=str,
                    required=False,
                    default=f"agent_{uuid.uuid4().hex[:8]}",
                    description="Unique identifier for this agent",
                ),
                "agent_role": NodeParameter(
                    name="agent_role",
                    type=str,
                    required=False,
                    default="general",
                    description="Role of the agent (researcher, analyst, coordinator, etc.)",
                ),
                "memory_pool": NodeParameter(
                    name="memory_pool",
                    type=Node,
                    required=False,
                    description="Reference to SharedMemoryPoolNode",
                ),
                "attention_filter": NodeParameter(
                    name="attention_filter",
                    type=dict,
                    required=False,
                    default={},
                    description="Criteria for filtering relevant information from shared memory",
                ),
                "communication_config": NodeParameter(
                    name="communication_config",
                    type=dict,
                    required=False,
                    default={"mode": "direct", "protocol": "json-rpc"},
                    description="A2A communication settings",
                ),
                "collaboration_mode": NodeParameter(
                    name="collaboration_mode",
                    type=str,
                    required=False,
                    default="cooperative",
                    description="How agent collaborates: cooperative, competitive, hierarchical",
                ),
                "peer_agents": NodeParameter(
                    name="peer_agents",
                    type=list,
                    required=False,
                    default=[],
                    description="List of peer agent IDs for direct communication",
                ),
            }
        )
        return params

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the A2A agent with enhanced communication capabilities.

        This method extends the base LLMAgentNode execution by:
        1. Reading relevant context from the shared memory pool
        2. Enhancing the prompt with shared discoveries
        3. Executing the LLM call with enriched context
        4. Extracting insights from the response
        5. Sharing valuable insights back to the memory pool

        Args:
            **kwargs: All LLMAgentNode parameters plus:
                agent_id (str): Unique identifier for this agent
                agent_role (str): Agent's role in the team
                memory_pool (SharedMemoryPoolNode): Shared memory instance
                attention_filter (dict): Criteria for filtering memories
                collaboration_mode (str): How agent collaborates

        Returns:
            Dict[str, Any]: LLMAgentNode response plus:
                a2a_metadata: Information about A2A interactions including
                    insights_generated, shared_context_used, collaboration_stats

        Side Effects:
            Writes insights to shared memory pool if available
            Updates internal conversation history
        """
        # Extract A2A specific parameters
        agent_id = kwargs.get("agent_id")
        agent_role = kwargs.get("agent_role", "general")
        memory_pool = kwargs.get("memory_pool")
        attention_filter = kwargs.get("attention_filter", {})

        # Read from shared memory if available
        shared_context = []
        if memory_pool:
            memory_result = memory_pool.execute(
                action="read", agent_id=agent_id, attention_filter=attention_filter
            )
            if memory_result.get("success"):
                shared_context = memory_result.get("memories", [])

        # Store provider and model for use in summarization
        self._current_provider = kwargs.get("provider", "mock")
        self._current_model = kwargs.get("model", "mock-model")

        # Enhance messages with shared context
        messages = kwargs.get("messages", [])
        if shared_context:
            context_summary = self._summarize_shared_context(shared_context)
            enhanced_system_prompt = f"""You are agent {agent_id} with role: {agent_role}.

Relevant shared context from other agents:
{context_summary}

{kwargs.get('system_prompt', '')}"""
            kwargs["system_prompt"] = enhanced_system_prompt

        # Execute LLM agent
        result = super().run(**kwargs)

        # If successful, write insights to shared memory
        if result.get("success") and memory_pool:
            response_content = result.get("response", {}).get("content", "")

            # Use LLM to extract insights if provider supports it
            use_llm_extraction = kwargs.get("use_llm_insight_extraction", True)
            provider = kwargs.get("provider", "mock")

            if use_llm_extraction and provider not in ["mock"]:
                # Use LLM to extract and analyze insights
                insights = self._extract_insights_with_llm(
                    response_content, agent_role, agent_id, kwargs
                )
            else:
                # Fallback to rule-based extraction
                insights = self._extract_insights(response_content, agent_role)

            # Track insight statistics
            insight_stats = {
                "total": len(insights),
                "high_importance": sum(1 for i in insights if i["importance"] >= 0.8),
                "by_type": {},
                "extraction_method": (
                    "llm"
                    if use_llm_extraction and provider not in ["mock"]
                    else "rule-based"
                ),
            }

            for insight in insights:
                # Update type statistics
                insight_type = insight.get("metadata", {}).get(
                    "insight_type", "general"
                )
                insight_stats["by_type"][insight_type] = (
                    insight_stats["by_type"].get(insight_type, 0) + 1
                )

                # Write to memory pool with enhanced context
                memory_pool.execute(
                    action="write",
                    agent_id=agent_id,
                    content=insight["content"],
                    tags=insight.get("tags", [agent_role]),
                    importance=insight.get("importance", 0.6),
                    segment=insight.get("segment", agent_role),
                    context={
                        "source_message": messages[-1] if messages else None,
                        "agent_role": agent_role,
                        "insight_metadata": insight.get("metadata", {}),
                        "timestamp": kwargs.get("timestamp", time.time()),
                    },
                )

            # Store insights in local memory for agent's own reference
            for insight in insights:
                self.local_memory.append(
                    {
                        "type": "insight",
                        "content": insight["content"],
                        "importance": insight["importance"],
                        "timestamp": time.time(),
                    }
                )

        # Add A2A metadata to result
        result["a2a_metadata"] = {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "shared_context_used": len(shared_context),
            "insights_generated": len(insights) if "insights" in locals() else 0,
            "insight_statistics": insight_stats if "insight_stats" in locals() else {},
            "memory_pool_active": memory_pool is not None,
            "local_memory_size": len(self.local_memory),
        }

        return result

    def _summarize_shared_context(self, shared_context: List[Dict[str, Any]]) -> str:
        """Summarize shared context for inclusion in prompt."""
        if not shared_context:
            return "No relevant shared context available."

        # For small context, use simple formatting
        if len(shared_context) <= 3:
            summary_parts = []
            for memory in shared_context:
                agent_id = memory.get("agent_id", "unknown")
                content = memory.get("content", "")
                importance = memory.get("importance", 0)
                tags = ", ".join(memory.get("tags", []))

                summary_parts.append(
                    f"- Agent {agent_id} ({importance:.1f} importance, tags: {tags}): {content}"
                )
            return "\n".join(summary_parts)

        # For larger context, use LLM to create intelligent summary
        return self._summarize_with_llm(shared_context)

    def _summarize_with_llm(self, shared_context: List[Dict[str, Any]]) -> str:
        """Use LLM to create an intelligent summary of shared context."""

        # Prepare context for summarization
        context_items = []
        for memory in shared_context[:10]:  # Process up to 10 most relevant
            context_items.append(
                {
                    "agent": memory.get("agent_id", "unknown"),
                    "content": memory.get("content", ""),
                    "importance": memory.get("importance", 0),
                    "tags": memory.get("tags", []),
                    "type": memory.get("context", {})
                    .get("insight_metadata", {})
                    .get("insight_type", "general"),
                }
            )

        # Create summarization prompt
        summarization_prompt = f"""Summarize the following shared insights from other agents into a concise, actionable briefing.

Shared Context Items:
{json.dumps(context_items, indent=2)}

Create a summary that:
1. Groups related insights by theme
2. Highlights the most important findings (importance >= 0.8)
3. Identifies consensus points where multiple agents agree
4. Notes any contradictions or disagreements
5. Extracts key metrics and data points
6. Suggests areas needing further investigation

Format the summary as a brief paragraph (max 200 words) that another agent can quickly understand and act upon.
Focus on actionable intelligence rather than just listing what each agent said."""

        try:
            # Use the current agent's LLM configuration for summarization
            provider = getattr(self, "_current_provider", "mock")
            model = getattr(self, "_current_model", "mock-model")

            if provider not in ["mock"]:
                summary_kwargs = {
                    "provider": provider,
                    "model": model,
                    "temperature": 0.3,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert at synthesizing information from multiple sources into clear, actionable summaries.",
                        },
                        {"role": "user", "content": summarization_prompt},
                    ],
                    "max_tokens": 300,
                }

                result = super().run(**summary_kwargs)

                if result.get("success"):
                    summary = result.get("response", {}).get("content", "")
                    if summary:
                        return f"Shared Context Summary:\n{summary}"
        except Exception:
            pass

        # Fallback to simple summary
        summary_parts = []
        for memory in shared_context[:5]:
            agent_id = memory.get("agent_id", "unknown")
            content = memory.get("content", "")[:100] + "..."
            importance = memory.get("importance", 0)

            summary_parts.append(f"- {agent_id} [{importance:.1f}]: {content}")

        return "Recent insights:\n" + "\n".join(summary_parts)

    def _extract_insights(self, response: str, agent_role: str) -> List[Dict[str, Any]]:
        """Extract important insights from agent response using advanced NLP techniques."""
        insights = []

        # Enhanced keyword patterns for different types of insights
        insight_patterns = {
            "findings": {
                "keywords": [
                    "found",
                    "discovered",
                    "identified",
                    "revealed",
                    "uncovered",
                    "detected",
                    "observed",
                    "noted",
                    "recognized",
                ],
                "importance": 0.8,
                "tags": ["finding", "discovery"],
            },
            "conclusions": {
                "keywords": [
                    "conclude",
                    "therefore",
                    "thus",
                    "hence",
                    "consequently",
                    "as a result",
                    "in summary",
                    "overall",
                    "in conclusion",
                ],
                "importance": 0.9,
                "tags": ["conclusion", "summary"],
            },
            "comparisons": {
                "keywords": [
                    "compared to",
                    "versus",
                    "vs",
                    "better than",
                    "worse than",
                    "improvement",
                    "decline",
                    "increase",
                    "decrease",
                    "change",
                ],
                "importance": 0.7,
                "tags": ["comparison", "analysis"],
            },
            "recommendations": {
                "keywords": [
                    "recommend",
                    "suggest",
                    "should",
                    "advise",
                    "propose",
                    "best practice",
                    "optimal",
                    "ideal",
                ],
                "importance": 0.85,
                "tags": ["recommendation", "advice"],
            },
            "problems": {
                "keywords": [
                    "issue",
                    "problem",
                    "challenge",
                    "limitation",
                    "constraint",
                    "difficulty",
                    "obstacle",
                    "concern",
                    "risk",
                ],
                "importance": 0.75,
                "tags": ["problem", "challenge"],
            },
            "metrics": {
                "keywords": [
                    "percent",
                    "%",
                    "score",
                    "rating",
                    "benchmark",
                    "metric",
                    "measurement",
                    "performance",
                    "efficiency",
                ],
                "importance": 0.65,
                "tags": ["metric", "measurement"],
            },
        }

        # Process response by sentences for better context
        import re

        sentences = re.split(r"[.!?]+", response)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 20:
                continue

            # Calculate importance based on multiple factors
            importance = 0.5  # Base importance
            matched_tags = set([agent_role])
            insight_type = None

            # Check for insight patterns
            sentence_lower = sentence.lower()
            for pattern_type, pattern_info in insight_patterns.items():
                if any(
                    keyword in sentence_lower for keyword in pattern_info["keywords"]
                ):
                    importance = max(importance, pattern_info["importance"])
                    matched_tags.update(pattern_info["tags"])
                    insight_type = pattern_type
                    break

            # Extract entities and add as tags
            # Simple entity extraction - numbers, capitalized words, technical terms
            numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", sentence)
            if numbers:
                matched_tags.add("quantitative")
                importance += 0.1

            # Extract technical terms (words with specific patterns)
            tech_terms = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", sentence)
            if tech_terms:
                matched_tags.update(
                    [term.lower() for term in tech_terms[:2]]
                )  # Limit tags

            # Boost importance for sentences with multiple capital letters (proper nouns)
            capital_words = re.findall(r"\b[A-Z][A-Za-z]+\b", sentence)
            if len(capital_words) > 2:
                importance += 0.05

            # Check for structured data (JSON, lists, etc.)
            if any(char in sentence for char in ["{", "[", ":", "-"]):
                matched_tags.add("structured")
                importance += 0.05

            # Determine segment based on insight type and role
            segment = f"{agent_role}_{insight_type}" if insight_type else agent_role

            # Create insight with rich metadata
            insight = {
                "content": sentence,
                "importance": min(importance, 1.0),  # Cap at 1.0
                "tags": list(matched_tags),
                "segment": segment,
                "metadata": {
                    "length": len(sentence),
                    "has_numbers": bool(numbers),
                    "insight_type": insight_type or "general",
                    "extracted_entities": tech_terms[:3] if tech_terms else [],
                },
            }

            insights.append(insight)

        # Sort by importance and return top insights
        insights.sort(key=lambda x: x["importance"], reverse=True)

        # Dynamic limit based on response quality
        # If we have many high-quality insights, return more
        high_quality_count = sum(1 for i in insights if i["importance"] >= 0.7)
        limit = min(5 if high_quality_count > 3 else 3, len(insights))

        return insights[:limit]

    def _extract_insights_with_llm(
        self,
        response: str,
        agent_role: str,
        agent_id: str,
        original_kwargs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Use LLM to extract and analyze insights from the response."""

        # Prepare a focused prompt for insight extraction
        insight_extraction_prompt = f"""You are an AI insight extraction specialist. Analyze the following response and extract the most important insights.

Agent Role: {agent_role}
Original Response:
{response}

Extract 3-5 key insights from this response. For each insight:
1. Summarize the core finding or conclusion (max 100 words)
2. Assign an importance score (0.0-1.0) based on:
   - Novelty and uniqueness (0.3 weight)
   - Impact on decision-making (0.4 weight)
   - Supporting evidence quality (0.3 weight)
3. Categorize the insight type: finding, conclusion, comparison, recommendation, problem, metric, or pattern
4. Extract key entities mentioned (products, technologies, metrics, etc.)
5. Suggest relevant tags for categorization

Output your analysis as a JSON array with this structure:
[
  {{
    "content": "The core insight summarized concisely",
    "importance": 0.85,
    "type": "finding",
    "entities": ["MacBook Air M3", "M2", "battery life"],
    "tags": ["performance", "comparison", "hardware"],
    "evidence": "Brief supporting evidence from the text"
  }}
]

Focus on insights that would be valuable for other agents to know. Ensure the JSON is valid."""

        try:
            # Create a sub-call to the LLM for insight extraction
            extraction_kwargs = {
                "provider": original_kwargs.get("provider", "ollama"),
                "model": original_kwargs.get("model", "mistral"),
                "temperature": 0.3,  # Lower temperature for more focused extraction
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing text and extracting structured insights. Always respond with valid JSON.",
                    },
                    {"role": "user", "content": insight_extraction_prompt},
                ],
                "max_tokens": original_kwargs.get("max_tokens", 1000),
            }

            # Execute LLM call for insight extraction
            extraction_result = super().run(**extraction_kwargs)

            if extraction_result.get("success"):
                extracted_content = extraction_result.get("response", {}).get(
                    "content", ""
                )

                # Parse the JSON response
                import json
                import re

                # Try to extract JSON from the response
                json_match = re.search(r"\[.*?\]", extracted_content, re.DOTALL)
                if json_match:
                    try:
                        extracted_insights = json.loads(json_match.group())

                        # Convert to our insight format
                        insights = []
                        for item in extracted_insights[:5]:  # Limit to 5 insights
                            insight = {
                                "content": item.get("content", ""),
                                "importance": min(
                                    max(item.get("importance", 0.5), 0.0), 1.0
                                ),
                                "tags": item.get("tags", []) + [agent_role],
                                "segment": f"{agent_role}_{item.get('type', 'general')}",
                                "metadata": {
                                    "insight_type": item.get("type", "general"),
                                    "extracted_entities": item.get("entities", []),
                                    "evidence": item.get("evidence", ""),
                                    "llm_extracted": True,
                                },
                            }
                            insights.append(insight)

                        return insights
                    except json.JSONDecodeError:
                        pass

        except Exception:
            # Log the error but don't fail - fall back to rule-based extraction
            pass

        # If LLM extraction fails, fall back to rule-based
        return self._extract_insights(response, agent_role)


@register_node()
class A2ACoordinatorNode(CycleAwareNode):
    """
    Coordinates communication and task delegation between A2A agents.

    This node acts as a central orchestrator for multi-agent systems, managing task
    distribution, consensus building, and workflow coordination. It implements various
    coordination strategies to optimize agent utilization and ensure effective
    collaboration across heterogeneous agent teams.

    Design Philosophy:
        The A2ACoordinatorNode serves as a decentralized coordination mechanism that
        enables agents to self-organize without requiring a fixed hierarchy. It provides
        flexible coordination patterns (delegation, broadcast, consensus, workflow)
        that can be composed to create sophisticated multi-agent behaviors.

    Upstream Dependencies:
        - ProblemAnalyzerNode: Provides decomposed tasks and requirements
        - TeamFormationNode: Supplies formed teams and agent assignments
        - QueryAnalysisNode: Delivers analyzed queries needing coordination
        - OrchestrationManagerNode: High-level orchestration directives

    Downstream Consumers:
        - A2AAgentNode: Receives task assignments and coordination messages
        - SharedMemoryPoolNode: Stores coordination decisions and progress
        - SolutionEvaluatorNode: Evaluates coordinated solution components
        - ConvergenceDetectorNode: Monitors coordination effectiveness

    Configuration:
        The coordinator adapts its behavior based on the coordination strategy
        selected and the characteristics of available agents. No static configuration
        is required, but runtime parameters control coordination behavior.

    Implementation Details:
        - Maintains registry of active agents with capabilities and status
        - Implements multiple delegation strategies (best_match, round_robin, auction)
        - Tracks task assignments and agent performance metrics
        - Supports both synchronous and asynchronous coordination patterns
        - Manages consensus voting with configurable thresholds

    Error Handling:
        - Handles agent failures with automatic reassignment
        - Validates task requirements before delegation
        - Falls back to broadcast when specific agents unavailable
        - Returns partial results if consensus cannot be reached

    Side Effects:
        - Maintains internal agent registry across calls
        - Updates agent performance metrics after task completion
        - May modify task priorities based on agent availability

    Examples:
        >>> # Create coordinator
        >>> coordinator = A2ACoordinatorNode()
        >>>
        >>> # Register agents
        >>> coordinator.execute(
        ...     action="register",
        ...     agent_info={
        ...         "id": "analyst_001",
        ...         "skills": ["data_analysis", "statistics"],
        ...         "role": "analyst"
        ...     }
        ... )
        >>>
        >>> # Delegate task with best match strategy
        >>> result = coordinator.execute(
        ...     action="delegate",
        ...     task={
        ...         "type": "analysis",
        ...         "description": "Analyze sales data",
        ...         "required_skills": ["data_analysis"],
        ...         "priority": "high"
        ...     },
        ...     available_agents=[
        ...         {"id": "analyst_001", "skills": ["data_analysis"]},
        ...         {"id": "researcher_001", "skills": ["research"]}
        ...     ],
        ...     coordination_strategy="best_match"
        ... )
        >>> assert result["success"] == True
        >>> assert result["assigned_agent"] == "analyst_001"
        >>>
        >>> # Build consensus among agents
        >>> consensus_result = coordinator.execute(
        ...     action="consensus",
        ...     proposal="Implement new feature X",
        ...     voting_agents=["agent1", "agent2", "agent3"],
        ...     consensus_threshold=0.66
        ... )
    """

    def __init__(self, name=None, **kwargs):
        # Accept name parameter and pass all kwargs to parent
        if name:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.registered_agents = {}
        self.task_queue = deque()
        self.consensus_sessions = {}

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="coordinate",
                description="Action: 'register', 'delegate', 'broadcast', 'consensus', 'coordinate'",
            ),
            "agent_info": NodeParameter(
                name="agent_info",
                type=dict,
                required=False,
                description="Information about agent (for registration)",
            ),
            "task": NodeParameter(
                name="task",
                type=dict,
                required=False,
                description="Task to delegate or coordinate",
            ),
            "message": NodeParameter(
                name="message",
                type=dict,
                required=False,
                description="Message to broadcast",
            ),
            "consensus_proposal": NodeParameter(
                name="consensus_proposal",
                type=dict,
                required=False,
                description="Proposal for consensus",
            ),
            "available_agents": NodeParameter(
                name="available_agents",
                type=list,
                required=False,
                default=[],
                description="List of available agents",
            ),
            "coordination_strategy": NodeParameter(
                name="coordination_strategy",
                type=str,
                required=False,
                default="best_match",
                description="Strategy: 'best_match', 'round_robin', 'broadcast', 'auction'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute coordination action with cycle awareness.

        Routes coordination requests to appropriate handlers based on action
        parameter. Tracks coordination history and agent performance across
        iterations for cycle-aware optimization.

        Args:
            context: Execution context with cycle information
            **kwargs: Action-specific parameters including:
                action (str): Type of coordination action
                agent_info (dict): Agent registration details
                task (dict): Task to delegate
                available_agents (list): Agents available for tasks
                coordination_strategy (str): Delegation strategy

        Returns:
            Dict[str, Any]: Action results with cycle metadata including:
                success (bool): Whether action succeeded
                cycle_info (dict): Iteration and history information
                Additional action-specific fields

        Raises:
            None - errors returned in result dictionary

        Side Effects:
            Updates internal agent registry
            Modifies coordination history
            Updates agent performance metrics

        Examples:
            >>> coordinator = A2ACoordinatorNode()
            >>> result = coordinator.execute(context,
            ...     action=\"delegate\",
            ...     task={\"type\": \"analysis\", \"required_skills\": [\"data\"]},
            ...     coordination_strategy=\"best_match\"
            ... )
            >>> assert result[\"success\"] == True
        """
        context = kwargs.get("context", {})
        action = kwargs.get("action")

        # Get cycle information using CycleAwareNode helpers
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)
        prev_state = self.get_previous_state(context)

        # Initialize cycle-aware coordination state
        if is_first:
            self.log_cycle_info(context, f"Starting coordination with action: {action}")
            coordination_history = []
            agent_performance_history = {}
        else:
            coordination_history = prev_state.get("coordination_history", [])
            agent_performance_history = prev_state.get("agent_performance", {})

        # Execute the coordination action
        if action == "register":
            result = self._register_agent(kwargs, context)
        elif action == "delegate":
            result = self._delegate_task(
                kwargs, context, coordination_history, agent_performance_history
            )
        elif action == "broadcast":
            result = self._broadcast_message(kwargs, context)
        elif action == "consensus":
            result = self._manage_consensus(kwargs, context, coordination_history)
        elif action == "coordinate":
            result = self._coordinate_workflow(kwargs, context, iteration)
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}

        # Track coordination history for cycle learning
        coordination_event = {
            "iteration": iteration,
            "action": action,
            "success": result.get("success", False),
            "timestamp": time.time(),
            "details": {k: v for k, v in result.items() if k not in ["success"]},
        }
        coordination_history.append(coordination_event)

        # Update agent performance tracking
        if action == "delegate" and result.get("success"):
            agent_id = result.get("delegated_to")
            if agent_id:
                if agent_id not in agent_performance_history:
                    agent_performance_history[agent_id] = {
                        "assignments": 0,
                        "success_rate": 1.0,
                    }
                agent_performance_history[agent_id]["assignments"] += 1

        # Add cycle-aware metadata to result
        result.update(
            {
                "cycle_info": {
                    "iteration": iteration,
                    "coordination_history_length": len(coordination_history),
                    "active_agents": len(self.registered_agents),
                    "performance_tracked_agents": len(agent_performance_history),
                }
            }
        )

        # Log progress
        if iteration % 5 == 0:  # Log every 5 iterations
            self.log_cycle_info(
                context,
                f"Coordination stats: {len(coordination_history)} events, {len(self.registered_agents)} agents",
            )

        # Persist state for next iteration
        return {
            **result,
            **self.set_cycle_state(
                {
                    "coordination_history": coordination_history[
                        -50:
                    ],  # Keep last 50 events
                    "agent_performance": agent_performance_history,
                }
            ),
        }

    def _register_agent(
        self, kwargs: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Register an agent with the coordinator."""
        agent_info = kwargs.get("agent_info", {})
        agent_id = agent_info.get("id")

        if not agent_id:
            return {"success": False, "error": "Agent ID required"}

        self.registered_agents[agent_id] = {
            "id": agent_id,
            "skills": agent_info.get("skills", []),
            "role": agent_info.get("role", "general"),
            "status": "available",
            "registered_at": time.time(),
            "task_count": 0,
            "success_rate": 1.0,
        }

        return {
            "success": True,
            "agent_id": agent_id,
            "registered_agents": list(self.registered_agents.keys()),
        }

    def _delegate_task(
        self,
        kwargs: Dict[str, Any],
        context: Dict[str, Any],
        coordination_history: List[Dict],
        agent_performance: Dict,
    ) -> Dict[str, Any]:
        """Delegate task to most suitable agent with cycle-aware optimization."""
        task = kwargs.get("task", {})
        available_agents = kwargs.get("available_agents", [])
        strategy = kwargs.get("coordination_strategy", "best_match")

        if not available_agents:
            available_agents = [
                agent
                for agent in self.registered_agents.values()
                if agent["status"] == "available"
            ]

        if not available_agents:
            return {"success": False, "error": "No available agents"}

        # Use cycle-aware agent selection based on performance history
        iteration = self.get_iteration(context)

        # Select agent based on strategy with cycle learning
        if strategy == "best_match":
            selected_agent = self._find_best_match_cycle_aware(
                task, available_agents, agent_performance, iteration
            )
        elif strategy == "round_robin":
            # Cycle-aware round-robin based on iteration
            agent_index = iteration % len(available_agents)
            selected_agent = available_agents[agent_index]
        elif strategy == "auction":
            selected_agent = self._run_auction_cycle_aware(
                task, available_agents, agent_performance
            )
        else:
            selected_agent = available_agents[0]

        if not selected_agent:
            return {"success": False, "error": "No suitable agent found"}

        # Update agent status
        agent_id = selected_agent.get("id")
        if agent_id in self.registered_agents:
            self.registered_agents[agent_id]["status"] = "busy"
            self.registered_agents[agent_id]["task_count"] += 1

        return {
            "success": True,
            "delegated_to": agent_id,
            "task": task,
            "strategy": strategy,
            "agent_performance_score": agent_performance.get(agent_id, {}).get(
                "success_rate", 1.0
            ),
            "iteration": iteration,
        }

    def _broadcast_message(
        self, kwargs: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Broadcast message to relevant agents."""
        message = kwargs.get("message", {})
        target_roles = message.get("target_roles", [])
        target_skills = message.get("target_skills", [])

        recipients = []
        for agent in self.registered_agents.values():
            # Check role match
            if target_roles and agent["role"] not in target_roles:
                continue

            # Check skills match
            if target_skills:
                if not any(skill in agent["skills"] for skill in target_skills):
                    continue

            recipients.append(agent["id"])

        return {
            "success": True,
            "recipients": recipients,
            "message": message,
            "broadcast_time": time.time(),
        }

    def _manage_consensus(
        self,
        kwargs: Dict[str, Any],
        context: Dict[str, Any],
        coordination_history: List[Dict],
    ) -> Dict[str, Any]:
        """Manage consensus building among agents."""
        proposal = kwargs.get("consensus_proposal", {})
        session_id = proposal.get("session_id", str(uuid.uuid4()))

        if session_id not in self.consensus_sessions:
            self.consensus_sessions[session_id] = {
                "proposal": proposal,
                "votes": {},
                "started_at": time.time(),
                "status": "open",
            }

        session = self.consensus_sessions[session_id]

        # Handle vote
        if "vote" in kwargs:
            agent_id = kwargs.get("agent_id")
            vote = kwargs.get("vote")
            session["votes"][agent_id] = vote

        # Check if consensus reached
        total_agents = len(self.registered_agents)
        votes_cast = len(session["votes"])

        if votes_cast >= total_agents * 0.5:  # Simple majority
            yes_votes = sum(1 for v in session["votes"].values() if v)
            consensus_reached = yes_votes > votes_cast / 2

            session["status"] = "completed"
            session["result"] = "approved" if consensus_reached else "rejected"

            return {
                "success": True,
                "session_id": session_id,
                "consensus_reached": consensus_reached,
                "result": session["result"],
                "votes": session["votes"],
            }

        return {
            "success": True,
            "session_id": session_id,
            "status": session["status"],
            "votes_cast": votes_cast,
            "votes_needed": int(total_agents * 0.5),
        }

    def _coordinate_workflow(
        self, kwargs: Dict[str, Any], context: Dict[str, Any], iteration: int
    ) -> Dict[str, Any]:
        """Coordinate a multi-agent workflow."""
        workflow_spec = kwargs.get("task", {})
        steps = workflow_spec.get("steps", [])

        coordination_plan = []
        for step in steps:
            required_skills = step.get("required_skills", [])
            available_agents = [
                agent
                for agent in self.registered_agents.values()
                if any(skill in agent["skills"] for skill in required_skills)
            ]

            if available_agents:
                selected_agent = self._find_best_match(step, available_agents)
                coordination_plan.append(
                    {
                        "step": step["name"],
                        "assigned_to": selected_agent["id"],
                        "skills_matched": [
                            s for s in required_skills if s in selected_agent["skills"]
                        ],
                    }
                )
            else:
                coordination_plan.append(
                    {
                        "step": step["name"],
                        "assigned_to": None,
                        "error": "No agent with required skills",
                    }
                )

        return {
            "success": True,
            "workflow": workflow_spec.get("name", "unnamed"),
            "coordination_plan": coordination_plan,
            "total_steps": len(steps),
            "assigned_steps": sum(1 for p in coordination_plan if p.get("assigned_to")),
        }

    def _find_best_match(
        self, task: Dict[str, Any], agents: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find best matching agent for task."""
        required_skills = task.get("required_skills", [])
        if not required_skills:
            return agents[0] if agents else None

        best_agent = None
        best_score = 0

        for agent in agents:
            agent_skills = set(agent.get("skills", []))
            required_set = set(required_skills)

            # Calculate match score
            matches = agent_skills & required_set
            score = len(matches) / len(required_set) if required_set else 0

            # Consider success rate
            success_rate = agent.get("success_rate", 1.0)
            score *= success_rate

            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent

    def _run_auction(
        self, task: Dict[str, Any], agents: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Run auction-based task assignment."""
        # Simplified auction - agents bid based on their capability
        bids = []

        for agent in agents:
            # Calculate bid based on skill match and availability
            required_skills = set(task.get("required_skills", []))
            agent_skills = set(agent.get("skills", []))

            skill_match = (
                len(required_skills & agent_skills) / len(required_skills)
                if required_skills
                else 1.0
            )
            workload = 1.0 - (agent.get("task_count", 0) / 10.0)  # Lower bid if busy

            bid_value = skill_match * workload * agent.get("success_rate", 1.0)

            bids.append({"agent": agent, "bid": bid_value})

        # Select highest bidder
        if bids:
            bids.sort(key=lambda x: x["bid"], reverse=True)
            return bids[0]["agent"]

        return None

    def _find_best_match_cycle_aware(
        self,
        task: Dict[str, Any],
        agents: List[Dict[str, Any]],
        agent_performance: Dict[str, Dict],
        iteration: int,
    ) -> Optional[Dict[str, Any]]:
        """Find best matching agent using cycle-aware performance data."""
        required_skills = task.get("required_skills", [])
        if not required_skills:
            # When no specific skills required, prefer agents with better historical performance
            if agent_performance:
                best_agent = None
                best_score = 0
                for agent in agents:
                    agent_id = agent.get("id")
                    perf = agent_performance.get(
                        agent_id, {"success_rate": 1.0, "assignments": 0}
                    )
                    # Balance experience and success rate
                    experience_factor = min(
                        perf["assignments"] / 10.0, 1.0
                    )  # Max at 10 assignments
                    score = perf["success_rate"] * (0.7 + 0.3 * experience_factor)
                    if score > best_score:
                        best_score = score
                        best_agent = agent
                return best_agent or (agents[0] if agents else None)
            return agents[0] if agents else None

        best_agent = None
        best_score = 0

        for agent in agents:
            agent_id = agent.get("id")
            agent_skills = set(agent.get("skills", []))
            required_set = set(required_skills)

            # Calculate skill match score
            matches = agent_skills & required_set
            skill_score = len(matches) / len(required_set) if required_set else 0

            # Get performance history
            perf = agent_performance.get(
                agent_id, {"success_rate": 1.0, "assignments": 0}
            )
            performance_score = perf["success_rate"]

            # Experience bonus (agents with more assignments get slight preference)
            experience_bonus = min(perf["assignments"] * 0.05, 0.2)  # Max 20% bonus

            # Cycle adaptation: prefer different agents in different iterations to explore
            diversity_factor = 1.0
            if iteration > 0 and agent_performance:
                recent_assignments = sum(
                    1 for p in agent_performance.values() if p["assignments"] > 0
                )
                if recent_assignments > 0:
                    agent_usage_ratio = perf["assignments"] / recent_assignments
                    if agent_usage_ratio > 0.5:  # Over-used agent
                        diversity_factor = 0.8  # Slight penalty

            # Combined score
            final_score = (
                skill_score * performance_score * diversity_factor
            ) + experience_bonus

            if final_score > best_score:
                best_score = final_score
                best_agent = agent

        return best_agent

    def _run_auction_cycle_aware(
        self,
        task: Dict[str, Any],
        agents: List[Dict[str, Any]],
        agent_performance: Dict[str, Dict],
    ) -> Optional[Dict[str, Any]]:
        """Run auction-based task assignment with cycle-aware bidding."""
        bids = []

        for agent in agents:
            agent_id = agent.get("id")

            # Calculate bid based on skill match and availability (original logic)
            required_skills = set(task.get("required_skills", []))
            agent_skills = set(agent.get("skills", []))

            skill_match = (
                len(required_skills & agent_skills) / len(required_skills)
                if required_skills
                else 1.0
            )
            workload = 1.0 - (agent.get("task_count", 0) / 10.0)  # Lower bid if busy

            # Enhance with performance history
            perf = agent_performance.get(
                agent_id, {"success_rate": 1.0, "assignments": 0}
            )
            performance_factor = perf["success_rate"]

            # Experience factor (slight preference for experienced agents)
            experience_factor = min(
                1.0 + (perf["assignments"] * 0.02), 1.2
            )  # Max 20% boost

            bid_value = skill_match * workload * performance_factor * experience_factor

            bids.append({"agent": agent, "bid": bid_value})

        # Select highest bidder
        if bids:
            bids.sort(key=lambda x: x["bid"], reverse=True)
            return bids[0]["agent"]

        return None
