# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Event store adapters for audit trail persistence."""

from dataflow.core.event_stores.sqlite import SQLiteEventStore

__all__ = ["SQLiteEventStore"]
