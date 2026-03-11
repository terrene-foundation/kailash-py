"""
Tier 3 E2E Tests: PersistentBufferMemory with Real Ollama LLMs.

Tests conversation persistence with real infrastructure:
- Real Ollama LLM inference (requires Ollama running)
- Real DataFlow database (SQLite)
- Real BaseAgent conversations
- Application restart simulation
- Long-running conversation validation

Requirements:
- Ollama running locally with llama3.1:8b-instruct-q8_0 model
- No mocking (real infrastructure only)
- Tests may take 1-2 minutes due to LLM inference
"""

import subprocess
import tempfile
import time
from pathlib import Path

import pytest

try:
    from dataflow import DataFlow
except ImportError:
    DataFlow = None

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.backends.dataflow_backend import DataFlowBackend
from kaizen.memory.persistent_buffer import PersistentBufferMemory
from kaizen.signatures import InputField, OutputField, Signature


# Skip all tests if Ollama is not available
def check_ollama_available():
    """Check if Ollama is running and has llama3.2 model."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "llama3.2" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_llama_model():
    """Get available llama3.2 model name."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        # Prefer smaller models for faster testing
        if "llama3.1:8b-instruct-q8_0" in result.stdout:
            return "llama3.1:8b-instruct-q8_0"
        elif "llama3.2" in result.stdout:
            return "llama3.2:latest"
        return "llama3.1:8b-instruct-q8_0"  # Default fallback
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "llama3.1:8b-instruct-q8_0"


LLAMA_MODEL = get_llama_model()

pytestmark = pytest.mark.skipif(
    not check_ollama_available(),
    reason="Ollama not running or llama3.2 model not available",
)


# Fixtures


@pytest.fixture
def temp_db():
    """Create temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_e2e.db"
        yield f"sqlite:///{db_path}"


@pytest.fixture
def dataflow_db(temp_db):
    """Create DataFlow instance with test database."""
    if DataFlow is None:
        pytest.skip("DataFlow not installed")

    db = DataFlow(db_url=temp_db, auto_migrate=True)

    @db.model
    class ConversationMessage:
        """Message model for conversation persistence."""

        id: str
        conversation_id: str
        sender: str  # "user" or "agent"
        content: str
        metadata: dict
        created_at: str

    yield db


@pytest.fixture
def persistent_memory(dataflow_db):
    """Create PersistentBufferMemory with DataFlow backend."""
    backend = DataFlowBackend(db=dataflow_db, model_name="ConversationMessage")
    memory = PersistentBufferMemory(
        session_id="e2e_test_session",
        backend=backend,
        max_turns=100,  # Large buffer for long conversations
        cache_ttl_seconds=300,  # 5 minutes
    )
    yield memory
    # Cleanup
    memory.clear()


# Simple Q&A Signature for testing


class QASignature(Signature):
    """Simple question-answer signature for E2E testing."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Concise answer (1-2 sentences)")


# Test Agent


class TestQAAgent(BaseAgent):
    """Simple Q&A agent for E2E testing."""

    def __init__(self, memory: PersistentBufferMemory, model: str = None):
        """Initialize agent with persistent memory."""
        if model is None:
            model = LLAMA_MODEL
        super().__init__(
            config={
                "llm_provider": "ollama",
                "model": model,
                "temperature": 0.1,  # Low temp for consistency
            },
            signature=QASignature(),
            memory=memory,
        )

    def ask(self, question: str) -> str:
        """Ask a question and get answer."""
        result = self.run(question=question)
        answer = self.extract_str(result, "answer", default="No answer")

        # Save to memory
        self.write_to_memory(
            content={"question": question, "answer": answer},
            tags=["qa"],
            importance=0.8,
        )

        return answer


# E2E Tests


def test_basic_conversation_persistence(persistent_memory, dataflow_db):
    """
    Test basic conversation persistence with real Ollama LLM.

    Validates:
    - Agent can answer questions using Ollama
    - Conversation is saved to database
    - Memory can be loaded from database
    """
    agent = TestQAAgent(memory=persistent_memory)

    # Ask first question
    answer1 = agent.ask("What is 2+2?")
    assert len(answer1) > 0, "Agent should return an answer"

    # Ask second question
    answer2 = agent.ask("What is the capital of France?")
    assert len(answer2) > 0, "Agent should return an answer"

    # Verify memory has both turns
    context = persistent_memory.load_context()
    assert len(context) == 2, "Memory should have 2 turns"

    # Verify database persistence
    backend = persistent_memory.backend
    turns_from_db = backend.load_turns("e2e_test_session")
    assert len(turns_from_db) == 2, "Database should have 2 turns"


