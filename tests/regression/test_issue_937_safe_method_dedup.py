# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression — durable gateways MUST NOT deduplicate safe HTTP methods (#937).

The durable request deduplicator cached responses for ALL methods with a 1-hour
TTL, so a second identical GET returned a stale cached body — e.g. a schedule
still showed ``enabled: true`` after a disable. Deduplication is meaningful only
for mutating methods (idempotent retry of POST/PUT/PATCH); GET/HEAD/OPTIONS are
safe reads that MUST reflect current state.

Both durable server classes carry the fix; this pins the invariant behaviorally
(calls ``_should_use_durability`` per method). The end-to-end HTTP coverage lives
in ``packages/kailash-nexus/tests/integration/test_scheduler_admin_panel_wiring.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.servers.durable_workflow_server import DurableWorkflowServer

SAFE = ["GET", "HEAD", "OPTIONS"]
MUTATING = ["POST", "PUT", "PATCH"]


def _request(method: str) -> SimpleNamespace:
    return SimpleNamespace(method=method, headers={}, query_params={})


def _make(cls):
    """Construct without running heavy __init__; set only the gate's inputs."""
    inst = cls.__new__(cls)
    inst.enable_durability = True
    inst.durability_opt_in = False
    return inst


@pytest.mark.regression
@pytest.mark.parametrize("cls", [DurableWorkflowServer, DurableAPIGateway])
class TestSafeMethodDedupSkip:
    @pytest.mark.parametrize("method", SAFE)
    def test_safe_methods_skip_dedup(self, cls, method):
        # Safe reads MUST NOT be deduplicated (no stale cache after a mutation).
        assert _make(cls)._should_deduplicate(_request(method)) is False

    @pytest.mark.parametrize("method", MUTATING)
    def test_mutating_methods_deduplicate(self, cls, method):
        assert _make(cls)._should_deduplicate(_request(method)) is True

    @pytest.mark.parametrize("method", SAFE + MUTATING)
    def test_durability_tracking_still_applies_to_all_methods(self, cls, method):
        # The dedup skip MUST NOT disable durability (audit/checkpoint) for
        # reads — only the dedup cache is skipped (#937).
        assert _make(cls)._should_use_durability(_request(method)) is True
