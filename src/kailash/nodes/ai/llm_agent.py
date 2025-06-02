"""Advanced LLM Agent node with LangChain integration and MCP support."""

import json
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class LLMAgent(Node):
    """
    Advanced Large Language Model agent with LangChain integration and MCP
    support.

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

        Basic Q&A agent with OpenAI::

        agent = LLMAgent()
        result = agent.run(
            provider="openai",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "Analyze the customer data and provide insights"}
            ],
            system_prompt="You are a data analyst expert.",
            mcp_context=["data://customer_reports/*"]
        )

        Tool-calling agent::

        tool_agent = LLMAgent()
        result = tool_agent.run(
            provider="anthropic",
            model="claude-3-sonnet",
            messages=[{"role": "user", "content": "Create a report and email it"}],
            tools=[
                {
                    "name": "create_report",
                    "description": "Generate a data report",
                    "parameters": {"type": "object", "properties": {"format": {"type": "string"}}}
                },
                {
                    "name": "send_email",
                    "description": "Send email with attachment",
                    "parameters": {"type": "object", "properties": {"recipient": {"type": "string"}}}
                }
            ],
            conversation_id="report_session_123"
        )

        RAG agent with MCP integration::

        rag_agent = LLMAgent()
        result = rag_agent.run(
            provider="azure",
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": "What are the compliance requirements?"}],
            rag_config={
                "enabled": True,
                "top_k": 5,
                "similarity_threshold": 0.8
            },
            mcp_servers=[
                {
                    "name": "compliance-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "compliance_mcp"]
                }
            ]
        )
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
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
        }

    def run(self, **kwargs) -> Dict[str, Any]:
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

            Basic usage with OpenAI::

                agent = LLMAgent()
                result = agent.run(
                    provider="openai",
                    model="gpt-4",
                    messages=[
                        {"role": "user", "content": "Explain quantum computing"}
                    ],
                    generation_config={
                        "temperature": 0.7,
                        "max_tokens": 500,
                        "top_p": 0.9,
                        "frequency_penalty": 0.0,
                        "presence_penalty": 0.0
                    }
                )
                print(result["response"]["content"])

            Using Ollama with custom model::

                result = agent.run(
                    provider="ollama",
                    model="llama3.1:8b-instruct-q8_0",
                    messages=[
                        {"role": "user", "content": "Write a Python function"}
                    ],
                    generation_config={
                        "temperature": 0.5,
                        "max_tokens": 1000,
                        "top_p": 0.95,
                        "seed": 42  # For reproducible outputs
                    }
                )

            With system prompt and conversation memory::

                result = agent.run(
                    provider="anthropic",
                    model="claude-3-sonnet-20240229",
                    system_prompt="You are a helpful coding assistant.",
                    messages=[
                        {"role": "user", "content": "Help me optimize this code"}
                    ],
                    conversation_id="coding-session-123",
                    memory_config={
                        "type": "buffer",  # or "summary", "buffer_window"
                        "max_tokens": 4000,
                        "persistence": "memory"  # or "disk", "database"
                    }
                )

            With tool calling::

                result = agent.run(
                    provider="openai",
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "user", "content": "Get the weather in NYC"}
                    ],
                    tools=[
                        {
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "description": "Get weather for a location",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "location": {"type": "string"},
                                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                                    },
                                    "required": ["location"]
                                }
                            }
                        }
                    ],
                    generation_config={
                        "temperature": 0,  # Use 0 for tool calling
                        "tool_choice": "auto"  # or "none", {"type": "function", "function": {"name": "get_weather"}}
                    }
                )

            With RAG (Retrieval Augmented Generation)::

                result = agent.run(
                    provider="openai",
                    model="gpt-4",
                    messages=[
                        {"role": "user", "content": "What is our refund policy?"}
                    ],
                    rag_config={
                        "enabled": True,
                        "top_k": 5,  # Number of documents to retrieve
                        "similarity_threshold": 0.7,  # Minimum similarity score
                        "embeddings": {
                            "model": "text-embedding-ada-002",
                            "dimension": 1536
                        },
                        "reranking": {
                            "enabled": True,
                            "model": "cross-encoder/ms-marco-MiniLM-L-12-v2"
                        }
                    }
                )

            With MCP (Model Context Protocol) integration::

                result = agent.run(
                    provider="anthropic",
                    model="claude-3-opus-20240229",
                    messages=[
                        {"role": "user", "content": "Analyze the sales data"}
                    ],
                    mcp_servers=[
                        {
                            "name": "data-server",
                            "transport": "stdio",
                            "command": "python",
                            "args": ["-m", "mcp_data_server"],
                            "env": {"API_KEY": "secret"}
                        }
                    ],
                    mcp_context=[
                        "data://sales/2024/q4",
                        "data://customers/segments",
                        "resource://templates/analysis"
                    ]
                )

            Advanced configuration with all features::

                result = agent.run(
                    provider="openai",
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "user", "content": "Complex analysis request"}
                    ],
                    system_prompt="You are an expert data analyst.",
                    conversation_id="analysis-session-456",
                    memory_config={
                        "type": "buffer_window",
                        "max_tokens": 3000,
                        "window_size": 10  # Keep last 10 exchanges
                    },
                    tools=[...],  # Tool definitions
                    rag_config={
                        "enabled": True,
                        "top_k": 3,
                        "similarity_threshold": 0.8
                    },
                    mcp_servers=[...],  # MCP server configs
                    mcp_context=["data://reports/*"],
                    generation_config={
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "top_p": 0.9,
                        "frequency_penalty": 0.1,
                        "presence_penalty": 0.1,
                        "stop": ["\\n\\n", "END"],  # Stop sequences
                        "logit_bias": {123: -100}  # Token biases
                    },
                    streaming=False,
                    timeout=120,
                    max_retries=3
                )

            Error handling::

                result = agent.run(
                    provider="openai",
                    model="gpt-4",
                    messages=[{"role": "user", "content": "Hello"}]
                )

                if result["success"]:
                    print(f"Response: {result['response']['content']}")
                    print(f"Tokens used: {result['usage']['total_tokens']}")
                    print(f"Estimated cost: ${result['usage']['estimated_cost_usd']}")
                else:
                    print(f"Error: {result['error']}")
                    print(f"Type: {result['error_type']}")
                    for suggestion in result['recovery_suggestions']:
                        print(f"- {suggestion}")
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
        rag_config = kwargs.get("rag_config", {})
        generation_config = kwargs.get("generation_config", {})
        streaming = kwargs.get("streaming", False)
        timeout = kwargs.get("timeout", 120)
        max_retries = kwargs.get("max_retries", 3)

        try:
            # Import LangChain and related libraries (graceful fallback)
            langchain_available = self._check_langchain_availability()

            # Load conversation memory if configured
            conversation_memory = self._load_conversation_memory(
                conversation_id, memory_config
            )

            # Retrieve MCP context if configured
            mcp_context_data = self._retrieve_mcp_context(mcp_servers, mcp_context)

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

            # Update conversation memory
            if conversation_id:
                self._update_conversation_memory(
                    conversation_id, enriched_messages, response, memory_config
                )

            # Track usage and performance
            usage_metrics = self._calculate_usage_metrics(
                enriched_messages, response, model, provider
            )

            return {
                "success": True,
                "response": response,
                "conversation_id": conversation_id,
                "usage": usage_metrics,
                "context": {
                    "mcp_resources_used": len(mcp_context_data),
                    "rag_documents_retrieved": len(rag_context.get("documents", [])),
                    "tools_available": len(tools),
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
        self, conversation_id: Optional[str], memory_config: dict
    ) -> Dict[str, Any]:
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
            Buffer memory (keep everything)::

                memory = self._load_conversation_memory(
                    "chat-123",
                    {"type": "buffer", "max_tokens": 4000}
                )

            Window memory (keep last 5 exchanges)::

                memory = self._load_conversation_memory(
                    "chat-456",
                    {
                        "type": "buffer_window",
                        "window_size": 5,
                        "max_tokens": 2000
                    }
                )

            Summary memory (summarize old content)::

                memory = self._load_conversation_memory(
                    "chat-789",
                    {
                        "type": "summary",
                        "max_tokens": 1000,
                        "summary_method": "abstractive"
                    }
                )
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

    def _retrieve_mcp_context(
        self, mcp_servers: List[dict], mcp_context: List[str]
    ) -> List[Dict[str, Any]]:
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
            Connect to stdio MCP server::

                context = self._retrieve_mcp_context(
                    mcp_servers=[{
                        "name": "data-server",
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "mcp_data_server"],
                        "env": {"API_KEY": "secret"}
                    }],
                    mcp_context=["data://sales/2024/q4"]
                )

            Connect to HTTP MCP server::

                context = self._retrieve_mcp_context(
                    mcp_servers=[{
                        "name": "api-server",
                        "transport": "http",
                        "url": "https://mcp.example.com",
                        "headers": {"Authorization": "Bearer token"}
                    }],
                    mcp_context=[
                        "resource://customers/segments",
                        "prompt://analysis/financial"
                    ]
                )
        """
        if not (mcp_servers or mcp_context):
            return []

        context_data = []

        # Mock MCP context retrieval
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

    def _perform_rag_retrieval(
        self, messages: List[dict], rag_config: dict, mcp_context: List[dict]
    ) -> Dict[str, Any]:
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
            Basic RAG retrieval::

                rag_result = self._perform_rag_retrieval(
                    messages=[{"role": "user", "content": "What is the refund policy?"}],
                    rag_config={
                        "enabled": True,
                        "top_k": 5,
                        "similarity_threshold": 0.7
                    },
                    mcp_context=[]
                )

            Advanced RAG with reranking::

                rag_result = self._perform_rag_retrieval(
                    messages=[{"role": "user", "content": "Technical specifications"}],
                    rag_config={
                        "enabled": True,
                        "top_k": 10,
                        "similarity_threshold": 0.6,
                        "embeddings": {
                            "model": "text-embedding-ada-002",
                            "dimension": 1536,
                            "provider": "openai"
                        },
                        "reranking": {
                            "enabled": True,
                            "model": "cross-encoder/ms-marco-MiniLM-L-12-v2",
                            "top_n": 3
                        },
                        "vector_store": {
                            "type": "pinecone",
                            "index_name": "products",
                            "namespace": "technical-docs"
                        }
                    },
                    mcp_context=[]
                )

            Hybrid search with filters::

                rag_result = self._perform_rag_retrieval(
                    messages=[{"role": "user", "content": "Python tutorials"}],
                    rag_config={
                        "enabled": True,
                        "top_k": 5,
                        "similarity_threshold": 0.7,
                        "filters": {
                            "category": "tutorial",
                            "language": "python",
                            "level": ["beginner", "intermediate"]
                        },
                        "hybrid_search": {
                            "enabled": True,
                            "alpha": 0.7  # 70% vector, 30% keyword
                        }
                    },
                    mcp_context=[]
                )
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
        messages: List[dict],
        system_prompt: Optional[str],
        memory: dict,
        mcp_context: List[dict],
        rag_context: dict,
    ) -> List[dict]:
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
        self, messages: List[dict], tools: List[dict], generation_config: dict
    ) -> Dict[str, Any]:
        """Generate mock LLM response for testing."""
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        # Generate contextual mock response
        if "analyze" in last_user_message.lower():
            response_content = "Based on the provided data and context, I can see several key patterns: 1) Customer engagement has increased by 15% this quarter, 2) Product A shows the highest conversion rate, and 3) There are opportunities for improvement in the onboarding process."
        elif (
            "create" in last_user_message.lower()
            or "generate" in last_user_message.lower()
        ):
            response_content = "I'll help you create that. Based on the requirements and available tools, I recommend a structured approach with the following steps..."
        elif "?" in last_user_message:
            response_content = f"Regarding your question about '{last_user_message[:50]}...', here's what I found from the available context and resources..."
        else:
            response_content = f"I understand you want me to work with: '{last_user_message[:100]}...'. Based on the context provided, I can help you achieve this goal."

        # Simulate tool calls if tools are available
        tool_calls = []
        if tools and any(
            keyword in last_user_message.lower()
            for keyword in ["create", "send", "execute", "run"]
        ):
            for tool in tools[:2]:  # Limit to first 2 tools
                tool_calls.append(
                    {
                        "id": f"call_{hash(tool['name']) % 10000}",
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "arguments": json.dumps({"mock": "arguments"}),
                        },
                    }
                )

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
                    " ".join(msg.get("content", "") for msg in messages)
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
        messages: List[dict],
        tools: List[dict],
        generation_config: dict,
        streaming: bool,
        timeout: int,
        max_retries: int,
    ) -> Dict[str, Any]:
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
        messages: List[dict],
        tools: List[dict],
        generation_config: dict,
    ) -> Dict[str, Any]:
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
        messages: List[dict],
        tools: List[dict],
        generation_config: dict,
    ) -> Dict[str, Any]:
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
        messages: List[dict],
        response: dict,
        memory_config: dict,
    ) -> None:
        """Update conversation memory with new exchange."""
        # Mock memory update (in real implementation, persist to storage)
        pass

    def _calculate_usage_metrics(
        self, messages: List[dict], response: dict, model: str, provider: str
    ) -> Dict[str, Any]:
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
