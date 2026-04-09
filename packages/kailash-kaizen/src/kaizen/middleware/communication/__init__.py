"""
AI-Powered Communication Middleware (placeholder)

This package was provisioned for AI-powered communication components to be
migrated from Core SDK to Kaizen. No modules currently live here — the
previous ``ai_chat`` module was removed as dead code because it depended on
Core SDK middleware internals (``AgentUIMiddleware``, ``DynamicSchemaRegistry``)
that were never re-exported, and its intent-classification path used
code-side keyword matching in violation of Kaizen's LLM-first rule.

When AI chat functionality is re-introduced, it MUST use Kaizen signatures
for routing, classification, and extraction — not deterministic keyword
matching.
"""

__all__: list[str] = []
