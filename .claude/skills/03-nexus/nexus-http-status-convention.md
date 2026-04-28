# Nexus HTTP Error Response Convention

Catalog of HTTP status codes used by Nexus handlers, with example error messages and the SDK's canonical error-code identifier per status. The body-shape contract itself is enforced by `rules/nexus-http-status-convention.md` — this skill is the quick-reference catalog that companion rule points back to.

## The Shape (Reference)

Every 4xx and 5xx response carries a JSON body of exactly this shape, produced by the SDK's `NexusError.into_response()` — never hand-rolled by handler code:

```json
{
  "error": "<human-readable message, one sentence>",
  "code":  "<SCREAMING_SNAKE_CASE error classifier>"
}
```

- `error` — operator-visible description. For 4xx it's the `NexusError` message. For 5xx it's a fixed safe string (e.g. `"internal server error"`); the raw error goes to server logs only.
- `code` — stable error-class identifier that downstream consumers (AgentUI banners, SRE dashboards, retry middleware, byte-diff tests) key on. **Never** localize it; **never** vary it per call.

For the MUST clauses (handler return primitives, upstream-vs-internal status discrimination, anti-patterns), see `rules/nexus-http-status-convention.md`. This skill covers the catalog + deviation cases only.

## Status Code Catalog

| Status | `code` (example)         | Meaning                                                  | Example `error` message                                   |
| ------ | ------------------------ | -------------------------------------------------------- | --------------------------------------------------------- |
| 400    | `INVALID_INPUT`          | Validation error — payload parsed but values invalid     | `"policy.type must be one of ['rbac', 'abac', 'custom']"` |
| 401    | `UNAUTHENTICATED`        | Authentication required or failed                        | `"missing bearer token"`                                  |
| 403    | `FORBIDDEN`              | Authenticated but not authorized                         | `"clearance=Public cannot read SECRET"`                   |
| 404    | `NOT_FOUND`              | Resource does not exist                                  | `"model 'User' not found"`                                |
| 409    | `CONFLICT`               | Conflict — write would violate an invariant              | `"tenant_id 'acme' already has a default policy"`         |
| 413    | `PAYLOAD_TOO_LARGE`      | Payload too large                                        | `"request body exceeds 1 MiB limit"`                      |
| 422    | `UNPROCESSABLE_ENTITY`   | Semantic validation passed parse but failed domain rules | `"migration 0043 requires force_drop=True"`               |
| 429    | `RATE_LIMIT_EXCEEDED`    | Rate limited                                             | `"too many requests; retry after 5s"`                     |
| 500    | `INTERNAL_ERROR`         | Internal error — handler crashed                         | `"internal server error"` (no stack leak)                 |
| 502    | `UPSTREAM_FAILED`        | Upstream service returned bad data                       | `"upstream kaizen service unavailable"`                   |
| 503    | `SERVICE_UNAVAILABLE`    | Service temporarily unavailable                          | `"database pool exhausted; retry"`                        |
| 504    | `UPSTREAM_TIMEOUT`       | Upstream timed out                                       | `"llm upstream timed out"`                                |

The exact `code` strings come from the SDK's `NexusError.error_code()` method — when adding a new variant in the SDK, update `status_code()` and `error_code()` in the same commit (per the rule's MUST NOT list). Some `code` strings used in production source: `INTERNAL_ERROR`, `INVALID_INPUT`, `UNAUTHENTICATED`, `FORBIDDEN`, `RATE_LIMIT_EXCEEDED`, `CSRF_REJECTED`, `UPSTREAM_FAILED`, `UPSTREAM_TIMEOUT`.

## Examples (Each Status)

### 400 — Validation

```python
from nexus import App
from nexus.errors import NexusHandlerError

app = App()

@app.handler_extract("/policies")
async def create_policy(body: JsonBody) -> dict:
    if not isinstance(body, dict):
        raise NexusHandlerError(
            status_code=400,
            body={"error": "policy payload must be a JSON object", "code": "INVALID_INPUT"},
        )
    if body.get("type") not in ("rbac", "abac", "custom"):
        raise NexusHandlerError(
            status_code=400,
            body={
                "error": "policy.type must be one of ['rbac', 'abac', 'custom']",
                "code": "INVALID_INPUT",
            },
        )
    ...
```

