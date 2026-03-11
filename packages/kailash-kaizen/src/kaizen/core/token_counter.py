"""
Token counting utility for accurate context window management.

Provides accurate token counting using tiktoken for OpenAI and Anthropic models,
with fallback heuristics for unknown models.

Key features:
- Model-specific tokenizers via tiktoken
- Encoder caching for performance
- Fallback estimates when tiktoken unavailable
- Support for OpenAI, Anthropic, and other model families

Usage:
    >>> from kaizen.core.token_counter import TokenCounter
    >>> counter = TokenCounter()
    >>> tokens = counter.count("Hello, world!", model="gpt-4")
    >>> print(f"{tokens} tokens")
    4 tokens

    >>> # Context usage check
    >>> usage = counter.calculate_context_usage(
    ...     text="...",
    ...     model="gpt-4",
    ...     max_context=128000
    ... )
    >>> if usage >= 0.92:
    ...     print("Time to compress context!")

Author: Kaizen Framework Team
Created: 2025-12-30
"""

import logging
from functools import lru_cache
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Check tiktoken availability
try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None  # type: ignore


# Model to tiktoken encoding mapping
# Based on OpenAI's published model-encoding relationships
MODEL_ENCODING_MAP = {
    # GPT-4 family (uses cl100k_base)
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4-turbo-preview": "cl100k_base",
    "gpt-4-vision-preview": "cl100k_base",
    "gpt-4o": "o200k_base",  # GPT-4o uses newer encoding
    "gpt-4o-mini": "o200k_base",
    "gpt-4o-2024-08-06": "o200k_base",
    "gpt-4o-mini-2024-07-18": "o200k_base",
    # GPT-3.5 family (uses cl100k_base)
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5-turbo-16k": "cl100k_base",
    "gpt-35-turbo": "cl100k_base",  # Azure naming
    # Embedding models
    "text-embedding-ada-002": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
    # Legacy models (uses older encodings)
    "davinci": "p50k_base",
    "curie": "p50k_base",
    "babbage": "p50k_base",
    "ada": "p50k_base",
    "text-davinci-003": "p50k_base",
    "text-davinci-002": "p50k_base",
    # Anthropic models (use cl100k_base as approximation)
    "claude-3-opus": "cl100k_base",
    "claude-3-sonnet": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "claude-3-5-sonnet": "cl100k_base",
    "claude-3-5-haiku": "cl100k_base",
    "claude-sonnet-4": "cl100k_base",
    "claude-opus-4": "cl100k_base",
    # Ollama models (use cl100k_base as approximation)
    "llama3.2": "cl100k_base",
    "llama3.2:1b": "cl100k_base",
    "llama3.2:3b": "cl100k_base",
    "llama2": "cl100k_base",
    "mistral": "cl100k_base",
    "mixtral": "cl100k_base",
    "codellama": "cl100k_base",
    "llava": "cl100k_base",
    "bakllava": "cl100k_base",
}

# Model context window sizes (max tokens)
MODEL_CONTEXT_SIZES = {
    # GPT-4 family
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4-vision-preview": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4o-2024-08-06": 128000,
    "gpt-4o-mini-2024-07-18": 128000,
    # GPT-3.5 family
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "gpt-35-turbo": 16385,
    # Claude models
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    "claude-sonnet-4": 200000,
    "claude-opus-4": 200000,
    # Ollama models (varies by model)
    "llama3.2": 128000,
    "llama3.2:1b": 128000,
    "llama3.2:3b": 128000,
    "llama2": 4096,
    "mistral": 32768,
    "mixtral": 32768,
    # Default
    "default": 8192,
}


