# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.enforce`` -> ``kailash.trust.enforce``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.enforce.strict import StrictEnforcer, Verdict
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.enforce is deprecated. "
    "Use 'from kailash.trust.enforce import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
