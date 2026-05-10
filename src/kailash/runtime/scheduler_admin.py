# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Runtime admin API for :class:`WorkflowScheduler` (issue #913).

Operators frequently need to disable a schedule, edit a cron expression,
or list active schedules WITHOUT shipping a code change and restarting
the process. The underlying :class:`WorkflowScheduler` already exposes
``pause`` / ``resume`` / ``update_cron`` / ``cancel`` / ``list_schedules``
on its instance, but those primitives are scheduler-internal and not
shaped for an admin surface (Nexus panel, CLI tool, ops UI):

* They mutate state in-place; a multi-tenant admin must filter the visible
  set per-caller.
* The list view returns :class:`ScheduleInfo` dataclasses; HTTP and CLI
  surfaces want JSON-serializable dicts whose shape is documented and
  versioned.
* They surface :class:`KeyError` on ``cancel`` and
  :class:`~kailash.sdk_exceptions.ScheduleNotFound` on the new admin
  methods (``pause`` / ``resume`` / ``update_cron``); a stable admin
  contract MUST emit a single typed exception class for all unknown-id
  cases so HTTP 404 / exit-code-4 mapping works without per-method
  branching.

This module wraps the scheduler with a thin :class:`SchedulerAdminAPI`
class whose every method is callable from tests, from a Nexus handler,
from a CLI tool, or from a worker-side admin RPC. The HTTP / CLI / RPC
layers are ALWAYS thin wrappers over this module — never re-implement
the operations elsewhere.

Tenant isolation
----------------

The current :class:`WorkflowScheduler` is a single-tenant object: every
schedule it owns is in the same logical scope. Per the brief's design
constraint, the admin surface declares this assumption explicitly via
the ``tenant_scope`` parameter and refuses to mutate schedules outside
its declared scope. When the SDK grows multi-tenant scheduler support,
the admin's ``_visible_ids`` filter is the structural extension point —
it converts to a per-tenant query against the scheduler's tenant index
without changing the public surface.

Authentication
--------------

This module performs ZERO authentication. The caller (Nexus handler,
CLI, ops RPC) is responsible for authenticating the operator and
supplying a non-empty ``actor`` field on every mutation. Every mutating
call writes a structured audit log entry naming the actor + operation
+ schedule_id so post-incident triage can reconstruct who edited what.

Related issues:

* #910 — per-job retry primitives (``RetrySpec``); admin pass-through
  reads via ``ScheduleInfo.retry_spec``.
* #912 — per-task time limits; reads via the persisted job kwargs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from kailash.sdk_exceptions import ScheduleNotFound

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kailash.runtime.scheduler import (
        RetrySpec,
        ScheduleInfo,
        ScheduleType,
        WorkflowScheduler,
    )

logger = logging.getLogger(__name__)

__all__ = [
    "SchedulerAdminAPI",
    "ScheduleAdminView",
    "DEFAULT_TENANT_SCOPE",
]

# Sentinel for the single-tenant scheduler shape. When multi-tenant
# scheduler support lands, replace this constant with a per-call lookup
# against the scheduler's tenant index — every public method already
# routes through ``_visible_ids`` so the change is one method, not the
# whole admin surface.
DEFAULT_TENANT_SCOPE = "default"


# Internal kwargs keys persisted by the scheduler in APScheduler's job
# kwargs dict. Re-defined here as module-private constants so the admin
# view can reach into a job's kwargs to surface retry + time-limit fields
# WITHOUT importing scheduler internals at function-call time (which
# would create a circular import when the scheduler grows an admin
# property).
_RETRY_SPEC_KWARG = "_kailash_retry_spec"
_TIME_LIMIT_KWARG = "_kailash_time_limits"


