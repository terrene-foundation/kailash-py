"""
AI Chat Integration for Kailash Middleware

Provides AI-powered chat interface for natural language workflow generation,
assistance, and guidance using existing Kailash LLM capabilities.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from ...nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from ...nodes.data import AsyncSQLDatabaseNode
from ...nodes.security import CredentialManagerNode
from ...nodes.transform import DataTransformer
from ...workflow.builder import WorkflowBuilder
from ..core.agent_ui import AgentUIMiddleware
from ..core.schema import DynamicSchemaRegistry

logger = logging.getLogger(__name__)


class ChatMessage:
    """Represents a chat message in the conversation."""

    def __init__(
        self,
        content: str,
        role: str = "user",
        message_id: str = None,
        timestamp: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        self.message_id = message_id or str(uuid.uuid4())
        self.content = content
        self.role = role  # user, assistant, system
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class ChatSession:
    """Manages a chat conversation for workflow assistance."""

    def __init__(self, session_id: str, user_id: str = None):
        self.session_id = session_id
        self.user_id = user_id
        self.messages: List[ChatMessage] = []
        self.context: Dict[str, Any] = {}
        self.created_at = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)

        # Initialize with system message
        system_msg = ChatMessage(
            content=self._get_system_prompt(),
            role="system",
            metadata={"type": "system_initialization"},
        )
        self.messages.append(system_msg)

    def add_message(
        self, content: str, role: str = "user", metadata: Dict[str, Any] = None
    ) -> str:
        """Add a message to the conversation."""
        message = ChatMessage(content, role, metadata=metadata)
        self.messages.append(message)
        self.last_activity = datetime.now(timezone.utc)
        return message.message_id

    def get_conversation_history(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get conversation history as list of dictionaries."""
        messages = self.messages[-limit:] if limit else self.messages
        return [msg.to_dict() for msg in messages]

    def update_context(self, key: str, value: Any):
        """Update conversation context."""
        self.context[key] = value
        self.last_activity = datetime.now(timezone.utc)

    def _get_system_prompt(self) -> str:
        """Get system prompt for workflow assistance."""
        return """You are an AI assistant specialized in helping users create and manage Kailash workflows.

Your capabilities include:
- Creating workflows from natural language descriptions
- Suggesting appropriate nodes for specific tasks
- Explaining workflow concepts and best practices
- Debugging workflow issues
- Optimizing workflow performance

You have access to a comprehensive node library including:
- AI nodes (LLM agents, embedding generators, A2A agents)
- Data nodes (CSV readers, SQL databases, directory readers)
- Transform nodes (filters, processors, chunkers)
- Logic nodes (switches, merges, conditionals)
- API nodes (HTTP requests, REST clients, GraphQL)

When creating workflows, always:
1. Ask clarifying questions if the requirements are unclear
2. Suggest the most appropriate nodes for the task
3. Explain the workflow structure and data flow
4. Provide configuration guidance
5. Mention any potential limitations or considerations

Be concise but thorough, and always prioritize creating working, efficient workflows."""


