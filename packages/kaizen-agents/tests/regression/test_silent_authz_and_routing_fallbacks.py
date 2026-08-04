# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: two silent fallbacks made loud (forest W12b + W13).

Both defects here are the SAME shape, found in two different files: a code path
whose SIBLING path is loud, while it itself said nothing — so the operator sees
a confident, ordinary-looking result and has no signal that the protection or
the ranking never actually ran.

W12b — `UserFilteredAgentDiscovery(registry)` with no `permission_checker`.
The parameter defaults to None, and with it None `_check_user_access` returns
`(True, AccessMetadata(permission_level="execute"))` for every user and every
agent. The class is named `UserFilteredAgentDiscovery`, its method is
`find_agents_for_user`, and that method takes `user_id` + `organization_id` —
so an un-wired instance LOOKS filtered at every call site while filtering
nothing. The class's own docstring example constructs it exactly this way.

`rules/security.md` § "Secure-Default For A New Security Feature" requires
such a default to fail CLOSED, or — where backward-compat forbids
on-by-default — to emit a LOUD one-time WARN naming the OFF protection and its
wiring. Fail-closed is genuinely unavailable here: the parameter has always
defaulted to None, so denying by default would break every existing caller.
The WARN is the required remedy, not a softer stand-in for one.

SCOPE — what this suite does NOT assert. The OTHER fail-open in the same
function (the `except Exception` path, which grants access when the checker
itself errors) is deliberately UNCHANGED and still fail-open. It is already
loud (ERROR) and carries an in-code note deferring it to its own
security-reviewed change, because flipping it would mean a transient checker
outage denies every user. Nothing here should be read as having closed it.

W13 — `OrchestrationRuntime._route_task` under SEMANTIC strategy.
`best_agent` is initialised to `active_agents[0]` as a fallback. When no
candidate carries an `a2a_card`, or every card's `capabilities` list is empty,
the `for cap in capabilities` loop never executes, the judge is never
consulted, and that initialiser is returned as if it were a ranking result.

This is NOT the #1981 degradation case and must not be conflated with it:
#1981 covers capabilities that WERE scored and came back degraded, and that
path is loud (raises when everything degraded, WARNs when only some did). The
case here is that there was nothing to rank on at all — an equally arbitrary
choice, previously made in complete silence.

It stays a WARN rather than a raise: raising would break a documented
`-> str | None` surface, and unlike a transient judge failure this is a
registration-shape issue the operator fixes by populating the cards.
"""

from __future__ import annotations

import logging

import pytest

from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery
from kaizen_agents.patterns.registry import AgentRegistry


class TestPermissionFilteringDisabledIsLoud:
    """W12b — the un-wired security default must announce itself."""

    def test_warns_when_permission_checker_is_absent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            UserFilteredAgentDiscovery(AgentRegistry())

        hits = [
            r
            for r in caplog.records
            if r.message == "discovery.permission_filtering_disabled"
        ]
        assert hits, (
            "Constructing UserFilteredAgentDiscovery with no permission_checker "
            "emitted no WARNING. The instance grants every user 'execute' on "
            "every agent while presenting a filtered-looking API — that default "
            "must be loud (security.md § Secure-Default)."
        )
        assert len(hits) == 1, (
            f"Expected exactly one WARNING per un-wired instance, got "
            f"{len(hits)}. A repeated warning on a discovery path gets filtered "
            f"out, which is how a loud signal becomes a silent one."
        )

        record = hits[0]
        assert record.levelno == logging.WARNING

        # The rule requires the warning to name BOTH the protection that is off
        # AND how to wire it. A bare "filtering disabled" line tells an operator
        # nothing actionable.
        assert (
            "protection_off" in record.__dict__
        ), "WARNING does not name the protection that is off."
        assert (
            "wiring" in record.__dict__
        ), "WARNING does not name the wiring that would enable it."
        assert "permission_checker" in record.__dict__["wiring"], (
            f"The wiring hint does not name the parameter to pass: "
            f"{record.__dict__['wiring']!r}"
        )

    def test_silent_when_permission_checker_is_supplied(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No-false-positive half: a correctly wired instance must NOT warn.

        Without this, the assertion above would still pass if the warning were
        emitted unconditionally — which would train operators to ignore it.
        """

        class _StubChecker:
            async def verify(self, **_kwargs: object) -> object:  # pragma: no cover
                raise AssertionError("not called during construction")

        with caplog.at_level(logging.WARNING):
            UserFilteredAgentDiscovery(
                AgentRegistry(), permission_checker=_StubChecker()
            )

        hits = [
            r
            for r in caplog.records
            if r.message == "discovery.permission_filtering_disabled"
        ]
        assert not hits, (
            "A correctly wired instance emitted the disabled-filtering WARNING. "
            "An always-on warning is noise and gets filtered out."
        )

    def test_unwired_instance_still_grants_access(self) -> None:
        """Pin the BEHAVIOUR the warning describes, not just the warning.

        If a later change quietly flips the un-wired default to deny, this test
        fails and forces that to be a deliberate, reviewed decision rather than
        a side effect — which is exactly the posture question the WARN defers.
        """
        import asyncio

        from kaizen_agents.patterns.runtime import AgentMetadata

        discovery = UserFilteredAgentDiscovery(AgentRegistry())
        granted, meta = asyncio.run(
            discovery._check_user_access(
                "user-1",
                "org-1",
                AgentMetadata.__new__(AgentMetadata),
            )
        )
        assert granted is True, (
            "The un-wired default no longer grants access. That may well be the "
            "RIGHT change — but it is a public-API security-posture change and "
            "must be made deliberately with security review, not incidentally."
        )
        assert meta.permission_level == "execute"


