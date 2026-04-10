# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.exceptions`` -> ``kailash.trust.exceptions``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.exceptions import TrustError, AuthorityNotFoundError
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.exceptions is deprecated. "
    "Use 'from kailash.trust.exceptions import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.exceptions import (  # noqa: E402
    AgentAlreadyEstablishedError,
    AuthorityInactiveError,
    AuthorityNotFoundError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationCycleError,
    DelegationError,
    DelegationExpiredError,
    HookError,
    HookTimeoutError,
    InvalidSignatureError,
    InvalidTrustChainError,
    PathTraversalError,
    PostureStoreError,
    TrustChainNotFoundError,
    TrustError,
    TrustStoreError,
    VerificationFailedError,
)

__all__ = [
    "AgentAlreadyEstablishedError",
    "AuthorityInactiveError",
    "AuthorityNotFoundError",
    "CapabilityNotFoundError",
    "ConstraintViolationError",
    "DelegationCycleError",
    "DelegationError",
    "DelegationExpiredError",
    "HookError",
    "HookTimeoutError",
    "InvalidSignatureError",
    "InvalidTrustChainError",
    "PathTraversalError",
    "PostureStoreError",
    "TrustChainNotFoundError",
    "TrustError",
    "TrustStoreError",
    "VerificationFailedError",
]
