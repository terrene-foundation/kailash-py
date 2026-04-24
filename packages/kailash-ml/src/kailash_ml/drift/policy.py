# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Reference-refresh policies for :class:`DriftMonitor`.

Per ``specs/ml-drift.md §4.5`` the drift monitor supports four
reference-refresh modes:

- ``static`` (default) — reference immutable until manually superseded.
- ``rolling`` — reference auto-refreshed to the last ``window`` on each
  ``check_drift`` call.
- ``sliding`` — rolling with an explicit ``refresh_cadence`` so heavy
  reference refreshes do not re-materialise on every check.
- ``seasonal`` — current window compared against the SAME weekday/hour
  in the prior ``seasonal_period`` (e.g. last Monday for weekly
  seasonality).

Why: Weekly-seasonal businesses (retail, B2C SaaS) see "drift" every
Monday relative to last Sunday in static mode. The seasonal policy
aligns the reference to the same weekday/hour one period back so drift
fires only when the seasonal pattern itself changes.

Implementation note: this module holds the immutable policy dataclass
and the compile-time mode validation. The per-mode reference-slicing
logic lives in :mod:`kailash_ml.engines.drift_monitor` alongside the
monitor state it operates on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from kailash_ml.errors import DriftThresholdError

__all__ = [
    "DriftMonitorReferencePolicy",
    "DriftPolicyMode",
]


DriftPolicyMode = Literal["static", "rolling", "sliding", "seasonal"]


_VALID_MODES: frozenset[str] = frozenset({"static", "rolling", "sliding", "seasonal"})


def _require_positive_timedelta(name: str, value: timedelta) -> None:
    if value.total_seconds() <= 0:
        raise DriftThresholdError(
            reason=(
                f"DriftMonitorReferencePolicy.{name} must be a positive "
                f"timedelta, got {value!r}"
            ),
        )


@dataclass(frozen=True, slots=True)
class DriftMonitorReferencePolicy:
    """Reference-refresh policy for :class:`DriftMonitor`.

    Parameters
    ----------
    mode:
        One of ``"static"``, ``"rolling"``, ``"sliding"``, ``"seasonal"``.
        Default ``"static"`` matches the pre-W26.b behaviour.
    window:
        Required for ``rolling`` and ``sliding``. The reference is
        sliced to the most recent ``window`` relative to ``checked_at``.
        MUST be omitted for ``static`` and ``seasonal`` (validator
        rejects over-specification).
    seasonal_period:
        Required for ``seasonal``. The reference is sliced to the same
        weekday/hour exactly ``seasonal_period`` before ``checked_at``.
        MUST be omitted for other modes.
    refresh_cadence:
        Required for ``sliding``. Heavy reference refreshes are skipped
        when ``(now - last_refresh) < refresh_cadence``. ``rolling`` may
        set this to force sub-check cadence; ``static`` and
        ``seasonal`` MUST leave it unset.

    Raises
    ------
    DriftThresholdError
        When the mode / timedelta invariants are violated. Following
        ``rules/zero-tolerance.md §3`` the default is to reject
        misconfigurations at construction time rather than silently
        normalise.
    """

    mode: DriftPolicyMode = "static"
    window: timedelta | None = None
    seasonal_period: timedelta | None = None
    refresh_cadence: timedelta | None = None

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            raise DriftThresholdError(
                reason=(
                    f"DriftMonitorReferencePolicy.mode must be one of "
                    f"{sorted(_VALID_MODES)!r}, got {self.mode!r}"
                ),
            )

        if self.mode == "static":
            for field_name in ("window", "seasonal_period", "refresh_cadence"):
                value = getattr(self, field_name)
                if value is not None:
                    raise DriftThresholdError(
                        reason=(
                            f"DriftMonitorReferencePolicy.{field_name} MUST be "
                            f"None when mode='static', got {value!r}"
                        ),
                    )
            return

        if self.mode == "rolling":
            if self.window is None:
                raise DriftThresholdError(
                    reason=(
                        "DriftMonitorReferencePolicy.window is required when "
                        "mode='rolling'"
                    ),
                )
            _require_positive_timedelta("window", self.window)
            if self.seasonal_period is not None:
                raise DriftThresholdError(
                    reason=(
                        "DriftMonitorReferencePolicy.seasonal_period MUST be "
                        "None when mode='rolling'"
                    ),
                )
            if self.refresh_cadence is not None:
                _require_positive_timedelta("refresh_cadence", self.refresh_cadence)
            return

        if self.mode == "sliding":
            if self.window is None:
                raise DriftThresholdError(
                    reason=(
                        "DriftMonitorReferencePolicy.window is required when "
                        "mode='sliding'"
                    ),
                )
            if self.refresh_cadence is None:
                raise DriftThresholdError(
                    reason=(
                        "DriftMonitorReferencePolicy.refresh_cadence is "
                        "required when mode='sliding'"
                    ),
                )
            _require_positive_timedelta("window", self.window)
            _require_positive_timedelta("refresh_cadence", self.refresh_cadence)
            if self.seasonal_period is not None:
                raise DriftThresholdError(
                    reason=(
                        "DriftMonitorReferencePolicy.seasonal_period MUST be "
                        "None when mode='sliding'"
                    ),
                )
            return

        # mode == "seasonal"
        if self.seasonal_period is None:
            raise DriftThresholdError(
                reason=(
                    "DriftMonitorReferencePolicy.seasonal_period is required "
                    "when mode='seasonal'"
                ),
            )
        _require_positive_timedelta("seasonal_period", self.seasonal_period)
        if self.window is not None:
            # window is allowed as an explicit tolerance for seasonal
            # alignment, but MUST be positive.
            _require_positive_timedelta("window", self.window)
        if self.refresh_cadence is not None:
            raise DriftThresholdError(
                reason=(
                    "DriftMonitorReferencePolicy.refresh_cadence MUST be None "
                    "when mode='seasonal'"
                ),
            )

    # ------------------------------------------------------------------
    # Serialisation helpers — persisted in _kml_drift_references.policy_json.
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        def _td(value: timedelta | None) -> float | None:
            return None if value is None else value.total_seconds()

        return {
            "mode": self.mode,
            "window_seconds": _td(self.window),
            "seasonal_period_seconds": _td(self.seasonal_period),
            "refresh_cadence_seconds": _td(self.refresh_cadence),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DriftMonitorReferencePolicy:
        def _td(key: str) -> timedelta | None:
            raw = data.get(key)
            if raw is None:
                return None
            return timedelta(seconds=float(raw))

        return cls(
            mode=data.get("mode", "static"),
            window=_td("window_seconds"),
            seasonal_period=_td("seasonal_period_seconds"),
            refresh_cadence=_td("refresh_cadence_seconds"),
        )
