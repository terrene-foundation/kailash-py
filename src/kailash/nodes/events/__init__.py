# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Workflow nodes for the kailash.EventBus primitive.

``EventPublishNode`` lets a :class:`~kailash.workflow.builder.WorkflowBuilder`
step publish a domain event to a :class:`kailash.EventBus` from inside a
running workflow, carrying ``correlation_id`` for trace continuity.
"""

from __future__ import annotations

from .publish import EventPublishNode

__all__ = ["EventPublishNode"]
