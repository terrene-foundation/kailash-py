# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Self-contained conftest for composition tests.

Pre-loads a stub 'kaizen' package into sys.modules so that
`from kaizen.composition.X import Y` does NOT trigger the real
kaizen/__init__.py (which has a broken import chain to kailash.nodes.base).

This conftest runs BEFORE test modules are collected, so the stub
is in place when test-level `from kaizen.composition...` executes.
"""

import os
import sys
import types

# Only apply the stub if the real kaizen package would fail
# (i.e., kailash.nodes.base.Node is not importable)
_need_stub = False
try:
    from kailash.nodes.base import Node  # noqa: F401
except (ImportError, AttributeError):
    _need_stub = True

if _need_stub and "kaizen" not in sys.modules:
    # Create a minimal namespace package for 'kaizen' that does NOT
    # execute the real __init__.py (which triggers the broken import chain).
    _src_dir = os.path.join(
        os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "src"
    )
    _src_dir = os.path.normpath(_src_dir)
    _kaizen_dir = os.path.join(_src_dir, "kaizen")

    stub = types.ModuleType("kaizen")
    stub.__path__ = [_kaizen_dir]
    stub.__package__ = "kaizen"
    stub.__file__ = os.path.join(_kaizen_dir, "__init__.py")
    sys.modules["kaizen"] = stub

    # Ensure src/ is on the path so subpackage discovery works
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
