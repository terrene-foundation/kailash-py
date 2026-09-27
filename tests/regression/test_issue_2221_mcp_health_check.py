# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: MCPChannel.health_check uses a FALSIFIABLE workflow-registry check (#2221).

The check was ``"workflows_available": len(self._workflow_registry) >= 0`` --
true for EVERY sized object, so it reported healthy for an empty, full, and
corrupt-but-nonempty registry alike, and raised ``TypeError`` on a ``None``
registry. An assertion that cannot fail is not a weaker check, it is not a
check. It is now ``self._workflow_registry is not None`` -- falsifiable (a
``None`` registry -> False -> unhealthy), matching its sibling ``is not None``
checks.

The discriminating input is a ``None`` registry:
  - pre-fix: ``len(None) >= 0`` raises ``TypeError`` (the check cannot report
    False for the state it must reject);
  - post-fix: ``is not None`` returns ``False`` and drops overall health.
"""

from __future__ import annotations

import pytest

from kailash.channels.base import ChannelConfig, ChannelType
from kailash.channels.mcp_channel import MCPChannel


def _channel() -> MCPChannel:
    # Pass a truthy sentinel mcp_server so no real server is created; runtime
    # defaults to a fresh LocalRuntime. health_check needs neither started.
    return MCPChannel(
        ChannelConfig(name="hc-2221", channel_type=ChannelType.MCP),
        mcp_server=object(),
    )


@pytest.mark.asyncio
async def test_workflows_available_true_for_initialized_registry() -> None:
    """Pole 1: an initialized (dict) registry reports workflows_available True."""
    channel = _channel()
    try:
        health = await channel.health_check()
        assert health["checks"]["workflows_available"] is True
    finally:
        channel.close()


@pytest.mark.asyncio
async def test_workflows_available_false_for_missing_registry() -> None:
    """Pole 2: a None registry (the state it must reject) reports False and unhealthy.

    Against the unfixed ``len(...) >= 0`` predicate this raises ``TypeError``;
    the falsifiable ``is not None`` predicate returns False instead.
    """
    channel = _channel()
    try:
        channel._workflow_registry = None  # simulate an uninitialized/corrupt registry
        health = await channel.health_check()
        assert health["checks"]["workflows_available"] is False
        assert health["healthy"] is False
    finally:
        channel.close()
