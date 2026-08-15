# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1973 — the reasoning bridges must propagate judge config on the SYNC branch.

``kaizen.nodes.ai.a2a.Capability.matches_requirement`` was flipped from ``async
def`` back to ``def`` (#1973). Both bridges here dispatch on
``inspect.iscoroutinefunction(matcher)`` and previously passed ``config`` /
``correlation_id`` on the async branch ONLY. With the matcher now sync, the sync
branch MUST carry the same kwargs — otherwise the bridge's legacy
``except TypeError`` fallback re-calls ``matcher(task)`` positionally, ``config``
arrives as ``None``, and the judge silently falls back to ``.env`` defaults
instead of the host agent's model. A dropped ``correlation_id`` additionally
breaks multi-capability loop tracing (``observability.md`` § correlation ID on
every log line).

WHY THIS LIVES IN ``kaizen-agents`` AND NOT ``kailash-kaizen``.
It was originally written in
``packages/kailash-kaizen/tests/regression/test_issue_1973_a2a_capability_match.py``
as that file's deliverable (d), guarding the sync flip's blast radius. But the
code under test — ``kaizen_agents.patterns._reasoning_bridge`` and
``kaizen_agents.patterns.runtime`` — ships in THIS package, and
``kaizen-agents`` depends on ``kailash-kaizen``, not the reverse. A test in the
depended-UPON package that imports its own dependent inverts that direction, and
``packages/kailash-kaizen/pytest.ini`` exposes only its own ``src``, so
``kaizen_agents`` there resolves to whatever wheel happens to be INSTALLED.
Against a stale wheel the test reds while the repo source is already correct —
it reported a live config-propagation bug for source that propagates config
fine, which is how correct code gets "fixed" to satisfy an old wheel. The
reverse is quieter: a wheel NEWER than the branch greens a regression the branch
actually has.

Here, ``packages/kaizen-agents/conftest.py`` puts this package's ``src`` at the
front of ``sys.path``, so these assertions always describe the branch under
test. Its sibling ``test_issue_1981_degraded_judgment.py`` covers the same
module for the same reason.

Tier-1 offline: the judge is stubbed at ``kaizen.llm.reasoning``, so no network
and no credentials. That is a STRUCTURAL assertion (kwarg plumbing across a
sync/async dispatch), not a semantic one — no probe is required per
``probe-driven-verification.md`` Rule 3.
"""

import asyncio

import pytest

from kaizen.nodes.ai.a2a import Capability, CapabilityLevel

pytestmark = pytest.mark.regression


def _cap(name: str) -> Capability:
    return Capability(
        name=name,
        domain="engineering",
        level=CapabilityLevel.EXPERT,
        description=f"can do {name}",
        keywords=[name],
    )


class TestReasoningBridgesPreserveConfigPropagation:
    """The sync flip must not silently drop judge config."""

    def test_score_capability_sync_propagates_config_and_correlation_id(
        self, monkeypatch
    ):
        import kaizen.llm.reasoning as reasoning
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        seen = {}

        def judge(**kw):
            seen.update(kw)
            return 1.0

        monkeypatch.setattr(reasoning, "llm_capability_match", judge)

        from kaizen.core.base_agent import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="mock-model")
        score = score_capability_sync(
            _cap("python"),
            "write python",
            reasoning_config=config,
            correlation_id="cid-1973",
        )

        assert score == 1.0
        assert seen.get("config") is config, (
            "the reasoning config was dropped on the sync matcher branch; the "
            "judge model silently falls back to .env defaults."
        )
        assert seen.get("correlation_id") == "cid-1973"

    def test_runtime_score_capability_propagates_config_and_correlation_id(
        self, monkeypatch
    ):
        import kaizen.llm.reasoning as reasoning
        from kaizen_agents.patterns.runtime import OrchestrationRuntime

        seen = {}

        def judge(**kw):
            seen.update(kw)
            return 1.0

        monkeypatch.setattr(reasoning, "llm_capability_match", judge)

        from kaizen.core.base_agent import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="mock-model")
        runtime = OrchestrationRuntime()
        score = asyncio.run(
            runtime._score_capability(
                _cap("python"), "write python", config, agent_id="a1"
            )
        )

        assert score == 1.0
        assert seen.get("config") is config
        assert seen.get("correlation_id") == "route_a1"

    def test_legacy_single_arg_sync_mocks_still_score(self):
        # The bridges' TypeError fallback exists for legacy mocks with a
        # single-positional matcher. Passing kwargs on the sync branch must not
        # break them.
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        class LegacyCap:
            def matches_requirement(self, requirement: str) -> float:
                return 0.42

        assert score_capability_sync(LegacyCap(), "anything") == pytest.approx(0.42)
