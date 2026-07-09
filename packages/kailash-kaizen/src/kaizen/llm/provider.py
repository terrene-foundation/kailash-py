# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Model-identifier → provider resolution (`LlmProvider.from_model`).

The four-axis `LlmDeployment` (`deployment.py` + `presets.py`) is the
canonical description of HOW to talk to a provider (wire protocol,
endpoint, auth). `LlmProvider` is the thin, immutable *identity* layer
above it: given a model name (`"deepseek-chat"`, `"gpt-4o"`), which
provider serves it, and what are that provider's public coordinates —
`display_name`, `base_url`, `api_key_env_vars`, `capabilities`.

Cross-SDK parity: this is the Python equivalent of the Rust SDK's
`LlmProvider::from_model` (EATP D6 — matching semantics, idiomatic
implementation). `from_model` fails closed on an unrecognised prefix
with a typed `UnknownModelProvider(ValueError)` rather than silently
routing to a default provider.

Single-source-of-truth discipline (no parallel data):

* `capabilities` delegates to `kaizen.llm.capabilities.for_preset(name)`
  — the same table `LlmDeployment.supports()` reads.
* `api_key_env_vars` is pinned byte-for-byte to
  `presets.py::_FROM_ENV_PROVIDERS` by a cross-check invariant test.
* `base_url` is pinned to the matching `<provider>_preset` default
  endpoint by a cross-check invariant test.
