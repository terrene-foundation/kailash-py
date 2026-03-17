# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Level 1 integration tests for infrastructure stores against real databases.

Tests run each store backend (EventStore, Checkpoint, DLQ, ExecutionStore,
IdempotencyStore) against PostgreSQL, MySQL, and SQLite to verify
dialect-portable behavior.
"""
