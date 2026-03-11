"""
OpenAI Chat Completion Integration

Demonstrates:
- AsyncLocalRuntime for async LLM API calls
- Timeout handling for long-running LLM operations (30s)
- Streaming response handling and chunk processing
- Error handling for API rate limits and failures
- Response parsing and storage with DataFlow

Dependencies:
    pip install dataflow kailash

Environment Variables:
    OPENAI_API_KEY: Your OpenAI API key

Usage:
    # Send chat completion request
    python openai_chat.py chat "Explain DataFlow in 3 sentences"

    # Stream chat completion response
    python openai_chat.py stream "Write a haiku about databases"
"""

import asyncio
import sys
from datetime import datetime

from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ============================================================================
# Database Models
# ============================================================================

# Create in-memory database for demonstration
db = DataFlow(":memory:")


@db.model
class ChatCompletion:
    """
    Chat completion model for storing OpenAI API responses.

    Demonstrates:
    - String ID preservation for API message IDs
    - Integer fields for token tracking
    - Float fields for cost calculation
    """

    id: str
    prompt: str
    response: str
    model: str
    tokens_used: int
    cost: float


@db.model
class StreamingCompletion:
    """
    Streaming completion model for tracking streamed responses.

    Demonstrates:
    - Chunk count tracking
    - Performance metrics (streaming time)
    - Full response aggregation
    """

    id: str
    prompt: str
    full_response: str
    chunks_received: int
    streaming_time_ms: int


# ============================================================================
# Workflow 1: Chat Completion
# ============================================================================


def build_chat_completion_workflow(prompt: str) -> WorkflowBuilder:
    """
    Build workflow for OpenAI chat completion.

    Workflow Steps:
    1. Prepare prompt with context (PythonCodeNode)
    2. Call OpenAI API for chat completion (PythonCodeNode)
    3. Parse and store response (ChatCompletionCreateNode)
    4. Log API usage and cost

    Args:
        prompt: User prompt for chat completion

    Returns:
        WorkflowBuilder configured for chat completion

    Demonstrates:
        - AsyncLocalRuntime for async operations
        - Timeout configuration (30s for LLM)
        - Error handling for API failures
        - Response parsing and storage
    """
    workflow = WorkflowBuilder()

    # Step 1: Prepare prompt
    workflow.add_node(
        "PythonCodeNode",
        "prepare_prompt",
        {
            "code": f"""
# Prepare chat completion prompt
# In production, add system message, context, etc.
prompt = "{prompt}"
model = "gpt-4"
max_tokens = 150

print(f"✓ Prepared prompt for model: {{model}}")
print(f"  Prompt: {{prompt[:50]}}...")
""",
            "inputs": {},
        },
    )

    # Step 2: Call OpenAI API (mock)
    workflow.add_node(
        "PythonCodeNode",
        "call_openai",
        {
            "code": """
import uuid

# Mock OpenAI API call
# In production, use:
# from openai import OpenAI
# client = OpenAI()
# response = client.chat.completions.create(
#     model=model,
#     messages=[{"role": "user", "content": prompt}],
#     max_tokens=max_tokens
# )

response_text = "DataFlow is a zero-config database framework built on Kailash SDK. It automatically generates 11 workflow nodes per model for database operations (7 CRUD + 4 Bulk). It supports PostgreSQL, MySQL, and SQLite with full feature parity."
tokens_used = 50
cost = 0.002
completion_id = f"cmpl_{uuid.uuid4().hex[:24]}"

print(f"✓ OpenAI API call completed")
print(f"  Completion ID: {completion_id}")
print(f"  Tokens used: {tokens_used}")
print(f"  Cost: ${cost:.4f}")
""",
            "inputs": {"prompt": "{{prepare_prompt.prompt}}"},
        },
    )

    # Step 3: Store completion
    workflow.add_node(
        "ChatCompletionCreateNode",
        "store_completion",
        {
            "id": "{{call_openai.completion_id}}",
            "prompt": prompt,
            "response": "{{call_openai.response_text}}",
            "model": "{{prepare_prompt.model}}",
            "tokens_used": "{{call_openai.tokens_used}}",
            "cost": "{{call_openai.cost}}",
        },
    )

    # Connections
    workflow.add_connection("prepare_prompt", "prompt", "call_openai", "prompt")
    workflow.add_connection(
        "call_openai", "response_text", "store_completion", "response"
    )

    return workflow