class TestSemanticRoutingWithoutCapabilityDataIsLoud:
    """W13 — positional fallback under SEMANTIC must announce itself."""

    @staticmethod
    def _runtime_with_uncapable_agents(monkeypatch: pytest.MonkeyPatch):
        """Two ACTIVE agents, neither carrying an a2a_card.

        This is the registration shape that reaches the fallback: the
        capability loop never runs, so nothing is scored and nothing degrades.
        """
        from kaizen_agents.patterns.runtime import (
            AgentStatus,
            OrchestrationRuntime,
            RoutingStrategy,
        )

        runtime = OrchestrationRuntime.__new__(OrchestrationRuntime)
        runtime._round_robin_index = 0

        class _Meta:
            def __init__(self) -> None:
                self.status = AgentStatus.ACTIVE
                self.a2a_card = None
                self.active_tasks = 0

        runtime.agents = {"a1": _Meta(), "a2": _Meta()}

        class _Cfg:
            default_routing_strategy = RoutingStrategy.SEMANTIC

        runtime.config = _Cfg()
        monkeypatch.setattr(
            type(runtime),
            "_resolve_reasoning_config",
            lambda self, tuples: None,
            raising=False,
        )
        return runtime

    def test_warns_and_still_returns_an_agent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import asyncio

        runtime = self._runtime_with_uncapable_agents(monkeypatch)

        with caplog.at_level(logging.WARNING):
            selected = asyncio.run(runtime._route_task("do the thing", ["a1", "a2"]))

        assert selected == "a1", (
            "Contract unchanged: the helper still returns the positional "
            "fallback rather than raising. Only the silence was the defect."
        )

        hits = [
            r for r in caplog.records if r.message == "route_task.no_capability_data"
        ]
        assert hits, (
            "SEMANTIC routing fell back to positional first-agent selection "
            "with no WARNING. The caller asked for semantic ranking and got an "
            "arbitrary pick with no signal (zero-tolerance Rule 3)."
        )
        assert (
            "remedy" in hits[0].__dict__
        ), "WARNING does not tell the operator how to fix the registration."

    def test_not_conflated_with_the_1981_degraded_signal(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The two cases must stay distinguishable in the logs.

        `route_task.degraded` means the judge was consulted and failed;
        `route_task.no_capability_data` means it was never consulted. Emitting
        the degraded signal here would misdirect triage toward the LLM provider
        when the actual fault is agent registration.
        """
        import asyncio

        runtime = self._runtime_with_uncapable_agents(monkeypatch)

        with caplog.at_level(logging.WARNING):
            asyncio.run(runtime._route_task("do the thing", ["a1", "a2"]))

        assert not [r for r in caplog.records if r.message == "route_task.degraded"], (
            "Emitted the #1981 degraded signal when nothing degraded — nothing "
            "was ever scored. This sends triage to the wrong subsystem."
        )
