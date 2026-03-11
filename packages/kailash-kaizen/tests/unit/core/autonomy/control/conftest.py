"""
Pytest configuration for autonomy control tests.

Configures anyio to use only asyncio backend due to trio CancelScope
compatibility issues in trio v0.27+.
"""

import pytest


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    """Configure anyio backend for async tests.

    Uses only asyncio due to trio CancelScope.cancel() API change in v0.27+
    where cancel() takes 1 positional argument but older code passes 2.
    """
    return request.param
