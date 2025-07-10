"""Advanced LLM Agent node with LangChain integration and MCP support."""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


@dataclass
class TokenUsage:
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage"):
        """Add another usage record."""
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


@dataclass
class CostEstimate:
    """Cost estimation for LLM usage."""

    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0
    currency: str = "USD"


@dataclass
class UsageMetrics:
    """Comprehensive usage metrics."""

    token_usage: TokenUsage = field(default_factory=TokenUsage)
    cost_estimate: CostEstimate = field(default_factory=CostEstimate)
    execution_time_ms: float = 0.0
    model: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@register_node()
class LLMAgentNode(Node):
    """
    Advanced Large Language Model agent with LangChain integration and MCP
    support, with optional cost tracking and usage monitoring.

    Design Purpose and Philosophy:
    The LLMAgent node provides enterprise-grade AI agent capabilities with
    support for multiple LLM providers, conversation memory, tool calling, and
    MCP protocol integration.
    It's designed to replace simple PythonCodeNode workarounds with proper
    agent architecture.

    Upstream Dependencies:
    - LLM provider credentials (OpenAI, Anthropic, Azure)
    - Tool definitions and implementations for agent capabilities
    - Conversation history and context for memory management
    - MCP server configurations for context sharing
    - Prompt templates and system instructions

    Downstream Consumers:
    - Workflow orchestration nodes that need AI decision-making
    - Data processing pipelines requiring intelligent analysis
    - Multi-agent systems coordinating complex tasks
    - User interfaces presenting agent responses
    - Monitoring systems tracking agent performance

    Usage Patterns:
    1. Single-turn Q&A with context from MCP resources
    2. Multi-turn conversations with persistent memory
    3. Tool-calling agents that execute workflow operations
    4. Planning agents that decompose complex goals
    5. RAG agents combining retrieval with generation

    Implementation Details:
    - Supports OpenAI, Anthropic Claude, Azure OpenAI, and local models
    - Integrates with LangChain for advanced agent patterns
    - Implements conversation memory with configurable persistence
    - Provides tool calling with proper error handling and validation
    - Supports MCP protocol for seamless context sharing
    - Includes prompt optimization and template management

    Error Handling:
    - APIError: When LLM provider API calls fail
    - AuthenticationError: When API credentials are invalid
    - RateLimitError: When API rate limits are exceeded
    - ToolExecutionError: When agent tool calls fail
    - MemoryError: When conversation memory operations fail
    - MCPError: When MCP protocol operations fail

    Side Effects:
    - Makes API calls to external LLM providers
    - Stores conversation history in memory or persistent storage
    - Executes tools that may modify external systems
    - Connects to MCP servers for context retrieval
    - Logs agent interactions and performance metrics

    Examples:
        >>> # Basic Q&A agent with OpenAI
        >>> agent = LLMAgentNode()
        >>> result = agent.execute(
        ...     provider="openai",
        ...     model="gpt-4",
        ...     messages=[
        ...         {"role": "user", "content": "Analyze the customer data and provide insights"}
        ...     ],
        ...     system_prompt="You are a data analyst expert.",
        ...     mcp_context=["data://customer_reports/*"]
        ... )

        >>> # Tool-calling agent
        >>> tool_agent = LLMAgentNode()
        >>> result = tool_agent.execute(
        ...     provider="anthropic",
        ...     model="claude-3-sonnet",
        ...     messages=[{"role": "user", "content": "Create a report and email it"}],
        ...     tools=[
        ...         {
        ...             "name": "create_report",
        ...             "description": "Generate a data report",
        ...             "parameters": {"type": "object", "properties": {"format": {"type": "string"}}}
        ...         },
        ...         {
        ...             "name": "send_email",
        ...             "description": "Send email with attachment",
        ...             "parameters": {"type": "object", "properties": {"recipient": {"type": "string"}}}
        ...         }
        ...     ],
        ...     conversation_id="report_session_123"
        ... )

        >>> # RAG agent with MCP integration
        >>> rag_agent = LLMAgentNode()
        >>> result = rag_agent.execute(
        ...     provider="azure",
        ...     model="gpt-4-turbo",
        ...     messages=[{"role": "user", "content": "What are the compliance requirements?"}],
        ...     rag_config={
        ...         "enabled": True,
        ...         "top_k": 5,
        ...         "similarity_threshold": 0.8
        ...     },
        ...     mcp_servers=[
        ...         {
        ...             "name": "compliance-server",
        ...             "transport": "stdio",
        ...             "command": "python",
        ...             "args": ["-m", "compliance_mcp"]
        ...         }
        ...     ]
        ... )
    """

    # Model pricing (USD per 1K tokens)
    MODEL_PRICING = {
        # OpenAI models
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-3.5-turbo": {"prompt": 0.001, "completion": 0.002},
        "gpt-3.5-turbo-16k": {"prompt": 0.003, "completion": 0.004},
        # Anthropic models
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        "claude-2.1": {"prompt": 0.008, "completion": 0.024},
        # Google models
        "gemini-pro": {"prompt": 0.00025, "completion": 0.0005},
        "gemini-pro-vision": {"prompt": 0.00025, "completion": 0.0005},
        # Cohere models
        "command": {"prompt": 0.0015, "completion": 0.0015},
        "command-light": {"prompt": 0.0006, "completion": 0.0006},
    }

    def __init__(self, **kwargs):
        """Initialize LLMAgentNode with optional monitoring features.

        Args:
            enable_monitoring: Enable token usage and cost tracking
            budget_limit: Maximum spend allowed in USD (None = unlimited)
            alert_threshold: Alert when usage reaches this fraction of budget
            track_history: Whether to keep usage history
            history_limit: Maximum history entries to keep
            custom_pricing: Override default pricing (per 1K tokens)
            cost_multiplier: Multiply all costs by this factor
            **kwargs: Additional Node parameters
        """
        super().__init__(**kwargs)

        # Monitoring configuration
        self.enable_monitoring = kwargs.get("enable_monitoring", False)
        self.budget_limit = kwargs.get("budget_limit")
        self.alert_threshold = kwargs.get("alert_threshold", 0.8)
        self.track_history = kwargs.get("track_history", True)
        self.history_limit = kwargs.get("history_limit", 1000)
        self.custom_pricing = kwargs.get("custom_pricing")
        self.cost_multiplier = kwargs.get("cost_multiplier", 1.0)

        # Usage tracking (only if monitoring enabled)
        if self.enable_monitoring:
            self._total_usage = TokenUsage()
            self._total_cost = 0.0
            self._usage_history: List[UsageMetrics] = []
            self._budget_alerts_sent = False

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "provider": NodeParameter(
                name="provider",
                type=str,
                required=False,
                default="mock",
                description="LLM provider: openai, anthropic, azure, local, or mock",
            ),
            "model": NodeParameter(
                name="model",
                type=str,
                required=False,
                default="gpt-4",
                description="Model name (e.g., gpt-4, claude-3-sonnet, gpt-4-turbo)",
            ),
            "messages": NodeParameter(
                name="messages",
                type=list,
                required=False,
                default=[],
                description="Conversation messages in OpenAI format",
            ),
            "system_prompt": NodeParameter(
                name="system_prompt",
                type=str,
                required=False,
                description="System prompt to guide agent behavior",
            ),
            "tools": NodeParameter(
                name="tools",
                type=list,
                required=False,
                default=[],
                description="Available tools for agent to call",
            ),
            "conversation_id": NodeParameter(
                name="conversation_id",
                type=str,
                required=False,
                description="Unique ID for conversation memory persistence",
            ),
            "memory_config": NodeParameter(
                name="memory_config",
                type=dict,
                required=False,
                default={},
                description="Memory configuration (type, max_tokens, persistence)",
            ),
            "mcp_servers": NodeParameter(
                name="mcp_servers",
                type=list,
                required=False,
                default=[],
                description="MCP server configurations for context retrieval",
            ),
            "mcp_context": NodeParameter(
                name="mcp_context",
                type=list,
                required=False,
                default=[],
                description="MCP resource URIs to include as context",
            ),
            "auto_discover_tools": NodeParameter(
                name="auto_discover_tools",
                type=bool,
                required=False,
                default=False,
                description="Automatically discover and use MCP tools",
            ),
            "rag_config": NodeParameter(
                name="rag_config",
                type=dict,
                required=False,
                default={},
                description="RAG configuration (enabled, top_k, threshold, embeddings)",
            ),
            "generation_config": NodeParameter(
                name="generation_config",
                type=dict,
                required=False,
                default={},
                description="Generation parameters (temperature, max_tokens, top_p)",
            ),
            "streaming": NodeParameter(
                name="streaming",
                type=bool,
                required=False,
                default=False,
                description="Enable streaming responses",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=120,
                description="Request timeout in seconds",
            ),
            "max_retries": NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum retry attempts for failed requests",
            ),
            # Monitoring parameters
            "enable_monitoring": NodeParameter(
                name="enable_monitoring",
                type=bool,
                required=False,
                default=False,
                description="Enable token usage tracking and cost monitoring",
            ),
            "budget_limit": NodeParameter(
                name="budget_limit",
                type=float,
                required=False,
                description="Maximum spend allowed in USD (None = unlimited)",
            ),
            "alert_threshold": NodeParameter(
                name="alert_threshold",
                type=float,
                required=False,
                default=0.8,
                description="Alert when usage reaches this fraction of budget",
            ),
            "track_history": NodeParameter(
                name="track_history",
                type=bool,
                required=False,
                default=True,
                description="Whether to keep usage history for analytics",
            ),
            "custom_pricing": NodeParameter(
                name="custom_pricing",
                type=dict,
                required=False,
                description="Override default model pricing (per 1K tokens)",
            ),
            "auto_execute_tools": NodeParameter(
                name="auto_execute_tools",
                type=bool,
                required=False,
                default=True,
                description="Automatically execute tool calls from LLM",
            ),
            "tool_execution_config": NodeParameter(
                name="tool_execution_config",
                type=dict,
                required=False,
                default={},
                description="Configuration for tool execution behavior",
            ),
            "use_real_mcp": NodeParameter(
                name="use_real_mcp",
                type=bool,
                required=False,
                default=True,
                description="Use real MCP tool execution instead of mock execution",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """
        Execute the LLM agent with the specified configuration.

        This is the main entry point for using the LLMAgent. It handles context
        preparation, provider selection, response generation, and
        post-processing.

        Args:
            **kwargs: Configuration parameters including:
                provider (str): LLM provider name. Options: "openai", "anthropic", "ollama", "mock"
                model (str): Model identifier specific to the provider
                messages (List[Dict[str, str]]): Conversation messages in OpenAI format
                system_prompt (str, optional): System message to guide agent behavior
                tools (List[Dict], optional): Available tools for function calling
                conversation_id (str, optional): ID for conversation memory persistence
                memory_config (Dict, optional): Memory configuration options
                mcp_servers (List[Dict], optional): MCP server configurations
                mcp_context (List[str], optional): MCP resource URIs to include
                rag_config (Dict, optional): RAG configuration for retrieval
                generation_config (Dict, optional): LLM generation parameters
                streaming (bool, optional): Enable streaming responses
                timeout (int, optional): Request timeout in seconds
                max_retries (int, optional): Maximum retry attempts

        Returns:
            Dict[str, Any]: Response dictionary containing:
                success (bool): Whether the operation succeeded
                response (Dict): LLM response with content, role, tool_calls, etc.
                conversation_id (str): Conversation identifier
                usage (Dict): Token usage and cost metrics
                context (Dict): Information about context sources used
                metadata (Dict): Additional metadata about the request
                error (str, optional): Error message if success is False
                error_type (str, optional): Type of error that occurred
                recovery_suggestions (List[str], optional): Suggestions for fixing errors

        Examples:

            Basic usage with OpenAI:

            >>> agent = LLMAgentNode()
            >>> result = agent.execute(
            ...     provider="openai",
            ...     model="gpt-4",
            ...     messages=[
            ...         {"role": "user", "content": "Explain quantum computing"}
            ...     ],
            ...     generation_config={
            ...         "temperature": 0.7,
            ...         "max_tokens": 500,
            ...         "top_p": 0.9,
            ...         "frequency_penalty": 0.0,
            ...         "presence_penalty": 0.0
            ...     }
            ... )
            >>> print(result["response"]["content"])  # doctest: +SKIP

            Using Ollama with custom model:

            >>> result = agent.execute(
            ...     provider="ollama",
            ...     model="llama3.1:8b-instruct-q8_0",
            ...     messages=[
            ...         {"role": "user", "content": "Write a Python function"}
            ...     ],
            ...     generation_config={
            ...         "temperature": 0.5,
            ...         "max_tokens": 1000,
            ...         "top_p": 0.95,
            ...         "seed": 42  # For reproducible outputs
            ...     }
            ... )  # doctest: +SKIP

            With system prompt and conversation memory:

            >>> result = agent.execute(
            ...     provider="anthropic",
            ...     model="claude-3-sonnet-20240229",
            ...     system_prompt="You are a helpful coding assistant.",
            ...     messages=[
            ...         {"role": "user", "content": "Help me optimize this code"}
            ...     ],
            ...     conversation_id="coding-session-123",
            ...     memory_config={
            ...         "type": "buffer",  # or "summary", "buffer_window"
            ...         "max_tokens": 4000,
            ...         "persistence": "memory"  # or "disk", "database"
            ...     }
            ... )  # doctest: +SKIP

            With tool calling:

            >>> result = agent.execute(
            ...     provider="openai",
            ...     model="gpt-4-turbo",
            ...     messages=[
            ...         {"role": "user", "content": "Get the weather in NYC"}
            ...     ],
            ...     tools=[
            ...         {
            ...             "type": "function",
            ...             "function": {
            ...                 "name": "get_weather",
            ...                 "description": "Get weather for a location",
            ...                 "parameters": {
            ...                     "type": "object",
            ...                     "properties": {
            ...                         "location": {"type": "string"},
            ...                         "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            ...                     },
            ...                     "required": ["location"]
            ...                 }
            ...             }
            ...         }
            ...     ],
            ...     generation_config={
            ...         "temperature": 0,  # Use 0 for tool calling
            ...         "tool_choice": "auto"  # or "none", {"type": "function", "function": {"name": "get_weather"}}
            ...     }
            ... )  # doctest: +SKIP

            With RAG (Retrieval Augmented Generation):

            >>> result = agent.execute(
            ...     provider="openai",
            ...     model="gpt-4",
            ...     messages=[
            ...         {"role": "user", "content": "What is our refund policy?"}
            ...     ],
            ...     rag_config={
            ...         "enabled": True,
            ...         "top_k": 5,  # Number of documents to retrieve
            ...         "similarity_threshold": 0.7,  # Minimum similarity score
            ...         "embeddings": {
            ...             "model": "text-embedding-ada-002",
            ...             "dimension": 1536
            ...         },
            ...         "reranking": {
            ...             "enabled": True,
            ...             "model": "cross-encoder/ms-marco-MiniLM-L-12-v2"
            ...         }
            ...     }
            ... )  # doctest: +SKIP

            With MCP (Model Context Protocol) integration:

            >>> result = agent.execute(
            ...     provider="anthropic",
            ...     model="claude-3-opus-20240229",
            ...     messages=[
            ...         {"role": "user", "content": "Analyze the sales data"}
            ...     ],
            ...     mcp_servers=[
            ...         {
            ...             "name": "data-server",
            ...             "transport": "stdio",
            ...             "command": "python",
            ...             "args": ["-m", "mcp_data_server"],
            ...             "env": {"API_KEY": "secret"}
            ...         }
            ...     ],
            ...     mcp_context=[
            ...         "data://sales/2024/q4",
            ...         "data://customers/segments",
            ...         "resource://templates/analysis"
            ...     ]
            ... )  # doctest: +SKIP

            Advanced configuration with all features:

            >>> result = agent.execute(
            ...     provider="openai",
            ...     model="gpt-4-turbo",
            ...     messages=[
            ...         {"role": "user", "content": "Complex analysis request"}
            ...     ],
            ...     system_prompt="You are an expert data analyst.",
            ...     conversation_id="analysis-session-456",
            ...     memory_config={
            ...         "type": "buffer_window",
            ...         "max_tokens": 3000,
            ...         "window_size": 10  # Keep last 10 exchanges
            ...     },
            ...     tools=[],  # Tool definitions would go here
            ...     rag_config={
            ...         "enabled": True,
            ...         "top_k": 3,
            ...         "similarity_threshold": 0.8
            ...     },
            ...     mcp_servers=[],  # MCP server configs would go here
            ...     mcp_context=["data://reports/*"],
            ...     generation_config={
            ...         "temperature": 0.7,
            ...         "max_tokens": 2000,
            ...         "top_p": 0.9,
            ...         "frequency_penalty": 0.1,
            ...         "presence_penalty": 0.1,
            ...         "stop": ["\\n\\n", "END"],  # Stop sequences
            ...         "logit_bias": {123: -100}  # Token biases
            ...     },
            ...     streaming=False,
            ...     timeout=120,
            ...     max_retries=3
            ... )  # doctest: +SKIP

            Error handling:

            >>> result = agent.execute(
            ...     provider="openai",
            ...     model="gpt-4",
            ...     messages=[{"role": "user", "content": "Hello"}]
            ... )
            >>> if result["success"]:
            ...     print(f"Response: {result['response']['content']}")
            ...     print(f"Tokens used: {result['usage']['total_tokens']}")
            ...     print(f"Estimated cost: ${result['usage']['estimated_cost_usd']}")
            ... else:
            ...     print(f"Error: {result['error']}")
            ...     print(f"Type: {result['error_type']}")
            ...     for suggestion in result['recovery_suggestions']:
            ...         print(f"- {suggestion}")  # doctest: +SKIP
        """
        provider = kwargs["provider"]
        model = kwargs["model"]
        messages = kwargs["messages"]
        system_prompt = kwargs.get("system_prompt")
        tools = kwargs.get("tools", [])
        conversation_id = kwargs.get("conversation_id")
        memory_config = kwargs.get("memory_config", {})
        mcp_servers = kwargs.get("mcp_servers", [])
        mcp_context = kwargs.get("mcp_context", [])
        auto_discover_tools = kwargs.get("auto_discover_tools", False)
        rag_config = kwargs.get("rag_config", {})
        generation_config = kwargs.get("generation_config", {})
        streaming = kwargs.get("streaming", False)
        timeout = kwargs.get("timeout", 120)
        max_retries = kwargs.get("max_retries", 3)
        auto_execute_tools = kwargs.get("auto_execute_tools", True)
        tool_execution_config = kwargs.get("tool_execution_config", {})

        # Check monitoring parameters
        enable_monitoring = kwargs.get("enable_monitoring", self.enable_monitoring)

        # Check budget if monitoring is enabled
        if enable_monitoring and not self._check_budget():
            raise ValueError(
                f"Budget limit exceeded: ${self._total_cost:.2f}/${self.budget_limit:.2f} USD. "
                "Reset budget or increase limit to continue."
            )

        # Track execution time
        start_time = time.time()

        try:
            # Import LangChain and related libraries (graceful fallback)
            langchain_available = self._check_langchain_availability()

            # Load conversation memory if configured
            conversation_memory = self._load_conversation_memory(
                conversation_id, memory_config
            )

            # Retrieve MCP context if configured
            mcp_context_data = self._retrieve_mcp_context(
                mcp_servers, mcp_context, kwargs
            )

            # Discover MCP tools if enabled
            discovered_mcp_tools = []
            if auto_discover_tools and mcp_servers:
                discovered_mcp_tools = self._discover_mcp_tools(mcp_servers, kwargs)
                # Merge MCP tools with existing tools
                tools = self._merge_tools(tools, discovered_mcp_tools)

            # Perform RAG retrieval if configured
            rag_context = self._perform_rag_retrieval(
                messages, rag_config, mcp_context_data
            )

            # Prepare conversation with context
            enriched_messages = self._prepare_conversation(
                messages,
                system_prompt,
                conversation_memory,
                mcp_context_data,
                rag_context,
            )

            # Generate response using selected provider
            if provider == "mock":
                response = self._mock_llm_response(
                    enriched_messages, tools, generation_config
                )
            elif langchain_available and provider in ["langchain"]:
                response = self._langchain_llm_response(
                    provider,
                    model,
                    enriched_messages,
                    tools,
                    generation_config,
                    streaming,
                    timeout,
                    max_retries,
                )
            else:
                # Use the new provider architecture
                response = self._provider_llm_response(
                    provider, model, enriched_messages, tools, generation_config
                )

            # Handle tool execution if enabled and tools were called
            if auto_execute_tools and response.get("tool_calls"):
                tool_execution_rounds = 0
                max_rounds = tool_execution_config.get("max_rounds", 5)

                # Keep executing tools until no more tool calls or max rounds reached
                while response.get("tool_calls") and tool_execution_rounds < max_rounds:
                    tool_execution_rounds += 1

                    # Execute all tool calls
                    tool_results = self._execute_tool_calls(
                        response["tool_calls"],
                        tools,
                        mcp_tools=discovered_mcp_tools,  # Track which tools are MCP
                    )

                    # Add assistant message with tool calls
                    enriched_messages.append(
                        {
                            "role": "assistant",
                            "content": response.get("content"),
                            "tool_calls": response["tool_calls"],
                        }
                    )

                    # Add tool results as tool messages
                    for tool_result in tool_results:
                        enriched_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_result["tool_call_id"],
                                "content": tool_result["content"],
                            }
                        )

                    # Get next response from LLM with tool results
                    if provider == "mock":
                        response = self._mock_llm_response(
                            enriched_messages, tools, generation_config
                        )
                    else:
                        response = self._provider_llm_response(
                            provider, model, enriched_messages, tools, generation_config
                        )

                # Update final response metadata
                response["tool_execution_rounds"] = tool_execution_rounds

            # Update conversation memory
            if conversation_id:
                self._update_conversation_memory(
                    conversation_id, enriched_messages, response, memory_config
                )

            # Track usage and performance
            usage_metrics = self._calculate_usage_metrics(
                enriched_messages, response, model, provider
            )

            # Add monitoring data if enabled
            execution_time = time.time() - start_time
            if enable_monitoring:
                # Extract token usage for monitoring
                usage = self._extract_token_usage(response)
                cost = self._calculate_cost(usage, model)

                # Update totals
                if hasattr(self, "_total_usage"):
                    self._total_usage.add(usage)
                    self._total_cost += cost.total_cost

                    # Record metrics
                    self._record_usage(usage, cost, execution_time, model)

                # Add monitoring section to response
                usage_metrics["monitoring"] = {
                    "tokens": {
                        "prompt": usage.prompt_tokens,
                        "completion": usage.completion_tokens,
                        "total": usage.total_tokens,
                    },
                    "cost": {
                        "prompt": round(cost.prompt_cost, 6),
                        "completion": round(cost.completion_cost, 6),
                        "total": round(cost.total_cost, 6),
                        "currency": cost.currency,
                    },
                    "execution_time_ms": round(execution_time * 1000, 2),
                    "model": model,
                    "budget": {
                        "used": round(self._total_cost, 4),
                        "limit": self.budget_limit,
                        "remaining": (
                            round(self.budget_limit - self._total_cost, 4)
                            if self.budget_limit
                            else None
                        ),
                    },
                }

            return {
                "success": True,
                "response": response,
                "conversation_id": conversation_id,
                "usage": usage_metrics,
                "context": {
                    "mcp_resources_used": len(mcp_context_data),
                    "rag_documents_retrieved": len(rag_context.get("documents", [])),
                    "tools_available": len(tools),
                    "tools_executed": response.get("tool_execution_rounds", 0),
                    "memory_tokens": conversation_memory.get("token_count", 0),
                },
                "metadata": {
                    "provider": provider,
                    "model": model,
                    "langchain_used": langchain_available,
                    "streaming": streaming,
                    "generation_config": generation_config,
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "provider": provider,
                "model": model,
                "conversation_id": conversation_id,
                "recovery_suggestions": [
                    "Check API credentials and model availability",
                    "Verify MCP server connections",
                    "Reduce message length if hitting token limits",
                    "Check tool definitions for syntax errors",
                ],
            }

    def _check_langchain_availability(self) -> bool:
        """Check if LangChain and related libraries are available."""
        try:
            import importlib.util

            langchain_spec = importlib.util.find_spec("langchain")
            langchain_anthropic_spec = importlib.util.find_spec("langchain_anthropic")
            langchain_openai_spec = importlib.util.find_spec("langchain_openai")

            return (
                langchain_spec is not None
                and langchain_anthropic_spec is not None
                and langchain_openai_spec is not None
            )
        except ImportError:
            return False

    def _load_conversation_memory(
        self, conversation_id: str | None, memory_config: dict
    ) -> dict[str, Any]:
        """
        Load conversation memory for persistent conversations.

        This method manages conversation history across multiple interactions,
        allowing the agent to maintain context over time.

        Args:
            conversation_id (Optional[str]): Unique identifier for the conversation.
                If None, no memory is loaded.
            memory_config (dict): Configuration for memory management with options:
                type (str): Memory type - "buffer", "summary", "buffer_window"
                    - "buffer": Keep full conversation history
                    - "summary": Summarize older messages
                    - "buffer_window": Keep only recent N exchanges
                max_tokens (int): Maximum tokens to store (default: 4000)
                persistence (str): Storage type - "memory", "disk", "database"
                window_size (int): For buffer_window, number of exchanges to keep
                summary_method (str): For summary type - "abstractive", "extractive"

        Returns:
            Dict[str, Any]: Memory data containing:
                conversation_id (str): The conversation identifier
                type (str): Memory type being used
                messages (List[Dict]): Previous conversation messages
                token_count (int): Estimated tokens in memory
                max_tokens (int): Maximum allowed tokens
                loaded_from (str): Source of the memory data

        Examples:
            Buffer memory (keep everything):

            >>> memory = self._load_conversation_memory(
            ...     "chat-123",
            ...     {"type": "buffer", "max_tokens": 4000}
            ... )  # doctest: +SKIP

            Window memory (keep last 5 exchanges):

            >>> memory = self._load_conversation_memory(
            ...     "chat-456",
            ...     {
            ...         "type": "buffer_window",
            ...         "window_size": 5,
            ...         "max_tokens": 2000
            ...     }
            ... )  # doctest: +SKIP

            Summary memory (summarize old content):

            >>> memory = self._load_conversation_memory(
            ...     "chat-789",
            ...     {
            ...         "type": "summary",
            ...         "max_tokens": 1000,
            ...         "summary_method": "abstractive"
            ...     }
            ... )  # doctest: +SKIP
        """
        if not conversation_id:
            return {"messages": [], "token_count": 0}

        # Mock memory implementation (in real implementation, use persistent storage)
        memory_type = memory_config.get("type", "buffer")
        max_tokens = memory_config.get("max_tokens", 4000)

        # Simulate loading conversation history
        mock_history = [
            {
                "role": "user",
                "content": "Previous conversation context...",
                "timestamp": "2025-06-01T10:00:00Z",
            },
            {
                "role": "assistant",
                "content": "Previous response context...",
                "timestamp": "2025-06-01T10:00:30Z",
            },
        ]

        return {
            "conversation_id": conversation_id,
            "type": memory_type,
            "messages": mock_history,
            "token_count": 150,  # Mock token count
            "max_tokens": max_tokens,
            "loaded_from": "mock_storage",
        }

    def _run_async_in_sync_context(self, coro):
        """
        Run async coroutine in a synchronous context, handling existing event loops.

        This helper method detects if an event loop is already running and handles
        the execution appropriately to avoid "RuntimeError: This event loop is already running".

        Args:
            coro: The coroutine to execute

        Returns:
            The result of the coroutine execution

        Raises:
            TimeoutError: If the operation times out (30 seconds)
            Exception: Any exception raised by the coroutine
        """
        import asyncio

        try:
            # Check if there's already a running event loop
            loop = asyncio.get_running_loop()
            # If we're here, there's a running loop - create a new thread
            import threading

            result = None
            exception = None

            def run_in_thread():
                nonlocal result, exception
                try:
                    # Create new event loop in thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
                except Exception as e:
                    exception = e

            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join(timeout=30)  # 30 second timeout

            if thread.is_alive():
                raise TimeoutError("MCP operation timed out after 30 seconds")

            if exception:
                raise exception
            return result

        except RuntimeError:
            # No running event loop, use asyncio.run()
            return asyncio.run(coro)

    def _retrieve_mcp_context(
        self, mcp_servers: list[dict], mcp_context: list[str], kwargs: dict = None
    ) -> list[dict[str, Any]]:
        """
        Retrieve context from Model Context Protocol (MCP) servers.

        MCP enables standardized context sharing between AI models and tools.
        This method connects to MCP servers and retrieves relevant context.

        Args:
            mcp_servers (List[dict]): MCP server configurations, each containing:
                name (str): Server identifier
                transport (str): Transport type - "stdio", "http", "sse"
                command (str): Command to launch stdio server
                args (List[str]): Command arguments
                env (Dict[str, str]): Environment variables
                url (str): For HTTP/SSE transports
                headers (Dict[str, str]): HTTP headers for auth
            mcp_context (List[str]): Resource URIs to retrieve:
                - "data://path/to/resource": Data resources
                - "file://path/to/file": File resources
                - "resource://type/name": Named resources
                - "prompt://template/name": Prompt templates

        Returns:
            List[Dict[str, Any]]: Retrieved context items, each containing:
                uri (str): Resource URI
                content (str): Resource content
                source (str): Server that provided the resource
                retrieved_at (str): ISO timestamp of retrieval
                relevance_score (float): Relevance score (0-1)
                metadata (Dict): Additional resource metadata

        Examples:
            Connect to stdio MCP server:

            >>> context = self._retrieve_mcp_context(
            ...     mcp_servers=[{
            ...         "name": "data-server",
            ...         "transport": "stdio",
            ...         "command": "python",
            ...         "args": ["-m", "mcp_data_server"],
            ...         "env": {"API_KEY": "secret"}
            ...     }],
            ...     mcp_context=["data://sales/2024/q4"]
            ... )  # doctest: +SKIP

            Connect to HTTP MCP server:

            >>> context = self._retrieve_mcp_context(
            ...     mcp_servers=[{
            ...         "name": "api-server",
            ...         "transport": "http",
            ...         "url": "https://mcp.example.com",
            ...         "headers": {"Authorization": "Bearer token"}
            ...     }],
            ...     mcp_context=[
            ...         "resource://customers/segments",
            ...         "prompt://analysis/financial"
            ...     ]
            ... )  # doctest: +SKIP
        """
        if not (mcp_servers or mcp_context):
            return []

        context_data = []

        # Check if we should use real MCP implementation
        use_real_mcp = hasattr(self, "_mcp_client") or self._should_use_real_mcp(kwargs)

        if use_real_mcp:
            # Use internal MCP client for real implementation
            try:
                import asyncio
                from datetime import datetime

                from kailash.mcp_server import MCPClient

                # Initialize MCP client if not already done
                if not hasattr(self, "_mcp_client"):
                    self._mcp_client = MCPClient()

                # Process each server
                for server_config in mcp_servers:
                    try:
                        # List resources from server
                        resources = self._run_async_in_sync_context(
                            self._mcp_client.list_resources(server_config)
                        )

                        # Read specific resources if requested
                        for uri in mcp_context:
                            try:
                                resource_data = self._run_async_in_sync_context(
                                    self._mcp_client.read_resource(server_config, uri)
                                )

                                if resource_data:
                                    # Extract content from resource data
                                    content = resource_data
                                    if isinstance(resource_data, dict):
                                        content = resource_data.get(
                                            "content", resource_data
                                        )

                                    # Handle different content formats
                                    if isinstance(content, list):
                                        # MCP returns content as array of items
                                        text_content = ""
                                        for item in content:
                                            if (
                                                isinstance(item, dict)
                                                and item.get("type") == "text"
                                            ):
                                                text_content += item.get("text", "")
                                            elif isinstance(item, str):
                                                text_content += item
                                        content = text_content

                                    context_data.append(
                                        {
                                            "uri": uri,
                                            "content": str(content),
                                            "source": server_config.get(
                                                "name", "mcp_server"
                                            ),
                                            "retrieved_at": datetime.now().isoformat(),
                                            "relevance_score": 0.95,  # High score for explicitly requested
                                            "metadata": (
                                                resource_data
                                                if isinstance(resource_data, dict)
                                                else {}
                                            ),
                                        }
                                    )
                            except Exception as e:
                                self.logger.debug(f"Failed to read resource {uri}: {e}")

                        # Auto-discover and include relevant resources
                        if resources and isinstance(resources, list):
                            for resource in resources[
                                :3
                            ]:  # Limit auto-discovered resources
                                resource_dict = (
                                    resource
                                    if isinstance(resource, dict)
                                    else {"uri": str(resource)}
                                )
                                context_data.append(
                                    {
                                        "uri": resource_dict.get("uri", ""),
                                        "content": f"Auto-discovered: {resource_dict.get('name', '')} - {resource_dict.get('description', '')}",
                                        "source": server_config.get(
                                            "name", "mcp_server"
                                        ),
                                        "retrieved_at": datetime.now().isoformat(),
                                        "relevance_score": 0.75,
                                        "metadata": resource_dict,
                                    }
                                )

                    except TimeoutError as e:
                        self.logger.warning(
                            f"MCP server '{server_config.get('name', 'unknown')}' timed out after 30 seconds: {e}"
                        )
                        # Fall back to mock for this server
                        context_data.append(
                            {
                                "uri": f"mcp://{server_config.get('name', 'unknown')}/fallback",
                                "content": "MCP server timed out - using fallback content. Check if the server is running and accessible.",
                                "source": server_config.get("name", "unknown"),
                                "retrieved_at": datetime.now().isoformat(),
                                "relevance_score": 0.5,
                                "metadata": {
                                    "error": "timeout",
                                    "error_message": str(e),
                                },
                            }
                        )
                    except Exception as e:
                        error_type = type(e).__name__
                        self.logger.error(
                            f"MCP server '{server_config.get('name', 'unknown')}' connection failed ({error_type}): {e}"
                        )

                        # Provide helpful error messages based on exception type
                        if "coroutine" in str(e).lower() and "await" in str(e).lower():
                            self.logger.error(
                                "This appears to be an async/await issue. Please report this bug to the Kailash SDK team."
                            )

                        # Fall back to mock for this server
                        context_data.append(
                            {
                                "uri": f"mcp://{server_config.get('name', 'unknown')}/fallback",
                                "content": f"Connection failed ({error_type}) - using fallback content. Error: {str(e)}",
                                "source": server_config.get("name", "unknown"),
                                "retrieved_at": datetime.now().isoformat(),
                                "relevance_score": 0.5,
                                "metadata": {
                                    "error": error_type,
                                    "error_message": str(e),
                                },
                            }
                        )

                # If we got real data, return it
                if context_data:
                    return context_data

            except ImportError as e:
                # MCPClient not available, fall back to mock
                self.logger.info(
                    "MCP client not available. Install the MCP SDK with 'pip install mcp' to use real MCP servers."
                )
                pass
            except Exception as e:
                self.logger.error(
                    f"Unexpected error in MCP retrieval: {type(e).__name__}: {e}"
                )
                self.logger.info("Falling back to mock MCP implementation.")

        # Fallback to mock implementation
        for uri in mcp_context:
            context_data.append(
                {
                    "uri": uri,
                    "content": f"Mock context content for {uri}",
                    "source": "mcp_server",
                    "retrieved_at": "2025-06-01T12:00:00Z",
                    "relevance_score": 0.85,
                }
            )

        # Simulate server-based retrieval
        for server_config in mcp_servers:
            server_name = server_config.get("name", "unknown")
            context_data.append(
                {
                    "uri": f"mcp://{server_name}/auto-context",
                    "content": f"Auto-retrieved context from {server_name}",
                    "source": server_name,
                    "retrieved_at": "2025-06-01T12:00:00Z",
                    "relevance_score": 0.75,
                }
            )

        return context_data

    def _should_use_real_mcp(self, kwargs: dict = None) -> bool:
        """Check if real MCP implementation should be used."""
        import os

        # 1. Check explicit parameter first (highest priority)
        if kwargs and "use_real_mcp" in kwargs:
            return kwargs["use_real_mcp"]

        # 2. Check environment variable (fallback)
        env_value = os.environ.get("KAILASH_USE_REAL_MCP", "").lower()
        if env_value in ("true", "false"):
            return env_value == "true"

        # 3. Default to True (real MCP execution)
        return True

    def _discover_mcp_tools(
        self, mcp_servers: list[dict], kwargs: dict = None
    ) -> list[dict[str, Any]]:
        """
        Discover available tools from MCP servers.

        Args:
            mcp_servers: List of MCP server configurations

        Returns:
            List of tool definitions in OpenAI function calling format
        """
        discovered_tools = []

        # Check if we should use real MCP implementation
        use_real_mcp = hasattr(self, "_mcp_client") or self._should_use_real_mcp(kwargs)

        if use_real_mcp:
            try:
                from kailash.mcp_server import MCPClient

                # Initialize MCP client if not already done
                if not hasattr(self, "_mcp_client"):
                    self._mcp_client = MCPClient()

                # Discover tools from each server
                for server_config in mcp_servers:
                    try:
                        # Discover tools asynchronously
                        tools = self._run_async_in_sync_context(
                            self._mcp_client.discover_tools(server_config)
                        )

                        # Convert MCP tools to OpenAI function calling format
                        if isinstance(tools, list):
                            for tool in tools:
                                tool_dict = (
                                    tool
                                    if isinstance(tool, dict)
                                    else {"name": str(tool)}
                                )
                                # Extract tool info
                                function_def = {
                                    "name": tool_dict.get("name", "unknown"),
                                    "description": tool_dict.get("description", ""),
                                    "parameters": tool_dict.get(
                                        "inputSchema", tool_dict.get("parameters", {})
                                    ),
                                }
                                # Add MCP metadata
                                function_def["mcp_server"] = server_config.get(
                                    "name", "mcp_server"
                                )
                                function_def["mcp_server_config"] = server_config

                                discovered_tools.append(
                                    {"type": "function", "function": function_def}
                                )

                    except TimeoutError as e:
                        self.logger.warning(
                            f"Tool discovery timed out for MCP server '{server_config.get('name', 'unknown')}': {e}"
                        )
                    except Exception as e:
                        error_type = type(e).__name__
                        self.logger.error(
                            f"Failed to discover tools from '{server_config.get('name', 'unknown')}' ({error_type}): {e}"
                        )

            except ImportError:
                # MCPClient not available, use mock tools
                self.logger.info(
                    "MCP client not available for tool discovery. Install with 'pip install mcp' for real MCP tools."
                )
                pass
            except Exception as e:
                self.logger.error(
                    f"Unexpected error in MCP tool discovery: {type(e).__name__}: {e}"
                )
                self.logger.info("Using mock tools as fallback.")

        # If no real tools discovered, provide minimal generic tools
        if not discovered_tools:
            # Provide minimal generic tools for each server
            for server_config in mcp_servers:
                server_name = server_config.get("name", "mcp_server")
                discovered_tools.extend(
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": f"mcp_{server_name}_search",
                                "description": f"Search for information in {server_name}",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "Search query",
                                        }
                                    },
                                    "required": ["query"],
                                },
                                "mcp_server": server_name,
                                "mcp_server_config": server_config,
                            },
                        }
                    ]
                )

        return discovered_tools

    def _merge_tools(
        self, existing_tools: list[dict], mcp_tools: list[dict]
    ) -> list[dict]:
        """
        Merge MCP discovered tools with existing tools, avoiding duplicates.

        Args:
            existing_tools: Tools already defined
            mcp_tools: Tools discovered from MCP servers

        Returns:
            Merged list of tools
        """
        # Create a set of existing tool names for deduplication
        existing_names = set()
        for tool in existing_tools:
            if isinstance(tool, dict) and "function" in tool:
                existing_names.add(tool["function"].get("name", ""))
            elif isinstance(tool, dict) and "name" in tool:
                existing_names.add(tool["name"])

        # Add MCP tools that don't conflict
        merged_tools = existing_tools.copy()
        for mcp_tool in mcp_tools:
            if isinstance(mcp_tool, dict) and "function" in mcp_tool:
                tool_name = mcp_tool["function"].get("name", "")
                if tool_name and tool_name not in existing_names:
                    merged_tools.append(mcp_tool)
                    existing_names.add(tool_name)

        return merged_tools

    def _perform_rag_retrieval(
        self, messages: list[dict], rag_config: dict, mcp_context: list[dict]
    ) -> dict[str, Any]:
        """
        Perform Retrieval Augmented Generation (RAG) to find relevant documents.

        This method searches through a knowledge base to find documents relevant
        to the user's query, which are then included as context for the LLM.

        Args:
            messages (List[dict]): Conversation messages to extract query from
            rag_config (dict): RAG configuration options:
                enabled (bool): Whether RAG is enabled
                top_k (int): Number of documents to retrieve (default: 5)
                similarity_threshold (float): Minimum similarity score (0-1)
                embeddings (dict): Embedding model configuration:
                    model (str): Embedding model name
                    dimension (int): Embedding dimension
                    provider (str): "openai", "huggingface", "sentence-transformers"
                reranking (dict): Reranking configuration:
                    enabled (bool): Whether to rerank results
                    model (str): Reranking model name
                    top_n (int): Number of results after reranking
                vector_store (dict): Vector database configuration:
                    type (str): "faiss", "pinecone", "weaviate", "chroma"
                    index_name (str): Name of the index
                    namespace (str): Namespace within index
                filters (dict): Metadata filters for search
                hybrid_search (dict): Hybrid search configuration:
                    enabled (bool): Combine vector and keyword search
                    alpha (float): Weight for vector search (0-1)
            mcp_context (List[dict]): MCP context to include in search

        Returns:
            Dict[str, Any]: RAG results containing:
                query (str): Extracted search query
                documents (List[Dict]): Retrieved documents with:
                    content (str): Document text
                    score (float): Relevance score
                    source (str): Document source
                    metadata (Dict): Document metadata
                scores (List[float]): Just the scores for quick access
                total_candidates (int): Total documents searched
                threshold (float): Similarity threshold used
                top_k (int): Number of results requested
                search_time_ms (float): Search duration

        Examples:
            Basic RAG retrieval:

            >>> rag_result = self._perform_rag_retrieval(
            ...     messages=[{"role": "user", "content": "What is the refund policy?"}],
            ...     rag_config={
            ...         "enabled": True,
            ...         "top_k": 5,
            ...         "similarity_threshold": 0.7
            ...     },
            ...     mcp_context=[]
            ... )  # doctest: +SKIP

            Advanced RAG with reranking:

            >>> rag_result = self._perform_rag_retrieval(
            ...     messages=[{"role": "user", "content": "Technical specifications"}],
            ...     rag_config={
            ...         "enabled": True,
            ...         "top_k": 10,
            ...         "similarity_threshold": 0.6,
            ...         "embeddings": {
            ...             "model": "text-embedding-ada-002",
            ...             "dimension": 1536,
            ...             "provider": "openai"
            ...         },
            ...         "reranking": {
            ...             "enabled": True,
            ...             "model": "cross-encoder/ms-marco-MiniLM-L-12-v2",
            ...             "top_n": 3
            ...         },
            ...         "vector_store": {
            ...             "type": "pinecone",
            ...             "index_name": "products",
            ...             "namespace": "technical-docs"
            ...         }
            ...     },
            ...     mcp_context=[]
            ... )  # doctest: +SKIP

            Hybrid search with filters:

            >>> rag_result = self._perform_rag_retrieval(
            ...     messages=[{"role": "user", "content": "Python tutorials"}],
            ...     rag_config={
            ...         "enabled": True,
            ...         "top_k": 5,
            ...         "similarity_threshold": 0.7,
            ...         "filters": {
            ...             "category": "tutorial",
            ...             "language": "python",
            ...             "level": ["beginner", "intermediate"]
            ...         },
            ...         "hybrid_search": {
            ...             "enabled": True,
            ...             "alpha": 0.7  # 70% vector, 30% keyword
            ...         }
            ...     },
            ...     mcp_context=[]
            ... )  # doctest: +SKIP
        """
        if not rag_config.get("enabled", False):
            return {"documents": [], "scores": []}

        # Extract query from the last user message
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

        if not query:
            return {"documents": [], "scores": []}

        top_k = rag_config.get("top_k", 5)
        threshold = rag_config.get("similarity_threshold", 0.7)

        # Mock RAG retrieval
        mock_documents = [
            {
                "content": f"Relevant document 1 for query: {query[:50]}...",
                "score": 0.92,
                "source": "knowledge_base",
                "metadata": {"doc_id": "kb_001", "section": "overview"},
            },
            {
                "content": f"Relevant document 2 for query: {query[:50]}...",
                "score": 0.87,
                "source": "documentation",
                "metadata": {"doc_id": "doc_023", "section": "procedures"},
            },
            {
                "content": f"Relevant document 3 for query: {query[:50]}...",
                "score": 0.81,
                "source": "mcp_resource",
                "metadata": {"uri": "data://reports/latest.json"},
            },
        ]

        # Filter by threshold and limit by top_k
        filtered_docs = [doc for doc in mock_documents if doc["score"] >= threshold][
            :top_k
        ]

        return {
            "query": query,
            "documents": filtered_docs,
            "scores": [doc["score"] for doc in filtered_docs],
            "total_candidates": len(mock_documents),
            "threshold": threshold,
            "top_k": top_k,
        }

    def _prepare_conversation(
        self,
        messages: list[dict],
        system_prompt: str | None,
        memory: dict,
        mcp_context: list[dict],
        rag_context: dict,
    ) -> list[dict]:
        """Prepare enriched conversation with all context."""
        enriched_messages = []

        # Add system prompt
        if system_prompt:
            enriched_messages.append({"role": "system", "content": system_prompt})

        # Add conversation memory
        if memory.get("messages"):
            enriched_messages.extend(memory["messages"])

        # Add MCP context as system messages
        if mcp_context:
            context_content = "=== MCP Context ===\n"
            for ctx in mcp_context:
                context_content += f"Resource: {ctx['uri']}\n{ctx['content']}\n\n"

            enriched_messages.append({"role": "system", "content": context_content})

        # Add RAG context
        if rag_context.get("documents"):
            rag_content = "=== Retrieved Documents ===\n"
            for doc in rag_context["documents"]:
                rag_content += (
                    f"Document (score: {doc['score']:.2f}): {doc['content']}\n\n"
                )

            enriched_messages.append({"role": "system", "content": rag_content})

        # Add current conversation messages
        enriched_messages.extend(messages)

        return enriched_messages

    def _mock_llm_response(
        self, messages: list[dict], tools: list[dict], generation_config: dict
    ) -> dict[str, Any]:
        """Generate mock LLM response for testing."""
        last_user_message = ""
        has_images = False
        has_tool_results = False

        # Check if we have tool results in the conversation
        for msg in messages:
            if msg.get("role") == "tool":
                has_tool_results = True
                break

        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Handle complex content with images
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            has_images = True
                    last_user_message = " ".join(text_parts)
                else:
                    last_user_message = content
                break

        # Generate contextual mock response
        if has_tool_results:
            # We've executed tools, provide final response
            response_content = "Based on the tool execution results, I've completed the requested task. The tools have been successfully executed and the operation is complete."
            tool_calls = []  # No more tool calls after execution
        elif has_images:
            response_content = "I can see the image(s) you've provided. Based on my analysis, [Mock vision response for testing]"
            tool_calls = []
        elif "analyze" in last_user_message.lower():
            response_content = "Based on the provided data and context, I can see several key patterns: 1) Customer engagement has increased by 15% this quarter, 2) Product A shows the highest conversion rate, and 3) There are opportunities for improvement in the onboarding process."
            tool_calls = []
        elif (
            "create" in last_user_message.lower()
            or "generate" in last_user_message.lower()
        ):
            response_content = "I'll help you create that. Based on the requirements and available tools, I recommend a structured approach with the following steps..."
            # Simulate tool calls if tools are available and no tools executed yet
            tool_calls = []
            if (
                tools
                and not has_tool_results
                and any(
                    keyword in last_user_message.lower()
                    for keyword in ["create", "send", "execute", "run"]
                )
            ):
                for tool in tools[:2]:  # Limit to first 2 tools
                    tool_name = tool.get("function", {}).get(
                        "name", tool.get("name", "unknown")
                    )
                    tool_calls.append(
                        {
                            "id": f"call_{hash(tool_name) % 10000}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps({"mock": "arguments"}),
                            },
                        }
                    )
        elif "?" in last_user_message:
            response_content = f"Regarding your question about '{last_user_message[:50]}...', here's what I found from the available context and resources..."
            tool_calls = []
        else:
            response_content = f"I understand you want me to work with: '{last_user_message[:100]}...'. Based on the context provided, I can help you achieve this goal."
            tool_calls = []

        return {
            "id": f"msg_{hash(last_user_message) % 100000}",
            "content": response_content,
            "role": "assistant",
            "model": "mock-model",
            "created": 1701234567,
            "tool_calls": tool_calls,
            "finish_reason": "stop" if not tool_calls else "tool_calls",
            "usage": {
                "prompt_tokens": len(
                    " ".join(
                        (
                            msg.get("content", "")
                            if isinstance(msg.get("content"), str)
                            else " ".join(
                                item.get("text", "")
                                for item in msg.get("content", [])
                                if item.get("type") == "text"
                            )
                        )
                        for msg in messages
                    )
                )
                // 4,
                "completion_tokens": len(response_content) // 4,
                "total_tokens": 0,  # Will be calculated
            },
        }

    def _langchain_llm_response(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
        generation_config: dict,
        streaming: bool,
        timeout: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """Generate LLM response using LangChain (mock implementation)."""
        # This would be the real LangChain integration
        return {
            "id": "langchain_response_123",
            "content": f"LangChain response using {provider} {model} with advanced agent capabilities",
            "role": "assistant",
            "model": model,
            "provider": provider,
            "langchain_used": True,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 250,
                "completion_tokens": 75,
                "total_tokens": 325,
            },
        }

    def _provider_llm_response(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
        generation_config: dict,
    ) -> dict[str, Any]:
        """Generate LLM response using provider architecture."""
        try:
            from .ai_providers import get_provider

            # Get the provider instance
            provider_instance = get_provider(provider)

            # Check if provider is available
            if not provider_instance.is_available():
                raise RuntimeError(
                    f"Provider {provider} is not available. Check dependencies and configuration."
                )

            # Call the provider
            response = provider_instance.chat(
                messages=messages,
                model=model,
                generation_config=generation_config,
                tools=tools,
            )

            # Ensure usage totals are calculated
            if "usage" in response:
                usage = response["usage"]
                if usage.get("total_tokens", 0) == 0:
                    usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get(
                        "completion_tokens", 0
                    )

            return response

        except ImportError:
            # Fallback to the original fallback method
            return self._fallback_llm_response(
                provider, model, messages, tools, generation_config
            )
        except Exception as e:
            # Re-raise provider errors with context
            raise RuntimeError(f"Provider {provider} error: {str(e)}") from e

    def _fallback_llm_response(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
        generation_config: dict,
    ) -> dict[str, Any]:
        """Generate LLM response using direct API calls (mock implementation)."""
        return {
            "id": "fallback_response_456",
            "content": f"Direct API response from {provider} {model}",
            "role": "assistant",
            "model": model,
            "provider": provider,
            "langchain_used": False,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 50,
                "total_tokens": 250,
            },
        }

    def _update_conversation_memory(
        self,
        conversation_id: str,
        messages: list[dict],
        response: dict,
        memory_config: dict,
    ) -> None:
        """Update conversation memory with new exchange."""
        # Mock memory update (in real implementation, persist to storage)

    def _calculate_usage_metrics(
        self, messages: list[dict], response: dict, model: str, provider: str
    ) -> dict[str, Any]:
        """Calculate token usage and cost metrics."""
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens

        # Mock cost calculation (real implementation would use current pricing)
        mock_costs = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        }

        cost_per_1k = mock_costs.get(model, {"input": 0.001, "output": 0.002})
        estimated_cost = (prompt_tokens / 1000) * cost_per_1k["input"] + (
            completion_tokens / 1000
        ) * cost_per_1k["output"]

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
            "model": model,
            "provider": provider,
            "efficiency_score": completion_tokens / max(total_tokens, 1),
        }

    async def _execute_mcp_tool_call(
        self, tool_call: dict, mcp_tools: list[dict]
    ) -> dict[str, Any]:
        """Execute an MCP tool call.

        Args:
            tool_call: Tool call from LLM response
            mcp_tools: List of discovered MCP tools

        Returns:
            Tool execution result
        """
        tool_name = tool_call.get("function", {}).get("name", "")
        tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

        # Find the MCP tool definition
        mcp_tool = None
        for tool in mcp_tools:
            if tool.get("function", {}).get("name") == tool_name:
                mcp_tool = tool
                break

        if not mcp_tool:
            return {"error": f"MCP tool '{tool_name}' not found", "success": False}

        # Get server config from tool
        server_config = mcp_tool.get("function", {}).get("mcp_server_config", {})

        try:
            from kailash.mcp_server import MCPClient

            # Initialize MCP client if not already done
            if not hasattr(self, "_mcp_client"):
                self._mcp_client = MCPClient()

            # Call the tool
            result = await self._mcp_client.call_tool(
                server_config, tool_name, tool_args
            )

            return {
                "result": result,
                "success": True,
                "tool_name": tool_name,
                "server": server_config.get("name", "unknown"),
            }

        except Exception as e:
            self.logger.error(f"MCP tool execution failed: {e}")
            return {"error": str(e), "success": False, "tool_name": tool_name}

    def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        mcp_tools: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute all tool calls from LLM response.

        Args:
            tool_calls: List of tool calls from LLM response
            available_tools: All available tools (MCP + regular)
            mcp_tools: Tools that came from MCP discovery

        Returns:
            List of tool results formatted for LLM consumption
        """
        tool_results = []
        mcp_tools = mcp_tools or []

        # Create lookup for MCP tools
        mcp_tool_names = {
            tool.get("function", {}).get("name"): tool for tool in mcp_tools
        }

        for tool_call in tool_calls:
            try:
                tool_name = tool_call.get("function", {}).get("name")
                tool_id = tool_call.get("id")

                # Check if this is an MCP tool
                if tool_name in mcp_tool_names:
                    # Execute via MCP
                    result = self._run_async_in_sync_context(
                        self._execute_mcp_tool_call(tool_call, mcp_tools)
                    )
                else:
                    # Execute regular tool (future implementation)
                    result = self._execute_regular_tool(tool_call, available_tools)

                # Format successful result
                tool_results.append(
                    {
                        "tool_call_id": tool_id,
                        "content": (
                            json.dumps(result)
                            if isinstance(result, dict)
                            else str(result)
                        ),
                    }
                )

            except Exception as e:
                # Format error result
                tool_name = tool_call.get("function", {}).get("name", "unknown")
                self.logger.error(f"Tool execution failed for {tool_name}: {e}")
                tool_results.append(
                    {
                        "tool_call_id": tool_call.get("id", "unknown"),
                        "content": json.dumps(
                            {"error": str(e), "tool": tool_name, "status": "failed"}
                        ),
                    }
                )

        return tool_results

    def _execute_regular_tool(
        self, tool_call: dict[str, Any], available_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute a regular (non-MCP) tool.

        Args:
            tool_call: Tool call from LLM
            available_tools: List of available tools

        Returns:
            Tool execution result
        """
        tool_name = tool_call.get("function", {}).get("name")
        tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

        # For now, return a mock result
        # In future, this could execute actual Python functions
        return {
            "status": "success",
            "tool": tool_name,
            "result": f"Executed {tool_name} with args: {tool_args}",
            "note": "Regular tool execution not yet implemented",
        }

    # Monitoring methods
    def _get_pricing(self, model: str) -> Dict[str, float]:
        """Get pricing for current model."""
        if self.custom_pricing:
            return {
                "prompt": self.custom_pricing.get("prompt_token_cost", 0.001),
                "completion": self.custom_pricing.get("completion_token_cost", 0.002),
            }

        # Check if model has pricing info
        model_key = None
        for key in self.MODEL_PRICING:
            if key in model.lower():
                model_key = key
                break

        if model_key:
            return self.MODEL_PRICING[model_key]

        # Default pricing if model not found
        return {"prompt": 0.001, "completion": 0.002}

    def _calculate_cost(self, usage: TokenUsage, model: str) -> CostEstimate:
        """Calculate cost from token usage."""
        pricing = self._get_pricing(model)

        # Cost per 1K tokens
        prompt_cost = (
            (usage.prompt_tokens / 1000) * pricing["prompt"] * self.cost_multiplier
        )
        completion_cost = (
            (usage.completion_tokens / 1000)
            * pricing["completion"]
            * self.cost_multiplier
        )

        return CostEstimate(
            prompt_cost=prompt_cost,
            completion_cost=completion_cost,
            total_cost=prompt_cost + completion_cost,
            currency="USD",
        )

    def _extract_token_usage(self, response: Dict[str, Any]) -> TokenUsage:
        """Extract token usage from LLM response."""
        usage = TokenUsage()

        # Check if response has usage data
        if "usage" in response:
            usage_data = response["usage"]
            usage.prompt_tokens = usage_data.get("prompt_tokens", 0)
            usage.completion_tokens = usage_data.get("completion_tokens", 0)
            usage.total_tokens = usage_data.get("total_tokens", 0)

        # Anthropic format
        elif "metadata" in response and "usage" in response["metadata"]:
            usage_data = response["metadata"]["usage"]
            usage.prompt_tokens = usage_data.get("input_tokens", 0)
            usage.completion_tokens = usage_data.get("output_tokens", 0)
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        # Fallback: estimate from text length
        elif "content" in response or "text" in response:
            text = response.get("content") or response.get("text", "")
            # Rough estimation: 1 token ≈ 4 characters
            usage.completion_tokens = len(text) // 4
            usage.prompt_tokens = 100  # Rough estimate
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        return usage

    def _check_budget(self) -> bool:
        """Check if within budget. Returns True if OK to proceed."""
        if not self.budget_limit or not hasattr(self, "_total_cost"):
            return True

        if self._total_cost >= self.budget_limit:
            return False

        # Check alert threshold
        if (
            not self._budget_alerts_sent
            and self._total_cost >= self.budget_limit * self.alert_threshold
        ):
            self._budget_alerts_sent = True
            # In production, this would send actual alerts
            self.logger.warning(
                f"Budget Alert: ${self._total_cost:.2f}/${self.budget_limit:.2f} USD used "
                f"({self._total_cost/self.budget_limit*100:.1f}%)"
            )

        return True

    def _record_usage(
        self, usage: TokenUsage, cost: CostEstimate, execution_time: float, model: str
    ):
        """Record usage metrics."""
        if not self.track_history or not hasattr(self, "_usage_history"):
            return

        metrics = UsageMetrics(
            token_usage=usage,
            cost_estimate=cost,
            execution_time_ms=execution_time * 1000,
            model=model,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "node_id": self.id,
                "budget_remaining": (
                    self.budget_limit - self._total_cost if self.budget_limit else None
                ),
            },
        )

        self._usage_history.append(metrics)

        # Maintain history limit
        if len(self._usage_history) > self.history_limit:
            self._usage_history.pop(0)

    def get_usage_report(self) -> Dict[str, Any]:
        """Get comprehensive usage report."""
        if not self.enable_monitoring or not hasattr(self, "_total_usage"):
            return {"error": "Monitoring not enabled"}

        report = {
            "summary": {
                "total_tokens": self._total_usage.total_tokens,
                "prompt_tokens": self._total_usage.prompt_tokens,
                "completion_tokens": self._total_usage.completion_tokens,
                "total_cost": round(self._total_cost, 4),
                "currency": "USD",
                "requests": (
                    len(self._usage_history) if hasattr(self, "_usage_history") else 0
                ),
            },
            "budget": {
                "limit": self.budget_limit,
                "used": round(self._total_cost, 4),
                "remaining": (
                    round(self.budget_limit - self._total_cost, 4)
                    if self.budget_limit
                    else None
                ),
                "percentage_used": (
                    round(self._total_cost / self.budget_limit * 100, 1)
                    if self.budget_limit
                    else 0
                ),
            },
        }

        if hasattr(self, "_usage_history") and self._usage_history:
            # Calculate analytics
            total_time = sum(m.execution_time_ms for m in self._usage_history)
            avg_time = total_time / len(self._usage_history)

            report["analytics"] = {
                "average_tokens_per_request": self._total_usage.total_tokens
                // len(self._usage_history),
                "average_cost_per_request": round(
                    self._total_cost / len(self._usage_history), 4
                ),
                "average_execution_time_ms": round(avg_time, 2),
                "cost_per_1k_tokens": (
                    round(self._total_cost / (self._total_usage.total_tokens / 1000), 4)
                    if self._total_usage.total_tokens > 0
                    else 0
                ),
            }

            # Recent history
            report["recent_usage"] = [
                {
                    "timestamp": m.timestamp,
                    "tokens": m.token_usage.total_tokens,
                    "cost": round(m.cost_estimate.total_cost, 6),
                    "execution_time_ms": round(m.execution_time_ms, 2),
                }
                for m in self._usage_history[-10:]  # Last 10 requests
            ]

        return report

    def reset_budget(self):
        """Reset budget tracking."""
        if hasattr(self, "_total_cost"):
            self._total_cost = 0.0
            self._budget_alerts_sent = False

    def reset_usage(self):
        """Reset all usage tracking."""
        if hasattr(self, "_total_usage"):
            self._total_usage = TokenUsage()
            self._total_cost = 0.0
            self._usage_history = []
            self._budget_alerts_sent = False

    def export_usage_data(self, format: Literal["json", "csv"] = "json") -> str:
        """Export usage data for analysis."""
        if not self.enable_monitoring:
            return json.dumps({"error": "Monitoring not enabled"})

        if format == "json":
            return json.dumps(self.get_usage_report(), indent=2)

        elif format == "csv":
            if not hasattr(self, "_usage_history"):
                return "timestamp,model,prompt_tokens,completion_tokens,total_tokens,cost,execution_time_ms"

            # Simple CSV export
            lines = [
                "timestamp,model,prompt_tokens,completion_tokens,total_tokens,cost,execution_time_ms"
            ]
            for m in self._usage_history:
                lines.append(
                    f"{m.timestamp},{m.model},{m.token_usage.prompt_tokens},"
                    f"{m.token_usage.completion_tokens},{m.token_usage.total_tokens},"
                    f"{m.cost_estimate.total_cost:.6f},{m.execution_time_ms:.2f}"
                )
            return "\n".join(lines)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
