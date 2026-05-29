# DISCOVERY — Nexus has no NexusError→HTTP exception handler (docstring lies)

Date: 2026-05-29 | Workspace: nexus-scheduler-admin-937 | Issue: #937

## Finding

`packages/kailash-nexus/src/nexus/errors.py:28` docstring claims: "The Nexus HTTP
transport catches NexusError subclasses and returns the appropriate JSON response."
This is FALSE. `grep add_exception_handler` across `packages/kailash-nexus/src/` and
`src/kailash/servers/` returns ZERO matches. Raising `nexus.errors.NotFoundError`
from a `register_endpoint` handler today produces an unhandled-exception **500**,
not a 404.

## Impact

This is a zero-tolerance Rule 3c / Rule 4 class defect: the SDK advertises behavior
(in a docstring) the code does not perform. Any consumer that trusts the docstring
and raises `NexusError` from a FastAPI route gets 500s instead of the documented
status. #937 cannot ship a correct status convention (AC5) without resolving this.

## Disposition (pending user — this is SDK scope, not just feature scope)

Two paths:

- (a) **Scope to admin module**: `register_scheduler_admin` registers its own
  FastAPI exception handler converting `NexusError` via `to_response_dict()`.
  Bounded blast radius; makes #937 correct; leaves the docstring still-lying for
  every OTHER handler.
- (b) **Fix the transport** (per zero-tolerance Rule 4 — fix SDK bugs directly):
  wire one `add_exception_handler(NexusError, ...)` into `HTTPTransport.start` so
  the docstring becomes true for ALL handlers. Broader blast radius; correct root fix.

Recommend (b) per Rule 4 ("This is a BUILD repo. You have the source. Fix bugs
directly"), with #937's handlers as the first consumer. User decision needed because
it widens #937 from a feature PR into a feature + SDK-fix PR.

Evidence: `errors.py:28` (docstring), `errors.py:79` (`to_response_dict`),
`transports/http.py:137` (`start`, no handler install), `servers/gateway.py:19`.
