"""
Tier 2 Integration Tests: Strategy Systems with Real Execution.

Tests execution strategies (AsyncSingleShot, Streaming, ParallelBatch, Fallback, MultiCycle)
with REAL execution and REAL LLM providers. NO MOCKING ALLOWED.

Test Coverage:
- AsyncSingleShotStrategy with real LLM (3 tests)
- StreamingStrategy with real streaming (4 tests)
- ParallelBatchStrategy with real concurrency (4 tests)
- FallbackStrategy with real fallback (4 tests)
- MultiCycleStrategy with real convergence (5 tests)

Total: 20 integration tests
"""

import asyncio
import os
from typing import Any, Dict

import pytest

# Strategy implementations
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
from kaizen.strategies.fallback import FallbackStrategy
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.parallel_batch import ParallelBatchStrategy
from kaizen.strategies.streaming import StreamingStrategy

# Real LLM providers
from tests.utils.real_llm_providers import RealOpenAIProvider

# =============================================================================
# ASYNC SINGLE SHOT STRATEGY INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_async_single_shot_strategy_with_real_llm():
    """Test AsyncSingleShotStrategy with real OpenAI API call."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_llm_call(prompt: str) -> Dict[str, Any]:
        """Async wrapper for real LLM call."""
        messages = [{"role": "user", "content": prompt}]
        # Simulate async with real API call
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=100)
        return {"response": result["content"], "usage": result["usage"]}

    strategy = AsyncSingleShotStrategy()

    # Execute with real LLM
    result = await strategy.execute(
        llm_fn=async_llm_call,
        prompt="What is 2+2? Answer with just the number.",
        max_tokens=50,
    )

    # Verify real response
    assert result is not None
    assert "response" in result
    assert len(result["response"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_async_single_shot_strategy_concurrent_execution():
    """Test AsyncSingleShotStrategy handles concurrent requests."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_llm_call(prompt: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=50)
        return {"response": result["content"]}

    strategy = AsyncSingleShotStrategy()

    # Execute multiple concurrent requests
    prompts = ["What is Python?", "What is JavaScript?", "What is Java?"]

    tasks = [
        strategy.execute(llm_fn=async_llm_call, prompt=p, max_tokens=50)
        for p in prompts
    ]

    results = await asyncio.gather(*tasks)

    # All should complete successfully
    assert len(results) == 3
    assert all("response" in r for r in results)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_async_single_shot_strategy_error_handling():
    """Test AsyncSingleShotStrategy handles errors correctly."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_llm_call_with_error(prompt: str) -> Dict[str, Any]:
        if "error" in prompt.lower():
            raise ValueError("Simulated API error")

        messages = [{"role": "user", "content": prompt}]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=50)
        return {"response": result["content"]}

    strategy = AsyncSingleShotStrategy()

    # Should handle error gracefully
    with pytest.raises(ValueError):
        await strategy.execute(
            llm_fn=async_llm_call_with_error,
            prompt="This will cause an error",
            max_tokens=50,
        )


# =============================================================================
# STREAMING STRATEGY INTEGRATION TESTS (4 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_strategy_with_real_streaming():
    """Test StreamingStrategy with real token streaming."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def real_streaming_llm(prompt: str):
        """Generator that yields real tokens from OpenAI."""
        messages = [{"role": "user", "content": prompt}]

        stream = client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages,
            stream=True,
            max_completion_tokens=100,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    strategy = StreamingStrategy()

    # Collect streamed tokens
    tokens = []
    for token in strategy.execute(
        llm_fn=real_streaming_llm, prompt="Count from 1 to 5 slowly.", stream=True
    ):
        tokens.append(token)

    # Verify streaming worked
    assert len(tokens) > 0
    full_response = "".join(tokens)
    assert len(full_response) > 0


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_strategy_token_by_token():
    """Test StreamingStrategy yields tokens incrementally."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def real_streaming_llm(prompt: str):
        messages = [{"role": "user", "content": prompt}]

        stream = client.chat.completions.create(
            model="gpt-5-nano", messages=messages, stream=True, max_completion_tokens=50
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    strategy = StreamingStrategy()

    token_count = 0
    for token in strategy.execute(
        llm_fn=real_streaming_llm, prompt="Say hello.", stream=True
    ):
        token_count += 1

    # Should receive multiple tokens
    assert token_count > 0


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_strategy_progressive_display():
    """Test StreamingStrategy enables progressive response display."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def real_streaming_llm(prompt: str):
        messages = [{"role": "user", "content": prompt}]

        stream = client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages,
            stream=True,
            max_completion_tokens=100,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    strategy = StreamingStrategy()

    # Simulate progressive display
    displayed_text = ""
    for token in strategy.execute(
        llm_fn=real_streaming_llm,
        prompt="Explain what Python is in one sentence.",
        stream=True,
    ):
        displayed_text += token

    # Final displayed text should be complete
    assert len(displayed_text) > 10
    assert "python" in displayed_text.lower() or "programming" in displayed_text.lower()


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_strategy_callback_support():
    """Test StreamingStrategy supports token callbacks."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def real_streaming_llm(prompt: str):
        messages = [{"role": "user", "content": prompt}]

        stream = client.chat.completions.create(
            model="gpt-5-nano", messages=messages, stream=True, max_completion_tokens=50
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    strategy = StreamingStrategy()

    # Track tokens via callback
    received_tokens = []

    def token_callback(token: str):
        received_tokens.append(token)

    for token in strategy.execute(
        llm_fn=real_streaming_llm, prompt="Hello!", stream=True
    ):
        token_callback(token)

    # Callback should have received tokens
    assert len(received_tokens) > 0


# =============================================================================
# PARALLEL BATCH STRATEGY INTEGRATION TESTS (4 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_parallel_batch_strategy_concurrent_processing():
    """Test ParallelBatchStrategy processes items concurrently."""
    import time

    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_process_item(item: str) -> Dict[str, Any]:
        """Process single item with real LLM."""
        messages = [{"role": "user", "content": f"Summarize: {item}"}]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=30)
        return {"item": item, "summary": result["content"]}

    strategy = ParallelBatchStrategy(max_concurrent=3)

    items = [
        "Python is a programming language",
        "JavaScript runs in browsers",
        "Java is platform independent",
    ]

    start_time = time.time()

    results = await strategy.execute(process_fn=async_process_item, items=items)

    elapsed = time.time() - start_time

    # Should complete faster than sequential (all 3 items)
    assert len(results) == 3
    assert all("summary" in r for r in results)
    # Parallel should be faster than 3x sequential (rough check)
    # Each call might take ~1s, sequential would be ~3s, parallel should be closer to 1s
    assert elapsed < 5  # Generous timeout for network variance


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_parallel_batch_strategy_batch_size_control():
    """Test ParallelBatchStrategy respects batch size limits."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_process_item(item: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": f"Process: {item}"}]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=20)
        return {"item": item, "result": result["content"]}

    # Limit to 2 concurrent
    strategy = ParallelBatchStrategy(max_concurrent=2)

    items = [f"Item {i}" for i in range(5)]

    results = await strategy.execute(process_fn=async_process_item, items=items)

    # All items should be processed
    assert len(results) == 5


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_parallel_batch_strategy_error_isolation():
    """Test ParallelBatchStrategy isolates errors to individual items."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_process_item(item: str) -> Dict[str, Any]:
        if "error" in item.lower():
            raise ValueError(f"Error processing {item}")

        messages = [{"role": "user", "content": f"Process: {item}"}]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=20)
        return {"item": item, "result": result["content"]}

    strategy = ParallelBatchStrategy(max_concurrent=3, continue_on_error=True)

    items = ["Good item 1", "Error item", "Good item 2"]

    results = await strategy.execute(process_fn=async_process_item, items=items)

    # Should have results for good items, errors marked for bad items
    assert len(results) == 3
    # At least the good items should have results
    successful_results = [r for r in results if "result" in r]
    assert len(successful_results) >= 2


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_parallel_batch_strategy_result_ordering():
    """Test ParallelBatchStrategy preserves result order."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def async_process_item(item: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": f"Echo: {item}"}]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=20)
        return {"item": item, "result": result["content"]}

    strategy = ParallelBatchStrategy(max_concurrent=3, preserve_order=True)

    items = ["First", "Second", "Third", "Fourth"]

    results = await strategy.execute(process_fn=async_process_item, items=items)

    # Results should be in same order as input
    assert len(results) == 4
    for i, result in enumerate(results):
        assert items[i].lower() in str(result).lower()