class TokenCounter:
    """
    Token counter with tiktoken support and fallback heuristics.

    Provides accurate token counting for OpenAI and Anthropic models using
    tiktoken. Falls back to character-based estimates when tiktoken is not
    available or for unknown models.

    Attributes:
        default_encoding: Default tiktoken encoding to use
        fallback_chars_per_token: Characters per token for fallback estimation

    Example:
        >>> counter = TokenCounter()
        >>> # Count tokens in text
        >>> tokens = counter.count("Hello, world!", model="gpt-4")
        >>> print(f"{tokens} tokens")
        4 tokens

        >>> # Get context usage percentage
        >>> usage = counter.calculate_context_usage(
        ...     text="...",
        ...     model="gpt-4",
        ...     max_context=8192
        ... )
        >>> print(f"Context usage: {usage:.1%}")
        Context usage: 45.2%

        >>> # Count messages in chat format
        >>> messages = [
        ...     {"role": "system", "content": "You are helpful."},
        ...     {"role": "user", "content": "Hello!"}
        ... ]
        >>> tokens = counter.count_messages(messages, model="gpt-4")
    """

    def __init__(
        self,
        default_encoding: str = "cl100k_base",
        fallback_chars_per_token: float = 4.0,
    ):
        """
        Initialize token counter.

        Args:
            default_encoding: Default tiktoken encoding to use
            fallback_chars_per_token: Average characters per token for fallback
                                     estimation (default: 4.0)
        """
        self.default_encoding = default_encoding
        self.fallback_chars_per_token = fallback_chars_per_token
        self._encoder_cache: Dict[str, Any] = {}
        self._tiktoken_warning_shown = False

    @lru_cache(maxsize=32)
    def _get_encoding_for_model(self, model: str) -> str:
        """
        Get tiktoken encoding name for model.

        Args:
            model: Model name (e.g., "gpt-4", "claude-3-sonnet")

        Returns:
            Tiktoken encoding name
        """
        # Check exact match first
        if model in MODEL_ENCODING_MAP:
            return MODEL_ENCODING_MAP[model]

        # Check prefix matches for model families
        model_lower = model.lower()
        if model_lower.startswith("gpt-4o"):
            return "o200k_base"
        if model_lower.startswith("gpt-4"):
            return "cl100k_base"
        if model_lower.startswith("gpt-3.5"):
            return "cl100k_base"
        if model_lower.startswith("claude"):
            return "cl100k_base"  # Approximation

        # Default
        return self.default_encoding

    def _get_encoder(self, encoding_name: str) -> Optional[Any]:
        """
        Get or create cached tiktoken encoder.

        Args:
            encoding_name: Tiktoken encoding name

        Returns:
            Tiktoken encoder or None if unavailable
        """
        if not TIKTOKEN_AVAILABLE:
            return None

        if encoding_name not in self._encoder_cache:
            try:
                self._encoder_cache[encoding_name] = tiktoken.get_encoding(
                    encoding_name
                )
            except Exception as e:
                logger.warning(f"Failed to get encoder {encoding_name}: {e}")
                return None

        return self._encoder_cache[encoding_name]

    def count(
        self,
        text: str,
        model: Optional[str] = None,
        encoding_name: Optional[str] = None,
    ) -> int:
        """
        Count tokens in text.

        Uses tiktoken for accurate counting when available, falls back to
        character-based estimation otherwise.

        Args:
            text: Text to count tokens in
            model: Model name for model-specific encoding (optional)
            encoding_name: Explicit encoding name to use (overrides model)

        Returns:
            Token count

        Example:
            >>> counter = TokenCounter()
            >>> counter.count("Hello, world!", model="gpt-4")
            4
            >>> counter.count("Hello, world!")  # Uses default encoding
            4
        """
        if not text:
            return 0

        # Determine encoding
        if encoding_name:
            enc_name = encoding_name
        elif model:
            enc_name = self._get_encoding_for_model(model)
        else:
            enc_name = self.default_encoding

        # Try tiktoken first
        encoder = self._get_encoder(enc_name)
        if encoder:
            try:
                return len(encoder.encode(text))
            except Exception as e:
                logger.warning(f"Tiktoken encoding failed: {e}, using fallback")

        # Fallback: character-based estimate
        if not self._tiktoken_warning_shown:
            logger.warning(
                "Using character-based token estimation. "
                "Install tiktoken for accurate counting: pip install tiktoken"
            )
            self._tiktoken_warning_shown = True

        return self._estimate_tokens(text)

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using character heuristic.

        This is a fallback when tiktoken is unavailable. The estimation assumes
        approximately 4 characters per token, which is a reasonable average for
        English text.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Character-based estimate (roughly 4 chars per token for English)
        char_estimate = len(text) / self.fallback_chars_per_token

        # Word-based adjustment (add ~1 token per word boundary for special tokens)
        word_count = len(text.split())
        word_adjustment = word_count * 0.1

        return int(char_estimate + word_adjustment)

    def count_messages(
        self,
        messages: list,
        model: str = "gpt-4",
    ) -> int:
        """
        Count tokens in chat messages.

        Accounts for message formatting overhead (role, content keys, etc.).

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model name for encoding

        Returns:
            Total token count including overhead

        Example:
            >>> counter = TokenCounter()
            >>> messages = [
            ...     {"role": "system", "content": "You are helpful."},
            ...     {"role": "user", "content": "Hello!"}
            ... ]
            >>> counter.count_messages(messages, model="gpt-4")
            18
        """
        total_tokens = 0

        # Message overhead varies by model
        # GPT-4: ~4 tokens per message for formatting
        # This includes: <|im_start|>, role, <|im_sep|>, <|im_end|>
        tokens_per_message = 4
        tokens_per_name = -1  # Omit if no name

        for message in messages:
            total_tokens += tokens_per_message

            # Count content
            content = message.get("content", "")
            if isinstance(content, str):
                total_tokens += self.count(content, model=model)
            elif isinstance(content, list):
                # Multi-modal content (text + images)
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total_tokens += self.count(part["text"], model=model)
                    # Image tokens would be estimated separately

            # Count role
            role = message.get("role", "")
            total_tokens += self.count(role, model=model)

            # Count name if present
            if "name" in message:
                total_tokens += tokens_per_name
                total_tokens += self.count(message["name"], model=model)

        # Add priming tokens (varies by model)
        total_tokens += 3  # Assistant priming

        return total_tokens

    def get_context_size(self, model: str) -> int:
        """
        Get context window size for model.

        Args:
            model: Model name

        Returns:
            Context window size in tokens
        """
        if model in MODEL_CONTEXT_SIZES:
            return MODEL_CONTEXT_SIZES[model]

        # Check prefix matches
        model_lower = model.lower()
        if model_lower.startswith("gpt-4o"):
            return 128000
        if model_lower.startswith("gpt-4"):
            return 128000
        if model_lower.startswith("gpt-3.5"):
            return 16385
        if model_lower.startswith("claude"):
            return 200000

        return MODEL_CONTEXT_SIZES["default"]

    def calculate_context_usage(
        self,
        text: str,
        model: Optional[str] = None,
        max_context: Optional[int] = None,
    ) -> float:
        """
        Calculate context window usage percentage.

        Args:
            text: Text to check
            model: Model name for context size and encoding
            max_context: Override max context size (optional)

        Returns:
            Float between 0.0 and 1.0 representing usage percentage

        Example:
            >>> counter = TokenCounter()
            >>> usage = counter.calculate_context_usage(
            ...     text="Hello, world!",
            ...     model="gpt-4"
            ... )
            >>> print(f"Usage: {usage:.1%}")
            Usage: 0.0%
        """
        token_count = self.count(text, model=model)

        if max_context is None:
            max_context = self.get_context_size(model or "default")

        if max_context <= 0:
            return 0.0

        usage = token_count / max_context
        return min(usage, 1.0)  # Cap at 100%

    def truncate_to_limit(
        self,
        text: str,
        max_tokens: int,
        model: Optional[str] = None,
        strategy: str = "end",
    ) -> str:
        """
        Truncate text to fit within token limit.

        Args:
            text: Text to truncate
            max_tokens: Maximum tokens allowed
            model: Model name for encoding
            strategy: Truncation strategy ('end', 'start', 'middle')

        Returns:
            Truncated text

        Example:
            >>> counter = TokenCounter()
            >>> truncated = counter.truncate_to_limit(
            ...     "This is a very long text...",
            ...     max_tokens=5,
            ...     model="gpt-4"
            ... )
        """
        current_tokens = self.count(text, model=model)

        if current_tokens <= max_tokens:
            return text

        # Estimate characters to keep
        ratio = max_tokens / current_tokens
        chars_to_keep = int(len(text) * ratio * 0.9)  # 10% safety margin

        if strategy == "end":
            # Keep beginning
            truncated = text[:chars_to_keep] + "..."
        elif strategy == "start":
            # Keep end
            truncated = "..." + text[-chars_to_keep:]
        else:  # middle
            # Keep beginning and end
            half = chars_to_keep // 2
            truncated = text[:half] + " ... " + text[-half:]

        # Iteratively trim if still too long
        while self.count(truncated, model=model) > max_tokens and len(truncated) > 10:
            chars_to_keep = int(len(truncated) * 0.9)
            if strategy == "end":
                truncated = truncated[:chars_to_keep] + "..."
            elif strategy == "start":
                truncated = "..." + truncated[-chars_to_keep:]
            else:
                half = chars_to_keep // 2
                truncated = truncated[:half] + " ... " + truncated[-half:]

        return truncated


# Global singleton for convenience
_global_counter: Optional[TokenCounter] = None


def get_token_counter() -> TokenCounter:
    """
    Get global token counter instance.

    Returns:
        TokenCounter singleton instance

    Example:
        >>> from kaizen.core.token_counter import get_token_counter
        >>> counter = get_token_counter()
        >>> tokens = counter.count("Hello!")
    """
    global _global_counter
    if _global_counter is None:
        _global_counter = TokenCounter()
    return _global_counter


def count_tokens(
    text: str,
    model: Optional[str] = None,
) -> int:
    """
    Convenience function to count tokens.

    Args:
        text: Text to count tokens in
        model: Model name for model-specific encoding

    Returns:
        Token count

    Example:
        >>> from kaizen.core.token_counter import count_tokens
        >>> tokens = count_tokens("Hello, world!", model="gpt-4")
        >>> print(f"{tokens} tokens")
    """
    return get_token_counter().count(text, model=model)


# Export public API
__all__ = [
    "TokenCounter",
    "get_token_counter",
    "count_tokens",
    "TIKTOKEN_AVAILABLE",
    "MODEL_CONTEXT_SIZES",
]
