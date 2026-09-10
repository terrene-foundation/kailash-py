# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Gemini ``thought_signature`` capture/replay — the ONE implementation (#2120/#2121).

Gemini 3.x REQUIRES every replayed ``functionCall`` part to carry back the
``thought_signature`` the model issued alongside it. Omitting it is a hard
``400 INVALID_ARGUMENT``::

    Function call is missing a thought_signature in functionCall parts. This is
    required for tools to work correctly, and missing thought_signature may lead
    to degraded model performance.

so the SECOND request of every tool loop is rejected and no tool ever executes.
Gemini 2.5 issues no signature and is unaffected.

TWO Google surfaces replay a tool turn and BOTH dropped the signature:

* ``kaizen_agents.delegate.adapters.google_adapter`` — the ``Delegate``
  streaming path, which builds ``google.genai`` SDK dicts (snake_case keys,
  ``Part.thought_signature`` typed ``Optional[bytes]``).
* ``kaizen.llm.wire_protocols.google_generate_content`` — the four-axis REST
  wire used by ``LLMAgentNode`` / ``BaseAgent`` (camelCase keys,
  ``thoughtSignature`` carried as a base64 **string** in JSON).

They need the same capture semantics but DIFFERENT emission types, which is
exactly the shape that grows two divergent copies. This module is the single
source of truth: one stash key, one encoder, and one accessor per emission
form.

Stash form
----------
The signature is stashed on the OpenAI-shaped tool-call dict under
:data:`THOUGHT_SIGNATURE_KEY` as a **base64 str**, never raw ``bytes``, so the
tool-call dict stays JSON-serializable for session persistence, event emission
and the ``to_legacy_shape`` passthrough. Both the ``Delegate`` ``AgentLoop``
and ``LLMAgentNode``'s tool loop round-trip tool-call dicts opaquely (they read
only ``id`` / ``function.name``), so the extra key survives capture → replay
untouched.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Optional

#: Key under which a captured Gemini ``thought_signature`` is stashed on the
#: OpenAI-shaped tool-call dict. Underscore-prefixed and provider-namespaced so
#: it is greppable and cannot collide with an OpenAI tool-call field.
THOUGHT_SIGNATURE_KEY = "_google_thought_signature"


def encode_thought_signature(raw: Any) -> Optional[str]:
    """Normalize a captured signature to the base64 ``str`` stash form.

    ``raw`` is ``google.genai``'s ``Part.thought_signature`` (``bytes``) on the
    SDK path, or an already-base64 ``str`` on the REST path / when rehydrated
    from a persisted session.

    Returns ``None`` when the signature is absent — every Gemini 2.5 response —
    which keeps the emitted tool-call dict byte-identical to the pre-#2120
    shape. Raises ``TypeError`` on any other type rather than coercing: a
    silently mangled signature reproduces the exact opaque 400 this module
    exists to remove (``zero-tolerance`` Rule 3).
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return base64.b64encode(raw).decode("ascii")
    if isinstance(raw, str):
        return raw
    raise TypeError(
        "Gemini thought_signature must be bytes or a base64 str; got "
        f"{type(raw).__name__}"
    )


def thought_signature_for_sdk(stashed: Any) -> bytes:
    """Return the stashed signature as ``bytes`` for a ``google.genai`` Part.

    The SDK types ``Part.thought_signature`` as ``Optional[bytes]``; this is the
    accessor for the ``Delegate`` adapter path.

    Raises ``ValueError`` on a malformed stash rather than dropping the
    signature — dropping it is precisely the defect (``zero-tolerance`` Rule 3).
    """
    if isinstance(stashed, bytes):
        return stashed
    if not isinstance(stashed, str):
        raise ValueError(
            f"stashed {THOUGHT_SIGNATURE_KEY} must be a base64 str or bytes; "
            f"got {type(stashed).__name__}"
        )
    try:
        return base64.b64decode(stashed, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            f"stashed {THOUGHT_SIGNATURE_KEY} is not valid base64; Gemini 3.x "
            "rejects a functionCall part replayed without its thought_signature"
        ) from exc


def thought_signature_for_rest(stashed: Any) -> str:
    """Return the stashed signature as the base64 ``str`` the REST wire carries.

    Gemini's ``generateContent`` JSON body carries ``thoughtSignature`` as a
    base64 string (``bytes`` are not JSON-serializable, and the payload is
    ``json.dumps``-ed by ``LlmClient``). Validates the encoding so a malformed
    stash fails loudly here instead of as an opaque provider 400.
    """
    if isinstance(stashed, bytes):
        return base64.b64encode(stashed).decode("ascii")
    if not isinstance(stashed, str):
        raise ValueError(
            f"stashed {THOUGHT_SIGNATURE_KEY} must be a base64 str or bytes; "
            f"got {type(stashed).__name__}"
        )
    try:
        base64.b64decode(stashed, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            f"stashed {THOUGHT_SIGNATURE_KEY} is not valid base64; Gemini 3.x "
            "rejects a functionCall part replayed without its thought_signature"
        ) from exc
    return stashed


__all__ = [
    "THOUGHT_SIGNATURE_KEY",
    "encode_thought_signature",
    "thought_signature_for_sdk",
    "thought_signature_for_rest",
]