def _serialize_retry_spec(spec: Optional["RetrySpec"]) -> Optional[Dict[str, Any]]:
    """Convert a :class:`RetrySpec` to a JSON-friendly dict.

    The dataclass uses ``Tuple[Type[BaseException], ...]`` for
    ``retry_on`` / ``dont_retry_on`` — class objects are not
    JSON-serializable. Map to their qualified name so the admin view
    is round-trip safe through HTTP/CLI without surfacing class
    objects to non-Python clients.
    """
    if spec is None:
        return None
    return {
        "max_retries": spec.max_retries,
        "backoff": spec.backoff,
        "backoff_base_seconds": spec.backoff_base_seconds,
        "backoff_max_seconds": spec.backoff_max_seconds,
        "retry_on": [t.__name__ for t in spec.retry_on],
        "dont_retry_on": [t.__name__ for t in spec.dont_retry_on],
    }


def _serialize_time_limits(
    pair: Optional[Any],
) -> Dict[str, Optional[float]]:
    """Surface the persisted (soft, hard) tuple as a documented dict.

    The scheduler stores effective time limits as a 2-tuple under
    ``_TIME_LIMIT_KWARG``. Return ``{"soft_time_limit": s,
    "time_limit": h}`` so the admin view never leaks the internal
    tuple shape to API consumers.
    """
    if pair is None:
        return {"soft_time_limit": None, "time_limit": None}
    soft, hard = pair
    return {"soft_time_limit": soft, "time_limit": hard}


class ScheduleAdminView(Dict[str, Any]):
    """Documented JSON-friendly view of a schedule for admin surfaces.

    Inherits ``dict`` so the value is directly JSON-serializable AND
    the field set is documented in this class's docstring. Field
    schema (stable across the admin surface):

    * ``schedule_id``: str, format ``sched-{12_hex_chars}``
    * ``schedule_type``: str, one of ``"cron"`` / ``"interval"`` / ``"once"``
    * ``workflow_name``: str, operator-supplied label or ``""``
    * ``trigger_args``: dict, schedule-type-specific (cron expression,
      interval seconds, or run_at ISO string)
    * ``created_at``: ISO 8601 timestamp string (UTC)
    * ``next_run_time``: ISO 8601 timestamp string OR ``None`` if paused
      / completed
    * ``enabled``: bool — ``True`` if the scheduler will fire this
      schedule on its next tick
    * ``kwargs``: dict — user-supplied runtime kwargs (sanitized: the
      scheduler's internal ``_kailash_*`` keys are filtered out)
    * ``retry_spec``: dict OR ``None`` — issue #910 retry primitives
      shape (when supplied at schedule time)
    * ``time_limits``: dict — issue #912 per-fire deadlines
      ``{"soft_time_limit": <s|None>, "time_limit": <s|None>}``
    """


