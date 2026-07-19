# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Canonical-first Azure environment-variable resolution.

``resolve_azure_env`` is the single shared helper for reading Azure
environment variables with canonical-first, legacy-with-deprecation
semantics. It is consumed by the four-axis Azure deployment builder
(``kaizen.llm.deployment_resolver._resolve_azure_deployment``) and by the
config-layer Azure detection helpers (``kaizen.config.providers``).

Relocated here from ``kaizen.nodes.ai.azure_detection`` in #1820 when the
legacy unified-azure provider stack (``unified_azure_provider`` /
``azure_backends`` / ``azure_capabilities`` / ``azure_detection``) was
retired in favour of the four-axis ``LlmClient`` path. The helper itself
carries no legacy behaviour — it is pure ``os.getenv`` resolution — so it
survives in the four-axis layer that now owns Azure resolution.

Pure stdlib (``os`` / ``warnings`` / ``logging``); imports no ``kaizen``
symbols, so it is safe to import from any layer without cycles.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
import warnings

logger = logging.getLogger(__name__)


def resolve_azure_env(canonical: str, *legacy: str) -> Optional[str]:
    """Resolve an Azure environment variable with canonical-first semantics.

    Checks the canonical name first. If not set, checks each legacy name in
    order and emits a :class:`DeprecationWarning` on the first match.

    The warning uses ``stacklevel=3`` so it points at the caller's caller
    (typically user code), not internal framework code.

    Args:
        canonical: The preferred environment variable name (e.g. ``AZURE_ENDPOINT``).
        *legacy: Zero or more legacy names to check as fallbacks.

    Returns:
        The resolved value, or ``None`` if no variable is set.
    """
    value = os.getenv(canonical)
    if value:
        return value
    for legacy_name in legacy:
        value = os.getenv(legacy_name)
        if value:
            warnings.warn(
                f"Environment variable {legacy_name} is deprecated. "
                f"Use {canonical} instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            return value
    return None


__all__ = ["resolve_azure_env"]
