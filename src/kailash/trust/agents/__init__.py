# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Trust Agents — trust-enhanced agent wrappers.

Provides agent types that integrate EATP trust verification transparently:

- :class:`TrustedAgent` — Wraps any agent with automatic trust verification
  and audit recording (the "trust sandwich" pattern).
- :class:`PseudoAgent` — Human facade for the EATP system; the root of all
  trust chains.

These types depend on ``pynacl`` for cryptographic operations. If ``pynacl``
is not installed, imports are deferred and raise ``ImportError`` with
installation instructions on access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Lazy imports — these modules depend on pynacl transitively through
# eatp.operations / eatp.chain crypto functions.

_AGENT_NAMES = frozenset(
    {
        "TrustedAgent",
        "TrustedAgentConfig",
        "TrustedSupervisorAgent",
        "PseudoAgent",
        "PseudoAgentConfig",
        "PseudoAgentFactory",
        "AuthProvider",
    }
)

_INSTALL_HINT = "Trust agent types require PyNaCl. " "Install with: pip install kailash"


def __getattr__(name: str):
    """Lazy-load agent classes that may depend on pynacl."""
    if name in ("TrustedAgent", "TrustedAgentConfig", "TrustedSupervisorAgent"):
        try:
            from kailash.trust.agents.trusted_agent import (
                TrustedAgent,
                TrustedAgentConfig,
                TrustedSupervisorAgent,
            )
        except ImportError:
            raise ImportError(_INSTALL_HINT) from None

        import sys

        module = sys.modules[__name__]
        setattr(module, "TrustedAgent", TrustedAgent)
        setattr(module, "TrustedAgentConfig", TrustedAgentConfig)
        setattr(module, "TrustedSupervisorAgent", TrustedSupervisorAgent)
        return {
            "TrustedAgent": TrustedAgent,
            "TrustedAgentConfig": TrustedAgentConfig,
            "TrustedSupervisorAgent": TrustedSupervisorAgent,
        }[name]

    if name in (
        "PseudoAgent",
        "PseudoAgentConfig",
        "PseudoAgentFactory",
        "AuthProvider",
    ):
        try:
            from kailash.trust.agents.pseudo_agent import (
                AuthProvider,
                PseudoAgent,
                PseudoAgentConfig,
                PseudoAgentFactory,
            )
        except ImportError:
            raise ImportError(_INSTALL_HINT) from None

        import sys

        module = sys.modules[__name__]
        setattr(module, "PseudoAgent", PseudoAgent)
        setattr(module, "PseudoAgentConfig", PseudoAgentConfig)
        setattr(module, "PseudoAgentFactory", PseudoAgentFactory)
        setattr(module, "AuthProvider", AuthProvider)
        return {
            "PseudoAgent": PseudoAgent,
            "PseudoAgentConfig": PseudoAgentConfig,
            "PseudoAgentFactory": PseudoAgentFactory,
            "AuthProvider": AuthProvider,
        }[name]

    raise AttributeError(f"module 'kailash.trust.agents' has no attribute {name!r}")


__all__ = [
    "TrustedAgent",
    "TrustedAgentConfig",
    "TrustedSupervisorAgent",
    "PseudoAgent",
    "PseudoAgentConfig",
    "PseudoAgentFactory",
    "AuthProvider",
]
