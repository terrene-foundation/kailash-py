# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — public-surface presence for ``kaizen.ml``.

Per ``specs/kaizen-ml-integration.md §1.1`` the module MUST export every
symbol enumerated below. This guards against silent surface shrinkage
from a refactor that moves a symbol without updating ``__all__``.

Also per ``rules/orphan-detection.md §6``: every symbol in the module's
``__all__`` MUST be eagerly importable at module scope.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_kaizen_ml_public_surface_matches_spec() -> None:
    """Every symbol from spec §1.1 MUST be re-exported from ``kaizen.ml``."""
    import kaizen.ml as km_bridge

    expected = {
        # Shared wire format
        "CostDelta",
        "CostDeltaError",
        # SQLite sink
        "SQLiteSink",
        "SQLiteSinkError",
        "VALID_AGENT_RUN_STATUSES",
        "default_ml_db_path",
        # Tracker bridge (auto-emission)
        "resolve_active_tracker",
        "emit_metric",
        "emit_param",
        "emit_artifact",
        "is_emit_rank_0",
        # Tool discovery (§2.4)
        "discover_ml_tools",
        "engine_info",
        "MLEngineDescriptor",
        "MLRegistryUnavailableError",
        "MLToolDiscoveryError",
        # ML-aware agent — §2.4.6 production call site
        "MLAwareAgent",
    }
    actual = set(km_bridge.__all__)
    missing = expected - actual
    assert not missing, f"kaizen.ml missing expected exports: {missing}"

    # Every symbol MUST be eagerly importable — §6 orphan-detection rule.
    for name in sorted(expected):
        assert (
            getattr(km_bridge, name) is not None
        ), f"kaizen.ml.{name} is in __all__ but resolves to None"


@pytest.mark.unit
def test_cost_delta_from_usd_rounds_to_microdollars() -> None:
    """``from_usd(0.00013)`` → 130 microdollars (sub-cent precision preserved)."""
    from datetime import datetime, timezone

    from kaizen.ml import CostDelta

    delta = CostDelta.from_usd(
        0.00013,
        provider="openai",
        model="text-embedding-ada-002",
        prompt_tokens=100,
        completion_tokens=0,
        at=datetime.now(timezone.utc),
    )
    assert delta.microdollars == 130


@pytest.mark.unit
def test_cost_delta_nan_usd_raises() -> None:
    """Spec §4.2 + ``rules/security.md`` — NaN USD is rejected loudly."""
    from datetime import datetime, timezone

    from kaizen.ml import CostDelta, CostDeltaError

    with pytest.raises(CostDeltaError):
        CostDelta.from_usd(
            float("nan"),
            provider="x",
            model="y",
            prompt_tokens=0,
            completion_tokens=0,
            at=datetime.now(timezone.utc),
        )


@pytest.mark.unit
def test_cost_delta_negative_usd_raises() -> None:
    """Spec §4.2 — negative USD is rejected (refunds tracked separately)."""
    from datetime import datetime, timezone

    from kaizen.ml import CostDelta, CostDeltaError

    with pytest.raises(CostDeltaError):
        CostDelta.from_usd(
            -1.0,
            provider="x",
            model="y",
            prompt_tokens=0,
            completion_tokens=0,
            at=datetime.now(timezone.utc),
        )


@pytest.mark.unit
def test_cost_delta_roundtrip_to_dict_from_dict() -> None:
    """Spec §4.2 — cross-SDK round-trip parity on the canonical dict shape."""
    from datetime import datetime, timezone

    from kaizen.ml import CostDelta

    original = CostDelta(
        microdollars=1500,
        provider="anthropic",
        model="claude-3-5-sonnet",
        prompt_tokens=10,
        completion_tokens=20,
        at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
        tenant_id="acme",
        actor_id="agent-42",
    )
    restored = CostDelta.from_dict(original.to_dict())
    assert restored == original


@pytest.mark.unit
def test_sqlitesink_rejects_invalid_finalize_status(tmp_path) -> None:
    """Spec §5.3 — only RUNNING / FINISHED / FAILED / KILLED are accepted.

    Legacy values SUCCESS / COMPLETED are BLOCKED.
    """
    from kaizen.ml import SQLiteSink, SQLiteSinkError

    sink = SQLiteSink(db_path=tmp_path / "ml.db")
    try:
        with pytest.raises(SQLiteSinkError):
            sink.finalize_trace("trace-does-not-matter", status="COMPLETED")
        with pytest.raises(SQLiteSinkError):
            sink.finalize_trace("trace-does-not-matter", status="SUCCESS")
    finally:
        sink.close()


@pytest.mark.unit
def test_ml_registry_unavailable_raises_typed_error() -> None:
    """Hardcoded engine imports are BLOCKED — discovery must fail loudly.

    Even when ``km.engine_info`` isn't yet shipped, the helper MUST raise
    :class:`MLRegistryUnavailableError` with an actionable message instead
    of silently falling back to direct imports.
    """
    import importlib

    import kaizen.ml._tool_discovery as disc

    try:
        import kailash_ml as km  # noqa: F401

        has_km = True
    except ImportError:
        has_km = False

    if not has_km or not all(
        hasattr(__import__("kailash_ml"), n) for n in ("engine_info", "list_engines")
    ):
        from kaizen.ml import MLRegistryUnavailableError, discover_ml_tools

        with pytest.raises(MLRegistryUnavailableError):
            discover_ml_tools()
    else:
        # Registry is live — the helper should return a tuple, not raise.
        descriptors = disc.discover_ml_tools()
        assert isinstance(descriptors, tuple)
