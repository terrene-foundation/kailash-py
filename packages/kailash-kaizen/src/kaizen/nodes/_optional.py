"""Optional-dependency helpers for kaizen node modules.

numpy (and the other RAG numerics) ship in the ``kailash-kaizen[rag]`` extra,
NOT the base dependency set. Modules on the base import surface (everything
eagerly imported by ``kaizen.nodes.ai.__init__`` and below) MUST NOT import
numpy at module scope — route runtime usage through :func:`require_numpy` so
absence surfaces as a typed, actionable error at call time instead of an
ImportError at base ``import kaizen`` time (F31-FU5).
"""

from __future__ import annotations

from types import ModuleType


def require_numpy(feature: str = "this feature") -> ModuleType:
    """Return the numpy module, or raise a typed install-guidance error.

    Args:
        feature: Human-readable name of the capability that needs numpy,
            used in the error message.

    Raises:
        ImportError: When numpy is not installed, with the ``[rag]`` extra
            install command.
    """
    try:
        import numpy
    except ImportError as exc:
        raise ImportError(
            f"numpy is required for {feature} but is not installed. "
            "Install the RAG extra: pip install kailash-kaizen[rag]"
        ) from exc
    return numpy