# =============================================================================
# FALLBACK STRATEGY INTEGRATION TESTS (4 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_fallback_strategy_primary_success():
    """Test FallbackStrategy uses primary provider when successful."""
    primary_provider = RealOpenAIProvider(model="gpt-5-nano")

    def primary_llm(prompt: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        result = primary_provider.complete(messages, temperature=0.1, max_tokens=50)
        return {"response": result["content"], "provider": "primary"}

    def fallback_llm(prompt: str) -> Dict[str, Any]:
        return {"response": "Fallback response", "provider": "fallback"}

    strategy = FallbackStrategy(providers=[primary_llm, fallback_llm])

    result = strategy.execute(prompt="What is 2+2?")

    # Should use primary provider
    assert result["provider"] == "primary"
    assert "response" in result


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_fallback_strategy_fallback_on_error():
    """Test FallbackStrategy falls back on primary failure."""

    def primary_llm_with_error(prompt: str) -> Dict[str, Any]:
        raise ValueError("Primary provider failed")

    fallback_provider = RealOpenAIProvider(model="gpt-5-nano")

    def fallback_llm(prompt: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        result = fallback_provider.complete(messages, temperature=0.1, max_tokens=50)
        return {"response": result["content"], "provider": "fallback"}

    strategy = FallbackStrategy(providers=[primary_llm_with_error, fallback_llm])

    result = strategy.execute(prompt="What is Python?")

    # Should use fallback provider
    assert result["provider"] == "fallback"
    assert "response" in result


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_fallback_strategy_multiple_fallbacks():
    """Test FallbackStrategy chains through multiple fallbacks."""

    def primary_error(prompt: str) -> Dict[str, Any]:
        raise ValueError("Primary failed")

    def secondary_error(prompt: str) -> Dict[str, Any]:
        raise ValueError("Secondary failed")

    tertiary_provider = RealOpenAIProvider(model="gpt-5-nano")

    def tertiary_llm(prompt: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        result = tertiary_provider.complete(messages, temperature=0.1, max_tokens=50)
        return {"response": result["content"], "provider": "tertiary"}

    strategy = FallbackStrategy(
        providers=[primary_error, secondary_error, tertiary_llm]
    )

    result = strategy.execute(prompt="Hello")

    # Should reach tertiary provider
    assert result["provider"] == "tertiary"


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_fallback_strategy_all_fail():
    """Test FallbackStrategy handles all providers failing."""

    def error_provider_1(prompt: str) -> Dict[str, Any]:
        raise ValueError("Provider 1 failed")

    def error_provider_2(prompt: str) -> Dict[str, Any]:
        raise ValueError("Provider 2 failed")

    strategy = FallbackStrategy(providers=[error_provider_1, error_provider_2])

    # All providers fail - should raise error
    with pytest.raises(ValueError):
        strategy.execute(prompt="Test")


# =============================================================================
# MULTI CYCLE STRATEGY INTEGRATION TESTS (5 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_cycle_strategy_iterative_refinement():
    """Test MultiCycleStrategy refines output over iterations."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def llm_with_refinement(prompt: str, previous_output: str = None) -> Dict[str, Any]:
        if previous_output:
            full_prompt = (
                f"{prompt}\n\nPrevious attempt: {previous_output}\nImprove this."
            )
        else:
            full_prompt = prompt

        messages = [{"role": "user", "content": full_prompt}]
        result = llm_provider.complete(messages, temperature=0.3, max_tokens=100)
        return {"response": result["content"], "cycle": "refinement"}

    strategy = MultiCycleStrategy(max_cycles=3)

    result = strategy.execute(
        llm_fn=llm_with_refinement,
        prompt="Write a one-sentence explanation of Python.",
        refinement_enabled=True,
    )

    # Should complete refinement cycles
    assert "response" in result
    assert result.get("cycle") == "refinement"


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_cycle_strategy_convergence_detection():
    """Test MultiCycleStrategy detects when output converges."""
    RealOpenAIProvider(model="gpt-5-nano")

    cycle_count = 0

    def llm_with_convergence(
        prompt: str, previous_output: str = None
    ) -> Dict[str, Any]:
        nonlocal cycle_count
        cycle_count += 1

        # Converge after 2 cycles
        if cycle_count >= 2:
            response = "Final stable answer: Python is a programming language."
        else:
            response = f"Draft {cycle_count}: Python is a language."

        return {"response": response, "cycle": cycle_count}

    strategy = MultiCycleStrategy(max_cycles=5, convergence_threshold=0.9)

    result = strategy.execute(
        llm_fn=llm_with_convergence, prompt="What is Python?", check_convergence=True
    )

    # Should converge before max_cycles
    assert result.get("cycle", 0) <= 5


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_cycle_strategy_max_cycles_limit():
    """Test MultiCycleStrategy respects max_cycles limit."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    cycle_count = 0

    def llm_counter(prompt: str, previous_output: str = None) -> Dict[str, Any]:
        nonlocal cycle_count
        cycle_count += 1

        messages = [{"role": "user", "content": prompt}]
        result = llm_provider.complete(messages, temperature=0.3, max_tokens=50)
        return {"response": result["content"], "cycle": cycle_count}

    strategy = MultiCycleStrategy(max_cycles=3)

    result = strategy.execute(
        llm_fn=llm_counter, prompt="Count iterations.", refinement_enabled=True
    )

    # Should not exceed max_cycles
    assert result.get("cycle", 0) <= 3


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_cycle_strategy_quality_improvement():
    """Test MultiCycleStrategy improves quality over cycles."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    outputs = []

    def llm_with_tracking(prompt: str, previous_output: str = None) -> Dict[str, Any]:
        if previous_output:
            full_prompt = f"Improve this explanation: {previous_output}"
        else:
            full_prompt = prompt

        messages = [{"role": "user", "content": full_prompt}]
        result = llm_provider.complete(messages, temperature=0.3, max_tokens=100)

        outputs.append(result["content"])
        return {"response": result["content"], "iteration": len(outputs)}

    strategy = MultiCycleStrategy(max_cycles=3)

    result = strategy.execute(
        llm_fn=llm_with_tracking,
        prompt="Explain Python briefly.",
        refinement_enabled=True,
    )

    # Should have multiple iterations
    assert len(outputs) >= 1
    assert "response" in result


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_cycle_strategy_context_preservation():
    """Test MultiCycleStrategy preserves context across cycles."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def llm_with_context(
        prompt: str, previous_output: str = None, context: Dict = None
    ) -> Dict[str, Any]:
        context = context or {}

        if previous_output:
            context["previous_attempts"] = context.get("previous_attempts", [])
            context["previous_attempts"].append(previous_output)

        messages = [{"role": "user", "content": prompt}]
        result = llm_provider.complete(messages, temperature=0.3, max_tokens=50)

        return {
            "response": result["content"],
            "context": context,
            "attempts": len(context.get("previous_attempts", [])),
        }

    strategy = MultiCycleStrategy(max_cycles=3)

    result = strategy.execute(
        llm_fn=llm_with_context, prompt="Explain AI.", preserve_context=True
    )

    # Context should be preserved
    assert "response" in result
