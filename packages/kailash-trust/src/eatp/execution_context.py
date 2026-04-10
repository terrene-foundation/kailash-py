# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.execution_context`` -> ``kailash.trust.execution_context``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.execution_context import ExecutionContext, HumanOrigin
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.execution_context is deprecated. "
    "Use 'from kailash.trust.execution_context import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.execution_context import (  # noqa: E402
    ExecutionContext,
    HumanOrigin,
    execution_context,
    get_current_context,
    get_delegation_chain,
    get_human_origin,
    get_trace_id,
    require_current_context,
    set_current_context,
)

__all__ = [
    "ExecutionContext",
    "HumanOrigin",
    "execution_context",
    "get_current_context",
    "get_delegation_chain",
    "get_human_origin",
    "get_trace_id",
    "require_current_context",
    "set_current_context",
]
