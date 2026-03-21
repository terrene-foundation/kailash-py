# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "security: marks tests as security regression tests for hardened patterns",
    )