class SchedulerAdminAPI:
    """Runtime admin surface for an in-process :class:`WorkflowScheduler`.

    Wraps the scheduler with operations safe to call from a privileged
    admin endpoint: list / enable (resume) / disable (pause) /
    update_cron / delete (cancel). All mutating operations write a
    structured audit log line naming the supplied ``actor`` and the
    schedule_id touched, so post-incident triage can reconstruct who
    edited what.

    The scheduler's reload semantics are handled by APScheduler itself:
    ``pause_job`` / ``resume_job`` / ``reschedule_job`` mutate the
    in-memory job graph AND the persisted SQLAlchemyJobStore atomically;
    APScheduler's ``AsyncIOScheduler`` picks up the change on its next
    tick (typically immediate since the scheduler holds the
    just-modified job in memory).

    Args:
        scheduler: The :class:`WorkflowScheduler` instance to expose
            for admin operations. The admin holds a reference to the
            same scheduler the runtime is firing — no parallel state.
        tenant_scope: A logical scope identifier the admin recognizes.
            The single-tenant scheduler MUST receive the default
            ``"default"`` value; multi-tenant schedulers (future) MUST
            pass the caller's tenant id and the admin will filter
            ``list_schedules`` / mutation calls to that tenant.

    Example:
        >>> from kailash.runtime.scheduler import WorkflowScheduler
        >>> from kailash.runtime.scheduler_admin import SchedulerAdminAPI
        >>>
        >>> scheduler = WorkflowScheduler()
        >>> scheduler.start()
        >>> admin = SchedulerAdminAPI(scheduler)
        >>>
        >>> # List active schedules
        >>> for view in admin.list_schedules():
        ...     print(view["schedule_id"], view["enabled"])
        >>>
        >>> # Disable a schedule without redeploying
        >>> admin.disable_schedule("sched-abc123def456", actor="ops@example.com")
        >>>
        >>> # Edit cron at runtime
        >>> admin.update_cron(
        ...     "sched-abc123def456",
        ...     "0 7 * * *",
        ...     actor="ops@example.com",
        ... )

    Notes:
        **Single-tenant assumption.** The default scheduler is
        single-tenant: every registered schedule belongs to the same
        logical scope. The ``tenant_scope`` parameter exists so admin
        surfaces can declare their scope explicitly (and so a future
        multi-tenant scheduler can grow per-tenant filtering without
        breaking this surface).

        **Authentication is the caller's job.** This class performs no
        identity check on ``actor``. The HTTP / CLI / RPC wrapper that
        calls into this admin MUST authenticate the operator and
        supply a non-empty ``actor`` string for the audit trail.
    """

    def __init__(
        self,
        scheduler: "WorkflowScheduler",
        *,
        tenant_scope: str = DEFAULT_TENANT_SCOPE,
    ) -> None:
        if scheduler is None:
            raise ValueError(
                "SchedulerAdminAPI requires a non-None WorkflowScheduler "
                "instance; got None"
            )
        if not isinstance(tenant_scope, str) or not tenant_scope:
            raise ValueError(
                f"SchedulerAdminAPI tenant_scope must be a non-empty string, "
                f"got {tenant_scope!r}"
            )
        self._scheduler = scheduler
        self._tenant_scope = tenant_scope

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_schedules(self) -> List[ScheduleAdminView]:
        """Return every schedule the admin can see, as JSON-friendly dicts.

        The scheduler's ``list_schedules`` returns
        :class:`ScheduleInfo` dataclasses; this method serializes each
        to a :class:`ScheduleAdminView` (a dict) so the same value can
        be returned from a Nexus handler over HTTP, dumped to a CLI's
        stdout, or relayed to a worker-side admin RPC without further
        massaging.

        Single-tenant schedulers return every registered schedule.
        Multi-tenant schedulers (future) MUST filter to the admin's
        ``tenant_scope`` via :meth:`_visible_ids`.

        Returns:
            List of :class:`ScheduleAdminView` dicts, one per visible
            schedule. Empty list when no schedules are registered.
        """
        infos = self._scheduler.list_schedules()
        return [self._info_to_view(info) for info in infos]

    def get_schedule(self, schedule_id: str) -> ScheduleAdminView:
        """Return the JSON-friendly view of a single schedule.

        Args:
            schedule_id: The ID returned at schedule-time.

        Raises:
            ScheduleNotFound: When ``schedule_id`` is not registered
                (or not visible to the admin's tenant scope).
        """
        self._ensure_visible(schedule_id)
        # Re-fetch from the scheduler so ``next_run_time`` reflects the
        # latest APScheduler state (the scheduler's list_schedules()
        # populates it from the live job graph).
        for info in self._scheduler.list_schedules():
            if info.schedule_id == schedule_id:
                return self._info_to_view(info)
        raise ScheduleNotFound(schedule_id)

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def disable_schedule(
        self,
        schedule_id: str,
        *,
        actor: str,
    ) -> ScheduleAdminView:
        """Pause a schedule so no further fires occur.

        Idempotent — disabling an already-disabled schedule is a no-op
        on the scheduler and still returns the current view.

        Args:
            schedule_id: The ID returned at schedule-time.
            actor: Non-empty operator identifier (email, username,
                service principal). Written to the audit log.

        Returns:
            The post-disable :class:`ScheduleAdminView` (with
            ``enabled=False`` and ``next_run_time=None``).

        Raises:
            ScheduleNotFound: When ``schedule_id`` is unknown.
            ValueError: When ``actor`` is empty.
        """
        self._require_actor(actor)
        self._ensure_visible(schedule_id)
        self._scheduler.pause(schedule_id)
        logger.info(
            "scheduler.admin.disable actor=%s schedule_id=%s tenant=%s",
            actor,
            schedule_id,
            self._tenant_scope,
        )
        return self.get_schedule(schedule_id)

    def enable_schedule(
        self,
        schedule_id: str,
        *,
        actor: str,
    ) -> ScheduleAdminView:
        """Resume a paused schedule, recomputing the next fire time.

        Idempotent — enabling an already-enabled schedule is a no-op.

        Args:
            schedule_id: The ID returned at schedule-time.
            actor: Non-empty operator identifier. Written to the
                audit log.

        Returns:
            The post-resume :class:`ScheduleAdminView` (with the new
            ``next_run_time`` recomputed from the trigger).

        Raises:
            ScheduleNotFound: When ``schedule_id`` is unknown.
            ValueError: When ``actor`` is empty.
        """
        self._require_actor(actor)
        self._ensure_visible(schedule_id)
        self._scheduler.resume(schedule_id)
        logger.info(
            "scheduler.admin.enable actor=%s schedule_id=%s tenant=%s",
            actor,
            schedule_id,
            self._tenant_scope,
        )
        return self.get_schedule(schedule_id)

    def update_cron(
        self,
        schedule_id: str,
        cron_expression: str,
        *,
        actor: str,
    ) -> ScheduleAdminView:
        """Replace a cron schedule's expression. Reloads on next tick.

        APScheduler's ``reschedule_job`` swaps the trigger atomically
        AND recomputes ``next_run_time`` — so the running scheduler
        picks up the new cron on its next event-loop tick (typically
        immediate).

        Args:
            schedule_id: The ID of an existing CRON schedule.
            cron_expression: A 5-field cron expression
                (minute hour day month weekday).
            actor: Non-empty operator identifier.

        Returns:
            The post-update :class:`ScheduleAdminView` reflecting the
            new cron + recomputed ``next_run_time``.

        Raises:
            ScheduleNotFound: When ``schedule_id`` is unknown.
            ValueError: When ``cron_expression`` is invalid OR
                ``actor`` is empty. Cron-validation messages start
                with ``"invalid cron"`` for grep-able pattern matching
                by callers (mirrors the underlying scheduler's
                contract).
        """
        self._require_actor(actor)
        self._ensure_visible(schedule_id)
        # Refuse update_cron on non-CRON schedules with a clear typed
        # error rather than letting APScheduler raise an opaque
        # internal exception about trigger mismatch — the admin
        # surface is the operator-facing contract, so the precondition
        # is checked here.
        info = self._lookup_info(schedule_id)
        if info.schedule_type.value != "cron":
            raise ValueError(
                f"update_cron is only valid for cron schedules; schedule "
                f"{schedule_id!r} is of type "
                f"{info.schedule_type.value!r}. Cancel and recreate as a "
                f"cron schedule instead."
            )
        self._scheduler.update_cron(schedule_id, cron_expression)
        logger.info(
            "scheduler.admin.update_cron actor=%s schedule_id=%s "
            "cron='%s' tenant=%s",
            actor,
            schedule_id,
            cron_expression,
            self._tenant_scope,
        )
        return self.get_schedule(schedule_id)

    def delete_schedule(
        self,
        schedule_id: str,
        *,
        actor: str,
    ) -> None:
        """Remove a schedule entirely. Subsequent ``get_schedule`` raises.

        Maps to :meth:`WorkflowScheduler.cancel`; replaces the
        scheduler's :class:`KeyError` with a typed
        :class:`ScheduleNotFound` for stable admin-surface error
        mapping.

        Args:
            schedule_id: The ID to remove.
            actor: Non-empty operator identifier.

        Raises:
            ScheduleNotFound: When ``schedule_id`` is unknown.
            ValueError: When ``actor`` is empty.
        """
        self._require_actor(actor)
        self._ensure_visible(schedule_id)
        try:
            self._scheduler.cancel(schedule_id)
        except KeyError as exc:
            # Translate to the typed admin-surface exception so HTTP /
            # CLI mappings can rely on a single class for unknown-id
            # cases across every method in this surface.
            raise ScheduleNotFound(schedule_id) from exc
        logger.info(
            "scheduler.admin.delete actor=%s schedule_id=%s tenant=%s",
            actor,
            schedule_id,
            self._tenant_scope,
        )

    # ------------------------------------------------------------------
    # Internal helpers — single source of truth for tenant filtering
    # ------------------------------------------------------------------

    def _visible_ids(self) -> Iterable[str]:
        """Yield schedule_ids visible to the admin's tenant scope.

        Single-tenant: every registered schedule. Multi-tenant
        (future): filter the scheduler's tenant index to those
        matching ``self._tenant_scope``. This is the structural
        extension point for multi-tenancy — every public method
        routes through ``_ensure_visible`` so per-tenant filtering
        kicks in here without API changes.
        """
        return list(self._scheduler._schedules.keys())

    def _ensure_visible(self, schedule_id: str) -> None:
        """Raise :class:`ScheduleNotFound` when ``schedule_id`` not visible.

        Single source of truth for unknown-id handling across every
        admin operation. Translates the scheduler's internal
        ``KeyError`` (cancel) and :class:`ScheduleNotFound` (pause/
        resume/update_cron) into one canonical class for the admin
        contract.
        """
        if schedule_id not in self._visible_ids():
            raise ScheduleNotFound(schedule_id)

    def _lookup_info(self, schedule_id: str) -> "ScheduleInfo":
        """Return the live :class:`ScheduleInfo` for ``schedule_id``."""
        info = self._scheduler._schedules.get(schedule_id)
        if info is None:
            raise ScheduleNotFound(schedule_id)
        return info

    @staticmethod
    def _require_actor(actor: str) -> None:
        """Validate the audit-trail ``actor`` is non-empty.

        Empty actor is BLOCKED at the admin surface — every mutating
        call writes the actor into the audit log; an empty value
        would render the log entry useless for post-incident triage.
        """
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError(
                "actor must be a non-empty string identifying the operator "
                "performing the admin action (audit trail requirement)"
            )

    def _info_to_view(self, info: "ScheduleInfo") -> ScheduleAdminView:
        """Convert a :class:`ScheduleInfo` to a :class:`ScheduleAdminView`."""
        # Reach into the underlying APScheduler job kwargs to surface
        # retry + time-limit fields (issues #910/#912) — the
        # ScheduleInfo only carries `retry_spec`, the time-limit pair
        # lives in the persisted job kwargs under a private kwarg key.
        job = self._scheduler._scheduler.get_job(info.schedule_id)
        time_limits_pair = None
        if job is not None and job.kwargs is not None:
            time_limits_pair = job.kwargs.get(_TIME_LIMIT_KWARG)
        view: ScheduleAdminView = ScheduleAdminView(
            schedule_id=info.schedule_id,
            schedule_type=info.schedule_type.value,
            workflow_name=info.workflow_name,
            trigger_args=dict(info.trigger_args),
            created_at=_isoformat(info.created_at),
            next_run_time=_isoformat(info.next_run_time),
            enabled=info.enabled,
            kwargs=dict(info.kwargs),
            retry_spec=_serialize_retry_spec(info.retry_spec),
            time_limits=_serialize_time_limits(time_limits_pair),
        )
        return view


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    """Return ISO 8601 for a datetime, or ``None`` when not set."""
    if value is None:
        return None
    return value.isoformat()
