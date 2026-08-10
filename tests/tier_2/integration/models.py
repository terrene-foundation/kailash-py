# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DataFlow model definitions for tier_2 integration tests.

Defines the User model used by DataFlow auto-generated nodes:
UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
UserListNode, UserBulkCreateNode, UserBulkDeleteNode,
UserBulkUpdateNode, UserBulkUpsertNode.

Importing this module registers all auto-generated nodes with the
Kailash node registry so they are available for workflow execution.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Deliberately after load_dotenv() above — DataFlow env-models.md rule requires
# .env loaded before any operation. noqa: E402 is the guard, not an oversight.
from dataflow import DataFlow  # noqa: E402

# Use TEST_DATABASE_URL from environment, defaulting to the standard test PostgreSQL instance
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://admin:changeme123@127.0.0.1:5433/central_it_hub",
)

db = DataFlow(TEST_DATABASE_URL)


@db.model
class User:
    id: str
    email: str
    display_name: str
    country: str
    department: str
    account_enabled: bool = True
