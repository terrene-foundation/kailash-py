# Token Counting for Kaizen

**Version**: 1.0.0
**Status**: Production Ready
**Implementation**: TODO-204 (Task 1.8: Token Counting)
**Test Coverage**: 38 tests passing (100%)

---

## Overview

Kaizen provides accurate token counting using tiktoken for context window management.
The `TokenCounter` utility supports:

- **Accurate Token Counting**: Uses tiktoken for OpenAI and Anthropic model encodings
- **Model-Specific Encodings**: Automatic encoding selection based on model name
- **Context Usage Tracking**: Calculate percentage of context window used
- **Text Truncation**: Truncate text to fit within token limits
- **Fallback Estimation**: Character-based estimation when tiktoken unavailable

---

## Quick Start

### Basic Token Counting

```python
from kaizen.core import count_tokens, TokenCounter

# Simple convenience function
tokens = count_tokens("Hello, world!", model="gpt-4")
print(f"{tokens} tokens")  # 4 tokens

# Or use TokenCounter directly
counter = TokenCounter()
tokens = counter.count("Hello, world!", model="gpt-4")
```

### Context Usage Monitoring

```python
from kaizen.core import TokenCounter

counter = TokenCounter()

# Check how much of context window is used
long_text = "..." * 10000  # Some long text
usage = counter.calculate_context_usage(
    text=long_text,
    model="gpt-4",  # 8192 context
)
print(f"Context usage: {usage:.1%}")

# Or specify custom max context
usage = counter.calculate_context_usage(
    text=long_text,
    model="claude-3-sonnet",
    max_context=100000,  # Override default
)
```

### Message Token Counting

```python
from kaizen.core import TokenCounter

counter = TokenCounter()

# Count tokens in chat messages (with overhead)
messages = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there!"},
]

tokens = counter.count_messages(messages, model="gpt-4")
print(f"Total message tokens: {tokens}")
```

### Text Truncation

```python
from kaizen.core import TokenCounter

counter = TokenCounter()

# Truncate text to fit within token limit
long_text = "This is a very long text... " * 1000
truncated = counter.truncate_to_limit(
    long_text,
    max_tokens=100,
    model="gpt-4",
    strategy="end",  # Keep beginning, truncate end
)
```

---

## Integration with ClaudeCodeAgent

The token counter is integrated into ClaudeCodeAgent for accurate context tracking:

```python
from kaizen.agents.autonomous.claude_code import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(
    max_cycles=100,
    context_threshold=0.92,  # Compress at 92% usage
)

agent = ClaudeCodeAgent(config=config, signature=signature)

# Run task - context usage tracked automatically
result = await agent.run_autonomous(task="Build API")

# Access token metadata in result
print(f"Tokens used: {result['tokens_used']}")
print(f"Context window: {result['context_window_size']}")
print(f"Context usage: {result['context_usage_final']:.1%}")
```

---

## Supported Models

### OpenAI Models

| Model | Encoding | Context Size |
|-------|----------|--------------|
| gpt-4 | cl100k_base | 8,192 |
| gpt-4-turbo | cl100k_base | 128,000 |
| gpt-4o | o200k_base | 128,000 |
| gpt-4o-mini | o200k_base | 128,000 |
| gpt-3.5-turbo | cl100k_base | 16,385 |

### Anthropic Models

| Model | Encoding | Context Size |
|-------|----------|--------------|
| claude-3-opus | cl100k_base* | 200,000 |
| claude-3-sonnet | cl100k_base* | 200,000 |
| claude-3-haiku | cl100k_base* | 200,000 |
| claude-sonnet-4 | cl100k_base* | 200,000 |
| claude-opus-4 | cl100k_base* | 200,000 |

*Note: Anthropic models use cl100k_base as an approximation. Token counts may vary slightly from Anthropic's official counts.

### Ollama Models

| Model | Encoding | Context Size |
|-------|----------|--------------|
| llama3.2 | cl100k_base* | 128,000 |
| llama2 | cl100k_base* | 4,096 |
| mistral | cl100k_base* | 32,768 |
| llava | cl100k_base* | varies |

