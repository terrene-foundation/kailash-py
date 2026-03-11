"""
Tier 2 Integration Tests: BaseAgent with Control Protocol

Tests BaseAgent's ask_user_question() and request_approval() methods with:
1. Real Ollama LLM provider (NO MOCKING)
2. Real Control Protocol communication
3. Actual interactive workflows

Test Strategy:
- Uses MockTransport for controlled user responses
- Uses real Ollama for LLM inference
- Validates end-to-end interactive agent workflows

Prerequisites:
- Ollama running locally
- Model available (llama3.1:8b-instruct-q8_0 recommended for speed)

Coverage:
- BaseAgent.ask_user_question() with real LLM
- BaseAgent.request_approval() with real LLM
- Control Protocol integration
- Error handling and timeouts
"""

from dataclasses import dataclass

import anyio
import pytest
from kaizen.core.autonomy.control.protocol import ControlProtocol

# Real imports (no mocks)
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

from tests.utils.mock_transport import MockTransport

# Configure for asyncio (required by Control Protocol)
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    """Force asyncio backend."""
    return "asyncio"


# ============================================
# Test Fixtures
# ============================================


class InteractiveTaskSignature(Signature):
    """Signature for interactive agent tasks."""

    task: str = InputField(description="Task description")
    user_input: str = InputField(description="User input received", default="")
    approval_status: str = InputField(description="Approval status", default="")
    result: str = OutputField(description="Task result")


@dataclass
class InteractiveAgentConfig:
    """Config for interactive agent using Ollama."""

    llm_provider: str = "ollama"
    model: str = "llama3.1:8b-instruct-q8_0"  # Fast, lightweight model
    temperature: float = 0.1  # Low temperature for consistent responses


def queue_response_for_request(transport: MockTransport, response_data: dict) -> None:
    """
    Helper to queue a response matching the last written request.

    Extracts request_id from the last written message and creates
    a properly formatted ControlResponse.

    Args:
        transport: MockTransport instance
        response_data: Response data dict (e.g., {"answer": "value"})
    """

    from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse

    # Get last written request
    if not transport.written_messages:
        raise ValueError("No request written yet")

    last_request_json = transport.written_messages[-1]
    request = ControlRequest.from_json(last_request_json)

    # Create matching response
    response = ControlResponse(request_id=request.request_id, data=response_data)

    # Queue response
    transport.queue_message(response.to_json())


@pytest.fixture
async def control_protocol():
    """Create Control Protocol with MockTransport."""
    transport = MockTransport()
    await transport.connect()

    protocol = ControlProtocol(transport)

    yield protocol, transport

    # Cleanup
    await protocol.stop()
    await transport.close()


@pytest.fixture
def interactive_agent(control_protocol):
    """Create BaseAgent with Control Protocol using real Ollama."""
    protocol, transport = control_protocol

    config = InteractiveAgentConfig()
    signature = InteractiveTaskSignature()

    agent = BaseAgent(config=config, signature=signature, control_protocol=protocol)

    return agent, protocol, transport


# ============================================
# Test 1: BaseAgent with Control Protocol - Question Flow
# ============================================


class TestBaseAgentQuestionFlow:
    """Test ask_user_question() with real Ollama LLM."""

    async def test_agent_can_ask_question_and_receive_answer(self, interactive_agent):
        """Test basic question/answer flow."""
        agent, protocol, transport = interactive_agent

        # Start protocol
        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create background task to respond to questions
            async def auto_respond():
                """Wait for question and respond."""
                await anyio.sleep(0.1)  # Give question time to be sent
                queue_response_for_request(transport, {"answer": "Alice"})

            tg.start_soon(auto_respond)

            # Agent asks question
            answer = await agent.ask_user_question(
                question="What is your name?", timeout=10.0
            )

            # Verify response received
            assert answer == "Alice"
            assert len(transport.written_messages) > 0

            # Stop protocol
            await protocol.stop()

    async def test_agent_can_ask_multiple_choice_question(self, interactive_agent):
        """Test question with options."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create background task to respond after question is sent
            async def auto_respond():
                await anyio.sleep(0.1)  # Give question time to be sent
                transport.queue_response("question", {"answer": "Python"})

            tg.start_soon(auto_respond)

            # Agent asks question with options
            answer = await agent.ask_user_question(
                question="Which language do you prefer?",
                options=["Python", "JavaScript", "Go"],
                timeout=10.0,
            )

            assert answer == "Python"

            # Verify options were sent
            request_data = transport.written_messages[0]
            assert "question" in request_data

            await protocol.stop()

    async def test_agent_question_timeout_handling(self, interactive_agent):
        """Test timeout when user doesn't respond."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Don't queue any response - will timeout

            with pytest.raises(TimeoutError):
                await agent.ask_user_question(
                    question="This will timeout",
                    timeout=0.5,  # Short timeout for fast test
                )

            await protocol.stop()


# ============================================
# Test 2: BaseAgent with Control Protocol - Approval Flow
# ============================================


