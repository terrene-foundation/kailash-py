"""
Conftest for native tools tests.

Ensures proper module isolation for BaseTool isinstance checks.
"""

import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def ensure_consistent_basetool():
    """Ensure BaseTool class is consistent across modules.

    This fixture reloads the base module before tests that register tools
    to ensure isinstance checks work correctly. The issue is that when
    running the full test suite, other tests may cause module reloading
    that results in multiple BaseTool classes.
    """
    # Force reimport of base module to ensure consistent BaseTool class
    modules_to_reload = [
        "kaizen.tools.native.base",
        "kaizen.tools.native.file_tools",
        "kaizen.tools.native.bash_tools",
        "kaizen.tools.native.search_tools",
        "kaizen.tools.native.task_tool",
        "kaizen.tools.native.skill_tool",
        "kaizen.tools.native.registry",
    ]

    # Remove modules from cache to force fresh import
    for mod_name in modules_to_reload:
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    # Pre-import base to ensure it's loaded first
    from kaizen.tools.native import base

    yield

    # Cleanup: remove modules again to avoid affecting other tests
    for mod_name in modules_to_reload:
        if mod_name in sys.modules:
            del sys.modules[mod_name]
