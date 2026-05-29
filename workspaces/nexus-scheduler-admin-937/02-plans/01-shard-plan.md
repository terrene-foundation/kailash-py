# 02 — Shard Plan (#937)

Per `autonomous-execution.md` § Per-Session Capacity Budget. Work holds ~4
invariants (path/verb correctness, actor-from-JWT-identity, exception→status
mapping, role-guard placement), ~2 call-graph hops.

## Shards

- **S1 — Handler module + route wiring** (~150–250 LOC load-bearing)
  `nexus/admin/__init__.py` + `nexus/admin/scheduler.py`: `register_scheduler_admin(app, admin, *, role)`
  registering 6 routes via `register_endpoint`; `CronUpdate` model; 6 handler
  closures with `{id}`/body/`actor=user.user_id` extraction + exception mapping.
  Value-anchor: AC1+AC2 (the routes ops actually call) per issue #937 body.

- **S2 — Auth + error-handler wiring** (~80–150 LOC load-bearing)
  `Depends(RequireRole(role))` on each route + the `NexusError`→HTTP exception
  handler (resolves D3). Scope depends on D3 decision (admin-module-local vs
  transport-level fix). Value-anchor: AC5 (status convention) per issue #937 body.

- **S3 — Tier-2 tests** (real Nexus app + real HTTP client + real WorkflowScheduler,
  NO mocks per `rules/testing.md`)
  Round-trip list→get→disable→enable→update-cron→delete + 401/403/404/400 cases;
  assert recorded `actor` == JWT subject; drive a real schedule so the facade
  isn't orphan-wired (observe disabled state after PATCH).
  Value-anchor: AC3 (Tier-2 round-trip) per issue #937 body.

## Sequencing

S1+S2 may be ONE PR if D3 = "scope to admin module". If D3 = "fix transport",
S2 becomes a separate transport PR (broader blast radius). S3 always follows S1+S2.

## Blocked on user decisions (D2, D3, D5) — see analysis § Decisions
