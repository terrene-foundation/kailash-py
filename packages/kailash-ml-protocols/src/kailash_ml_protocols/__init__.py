# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml-protocols -- Frozen interface contracts for ML interop.

This package has ZERO pip dependencies (Python 3.10+ stdlib only).
It breaks the circular dependency between kailash-ml and kailash-kaizen.
"""
from __future__ import annotations

from kailash_ml_protocols.protocols import AgentInfusionProtocol, MLToolProtocol
from kailash_ml_protocols.schemas import (
    FeatureField,
    FeatureSchema,
    MetricSpec,
    ModelSignature,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Protocols
    "MLToolProtocol",
    "AgentInfusionProtocol",
    # Schemas
    "FeatureField",
    "FeatureSchema",
    "ModelSignature",
    "MetricSpec",
]
