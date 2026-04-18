# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Preset registry + provider-specific deployment factories.

Every preset factory:

* Returns a fully-constructed `LlmDeployment` with the correct wire protocol,
  endpoint URL + path prefix, and auth strategy for its provider.
* Is registered in `_PRESETS` under a short snake_case name matching the
  allowlist regex `^[a-z][a-z0-9_]{0,31}$`.
* Is exposed as a classmethod on `LlmDeployment` via `_attach_preset_methods()`
  so both call styles work:
      LlmDeployment.openai(api_key, model="gpt-4")     # classmethod form
      from kaizen.llm.presets import openai_preset      # module-level form

Session 1 ships only the `openai` preset. Every subsequent session adds its
presets (anthropic, google, bedrock_*, azure_*, vertex_*) to this file.

Security invariants enforced here:

* `register_preset(name, factory)` validates `name` against the regex and
  rejects CRLF / spaces / unicode / null-byte / leading-digit / >32-char
  inputs. The error message MUST NOT echo the raw bad name — that's a
  log-injection vector. The caller sees a fingerprint instead.
* Every call site of `register_preset` in this file uses a literal snake_case
  name; the validation is defence-in-depth for any future code path that
  might register from a config file or environment variable.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Callable, Dict

from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------

# Allowlist regex: lowercase ASCII letter first, then up to 31 of [a-z0-9_].
# Deliberate: rejects CRLF, spaces, unicode confusables (Cyrillic 'а' etc),
# null bytes, leading digits, and anything > 32 chars.
_PRESET_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _fingerprint(raw: str) -> str:
    """Short, non-reversible tag for log correlation without echoing input."""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:4]


def _validate_preset_name(name: Any) -> str:
    """Assert `name` matches the regex; raise ValueError if not.

    The error message MUST NOT contain `name` verbatim (log-injection
    defence — CRLF in a preset name would otherwise split log lines).
    Instead it carries a 4-char SHA-256 fingerprint so the audit trail can
    correlate without reproducing the payload.
    """
    if not isinstance(name, str):
        raise ValueError(
            "preset name must be a string; rejected non-string input "
            f"(type_fingerprint={type(name).__name__})"
        )
    if not _PRESET_NAME_RE.match(name):
        raise ValueError(
            "preset name failed validation against "
            f"^[a-z][a-z0-9_]{{0,31}}$ (name_fingerprint={_fingerprint(name)})"
        )
    return name


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_PRESETS: Dict[str, Callable[..., LlmDeployment]] = {}


def register_preset(name: str, factory: Callable[..., LlmDeployment]) -> None:
    """Register a preset factory under `name`.

    Validates `name` against `_PRESET_NAME_RE`. Rejects duplicate
    registrations with a typed error to prevent silent shadowing — if a
    refactor tries to re-register `openai`, the second call raises.
    """
    validated = _validate_preset_name(name)
    if not callable(factory):
        raise TypeError("factory must be callable")
    if validated in _PRESETS:
        raise ValueError(
            f"preset already registered (name_fingerprint={_fingerprint(validated)})"
        )
    _PRESETS[validated] = factory


def get_preset(name: str) -> Callable[..., LlmDeployment]:
    """Retrieve a preset factory by name. Validates the name first."""
    validated = _validate_preset_name(name)
    try:
        return _PRESETS[validated]
    except KeyError:
        raise ValueError(
            f"preset not registered (name_fingerprint={_fingerprint(validated)})"
        )


def list_presets() -> list[str]:
    """Return the registered preset names in registration order."""
    return list(_PRESETS.keys())


# ---------------------------------------------------------------------------
# OpenAI preset (Session 2)
# ---------------------------------------------------------------------------


def openai_preset(
    api_key: str,
    model: str = "gpt-4",
    *,
    base_url: str = "https://api.openai.com",
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """Build a deployment for the public OpenAI API.

    Wire:        `OpenAiChat`
    Endpoint:    `https://api.openai.com/v1`
    Auth:        `ApiKeyBearer(Authorization_Bearer, ApiKey(api_key))`

    `api_key` MUST be a non-empty string; we do not accept `None` on the
    grounds that "let the provider 401" produces opaque errors.
    """
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("openai_preset requires a non-empty api_key string")
    if not isinstance(model, str) or not model:
        raise ValueError("openai_preset requires a non-empty model string")

    endpoint = Endpoint(
        base_url=base_url,
        path_prefix=path_prefix,
    )
    auth = ApiKeyBearer(
        kind=ApiKeyHeaderKind.Authorization_Bearer,
        key=ApiKey(api_key),
    )
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
    )


register_preset("openai", openai_preset)


# ---------------------------------------------------------------------------
# Attach presets as classmethods on LlmDeployment
# ---------------------------------------------------------------------------


def _attach_openai_classmethod() -> None:
    """Wire `openai_preset` onto `LlmDeployment.openai`.

    The LlmDeployment class already declares stubs for every other preset
    (they raise NotImplementedError with the session marker). Session 1
    replaces the `openai` entry only; subsequent sessions add their own.
    """

    @classmethod  # type: ignore[misc]
    def openai(cls, api_key: str, model: str = "gpt-4", **kwargs: Any) -> LlmDeployment:
        return openai_preset(api_key, model=model, **kwargs)

    LlmDeployment.openai = openai  # type: ignore[attr-defined]


_attach_openai_classmethod()


__all__ = [
    "openai_preset",
    "register_preset",
    "get_preset",
    "list_presets",
]
