# Nexus Webhook HMAC — Raw-Body Audit (Issue #497)

**Cross-SDK origin:** kailash-rs#404 (D1 — `axum::extract::Json` consumes the
raw body before the handler runs; HMAC over re-serialized JSON is structurally
broken). This audit determines whether kailash-py has the same gap.

**Rule loadability:** confirmed — `/Users/esperie/repos/loom/.claude/rules/nexus-webhook-hmac.md` exists and is loaded above.

## Per-Surface Table

| #   | Surface (file:line)                                                                                                                                                                           | Handler signature received from caller                                                                                                   | Raw bytes?                                                  | Full headers?              | `Request` object?                                         | Verdict                                                                                                                                                                      |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `transports/webhook.py:329-372` `WebhookTransport.receive(handler_name, payload, payload_bytes, signature, idempotency_key)` then `func(**payload)` at L404/407                               | Pre-parsed `payload` dict only — `payload_bytes` is consumed inside `verify_signature` at L371 and is NOT forwarded to the user handler  | Internal only                                               | No                         | No                                                        | **WORKAROUND-AVAILABLE.** HMAC is verified internally before dispatch. User handler intentionally receives parsed JSON only. This is the supported signed-webhook path.      |
| 2a  | `transports/http.py:172-187` workflow registration via `gateway.register_workflow(name, workflow)` → `WorkflowAPI` mounted at `/workflows/{name}` (`src/kailash/api/workflow_api.py:211-245`) | `WorkflowRequest(**json_data)` — Pydantic-parsed JSON; `request.body()` is awaited then discarded at L218                                | **No (discarded)**                                          | No (only `request.json()`) | No (consumed inside the WorkflowAPI wrapper, not exposed) | **NOT-SUPPORTED for HMAC.** This is the gap. Workflows registered via `Nexus.register()` cannot verify provider-signed HMAC inside the workflow.                             |
| 2b  | `transports/http.py:246-253` `register_endpoint(path, methods, func, **kwargs)` → user-supplied FastAPI handler attached directly via `route_func(path, **kwargs)(func)` (L304-305)           | Whatever signature the user declares — FastAPI dependency injection, so `Request`, `bytes`, `Body(...)`, `Header(...)` are all available | **Yes (if user types `body: bytes` or `request: Request`)** | Yes                        | Yes                                                       | **SUPPORTED.** Custom endpoints can extract raw bytes via FastAPI's standard mechanisms.                                                                                     |
| 3a  | `auth/jwt.py`, `auth/tenant/middleware.py`, `auth/rbac.py`, `auth/audit/middleware.py`, `trust/middleware.py`                                                                                 | Middleware reads `request.headers` and `request.state` only                                                                              | No middleware calls `await request.body()`                  | n/a                        | n/a                                                       | **No raw-body stash exists.** Workaround A from `rules/nexus-webhook-hmac.md` (middleware-stashed `request.state.raw_body`) is NOT pre-built — users must add it themselves. |
| 3b  | `middleware/cache.py`, `middleware/csrf.py`, `middleware/governance.py`, `middleware/security_headers.py`                                                                                     | Header / response transforms only                                                                                                        | No                                                          | n/a                        | n/a                                                       | Same as 3a — no raw-body capture.                                                                                                                                            |
| 4a  | `transports/websocket.py:387` `_connection_handler(websocket)`                                                                                                                                | WebSocket frames, not HTTP body                                                                                                          | n/a                                                         | n/a                        | n/a                                                       | Out of HMAC scope.                                                                                                                                                           |
| 4b  | `transports/mcp.py:148-152` `_register_workflow_tool(name, workflow)` → `async def workflow_tool(**kwargs)`                                                                                   | MCP tool kwargs, not HTTP                                                                                                                | n/a                                                         | n/a                        | n/a                                                       | Out of HMAC scope.                                                                                                                                                           |

## Final Verdict — Generic HTTP Workflow Handler HAS The Gap

`Nexus.register("name", workflow)` mounts the workflow under `WorkflowAPI`,
which calls `await request.json()` and discards the raw bytes (`workflow_api.py:218`).
Provider-signed HMAC verification (Stripe, GitHub, Twilio, Shopify, Slack)
is structurally impossible inside such a workflow because the bytes the
provider signed are gone before any node sees the payload.

**Three intended paths today:**

1. **`WebhookTransport`** (recommended, supported) — operator constructs
   `WebhookTransport(secret=...)` and calls `.receive(handler, payload, payload_bytes=..., signature=...)`. HMAC verified internally; user handler gets parsed payload. This IS the architectural decision for signed webhooks.
