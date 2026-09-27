# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Keyed correlation tags for rate-limit identifiers (issue #2171).

Why this module exists
----------------------

``RateLimitMiddleware`` logs a tag for the identifier that tripped a 429 so
operators can correlate repeat offenders. The identifier is, by the default
extractor's own documented priority, a ``user:<id>``, an ``apikey:<prefix>``
or an ``ip:<addr>`` -- the last two of which are PII, and the IP case is
drawn from a space of only 2**32 values.

The previous tag was :func:`kailash.utils.url_credentials.fingerprint_secret`,
an UNKEYED BLAKE2b digest truncated to 8 hex characters. That helper never
claimed confidentiality -- its own docstring says plainly that "anyone who
knows the plaintext can reproduce the fingerprint" -- so the defect was the
call site relying on a property the helper does not provide. Measured on
commodity hardware at ~1.3e5 candidate digests/second/core, the entire IPv4
space is exhaustible in roughly 9 single-core-hours, and a realistic target
(one ISP allocation) in well under a second. Against an unkeyed fast hash the
logged tag is therefore equivalent to the plaintext IP for anyone who can read
the log, which is precisely the audience the tag existed to withhold it from.

The construction
----------------

``HMAC-SHA256(key, DOMAIN || 0x00 || identifier)`` truncated to hex. The MAC is
keyed, so the digest is not a brute-forceable oracle for its pre-image even for
an attacker who knows the full candidate space and the algorithm. The domain
tag is prefixed so that a key which is ever reused for another purpose cannot
produce cross-purpose collisions, and the ``0x00`` separator makes the encoding
unambiguous.

Width is 16 hex characters (64 bits), not the 8 (32 bits) the old helper used.
Eight hex characters collide at roughly 2**16 distinct identifiers by the
birthday bound -- reachable in a single busy hour -- and a collision merges two
different offenders under one tag, which silently corrupts the forensic
question the tag exists to answer.

Key sourcing, and what happens when no key is configured
--------------------------------------------------------

The key is read from ``NEXUS_RATE_LIMIT_FINGERPRINT_KEY`` (``rules/env-models.md``:
the environment is the single source of truth; there is no in-source default and
no literal key anywhere in this file). A DEPLOYMENT-scoped key -- the same value
on every node -- is what preserves cross-node log correlation, which is the
stated reason the unkeyed helper was unkeyed in the first place. Per-process
keying would defeat enumeration equally well but would break that correlation,
so it is the fallback, not the design.

When the variable is absent this module does NOT fall back to an unkeyed digest
and does NOT drop the tag. Both of those are the silent-no-op default that
``rules/security.md`` § Secure-Default and ``rules/zero-tolerance.md`` Rule 3
BLOCK. Instead the two properties at stake are dispositioned separately:

* **Confidentiality fails CLOSED.** A fresh random 32-byte key is generated for
  the process. It is never written down, never logged and never returned, so
  the tag is unforgeable and irreversible with no operator action at all. This
  is the same disposition -- and for the same reason -- that
  ``nexus.auth_bootstrap.build_auth_config`` already takes for a missing JWT
  signing key. Note the key is per-PROCESS, not per-host: under
  ``uvicorn --workers N`` one machine runs N keys, so tags do not correlate
  even within a single node.
* **Cross-node correlation is DEGRADED, and says so LOUDLY.** A
  ``logger.warning`` at CONSTRUCTION time names the property that is off and
  the exact variable that turns it on. It fires once per middleware
  construction -- a startup-time event -- and never per request, so it cannot
  be drowned out by the 429 log lines it is warning about.

A key that is PRESENT but shorter than :data:`MIN_FINGERPRINT_KEY_BYTES` raises
:class:`InvalidFingerprintKeyError` rather than being padded or accepted. A
short key is worse than no key, because the operator believes the control is
wired; this mirrors ``InvalidAuthSecretError`` in ``nexus.auth_bootstrap``.

That is a LENGTH floor, not an ENTROPY floor -- the same caveat
``KAILASH_JWT_SECRET_KEY`` carries in ``.env.example``, and it matters more
here. 32 repeats of one character clears the check, and eight 4-byte emoji
clear it at only eight characters, because the floor counts UTF-8 BYTES. A
guessed or dictionary-recovered key restores the ENTIRE original attack: an
adversary who reads logs and recovers the key can recompute the MAC over the
2**32 IPv4 space and reverse every tag ever emitted. Nothing in this module can
verify entropy, so GENERATE the key rather than composing it::

    python -c 'import secrets; print(secrets.token_urlsafe(32))'