class WorkflowGenerator:
    """Generates workflows from natural language descriptions."""

    def __init__(self, schema_registry: DynamicSchemaRegistry):
        self.schema_registry = schema_registry
        self.llm_node = None
        self._initialize_llm()

    def _initialize_llm(self):
        """Initialize LLM node for workflow generation."""
        try:
            self.llm_node = LLMAgentNode(
                name="workflow_generator",
                provider="ollama",  # Default to Ollama
                model="llama3.2:3b",
                temperature=0.3,  # Lower temperature for more consistent results
            )
        except Exception as e:
            logger.warning(f"Could not initialize LLM node: {e}")

    async def generate_workflow_from_description(
        self, description: str, context: Dict[str, Any] = None
    ) -> Tuple[Dict[str, Any], str]:
        """
        Generate workflow configuration from natural language description.

        Returns:
            Tuple of (workflow_config, explanation)
        """
        if not self.llm_node:
            return self._fallback_workflow_generation(description)

        try:
            # Get available nodes for context
            available_nodes = await self._get_available_nodes_summary()

            # Create prompt for workflow generation
            prompt = self._create_workflow_generation_prompt(
                description, available_nodes, context
            )

            # Generate workflow using LLM
            response = await self._call_llm(prompt)

            # Parse response to extract workflow config
            workflow_config, explanation = self._parse_workflow_response(response)

            # Validate and enhance the configuration
            workflow_config = await self._validate_and_enhance_config(workflow_config)

            return workflow_config, explanation

        except Exception as e:
            logger.error(f"Error generating workflow: {e}")
            return self._fallback_workflow_generation(description)

    async def suggest_nodes_for_task(
        self, task_description: str
    ) -> List[Dict[str, Any]]:
        """Suggest appropriate nodes for a specific task."""
        try:
            # Hardcoded common nodes for now - in production this would query node registry
            available_nodes = {
                "CSVReaderNode": {"description": "Read CSV files", "category": "data"},
                "JSONReaderNode": {
                    "description": "Read JSON files",
                    "category": "data",
                },
                "HTTPRequestNode": {
                    "description": "Make HTTP API requests",
                    "category": "api",
                },
                "LLMAgentNode": {"description": "Run LLM inference", "category": "ai"},
                "PythonCodeNode": {
                    "description": "Execute Python code",
                    "category": "code",
                },
                "DataTransformer": {
                    "description": "Transform data",
                    "category": "transform",
                },
                "SwitchNode": {
                    "description": "Conditional routing",
                    "category": "logic",
                },
                "AsyncSQLDatabaseNode": {
                    "description": "Database operations",
                    "category": "data",
                },
            }

            suggestions = []
            task_lower = task_description.lower()

            for node_name, node_info in available_nodes.items():
                description = node_info["description"].lower()

                # Calculate relevance score
                relevance = self._calculate_relevance(
                    task_lower, description, node_name.lower()
                )

                if relevance > 0.3:  # Threshold for relevance
                    suggestions.append(
                        {
                            "node_type": node_name,
                            "description": node_info["description"],
                            "category": node_info["category"],
                            "relevance": relevance,
                            "schema": node_info,
                        }
                    )

            # Sort by relevance
            suggestions.sort(key=lambda x: x["relevance"], reverse=True)
            return suggestions[:10]  # Return top 10 suggestions

        except Exception as e:
            logger.error(f"Error suggesting nodes: {e}")
            return []

    def _calculate_relevance(
        self, task: str, description: str, node_name: str
    ) -> float:
        """Calculate relevance score between task and node."""
        relevance = 0.0

        # Direct keyword matches
        task_words = set(task.split())
        desc_words = set(description.split())
        name_words = set(node_name.split("_"))

        # Exact matches get high scores
        common_words = task_words.intersection(desc_words.union(name_words))
        relevance += len(common_words) * 0.3

        # Category-based matching
        category_keywords = {
            "data": [
                "read",
                "load",
                "import",
                "data",
                "file",
                "csv",
                "json",
                "database",
            ],
            "ai": [
                "llm",
                "ai",
                "generate",
                "analyze",
                "understand",
                "chat",
                "language",
            ],
            "transform": [
                "process",
                "transform",
                "filter",
                "clean",
                "modify",
                "convert",
            ],
            "api": ["api", "http", "request", "fetch", "call", "rest", "graphql"],
            "logic": ["if", "then", "condition", "switch", "route", "decide", "logic"],
        }

        for category, keywords in category_keywords.items():
            if category in node_name.lower():
                matches = len(task_words.intersection(set(keywords)))
                relevance += matches * 0.2

        return min(relevance, 1.0)  # Cap at 1.0

    async def _get_available_nodes_summary(self) -> str:
        """Get a summary of available nodes for LLM context."""
        try:
            # Hardcoded for now - in production would query node registry
            summary_parts = [
                "Data: CSVReaderNode, JSONReaderNode, AsyncSQLDatabaseNode",
                "AI: LLMAgentNode, EmbeddingGeneratorNode",
                "API: HTTPRequestNode, RESTClientNode",
                "Transform: DataTransformer, FilterNode",
                "Logic: SwitchNode, MergeNode",
                "Code: PythonCodeNode",
            ]

            return "\n".join(summary_parts)

        except Exception as e:
            logger.error(f"Error getting nodes summary: {e}")
            return "Node information not available"

    def _create_workflow_generation_prompt(
        self, description: str, available_nodes: str, context: Dict[str, Any] = None
    ) -> str:
        """Create prompt for workflow generation."""
        prompt = f"""Create a Kailash workflow configuration for the following requirement:

REQUIREMENT: {description}

AVAILABLE NODES:
{available_nodes}

Please respond with a JSON configuration that includes:
1. workflow metadata (name, description)
2. nodes array with type, id, and parameters
3. connections array linking nodes together
4. a brief explanation of the workflow

Format your response as:
```json
{{
  "metadata": {{
    "name": "workflow_name",
    "description": "Brief description"
  }},
  "nodes": [
    {{
      "id": "node1",
      "type": "NodeType",
      "parameters": {{}}
    }}
  ],
  "connections": [
    {{
      "source": "node1",
      "target": "node2",
      "source_output": "output",
      "target_input": "input"
    }}
  ]
}}
```

EXPLANATION:
[Brief explanation of the workflow and its components]
"""

        if context:
            prompt += f"\n\nADDITIONAL CONTEXT:\n{json.dumps(context, indent=2)}"

        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with the given prompt."""
        if not self.llm_node:
            raise Exception("LLM node not available")

        try:
            result = await asyncio.to_thread(
                self.llm_node.execute, messages=[{"role": "user", "content": prompt}]
            )

            # Extract content from response
            if isinstance(result, dict) and "choices" in result:
                return result["choices"][0]["message"]["content"]
            else:
                return str(result)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_workflow_response(self, response: str) -> Tuple[Dict[str, Any], str]:
        """Parse LLM response to extract workflow config and explanation."""
        try:
            # Extract JSON from response
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON configuration found in response")

            json_str = json_match.group(1)
            workflow_config = json.loads(json_str)

            # Extract explanation
            explanation_match = re.search(
                r"EXPLANATION:\s*(.*?)(?:\n\n|$)", response, re.DOTALL
            )
            explanation = (
                explanation_match.group(1).strip()
                if explanation_match
                else "Workflow generated successfully"
            )

            return workflow_config, explanation

        except Exception as e:
            logger.error(f"Error parsing workflow response: {e}")
            raise ValueError(f"Failed to parse workflow configuration: {e}")

    async def _validate_and_enhance_config(
        self, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and enhance workflow configuration."""
        try:
            # Ensure required fields exist
            if "metadata" not in config:
                config["metadata"] = {}
            if "nodes" not in config:
                config["nodes"] = []
            if "connections" not in config:
                config["connections"] = []

            # Validate node types (simplified for now)
            valid_node_types = {
                "CSVReaderNode",
                "JSONReaderNode",
                "HTTPRequestNode",
                "LLMAgentNode",
                "PythonCodeNode",
                "DataTransformer",
                "SwitchNode",
                "AsyncSQLDatabaseNode",
            }
            for node in config["nodes"]:
                if node.get("type") not in valid_node_types:
                    logger.warning(f"Unknown node type: {node.get('type')}")
                    # Could suggest alternative or use PythonCodeNode as fallback

            # Ensure unique node IDs
            node_ids = [node.get("id") for node in config["nodes"]]
            if len(set(node_ids)) != len(node_ids):
                # Make IDs unique
                for i, node in enumerate(config["nodes"]):
                    if not node.get("id"):
                        node["id"] = f"node_{i+1}"

            return config

        except Exception as e:
            logger.error(f"Error validating workflow config: {e}")
            return config

    def _fallback_workflow_generation(
        self, description: str
    ) -> Tuple[Dict[str, Any], str]:
        """Fallback workflow generation when LLM is not available."""
        # Create a simple workflow with PythonCodeNode
        workflow_config = {
            "metadata": {
                "name": "simple_workflow",
                "description": f"Generated workflow for: {description}",
            },
            "nodes": [
                {
                    "id": "input_node",
                    "type": "PythonCodeNode",
                    "parameters": {
                        "code": "# Process input data\nresult = {'message': 'Workflow created successfully'}\nreturn {'result': result}"
                    },
                }
            ],
            "connections": [],
        }

        explanation = (
            "Created a simple workflow with a Python code node. "
            "For more sophisticated workflows, please configure an LLM provider."
        )

        return workflow_config, explanation


