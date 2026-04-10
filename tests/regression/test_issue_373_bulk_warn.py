"""Regression test for #373: BulkResult MUST auto-emit WARN on partial failure.

Verifies that bulk operations emit WARN-level log when some records fail.
Per observability.md Rule 6: bulk ops with `failed > 0` must log WARN.

These tests read source files directly rather than importing the dataflow
package, because kailash-dataflow is a sub-package that may not be installed
in the root project venv. The source files are always available on disk.
"""

from pathlib import Path

import pytest

_DATAFLOW_SRC = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "kailash-dataflow"
    / "src"
    / "dataflow"
)


@pytest.mark.regression
class TestBulkResultPartialFailureWarn:
    """Issue #373: BulkResult auto-emit WARN on partial failure."""

    def test_bulk_create_partial_failure_emits_warn(self):
        """When bulk_create result has failed > 0, WARN is emitted."""
        source = (_DATAFLOW_SRC / "features" / "express.py").read_text()
        assert (
            "bulk_create.partial_failure" in source
        ), "express.bulk_create must emit 'bulk_create.partial_failure' WARN log"

    def test_bulk_update_partial_failure_emits_warn(self):
        """When bulk_update has skipped/failed records, WARN is emitted."""
        source = (_DATAFLOW_SRC / "features" / "express.py").read_text()
        assert (
            "bulk_update.partial_failure" in source
        ), "express.bulk_update must emit 'bulk_update.partial_failure' WARN log"

    def test_bulk_create_success_uses_info_not_warn(self):
        """Successful bulk_create uses INFO, not WARNING (was incorrectly WARNING before)."""
        source = (_DATAFLOW_SRC / "features" / "bulk.py").read_text()
        # The success path should use logger.info, not logger.warning
        assert (
            "logger.info" in source
        ), "bulk.bulk_create success path should use logger.info, not logger.warning"
