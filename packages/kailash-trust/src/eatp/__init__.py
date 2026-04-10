# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy ``eatp`` namespace -- backward-compatibility shim.

This package re-exports symbols from ``kailash.trust.*`` under the legacy
``eatp.*`` namespace so that downstream consumers (e.g., aegis) that relied
on the yanked ``eatp`` PyPI package can continue to operate while they
migrate to the canonical ``kailash.trust`` imports.

Every submodule emits a :class:`DeprecationWarning` on first import.

Migration guide
---------------
Replace::

    from eatp.execution_context import ExecutionContext

with::

    from kailash.trust.execution_context import ExecutionContext

Install ``kailash`` (the main package) to get all trust symbols.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "The 'eatp' package is deprecated. "
    "Migrate to 'kailash.trust' — e.g. 'from kailash.trust import ...'.",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