class AIChatMiddleware:
    """
    AI Chat middleware for natural language workflow assistance.

    Enhanced with SDK components:
    - Vector database for semantic search of chat history
    - Embedding generation for conversation similarity
    - Audit logging for all chat interactions
    - Data transformation for message formatting

    Provides:
    - Natural language workflow generation
    - Interactive workflow assistance
    - Node suggestions and recommendations
    - Workflow optimization guidance
    - Debug and troubleshooting help
    - Semantic search of past conversations
    """

    def __init__(
        self,
        agent_ui_middleware: AgentUIMiddleware,
        vector_db_url: str = None,
        enable_semantic_search: bool = True,
    ):
        self.agent_ui = agent_ui_middleware
        self.schema_registry = DynamicSchemaRegistry()
        self.workflow_generator = WorkflowGenerator(self.schema_registry)
        self.enable_semantic_search = (
            enable_semantic_search and vector_db_url is not None
        )

        # Chat sessions (kept for quick access)
        self.chat_sessions: Dict[str, ChatSession] = {}

        # Initialize SDK nodes
        self._initialize_sdk_nodes(vector_db_url)

        # Performance tracking
        self.conversations_started = 0
        self.workflows_generated = 0
        self.suggestions_provided = 0
        self.embeddings_generated = 0

    def _initialize_sdk_nodes(self, vector_db_url: str = None):
        """Initialize SDK nodes for enhanced chat functionality."""

        # Embedding generator for semantic search
        if self.enable_semantic_search:
            self.embedding_node = EmbeddingGeneratorNode(
                name="chat_embedder",
                provider="sentence-transformers",
                model="all-MiniLM-L6-v2",
            )

            # Vector database for chat history (using SQL database for now)
            self.vector_db = AsyncSQLDatabaseNode(
                name="chat_vector_store", connection_string=vector_db_url, pool_size=5
            )

        # Credential management for chat features
        self.credential_node = CredentialManagerNode(
            name="chat_credentials",
            credential_name="chat_config",
            credential_type="custom",
        )

        # Data transformer for message formatting
        self.message_transformer = DataTransformer(
            name="chat_message_transformer",
            transformations=[
                {"type": "validate", "schema": "chat_message"},
                {"type": "add_field", "field": "processed_at", "value": "now()"},
            ],
        )

    async def start_chat_session(self, session_id: str, user_id: str = None) -> str:
        """Start a new chat session."""
        chat_session = ChatSession(session_id, user_id)
        self.chat_sessions[session_id] = chat_session
        self.conversations_started += 1

        logger.info(f"Started chat session {session_id} for user {user_id}")
        return session_id

    async def send_message(
        self, session_id: str, content: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send message and get AI response, storing in vector database."""
        chat_session = self.chat_sessions.get(session_id)
        if not chat_session:
            raise ValueError(f"Chat session {session_id} not found")

        # Add user message to session
        user_message_id = chat_session.add_message(content, "user")

        # Store user message in vector database if enabled
        if self.enable_semantic_search:
            await self._store_message_with_embedding(
                session_id, user_message_id, content, "user", chat_session.user_id
            )

        # Log user message
        logger.info(
            f"Chat message received: session={session_id}, user={chat_session.user_id}, length={len(content)}"
        )

        # Update context if provided
        if context:
            for key, value in context.items():
                chat_session.update_context(key, value)

        # Find similar past conversations if semantic search is enabled
        similar_conversations = []
        if self.enable_semantic_search:
            similar_conversations = await self._find_similar_conversations(
                content, limit=3
            )

        # Determine intent and generate response
        intent, confidence = await self._analyze_intent(content)

        response_content = ""
        workflow_config = None
        suggestions = []

        if intent == "generate_workflow" and confidence > 0.7:
            # Generate workflow
            try:
                # Include similar conversations as context
                enhanced_context = {
                    **chat_session.context,
                    "similar_conversations": similar_conversations,
                }

                workflow_config, explanation = (
                    await self.workflow_generator.generate_workflow_from_description(
                        content, enhanced_context
                    )
                )

                response_content = f"I've created a workflow for you. {explanation}"
                self.workflows_generated += 1

                # Log workflow generation
                logger.info(
                    f"Workflow generated: session={session_id}, name={workflow_config.get('metadata', {}).get('name', 'unnamed')}"
                )

            except Exception as e:
                response_content = f"I had trouble generating the workflow: {str(e)}. Could you provide more details about what you want to accomplish?"

        elif intent == "suggest_nodes" and confidence > 0.6:
            # Suggest nodes
            try:
                suggestions = await self.workflow_generator.suggest_nodes_for_task(
                    content
                )

                if suggestions:
                    response_content = (
                        "Based on your request, I recommend these nodes:\n\n"
                    )
                    for i, suggestion in enumerate(suggestions[:5], 1):
                        response_content += f"{i}. **{suggestion['node_type']}** - {suggestion['description']}\n"

                    self.suggestions_provided += 1

                    # Log suggestions
                    logger.info(
                        f"Nodes suggested: session={session_id}, count={len(suggestions)}, top={suggestions[0]['node_type'] if suggestions else None}"
                    )
                else:
                    response_content = "I couldn't find specific node recommendations. Could you describe your task in more detail?"

            except Exception as e:
                response_content = f"I had trouble finding node suggestions: {str(e)}"

        elif intent == "explain_concept":
            # Explain Kailash concepts
            response_content = await self._explain_concept(content)

        elif intent == "help_debug":
            # Help with debugging
            response_content = await self._help_debug(content, chat_session.context)

        else:
            # General assistance
            response_content = await self._provide_general_assistance(
                content, chat_session.context
            )

        # Add assistant response to session
        assistant_message_id = chat_session.add_message(
            response_content,
            "assistant",
            metadata={
                "intent": intent,
                "confidence": confidence,
                "has_workflow": workflow_config is not None,
                "suggestion_count": len(suggestions),
            },
        )

        # Store assistant response in vector database if enabled
        if self.enable_semantic_search:
            await self._store_message_with_embedding(
                session_id,
                assistant_message_id,
                response_content,
                "assistant",
                chat_session.user_id,
            )

        # Log assistant response
        logger.info(
            f"Chat response sent: session={session_id}, intent={intent}, confidence={confidence}, length={len(response_content)}"
        )

        return {
            "message": response_content,
            "intent": intent,
            "confidence": confidence,
            "workflow_config": workflow_config,
            "suggestions": suggestions,
            "session_id": session_id,
            "similar_conversations": len(similar_conversations),
        }

    async def _analyze_intent(self, content: str) -> Tuple[str, float]:
        """Analyze user message to determine intent."""
        content_lower = content.lower()

        # Workflow generation keywords
        generate_keywords = [
            "create",
            "build",
            "make",
            "generate",
            "workflow",
            "pipeline",
            "automate",
            "process",
            "chain",
            "flow",
        ]

        # Node suggestion keywords
        suggest_keywords = [
            "recommend",
            "suggest",
            "what node",
            "which node",
            "best node",
            "how to",
            "node for",
        ]

        # Explanation keywords
        explain_keywords = [
            "what is",
            "explain",
            "how does",
            "understand",
            "concept",
            "definition",
            "meaning",
        ]

        # Debug keywords
        debug_keywords = [
            "error",
            "problem",
            "issue",
            "debug",
            "troubleshoot",
            "fix",
            "not working",
            "failed",
        ]

        # Calculate scores
        generate_score = sum(
            1 for keyword in generate_keywords if keyword in content_lower
        )
        suggest_score = sum(
            1 for keyword in suggest_keywords if keyword in content_lower
        )
        explain_score = sum(
            1 for keyword in explain_keywords if keyword in content_lower
        )
        debug_score = sum(1 for keyword in debug_keywords if keyword in content_lower)

        # Determine intent
        scores = {
            "generate_workflow": generate_score / len(generate_keywords),
            "suggest_nodes": suggest_score / len(suggest_keywords),
            "explain_concept": explain_score / len(explain_keywords),
            "help_debug": debug_score / len(debug_keywords),
        }

        intent = max(scores.items(), key=lambda x: x[1])
        return intent[0], min(intent[1] * 2, 1.0)  # Scale confidence

    async def _explain_concept(self, content: str) -> str:
        """Provide explanations for Kailash concepts."""
        concepts = {
            "workflow": "A workflow in Kailash is a directed graph of interconnected nodes that process data. Each node performs a specific task, and connections define how data flows between nodes.",
            "node": "A node is a single processing unit in a workflow. Nodes can read data, transform it, call APIs, run AI models, or perform logic operations.",
            "connection": "Connections link nodes together, defining how output from one node becomes input to another. You can map specific outputs to specific inputs.",
            "session": "A session represents a frontend client's interaction with the Kailash middleware. Sessions can contain multiple workflows and executions.",
            "execution": "An execution is a single run of a workflow with specific input parameters. You can track progress and get real-time updates.",
            "schema": "Schemas define the structure and parameters of nodes, enabling dynamic UI generation and validation.",
        }

        content_lower = content.lower()
        for concept, explanation in concepts.items():
            if concept in content_lower:
                return f"**{concept.title()}**: {explanation}"

        return "I can explain concepts like workflows, nodes, connections, sessions, executions, and schemas. What would you like to know more about?"

    async def _help_debug(self, content: str, context: Dict[str, Any]) -> str:
        """Provide debugging assistance."""
        common_issues = {
            "connection": "Check that node IDs match exactly in your connections. Ensure source_output and target_input names are correct.",
            "parameter": "Verify that all required parameters are provided and have the correct types. Check the node schema for requirements.",
            "execution": "Look at the execution status and error messages. Common issues include missing inputs or incorrect parameter values.",
            "timeout": "Some operations may take time. Check if your workflow is still running or if there are performance bottlenecks.",
        }

        content_lower = content.lower()
        for issue_type, suggestion in common_issues.items():
            if issue_type in content_lower:
                return f"**{issue_type.title()} Issue**: {suggestion}"

        return "I can help debug common issues with connections, parameters, executions, and timeouts. Can you describe the specific problem you're experiencing?"

    async def _provide_general_assistance(
        self, content: str, context: Dict[str, Any]
    ) -> str:
        """Provide general assistance and guidance."""
        return """I'm here to help you with Kailash workflows! I can:

• **Create workflows** from natural language descriptions
• **Suggest nodes** for specific tasks
• **Explain concepts** and best practices
• **Debug issues** and troubleshoot problems
• **Optimize workflows** for better performance

What would you like to work on? Just describe what you want to accomplish and I'll help you build it!"""

    async def _store_message_with_embedding(
        self,
        session_id: str,
        message_id: str,
        content: str,
        role: str,
        user_id: str = None,
    ):
        """Store chat message with embedding in vector database."""
        try:
            # Generate embedding
            embedding_result = self.embedding_node.execute(text=content)

            # Store in database (simplified for now)
            self.vector_db.execute(
                {
                    "query": "INSERT INTO chat_messages (id, session_id, user_id, content, role, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    "parameters": [
                        message_id,
                        session_id,
                        user_id,
                        content,
                        role,
                        datetime.now(timezone.utc),
                    ],
                }
            )

            self.embeddings_generated += 1

        except Exception as e:
            logger.error(f"Failed to store message with embedding: {e}")

    async def _find_similar_conversations(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar past conversations using vector search."""
        try:
            # Generate query embedding
            query_embedding = self.embedding_node.execute(text=query)

            # Search for similar messages (simplified for now)
            search_result = self.vector_db.execute(
                {
                    "query": "SELECT * FROM chat_messages WHERE role = 'user' ORDER BY timestamp DESC LIMIT ?",
                    "parameters": [limit * 2],
                }
            )

            # Group by session and return unique conversations
            seen_sessions = set()
            similar_conversations = []

            for row in search_result.get("rows", []):
                session_id = row["session_id"]
                if session_id not in seen_sessions:
                    seen_sessions.add(session_id)
                    similar_conversations.append(
                        {
                            "session_id": session_id,
                            "content": row["content"],
                            "similarity": 0.8,  # Simplified similarity
                            "timestamp": row["timestamp"],
                        }
                    )

                if len(similar_conversations) >= limit:
                    break

            return similar_conversations

        except Exception as e:
            logger.error(f"Failed to find similar conversations: {e}")
            return []

    def get_chat_history(
        self, session_id: str, limit: int = None
    ) -> List[Dict[str, Any]]:
        """Get chat history for a session."""
        chat_session = self.chat_sessions.get(session_id)
        if not chat_session:
            return []

        return chat_session.get_conversation_history(limit)

    async def search_chat_history(
        self, query: str, user_id: str = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search chat history using semantic search."""
        if not self.enable_semantic_search:
            return []

        try:
            # Generate query embedding
            query_embedding = self.embedding_node.execute(text=query)

            # Prepare filters
            filters = {}
            if user_id:
                filters["user_id"] = user_id

            # Search database (simplified for now)
            query_parts = ["SELECT * FROM chat_messages WHERE 1=1"]
            params = []

            if user_id:
                query_parts.append("AND user_id = ?")
                params.append(user_id)

            query_parts.append("ORDER BY timestamp DESC LIMIT ?")
            params.append(limit)

            search_result = self.vector_db.execute(
                {"query": " ".join(query_parts), "parameters": params}
            )

            # Format results
            results = []
            for row in search_result.get("rows", []):
                results.append(
                    {
                        "message_id": row["id"],
                        "session_id": row["session_id"],
                        "content": row["content"],
                        "role": row["role"],
                        "similarity": 0.8,  # Simplified similarity
                        "timestamp": row["timestamp"],
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Failed to search chat history: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get chat middleware statistics."""
        stats = {
            "conversations_started": self.conversations_started,
            "workflows_generated": self.workflows_generated,
            "suggestions_provided": self.suggestions_provided,
            "active_chat_sessions": len(self.chat_sessions),
            "embeddings_generated": self.embeddings_generated,
        }

        # Add vector database stats if available
        if self.enable_semantic_search:
            stats["semantic_search_enabled"] = True

        return stats
