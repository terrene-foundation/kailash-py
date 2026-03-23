"""LLM provider adapters for the Delegate.

Each adapter implements the LLMAdapter protocol, providing model-agnostic
streaming completions. The Delegate doesn't know which LLM provider is
being used — it just calls the adapter.

Current:
    openai_stream.py — OpenAI SSE stream processing (moved from kz/cli/stream.py)

Planned:
    openai.py — Full OpenAI adapter (extract from loop.py's AsyncOpenAI usage)
    anthropic.py — Anthropic adapter (wire to kailash-kaizen's Anthropic provider)
    google.py — Google Gemini adapter
    ollama.py — Ollama local model adapter
"""