2. **Custom FastAPI endpoint via `app.register_endpoint(...)`** — user can
   declare `body: bytes` / `request: Request` and verify HMAC inline. Supported but un-ergonomic.
3. **Operator-supplied ASGI middleware** — Workaround A from `rules/nexus-webhook-hmac.md` works because Nexus exposes `app.add_middleware(...)`. No first-party middleware for this exists.

**Architectural decision recorded:** signed webhooks go through `WebhookTransport`, not through `Nexus.register(workflow)`. The `rules/nexus-webhook-hmac.md` workarounds (middleware / proxy verification) cover the case where users insist on using a workflow.

## Cross-SDK Alignment To kailash-rs#404

| Aspect                          | kailash-rs (#404)                               | kailash-py (this audit)                                                                                                                                       |
| ------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Generic handler raw-body access | Blocked by `axum::extract::Json` consuming body | Blocked by `WorkflowAPI.execute_workflow_root` calling `request.json()` and dropping bytes                                                                    |
| Workaround for users today      | Middleware (tower) above the Nexus router       | ASGI middleware via `Nexus.add_middleware(...)` (Starlette) — same shape                                                                                      |
| Dedicated webhook transport     | Not present                                     | **Present** — `WebhookTransport` (`packages/kailash-nexus/src/nexus/transports/webhook.py`) already exists, accepts `payload_bytes`, computes HMAC internally |
| Tracking for ergonomic fix      | #404 D1 — `NexusExtract` trait, shards S1–S8    | This issue (#497) — proposed below                                                                                                                            |

EATP D6 status: **partially aligned.** Both SDKs structurally cannot expose
raw bytes through the generic workflow handler. kailash-py is one step
ahead because it ships `WebhookTransport` for the signed-webhook case;
kailash-rs has no equivalent transport and must use the trait rework.

## Proposed Follow-Up Ticket (for #497 closure or new issue)

**Title:** `feat(nexus): expose raw request body to handlers registered via Nexus.register(workflow)`

**Body:**

> ## Context
>
> Cross-SDK alignment with esperie-enterprise/kailash-rs#404 (D1 — `axum::extract::Json` consumes raw body before handler).
>
> Audit (`workspaces/issues-492-497/04-validate/497-nexus-webhook-hmac-audit.md`) confirms kailash-py has the equivalent gap in the generic workflow path: `WorkflowAPI.execute_workflow_root` (`src/kailash/api/workflow_api.py:211-223`) calls `await request.json()` and discards raw bytes before any workflow node runs.
>
> Today, signed webhooks must go through `WebhookTransport` (which accepts `payload_bytes` and verifies HMAC internally). This is the supported architectural path and is documented in `rules/nexus-webhook-hmac.md`.
>
> ## Proposal — match kailash-rs#404 D1 ergonomics
>
> Add an opt-in handler signature that exposes (a) raw bytes, (b) full header map. Concretely either:
>
> - **Option A** — typed handler parameter (matches kailash-rs `NexusExtract` trait). Workflow nodes opt in via parameter type annotations; raw body stashed by Nexus middleware on first access.
> - **Option B** — first-party ASGI middleware (`nexus.middleware.RawBodyMiddleware`) that stashes `await request.body()` on `request.state.raw_body` for explicitly opted-in routes, exposed to workflow nodes via a context accessor.
>
> Option B is a smaller change and matches the existing `rules/nexus-webhook-hmac.md` Workaround A pattern.
>
> ## Out of scope
>
> - Replacing `WebhookTransport` — it remains the recommended path for signed webhooks from third-party providers.
>
> ## Cross-SDK
>
> - Originating: esperie-enterprise/kailash-rs#404 (shards S1–S8)
> - This is the kailash-py equivalent.
> - Label: `cross-sdk`

## Files Referenced (absolute)

- `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/transports/webhook.py` (lines 227-419)
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/transports/http.py` (lines 137-305)
- `/Users/esperie/repos/loom/kailash-py/src/kailash/api/workflow_api.py` (lines 205-245)
- `/Users/esperie/repos/loom/kailash-py/src/kailash/servers/workflow_server.py` (lines 432-468)
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/auth/*.py` (no raw-body stash)
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/trust/middleware.py` (no raw-body stash)
- `/Users/esperie/repos/loom/.claude/rules/nexus-webhook-hmac.md` (rule loadable, applies)