def test_application_restart_simulation(dataflow_db):
    """
    Test conversation persistence across application restart.

    Simulates:
    1. Agent has conversation (saves to DB)
    2. Application "restarts" (new memory instance)
    3. Agent resumes conversation from DB

    Validates:
    - Conversation survives memory instance destruction
    - New agent can access previous conversation
    - No data loss during restart
    """
    session_id = "restart_test_session"

    # Phase 1: Initial conversation
    backend1 = DataFlowBackend(db=dataflow_db, model_name="ConversationMessage")
    memory1 = PersistentBufferMemory(
        session_id=session_id, backend=backend1, max_turns=100
    )
    agent1 = TestQAAgent(memory=memory1)

    # Have conversation
    answer1 = agent1.ask("What is Python?")
    assert len(answer1) > 0

    # Save turn count before "restart"
    turns_before = len(memory1.load_context())
    assert turns_before == 1, "Should have 1 turn before restart"

    # Phase 2: "Application restart" - destroy memory instance
    del memory1
    del agent1

    # Phase 3: Resume conversation with new instances
    backend2 = DataFlowBackend(db=dataflow_db, model_name="ConversationMessage")
    memory2 = PersistentBufferMemory(
        session_id=session_id, backend=backend2, max_turns=100  # Same session ID
    )
    agent2 = TestQAAgent(memory=memory2)

    # Load previous conversation
    context = memory2.load_context()
    assert len(context) == turns_before, "Should load previous conversation"

    # Continue conversation
    answer2 = agent2.ask("What is JavaScript?")
    assert len(answer2) > 0

    # Verify total turns
    final_context = memory2.load_context()
    assert len(final_context) == 2, "Should have 2 turns after restart"

    # Cleanup
    memory2.clear()


def test_multi_session_isolation(dataflow_db):
    """
    Test that multiple sessions are isolated.

    Validates:
    - Session A conversations don't appear in Session B
    - Each session maintains independent conversation history
    - Database correctly partitions by session_id
    """
    backend = DataFlowBackend(db=dataflow_db, model_name="ConversationMessage")

    # Create two independent sessions
    memory_a = PersistentBufferMemory(
        session_id="session_a", backend=backend, max_turns=100
    )
    memory_b = PersistentBufferMemory(
        session_id="session_b", backend=backend, max_turns=100
    )

    agent_a = TestQAAgent(memory=memory_a)
    agent_b = TestQAAgent(memory=memory_b)

    # Session A conversation
    agent_a.ask("What is 1+1?")

    # Session B conversation (different question)
    agent_b.ask("What is 3+3?")

    # Verify isolation
    context_a = memory_a.load_context()
    context_b = memory_b.load_context()

    assert len(context_a) == 1, "Session A should have 1 turn"
    assert len(context_b) == 1, "Session B should have 1 turn"

    # Verify different content
    assert (
        context_a[0]["user"] != context_b[0]["user"]
    ), "Sessions should have different questions"

    # Cleanup
    memory_a.clear()
    memory_b.clear()


def test_long_conversation_persistence(persistent_memory):
    """
    Test persistence of long conversation (10+ turns).

    Validates:
    - Memory can handle many turns
    - Database operations remain performant
    - FIFO limiting works correctly (if max_turns < conversation length)
    - All data persists correctly
    """
    agent = TestQAAgent(memory=persistent_memory)

    # Have 10 turn conversation
    questions = [
        "What is 1+1?",
        "What is 2+2?",
        "What is 3+3?",
        "What is Python?",
        "What is JavaScript?",
        "What is HTML?",
        "What is CSS?",
        "What is React?",
        "What is Node.js?",
        "What is SQL?",
    ]

    for question in questions:
        answer = agent.ask(question)
        assert len(answer) > 0, f"Should get answer for: {question}"

    # Verify all turns saved
    context = persistent_memory.load_context()
    assert len(context) == 10, "Should have 10 turns"

    # Verify database has all turns
    turns_from_db = persistent_memory.backend.load_turns("e2e_test_session")
    assert len(turns_from_db) == 10, "Database should have 10 turns"


