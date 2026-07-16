# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Canonical multimodal content-part translator (#1720 Wave-1b).

The canonical content-part shape carried inside ``messages[i]["content"]``
is OpenAI-shaped: a list of parts like ``{"type": "text", "text": ...}``
and ``{"type": "image_url", "image_url": {"url": ...}}`` where the url is
EITHER a base64 data-URI (``data:<media_type>;base64,<data>``) OR a remote
``http(s)`` url.

``openai_chat`` and ``mistral_chat`` pass this canonical shape through
verbatim — no translation needed, because it already IS their wire shape.
The three vision-capable non-OpenAI wires (``anthropic_messages``,
``google_generate_content``, ``ollama_native``) each speak a DIFFERENT
native image shape and translate via the functions in this module. The
text-only wires (e.g. ``cohere_generate``) do not translate — they WARN and
drop, per the observability contract (see ``cohere_generate`` module docs).

This module is a pure, dumb-data translator: no I/O, no network, no
provider SDK calls, and no LLM/keyword reasoning. Classifying a content
part (text vs image, data-URI vs remote URL) is a STRUCTURAL data-format
operation on a typed dict — parsing a well-known key/value shape, not
natural-language reasoning about user intent — which is the "tool result
parsing / output formatting" exception permitted by
``rules/agent-reasoning.md`` § Permitted Deterministic Logic.

Cross-SDK parity: this module's classification + per-target emission is
intended to match the Rust SDK's equivalent multimodal translator shape.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

__all__ = [
    "TextPart",
    "ImagePart",
    "ContentPart",
    "parse_data_uri",
    "is_remote_url",
    "parse_content_part",
    "guess_media_type",
    "to_anthropic_block",
    "to_gemini_part",
    "to_ollama_images",
]


@dataclass(frozen=True)
class TextPart:
    """A plain text content part (``{"type": "text", "text": ...}``)."""

    text: str


@dataclass(frozen=True)
class ImagePart:
    """Intermediate representation of an OpenAI ``image_url`` content part.

    Exactly one of two shapes is populated, discriminated by
    ``is_data_uri``:

    * data-URI (``is_data_uri=True``) — ``media_type`` + ``data`` (the
      base64 payload) are set; ``url`` is ``None``.
    * remote http(s) URL (``is_data_uri=False``) — ``url`` is set;
      ``media_type`` + ``data`` are ``None``.
    """

    is_data_uri: bool
    media_type: Optional[str] = None
    data: Optional[str] = None
    url: Optional[str] = None


ContentPart = Union[TextPart, ImagePart]


def parse_data_uri(uri: str) -> Optional[Tuple[str, str]]:
    """Split a ``data:<media_type>;base64,<data>`` URI into (media_type, data).

    Returns ``None`` when ``uri`` is not a well-formed base64 data URI
    (missing the ``data:`` scheme, missing the ``;base64,`` separator, or
    either half empty). Pure string parsing only — the base64 payload
    itself is never decoded or validated here; that is the receiving
    provider's concern.
    """
    if not isinstance(uri, str) or not uri.startswith("data:"):
        return None
    rest = uri[len("data:") :]
    if ";base64," not in rest:
        return None
    media_type, _, data = rest.partition(";base64,")
    if not media_type or not data:
        return None
    return media_type, data


def is_remote_url(url: str) -> bool:
    """True when ``url`` is a remote ``http(s)`` URL (not a data URI)."""
    return isinstance(url, str) and (
        url.startswith("http://") or url.startswith("https://")
    )


def parse_content_part(block: Any) -> Optional[ContentPart]:
    """Classify one OpenAI-shaped content-part dict into the intermediate form.

    Recognizes:

    * ``{"type": "text", "text": ...}`` -> :class:`TextPart`
    * ``{"type": "image_url", "image_url": {"url": <data-URI or http(s)>}}``
      -> :class:`ImagePart`

    Returns ``None`` for any other shape (an unrecognized block type, a
    malformed ``image_url`` sub-dict, or a url that is neither a base64
    data-URI nor a remote http(s) url) — callers pass such blocks through
    unchanged rather than treating ``None`` as an error.
    """
    if not isinstance(block, dict):
        return None
    block_type = block.get("type")
    if block_type == "text":
        text = block.get("text", "")
        return TextPart(text=text if isinstance(text, str) else "")
    if block_type == "image_url":
        image_url = block.get("image_url")
        url = image_url.get("url") if isinstance(image_url, dict) else None
        if not isinstance(url, str):
            return None
        parsed = parse_data_uri(url)
        if parsed is not None:
            media_type, data = parsed
            return ImagePart(is_data_uri=True, media_type=media_type, data=data)
        if is_remote_url(url):
            return ImagePart(is_data_uri=False, url=url)
        return None
    return None


def guess_media_type(url: str) -> str:
    """Best-effort MIME type guess for a remote image URL, from its extension.

    Falls back to ``application/octet-stream`` when the extension is
    unrecognized or absent. A remote ``http(s)`` image_url carries no
    media-type metadata in the canonical OpenAI shape, yet Gemini's
    ``fileData`` part requires a ``mimeType`` field — this is the
    deterministic, structural guess (extension lookup only; no content
    inspection, no network fetch).
    """
    guessed, _ = mimetypes.guess_type(url)
    return guessed or "application/octet-stream"


# --- Per-target emitters -----------------------------------------------


def to_anthropic_block(part: ImagePart) -> Dict[str, Any]:
    """Convert an :class:`ImagePart` to an Anthropic ``image`` content block.

    Data-URI -> ``{"type": "image", "source": {"type": "base64",
    "media_type": ..., "data": ...}}``. Remote url -> ``{"type": "image",
    "source": {"type": "url", "url": ...}}`` (Anthropic's ``/v1/messages``
    natively supports a ``url``-sourced image block).
    """
    if part.is_data_uri:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": part.media_type,
                "data": part.data,
            },
        }
    return {
        "type": "image",
        "source": {"type": "url", "url": part.url},
    }


def to_gemini_part(part: ImagePart) -> Dict[str, Any]:
    """Convert an :class:`ImagePart` to a Gemini ``inlineData``/``fileData`` part.

    Data-URI -> ``{"inlineData": {"mimeType": ..., "data": ...}}``. Remote
    url -> ``{"fileData": {"mimeType": ..., "fileUri": ...}}`` (Gemini
    requires ``mimeType`` even for a ``fileData`` reference; see
    :func:`guess_media_type`).
    """
    if part.is_data_uri:
        return {"inlineData": {"mimeType": part.media_type, "data": part.data}}
    return {
        "fileData": {
            "mimeType": guess_media_type(part.url or ""),
            "fileUri": part.url,
        }
    }


def to_ollama_images(parts: List[ImagePart]) -> List[str]:
    """Convert data-URI :class:`ImagePart` entries to Ollama-native's ``images`` field.

    Ollama's per-message ``images`` field is a bare list of base64 strings
    (no media-type wrapper, no data-URI prefix) — so only data-URI parts
    contribute an entry. A remote-URL :class:`ImagePart` has no base64
    payload to emit here; fetching a remote image over the network is an
    I/O operation and is explicitly out of scope for this pure translator
    (callers that need remote-image support for Ollama MUST fetch and
    re-encode BEFORE calling this function, and MUST log the drop when
    they do not — see ``ollama_native.build_request_payload``).
    """
    return [p.data for p in parts if p.is_data_uri and p.data is not None]
