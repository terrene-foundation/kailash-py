"""
Mock Providers for Kaizen framework unit testing.

Provides mock services for Tier 1 (Unit) testing without external dependencies.
IMPORTANT: These mocks are ONLY for unit tests. Integration and E2E tests use real services.

Based on Kailash Core SDK mock providers with Kaizen-specific enhancements.
"""

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import Mock

from kaizen.signatures import Signature


@dataclass
class MockCallRecord:
    """Record of a mock service call."""

    call_id: str
    timestamp: float
    method: str
    args: tuple
    kwargs: dict
    response: Any
    duration_ms: float


class MockLLMProvider:
    """Mock LLM provider for unit testing without real LLM services."""

    def __init__(self, custom_responses: Optional[Dict[str, Any]] = None):
        """
        Initialize mock LLM provider.

        Args:
            custom_responses: Optional dictionary mapping prompts to responses
        """
        self.custom_responses = custom_responses or {}
        self.call_count = 0
        self.call_history: List[MockCallRecord] = []
        self.default_model = "mock-gpt-3.5-turbo"
        self.simulate_delays = False
        self.failure_rate = 0.0  # 0-1 probability of failure

    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Mock LLM completion.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters (model, temperature, etc.)

        Returns:
            Mock completion response in standard format
        """
        start_time = time.time()
        self.call_count += 1
        call_id = str(uuid.uuid4())

        # Simulate processing delay if enabled
        if self.simulate_delays:
            delay = kwargs.get("timeout", 1.0) * 0.1  # 10% of timeout
            time.sleep(min(delay, 0.5))  # Max 500ms delay

        # Simulate failures if configured
        if self.failure_rate > 0 and time.time() % 1 < self.failure_rate:
            raise Exception("Mock LLM provider failure simulation")

        # Check for custom response
        response_text = self._generate_response(prompt, kwargs)

        duration_ms = (time.time() - start_time) * 1000

        response = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(prompt.split()) + len(response_text.split()),
            },
            "model": kwargs.get("model", self.default_model),
            "id": call_id,
            "object": "chat.completion",
            "created": int(time.time()),
        }

        # Record call
        record = MockCallRecord(
            call_id=call_id,
            timestamp=start_time,
            method="complete",
            args=(prompt,),
            kwargs=kwargs,
            response=response,
            duration_ms=duration_ms,
        )
        self.call_history.append(record)

        return response

    def stream_complete(
        self, prompt: str, **kwargs
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Mock streaming completion.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters

        Yields:
            Mock streaming response chunks
        """
        time.time()
        call_id = str(uuid.uuid4())
        response_text = self._generate_response(prompt, kwargs)

        # Simulate streaming by yielding chunks
        chunk_size = kwargs.get("chunk_size", 10)
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i : i + chunk_size]
            is_final = i + chunk_size >= len(response_text)

            chunk_response = {
                "id": call_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": kwargs.get("model", self.default_model),
                "choices": [
                    {
                        "delta": {"content": chunk if not is_final else ""},
                        "finish_reason": "stop" if is_final else None,
                        "index": 0,
                    }
                ],
            }

            yield chunk_response

            # Small delay between chunks
            if self.simulate_delays:
                time.sleep(0.01)

    def _generate_response(self, prompt: str, kwargs: Dict[str, Any]) -> str:
        """Generate appropriate mock response based on prompt and parameters."""
        # Check for exact custom response
        if prompt in self.custom_responses:
            response = self.custom_responses[prompt]
            if isinstance(response, dict):
                return json.dumps(response)
            return str(response)

        # Check for pattern-based responses
        prompt_lower = prompt.lower()

        # Proposal generation (consensus building)
        if "problem:" in prompt_lower and "proposal" in prompt_lower:
            return json.dumps(
                {
                    "proposal": "Implement automated code review checks with AI assistance",
                    "reasoning": "This approach combines automation with human oversight to improve efficiency while maintaining quality standards",
                }
            )

        # Task delegation (supervisor-worker)
        if "request:" in prompt_lower and "tasks" in prompt_lower:
            return json.dumps(
                {
                    "tasks": [
                        {
                            "task_id": "task_1",
                            "description": "Process document 1",
                            "assigned_to": "worker",
                        },
                        {
                            "task_id": "task_2",
                            "description": "Process document 2",
                            "assigned_to": "worker",
                        },
                        {
                            "task_id": "task_3",
                            "description": "Process document 3",
                            "assigned_to": "worker",
                        },
                    ],
                    "reasoning": "Break work into parallel tasks for efficient processing",
                }
            )

        # Review/voting
        if "proposal:" in prompt_lower and (
            "vote" in prompt_lower or "review" in prompt_lower
        ):
            return json.dumps(
                {
                    "vote": "approve",
                    "feedback": "The proposal addresses key concerns effectively",
                    "confidence": "0.85",
                }
            )

        # Facilitation/consensus
        if "votes:" in prompt_lower and "decision" in prompt_lower:
            return json.dumps(
                {
                    "decision": "ACCEPT",
                    "rationale": "Majority of reviewers approved the proposal",
                    "consensus_level": "0.75",
                }
            )

        # Worker task execution
        if "task:" in prompt_lower and "result" in prompt_lower:
            return json.dumps(
                {
                    "result": "Task completed successfully",
                    "status": "completed",
                    "details": "Processing completed with expected output",
                }
            )

        # Batch processing signature
        if "items:" in prompt_lower and "results" in prompt_lower:
            return json.dumps(
                {
                    "results": [
                        "Processed item 1",
                        "Processed item 2",
                        "Processed item 3",
                    ],
                    "count": "3",
                }
            )

        # Policy parsing (compliance)
        if "policies:" in prompt_lower and "parsed_policies" in prompt_lower:
            return json.dumps(
                {
                    "parsed_policies": [
                        {
                            "id": "policy_1",
                            "name": "Security Policy",
                            "rules": ["Rule 1", "Rule 2"],
                        },
                        {
                            "id": "policy_2",
                            "name": "Data Privacy",
                            "rules": ["Rule 3", "Rule 4"],
                        },
                    ],
                    "policy_count": "2",
                }
            )

        # Compliance checking
        if "action:" in prompt_lower and "compliant" in prompt_lower:
            return json.dumps(
                {"compliant": "true", "violations": "[]", "compliance_score": "1.0"}
            )

        # Chart generation (data reporting)
        if "data:" in prompt_lower and "chart" in prompt_lower:
            return json.dumps(
                {
                    "chart": "Bar chart showing sales trends",
                    "chart_type": "bar",
                    "insights": "Sales increased by 20% in Q3",
                }
            )

        # Document analysis
        if "documents:" in prompt_lower and "analysis" in prompt_lower:
            return json.dumps(
                {
                    "analysis": "The documents contain key information about market trends",
                    "key_points": [
                        "Market growth",
                        "Customer preferences",
                        "Competition analysis",
                    ],
                    "summary": "Comprehensive market analysis with actionable insights",
                }
            )

        # Query decomposition (multi-hop RAG)
        if "question:" in prompt_lower and "sub_questions" in prompt_lower:
            return json.dumps(
                {
                    "sub_questions": [
                        "What is the main topic?",
                        "What are the key details?",
                        "How do they relate?",
                    ],
                    "reasoning": "Breaking complex question into manageable parts",
                }
            )

        # Source coordination (federated RAG)
        if "query:" in prompt_lower and "sources" in prompt_lower:
            return json.dumps(
                {
                    "sources": ["source_1", "source_2", "source_3"],
                    "strategy": "parallel",
                    "reasoning": "Query multiple sources for comprehensive results",
                }
            )

        # Human approval
        if "request:" in prompt_lower and "approval" in prompt_lower:
            return json.dumps(
                {
                    "approval": "approved",
                    "reasoning": "Request meets all criteria",
                    "confidence": "0.9",
                }
            )

        # Fallback/resilience
        if "query:" in prompt_lower and "fallback" in prompt_lower:
            return json.dumps(
                {"result": "Mock result from primary provider", "source": "primary"}
            )

        # Streaming chat
        if "message:" in prompt_lower and "response" in prompt_lower:
            return json.dumps(
                {
                    "response": "This is a mock chat response to your message",
                    "context": "Chat conversation",
                }
            )

        # Agentic RAG workflow responses
        if "query:" in prompt_lower:
            if "strategy" in prompt_lower:
                return json.dumps(
                    {
                        "strategy": "semantic",
                        "reasoning": "Query requires semantic search for best results",
                    }
                )
            elif "documents" in prompt_lower:
                return json.dumps(
                    {
                        "documents": [
                            {
                                "id": "doc1",
                                "content": "Relevant document 1",
                                "score": "0.95",
                            },
                            {
                                "id": "doc2",
                                "content": "Relevant document 2",
                                "score": "0.85",
                            },
                        ]
                    }
                )
            elif "quality" in prompt_lower:
                return json.dumps(
                    {
                        "quality_score": "0.9",
                        "sufficient": "true",
                        "feedback": "Documents are highly relevant",
                    }
                )
            elif "answer" in prompt_lower:
                return json.dumps(
                    {
                        "answer": "This is a comprehensive answer based on retrieved documents",
                        "confidence": "0.92",
                        "sources": ["doc1", "doc2"],
                    }
                )

        # Generic question answering
        if "question" in prompt_lower and "?" in prompt:
            return json.dumps(
                {
                    "answer": "This is a mock answer to your question",
                    "confidence": "0.85",
                }
            )

        # Analysis tasks
        if "analyze" in prompt_lower or "analysis" in prompt_lower:
            return json.dumps(
                {
                    "analysis": {
                        "key_findings": ["Mock finding 1", "Mock finding 2"],
                        "metrics": {"accuracy": 0.95, "confidence": 0.88},
                    },
                    "insights": [
                        "Mock insight about the data",
                        "Pattern detected in mock analysis",
                    ],
                    "recommendations": [
                        "Consider mock recommendation 1",
                        "Implement mock strategy 2",
                    ],
                }
            )

        # Code/content generation
        if "create" in prompt_lower or "generate" in prompt_lower:
            return json.dumps(
                {
                    "content": "This is mock generated content based on your requirements",
                    "format": "structured",
                }
            )

        # Chain of thought / reasoning
        if "steps" in prompt_lower or "reasoning" in prompt_lower:
            return json.dumps(
                {
                    "steps": [
                        "Step 1: Analyze the mock problem",
                        "Step 2: Consider mock alternatives",
                        "Step 3: Arrive at mock solution",
                    ],
                    "solution": "Mock solution to the problem",
                    "confidence": "0.85",
                }
            )

        # Default structured response
        return json.dumps(
            {
                "response": f"Mock response to: {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
                "status": "success",
            }
        )

    def get_call_history(self) -> List[MockCallRecord]:
        """Get history of all LLM calls."""
        return self.call_history.copy()

    def reset_history(self) -> None:
        """Reset call history and count."""
        self.call_history = []
        self.call_count = 0

    def set_failure_rate(self, rate: float) -> None:
        """Set the failure simulation rate (0-1)."""
        self.failure_rate = max(0.0, min(1.0, rate))

    def enable_delays(self, enabled: bool = True) -> None:
        """Enable or disable simulated processing delays."""
        self.simulate_delays = enabled