* `deployment(...)` bridges to the registered preset factory via
  `presets.get_preset(name)` — it does NOT re-implement wire/auth/endpoint
  assembly, so a `from_model(...)` result has a real production path into
  an `LlmDeployment` (orphan-detection Rule 1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from kaizen.llm.capabilities import for_preset
from kaizen.llm.errors import MissingCredential

if TYPE_CHECKING:  # avoid importing the heavy presets module at import time
    from kaizen.llm.deployment import LlmDeployment


# Canonical per-provider base URLs. These are provider *identity*
# coordinates (stable infrastructure endpoints), NOT model names, so they
# are not an `env-models.md` violation. Each value is pinned to the
# matching `<provider>_preset` default endpoint by a cross-check test in
# `tests/unit/llm/test_llm_provider_from_model.py`.
OPENAI_BASE_URL = "https://api.openai.com"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class UnknownModelProvider(ValueError):
    """No provider could be resolved from a model identifier.

    Raised by :meth:`LlmProvider.from_model` when the model name matches
    no registered provider prefix. Fails closed (a `ValueError`) rather
    than routing to an arbitrary default — a silent default route is the
    exact fail-open the DeepSeek issue (#1609) reported (`from_model`
    raised `unknown prefix` before DeepSeek was registered).
    """

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(
            f"LLM provider detection failed for model {model!r}: unknown prefix. "
            f"Registered prefixes: {sorted(_PREFIX_TO_NAME)}."
        )


@dataclass(frozen=True)
class LlmProvider:
    """Immutable provider identity resolved from a model name.

    Construct via :meth:`from_model` / :meth:`from_name`, never directly —
    the registry (`_REGISTRY`) is the single source of provider entries.
    """

    name: str
    """Canonical preset literal — matches `LlmDeployment.preset_name` and
    the `presets.get_preset(name)` registry key (e.g. ``"deepseek"``)."""

    display_name: str
    """Human-readable provider name (e.g. ``"DeepSeek"``)."""

    base_url: str
    """Provider's public API base URL (no trailing slash)."""

    openai_compatible: bool
    """True when the provider speaks the OpenAI chat-completions wire
    schema (`WireProtocol.OpenAiChat`) — DeepSeek and OpenAI itself."""

    # Stored as tuples for immutability; exposed as fresh lists via the
    # public properties below so the frozen value object cannot be mutated
    # through its own accessors and each caller gets an independent copy.
    _api_key_env_vars: Tuple[str, ...]
    _model_prefixes: Tuple[str, ...]

    @property
    def api_key_env_vars(self) -> List[str]:
        """Env var names carrying this provider's API key, in precedence
        order. A fresh list per access (mutating it does not affect the
        registry)."""
        return list(self._api_key_env_vars)

    @property
    def model_prefixes(self) -> List[str]:
        """Model-name prefixes this provider serves (e.g. ``["deepseek-"]``)."""
        return list(self._model_prefixes)

    @property
    def capabilities(self) -> Dict[str, bool]:
        """Capability matrix for this provider.

        `chat` and `streaming` are True for every registered provider
        (all are chat-completions endpoints with SSE streaming). The
        deployment-surface capabilities (`tools`, `vision`, `batch`,
        `caching`, `audio`) delegate to
        :func:`kaizen.llm.capabilities.for_preset` — the single source of
        truth also read by :meth:`LlmDeployment.supports`. `openai_compatible`
        echoes the wire-schema flag. Returns a fresh dict per call.
        """
        caps: Dict[str, bool] = {
            "chat": True,
            "streaming": True,
            "openai_compatible": self.openai_compatible,
        }
        caps.update(for_preset(self.name))
        return caps

    @classmethod
    def from_model(cls, model: str) -> "LlmProvider":
        """Resolve the provider serving ``model`` by prefix, or raise.

        Matching is case-insensitive on the model-name prefix
        (``"deepseek-chat"`` / ``"deepseek-reasoner"`` → DeepSeek;
        ``"gpt-4o"`` → OpenAI; ``"claude-3"`` → Anthropic). An
        unrecognised prefix raises :class:`UnknownModelProvider` (fail
        closed) rather than defaulting.
        """
        if not isinstance(model, str) or not model.strip():
            raise UnknownModelProvider(model)
        lowered = model.strip().lower()
        for prefix, name in _PREFIX_TO_NAME.items():
            if lowered.startswith(prefix):
                return _REGISTRY[name]
        raise UnknownModelProvider(model)

    @classmethod
    def from_name(cls, name: str) -> "LlmProvider":
        """Look up a provider by its canonical preset literal (`"deepseek"`)."""
        try:
            return _REGISTRY[name]
        except KeyError as exc:
            raise UnknownModelProvider(name) from exc

    @classmethod
    def all(cls) -> Tuple["LlmProvider", ...]:
        """Every registered provider, in registration order."""
        return tuple(_REGISTRY.values())

    def deployment(
        self,
        api_key: Optional[str] = None,
        *,
        model: str,
    ) -> "LlmDeployment":
        """Build a concrete :class:`LlmDeployment` for this provider.

        Bridges to the registered preset factory
        (`presets.get_preset(self.name)`) — no wire/auth/endpoint logic is
        re-implemented here. ``api_key`` defaults to the first non-empty
        value among :attr:`api_key_env_vars`; if none is set a typed
        :class:`MissingCredential` is raised (never a silent unauthenticated
        client). ``model`` is required and is validated by the preset.
        """
        from kaizen.llm.presets import get_preset

        resolved_key = api_key
        if resolved_key is None:
            for var in self._api_key_env_vars:
                val = os.environ.get(var, "").strip()
                if val:
                    resolved_key = val
                    break
        if not resolved_key:
            raise MissingCredential(" or ".join(self._api_key_env_vars))

        factory = get_preset(self.name)
        return factory(resolved_key, model=model)


# ---------------------------------------------------------------------------
# Registry — the single source of provider identity entries.
# ---------------------------------------------------------------------------
#
# `name` MUST match a `presets.get_preset(name)` registry key AND the
# capability-table literal in `capabilities.py`. `_api_key_env_vars` is
# pinned to `_FROM_ENV_PROVIDERS`; `base_url` to the preset default — both
# by cross-check tests. New providers: add a row here + the matching preset
# + capability row (all three verified by the parity tests).
_REGISTRY: Dict[str, LlmProvider] = {
    "openai": LlmProvider(
        name="openai",
        display_name="OpenAI",
        base_url=OPENAI_BASE_URL,
        openai_compatible=True,
        _api_key_env_vars=("OPENAI_API_KEY",),
        _model_prefixes=("gpt-", "o1-", "o3-", "o4-"),
    ),
    "anthropic": LlmProvider(
        name="anthropic",
        display_name="Anthropic",
        base_url=ANTHROPIC_BASE_URL,
        openai_compatible=False,
        _api_key_env_vars=("ANTHROPIC_API_KEY",),
        _model_prefixes=("claude-",),
    ),
    "google": LlmProvider(
        name="google",
        display_name="Google",
        base_url=GOOGLE_BASE_URL,
        openai_compatible=False,
        _api_key_env_vars=("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        _model_prefixes=("gemini-",),
    ),
    "deepseek": LlmProvider(
        name="deepseek",
        display_name="DeepSeek",
        base_url=DEEPSEEK_BASE_URL,
        openai_compatible=True,
        _api_key_env_vars=("DEEPSEEK_API_KEY",),
        _model_prefixes=("deepseek-",),
    ),
}

# Prefix → provider-name lookup, built from the registry so it can never
# drift from `_REGISTRY`. Longer prefixes are naturally distinct here
# (no registered prefix is a prefix of another).
_PREFIX_TO_NAME: Dict[str, str] = {
    prefix: provider.name
    for provider in _REGISTRY.values()
    for prefix in provider._model_prefixes
}


__all__ = [
    "LlmProvider",
    "UnknownModelProvider",
    "OPENAI_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "GOOGLE_BASE_URL",
    "DEEPSEEK_BASE_URL",
]
