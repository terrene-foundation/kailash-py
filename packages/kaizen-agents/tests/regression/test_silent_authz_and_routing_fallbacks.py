# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: the un-wired authz default made loud (forest W12b).

The defect shape: a code path whose SIBLING path is loud, while it itself said
nothing — so the operator sees a confident, ordinary-looking result and has no
signal that the protection never actually ran.

The W13 routing half of this suite MOVED to
`test_routing_single_implementation.py`. It was retargeted when the duplicate
`_route_task` implementation was deleted: the warning now belongs to
`_route_semantic`, the single surviving implementation, and the fixture there
builds a REAL `OrchestrationRuntimeConfig` instead of the hand-rolled stub used
here — which silently lacked `enable_semantic_routing` and would have kept
asserting against a config shape production does not use.

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
