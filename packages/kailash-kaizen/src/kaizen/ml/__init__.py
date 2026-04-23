# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``kaizen.ml`` — ML-integration surface for Kaizen agents.

Public surface per ``specs/kaizen-ml-integration.md`` §1.1:

    from kaizen.ml import (
        # Auto-emission bridge used by every diagnostic adapter
        resolve_active_tracker,
        emit_metric,
        emit_param,
        emit_artifact,
        is_emit_rank_0,
        # Shared cost-delta wire format (cross-SDK — microdollars)
        CostDelta,
        CostDeltaError,
        # Durable TraceExporter sink
        SQLiteSink,
        SQLiteSinkError,
        default_ml_db_path,
        VALID_AGENT_RUN_STATUSES,
        # Discovery-driven agent tool-set construction
        discover_ml_tools,
        engine_info,
        MLEngineDescriptor,
        MLRegistryUnavailableError,
        MLToolDiscoveryError,
    )

This module is the single facade for every Kaizen↔kailash-ml
integration point. ``specs/kaizen-ml-integration.md §2.4.5`` forbids
hardcoded engine imports in agent tool-set construction — every path
MUST route through the helpers here.

Per ``rules/orphan-detection.md`` §6: every public symbol re-exported
through ``kaizen.ml`` is eagerly imported at module scope AND listed
in ``__all__``. No lazy ``__getattr__`` paths.
"""

from __future__ import annotations

from kaizen.ml._cost_delta import CostDelta, CostDeltaError
from kaizen.ml._sqlite_sink import (
    VALID_AGENT_RUN_STATUSES,
    SQLiteSink,
    SQLiteSinkError,
    default_ml_db_path,
)
from kaizen.ml._tool_discovery import (
    MLEngineDescriptor,
    MLRegistryUnavailableError,
    MLToolDiscoveryError,
    discover_ml_tools,
    engine_info,
)
from kaizen.ml._tracker_bridge import (
    emit_artifact,
    emit_metric,
    emit_param,
    is_emit_rank_0,
    resolve_active_tracker,
)

__all__ = [
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
]
