# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.operations`` -> ``kailash.trust.operations``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.operations import TrustOperations, TrustKeyManager
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.operations is deprecated. "
    "Use 'from kailash.trust.operations import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.operations import (  # noqa: E402
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)

__all__ = [
    "CapabilityRequest",
    "TrustKeyManager",
    "TrustOperations",
]