Operational consequence for rate limiting: NONE
------------------------------------------------

This is worth stating explicitly because it is the obvious thing to fear.
Rotating the key, or restarting without one, changes every emitted tag -- so a
tag from before the rotation will not equal a tag from after it for the same
client, and log queries must be scoped to one key epoch.

It does NOT reset rate-limit state. The backend is keyed on the RAW identifier
(``check_and_record(identifier=...)``; ``InMemoryBackend`` indexes
``self._buckets[identifier]`` directly), and no fingerprint of any kind reaches
it -- ``grep -rn fingerprint src/kailash/trust/rate_limit/`` returns nothing.
The tag is confined to the log line. An attacker therefore cannot reset their
own token bucket by provoking a key rotation, and a rotation cannot be used to
wash away an in-progress throttle.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "FINGERPRINT_KEY_ENV",
    "MIN_FINGERPRINT_KEY_BYTES",
    "FINGERPRINT_HEX_LENGTH",
    "InvalidFingerprintKeyError",
    "IdentifierFingerprinter",
    "resolve_fingerprint_key",
    "build_identifier_fingerprinter",
]

#: Deployment-scoped keying material for rate-limit identifier tags. Set the
#: SAME value on every node so tags correlate across the fleet.
FINGERPRINT_KEY_ENV = "NEXUS_RATE_LIMIT_FINGERPRINT_KEY"

#: HMAC-SHA256's block-level security is bounded by its key; 32 bytes matches
#: the digest width and the floor already enforced for ``NEXUS_JWT_SECRET``.
MIN_FINGERPRINT_KEY_BYTES = 32

#: 64 bits. See the module docstring on why 32 bits is too narrow here.
FINGERPRINT_HEX_LENGTH = 16

#: Domain separation. Bump the suffix if the pre-image encoding ever changes,
#: so old and new tags are visibly different rather than subtly incomparable.
_DOMAIN = b"nexus.rate_limit.identifier.v1"


class InvalidFingerprintKeyError(ValueError):
    """``NEXUS_RATE_LIMIT_FINGERPRINT_KEY`` is present but too weak to use.

    Subclasses :class:`ValueError` to match the ``InvalidAuthSecretError``
    precedent in :mod:`nexus.auth_bootstrap` for the same defect class.
    """


class IdentifierFingerprinter:
    """Derive a keyed, non-reversible correlation tag for an identifier.

    Instances are cheap, immutable and safe to share across threads --
    :func:`hmac.new` builds fresh state per call.

    Args:
        key: Keying material. MUST be at least
            :data:`MIN_FINGERPRINT_KEY_BYTES` bytes.
        deployment_scoped: ``True`` when the key came from the environment and
            is therefore shared across nodes; ``False`` when it was generated
            for this process only, which means tags do not correlate beyond it.

    Raises:
        InvalidFingerprintKeyError: ``key`` is shorter than the floor.
    """

    __slots__ = ("_key", "deployment_scoped")

    def __init__(self, key: bytes, *, deployment_scoped: bool) -> None:
        if len(key) < MIN_FINGERPRINT_KEY_BYTES:
            raise InvalidFingerprintKeyError(
                f"Rate-limit fingerprint key must be at least "
                f"{MIN_FINGERPRINT_KEY_BYTES} bytes (got {len(key)})."
            )
        self._key = key
        self.deployment_scoped = deployment_scoped

    def __call__(self, identifier: str, *, length: int = FINGERPRINT_HEX_LENGTH) -> str:
        """Return the keyed tag for ``identifier``.

        Args:
            identifier: The rate-limit identifier. Its raw value is never
                logged, returned, or stored by this call.
            length: Hex characters to return. Capped at the 64 of SHA-256.

        Returns:
            ``length`` hex characters. Stable for a given (key, identifier)
            pair, which is what makes the tag usable for correlation.
        """
        mac = hmac.new(
            self._key,
            # surrogatepass: a JWT claim decoded by `json.loads` can contain a
            # lone surrogate (e.g. {"sub": "\ud800"}), which plain UTF-8
            # encoding rejects with UnicodeEncodeError. That exception would
            # propagate out of `dispatch` and turn the 429 into a 500 -- the
            # precise failure the constructor-time key check exists to avoid,
            # reintroduced on the request path by an attacker-chosen username.
            _DOMAIN + b"\x00" + identifier.encode("utf-8", errors="surrogatepass"),
            hashlib.sha256,
        )
        return mac.hexdigest()[: max(1, min(length, 64))]

    def __repr__(self) -> str:  # pragma: no cover -- diagnostics only
        # NEVER render the key. A repr lands in tracebacks and debug logs.
        scope = "deployment" if self.deployment_scoped else "process"
        return f"<IdentifierFingerprinter scope={scope}>"

    def __reduce__(self):
        """Refuse to pickle.

        ``__slots__`` alone does not prevent serialization: the default
        protocol-2 reducer would write ``_key`` into the stream, so an instance
        crossing a ``multiprocessing`` spawn boundary or captured in a debug
        dump would carry the keying material with it. Raising is correct rather
        than merely inconvenient -- a fingerprinter is cheap to rebuild from the
        environment on the far side, which is what a worker process should do
        anyway so that every worker shares the configured key.
        """
        raise TypeError(
            "IdentifierFingerprinter is not picklable: it holds keying "
            "material. Rebuild it with build_identifier_fingerprinter() in the "
            "target process instead."
        )


