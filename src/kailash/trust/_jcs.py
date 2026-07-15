# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RFC 8785 (JSON Canonicalization Scheme / JCS) encoder for EATP v3.

This module is the SINGLE true RFC 8785 canonical encoder in the trust plane.
It exists to hash EXTERNAL governed subjects into a ``subject_hash`` on the
EATP Audit Anchor (issue #1590 — the EATP v3 keystone). It is deliberately
NARROW in blast radius:

* The pre-existing trust-plane signing encoders
  (``kailash.trust.signing.crypto.serialize_for_signing``,
  ``kailash.trust._json.canonical_json_dumps``, and
  ``AuditAnchor._canonical_input``'s v2.2 metadata form) each emit
  ``json.dumps(..., sort_keys=True)`` output. That form DIVERGES from RFC 8785
  on two axes:

  1. **Numbers** — ``json.dumps`` emits Python ``repr(float)`` (``1.0`` →
     ``"1.0"``, ``1e21`` → ``"1e+21"`` but ``1e-7`` → ``"1e-07"`` with a
     zero-padded two-digit exponent). RFC 8785 §3.2.2.3 mandates the
     ECMAScript ``Number::toString`` form (``1.0`` → ``"1"``, ``1e-7`` →
     ``"1e-7"``, shortest round-tripping significand).
  2. **Object keys** — ``sort_keys=True`` sorts by Unicode code POINT. RFC
     8785 §3.2.3 sorts by UTF-16 code UNIT, which differs for
     supplementary-plane characters (a high surrogate 0xD800–0xDBFF sorts
     BEFORE a BMP character ≥ 0xE000, the opposite of code-point order).

  Those encoders are cross-SDK byte-pinned (issue #959 / #1258 / kailash-rs
  #449). Switching them to RFC 8785 wholesale is a byte-CHANGING cross-SDK
  lockstep migration (``cross-sdk-inspection.md`` Rule 4b) and is BLOCKED as a
  single-SDK change. This module is therefore additive: it powers ONLY the NEW
  ``subject_hash`` path, leaving every grandfathered v2.2 pre-image untouched.

The encoder reuses ``kailash.trust._canonical.canonical_scalars`` for
typed-scalar normalization (Decimal / UUID / datetime / bytes / Enum /
dataclass → JSON-native forms), then applies RFC 8785 emission on top.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import fields, is_dataclass
from typing import Any

from kailash.trust._canonical import canonical_scalars

__all__ = [
    "MAX_DIGEST_CHILDREN",
    "MAX_DIGEST_DEPTH",
    "MAX_DIGEST_NODES",
    "MAX_DIGEST_STRING_TOTAL_BYTES",
    "jcs_encode",
    "jcs_subject_hash",
]

# ---------------------------------------------------------------------------
# Fail-closed resource bounds on the digest ingress (issue #1713).
#
# `jcs_encode` is the SHARED ingress for every attacker-influenceable subject
# that reaches this canonical encoder: the BH3 origin digest
# (`reasoning.origin.compute_origin_digest`, #1510) AND the EATP Audit-Anchor
# external-`subject_hash` path (`pact.audit`, #1590), plus the weft / bilateral
# / attestation content-hash paths. Every one of those runs an attacker-shaped
# `Any` through TWO unbounded recursive passes (`canonical_scalars` then
# `_encode`) and a SHA-256 BEFORE any auth check — an unauthenticated CPU /
# memory denial-of-service. A crafted wide/large payload burns unbounded
# CPU+memory; a deeply-nested payload drives the recursion toward RecursionError
# (swallowed to False on verify, but propagated UNCAUGHT on the sign path).
#
# The guard below traverses the RAW input ONCE, iteratively (its own traversal
# CANNOT RecursionError), and fails closed with a typed ValueError naming the
# exceeded limit + the observed value BEFORE canonicalization/hashing runs. The
# magnitudes mirror the PACT org-compilation limits (`pact.compilation`,
# `pact-governance.md` §7) — they are DoS backstops, NOT business limits, and
# are generous enough that every legitimate subject passes unchanged. A
# reject-only bound changes ZERO bytes for in-bounds input, so the pinned
# cross-SDK conformance vectors stay byte-identical (no cross-SDK lockstep).
# ---------------------------------------------------------------------------

MAX_DIGEST_DEPTH: int = 50
"""Maximum container-nesting depth of a subject passed to :func:`jcs_encode`."""

MAX_DIGEST_NODES: int = 100_000
"""Maximum total nodes (scalars + containers + dict keys) traversed."""

MAX_DIGEST_CHILDREN: int = 500
"""Maximum direct children (entries / elements) of any single container."""

MAX_DIGEST_STRING_TOTAL_BYTES: int = 10_000_000
"""Maximum cumulative UTF-8 byte length of all strings/bytes in the subject
(10 MB) — rejects a single multi-GB string or the sum of many large ones."""


def _check_digest_bounds(root: Any) -> None:
    """Fail-closed resource-bound check over the RAW digest input (issue #1713).

    Traverses ``root`` ONCE with an explicit stack (never Python recursion — so
    a deeply-nested adversarial payload cannot RecursionError the guard itself),
    enforcing :data:`MAX_DIGEST_DEPTH`, :data:`MAX_DIGEST_NODES`,
    :data:`MAX_DIGEST_CHILDREN`, and :data:`MAX_DIGEST_STRING_TOTAL_BYTES`. Runs
    BEFORE :func:`canonical_scalars` / :func:`_encode` / the SHA-256 so an
    oversize subject is rejected before any unbounded work.

    Raises:
        ValueError: ``origin-oversize-rejected``-class error naming the exceeded
            limit AND the observed value. Fail-closed: unknown/error → reject
            (never sign/verify).
    """
    total_nodes = 0
    total_str_bytes = 0
    # Stack of (node, depth); iterative to bound the guard's own memory/stack.
    stack: list[tuple[Any, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        total_nodes += 1
        if total_nodes > MAX_DIGEST_NODES:
            raise ValueError(
                "origin-oversize-rejected: subject exceeds max total nodes "
                f"(limit={MAX_DIGEST_NODES}, observed>{MAX_DIGEST_NODES})"
            )
        if depth > MAX_DIGEST_DEPTH:
            raise ValueError(
                "origin-oversize-rejected: subject exceeds max nesting depth "
                f"(limit={MAX_DIGEST_DEPTH}, observed={depth})"
            )

        # Leaf scalars carrying byte weight — accumulate and stop descending.
        if isinstance(node, str):
            total_str_bytes += len(node.encode("utf-8"))
            if total_str_bytes > MAX_DIGEST_STRING_TOTAL_BYTES:
                raise ValueError(
                    "origin-oversize-rejected: subject exceeds max cumulative "
                    f"string length (limit={MAX_DIGEST_STRING_TOTAL_BYTES} bytes, "
                    f"observed>{MAX_DIGEST_STRING_TOTAL_BYTES})"
                )
            continue
        if isinstance(node, (bytes, bytearray)):
            total_str_bytes += len(node)
            if total_str_bytes > MAX_DIGEST_STRING_TOTAL_BYTES:
                raise ValueError(
                    "origin-oversize-rejected: subject exceeds max cumulative "
                    f"string length (limit={MAX_DIGEST_STRING_TOTAL_BYTES} bytes, "
                    f"observed>{MAX_DIGEST_STRING_TOTAL_BYTES})"
                )
            continue

        # Containers — count direct children, then descend. Mirrors the type
        # whitelist canonical_scalars recurses into (dict / set / list / tuple /
        # dataclass) so the guard sees exactly what the encoder will.
        children: list[Any] | None = None
        if not isinstance(node, type) and is_dataclass(node):
            children = [getattr(node, f.name) for f in fields(node)]
        elif isinstance(node, dict):
            # Both keys and values are traversed by the encoder; count entries.
            if len(node) > MAX_DIGEST_CHILDREN:
                raise ValueError(
                    "origin-oversize-rejected: container exceeds max children "
                    f"(limit={MAX_DIGEST_CHILDREN}, observed={len(node)})"
                )
            for key, value in node.items():
                stack.append((key, depth + 1))
                stack.append((value, depth + 1))
            continue
        elif isinstance(node, (list, tuple, set, frozenset)):
            children = list(node)

        if children is not None:
            if len(children) > MAX_DIGEST_CHILDREN:
                raise ValueError(
                    "origin-oversize-rejected: container exceeds max children "
                    f"(limit={MAX_DIGEST_CHILDREN}, observed={len(children)})"
                )
            for child in children:
                stack.append((child, depth + 1))


# repr(float) either has an exponent ("1e+21", "1.5e-08") or does not
# ("123.45", "1.0"). Split on the exponent marker to recover mantissa + exponent.
_EXP_SPLIT = re.compile("[eE]")


def _es_number_to_string(m: float) -> str:
    """Serialize a finite ``float`` per ECMAScript ``Number::toString``.

    This is RFC 8785 §3.2.2.3 number serialization: the shortest decimal
    significand that round-trips to the same IEEE-754 double, formatted with
    ECMAScript's exponent/integer rules (NOT Python's ``repr`` formatting).

    The algorithm derives ``(s, k, n)`` such that ``s`` is the ``k``-digit
    shortest significand (no leading/trailing zeros) and ``s × 10**(n-k) == m``
    — i.e. the decimal point falls after position ``n`` of ``s``. It then
    applies the ECMAScript §7.1.12.1 formatting cases:

    * ``k <= n <= 21`` — integer: ``s`` followed by ``n-k`` zeros.
    * ``0 < n <= 21`` — fraction: first ``n`` digits, ``.``, remaining digits.
    * ``-6 < n <= 0`` — leading-zero fraction: ``0.`` + ``-n`` zeros + ``s``.
    * otherwise — exponential: ``d[.ddd]e±(n-1)``.

    Python's ``repr(float)`` already yields the shortest round-tripping
    significand (David Gay / Grisu), so this function reformats ``repr`` rather
    than re-deriving the digits.

    Raises:
        ValueError: on ``NaN`` / ``Infinity`` / ``-Infinity`` — non-finite
            floats are not valid JSON (RFC 8259) and MUST NOT reach a signed
            pre-image (``trust-plane-security.md`` MUST-8, fail-closed).
    """
    if math.isnan(m) or math.isinf(m):
        raise ValueError(
            "RFC 8785 rejects non-finite floats (NaN / Infinity / -Infinity); "
            f"got {m!r}"
        )
    # +0.0 and -0.0 both canonicalize to "0" (RFC 8785 / ECMAScript).
    if m == 0.0:
        return "0"
    if m < 0:
        return "-" + _es_number_to_string(-m)

    # m is positive finite. Recover mantissa digits + decimal exponent from repr.
    r = repr(m)
    parts = _EXP_SPLIT.split(r)
    if len(parts) == 2:
        mantissa, exp = parts[0], int(parts[1])
    else:
        mantissa, exp = parts[0], 0
    if "." in mantissa:
        int_part, frac_part = mantissa.split(".")
    else:
        int_part, frac_part = mantissa, ""

    all_digits = int_part + frac_part
    # value == int(all_digits) * 10**scale
    scale = exp - len(frac_part)

    lstripped = all_digits.lstrip("0")
    rstripped = lstripped.rstrip("0")
    s = rstripped
    if not s:
        # Unreachable for m != 0, but keep fail-safe.
        return "0"
    k = len(s)
    n_trailing = len(lstripped) - len(rstripped)
    low = scale + n_trailing  # exponent of the least-significant digit of s
    n = low + k  # decimal point falls after position n of s

    if k <= n <= 21:
        return s + "0" * (n - k)
    if 0 < n <= 21:
        return s[:n] + "." + s[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + s
    # Exponential form.
    e = n - 1
    mant_out = s if k == 1 else s[0] + "." + s[1:]
    sign = "+" if e >= 0 else "-"
    return f"{mant_out}e{sign}{abs(e)}"


def _escape_string(value: str) -> str:
    r"""Escape a string per RFC 8785 §3.2.2.2 (ECMAScript ``JSON.stringify``).

    Escapes ``"`` and ``\``, the five short control escapes
    (``\b \t \n \f \r``), and any other C0 control (U+0000–U+001F) as
    ``\u00XX`` (lowercase hex). Every other code point — including U+007F and
    all non-ASCII — is emitted as raw UTF-8. Forward slash is NOT escaped.

    This is byte-identical to Python's ``json``-module string escaping with
    ``ensure_ascii=False``; it is spelled out here (rather than delegating to
    ``json.dumps``) because this is a signed-crypto surface and the escaping
    contract MUST be explicit and independent of ``json`` internals.
    """
    out = ['"']
    for ch in value:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\r":
            out.append("\\r")
        elif cp < 0x20:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16_sort_key(key: Any) -> bytes:
    """UTF-16 code-unit sort key for an object key.

    Encoding as UTF-16-BE and comparing the byte sequences is exactly a
    code-unit lexicographic comparison (each unit is 2 big-endian bytes), and
    correctly orders supplementary-plane keys (high surrogate 0xD8xx sorts
    before a BMP key ≥ 0xE000).

    Raises:
        TypeError: if ``key`` is not a ``str`` — RFC 8259 object members MUST
            have string keys, and a non-string key that survived
            ``canonical_scalars`` is a programming error, not silently coerced.
    """
    if not isinstance(key, str):
        raise TypeError(
            f"object key {key!r} ({type(key).__name__}) is not a string; "
            f"RFC 8785 requires string object keys (RFC 8259 members)"
        )
    return key.encode("utf-16-be")


def _encode(value: Any) -> str:
    """Recursively emit the RFC 8785 canonical form of a JSON-native value.

    ``value`` MUST already be normalized to JSON-native types (str / int /
    float / bool / None / dict / list) by :func:`canonical_scalars`.
    """
    if value is None:
        return "null"
    # bool is a subclass of int — check it FIRST.
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _escape_string(value)
    if isinstance(value, bool):
        # Defensive: any bool not caught by the `is True/False` identity checks
        # above (e.g. numpy.bool_ would not be `bool`, so this is truly just
        # Python bool) still must NOT fall through to the int branch.
        return "true" if value else "false"
    if isinstance(value, int):
        # Integers serialize as their exact decimal form (JSON integer token).
        return str(value)
    if isinstance(value, float):
        return _es_number_to_string(value)
    if isinstance(value, dict):
        # RFC 8785 §3.2.3: sort object keys by UTF-16 code unit.
        parts = [
            _escape_string(key) + ":" + _encode(value[key])
            for key in sorted(value.keys(), key=_utf16_sort_key)
        ]
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise TypeError(
        f"value of type {type(value).__name__!r} is not JSON-native after "
        f"canonical_scalars normalization; RFC 8785 cannot encode it"
    )


def jcs_encode(value: Any) -> str:
    """Return the RFC 8785 (JCS) canonical JSON string for ``value``.

    ``value`` is first normalized by
    :func:`kailash.trust._canonical.canonical_scalars` (typed scalars →
    JSON-native forms), then emitted per RFC 8785: shortest-round-trip
    ECMAScript number serialization, RFC-8785 string escaping, object keys
    sorted by UTF-16 code unit, no inter-token whitespace.

    Raises:
        ValueError: if ``value`` exceeds a digest resource bound (issue #1713 —
            depth / node-count / per-container children / cumulative string
            length), or if ``value`` contains a non-finite float.
        TypeError: if ``value`` contains a value with no RFC-8785 encoding
            after normalization, or a non-string object key.
    """
    # Fail-closed resource-bound check on the RAW input BEFORE the two unbounded
    # recursive passes (canonical_scalars → _encode) + hash run (issue #1713).
    _check_digest_bounds(value)
    normalized = canonical_scalars(value)
    return _encode(normalized)


def jcs_subject_hash(subject: Any) -> str:
    """Return ``"sha256:<hex>"`` — the SHA-256 of ``jcs_encode(subject)``.

    This is the ``subject_hash`` bound into an EATP v3 Audit Anchor's signing
    pre-image when an external subject is anchored (issue #1590).
    """
    encoded = jcs_encode(subject).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
