# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry instrumentation for Kailash runtime components.

Sub-modules provide progressive instrumentation controlled by
:class:`~kailash.runtime.tracing.TracingLevel`:

- :mod:`.nodes`     -- Node-level execution spans (DETAILED+).
- :mod:`.dataflow`  -- DataFlow query tracing (FULL).
- :mod:`.database`  -- ConnectionManager auto-instrumentation (FULL).

All instrumentation degrades gracefully when ``opentelemetry`` is not installed.
"""

from __future__ import annotations

__all__ = [
    "NodeInstrumentor",
    "DataFlowInstrumentor",
    "DatabaseInstrumentor",
]


def __getattr__(name: str):  # noqa: ANN001
    """Lazy imports to avoid loading OTel at module scope."""
    if name == "NodeInstrumentor":
        from kailash.runtime.instrumentation.nodes import NodeInstrumentor

        return NodeInstrumentor
    if name == "DataFlowInstrumentor":
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        return DataFlowInstrumentor
    if name == "DatabaseInstrumentor":
        from kailash.runtime.instrumentation.database import DatabaseInstrumentor

        return DatabaseInstrumentor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