def resolve_fingerprint_key(
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[bytes, bool]:
    """Resolve keying material from the environment, or mint an ephemeral key.

    Args:
        env: Environment mapping to read. Defaults to :data:`os.environ`.

    Returns:
        ``(key, deployment_scoped)``. ``deployment_scoped`` is ``True`` only
        when the key came from :data:`FINGERPRINT_KEY_ENV`.

    Raises:
        InvalidFingerprintKeyError: The variable is set but shorter than
            :data:`MIN_FINGERPRINT_KEY_BYTES`.
    """
    source = os.environ if env is None else env
    # An empty string is a misconfigured deployment, not a configured one --
    # treat it as absent, matching auth_bootstrap's `source.get(...) or None`.
    configured = source.get(FINGERPRINT_KEY_ENV) or None

    if configured is not None:
        key = configured.encode("utf-8")
        if len(key) < MIN_FINGERPRINT_KEY_BYTES:
            raise InvalidFingerprintKeyError(
                f"{FINGERPRINT_KEY_ENV} must be at least "
                f"{MIN_FINGERPRINT_KEY_BYTES} bytes (got {len(key)}). A short "
                "key is brute-forceable, which would restore exactly the "
                "weakness this control exists to remove (issue #2171). "
                "Generate one with: "
                "python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        return key, True

    # No key configured. Fail CLOSED on confidentiality: an unguessable
    # ephemeral key, never persisted and never logged. Falling back to an
    # unkeyed digest here -- or to dropping the tag -- is the silent-no-op
    # default that rules/security.md Secure-Default BLOCKS.
    return secrets.token_bytes(MIN_FINGERPRINT_KEY_BYTES), False


def build_identifier_fingerprinter(
    env: Optional[Mapping[str, str]] = None,
) -> IdentifierFingerprinter:
    """Build a fingerprinter, warning LOUDLY if the key is ephemeral.

    The warning fires here -- at construction, i.e. startup -- and never on the
    request path, so a degraded deployment is announced exactly once per
    middleware rather than once per throttled request.

    Args:
        env: Environment mapping to read. Defaults to :data:`os.environ`.

    Returns:
        A ready :class:`IdentifierFingerprinter`.

    Raises:
        InvalidFingerprintKeyError: The configured key is too short.
    """
    key, deployment_scoped = resolve_fingerprint_key(env)

    if not deployment_scoped:
        # Loud, one-time, and it names the exact wiring. Logged WITHOUT the
        # key and WITHOUT any identifier -- see rules/security.md
        # § "No secrets in logs".
        logger.warning(
            "Rate-limit identifier tags are keyed with a PROCESS-LOCAL random "
            "key because %s is not set. Tags stay unforgeable and "
            "irreversible, but they will NOT correlate across WORKER "
            "PROCESSES, nodes, or restarts -- under `uvicorn --workers N` a "
            "single host produces N different tags for the same client. Set "
            "%s to the SAME value (>= %d bytes) everywhere to restore "
            "correlation. Rate-limit enforcement itself is unaffected -- "
            "buckets are keyed on the raw identifier, not on the tag.",
            FINGERPRINT_KEY_ENV,
            FINGERPRINT_KEY_ENV,
            MIN_FINGERPRINT_KEY_BYTES,
        )

    return IdentifierFingerprinter(key, deployment_scoped=deployment_scoped)
