# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared canonical typed-scalar normalization for cross-SDK byte parity.

This module owns the SINGLE typed-scalar whitelist used by every
``ensure_ascii=True`` signing/hash canonical encoder in the trust plane:

* ``kailash.trust.signing.crypto.serialize_for_signing`` (trust-plane signing)
* ``kailash.trust.pact.audit.AuditAnchor`` metadata (audit-chain integrity hash)
* ``kailash.diagnostics.protocols.compute_trace_event_fingerprint`` (cross-SDK
  trace-event correlation anchor)

Before this module existed, each site re-implemented its own typed-scalar
handling: ``serialize_for_signing`` carried the canonical whitelist, while the
audit-chain and trace-event fingerprint paths used ``json.dumps(..., default=str)``.
``default=str`` is the cross-SDK byte-parity hazard documented below — it routes
``Decimal`` / ``UUID`` / ``datetime`` / ``set`` and any non-JSON-native value
through Python's implementation-defined ``str()``, whose output a peer
implementation (kailash-rs) has no reason to reproduce and which can change
across CPython versions. Consolidating the whitelist here gives every signing /
hash path ONE deterministic typed-scalar policy (issue #1403 / #1405).

The whitelist is byte-output-identical to the closure formerly nested inside
``serialize_for_signing`` (issue #959); extracting it is a pure refactor for
that path, regression-pinned by ``tests/test-vectors/trust-plane-canonical.json``.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

__all__ = ["canonical_scalars"]


def canonical_scalars(item: Any) -> Any:
    """Recursively convert objects to canonical JSON-serializable types.

    Type whitelist for byte-stable canonical bytes (issue #959):

    * dataclasses → ``asdict()`` recursively
    * dict → recursively, keys sorted
    * frozenset / set → sorted list
    * list / tuple → recursively
    * datetime / date / time → ``isoformat()`` (canonical Python form)
    * Decimal → ``str()`` with full precision preserved (e.g. ``Decimal("1.50")``
      serializes as ``"1.50"``, NOT ``"1.5"``)
    * UUID → hex string (``str(u)`` produces the canonical 8-4-4-4-12 form)
    * Enum → ``.value``
    * bytes → base64

    Native JSON primitives (str, int, float, bool, None) pass through
    unchanged. ANY other type is left for ``json.dumps`` to reject with
    ``TypeError`` — there is **no ``default=str`` fallback**, because
    ``str(obj)`` is implementation-defined and breaks cross-version /
    cross-SDK byte parity. The caller MUST ``json.dumps`` the returned value
    with ``allow_nan=False`` (and the caller's family-specific ``ensure_ascii``)
    to obtain the canonical string.
    """
    if not isinstance(item, type) and is_dataclass(item):
        # `item` is a dataclass INSTANCE here (not a class — excluded above).
        # Pyright's is_dataclass TypeGuard does not fully narrow away the
        # dataclass-class arm across the `and`, so suppress the known-false
        # arg narrowing on asdict (runtime is correct: a class falls through
        # to `else`). See microsoft/pyright is_dataclass+isinstance(type).
        return canonical_scalars(asdict(item))  # pyright: ignore[reportArgumentType]
    elif isinstance(item, dict):
        return {k: canonical_scalars(v) for k, v in sorted(item.items())}
    elif isinstance(item, (frozenset, set)):
        return [canonical_scalars(i) for i in sorted(item)]
    elif isinstance(item, (list, tuple)):
        return [canonical_scalars(i) for i in item]
    elif isinstance(item, (datetime, date, time)):
        return item.isoformat()
    elif isinstance(item, Decimal):
        return str(item)
    elif isinstance(item, uuid.UUID):
        return str(item)
    elif isinstance(item, Enum):
        return item.value
    elif isinstance(item, bytes):
        return base64.b64encode(item).decode("utf-8")
    else:
        return item
