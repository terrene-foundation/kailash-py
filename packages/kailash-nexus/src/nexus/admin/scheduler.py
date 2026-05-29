# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HTTP admin panel for the runtime workflow scheduler (issue #937).

Wraps the framework-agnostic ``kailash.runtime.scheduler_admin.SchedulerAdminAPI``
(issue #913 / PR #936) in six Nexus HTTP routes so operators can list, inspect,
enable, disable, reschedule, and delete schedules over HTTP behind a role guard.

The admin class performs ZERO authentication (per ``specs/scheduling.md`` §11.7);
this module supplies it: every route runs behind
``RequireRole("scheduler-admin")`` and the audit ``actor`` is taken from the
authenticated identity's JWT subject (``user.user_id``), never a request body.

Note: this module deliberately does NOT use ``from __future__ import
annotations`` — FastAPI inspects parameter annotations at runtime to inject
``Request`` / ``Depends`` values, and PEP 563 string annotations break that.
"""

from typing import Any, Dict, List, Optional

from fastapi import Depends
from pydantic import BaseModel

from kailash.runtime.scheduler_admin import ScheduleAdminView, SchedulerAdminAPI
from kailash.sdk_exceptions import ScheduleNotFound
from kailash.trust.auth.models import AuthenticatedUser
from nexus.auth.dependencies import RequireRole
from nexus.errors import NotFoundError, ValidationError

__all__ = ["register_scheduler_admin", "ScheduleView", "CronUpdate"]


class CronUpdate(BaseModel):
    """Request body for ``PATCH /admin/schedules/{id}/cron``."""

    cron_expression: str


class ScheduleView(BaseModel):
    """OpenAPI response shape mirroring ``ScheduleAdminView`` (spec §11.4)."""

    schedule_id: str
    schedule_type: str
    workflow_name: str
    trigger_args: Dict[str, Any]
    created_at: str
    next_run_time: Optional[str] = None
    enabled: bool
    kwargs: Dict[str, Any]
    retry_spec: Optional[Dict[str, Any]] = None
    time_limits: Dict[str, Optional[float]]


def register_scheduler_admin(
    app: Any,
    admin: SchedulerAdminAPI,
    *,
    role: str = "scheduler-admin",
) -> None:
    """Register the six scheduler-admin HTTP routes on a Nexus app.

    Args:
        app: A ``Nexus`` instance with the HTTP transport initialized. Call
            this BEFORE ``app.start()`` (registrations queue and apply at start)
            or after the gateway exists (they apply immediately).
        admin: A ``SchedulerAdminAPI`` bound to the running ``WorkflowScheduler``.
        role: The role a caller MUST hold to reach any route (default
            ``"scheduler-admin"``). No/invalid auth -> 401; wrong role -> 403.

    Routes (all under the ``role`` guard):
        - ``GET    /admin/schedules``               -> list
        - ``GET    /admin/schedules/{id}``          -> get
        - ``PATCH  /admin/schedules/{id}/disable``  -> disable
        - ``PATCH  /admin/schedules/{id}/enable``   -> enable
        - ``PATCH  /admin/schedules/{id}/cron``     -> reschedule (body: CronUpdate)
        - ``DELETE /admin/schedules/{id}``          -> delete (204)

    Error mapping (via the transport's NexusError handler):
        ``ScheduleNotFound`` -> 404, ``ValueError`` -> 400.

    Operator notes:
        - ``JWTMiddleware`` MUST be installed on the app for the role guard to
          resolve an authenticated user. If it is absent, every route fails
          CLOSED (401 "Not authenticated") rather than open — but the panel is
          then unusable, so install the auth middleware before registering.
        - These routes are privileged but not rate-limited here. For
          internet-exposed deployments, mount a rate-limit middleware in front
          of the admin router (the role gate already bounds exposure to
          authenticated ``scheduler-admin`` operators; this is defense-in-depth).
    """
    guard = RequireRole(role)

    async def list_schedules() -> List[ScheduleAdminView]:
        return admin.list_schedules()

    async def get_schedule(schedule_id: str) -> ScheduleAdminView:
        try:
            return admin.get_schedule(schedule_id)
        except ScheduleNotFound as exc:
            raise NotFoundError(str(exc))

    async def disable_schedule(
        schedule_id: str,
        user: AuthenticatedUser = Depends(guard),
    ) -> Dict[str, Any]:
        try:
            return admin.disable_schedule(schedule_id, actor=user.user_id)
        except ScheduleNotFound as exc:
            raise NotFoundError(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))

    async def enable_schedule(
        schedule_id: str,
        user: AuthenticatedUser = Depends(guard),
    ) -> Dict[str, Any]:
        try:
            return admin.enable_schedule(schedule_id, actor=user.user_id)
        except ScheduleNotFound as exc:
            raise NotFoundError(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))

    async def update_cron(
        schedule_id: str,
        body: CronUpdate,
        user: AuthenticatedUser = Depends(guard),
    ) -> Dict[str, Any]:
        try:
            return admin.update_cron(
                schedule_id, body.cron_expression, actor=user.user_id
            )
        except ScheduleNotFound as exc:
            raise NotFoundError(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))

    async def delete_schedule(
        schedule_id: str,
        user: AuthenticatedUser = Depends(guard),
    ) -> None:
        try:
            admin.delete_schedule(schedule_id, actor=user.user_id)
        except ScheduleNotFound as exc:
            raise NotFoundError(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))

    app.register_endpoint(
        "/admin/schedules",
        ["GET"],
        list_schedules,
        response_model=List[ScheduleView],
        dependencies=[Depends(guard)],
    )
    app.register_endpoint(
        "/admin/schedules/{schedule_id}",
        ["GET"],
        get_schedule,
        response_model=ScheduleView,
        dependencies=[Depends(guard)],
    )
    app.register_endpoint(
        "/admin/schedules/{schedule_id}/disable",
        ["PATCH"],
        disable_schedule,
        response_model=ScheduleView,
    )
    app.register_endpoint(
        "/admin/schedules/{schedule_id}/enable",
        ["PATCH"],
        enable_schedule,
        response_model=ScheduleView,
    )
    app.register_endpoint(
        "/admin/schedules/{schedule_id}/cron",
        ["PATCH"],
        update_cron,
        response_model=ScheduleView,
    )
    app.register_endpoint(
        "/admin/schedules/{schedule_id}",
        ["DELETE"],
        delete_schedule,
        status_code=204,
    )
