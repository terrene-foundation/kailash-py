# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""WEFT -- a citable, hash-chained provenance event schema for EATP v3.

WEFT (the crosswise thread in weaving, paired with the warp) records the
distribution provenance of governed subjects: the sequence of ``Mint`` /
``Distribute`` / ``Decline`` / ``Obsolete`` / ``HumanGate`` events by which a
subject enters, moves through, and leaves the governed fabric.

Each :class:`WeftEvent` is a versioned, citable envelope::

    {schema_version, kind, ts, session, identity_ref, payload, prev_link}

* ``schema_version`` reuses the #1590 ``SCHEMA_VERSION`` discriminator
  (``SCHEMA_VERSION_V3`` == ``"v3"``) so a WEFT log shares the audit-anchor
  versioning convention.
* ``kind`` is one of the five known :class:`WeftKind` members.
* :meth:`WeftEvent.content_hash` is ``"sha256:" + sha256(canonical_json)`` where
  ``canonical_json`` is the RFC 8785 (JCS) canonicalization of the envelope
  (:func:`kailash.trust._jcs.jcs_encode`). An event cited by its content hash is
  therefore byte-verifiable across every SDK -- WEFT builds ON the #1590 JCS
  keystone, it does not re-invent canonicalization. Because ``jcs_encode``
  rejects non-finite floats at serialize time, a ``NaN`` / ``Infinity`` in a
  payload fails CLOSED before it can enter a citable pre-image
  (``trust-plane-security.md`` MUST-8).
* ``prev_link`` is the ``content_hash`` of the predecessor event (``None`` for a
  genesis/first event), forming a tamper-evident chain.

Two load-bearing invariants:

1. **Reader MUST-IGNORE unknown kind** (forward-compat). :func:`read_weft_events`
   parsing an event whose ``kind`` it does not recognize IGNORES it gracefully
   (never crashes), preserving cross-``schema_version`` continuity: an older
   reader encountering a newer event kind skips it and keeps reading the chain.
   :meth:`WeftEvent.from_dict` is the STRICT counterpart -- it raises
   :class:`UnknownWeftKindError` on an unrecognized kind, and the reader is the
   forgiving wrapper that catches-and-skips.

2. **Distributor fails CLOSED on a missing required gate.**
   :meth:`WeftDistributor.distribute` for a subject that has no recorded
   ``HumanGate`` raises :class:`MissingGateError` -- the human gate is mandatory
   and its absence DENIES distribution (never silently permits). A gate for one
   subject does NOT authorize distributing a different subject.

Follows the EATP dataclass conventions (``eatp.md``): ``@dataclass`` with
``to_dict`` / ``from_dict``, a ``str``-backed ``Enum`` for ``kind``, an explicit
``__all__``, ``from __future__ import annotations``, and a ``PactError``-derived
error hierarchy that fails closed on unknown / error states.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from kailash.trust._jcs import jcs_encode
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "WeftKind",
    "WeftError",
    "UnknownWeftKindError",
    "MissingGateError",
    "WeftEvent",
    "read_weft_events",
    "WeftDistributor",
]


class WeftKind(str, Enum):
    """The five recognized WEFT provenance event kinds.

    ``str``-backed so ``kind`` serializes to its wire name (``"Mint"``, ...)
    directly in JSON. A ``kind`` value outside this set is an UNKNOWN kind: the
    reader ignores it (forward-compat), :meth:`WeftEvent.from_dict` raises
    :class:`UnknownWeftKindError`.
    """

    MINT = "Mint"
    """A governed subject is minted into the fabric (its provenance origin)."""

    DISTRIBUTE = "Distribute"
    """A subject is distributed to a recipient. Requires a prior ``HumanGate``."""

    DECLINE = "Decline"
    """A distribution / mint request is declined (fail-closed refusal)."""

    OBSOLETE = "Obsolete"
    """A subject is retired -- no longer valid for distribution."""

    HUMAN_GATE = "HumanGate"
    """A human authorization gate is recorded for a subject (unlocks Distribute)."""


class WeftError(PactError):
    """Base class for WEFT provenance errors.

    Inherits ``PactError`` (carrying a structured ``.details`` dict) so WEFT
    failures are caught by the PACT trust-layer catch blocks rather than
    surfacing as unstructured crashes.
    """


