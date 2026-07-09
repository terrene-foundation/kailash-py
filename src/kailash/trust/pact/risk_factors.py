# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Extensible risk-factor calibration seam for the governance disposition step.

The ``GovernanceEngine`` calibrates a verdict primarily by *limit proximity*
(how close a cost is to a financial ceiling, whether an action is on the
allow/block list, whether it falls inside active hours, etc.). Limit proximity
does not, on its own, capture the *intrinsic* risk of an action: a $0 action
that is irreversible and touches secret data is far riskier than its spend
proximity suggests.

This module adds a structured, **extensible** risk-factor input to that
disposition step. A caller may pass a ``risk_factors`` mapping in the action
context::

    engine.verify_action(
        "Eng-CTO-Backend-Lead",
        "delete_production_table",
        {"cost": 0.0, "risk_factors": {"reversibility": "irreversible"}},
    )

Each named factor is evaluated by a registered callable that maps the factor
value to a *proposed* verification level. The engine then combines the
limit-proximity verdict with the worst factor verdict using a **monotonic**
max-severity rule (``combine_levels``): factors can only *tighten* a verdict,
never loosen it. A near-zero-limit-proximity action that is irreversible or
high-materiality is therefore escalated (``held``) or denied (``blocked``)
independently of spend proximity.

Design invariants (mirroring ``rules/pact-governance.md`` and the trust plane):

* **Extensible without engine edits.** New factors register through
  :data:`GLOBAL_RISK_FACTOR_REGISTRY` (or a per-call registry); the engine
  composes whatever is registered. The factor->level mapping is deterministic
  configuration, NOT model reasoning.
* **Monotonic.** :func:`combine_levels` takes the maximum severity, so a factor
  can never downgrade ``blocked`` -> ``flagged``.
* **Fail-closed.** A malformed / unparseable factor set (wrong type, unknown
  factor name, unknown value token, or a factor callable that raises) raises
  :class:`MalformedRiskFactorError`. The engine treats that as maximal risk
  (``blocked``) -- it is NEVER silently ignored.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "RiskLevel",
    "RISK_LEVEL_ORDER",
    "combine_levels",
    "MalformedRiskFactorError",
    "RiskFactor",
    "RiskFactorEvaluation",
    "RiskFactorRegistry",
    "GLOBAL_RISK_FACTOR_REGISTRY",
    "register_risk_factor",
    "evaluate_risk_factors",
    "reversibility_factor",
    "materiality_factor",
    "blast_radius_factor",
    "novelty_factor",
    "sensitivity_factor",
]

# ---------------------------------------------------------------------------
# Verification-level ordering (shared with the engine's gradient zones)
# ---------------------------------------------------------------------------

#: The four verification gradient levels, from most permissive to most
#: restrictive. Identical to the ``GovernanceVerdict.level`` vocabulary so a
#: proposed factor level composes directly with the engine verdict.
RiskLevel = Literal["auto_approved", "flagged", "held", "blocked"]

#: Total ordering over :data:`RiskLevel`. Higher value == more restrictive.
RISK_LEVEL_ORDER: dict[str, int] = {
    "auto_approved": 0,
    "flagged": 1,
    "held": 2,
    "blocked": 3,
}


def combine_levels(*levels: str) -> str:
    """Return the most restrictive (highest-severity) level among ``levels``.

    This is the monotonic-tightening combinator: the result is never less
    restrictive than any input, so a risk factor can only escalate a verdict.

    Args:
        levels: One or more verification level strings.

    Returns:
        The level with the greatest :data:`RISK_LEVEL_ORDER` value. Defaults to
        ``"auto_approved"`` when called with no arguments.

    Raises:
        MalformedRiskFactorError: If any argument is not a recognized level.
            Unrecognized levels fail closed rather than sorting as permissive.
    """
    result = "auto_approved"
    result_rank = RISK_LEVEL_ORDER["auto_approved"]
    for level in levels:
        rank = RISK_LEVEL_ORDER.get(level)
        if rank is None:
            raise MalformedRiskFactorError(
                f"Unknown verification level {level!r} -- cannot combine; "
                f"expected one of {sorted(RISK_LEVEL_ORDER)}",
                details={"level": level},
            )
        if rank > result_rank:
            result, result_rank = level, rank
    return result


