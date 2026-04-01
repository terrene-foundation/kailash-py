# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""DataFlow User model fixture for MCP integration tests."""

from dataflow import DataFlow

db = DataFlow("sqlite:///test.db")


@db.model
class User:
    id: int
    name: str
    email: str
    active: bool = True
    created_at: str = ""
    updated_at: str = ""