Response:

```json
{
  "error": "policy.type must be one of ['rbac', 'abac', 'custom']",
  "code":  "INVALID_INPUT"
}
```

### 404 — Not Found

```python
@app.handler_extract("/models/{name}")
async def get_model(name: PathParam[str]) -> dict:
    model = db.express.read_model(name)
    if model is None:
        raise NexusHandlerError(
            status_code=404,
            body={"error": f"model '{name}' not found", "code": "NOT_FOUND"},
        )
    return model
```

Response:

```json
{ "error": "model 'User' not found", "code": "NOT_FOUND" }
```

### 413 — Payload Too Large

```json
{ "error": "request body exceeds 1048576 byte limit", "code": "PAYLOAD_TOO_LARGE" }
```

### 429 — Rate Limited

```json
{ "error": "rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED" }
```

Include a `Retry-After: 5` header on 429 responses where the delay is deterministic.

### 502 vs 504 — Upstream Disambiguation

```python
# Upstream returned a malformed response → 502
raise NexusHandlerError(
    status_code=502,
    body={"error": "llm upstream returned malformed JSON", "code": "UPSTREAM_FAILED"},
)

# Upstream did not respond in time → 504
raise NexusHandlerError(
    status_code=504,
    body={"error": "llm upstream timed out", "code": "UPSTREAM_TIMEOUT"},
)
```

Per the rule, never collapse upstream degradation into 500 — operators page on 500 ≠ 502/504.

## What Belongs In Logs Vs The Response

```python
import tracing

try:
    result = call_upstream()
except UpstreamException as exc:
    tracing.error(f"upstream failed: {exc}", extra={"trace_id": ctx.trace_id})  # logs
    raise NexusHandlerError(
        status_code=502,
        body={"error": "upstream temporarily unavailable", "code": "UPSTREAM_FAILED"},  # response
    )
```

Logs get the stack trace and full exception. Clients get the safe message + stable code. **Never echo credentials, tokens, or internal stack frames into the response body** (per `rules/security.md`).

## Testing The Convention

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_missing_model_returns_404(client: AsyncClient):
    response = await client.get("/models/DoesNotExist")
    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"error", "code"}
    assert body["code"] == "NOT_FOUND"
    assert "not found" in body["error"]
```

A repo-wide byte-diff test on this body shape is the cheap structural defense against drift — see the rule's "Shape Regression" guidance.

## When To Deviate

- **Streaming endpoints** (SSE / WebSockets): errors mid-stream use the protocol's frame shape (SSE `event: error`, WS close frame with reason), not the JSON body shape.
- **OpenAPI-first endpoints** generated from an external spec: follow the spec, note the deviation in the handler docstring.
- **K8s liveness/readiness probes** (`/healthz`, `/readyz`): use `{"status": "alive"}` / `{"status": "ready"}` — that's the K8s probe protocol, not an error response. Out of scope for this convention.
- **Legacy endpoints** during migration: keep the old shape temporarily, add a deprecation header, migrate before the next major release.

## Related

- `rules/nexus-http-status-convention.md` — **the contract**: 5 MUST clauses, NexusError variant table, anti-patterns. This skill is the catalog companion.
- `skills/03-nexus/handler-status-codes.md` — full upstream-vs-internal decision table with concrete LLM/MCP/DB examples.
- `skills/03-nexus/nexus-extractors.md` — the extractor surface (`JsonBody`, `PathParam`, etc.) used in handler examples above.
- `rules/security.md` § No Secrets in Logs — applies to error messages: never echo credentials, tokens, or internal paths.
- `rules/communication.md` — the `error` message should be human-readable for frontend display, not developer-only shorthand.

Origin: gh-coc-claude-rs#51 item 3a (2026-04-17) authored the original `{error, status}` body shape as a speculative convention. Superseded at loom 2.8.18 by the actual SDK contract from kailash-rs#404 S8 (loom 2.8.17 rule), verified by red-team grep against 8 production references in `crates/kailash-nexus/src/` — every shipping `NexusError.into_response()` call uses `{"error": "...", "code": "..."}`. Skill rewritten to match SDK truth + cross-link to the contract rule.
