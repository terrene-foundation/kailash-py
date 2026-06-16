# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Standalone, directly-callable masking primitives.

These are the masking algorithms that back
:meth:`dataflow.classification.policy.ClassificationPolicy.apply_masking_strategy`,
exposed as free functions usable over an arbitrary value with **no**
``ModelDefinition`` and **no** pipeline. They cover three needs the
record-bound classification path could not:

* directly-callable ``hash_value`` / ``last_four`` / ``redact`` over an
  arbitrary string (with optional HMAC salt on the hash), and
* record-agnostic redaction (``redact_text`` / ``redact_mapping``) plus a
  drop-in :class:`RedactionFilter` (a ``logging.Filter``) for log/telemetry
  redaction outside the data pipeline.

Cross-SDK parity with esperie-enterprise/kailash-rs ``kailash.dataflow``
masking (#1350 / #1351). See GH #1337.

Usage::

    from dataflow.classification import hash_value, last_four, redact
    from dataflow.classification import RedactionFilter, MaskingStrategy

    hash_value("4111111111111111", salt="per-tenant-pepper")  # HMAC-SHA256 hex
    last_four("4111111111111111")                             # "************1111"
    redact("anything")                                         # "[REDACTED]"

    import logging, re
    handler.addFilter(RedactionFilter(
        patterns=[re.compile(r"\\b\\d{16}\\b")],   # mask 16-digit card numbers
        strategy=MaskingStrategy.LAST_FOUR,
    ))
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Pattern, Union

from dataflow.classification.types import MaskingStrategy

# A masking strategy may be supplied as the enum OR as its raw string value
# (``MaskingStrategy`` is a ``str``-Enum, so ``"hash" == MaskingStrategy.HASH``).
# Accepting the union keeps the fail-closed default reachable for unknown strings.
_StrategyLike = Union[MaskingStrategy, str]

__all__ = [
    "hash_value",
    "last_four",
    "redact",
    "redact_text",
    "redact_mapping",
    "RedactionFilter",
]

# Public redaction sentinel — identical to the value produced by
# ``ClassificationPolicy.apply_masking_strategy`` for ``REDACT`` so the two
# paths stay byte-for-byte aligned.
REDACTED = "[REDACTED]"

_PatternLike = Union[str, "Pattern[str]"]


def hash_value(
    value: Any,
    salt: Optional[Union[str, bytes]] = None,
    length: Optional[int] = None,
) -> str:
    """Hash ``value`` to a hex digest.

    With ``salt`` the digest is ``HMAC-SHA256(salt, value)``; without it the
    digest is plain ``SHA-256(value)`` (matching the legacy ``HASH`` strategy
    output exactly). ``length``, when given, truncates the hex digest to that
    many leading characters.

    A salt is strongly recommended for low-entropy PII (SSN, phone, card
    number): an unsalted hash of a small value space is reversible by
    rainbow table. ``salt`` may be a str (UTF-8 encoded) or raw bytes.
    """
    msg = str(value).encode("utf-8")
    if salt is None:
        digest = hashlib.sha256(msg).hexdigest()
    else:
        key = salt.encode("utf-8") if isinstance(salt, str) else salt
        digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    if length is not None:
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        return digest[:length]
    return digest


def last_four(value: Any) -> str:
    """Mask all but the final four characters of ``str(value)``.

    Strings of length ≤ 4 are fully masked (one ``*`` per character), so no
    value short enough to be guessable leaks any character.
    """
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def redact(value: Any = None) -> str:
    """Return the constant redaction sentinel ``"[REDACTED]"``.

    The ``value`` argument is accepted (and ignored) so ``redact`` has the
    same call shape as the other masking primitives and can be used
    interchangeably as a callable.
    """
    del value  # accepted for call-shape uniformity; redaction is value-independent
    return REDACTED


def _mask_match(
    matched: str, strategy: _StrategyLike, salt: Optional[Union[str, bytes]]
) -> str:
    """Apply ``strategy`` to a single matched substring."""
    if strategy == MaskingStrategy.NONE:
        return matched
    if strategy == MaskingStrategy.REDACT:
        return REDACTED
    if strategy == MaskingStrategy.ENCRYPT:
        return "[ENCRYPTED]"
    if strategy == MaskingStrategy.HASH:
        return hash_value(matched, salt=salt)
    if strategy == MaskingStrategy.LAST_FOUR:
        return last_four(matched)
    # Unknown strategy — fail closed.
    return REDACTED


def _compile(patterns: Optional[Iterable[_PatternLike]]) -> list["Pattern[str]"]:
    compiled: list[Pattern[str]] = []
    for p in patterns or ():
        compiled.append(re.compile(p) if isinstance(p, str) else p)
    return compiled


def redact_text(
    text: Any,
    patterns: Optional[Iterable[_PatternLike]] = None,
    *,
    strategy: _StrategyLike = MaskingStrategy.REDACT,
    salt: Optional[Union[str, bytes]] = None,
) -> str:
    """Redact every ``patterns`` match in ``str(text)`` using ``strategy``.

    Record-agnostic: operates on arbitrary text with no model definition.
    Each regex match is replaced by ``strategy`` applied to the matched
    substring. With no ``patterns`` the text is returned unchanged.
    """
    out = str(text)
    for pat in _compile(patterns):
        out = pat.sub(lambda m: _mask_match(m.group(0), strategy, salt), out)
    return out


def redact_mapping(
    mapping: Any,
    *,
    keys: Optional[Iterable[str]] = None,
    patterns: Optional[Iterable[_PatternLike]] = None,
    strategy: _StrategyLike = MaskingStrategy.REDACT,
    salt: Optional[Union[str, bytes]] = None,
) -> Any:
    """Redact a telemetry / log dict by sensitive key name and/or value pattern.

    Record-agnostic counterpart to ``apply_masking_to_record`` that needs no
    registered model. A value is masked when its key (case-insensitive)
    matches ``keys`` OR its string form matches any of ``patterns``. Nested
    mappings are redacted recursively. Non-mapping input is returned
    unchanged (so callers can pass arbitrary ``record.args`` safely).
    """
    if not isinstance(mapping, Mapping):
        return mapping
    key_set = {k.lower() for k in (keys or ())}
    compiled = _compile(patterns)
    out: Dict[str, Any] = {}
    for k, v in mapping.items():
        if isinstance(v, Mapping):
            out[k] = redact_mapping(
                v, keys=keys, patterns=patterns, strategy=strategy, salt=salt
            )
        elif isinstance(k, str) and k.lower() in key_set:
            out[k] = _mask_match(str(v), strategy, salt)
        elif compiled and any(p.search(str(v)) for p in compiled):
            out[k] = redact_text(v, patterns, strategy=strategy, salt=salt)
        else:
            out[k] = v
    return out


class RedactionFilter(logging.Filter):
    """A ``logging.Filter`` that redacts sensitive data from log records.

    Record-agnostic: needs no ``ModelDefinition``. Attach it to any handler
    or logger. The filter redacts the rendered message (``record.getMessage()``
    after %-formatting) by ``patterns``, and any ``Mapping`` positional arg by
    ``keys`` + ``patterns``. It never drops a record (always returns ``True``)
    and never raises into the logging machinery.

    Example::

        import logging, re
        h = logging.StreamHandler()
        h.addFilter(RedactionFilter(patterns=[re.compile(r"\\b\\d{16}\\b")],
                                    strategy=MaskingStrategy.LAST_FOUR))
    """

    def __init__(
        self,
        name: str = "",
        *,
        patterns: Optional[Iterable[_PatternLike]] = None,
        keys: Optional[Iterable[str]] = None,
        strategy: _StrategyLike = MaskingStrategy.REDACT,
        salt: Optional[Union[str, bytes]] = None,
    ) -> None:
        super().__init__(name)
        self._patterns = _compile(patterns)
        self._keys = list(keys or ())
        self._strategy = strategy
        self._salt = salt

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact any Mapping positional arg by key/pattern first, so a
        # subsequent getMessage() renders already-redacted dict values.
        if self._keys or self._patterns:
            if isinstance(record.args, Mapping):
                record.args = redact_mapping(
                    record.args,
                    keys=self._keys,
                    patterns=self._patterns,
                    strategy=self._strategy,
                    salt=self._salt,
                )
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    (
                        redact_text(
                            a, self._patterns, strategy=self._strategy, salt=self._salt
                        )
                        if isinstance(a, str)
                        else a
                    )
                    for a in record.args
                )
        # Redact the rendered message by pattern.
        if self._patterns:
            try:
                rendered = record.getMessage()
            except (TypeError, ValueError):
                # Malformed record (arg/placeholder mismatch). The handler's own
                # getMessage() would raise identically at format time, so this is
                # not our error to introduce — redact the raw template in place
                # (args were already redacted above) and let the handler surface
                # the real formatting error. A logging.Filter MUST NOT raise into
                # the logging machinery (see RedactionFilter contract).
                if isinstance(record.msg, str):
                    record.msg = redact_text(
                        record.msg,
                        self._patterns,
                        strategy=self._strategy,
                        salt=self._salt,
                    )
                return True
            redacted = redact_text(
                rendered, self._patterns, strategy=self._strategy, salt=self._salt
            )
            if redacted != rendered:
                record.msg = redacted
                record.args = ()
        return True