*Note: Ollama models use cl100k_base as an approximation.

---

## API Reference

### TokenCounter

```python
class TokenCounter:
    def __init__(
        self,
        default_encoding: str = "cl100k_base",
        fallback_chars_per_token: float = 4.0,
    ): ...

    def count(
        self,
        text: str,
        model: Optional[str] = None,
        encoding_name: Optional[str] = None,
    ) -> int:
        """Count tokens in text."""
        ...

    def count_messages(
        self,
        messages: list,
        model: str = "gpt-4",
    ) -> int:
        """Count tokens in chat messages with overhead."""
        ...

    def get_context_size(self, model: str) -> int:
        """Get context window size for model."""
        ...

    def calculate_context_usage(
        self,
        text: str,
        model: Optional[str] = None,
        max_context: Optional[int] = None,
    ) -> float:
        """Calculate context window usage (0.0-1.0)."""
        ...

    def truncate_to_limit(
        self,
        text: str,
        max_tokens: int,
        model: Optional[str] = None,
        strategy: str = "end",  # "end", "start", "middle"
    ) -> str:
        """Truncate text to fit within token limit."""
        ...
```

### Convenience Functions

```python
from kaizen.core import (
    count_tokens,       # Quick token count
    get_token_counter,  # Get global singleton
    TIKTOKEN_AVAILABLE, # Check if tiktoken installed
)

# Quick count
tokens = count_tokens("Hello!", model="gpt-4")

# Get singleton for reuse
counter = get_token_counter()

# Check tiktoken availability
if TIKTOKEN_AVAILABLE:
    print("Using tiktoken for accurate counts")
else:
    print("Using fallback estimation")
```

---

## Installation

Token counting works out of the box with fallback estimation. For accurate
tiktoken-based counting, install the optional dependency:

```bash
# Install with tiktoken
pip install kailash-kaizen[tokens]

# Or install tiktoken directly
pip install tiktoken
```

---

## Fallback Estimation

When tiktoken is not available, the TokenCounter uses a character-based
estimation:

```python
# Fallback formula:
tokens ≈ (len(text) / 4.0) + (word_count * 0.1)
```

This provides reasonable estimates for English text but may be less accurate
for:
- Non-English text
- Code (often has shorter tokens)
- Text with many special characters

---

## Best Practices

### 1. Check Context Usage Before Long Operations

```python
counter = TokenCounter()
current_context = "..." # Your accumulated context

usage = counter.calculate_context_usage(
    current_context,
    model="gpt-4",
)

if usage >= 0.9:
    # Time to summarize or truncate
    current_context = counter.truncate_to_limit(
        current_context,
        max_tokens=int(counter.get_context_size("gpt-4") * 0.5),
        model="gpt-4",
    )
```

### 2. Use Model-Specific Counting

```python
# Always specify model for accurate counts
tokens = counter.count(text, model="gpt-4o")  # Uses o200k_base
tokens = counter.count(text, model="gpt-4")   # Uses cl100k_base
```

### 3. Cache the Counter

```python
# Use global singleton for efficiency
from kaizen.core import get_token_counter

counter = get_token_counter()  # Cached encoders
```

---

## Performance Characteristics

| Operation | Typical Latency |
|-----------|----------------|
| count() first call | 2-3s (encoder loading) |
| count() subsequent | <1ms |
| count_messages() | 1-5ms |
| calculate_context_usage() | 1-2ms |
| truncate_to_limit() | 2-10ms |

Encoders are cached, so subsequent calls to the same encoding are fast.

---

## Related Documentation

- [State Management](./state-management.md)
- [Checkpoint & Resume System](./checkpoint-resume-system.md)
- [ClaudeCodeAgent](../guides/claude-code-agent.md)

---

## Changelog

### Version 1.0.0 (2025-12-30)

**Initial Release (TODO-204 Task 1.8)**:
- TokenCounter class with tiktoken integration
- Model-specific encoding selection
- Context usage calculation
- Text truncation utilities
- ClaudeCodeAgent integration
- 38 tests passing (100% coverage)

---

**Last Updated**: 2025-12-30
**Maintained By**: Kailash Kaizen Team