# ---------------------------------------------------------------------------
# Typed error
# ---------------------------------------------------------------------------


class MalformedRiskFactorError(PactError):
    """Raised when a risk-factor set cannot be parsed or evaluated.

    Triggers: ``risk_factors`` is not a mapping, a factor name is not
    registered, a factor value is not in the factor's documented vocabulary,
    or a factor callable raised. The engine maps this to a fail-closed
    ``blocked`` verdict -- a malformed risk declaration is treated as maximal
    risk, never silently dropped.
    """

    pass


# ---------------------------------------------------------------------------
# Factor + evaluation records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskFactor:
    """A named, registered risk-calibration factor.

    Attributes:
        name: The key looked up in the ``risk_factors`` context mapping.
        evaluate: A pure callable ``(action_ctx, factor_value) -> level``. It
            MUST return one of the :data:`RiskLevel` strings, or raise
            :class:`MalformedRiskFactorError` for an unparseable value. The
            engine composes the returned level via :func:`combine_levels`, so a
            factor can only tighten the verdict regardless of what it returns.
        description: Human-readable summary for audit / documentation.
    """

    name: str
    evaluate: Callable[[Mapping[str, Any], Any], str]
    description: str = ""


@dataclass(frozen=True)
class RiskFactorEvaluation:
    """Structured result of evaluating a ``risk_factors`` set.

    Attributes:
        present: True if the action context carried a ``risk_factors`` mapping.
        combined_level: The most restrictive level across all factors (the
            value that gets combined with the limit-proximity verdict). When no
            factors are present this is ``"auto_approved"`` (a no-op).
        per_factor: Mapping of factor name -> the level that factor proposed.
        driving_factors: The factor names whose proposed level equals
            ``combined_level`` (and is more restrictive than ``auto_approved``)
            -- i.e. the factor(s) that actually shifted the verdict.
        factor_values: The raw input tokens per factor, preserved for audit.
    """

    present: bool
    combined_level: str
    per_factor: dict[str, str] = field(default_factory=dict)
    driving_factors: list[str] = field(default_factory=list)
    factor_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for audit anchoring."""
        return {
            "present": self.present,
            "combined_level": self.combined_level,
            "per_factor": dict(self.per_factor),
            "driving_factors": list(self.driving_factors),
            "factor_values": dict(self.factor_values),
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class RiskFactorRegistry:
    """Thread-safe registry of :class:`RiskFactor` objects.

    New factors register here (or on a per-call registry) without any edit to
    the engine core -- the engine iterates whatever is registered.
    """

    def __init__(self) -> None:
        self._factors: dict[str, RiskFactor] = {}
        self._lock = threading.RLock()

    def register(self, factor: RiskFactor, *, replace: bool = False) -> None:
        """Register a factor.

        Args:
            factor: The :class:`RiskFactor` to register.
            replace: If False (default), registering a duplicate name raises.
                If True, the existing factor is overwritten.

        Raises:
            ValueError: If ``factor.name`` is empty, ``factor.evaluate`` is not
                callable, or the name is already registered and ``replace`` is
                False.
        """
        if not factor.name:
            raise ValueError("RiskFactor.name must be a non-empty string")
        if not callable(factor.evaluate):
            raise ValueError(
                f"RiskFactor.evaluate for {factor.name!r} must be callable"
            )
        with self._lock:
            if not replace and factor.name in self._factors:
                raise ValueError(
                    f"Risk factor {factor.name!r} is already registered; "
                    f"pass replace=True to override"
                )
            self._factors[factor.name] = factor

    def get(self, name: str) -> RiskFactor | None:
        """Return the factor registered under ``name``, or None."""
        with self._lock:
            return self._factors.get(name)

    def unregister(self, name: str) -> None:
        """Remove ``name`` from the registry if present (idempotent)."""
        with self._lock:
            self._factors.pop(name, None)

    def names(self) -> list[str]:
        """Return the sorted list of registered factor names."""
        with self._lock:
            return sorted(self._factors)


#: Process-wide default registry. New factors register here to be picked up by
#: :func:`evaluate_risk_factors` (and therefore the engine) automatically.
GLOBAL_RISK_FACTOR_REGISTRY = RiskFactorRegistry()


def register_risk_factor(factor: RiskFactor, *, replace: bool = False) -> RiskFactor:
    """Register ``factor`` on the global registry and return it.

    Convenience wrapper so a new factor registers in one call without the
    engine ever being edited::

        register_risk_factor(RiskFactor("pii_exposure", my_callable))
    """
    GLOBAL_RISK_FACTOR_REGISTRY.register(factor, replace=replace)
    return factor


# ---------------------------------------------------------------------------
# Built-in factor vocabularies + callables
# ---------------------------------------------------------------------------


def _map_vocab(factor_name: str, vocab: Mapping[str, str], value: Any) -> str:
    """Map a documented token ``value`` to a level via ``vocab``.

    Fail-closed: a non-string value or an unknown token raises
    :class:`MalformedRiskFactorError` (never silently treated as low risk).
    """
    if not isinstance(value, str):
        raise MalformedRiskFactorError(
            f"Risk factor {factor_name!r} expects a string token "
            f"(one of {sorted(vocab)}), got {type(value).__name__}",
            details={"factor": factor_name, "value_type": type(value).__name__},
        )
    token = value.strip().lower()
    level = vocab.get(token)
    if level is None:
        raise MalformedRiskFactorError(
            f"Risk factor {factor_name!r} received unknown token {value!r}; "
            f"expected one of {sorted(vocab)}",
            details={"factor": factor_name, "value": value},
        )
    return level


#: How easily the action can be undone.
_REVERSIBILITY_VOCAB: dict[str, str] = {
    "reversible": "auto_approved",
    "recoverable": "flagged",
    "irreversible": "held",
}

#: Business/impact materiality of the action's outcome.
_MATERIALITY_VOCAB: dict[str, str] = {
    "none": "auto_approved",
    "low": "flagged",
    "moderate": "flagged",
    "high": "held",
    "critical": "blocked",
}

#: How wide a surface the action affects.
_BLAST_RADIUS_VOCAB: dict[str, str] = {
    "isolated": "auto_approved",
    "local": "flagged",
    "broad": "held",
    "systemic": "blocked",
}

#: How novel / anomalous the action is relative to normal operation.
_NOVELTY_VOCAB: dict[str, str] = {
    "routine": "auto_approved",
    "familiar": "auto_approved",
    "novel": "flagged",
    "anomalous": "held",
}

#: Sensitivity of the data / resource the action touches.
_SENSITIVITY_VOCAB: dict[str, str] = {
    "public": "auto_approved",
    "internal": "flagged",
    "confidential": "held",
    "secret": "blocked",
}


def reversibility_factor(action_ctx: Mapping[str, Any], value: Any) -> str:
    """Map reversibility -> level. Irreversible actions escalate to ``held``."""
    return _map_vocab("reversibility", _REVERSIBILITY_VOCAB, value)


def materiality_factor(action_ctx: Mapping[str, Any], value: Any) -> str:
    """Map materiality/impact -> level. Critical impact denies (``blocked``)."""
    return _map_vocab("materiality", _MATERIALITY_VOCAB, value)


def blast_radius_factor(action_ctx: Mapping[str, Any], value: Any) -> str:
    """Map blast radius -> level. Systemic blast radius denies (``blocked``)."""
    return _map_vocab("blast_radius", _BLAST_RADIUS_VOCAB, value)


def novelty_factor(action_ctx: Mapping[str, Any], value: Any) -> str:
    """Map novelty/anomaly -> level. Anomalous actions escalate to ``held``."""
    return _map_vocab("novelty", _NOVELTY_VOCAB, value)


def sensitivity_factor(action_ctx: Mapping[str, Any], value: Any) -> str:
    """Map data sensitivity -> level. Secret data denies (``blocked``)."""
    return _map_vocab("sensitivity", _SENSITIVITY_VOCAB, value)


def _register_builtins(registry: RiskFactorRegistry) -> None:
    registry.register(
        RiskFactor(
            "reversibility",
            reversibility_factor,
            "How easily the action can be undone.",
        ),
        replace=True,
    )
    registry.register(
        RiskFactor(
            "materiality",
            materiality_factor,
            "Business / impact materiality of the action outcome.",
        ),
        replace=True,
    )
    registry.register(
        RiskFactor(
            "blast_radius",
            blast_radius_factor,
            "How wide a surface the action affects.",
        ),
        replace=True,
    )
    registry.register(
        RiskFactor(
            "novelty",
            novelty_factor,
            "How novel / anomalous the action is vs normal operation.",
        ),
        replace=True,
    )
    registry.register(
        RiskFactor(
            "sensitivity",
            sensitivity_factor,
            "Sensitivity of the data / resource the action touches.",
        ),
        replace=True,
    )


_register_builtins(GLOBAL_RISK_FACTOR_REGISTRY)


# ---------------------------------------------------------------------------
# Evaluation entry point
# ---------------------------------------------------------------------------


def evaluate_risk_factors(
    action_ctx: Mapping[str, Any],
    registry: RiskFactorRegistry | None = None,
) -> RiskFactorEvaluation:
    """Evaluate the ``risk_factors`` entry of an action context.

    Args:
        action_ctx: The action context mapping. If it carries a ``risk_factors``
            key, that value MUST be a mapping of ``factor_name -> factor_value``.
        registry: The registry to resolve factor names against. Defaults to
            :data:`GLOBAL_RISK_FACTOR_REGISTRY`.

    Returns:
        A :class:`RiskFactorEvaluation`. When no ``risk_factors`` key is present
        the result is a no-op (``present=False``, ``combined_level=
        "auto_approved"``) so backward-compatible callers are unaffected.

    Raises:
        MalformedRiskFactorError: If ``risk_factors`` is present but is not a
            mapping, names an unregistered factor, carries an unparseable value,
            or a factor callable raises. Fail-closed by design -- the caller
            (the engine) maps this to a ``blocked`` verdict.
    """
    reg = registry if registry is not None else GLOBAL_RISK_FACTOR_REGISTRY

    if "risk_factors" not in action_ctx:
        return RiskFactorEvaluation(present=False, combined_level="auto_approved")

    raw = action_ctx["risk_factors"]
    if raw is None:
        return RiskFactorEvaluation(present=False, combined_level="auto_approved")
    if not isinstance(raw, Mapping):
        raise MalformedRiskFactorError(
            f"'risk_factors' must be a mapping of factor_name -> value, got "
            f"{type(raw).__name__} -- fail-closed to BLOCKED",
            details={"risk_factors_type": type(raw).__name__},
        )

    per_factor: dict[str, str] = {}
    factor_values: dict[str, Any] = {}
    combined = "auto_approved"

    for name, value in raw.items():
        if not isinstance(name, str):
            raise MalformedRiskFactorError(
                f"Risk factor names must be strings, got {type(name).__name__}",
                details={"name_type": type(name).__name__},
            )
        factor = reg.get(name)
        if factor is None:
            raise MalformedRiskFactorError(
                f"Unknown risk factor {name!r}; registered factors are "
                f"{reg.names()} -- fail-closed to BLOCKED",
                details={"factor": name, "registered": reg.names()},
            )
        try:
            proposed = factor.evaluate(action_ctx, value)
        except MalformedRiskFactorError:
            raise
        except Exception as exc:  # a factor callable misbehaved -> fail closed
            raise MalformedRiskFactorError(
                f"Risk factor {name!r} raised while evaluating value {value!r}: "
                f"{exc} -- fail-closed to BLOCKED",
                details={"factor": name, "error": str(exc)},
            ) from exc
        if proposed not in RISK_LEVEL_ORDER:
            raise MalformedRiskFactorError(
                f"Risk factor {name!r} returned invalid level {proposed!r}; "
                f"expected one of {sorted(RISK_LEVEL_ORDER)}",
                details={"factor": name, "returned": proposed},
            )
        per_factor[name] = proposed
        factor_values[name] = value
        combined = combine_levels(combined, proposed)

    driving = (
        [n for n, lvl in per_factor.items() if lvl == combined]
        if combined != "auto_approved"
        else []
    )

    return RiskFactorEvaluation(
        present=True,
        combined_level=combined,
        per_factor=per_factor,
        driving_factors=sorted(driving),
        factor_values=factor_values,
    )