class MockMemoryProvider:
    """Mock memory provider for testing memory functionality."""

    def __init__(self):
        """Initialize mock memory provider."""
        self.memories: Dict[str, Dict[str, Any]] = {}
        self.call_history: List[MockCallRecord] = []

    def store(self, key: str, data: Any, metadata: Optional[Dict] = None) -> str:
        """
        Mock memory storage.

        Args:
            key: Memory key
            data: Data to store
            metadata: Optional metadata

        Returns:
            Storage ID
        """
        start_time = time.time()
        storage_id = str(uuid.uuid4())

        memory_record = {
            "id": storage_id,
            "key": key,
            "data": data,
            "metadata": metadata or {},
            "created": datetime.now().isoformat(),
            "accessed": datetime.now().isoformat(),
        }

        self.memories[key] = memory_record

        # Record call
        record = MockCallRecord(
            call_id=storage_id,
            timestamp=start_time,
            method="store",
            args=(key, data),
            kwargs={"metadata": metadata},
            response=storage_id,
            duration_ms=(time.time() - start_time) * 1000,
        )
        self.call_history.append(record)

        return storage_id

    def retrieve(self, key: str) -> Optional[Any]:
        """
        Mock memory retrieval.

        Args:
            key: Memory key

        Returns:
            Retrieved data or None
        """
        start_time = time.time()
        call_id = str(uuid.uuid4())

        result = None
        if key in self.memories:
            result = self.memories[key]["data"]
            # Update access time
            self.memories[key]["accessed"] = datetime.now().isoformat()

        # Record call
        record = MockCallRecord(
            call_id=call_id,
            timestamp=start_time,
            method="retrieve",
            args=(key,),
            kwargs={},
            response=result,
            duration_ms=(time.time() - start_time) * 1000,
        )
        self.call_history.append(record)

        return result

    def delete(self, key: str) -> bool:
        """
        Mock memory deletion.

        Args:
            key: Memory key

        Returns:
            True if deleted, False if not found
        """
        start_time = time.time()
        call_id = str(uuid.uuid4())

        deleted = key in self.memories
        if deleted:
            del self.memories[key]

        # Record call
        record = MockCallRecord(
            call_id=call_id,
            timestamp=start_time,
            method="delete",
            args=(key,),
            kwargs={},
            response=deleted,
            duration_ms=(time.time() - start_time) * 1000,
        )
        self.call_history.append(record)

        return deleted

    def list_keys(self) -> List[str]:
        """List all memory keys."""
        return list(self.memories.keys())

    def clear(self) -> None:
        """Clear all memories."""
        self.memories.clear()
        self.call_history.clear()


