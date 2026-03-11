"""
Unit tests for TokenCounter.

Tests the token counting utility with both tiktoken-based counting
and fallback heuristics when tiktoken is unavailable.
"""

import pytest
from kaizen.core.token_counter import (
    MODEL_CONTEXT_SIZES,
    TIKTOKEN_AVAILABLE,
    TokenCounter,
    count_tokens,
    get_token_counter,
)


class TestTokenCounter:
    """Tests for TokenCounter class."""

    def test_count_empty_string_returns_zero(self):
        """Test that empty string returns 0 tokens."""
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_count_simple_text(self):
        """Test counting tokens in simple text."""
        counter = TokenCounter()
        # "Hello, world!" should be 4 tokens in most encodings
        tokens = counter.count("Hello, world!")
        assert tokens > 0
        assert tokens < 10  # Should be 4-5 tokens

    def test_count_with_model_specified(self):
        """Test counting with specific model."""
        counter = TokenCounter()
        tokens = counter.count("Hello, world!", model="gpt-4")
        assert tokens > 0

    def test_count_with_encoding_specified(self):
        """Test counting with explicit encoding."""
        counter = TokenCounter()
        tokens = counter.count("Hello, world!", encoding_name="cl100k_base")
        assert tokens > 0

    def test_count_long_text(self):
        """Test counting tokens in longer text."""
        counter = TokenCounter()
        long_text = "This is a test sentence. " * 100
        tokens = counter.count(long_text)
        # Should be roughly 100 * 6 = 600 tokens (6 tokens per sentence)
        assert tokens > 400
        assert tokens < 1000

    def test_encoding_for_gpt4_models(self):
        """Test correct encoding for GPT-4 models."""
        counter = TokenCounter()
        encoding = counter._get_encoding_for_model("gpt-4")
        assert encoding == "cl100k_base"

        encoding = counter._get_encoding_for_model("gpt-4-turbo")
        assert encoding == "cl100k_base"

    def test_encoding_for_gpt4o_models(self):
        """Test correct encoding for GPT-4o models."""
        counter = TokenCounter()
        encoding = counter._get_encoding_for_model("gpt-4o")
        assert encoding == "o200k_base"

        encoding = counter._get_encoding_for_model("gpt-4o-mini")
        assert encoding == "o200k_base"

    def test_encoding_for_claude_models(self):
        """Test encoding for Claude models (approximation)."""
        counter = TokenCounter()
        encoding = counter._get_encoding_for_model("claude-3-sonnet")
        assert encoding == "cl100k_base"  # Approximation

        encoding = counter._get_encoding_for_model("claude-sonnet-4")
        assert encoding == "cl100k_base"

    def test_encoding_for_unknown_model(self):
        """Test default encoding for unknown models."""
        counter = TokenCounter()
        encoding = counter._get_encoding_for_model("some-unknown-model")
        assert encoding == "cl100k_base"  # Default

    def test_context_size_gpt4(self):
        """Test context size for GPT-4 models."""
        counter = TokenCounter()
        assert counter.get_context_size("gpt-4") == 8192
        assert counter.get_context_size("gpt-4-turbo") == 128000
        assert counter.get_context_size("gpt-4o") == 128000

    def test_context_size_claude(self):
        """Test context size for Claude models."""
        counter = TokenCounter()
        assert counter.get_context_size("claude-3-opus") == 200000
        assert counter.get_context_size("claude-sonnet-4") == 200000

    def test_context_size_unknown_model(self):
        """Test default context size for unknown models."""
        counter = TokenCounter()
        assert counter.get_context_size("unknown-model") == 8192  # Default


class TestContextUsage:
    """Tests for context usage calculation."""

    def test_calculate_context_usage_empty(self):
        """Test context usage with empty text."""
        counter = TokenCounter()
        usage = counter.calculate_context_usage("", model="gpt-4")
        assert usage == 0.0

    def test_calculate_context_usage_small(self):
        """Test context usage with small text."""
        counter = TokenCounter()
        usage = counter.calculate_context_usage("Hello, world!", model="gpt-4")
        # gpt-4 has 8192 context, so small text should have low usage
        assert usage < 0.01

    def test_calculate_context_usage_custom_max(self):
        """Test context usage with custom max context."""
        counter = TokenCounter()
        usage = counter.calculate_context_usage(
            "Hello, world!",
            model="gpt-4",
            max_context=10,  # Very small max
        )
        # Should be high usage with small max
        assert usage > 0.1

    def test_calculate_context_usage_caps_at_1(self):
        """Test that context usage caps at 1.0."""
        counter = TokenCounter()
        long_text = "This is a test. " * 10000
        usage = counter.calculate_context_usage(
            long_text,
            model="gpt-4",
            max_context=100,
        )
        assert usage <= 1.0


class TestMessageCounting:
    """Tests for chat message token counting."""

    def test_count_messages_empty(self):
        """Test counting empty message list."""
        counter = TokenCounter()
        tokens = counter.count_messages([])
        # Base overhead (priming)
        assert tokens >= 3

    def test_count_messages_single(self):
        """Test counting single message."""
        counter = TokenCounter()
        messages = [{"role": "user", "content": "Hello!"}]
        tokens = counter.count_messages(messages, model="gpt-4")
        assert tokens > 0
        assert tokens < 20

    def test_count_messages_multiple(self):
        """Test counting multiple messages."""
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = counter.count_messages(messages, model="gpt-4")
        assert tokens > 10

    def test_count_messages_with_name(self):
        """Test counting messages with name field."""
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Hello!", "name": "Alice"},
        ]
        tokens = counter.count_messages(messages, model="gpt-4")
        assert tokens > 0