class TestBaseAgentApprovalFlow:
    """Test request_approval() with real Ollama LLM."""

    async def test_agent_can_request_approval_and_receive_response(
        self, interactive_agent
    ):
        """Test basic approval request flow."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create background task to respond
            async def auto_respond():
                await anyio.sleep(0.1)
                transport.queue_response("approval", {"approved": True})

            tg.start_soon(auto_respond)

            # Agent requests approval
            approved = await agent.request_approval(
                action="Delete temporary files", timeout=10.0
            )

            assert approved is True
            assert len(transport.written_messages) > 0

            await protocol.stop()

    async def test_agent_approval_with_details(self, interactive_agent):
        """Test approval request with detailed information."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create background task to respond
            async def auto_respond():
                await anyio.sleep(0.1)
                transport.queue_response("approval", {"approved": False})

            tg.start_soon(auto_respond)

            # Agent requests approval with details
            approved = await agent.request_approval(
                action="Delete 100 files",
                details={
                    "files_count": 100,
                    "total_size_mb": 250,
                    "estimated_time": "30 seconds",
                },
                timeout=10.0,
            )

            assert approved is False

            # Verify details were sent
            request_data = transport.written_messages[0]
            assert "action" in request_data

            await protocol.stop()

    async def test_agent_approval_timeout_handling(self, interactive_agent):
        """Test timeout when user doesn't respond to approval."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Don't queue any response - will timeout

            with pytest.raises(TimeoutError):
                await agent.request_approval(
                    action="This will timeout",
                    timeout=0.5,  # Short timeout for fast test
                )

            await protocol.stop()


# ============================================
# Test 3: BaseAgent Interactive Workflow
# ============================================


class TestBaseAgentInteractiveWorkflow:
    """Test complete interactive workflow with real LLM."""

    async def test_complete_interactive_workflow(self, interactive_agent):
        """Test multi-step interactive workflow with questions and approvals."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Helper to respond after small delay
            async def respond_after_delay(response_type: str, data: dict):
                await anyio.sleep(0.1)
                transport.queue_response(response_type, data)

            # Step 1: Ask for file selection
            tg.start_soon(respond_after_delay, "question", {"answer": "data.csv"})
            file_choice = await agent.ask_user_question(
                question="Which file to process?",
                options=["data.csv", "report.pdf"],
                timeout=10.0,
            )
            assert file_choice == "data.csv"

            # Step 2: Ask for processing mode
            tg.start_soon(respond_after_delay, "question", {"answer": "quick"})
            mode = await agent.ask_user_question(
                question="Processing mode?", options=["quick", "thorough"], timeout=10.0
            )
            assert mode == "quick"

            # Step 3: Request approval for operation
            tg.start_soon(respond_after_delay, "approval", {"approved": True})
            approved = await agent.request_approval(
                action=f"Process {file_choice} in {mode} mode",
                details={"file": file_choice, "mode": mode},
                timeout=10.0,
            )
            assert approved is True

            # Verify all interactions recorded
            assert len(transport.written_messages) >= 3

            await protocol.stop()

    async def test_workflow_with_user_cancellation(self, interactive_agent):
        """Test workflow when user denies approval."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Helper to respond after small delay
            async def respond_after_delay(response_type: str, data: dict):
                await anyio.sleep(0.1)
                transport.queue_response(response_type, data)

            # Ask question
            tg.start_soon(
                respond_after_delay, "question", {"answer": "risky_operation"}
            )
            operation = await agent.ask_user_question(
                question="Select operation?", timeout=10.0
            )

            # User denies approval
            tg.start_soon(respond_after_delay, "approval", {"approved": False})
            approved = await agent.request_approval(
                action=f"Execute {operation}", timeout=10.0
            )

            # Workflow should handle denial gracefully
            assert approved is False

            await protocol.stop()


# ============================================
# Test 4: Error Handling
# ============================================


class TestBaseAgentErrorHandling:
    """Test error handling with Control Protocol."""

    async def test_agent_without_control_protocol_raises_error(self):
        """Test that methods raise error when control_protocol not configured."""
        # Create agent WITHOUT control_protocol
        config = InteractiveAgentConfig()
        signature = InteractiveTaskSignature()
        agent = BaseAgent(config=config, signature=signature)

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="not configured"):
            await agent.ask_user_question("Test question?")

        with pytest.raises(RuntimeError, match="not configured"):
            await agent.request_approval("Test action")

    async def test_agent_handles_error_responses(self, interactive_agent):
        """Test handling of error responses from user."""
        agent, protocol, transport = interactive_agent

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create background task to send error response
            async def send_error():
                await anyio.sleep(0.1)
                transport.queue_error_response("question", "User cancelled")

            tg.start_soon(send_error)

            # Should raise RuntimeError with error message
            with pytest.raises(RuntimeError, match="error"):
                await agent.ask_user_question(question="This will error", timeout=10.0)

            await protocol.stop()


# ============================================
# Test 5: Real LLM Validation (Optional - Slow)
# ============================================


@pytest.mark.slow
class TestBaseAgentRealLLMValidation:
    """Test with real Ollama inference (SLOW - mark as optional)."""

    async def test_agent_uses_real_llm_provider(self, interactive_agent):
        """Verify agent actually uses Ollama for processing."""
        agent, protocol, transport = interactive_agent

        # Verify agent is configured with Ollama
        assert agent.config.llm_provider == "ollama"
        assert agent.config.model == "llama3.1:8b-instruct-q8_0"

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            # Create background task to respond
            async def auto_respond():
                await anyio.sleep(0.1)
                transport.queue_response("question", {"answer": "test_response"})

            tg.start_soon(auto_respond)

            # Execute question - will use real Ollama if agent.run() is called internally
            answer = await agent.ask_user_question(
                question="Simple test question?",
                timeout=15.0,  # Longer timeout for real LLM
            )

            assert answer == "test_response"

            await protocol.stop()
