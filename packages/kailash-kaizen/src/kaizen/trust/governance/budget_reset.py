"""
Budget Reset Service.

Handles scheduled resets for external agent budgets:
- Daily reset at midnight UTC (daily_spent_usd, daily_execution_count)
- Monthly reset on 1st of month (monthly_spent_usd, monthly_execution_count)
- Graceful rollover with archival for reporting

Integrates with DataFlow for batch budget updates.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class BudgetResetService:
    """
    Service for scheduled budget resets.

    Resets budget counters on daily and monthly schedules:
    - Daily: 00:00 UTC (resets daily_spent_usd, daily_execution_count)
    - Monthly: 00:00 UTC on 1st (resets monthly_spent_usd, monthly_execution_count)

    Preserves historical data for reporting and audit.

    Examples:
        >>> from dataflow import DataFlow
        >>> db = DataFlow(database_type="sqlite", database_config={"database": ":memory:"})
        >>> runtime = AsyncLocalRuntime()
        >>> service = BudgetResetService(runtime=runtime, db=db)
        >>>
        >>> # Daily reset (typically scheduled via cron/APScheduler)
        >>> result = await service.reset_daily_budgets()
        >>> print(f"Reset {result['budgets_reset']} daily budgets")
        >>>
        >>> # Monthly reset
        >>> result = await service.reset_monthly_budgets()
        >>> print(f"Reset {result['budgets_reset']} monthly budgets")
    """

    def __init__(self, runtime: AsyncLocalRuntime, db: Any | None = None):
        """
        Initialize budget reset service.

        Args:
            runtime: AsyncLocalRuntime for workflow execution
            db: Optional DataFlow instance for persistence
        """
        self.runtime = runtime
        self.db = db

    async def reset_daily_budgets(self) -> dict[str, Any]:
        """
        Reset daily budget counters for all external agents.

        Resets:
        - daily_spent_usd → 0.0
        - daily_execution_count → 0
        - last_reset_daily → current timestamp

        Preserves:
        - All monthly counters
        - Budget limits
        - Configuration

        Returns:
            Result dict with:
                - budgets_reset: Number of budgets updated
                - timestamp: Reset timestamp
                - errors: List of errors if any

        Examples:
            >>> result = await service.reset_daily_budgets()
            >>> result['budgets_reset']
            5
            >>> result['errors']
            []
        """
        reset_timestamp = datetime.now(timezone.utc)
        budgets_reset = 0
        errors = []

        logger.info(f"Starting daily budget reset at {reset_timestamp.isoformat()}")

        if not self.db:
            logger.warning("No database configured, skipping daily reset")
            return {
                "budgets_reset": 0,
                "timestamp": reset_timestamp.isoformat(),
                "errors": ["No database configured"],
            }

        try:
            # Create workflow to fetch all budgets
            workflow = WorkflowBuilder()

            # List all ExternalAgentBudget records
            workflow.add_node(
                "ListExternalAgentBudgetNode",
                "list_budgets",
                {
                    "filters": {},  # Get all budgets
                    "limit": 1000,  # Reasonable batch size
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Get budget list from results
            budgets = results.get("list_budgets", {}).get("data", [])

            # Reset each budget's daily counters
            for budget_data in budgets:
                try:
                    await self._reset_daily_counters(
                        budget_data["external_agent_id"], reset_timestamp
                    )
                    budgets_reset += 1
                except Exception as e:
                    error_msg = (
                        f"Failed to reset daily budget for "
                        f"{budget_data.get('external_agent_id', 'unknown')}: {e}"
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)

            logger.info(
                f"Daily budget reset completed: {budgets_reset} budgets reset, "
                f"{len(errors)} errors"
            )

            return {
                "budgets_reset": budgets_reset,
                "timestamp": reset_timestamp.isoformat(),
                "errors": errors,
            }

        except Exception as e:
            error_msg = f"Daily budget reset failed: {e}"
            logger.error(error_msg)
            return {
                "budgets_reset": 0,
                "timestamp": reset_timestamp.isoformat(),
                "errors": [error_msg],
            }

    async def reset_monthly_budgets(
        self, archive_history: bool = True
    ) -> dict[str, Any]:
        """
        Reset monthly budget counters for all external agents.

        Resets:
        - monthly_spent_usd → 0.0
        - monthly_execution_count → 0
        - last_reset_monthly → current timestamp

        Preserves:
        - All daily counters (separate reset schedule)
        - Budget limits
        - Configuration

        Optionally archives previous month's data for reporting.

        Args:
            archive_history: Whether to archive previous month's data

        Returns:
            Result dict with:
                - budgets_reset: Number of budgets updated
                - archived: Whether history was archived
                - timestamp: Reset timestamp
                - errors: List of errors if any

        Examples:
            >>> result = await service.reset_monthly_budgets(archive_history=True)
            >>> result['budgets_reset']
            5
            >>> result['archived']
            True
        """
        reset_timestamp = datetime.now(timezone.utc)
        budgets_reset = 0
        archived_count = 0
        errors = []

        logger.info(
            f"Starting monthly budget reset at {reset_timestamp.isoformat()}, "
            f"archive_history={archive_history}"
        )

        if not self.db:
            logger.warning("No database configured, skipping monthly reset")
            return {
                "budgets_reset": 0,
                "archived": False,
                "timestamp": reset_timestamp.isoformat(),
                "errors": ["No database configured"],
            }

        try:
            # Create workflow to fetch all budgets
            workflow = WorkflowBuilder()

            # List all ExternalAgentBudget records
            workflow.add_node(
                "ListExternalAgentBudgetNode",
                "list_budgets",
                {
                    "filters": {},
                    "limit": 1000,
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Get budget list
            budgets = results.get("list_budgets", {}).get("data", [])

            # Reset each budget's monthly counters
            for budget_data in budgets:
                try:
                    # Archive if requested
                    if archive_history and budget_data.get("monthly_spent_usd", 0) > 0:
                        await self._archive_monthly_data(budget_data, reset_timestamp)
                        archived_count += 1

                    # Reset counters
                    await self._reset_monthly_counters(
                        budget_data["external_agent_id"], reset_timestamp
                    )
                    budgets_reset += 1

                except Exception as e:
                    error_msg = (
                        f"Failed to reset monthly budget for "
                        f"{budget_data.get('external_agent_id', 'unknown')}: {e}"
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)

            logger.info(
                f"Monthly budget reset completed: {budgets_reset} budgets reset, "
                f"{archived_count} archived, {len(errors)} errors"
            )

            return {
                "budgets_reset": budgets_reset,
                "archived": archive_history and archived_count > 0,
                "archived_count": archived_count,
                "timestamp": reset_timestamp.isoformat(),
                "errors": errors,
            }

        except Exception as e:
            error_msg = f"Monthly budget reset failed: {e}"
            logger.error(error_msg)
            return {
                "budgets_reset": 0,
                "archived": False,
                "archived_count": 0,
                "timestamp": reset_timestamp.isoformat(),
                "errors": [error_msg],
            }

    async def _reset_daily_counters(
        self, external_agent_id: str, reset_timestamp: datetime
    ) -> None:
        """
        Reset daily counters for a single budget.

        Args:
            external_agent_id: External agent identifier
            reset_timestamp: Timestamp of reset
        """
        if not self.db:
            return

        workflow = WorkflowBuilder()

        # Update daily counters
        workflow.add_node(
            "UpdateExternalAgentBudgetNode",
            "reset_daily",
            {
                "external_agent_id": external_agent_id,
                "daily_spent_usd": 0.0,
                "daily_execution_count": 0,
                "last_reset_daily": reset_timestamp.isoformat(),
            },
        )

        await self.runtime.execute_workflow_async(workflow.build(), inputs={})

        logger.debug(f"Daily counters reset for {external_agent_id}")

    async def _reset_monthly_counters(
        self, external_agent_id: str, reset_timestamp: datetime
    ) -> None:
        """
        Reset monthly counters for a single budget.

        Args:
            external_agent_id: External agent identifier
            reset_timestamp: Timestamp of reset
        """
        if not self.db:
            return

        workflow = WorkflowBuilder()

        # Update monthly counters
        workflow.add_node(
            "UpdateExternalAgentBudgetNode",
            "reset_monthly",
            {
                "external_agent_id": external_agent_id,
                "monthly_spent_usd": 0.0,
                "monthly_execution_count": 0,
                "last_reset_monthly": reset_timestamp.isoformat(),
            },
        )

        await self.runtime.execute_workflow_async(workflow.build(), inputs={})

        logger.debug(f"Monthly counters reset for {external_agent_id}")

    async def _archive_monthly_data(
        self, budget_data: dict[str, Any], reset_timestamp: datetime
    ) -> None:
        """
        Archive previous month's budget data for reporting.

        Args:
            budget_data: Current budget data to archive
            reset_timestamp: Timestamp of reset (start of new month)
        """
        if not self.db:
            return

        # Calculate archive period
        # If reset_timestamp is 2025-01-01, we're archiving December 2024
        year = reset_timestamp.year
        month = reset_timestamp.month - 1
        if month == 0:
            month = 12
            year -= 1

        archive_record = {
            "external_agent_id": budget_data["external_agent_id"],
            "year": year,
            "month": month,
            "monthly_spent_usd": budget_data.get("monthly_spent_usd", 0.0),
            "monthly_execution_count": budget_data.get("monthly_execution_count", 0),
            "archived_at": reset_timestamp.isoformat(),
        }

        workflow = WorkflowBuilder()

        # Create archive record
        workflow.add_node(
            "CreateBudgetHistoryNode",
            "archive",
            archive_record,
        )

        try:
            await self.runtime.execute_workflow_async(workflow.build(), inputs={})
            logger.debug(
                f"Archived monthly data for {budget_data['external_agent_id']}: "
                f"{year}-{month:02d}"
            )
        except Exception as e:
            logger.error(
                f"Failed to archive monthly data for "
                f"{budget_data['external_agent_id']}: {e}"
            )
            # Don't fail the reset if archival fails


# Export all public types
__all__ = [
    "BudgetResetService",
]
