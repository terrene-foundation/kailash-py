# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Keyed one-way derivation of per-recipient disclosure-trace tokens (issue #1482).

A disclosure-trace token attributes a leaked artifact back to the specific
recipient it was served to. It is a keyed, deterministic, ONE-WAY function of
``(recipient, resource, session)`` under a server-held key:

* **Keyed** -- an attacker without the server key cannot forge or predict a
  token, so tokens embedded in served artifacts cannot be attributed by third
  parties, only by the server.
* **Deterministic** -- the same ``(recipient, resource, session)`` under the
  same key always yields the same token, so re-serving the same artifact to the
  same recipient is idempotent and correlation across events is possible.
* **One-way** -- the token is an HMAC-SHA256 digest; the recipient is NOT
  recoverable by inverting it. Reverse attribution (token -> recipient) is done
  via a keyed store that persists the mapping at derivation time
  (``kailash.trust.disclosure``), NEVER by "decrypting" the token.

Boundary (engine vs application). This helper derives the token and nothing
more. Watermark RENDERING -- injecting the token into HTML/PDF/image bytes --
is presentation-specific and lives application-side. The engine owns
derivation, audit binding, and reverse lookup only.

The server key MUST come from injected key material (an environment variable or
a key manager), never a hardcoded literal -- see ``rules/security.md`` (no
hardcoded secrets). The helper fail-closes on an empty key.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod

from kailash.trust.signing.crypto import serialize_for_signing

_TRACE_TOKEN_DOMAIN = "kailash.trust.disclosure.trace-token.v1"
"""Domain-separation tag mixed into every trace-token pre-image.

Prevents a token derived for disclosure tracing from colliding with an HMAC
computed for any other purpose under the same server key.
"""


def derive_trace_token(
    server_key: bytes,
    recipient: str,
    resource: str,
    session: str,
) -> str:
    """Derive a deterministic per-``(recipient, resource, session)`` trace token.

    Computes ``HMAC-SHA256(server_key, canonical(domain, recipient, resource,
    session))`` and returns its lowercase hex digest. The pre-image is a
    canonical JSON object (sorted keys, no whitespace) so field boundaries are
    unambiguous -- concatenating the raw strings would let ``("ab", "c")`` and
    ``("a", "bc")`` collide.

    Args:
        server_key: Server-held HMAC key. MUST be non-empty and sourced from
            injected key material (env var / key manager), never a literal.
        recipient: Stable identity of the recipient the artifact is served to.
        resource: Identifier of the resource being disclosed.
        session: Session / delivery-context identifier.

    Returns:
        64-character lowercase hex HMAC-SHA256 digest (the trace token).

    Raises:
        ValueError: If ``server_key`` is empty (fail-closed).
        TypeError: If ``server_key`` is not bytes.
    """
    if not isinstance(server_key, (bytes, bytearray)):
        raise TypeError(f"server_key must be bytes, got {type(server_key).__name__}")
    if not server_key:
        raise ValueError(
            "server_key must be non-empty; source it from injected key material "
            "(environment variable or key manager), never a hardcoded literal"
        )

    pre_image = serialize_for_signing(
        {
            "domain": _TRACE_TOKEN_DOMAIN,
            "recipient": recipient,
            "resource": resource,
            "session": session,
        }
    ).encode("utf-8")
    return hmac_mod.new(bytes(server_key), pre_image, hashlib.sha256).hexdigest()


__all__ = [
    "derive_trace_token",
]
