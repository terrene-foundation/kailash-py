# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: the four observability flags stop lying (#2084 / #2070 follow-up).

`SmartDefaultsManager.create_observability` advertises four subsystems —
tracing, metrics, logging, audit. None of them exists: every import raises
`ImportError`, every one is caught, and the function always returns a
`HookManager` with zero hooks. Meanwhile all four flags default `True` and
`is_observability_enabled()` returns `True`, so the config actively reports
that observability is on.

The fix makes the flags HONEST. It does not make the features exist — that is
#2084, deliberately kept separate so the record does not blur them.

TRI-STATE, and why it is not a bool. The flags cannot simply raise when `True`,
because `True` IS the default: raising would break every agent construction,
including for callers who never mentioned observability. A dataclass cannot
distinguish "explicitly passed True" from "defaulted True" without a sentinel,
so the flags become `Optional[bool]`:

    None  (default, nobody asked)  -> loud WARN, behaviour otherwise unchanged
    True  (explicit opt-in)        -> raise, naming the subsystem
    False (explicit opt-out)       -> silent

Same mechanism as `LoggingHook.redact_sensitive` in #2070, and for the same
underlying reason: separating "requested" from "defaulted" is the only way to
fail loudly for the first without breaking the second.

WHAT NO EXISTING TEST ASSERTED, and why this shipped: nothing anywhere checks
that `create_observability` actually REGISTERS anything. `HookManager` exposes
no public accessor for registered hooks — `get_stats()` reports execution
counts, not registrations — so the only route is the private `_hooks`. That
missing public surface is part of why four dead subsystems were invisible, and
it is why `test_enabled_implies_hooks_registered` below reaches into `_hooks`
rather than asserting on a supported API.
"""

from __future__ import annotations

import logging

import pytest

from kaizen.agent_config import AgentConfig
from kaizen.errors import ObservabilityNotImplemented
from kaizen.smart_defaults import (
    SmartDefaultsManager,
    _warn_observability_unimplemented,
)


@pytest.fixture(autouse=True)
def _reset_one_time_warning() -> None:
    """Clear the process-wide warn cache before EVERY test in this module.

    Load-bearing, not hygiene. The warning fires once per process, so without
    this reset a test that asserts the warning is ABSENT (`explicit_false_is
    _silent`) would pass merely because an earlier test consumed it — a
    non-discriminating pass. Clearing first makes each absence assertion mean
    what it says.
    """
    _warn_observability_unimplemented.cache_clear()


#: Deliberately synthetic. `AgentConfig` requires SOME model string, but
#: nothing in this suite dispatches to a provider — every assertion is about
#: config flags and hook registration. A sentinel rather than a real model
#: name keeps this independent of `.env` (`rules/env-models.md`).
MODEL = "test-model"

#: flag name -> (human subsystem name that MUST appear in the error)
SUBSYSTEMS = {
    "enable_tracing": "tracing",
    "enable_metrics": "metrics",
    "enable_logging": "logging",
    "enable_audit": "audit",
}


def _registered_hook_count(manager: object) -> int:
    """Count registered hooks via the private `_hooks` (no public accessor)."""
    if manager is None:
        return 0
    return sum(len(v) for v in getattr(manager, "_hooks", {}).values())


class TestDefaultConstructionStaysWorking:
    """Requirement: nobody who did NOT ask gets a new error."""

    def test_default_construction_does_not_raise(self) -> None:
        """NEGATIVE control — passes before AND after.

        This is the assertion that forced the tri-state. All four flags
        default True today, so a naive "raise when True" would redden this
        for every caller in existence.
        """
        config = AgentConfig(model=MODEL)
        SmartDefaultsManager().create_observability(config)

    def test_default_construction_warns_that_features_are_unimplemented(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The default path must say NOT IMPLEMENTED, not 'not available'.

        Today it logs 'Tracing hook not available, skipping' — which reads as
        a missing optional dependency an operator could go install. There is
        nothing to install; the subsystem does not exist. The wording is the
        whole point of the warning, so the assertion is on the wording.
        """
        config = AgentConfig(model=MODEL)
        with caplog.at_level(logging.WARNING):
            SmartDefaultsManager().create_observability(config)

        rendered = "\n".join(r.getMessage() for r in caplog.records)
        assert "not implemented" in rendered.lower(), (
            "The default path warned, but not that the subsystems are "
            "UNIMPLEMENTED. 'not available' implies an installable optional "
            "dependency; there is none."
        )
        for subsystem in SUBSYSTEMS.values():
            assert subsystem in rendered.lower(), (
                f"Warning did not name {subsystem!r}. An operator cannot act "
                f"on a warning that does not say which feature is missing."
            )

    def test_warning_fires_once_per_process_not_per_construction(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`create_observability` runs on EVERY agent construction.

        Warning per call turns a real signal into log spam, and a spammed
        warning is a silenced one — operators filter it, which is how the
        loud-warning remedy quietly becomes no remedy at all. An instance
        flag cannot fix this: `SmartDefaultsManager` is constructed per
        agent, so every instance would warn once and the spam would remain.
        """
        config = AgentConfig(model=MODEL)

        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                SmartDefaultsManager().create_observability(config)

        hits = [
            r for r in caplog.records if "not implemented" in r.getMessage().lower()
        ]
        assert len(hits) == 1, (
            f"Expected exactly ONE unimplemented-subsystem warning across 5 "
            f"agent constructions, got {len(hits)}. Per-construction warning "
            f"is log spam on the hot path."
        )


class TestExplicitOptInFailsLoudly:
    """Requirement: an explicit request for a nonexistent feature RAISES."""

    @pytest.mark.parametrize("flag,subsystem", sorted(SUBSYSTEMS.items()))
    def test_explicit_true_raises_naming_the_subsystem(
        self, flag: str, subsystem: str
    ) -> None:
        config = AgentConfig(model=MODEL, **{flag: True})

        with pytest.raises(ObservabilityNotImplemented) as excinfo:
            SmartDefaultsManager().create_observability(config)

        message = str(excinfo.value)
        assert subsystem in message.lower(), (
            f"{flag}=True raised, but the error does not name {subsystem!r}. "
            f"A generic 'not available' does not tell the operator which of "
            f"the four features they asked for is missing."
        )
        assert flag in message, "Error must name the flag the caller set."

    @pytest.mark.parametrize("flag", sorted(SUBSYSTEMS))
    def test_explicit_false_is_silent(
        self, flag: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Explicit opt-out: no raise, and no warning about that subsystem."""
        disabled = {name: False for name in SUBSYSTEMS}
        config = AgentConfig(model=MODEL, **disabled)

        with caplog.at_level(logging.WARNING):
            SmartDefaultsManager().create_observability(config)

        rendered = "\n".join(r.getMessage() for r in caplog.records).lower()
        assert "not implemented" not in rendered, (
            "Explicitly disabling every subsystem still warned about "
            "unimplemented features. Opting out is not asking."
        )


class TestIsObservabilityEnabledBecomesTruthful:
    """The config must stop reporting observability it does not have."""

    def test_false_by_default(self) -> None:
        """Was `True` while zero hooks registered — a false report, now correct."""
        assert AgentConfig(model=MODEL).is_observability_enabled() is False

    @pytest.mark.parametrize("flag", sorted(SUBSYSTEMS))
    def test_true_when_explicitly_requested(self, flag: str) -> None:
        """NEGATIVE control — the correction must not flatten to always-False."""
        config = AgentConfig(model=MODEL, **{flag: True})
        assert config.is_observability_enabled() is True

    def test_enabled_implies_hooks_registered(self) -> None:
        """THE INVARIANT whose absence let four dead subsystems ship.

        `is_observability_enabled()` must never report True while
        `create_observability` yields a manager with nothing in it. Either it
        reports False (nothing requested), or the request raises, or hooks are
        genuinely registered. The one state that must be unreachable is
        "enabled, and empty" — which was the shipped behaviour.
        """
        config = AgentConfig(model=MODEL)

        if not config.is_observability_enabled():
            return  # honest: nothing requested, nothing registered

        try:
            manager = SmartDefaultsManager().create_observability(config)
        except ObservabilityNotImplemented:
            return  # honest: the request failed loudly

        assert _registered_hook_count(manager) > 0, (
            "is_observability_enabled() reported True, create_observability() "
            "returned without raising, and ZERO hooks were registered. That is "
            "the exact state that shipped four unimplemented subsystems."
        )
