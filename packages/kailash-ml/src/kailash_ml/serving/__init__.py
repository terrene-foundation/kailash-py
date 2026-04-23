# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml serving package — canonical inference runtime (W25).

Per ``specs/ml-serving.md`` this package hosts :class:`InferenceServer`
(the manager-shape runtime) + :class:`ServeHandle` (the process-local
handle returned by ``km.serve(...)``) + the REST / MCP / gRPC channel
adapters.

Public surface is exposed submodule-level via ``kailash_ml.serving.*``
only; the top-level ``kailash_ml.__all__`` is owned by the orchestrator
shard (W33). Callers do:

.. code-block:: python

    from kailash_ml.serving import InferenceServer, ServeHandle
    from kailash_ml.serving import InferenceServerConfig

    server = await InferenceServer.from_registry(
        "fraud@production", registry=my_registry, tenant_id="acme",
    )
    handle = await server.start()
    print(handle.urls["rest"])  # http://127.0.0.1:0/predict/fraud
    assert handle.urls["rest"].endswith("/predict/fraud")
    await handle.stop()
"""
from __future__ import annotations

from kailash_ml.serving.serve_handle import ServeHandle, ServeStatus
from kailash_ml.serving.server import (
    ALLOWED_CHANNELS,
    ALLOWED_RUNTIMES,
    DEFAULT_CHANNELS,
    InferenceServer,
    InferenceServerConfig,
    parse_model_uri,
)

__all__ = [
    # Server lifecycle
    "InferenceServer",
    "InferenceServerConfig",
    "ServeHandle",
    "ServeStatus",
    # Constants
    "ALLOWED_CHANNELS",
    "ALLOWED_RUNTIMES",
    "DEFAULT_CHANNELS",
    # URI parsing helper
    "parse_model_uri",
]