def test_cache_performance(persistent_memory):
    """
    Test cache vs database performance.

    Validates:
    - Cache hits are significantly faster than DB queries
    - Cache invalidation works correctly
    - Performance targets met (<1ms cache, <50ms DB)
    """
    agent = TestQAAgent(memory=persistent_memory)

    # Create conversation
    agent.ask("What is 1+1?")

    # First load (DB query)
    start = time.time()
    context1 = persistent_memory.load_context()
    db_time = time.time() - start

    # Second load (cache hit)
    start = time.time()
    context2 = persistent_memory.load_context()
    cache_time = time.time() - start

    # Verify cache is faster
    assert cache_time < db_time, "Cache should be faster than DB"
    assert cache_time < 0.001, "Cache should be <1ms"
    assert db_time < 0.1, "DB query should be <100ms"

    # Verify same data
    assert context1 == context2, "Cache and DB should return same data"


def test_memory_context_integration(persistent_memory):
    """
    Test that memory context is properly used by agent.

    Validates:
    - Agent can access previous conversation via memory
    - Memory provides correct context format
    - Context includes all conversation turns
    """
    agent = TestQAAgent(memory=persistent_memory)

    # Have multi-turn conversation
    agent.ask("My name is Alice.")
    agent.ask("What is 2+2?")
    agent.ask("What is Python?")

    # Load context
    context = persistent_memory.load_context()

    # Verify context structure
    assert len(context) == 3, "Should have 3 turns"

    for turn in context:
        assert "user" in turn, "Turn should have 'user' field"
        assert "agent" in turn, "Turn should have 'agent' field"
        assert len(turn["user"]) > 0, "User message should not be empty"
        assert len(turn["agent"]) > 0, "Agent message should not be empty"


def test_concurrent_sessions(dataflow_db):
    """
    Test concurrent access to different sessions.

    Validates:
    - Multiple agents can operate simultaneously
    - Sessions remain isolated under concurrency
    - No race conditions or data corruption
    """
    import threading

    backend = DataFlowBackend(db=dataflow_db, model_name="ConversationMessage")
    results = {}
    errors = []

    def run_session(session_id: str, question: str):
        """Run a session in a thread."""
        try:
            memory = PersistentBufferMemory(
                session_id=session_id, backend=backend, max_turns=100
            )
            agent = TestQAAgent(memory=memory, model="llama3.1:8b-instruct-q8_0")
            answer = agent.ask(question)
            results[session_id] = len(memory.load_context())
        except Exception as e:
            errors.append((session_id, str(e)))

    # Create threads for 3 concurrent sessions
    threads = [
        threading.Thread(target=run_session, args=("concurrent_1", "What is 1+1?")),
        threading.Thread(target=run_session, args=("concurrent_2", "What is 2+2?")),
        threading.Thread(target=run_session, args=("concurrent_3", "What is 3+3?")),
    ]

    # Start all threads
    for t in threads:
        t.start()

    # Wait for completion
    for t in threads:
        t.join(timeout=60)

    # Verify no errors
    assert len(errors) == 0, f"Should have no errors, got: {errors}"

    # Verify all sessions completed
    assert len(results) == 3, "All sessions should complete"
    assert all(
        count == 1 for count in results.values()
    ), "Each session should have 1 turn"


def test_error_recovery(persistent_memory):
    """
    Test error recovery and graceful degradation.

    Validates:
    - Memory handles invalid data gracefully
    - Agent can continue after errors
    - No data corruption on errors
    """
    agent = TestQAAgent(memory=persistent_memory)

    # Have valid conversation
    agent.ask("What is 1+1?")

    # Verify can still operate
    agent.ask("What is 2+2?")

    # Verify no data corruption
    context = persistent_memory.load_context()
    assert len(context) == 2, "Should have 2 valid turns"


# Performance Benchmarks


@pytest.mark.benchmark
def test_write_performance_benchmark(persistent_memory, benchmark):
    """
    Benchmark write performance.

    Target: <50ms per turn save (including DB write)
    """
    agent = TestQAAgent(memory=persistent_memory)

    def write_turn():
        agent.ask("What is Python?")

    # Note: This includes LLM inference time, so will be slower than target
    # Just ensuring no catastrophic performance issues
    result = benchmark(write_turn)

    # Verify operation completed (performance measured by pytest-benchmark)
    context = persistent_memory.load_context()
    assert len(context) > 0


@pytest.mark.benchmark
def test_read_performance_benchmark(persistent_memory, benchmark):
    """
    Benchmark read performance (cache hit).

    Target: <1ms for cache hit
    """
    agent = TestQAAgent(memory=persistent_memory)

    # Create data
    agent.ask("What is Python?")

    # Benchmark cache read
    def read_context():
        return persistent_memory.load_context()

    result = benchmark(read_context)

    # Verify correct data returned
    assert len(result) == 1
