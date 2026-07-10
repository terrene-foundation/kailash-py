# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""VERIFY_CHAIN -- deny-overrides chain verification for EATP v3 (#1592).

``VERIFY_CHAIN`` composes a sequence of per-link verdicts into a single
delegation-chain verdict under **deny-overrides** semantics: ANY ``DENY`` link
denies the WHOLE chain, regardless of how many links allow. The first denying
link is cited so the failure is diagnosable.

Fail-closed by construction:

* An EMPTY chain is DENIED (an unverified chain never passes -- absence of a
  positive verdict is not a positive verdict).
* An unrecognized verdict token at parse time raises
  :class:`VerifyChainError` (a malformed link is corruption, never an implicit
  allow).

This mirrors the PACT 5-step access enforcement's "no path found -> DENY"
disposition (``pact-governance.md`` Rule 4) applied to a chain of independent
verdicts: the composition is only as permissive as its most restrictive link.

Follows the EATP dataclass conventions (``eatp.md``).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "COMPOSITION_MODE",
    "ChainVerdict",
    "ChainLink",
    "ChainResult",
    "VerifyChainError",
    "verify_chain",
]

COMPOSITION_MODE = "VERIFY_CHAIN"
"""The canonical name of this composition mode (deny-overrides)."""


class VerifyChainError(PactError):
    """Raised when a chain link cannot be parsed (fail-closed at the boundary).

    A malformed link (missing field, unrecognized verdict) is corruption, not a
    forward-compatible unknown -- it never silently resolves to an allow.
    """


class ChainVerdict(str, Enum):
    """A single link's binary verdict.

    ``str``-backed so it serializes to its wire name directly in JSON.
    """

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class ChainLink:
    """One link in a verification chain.

    Attributes:
        link_id: Stable identifier for this link (cited when it denies).
        verdict: The link's :class:`ChainVerdict` (``ALLOW`` / ``DENY``).
        reason: Human-readable rationale for the verdict.
    """

    link_id: str
    verdict: ChainVerdict
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-native dict (``verdict`` as its wire value)."""
        return {
            "link_id": self.link_id,
            "verdict": self.verdict.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainLink:
        """Deserialize STRICTLY from a dict.

        Raises:
            VerifyChainError: if a required field is missing or ``verdict`` is
                not a recognized :class:`ChainVerdict` (fail-closed -- an
                unrecognized verdict never becomes an implicit allow).
        """
        for required in ("link_id", "verdict"):
            if required not in data:
                raise VerifyChainError(
                    f"ChainLink.from_dict: missing required field {required!r}",
                    details={"missing_field": required},
                )
        raw_verdict = data["verdict"]
        try:
            verdict = ChainVerdict(raw_verdict)
        except ValueError as exc:
            raise VerifyChainError(
                f"ChainLink.from_dict: unrecognized verdict {raw_verdict!r}; "
                f"known verdicts are {[v.value for v in ChainVerdict]}. A "
                f"malformed link fails CLOSED (never an implicit allow).",
                details={"verdict": raw_verdict},
            ) from exc
        return cls(
            link_id=data["link_id"],
            verdict=verdict,
            reason=data.get("reason", ""),
        )


@dataclass(frozen=True)
class ChainResult:
    """The composed verdict of a :func:`verify_chain` evaluation.

    Attributes:
        allowed: ``True`` iff EVERY link allowed and the chain was non-empty.
        reason: Human-readable summary of the composed verdict.
        denied_by: The ``link_id`` of the first denying link, or ``None`` when
            allowed or when the chain was empty.
        evaluated: The number of links inspected before the verdict was reached
            (short-circuits at the first deny).
    """

    allowed: bool
    reason: str
    denied_by: str | None
    evaluated: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-native dict."""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "denied_by": self.denied_by,
            "evaluated": self.evaluated,
        }


def verify_chain(links: Sequence[ChainLink]) -> ChainResult:
    """Compose ``links`` under deny-overrides semantics.

    Deny-overrides: the first ``DENY`` link denies the whole chain (short-circuit).
    An empty chain is DENIED (fail-closed).

    Args:
        links: The ordered chain links to compose.

    Returns:
        A :class:`ChainResult` -- ``allowed`` iff the chain is non-empty AND
        every link allowed.
    """
    if not links:
        logger.debug("verify_chain.empty_fail_closed")
        return ChainResult(
            allowed=False,
            reason="empty chain denied (fail-closed): an unverified chain never passes",
            denied_by=None,
            evaluated=0,
        )
    for index, link in enumerate(links, start=1):
        if link.verdict is ChainVerdict.DENY:
            return ChainResult(
                allowed=False,
                reason=(
                    f"deny-overrides: link {link.link_id!r} denied"
                    + (f" ({link.reason})" if link.reason else "")
                ),
                denied_by=link.link_id,
                evaluated=index,
            )
    return ChainResult(
        allowed=True,
        reason=f"all {len(links)} link(s) allowed",
        denied_by=None,
        evaluated=len(links),
    )
