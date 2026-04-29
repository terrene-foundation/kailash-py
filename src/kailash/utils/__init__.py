"""Utilities for the Kailash SDK.

This package contains implementation utilities. Most are internal; a small set
is intentionally public because third-party integrations need them to honor
framework-version-stable patterns (see ``framework-first.md`` § "Drive The
Data, Not The Dispatch"):

- :func:`drive_router_lifespan_startup` / :func:`drive_router_lifespan_shutdown`
  — iterate ``FastAPI.router.on_startup`` / ``on_shutdown`` from a custom
  ``lifespan=`` context manager so user-registered ``@app.on_event("startup")``
  handlers fire (#500). Used by every Kailash FastAPI surface that sets
  ``lifespan=`` (``WorkflowServer``, ``KailashAPIGateway``, ``WorkflowAPIGateway``,
  ``WorkflowAPI``) and available to user code that does the same.

Other modules (annotations, data_paths, etc.) remain internal — direct imports
from those are discouraged.
"""

from kailash.utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)

__all__ = [
    "drive_router_lifespan_shutdown",
    "drive_router_lifespan_startup",
]