class TestTruncation:
    """Tests for text truncation."""

    def test_truncate_short_text_unchanged(self):
        """Test that short text is not truncated."""
        counter = TokenCounter()
        text = "Hello!"
        truncated = counter.truncate_to_limit(text, max_tokens=100, model="gpt-4")
        assert truncated == text

    def test_truncate_long_text_end(self):
        """Test truncation from end."""
        counter = TokenCounter()
        long_text = "This is a test sentence. " * 100
        truncated = counter.truncate_to_limit(
            long_text, max_tokens=50, model="gpt-4", strategy="end"
        )
        assert len(truncated) < len(long_text)
        assert truncated.endswith("...")

    def test_truncate_long_text_start(self):
        """Test truncation from start."""
        counter = TokenCounter()
        long_text = "This is a test sentence. " * 100
        truncated = counter.truncate_to_limit(
            long_text, max_tokens=50, model="gpt-4", strategy="start"
        )
        assert len(truncated) < len(long_text)
        assert truncated.startswith("...")

    def test_truncate_long_text_middle(self):
        """Test truncation from middle."""
        counter = TokenCounter()
        long_text = "This is a test sentence. " * 100
        truncated = counter.truncate_to_limit(
            long_text, max_tokens=50, model="gpt-4", strategy="middle"
        )
        assert len(truncated) < len(long_text)
        assert "..." in truncated


class TestFallbackEstimation:
    """Tests for fallback token estimation when tiktoken unavailable."""

    def test_fallback_estimation_basic(self):
        """Test fallback estimation produces reasonable results."""
        counter = TokenCounter()
        # Test the fallback method directly
        tokens = counter._estimate_tokens("Hello, world!")
        # Should be roughly 4 tokens (13 chars / 4 = 3.25 + word adjustment)
        assert tokens >= 3
        assert tokens <= 10

    def test_fallback_estimation_long_text(self):
        """Test fallback estimation for longer text."""
        counter = TokenCounter()
        text = "This is a longer test sentence that has many more words."
        tokens = counter._estimate_tokens(text)
        # Should be roughly len/4 + word adjustment
        assert tokens > 10
        assert tokens < 50

    def test_fallback_estimation_empty(self):
        """Test fallback estimation for empty string."""
        counter = TokenCounter()
        tokens = counter._estimate_tokens("")
        assert tokens == 0


class TestGlobalCounter:
    """Tests for global counter singleton."""

    def test_get_token_counter_returns_instance(self):
        """Test that get_token_counter returns TokenCounter."""
        counter = get_token_counter()
        assert isinstance(counter, TokenCounter)

    def test_get_token_counter_is_singleton(self):
        """Test that get_token_counter returns same instance."""
        counter1 = get_token_counter()
        counter2 = get_token_counter()
        assert counter1 is counter2

    def test_count_tokens_convenience_function(self):
        """Test convenience function."""
        tokens = count_tokens("Hello, world!")
        assert tokens > 0
        assert tokens < 10

    def test_count_tokens_with_model(self):
        """Test convenience function with model."""
        tokens = count_tokens("Hello, world!", model="gpt-4")
        assert tokens > 0


class TestEncoderCaching:
    """Tests for encoder caching."""

    def test_encoder_caching(self):
        """Test that encoders are cached."""
        counter = TokenCounter()
        # First call should create encoder
        encoder1 = counter._get_encoder("cl100k_base")
        # Second call should return cached
        encoder2 = counter._get_encoder("cl100k_base")
        if encoder1 is not None:
            assert encoder1 is encoder2


@pytest.mark.skipif(
    not TIKTOKEN_AVAILABLE,
    reason="tiktoken not installed - tests require tiktoken",
)
class TestTiktokenSpecific:
    """Tests that specifically require tiktoken."""

    def test_tiktoken_exact_count(self):
        """Test exact token count with tiktoken."""
        counter = TokenCounter()
        # "Hello, world!" is exactly 4 tokens in cl100k_base
        tokens = counter.count("Hello, world!", encoding_name="cl100k_base")
        assert tokens == 4

    def test_tiktoken_encoding_for_model(self):
        """Test tiktoken-based encoding selection."""
        import tiktoken

        counter = TokenCounter()
        # Get encoding directly from tiktoken
        expected = tiktoken.encoding_for_model("gpt-4")
        actual = counter._get_encoder("cl100k_base")
        assert actual is not None
        # Verify they produce same result
        text = "Test text"
        assert len(expected.encode(text)) == len(actual.encode(text))


class TestModelContextSizes:
    """Tests for model context size mapping."""

    def test_model_context_sizes_exist(self):
        """Test that context size map is populated."""
        assert len(MODEL_CONTEXT_SIZES) > 0

    def test_context_sizes_are_positive(self):
        """Test that all context sizes are positive."""
        for model, size in MODEL_CONTEXT_SIZES.items():
            assert size > 0, f"Model {model} has non-positive context size"

    def test_gpt4o_has_large_context(self):
        """Test GPT-4o models have large context."""
        assert MODEL_CONTEXT_SIZES.get("gpt-4o", 0) >= 100000

    def test_claude_has_large_context(self):
        """Test Claude models have large context."""
        assert MODEL_CONTEXT_SIZES.get("claude-3-opus", 0) >= 100000
