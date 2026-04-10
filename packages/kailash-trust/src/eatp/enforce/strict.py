# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.enforce.strict`` -> ``kailash.trust.enforce.strict``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.enforce.strict import StrictEnforcer, Verdict
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.enforce.strict is deprecated. "
    "Use 'from kailash.trust.enforce.strict import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.enforce.strict import (  # noqa: E402
    EATPBlockedError,
    EATPHeldError,
    EnforcementRecord,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)

__all__ = [
    "EATPBlockedError",
    "EATPHeldError",
    "EnforcementRecord",
    "HeldBehavior",
    "StrictEnforcer",
    "Verdict",
]