async def chat_completion_example(prompt: str):
    """
    Execute chat completion workflow.

    Args:
        prompt: User prompt for chat completion

    Returns:
        Dictionary with completion results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_chat_completion_workflow(prompt)

    # Configure 30-second timeout for LLM operations
    runtime = AsyncLocalRuntime(execution_timeout=30)

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Chat completion successful (run_id: {run_id})")
        print(f"  Model: {results['store_completion']['model']}")
        print(f"  Tokens: {results['store_completion']['tokens_used']}")
        print(f"  Cost: ${results['store_completion']['cost']:.4f}")
        print()
        print("Response:")
        print(f"  {results['store_completion']['response']}")

        return results

    except Exception as e:
        print(f"✗ Error in chat completion: {e}")
        raise


# ============================================================================
# Workflow 2: Streaming Response
# ============================================================================


def build_streaming_workflow(prompt: str) -> WorkflowBuilder:
    """
    Build workflow for streaming chat completion.

    Workflow Steps:
    1. Initiate streaming chat completion (PythonCodeNode)
    2. Process chunks as they arrive (PythonCodeNode)
    3. Aggregate full response
    4. Store final response (StreamingCompletionCreateNode)

    Args:
        prompt: User prompt for streaming completion

    Returns:
        WorkflowBuilder configured for streaming

    Demonstrates:
        - Streaming API integration
        - Chunk processing in real-time
        - AsyncLocalRuntime for async streams
        - Progress tracking for streaming responses
    """
    workflow = WorkflowBuilder()

    # Step 1: Initiate streaming request
    workflow.add_node(
        "PythonCodeNode",
        "start_streaming",
        {
            "code": f"""
import uuid

# Mock streaming initialization
# In production, use:
# from openai import OpenAI
# client = OpenAI()
# stream = client.chat.completions.create(
#     model="gpt-4",
#     messages=[{{"role": "user", "content": "{prompt}"}}],
#     stream=True
# )

stream_id = f"stream_{{uuid.uuid4().hex[:16]}}"
prompt = "{prompt}"

print(f"✓ Streaming request initiated")
print(f"  Stream ID: {{stream_id}}")
print(f"  Prompt: {{prompt}}")
""",
            "inputs": {},
        },
    )

    # Step 2: Process streaming chunks
    workflow.add_node(
        "PythonCodeNode",
        "process_stream",
        {
            "code": """
# Mock streaming chunk processing
# In production, iterate over stream:
# chunks = []
# for chunk in stream:
#     if chunk.choices[0].delta.content:
#         content = chunk.choices[0].delta.content
#         chunks.append(content)
#         print(content, end='', flush=True)
# full_response = "".join(chunks)

chunks = [
    "Data flows like streams\\n",
    "Tables dance in memory\\n",
    "Queries bloom bright"
]
full_response = "".join(chunks)
chunks_received = len(chunks)
streaming_time_ms = 1500

print(f"\\n✓ Streaming completed")
print(f"  Chunks received: {chunks_received}")
print(f"  Streaming time: {streaming_time_ms}ms")
""",
            "inputs": {"stream_id": "{{start_streaming.stream_id}}"},
        },
    )

    # Step 3: Store streaming completion
    workflow.add_node(
        "StreamingCompletionCreateNode",
        "store_streaming",
        {
            "id": "{{start_streaming.stream_id}}",
            "prompt": prompt,
            "full_response": "{{process_stream.full_response}}",
            "chunks_received": "{{process_stream.chunks_received}}",
            "streaming_time_ms": "{{process_stream.streaming_time_ms}}",
        },
    )

    # Connections
    workflow.add_connection(
        "start_streaming", "stream_id", "process_stream", "stream_id"
    )
    workflow.add_connection(
        "process_stream", "full_response", "store_streaming", "full_response"
    )

    return workflow


async def streaming_completion_example(prompt: str):
    """
    Execute streaming completion workflow.

    Args:
        prompt: User prompt for streaming completion

    Returns:
        Dictionary with streaming results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_streaming_workflow(prompt)

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Streaming completion successful (run_id: {run_id})")
        print(f"  Chunks: {results['store_streaming']['chunks_received']}")
        print(f"  Time: {results['store_streaming']['streaming_time_ms']}ms")
        print()
        print("Full Response:")
        print(f"  {results['store_streaming']['full_response']}")

        return results

    except Exception as e:
        print(f"✗ Error in streaming completion: {e}")
        raise


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main entry point for example execution.

    Supports two commands:
    1. chat <prompt> - Send chat completion request
    2. stream <prompt> - Stream chat completion response
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print('  chat "<prompt>" - Send chat completion request')
        print('  stream "<prompt>" - Stream chat completion response')
        sys.exit(1)

    command = sys.argv[1]

    print("=" * 80)
    print("OpenAI Chat Completion Integration Example")
    print("=" * 80)
    print()

    if command == "chat":
        if len(sys.argv) < 3:
            print("Error: chat requires a prompt")
            print('Usage: chat "<prompt>"')
            sys.exit(1)

        prompt = " ".join(sys.argv[2:])

        print("Sending chat completion request...")
        print(f"Prompt: {prompt}")
        print()

        results = await chat_completion_example(prompt)

    elif command == "stream":
        if len(sys.argv) < 3:
            print("Error: stream requires a prompt")
            print('Usage: stream "<prompt>"')
            sys.exit(1)

        prompt = " ".join(sys.argv[2:])

        print("Streaming chat completion...")
        print(f"Prompt: {prompt}")
        print()

        results = await streaming_completion_example(prompt)

    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: chat, stream")
        sys.exit(1)

    print()
    print("=" * 80)
    print("✓ Example completed successfully")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
