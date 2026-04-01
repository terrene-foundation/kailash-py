# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Handler that references CreateUser generated node (for connection detection)."""

from kailash.workflow.builder import WorkflowBuilder


def create_user_handler(data: dict) -> dict:
    """Create a new user via the CreateUser workflow node."""
    workflow = WorkflowBuilder()
    workflow.add_node("CreateUser", "create", data)
    # In a real app, this would execute the workflow
    return {"status": "created"}
