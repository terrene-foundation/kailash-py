# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.authority`` -> ``kailash.trust.authority``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.authority import OrganizationalAuthority
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.authority is deprecated. "
    "Use 'from kailash.trust.authority import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.authority import (  # noqa: E402
    AuthorityPermission,
    AuthorityRegistryProtocol,
    OrganizationalAuthority,
)

__all__ = [
    "AuthorityPermission",
    "AuthorityRegistryProtocol",
    "OrganizationalAuthority",
]
