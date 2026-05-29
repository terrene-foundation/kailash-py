# 01 — Nexus Scheduler-Admin Design Analysis (#937)

Source: nexus-specialist design pass (2026-05-29), all API claims verified against
`packages/kailash-nexus/src/` at file:line.

## Wrapped class (exists, merged PR #936)

`kailash.runtime.scheduler_admin.SchedulerAdminAPI` — 6 methods map 1:1 to the
6 routes. `list_schedules`, `get_schedule` (raises `ScheduleNotFound`),
`disable_schedule`/`enable_schedule`/`update_cron`/`delete_schedule` (keyword-only
`actor`; `update_cron` raises `ValueError` for non-cron/invalid). `ScheduleAdminView`
is a JSON-friendly `dict` subclass.

## Verified Nexus API surface (corrects the issue's assumptions)

- **Route registration**: use `app.register_endpoint(path, methods, handler)`
  (`core.py:1533`) — real FastAPI routes with `{id}` path params + HTTP verbs.
  NOT `@app.handler` (that auto-derives a workflow route from the handler _name_,
  cannot express custom paths/verbs).
- **Auth**: `Depends(nexus.auth.dependencies.RequireRole("scheduler-admin"))`
  (`auth/dependencies.py:51`) on each route — the FastAPI-dependency RequireRole,
  NOT `AuthGuard.RequireRole` (which only fires inside the `@app.handler` wrapper).
  No/invalid JWT → 401 (`get_current_user`, `auth/dependencies.py:29`); wrong role
  → 403 (`auth/dependencies.py:75`).
- **Identity**: `user: AuthenticatedUser = Depends(get_current_user)`; `user.user_id`
  is the JWT `sub` claim (`trust/auth/models.py:24`). `actor` = `user.user_id`,
  NEVER a request-body field (satisfies AC by construction).
- **Errors (Python reality)**: class hierarchy in `nexus/errors.py` —
  `NotFoundError` (404), `ValidationError` (400), `UnauthorizedError` (401),
  `ForbiddenError` (403). Body shape `{"error": <error_code>, "detail": <message>}`.

## Handler module design

`packages/kailash-nexus/src/nexus/admin/scheduler.py` +
`register_scheduler_admin(app, admin, *, role="scheduler-admin")` — factory that
calls `register_endpoint` six times (each handler closes over the live `admin`).

| Route                                 | Maps to                                            | Exception mapping                        |
| ------------------------------------- | -------------------------------------------------- | ---------------------------------------- |
| `GET /admin/schedules`                | `list_schedules()`                                 | —                                        |
| `GET /admin/schedules/{id}`           | `get_schedule(id)`                                 | `ScheduleNotFound→NotFoundError`         |
| `PATCH /admin/schedules/{id}/disable` | `disable_schedule(id, actor=user.user_id)`         | `ScheduleNotFound→404`                   |
| `PATCH /admin/schedules/{id}/enable`  | `enable_schedule(id, actor=...)`                   | `ScheduleNotFound→404`                   |
| `PATCH /admin/schedules/{id}/cron`    | `update_cron(id, body.cron_expression, actor=...)` | `ScheduleNotFound→404`, `ValueError→400` |
| `DELETE /admin/schedules/{id}`        | `delete_schedule(id, actor=...)` → 204             | `ScheduleNotFound→404`                   |

`CronUpdate` Pydantic model `{cron_expression: str}` for the cron-body route.

## Three divergences from the issue (decisions needed — see § Decisions)

- **D1 (resolved by design)**: `@app.handler` is wrong → use `register_endpoint`.
- **D2 (user decision)**: `rules/nexus-http-status-convention.md` FROZEN taxonomy
  (`NexusError.InvalidInput`/`HandlerNotFound`, body `{"error","code"}`) is the
  RUST SDK shape — does NOT exist in the Python package. Python uses the class
  hierarchy above with body `{"error","detail"}`. Cross-SDK divergence.
- **D3 (user decision)**: NO `add_exception_handler` exists in kailash-nexus or
  kailash.servers (grep: zero matches) — yet `errors.py:28` docstring claims "the
  HTTP transport catches NexusError subclasses". Raising `NotFoundError` from a
  `register_endpoint` handler TODAY → unhandled 500, not 404. The mapping must be
  wired (transport-level fix, or scoped exception handler in the admin module).
- **D5 (minor)**: OpenAPI for `register_endpoint` routes comes from FastAPI, not
  Nexus's generator; `ScheduleAdminView` (dict subclass) → generic object unless
  explicit `response_model` Pydantic models are authored.

## Risks

- D6: `register_scheduler_admin` MUST run on an app with `enable_http_transport=True`
  and BEFORE `app.start()` (registrations queue, `transports/http.py:167`).
- Facade risk (`*API` class): Tier-2 test MUST drive a real schedule through
  `WorkflowScheduler` and observe an externally-visible effect (disabled state
  after PATCH), not just assert 200 — per orphan-detection.md.