class MockDatabaseProvider:
    """Mock database provider for testing database operations."""

    def __init__(self):
        """Initialize mock database provider."""
        self.tables: Dict[str, List[Dict[str, Any]]] = {}
        self.call_history: List[MockCallRecord] = []
        self.connection_status = "connected"

    def execute_query(
        self, query: str, params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Mock SQL query execution.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Mock query results
        """
        start_time = time.time()
        call_id = str(uuid.uuid4())

        # Simple mock query parsing
        query_lower = query.lower().strip()
        results = []

        if query_lower.startswith("select"):
            # Mock SELECT results
            results = [
                {"id": 1, "name": "Mock Record 1", "value": 100},
                {"id": 2, "name": "Mock Record 2", "value": 200},
            ]
        elif query_lower.startswith("insert"):
            # Mock INSERT result
            results = [{"inserted_id": 123, "rows_affected": 1}]
        elif query_lower.startswith("update"):
            # Mock UPDATE result
            results = [{"rows_affected": 1}]
        elif query_lower.startswith("delete"):
            # Mock DELETE result
            results = [{"rows_affected": 1}]

        # Record call
        record = MockCallRecord(
            call_id=call_id,
            timestamp=start_time,
            method="execute_query",
            args=(query,),
            kwargs={"params": params},
            response=results,
            duration_ms=(time.time() - start_time) * 1000,
        )
        self.call_history.append(record)

        return results

    def get_connection_status(self) -> str:
        """Get mock connection status."""
        return self.connection_status

    def set_connection_status(self, status: str) -> None:
        """Set mock connection status for testing."""
        self.connection_status = status


class MockSignatureCompiler:
    """Mock signature compiler for testing signature-based programming."""

    def __init__(self):
        """Initialize mock signature compiler."""
        self.compiled_signatures: Dict[str, Dict[str, Any]] = {}
        self.call_history: List[MockCallRecord] = []

    def compile_signature(self, signature: Signature) -> Dict[str, Any]:
        """
        Mock signature compilation.

        Args:
            signature: Signature to compile

        Returns:
            Mock compiled signature
        """
        start_time = time.time()
        call_id = str(uuid.uuid4())

        # Mock compilation result
        compiled = {
            "name": signature.name,
            "description": signature.description,
            "inputs": signature.define_inputs(),
            "outputs": signature.define_outputs(),
            "workflow_nodes": [
                {"type": "InputValidationNode", "id": "input_validator"},
                {"type": "LLMAgentNode", "id": "llm_processor"},
                {"type": "OutputFormatterNode", "id": "output_formatter"},
            ],
            "connections": [
                {"from": "input_validator", "to": "llm_processor"},
                {"from": "llm_processor", "to": "output_formatter"},
            ],
            "compiled_at": datetime.now().isoformat(),
        }

        self.compiled_signatures[signature.name] = compiled

        # Record call
        record = MockCallRecord(
            call_id=call_id,
            timestamp=start_time,
            method="compile_signature",
            args=(signature,),
            kwargs={},
            response=compiled,
            duration_ms=(time.time() - start_time) * 1000,
        )
        self.call_history.append(record)

        return compiled

    def get_compiled_signature(self, name: str) -> Optional[Dict[str, Any]]:
        """Get previously compiled signature."""
        return self.compiled_signatures.get(name)


class MockAuditLogger:
    """Mock audit logger for testing enterprise audit features."""

    def __init__(self):
        """Initialize mock audit logger."""
        self.audit_logs: List[Dict[str, Any]] = []
        self.call_history: List[MockCallRecord] = []

    def log_event(
        self,
        event_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Mock audit event logging.

        Args:
            event_type: Type of audit event
            details: Event details
            user_id: Optional user ID
            session_id: Optional session ID

        Returns:
            Audit log ID
        """
        start_time = time.time()
        log_id = str(uuid.uuid4())

        audit_entry = {
            "id": log_id,
            "event_type": event_type,
            "details": details,
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "source": "mock_audit_logger",
        }

        self.audit_logs.append(audit_entry)

        # Record call
        record = MockCallRecord(
            call_id=log_id,
            timestamp=start_time,
            method="log_event",
            args=(event_type, details),
            kwargs={"user_id": user_id, "session_id": session_id},
            response=log_id,
            duration_ms=(time.time() - start_time) * 1000,
        )
        self.call_history.append(record)

        return log_id

    def get_audit_logs(
        self,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit logs with optional filtering."""
        logs = self.audit_logs

        if event_type:
            logs = [log for log in logs if log["event_type"] == event_type]

        if user_id:
            logs = [log for log in logs if log["user_id"] == user_id]

        return logs[-limit:]


# Utility functions for creating mock objects
def create_mock_kaizen_config(**overrides) -> Mock:
    """Create a mock KaizenConfig with default values."""
    mock_config = Mock()
    mock_config.debug = overrides.get("debug", True)
    mock_config.memory_enabled = overrides.get("memory_enabled", False)
    mock_config.optimization_enabled = overrides.get("optimization_enabled", False)
    mock_config.monitoring_enabled = overrides.get("monitoring_enabled", False)
    mock_config.cache_enabled = overrides.get("cache_enabled", False)
    mock_config.signature_validation = overrides.get("signature_validation", True)
    mock_config.auto_optimization = overrides.get("auto_optimization", False)
    return mock_config


def create_mock_agent(**overrides) -> Mock:
    """Create a mock Agent with default behavior."""
    mock_agent = Mock()
    mock_agent.id = overrides.get("id", "mock_agent")
    mock_agent.config = overrides.get("config", {"model": "mock-gpt-3.5-turbo"})
    mock_agent.signature = overrides.get("signature", None)

    # Mock methods
    mock_agent.execute.return_value = {
        "response": "Mock agent response",
        "metadata": {},
    }
    mock_agent.compile_workflow.return_value = Mock()

    return mock_agent


def create_mock_workflow_builder() -> Mock:
    """Create a mock WorkflowBuilder."""
    mock_builder = Mock()
    mock_workflow = Mock()

    mock_builder.add_node.return_value = mock_builder
    mock_builder.add_connection.return_value = mock_builder
    mock_builder.build.return_value = mock_workflow

    return mock_builder


def create_mock_runtime() -> Mock:
    """Create a mock LocalRuntime."""
    mock_runtime = Mock()
    mock_runtime.execute.return_value = (
        {"result": "Mock workflow execution result"},
        str(uuid.uuid4()),
    )
    return mock_runtime


# Context managers for patching
class MockProviderContext:
    """Context manager for comprehensive mocking during unit tests."""

    def __init__(self, **provider_configs):
        """
        Initialize mock provider context.

        Args:
            **provider_configs: Configuration for each provider
        """
        self.llm_provider = MockLLMProvider(provider_configs.get("llm_responses", {}))
        self.memory_provider = MockMemoryProvider()
        self.database_provider = MockDatabaseProvider()
        self.audit_logger = MockAuditLogger()
        self.signature_compiler = MockSignatureCompiler()

        self.patches = []

    def __enter__(self):
        """Enter context and apply patches."""
        # This would typically patch real providers
        # Implementation depends on how Kaizen framework is structured
        return {
            "llm": self.llm_provider,
            "memory": self.memory_provider,
            "database": self.database_provider,
            "audit": self.audit_logger,
            "compiler": self.signature_compiler,
        }

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and remove patches."""
        for patcher in self.patches:
            patcher.stop()


# Export all mock providers
__all__ = [
    "MockLLMProvider",
    "MockMemoryProvider",
    "MockDatabaseProvider",
    "MockSignatureCompiler",
    "MockAuditLogger",
    "MockCallRecord",
    "create_mock_kaizen_config",
    "create_mock_agent",
    "create_mock_workflow_builder",
    "create_mock_runtime",
    "MockProviderContext",
]
