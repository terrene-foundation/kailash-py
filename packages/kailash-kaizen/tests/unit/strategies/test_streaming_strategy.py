"""
Unit tests for StreamingStrategy.

Tests cover:
- Stream yields chunks
- execute returns final result with all chunks
- Different chunk sizes (1, 5, 10)
- Async iteration works
- Empty response handling
- Chunk count correct
- Response reconstruction correct
- Multiple sequential streams
"""

import pytest
from kaizen.strategies.streaming import StreamingStrategy


class MockAgent:
    """Mock agent for testing."""

    async def execute(self, inputs):
        """Mock execution."""
        return {
            "response": "This is a streaming response from the agent with multiple tokens."
        }


@pytest.mark.asyncio
async def test_stream_yields_chunks():
    """Test that stream yields chunks."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    chunks = []
    async for chunk in strategy.stream(agent, inputs):
        chunks.append(chunk)

    assert len(chunks) > 0, "Should yield at least one chunk"
    assert all(
        isinstance(chunk, str) for chunk in chunks
    ), "All chunks should be strings"


@pytest.mark.asyncio
async def test_execute_returns_final_result():
    """Test that execute returns final result with all chunks."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    result = await strategy.execute(agent, inputs)

    assert "response" in result, "Result should have response"
    assert "chunks" in result, "Result should have chunk count"
    assert "streamed" in result, "Result should indicate streaming"
    assert result["streamed"] is True
    assert isinstance(result["chunks"], int)
    assert result["chunks"] > 0


@pytest.mark.asyncio
async def test_chunk_size_1_token_by_token():
    """Test chunk_size=1 yields token-by-token."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    chunks = []
    async for chunk in strategy.stream(agent, inputs):
        chunks.append(chunk)

    # With chunk_size=1, we should get many small chunks
    assert (
        len(chunks) >= 10
    ), f"Expected many chunks with chunk_size=1, got {len(chunks)}"


@pytest.mark.asyncio
async def test_chunk_size_5():
    """Test chunk_size=5 yields 5-token chunks."""
    strategy = StreamingStrategy(chunk_size=5)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    chunks = []
    async for chunk in strategy.stream(agent, inputs):
        chunks.append(chunk)

    # With chunk_size=5, we should get fewer, larger chunks
    assert (
        len(chunks) >= 2
    ), f"Expected multiple chunks with chunk_size=5, got {len(chunks)}"
    assert (
        len(chunks) <= 10
    ), f"Expected fewer chunks with chunk_size=5, got {len(chunks)}"


@pytest.mark.asyncio
async def test_chunk_size_10():
    """Test chunk_size=10 yields large chunks."""
    strategy = StreamingStrategy(chunk_size=10)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    chunks = []
    async for chunk in strategy.stream(agent, inputs):
        chunks.append(chunk)

    # With chunk_size=10, we should get even fewer chunks
    assert len(chunks) >= 1, "Expected at least one chunk with chunk_size=10"


@pytest.mark.asyncio
async def test_async_iteration_works():
    """Test async iteration protocol works correctly."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    # Test that we can iterate normally
    count = 0
    async for chunk in strategy.stream(agent, inputs):
        count += 1
        assert isinstance(chunk, str)

    assert count > 0, "Should iterate at least once"


@pytest.mark.asyncio
async def test_chunk_count_correct():
    """Test that chunk count in result matches actual chunks."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    # Count chunks from stream
    stream_chunks = []
    async for chunk in strategy.stream(agent, inputs):
        stream_chunks.append(chunk)

    # Get result from execute
    result = await strategy.execute(agent, inputs)

    assert result["chunks"] == len(
        stream_chunks
    ), f"Chunk count mismatch: result={result['chunks']}, actual={len(stream_chunks)}"


@pytest.mark.asyncio
async def test_response_reconstruction_correct():
    """Test that response reconstruction is correct."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    # Get chunks from stream
    stream_chunks = []
    async for chunk in strategy.stream(agent, inputs):
        stream_chunks.append(chunk)

    # Get result from execute
    result = await strategy.execute(agent, inputs)

    # Reconstruct from chunks
    reconstructed = "".join(stream_chunks)

    assert (
        result["response"] == reconstructed
    ), f"Response mismatch:\nResult: {result['response']}\nReconstructed: {reconstructed}"


@pytest.mark.asyncio
async def test_multiple_sequential_streams():
    """Test multiple sequential streams work independently."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    # First stream
    chunks1 = []
    async for chunk in strategy.stream(agent, inputs):
        chunks1.append(chunk)

    # Second stream
    chunks2 = []
    async for chunk in strategy.stream(agent, inputs):
        chunks2.append(chunk)

    # Both should be independent and complete
    assert len(chunks1) > 0
    assert len(chunks2) > 0
    assert len(chunks1) == len(
        chunks2
    ), "Both streams should yield same number of chunks"


@pytest.mark.asyncio
async def test_different_chunk_sizes_give_different_chunk_counts():
    """Test that different chunk sizes yield different chunk counts."""
    agent = MockAgent()
    inputs = {"prompt": "test"}

    # Test chunk_size=1
    strategy1 = StreamingStrategy(chunk_size=1)
    chunks1 = []
    async for chunk in strategy1.stream(agent, inputs):
        chunks1.append(chunk)

    # Test chunk_size=5
    strategy5 = StreamingStrategy(chunk_size=5)
    chunks5 = []
    async for chunk in strategy5.stream(agent, inputs):
        chunks5.append(chunk)

    # Larger chunk size should give fewer chunks
    assert len(chunks1) > len(
        chunks5
    ), f"chunk_size=1 should give more chunks than chunk_size=5: {len(chunks1)} vs {len(chunks5)}"


@pytest.mark.asyncio
async def test_streaming_delay_exists():
    """Test that streaming has a delay (simulates real streaming)."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    import time

    start = time.time()

    chunks = []
    async for chunk in strategy.stream(agent, inputs):
        chunks.append(chunk)

    elapsed = time.time() - start

    # With 0.01s delay per chunk, should take at least 0.01 * num_chunks
    expected_min = 0.01 * len(chunks)
    assert (
        elapsed >= expected_min * 0.5
    ), f"Streaming should have delay: elapsed={elapsed:.3f}s, expected>={expected_min:.3f}s"


@pytest.mark.asyncio
async def test_execute_includes_streamed_flag():
    """Test that execute result includes streamed flag."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    result = await strategy.execute(agent, inputs)

    assert "streamed" in result
    assert result["streamed"] is True


@pytest.mark.asyncio
async def test_execute_includes_chunk_count():
    """Test that execute result includes chunk count."""
    strategy = StreamingStrategy(chunk_size=1)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    result = await strategy.execute(agent, inputs)

    assert "chunks" in result
    assert isinstance(result["chunks"], int)
    assert result["chunks"] > 0
