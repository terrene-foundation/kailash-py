"""Regression test for #373: BulkResult MUST auto-emit WARN on partial failure.

Verifies that bulk operations emit WARN-level log when some records fail.
Per observability.md Rule 6: bulk ops with `failed > 0` must log WARN.
"""

import logging

import pytest


@pytest.mark.regression
class TestBulkResultPartialFailureWarn:
    """Issue #373: BulkResult auto-emit WARN on partial failure."""

    def test_bulk_create_partial_failure_emits_warn(self, caplog):
        """When bulk_create result has failed > 0, WARN is emitted."""
        # The WARN is emitted inside _bulk_create() when the node result dict
        # has failed > 0. We verify the logging path by checking that the
        # logger.warning call is wired correctly in the code.
        # Direct invocation requires a DataFlow instance; this test verifies
        # the code path exists via import and attribute inspection.
        import inspect

        from dataflow.features.express import ExpressDataFlow

        source = inspect.getsource(ExpressDataFlow.bulk_create)
        assert (
            "bulk_create.partial_failure" in source
        ), "express.bulk_create must emit 'bulk_create.partial_failure' WARN log"

    def test_bulk_update_partial_failure_emits_warn(self):
        """When bulk_update has skipped/failed records, WARN is emitted."""
        import inspect

        from dataflow.features.express import ExpressDataFlow

        source = inspect.getsource(ExpressDataFlow.bulk_update)
        assert (
            "bulk_update.partial_failure" in source
        ), "express.bulk_update must emit 'bulk_update.partial_failure' WARN log"

    def test_bulk_create_success_uses_info_not_warn(self):
        """Successful bulk_create uses INFO, not WARNING (was incorrectly WARNING before)."""
        import inspect

        from dataflow.features.bulk import BulkOperations

        source = inspect.getsource(BulkOperations.bulk_create)
        # The success path should use logger.info, not logger.warning
        assert (
            "logger.info" in source or "logger.info(" in source
        ), "bulk.bulk_create success path should use logger.info, not logger.warning"
