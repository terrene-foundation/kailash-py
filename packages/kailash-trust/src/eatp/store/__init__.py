# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.store`` -> ``kailash.trust.chain_store``.

Note the path shift: the legacy ``eatp.store`` maps to
``kailash.trust.chain_store`` (renamed during the merge into kailash-py).

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.chain_store import TrustStore
    from kailash.trust.chain_store.memory import InMemoryTrustStore
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.store is deprecated. "
    "Use 'from kailash.trust.chain_store import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.chain_store import TrustStore  # noqa: E402

__all__ = [
    "TrustStore",
]
