# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.store.memory`` -> ``kailash.trust.chain_store.memory``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.chain_store.memory import InMemoryTrustStore
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.store.memory is deprecated. "
    "Use 'from kailash.trust.chain_store.memory import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.chain_store.memory import InMemoryTrustStore  # noqa: E402

__all__ = [
    "InMemoryTrustStore",
]
