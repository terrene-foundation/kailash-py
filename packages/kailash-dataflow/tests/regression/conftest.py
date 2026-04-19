# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures + helpers for regression tests.

Hosts the ``sqlite_file_url`` fixture + ``RecordingExecutor`` stub +
``pass_through_plan`` factory used by the per-manager trust-wiring tests:

- ``test_trust_executor_wiring.py``
- ``test_audit_store_wiring.py``
- ``test_trust_manager_wiring.py``

These three files were split out of the former monolithic
``test_phase_5_11_trust_wiring.py`` per
rules/facade-manager-detection.md MUST Rule 2 (issue #499 Finding 8).

Helpers live in conftest (not a sibling module) because
``packages/kailash-dataflow/tests/regression/`` is not a Python package
(no ``__init__.py``), so relative imports from sibling test modules are
not available. Pytest auto-imports conftest and makes its names
importable by test files via the ``conftest`` attribute on the session,
but the canonical pattern for sharing helpers across pytest test modules
is a fixture + module-scoped pytest-importable globals.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import pytest

from dataflow.trust.query_wrapper import QueryAccessResult


@pytest.fixture
def recording_executor():
    """Factory fixture — returns the RecordingExecutor class.

    Fixture form lets sibling test files access the stub without needing
    to import it (conftest.py is auto-discovered by pytest but its names
    are not directly importable from sibling test files without package
    infrastructure).
    """
    return RecordingExecutor


@pytest.fixture
def plan_factory():
    """Factory fixture — returns the ``pass_through_plan`` helper."""
    return pass_through_plan


@pytest.fixture
def sqlite_file_url():
    """Yield a file-backed SQLite URL scoped to a single test.

    ``sqlite:///:memory:`` cannot be used because DataFlow's migration lock
    table is created lazily on a separate connection and ``:memory:``
    databases are not shared across connections.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"tf_{uuid.uuid4().hex}.db")
        yield f"sqlite:///{path}"


def pass_through_plan(
    *,
    additional_filters: Optional[Dict[str, Any]] = None,
    row_limit: Optional[int] = None,
    pii: Optional[List[str]] = None,
    allowed: bool = True,
    denied_reason: Optional[str] = None,
) -> QueryAccessResult:
    return QueryAccessResult(
        allowed=allowed,
        filtered_columns=[],
        additional_filters=additional_filters or {},
        row_limit=row_limit,
        denied_reason=denied_reason,
        applied_constraints=[],
        pii_columns_filtered=pii or [],
        sensitive_columns_flagged=[],
    )


class RecordingExecutor:
    """Observer executor that mimics the TrustAwareQueryExecutor surface.

    Every Express CRUD method calls one of these methods. The recorder lets
    tests assert exactly which model/operation/plan was seen.
    """

    def __init__(
        self,
        *,
        read_plan: Optional[QueryAccessResult] = None,
        write_plan: Optional[QueryAccessResult] = None,
        deny_writes: bool = False,
    ) -> None:
        self.read_plan = read_plan or pass_through_plan()
        self.write_plan = write_plan or pass_through_plan()
        self.deny_writes = deny_writes
        self.read_checks: List[Dict[str, Any]] = []
        self.write_checks: List[Dict[str, Any]] = []
        self.successes: List[Dict[str, Any]] = []
        self.failures: List[Dict[str, Any]] = []

    async def check_read_access(
        self,
        *,
        model_name: str,
        filter: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
    ) -> QueryAccessResult:
        self.read_checks.append(
            {"model": model_name, "filter": filter, "agent_id": agent_id}
        )
        return self.read_plan

    async def check_write_access(
        self,
        *,
        model_name: str,
        operation: str,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
    ) -> QueryAccessResult:
        self.write_checks.append(
            {"model": model_name, "operation": operation, "agent_id": agent_id}
        )
        if self.deny_writes:
            raise PermissionError(f"{operation} denied by test stub")
        return self.write_plan

    def apply_result_filter(self, data: Any, plan: QueryAccessResult) -> Any:
        if not plan.pii_columns_filtered:
            return data
        if isinstance(data, list):
            return [
                (
                    {k: v for k, v in row.items() if k not in plan.pii_columns_filtered}
                    if isinstance(row, dict)
                    else row
                )
                for row in data
            ]
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in plan.pii_columns_filtered}
        return data

    async def record_query_success(
        self,
        *,
        model_name: str,
        operation: str,
        plan: QueryAccessResult,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
        rows_affected: int = 0,
        query_params: Any = None,
    ) -> Optional[str]:
        self.successes.append(
            {
                "model": model_name,
                "operation": operation,
                "agent_id": agent_id,
                "rows_affected": rows_affected,
            }
        )
        return "success-event-id"

    async def record_query_failure(
        self,
        *,
        model_name: str,
        operation: str,
        plan: Optional[QueryAccessResult],
        agent_id: Optional[str] = None,
        trust_context: Any = None,
        error: Optional[str] = None,
        query_params: Any = None,
    ) -> None:
        self.failures.append(
            {
                "model": model_name,
                "operation": operation,
                "agent_id": agent_id,
                "error": error,
            }
        )
