"""Shared default-model resolution — ``.env`` is the single source of truth.

Per the env-models rule, model names MUST come from the environment, never a
hardcoded literal at a call site. This module is the ONE place the default
model is resolved, reused by the LLM client and the ``api`` config layer so the
resolution logic never drifts across the package.
"""

from __future__ import annotations

import os

# Provider-intrinsic final fallback used ONLY when neither environment variable
# is set. Documented module-level named constant (env-models carve-out):
# overridable via ``OPENAI_PROD_MODEL`` / ``DEFAULT_LLM_MODEL`` below.
_FALLBACK_MODEL = "gpt-4o"


def resolve_default_model() -> str:
    """Resolve the default model name from the environment.

    Priority:
        1. ``OPENAI_PROD_MODEL``
        2. ``DEFAULT_LLM_MODEL``
        3. ``"gpt-4o"`` (provider-intrinsic final fallback)
    """
    return (
        os.environ.get("OPENAI_PROD_MODEL")
        or os.environ.get("DEFAULT_LLM_MODEL")
        or _FALLBACK_MODEL
    )
