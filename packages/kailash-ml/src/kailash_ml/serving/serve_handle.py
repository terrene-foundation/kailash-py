# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Compatibility re-export of :class:`ServeHandle` and :data:`ServeStatus`.

The canonical definitions now live in :mod:`kailash_ml.serving._types` —
that module has no dependency on :mod:`kailash_ml.serving.server`, which
breaks the static import cycle that previously forced ``server.py`` and
``serve_handle.py`` to reference each other.

Existing downstream callers doing ``from kailash_ml.serving.serve_handle
import ServeHandle`` continue to work via this re-export.
"""
from __future__ import annotations

from kailash_ml.serving._types import InferenceServerProtocol, ServeHandle, ServeStatus

__all__ = ["ServeHandle", "ServeStatus", "InferenceServerProtocol"]
