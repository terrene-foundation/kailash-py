# DISCOVERY — Nexus error taxonomy: Python ≠ the frozen rule (cross-SDK)

Date: 2026-05-29 | Workspace: nexus-scheduler-admin-937 | Issue: #937

## Finding

`.claude/rules/nexus-http-status-convention.md` declares a FROZEN error taxonomy
(`NexusError.InvalidInput`, `HandlerNotFound`, `RouteConflict`; body
`{"error": <msg>, "code": <CODE>}`; `status_code()` / `into_response()` methods)
and scopes it to `**/nexus/**` (which includes the Python package). But that shape
is the **Rust SDK's**. The Python `packages/kailash-nexus/src/nexus/errors.py` uses
a CLASS HIERARCHY (`NotFoundError`/`ValidationError`/`ForbiddenError`/...) with body
`{"error": <error_code>, "detail": <message>}` (`errors.py:79-90`). The two shapes
differ in both the type model (enum-variant vs class) and the JSON body field names.

## Impact

The rule's MUST-1 mapping table cannot be followed literally in Python. Any Python
handler "raising typed NexusError per the rule" would be coding against a Rust API.

## Disposition (pending user)

For #937: follow the Python class hierarchy as-is (`ScheduleNotFound→NotFoundError`,
`ValueError→ValidationError`). Separately: file a cross-SDK issue per
`rules/cross-sdk-inspection.md` — either the rule is Rust-only and mis-scoped to
Python paths, or the Python package must align to the frozen shape. This is a
WHAT-decision for the user (analyze gate), not an autonomous pick.

Evidence: `errors.py:53,79,103,122,161,181`; rule MUST-1 table.
