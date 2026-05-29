# Brief — Expose SchedulerAdminAPI via Nexus admin panel (#937)

Source: GitHub issue #937 (follow-up to #913 / PR #936, both merged 2026-05-10).
User approved this workstream 2026-05-29.

## Goal

Wire the existing `kailash.runtime.scheduler_admin.SchedulerAdminAPI` (merged in
PR #936) into a Nexus-mediated HTTP admin panel so operators can manage workflow
schedules over HTTP instead of calling Python directly.

## Prerequisites (verified present 2026-05-29)

- `src/kailash/runtime/scheduler_admin.py::SchedulerAdminAPI` (line 167)
- `src/kailash/runtime/scheduler_admin.py::ScheduleAdminView` (line 141)
- `src/kailash/sdk_exceptions.py::ScheduleNotFound` (line 278)
- `specs/scheduling.md` §11 (Runtime Admin Surface)

The admin class is framework-agnostic by design: JSON-friendly `ScheduleAdminView`
dicts + typed `ScheduleNotFound` exceptions. This workstream is the HTTP wrapper.

## Acceptance criteria (verbatim from issue #937)

1. Nexus handlers (e.g. `packages/kailash-nexus/src/nexus/admin/scheduler.py`)
   exposing: `GET /admin/schedules`, `GET /admin/schedules/{id}`,
   `PATCH /admin/schedules/{id}/disable`, `PATCH /admin/schedules/{id}/enable`,
   `PATCH /admin/schedules/{id}/cron`, `DELETE /admin/schedules/{id}`.
2. Each handler registered via `@app.handler(...)` with
   `AuthGuard.RequireRole("scheduler-admin")` (or equivalent).
3. Tier-2 test: real Nexus app, real HTTP client, real `WorkflowScheduler` —
   round-trip a list/disable/update-cron/delete cycle through the HTTP surface.
4. OpenAPI schema for each route reflects the `ScheduleAdminView` shape.
5. Status convention: `ScheduleNotFound → 404`, `ValueError → 400`,
   missing/invalid auth → 401, missing role → 403
   (per `rules/nexus-http-status-convention.md`).
6. `rules/nexus-webhook-hmac.md` — N/A (these are NOT webhooks).

## Constraints

- Framework-first: use Nexus primitives (nexus-specialist), NOT raw FastAPI.
- NO mocking in Tier-2 tests (real Nexus app + real HTTP client + real scheduler).
- Cross-references: PR #936 (`src/kailash/runtime/scheduler_admin.py`),
  `specs/scheduling.md` §11.