class UnknownWeftKindError(WeftError):
    """Raised by :meth:`WeftEvent.from_dict` when ``kind`` is not a known member.

    STRICT-parse signal. The forward-compat reader (:func:`read_weft_events`)
    catches this and SKIPS the event, so an older reader stays forward-compatible
    with a newer schema that adds event kinds.
    """


class MissingGateError(WeftError):
    """Raised by :meth:`WeftDistributor.distribute` when the subject has no gate.

    Fail-closed: a ``Distribute`` for a subject with no recorded ``HumanGate`` is
    DENIED. The absence of the mandatory gate never silently permits distribution.
    """


@dataclass
class WeftEvent:
    """A single citable, hash-chained WEFT provenance event.

    Attributes:
        schema_version: The #1590 schema discriminator (default ``"v3"``).
        kind: One of the five :class:`WeftKind` members.
        ts: ISO-8601 timestamp string of when the event occurred.
        session: The session identifier under which the event was emitted.
        identity_ref: A reference to the emitting identity (D/T/R address, key
            fingerprint, or opaque handle).
        payload: Structured, event-specific data (JSON-native / typed-scalar).
        prev_link: The ``content_hash`` of the predecessor event, or ``None`` for
            a genesis event.
    """

    schema_version: str
    kind: WeftKind
    ts: str
    session: str
    identity_ref: str
    payload: dict[str, Any] = field(default_factory=dict)
    prev_link: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope to a JSON-native dict.

        ``kind`` serializes as its ``.value`` (the wire name). Key order here is
        cosmetic -- :meth:`canonical_json` re-sorts by RFC 8785 UTF-16 order.
        """
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "ts": self.ts,
            "session": self.session,
            "identity_ref": self.identity_ref,
            "payload": self.payload,
            "prev_link": self.prev_link,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeftEvent:
        """Deserialize STRICTLY from a dict.

        Raises:
            WeftError: if a required field is missing.
            UnknownWeftKindError: if ``kind`` is not a recognized
                :class:`WeftKind` member. The forgiving forward-compat path is
                :func:`read_weft_events`, which catches this and skips.
        """
        for required in ("schema_version", "kind", "ts", "session", "identity_ref"):
            if required not in data:
                raise WeftError(
                    f"WeftEvent.from_dict: missing required field {required!r}",
                    details={"missing_field": required},
                )
        raw_kind = data["kind"]
        try:
            kind = WeftKind(raw_kind)
        except ValueError as exc:
            raise UnknownWeftKindError(
                f"WeftEvent.from_dict: unrecognized kind {raw_kind!r}; "
                f"known kinds are {[k.value for k in WeftKind]}",
                details={"kind": raw_kind},
            ) from exc
        return cls(
            schema_version=data["schema_version"],
            kind=kind,
            ts=data["ts"],
            session=data["session"],
            identity_ref=data["identity_ref"],
            payload=data.get("payload", {}),
            prev_link=data.get("prev_link"),
        )

    def canonical_json(self) -> str:
        """Return the RFC 8785 (JCS) canonical JSON string of the envelope.

        Reuses the #1590 JCS keystone (:func:`kailash.trust._jcs.jcs_encode`),
        which rejects non-finite floats -- a ``NaN`` / ``Infinity`` in ``payload``
        fails CLOSED here before it can enter a citable pre-image.
        """
        return jcs_encode(self.to_dict())

    def content_hash(self) -> str:
        """Return ``"sha256:<hex>"`` -- the citable content hash of the envelope.

        This is the value a downstream event's ``prev_link`` references and the
        token by which the event is cited. Byte-stable across SDKs because the
        pre-image is the JCS canonicalization.
        """
        encoded = self.canonical_json().encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def read_weft_events(raw_events: Iterable[dict[str, Any]]) -> list[WeftEvent]:
    """Parse a sequence of raw event dicts, IGNORING unrecognized kinds.

    Forward-compat reader: an event whose ``kind`` this reader does not recognize
    is skipped (logged at DEBUG), not raised. This preserves cross-``schema_version``
    continuity -- an older reader keeps reading a chain that contains newer event
    kinds it does not understand. A genuinely malformed event (missing a required
    field) still raises :class:`WeftError`, because that is corruption, not a
    forward-compatible unknown kind.

    Args:
        raw_events: An iterable of event dicts (e.g. loaded from a JSON log).

    Returns:
        The recognized events, in input order, with unknown-kind entries dropped.
    """
    out: list[WeftEvent] = []
    for raw in raw_events:
        try:
            out.append(WeftEvent.from_dict(raw))
        except UnknownWeftKindError:
            logger.debug(
                "weft.reader.skip_unknown_kind",
                extra={"kind": raw.get("kind") if isinstance(raw, dict) else None},
            )
            continue
    return out


class WeftDistributor:
    """A hash-chained WEFT provenance emitter with a fail-closed gate invariant.

    The distributor maintains the running chain (``prev_link`` threading) and the
    set of subjects that have passed a ``HumanGate``. ``distribute`` for a
    subject with no recorded gate raises :class:`MissingGateError` -- fail-closed.

    Args:
        session: The session identifier stamped on every emitted event.
        identity_ref: The emitting identity stamped on every event.
        genesis_prev: The ``prev_link`` of the first emitted event (``None`` for a
            fresh genesis chain; a prior ``content_hash`` to continue an existing
            chain).
    """

    def __init__(
        self,
        *,
        session: str,
        identity_ref: str,
        genesis_prev: str | None = None,
    ) -> None:
        self._session = session
        self._identity_ref = identity_ref
        self._prev_link = genesis_prev
        self._gated: set[str] = set()
        self._log: list[WeftEvent] = []

    def _emit(self, kind: WeftKind, payload: dict[str, Any], *, ts: str) -> WeftEvent:
        """Emit an event, thread the chain, append to the log."""
        event = WeftEvent(
            schema_version=SCHEMA_VERSION_V3,
            kind=kind,
            ts=ts,
            session=self._session,
            identity_ref=self._identity_ref,
            payload=payload,
            prev_link=self._prev_link,
        )
        self._prev_link = event.content_hash()
        self._log.append(event)
        return event

    def mint(self, subject_ref: str, *, ts: str, **payload_extra: Any) -> WeftEvent:
        """Emit a ``Mint`` event for ``subject_ref``."""
        return self._emit(
            WeftKind.MINT, {"subject_ref": subject_ref, **payload_extra}, ts=ts
        )

    def human_gate(
        self, subject_ref: str, *, ts: str, **payload_extra: Any
    ) -> WeftEvent:
        """Emit a ``HumanGate`` event and mark ``subject_ref`` as gated.

        Recording the gate is what unlocks a subsequent :meth:`distribute` of the
        SAME subject. A gate for one subject does NOT authorize a different one.
        """
        event = self._emit(
            WeftKind.HUMAN_GATE, {"subject_ref": subject_ref, **payload_extra}, ts=ts
        )
        self._gated.add(subject_ref)
        return event

    def distribute(
        self, subject_ref: str, *, ts: str, **payload_extra: Any
    ) -> WeftEvent:
        """Emit a ``Distribute`` event for ``subject_ref`` -- fail-closed on no gate.

        Raises:
            MissingGateError: if ``subject_ref`` has no recorded ``HumanGate``.
                The mandatory gate's absence DENIES distribution (never permits).
        """
        if subject_ref not in self._gated:
            raise MissingGateError(
                f"Distribute denied for subject {subject_ref!r}: no HumanGate "
                f"recorded. A human gate is mandatory before distribution.",
                details={"subject_ref": subject_ref, "kind": WeftKind.DISTRIBUTE.value},
            )
        return self._emit(
            WeftKind.DISTRIBUTE, {"subject_ref": subject_ref, **payload_extra}, ts=ts
        )

    def decline(
        self, subject_ref: str, *, reason: str, ts: str, **payload_extra: Any
    ) -> WeftEvent:
        """Emit a ``Decline`` event for ``subject_ref``."""
        return self._emit(
            WeftKind.DECLINE,
            {"subject_ref": subject_ref, "reason": reason, **payload_extra},
            ts=ts,
        )

    def obsolete(self, subject_ref: str, *, ts: str, **payload_extra: Any) -> WeftEvent:
        """Emit an ``Obsolete`` event for ``subject_ref``."""
        return self._emit(
            WeftKind.OBSOLETE, {"subject_ref": subject_ref, **payload_extra}, ts=ts
        )

    @property
    def log(self) -> list[WeftEvent]:
        """A snapshot of the emitted events, in chain order."""
        return list(self._log)

    @property
    def head(self) -> str | None:
        """The ``content_hash`` of the most recent event (chain head), or ``None``."""
        return self._prev_link
