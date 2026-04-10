# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.pseudo_agent`` -> ``kailash.trust.agents.pseudo_agent``.

Note the path shift: the legacy ``eatp.pseudo_agent`` maps to
``kailash.trust.agents.pseudo_agent`` (the ``agents`` package was
added during the merge into kailash-py).

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.agents.pseudo_agent import PseudoAgent, PseudoAgentConfig
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.pseudo_agent is deprecated. "
    "Use 'from kailash.trust.agents.pseudo_agent import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.agents.pseudo_agent import (  # noqa: E402
    AuthProvider,
    PseudoAgent,
    PseudoAgentConfig,
    PseudoAgentFactory,
)

__all__ = [
    "AuthProvider",
    "PseudoAgent",
    "PseudoAgentConfig",
    "PseudoAgentFactory",
]
