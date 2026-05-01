---
priority: 10
scope: path-scoped
paths:
  - "**/nexus/**"
  - "**/*handler*"
  - "**/*endpoint*"
---

# Nexus HTTP Status Convention


<!-- slot:neutral-body -->

Every response a Nexus handler emits carries an HTTP status code that operators read as a triage signal at 03:00. The status taxonomy below is a contract: a handler returning the wrong code sends the operator to the wrong on-call page. This rule freezes the mapping from `NexusError` variants and handler-side errors to HTTP status codes, plus the JSON error body shape that rides on every 4xx/5xx response.

The source of truth is the SDK `NexusError` / `NexusApiError` type: its `status_code()` method defines the variant → HTTP mapping and its `into_response()` method defines the JSON body shape. Documents, skills, downstream templates, and new handler code MUST match the SDK shape bit-for-bit.

## MUST Rules

### 1. `NexusError` Variant → HTTP Status Mapping Is Frozen

Every mapping below is the canonical taxonomy. Changing any row requires an SDK version bump + migration guide, not a spot edit.

| `NexusError` variant | HTTP status | Error code (JSON body) |
| -------------------- | ----------- | ---------------------- |
| `HandlerNotFound`    | 404         | `HANDLER_NOT_FOUND`    |
| `InvalidInput`       | 400         | `INVALID_INPUT`        |
| `MissingParam`       | 400         | `MISSING_PARAM`        |
| `DuplicateHandler`   | 409         | `DUPLICATE_HANDLER`    |
| `Serialization`      | 400         | `SERIALIZATION_ERROR`  |
| `McpError`           | 400         | `MCP_ERROR`            |
| `ExecutionError`     | 500         | `EXECUTION_ERROR`      |
| `BindError`          | 500         | `BIND_ERROR`           |
| `PluginError`        | 500         | `PLUGIN_ERROR`         |
| `ConfigError`        | 500         | `CONFIG_ERROR`         |
| `RouteConflict`      | 409         | `ROUTE_CONFLICT`       |
| `Internal`           | 500         | `INTERNAL_ERROR`       |

```python
# DO — raise the typed error; SDK maps variant to status
from kailash.nexus import NexusError
raise NexusError.InvalidInput("payload is not an object")  # → 400 INVALID_INPUT

# DO NOT — invent a new mapping at the handler layer
return (422, {"error": "bad input"})  # drifts from the SDK taxonomy
```

**Why:** Once the taxonomy drifts between handlers and the SDK's error type, operators lose the "status-alone tells me which class of failure" property. The mapping is intentionally narrow so that every future addition goes through one file and shows up in every binding at once.

### 2. Canonical JSON Error Body Shape Is Bit-For-Bit Preserved

Every 4xx and 5xx response MUST carry a JSON body of exactly this shape:

```json
{ "error": "<message>", "code": "<CODE>" }
```

- `error` — operator-visible description. For 4xx it is the `NexusError` message. For 5xx it is the fixed string `"internal server error"` — the raw error is written to server logs (e.g. `tracing::error!`), never to the response body.
- `code` — one of the `Error code` values from Rule 1. Fixed identifiers, upper-snake-case, stable across releases.

```python
# DO — body shape produced by the SDK, not hand-rolled
raise NexusError.InvalidInput("not an object")
# Response: 400, body = {"error":"invalid input: not an object","code":"INVALID_INPUT"}

# DO NOT — hand-roll the body shape on the handler side
return (400, {"status": "error", "reason": "not an object"})  # wrong field names
```

**BLOCKED rationalizations:**

- "My handler needs an extra field, I'll just add it"
- "The frontend expects `message` instead of `error`"
- "Wrapping `error` in a `details` object is cleaner"

**Why:** The body shape is load-bearing across every Nexus consumer: downstream tests byte-match it, binding tests assert on it, AgentUI error banners key on `code`, and SRE dashboards filter by `code`. Changing the shape on one handler silently breaks every one of those consumers.

### 3. Hard Rule — `5xx = Us, 502/503/504 = Upstream`

Never map an upstream provider's 5xx to your own 500. The operator staring at a dashboard at 03:00 MUST be able to tell, from status code alone, whether **their code is broken** or **their upstream is degraded**. The full decision table lives in `skills/03-nexus/handler-status-codes.md`; the short form:

- **500** — our bug: unhandled exception, null-deref, `ConfigError` that should have been caught at startup
- **502** — upstream spoke garbage (LLM body failed JSON decode, MCP peer sent invalid frame)
- **503** — upstream is down or unreachable (DB pool exhausted, LLM 5xx, circuit breaker open)
- **504** — upstream exceeded our timeout budget

```python
# DO — re-classify upstream failures before returning
except LlmUpstream5xxError:
    return (503, {"error": "llm upstream unavailable", "code": "UPSTREAM_UNAVAILABLE"})
except LlmTimeoutError:
    return (504, {"error": "llm upstream timed out", "code": "UPSTREAM_TIMEOUT"})

# DO NOT — collapse every upstream error to 500
except Exception as e:
    raise NexusError.Internal(str(e))  # loses upstream classification
```

**Why:** Collapsing upstream degradation into 500 is the single most common cause of misdirected on-call pages — SREs get paged for "our bug" when the upstream is the actual fault. The handler-status-codes skill documents the full decision table; this rule anchors it in the status-convention MUST list.

### 4. Extractor-Based Handlers Return Typed Status

Handlers registered via the extractor-based dispatch path MUST return status through one of:

1. **Typed tuple** — `(status, body)` where body is a dict or `NexusResponse`-compatible value.
2. **`NexusHandlerError`** — raise a typed error carrying `status_code: int` + `body: dict | str`.
3. **Plain body** — bare dict / string defaults to HTTP 200.

```python
# DO — typed tuple return
from kailash.nexus.extractors import Headers

async def restricted(headers: Headers) -> tuple[int, dict]:
    if not headers.get("authorization"):
        return (403, {"error": "forbidden"})   # → HTTP 403
    return (200, {"ok": True})

# DO — typed error raise
from kailash.nexus.extractors import NexusHandlerError, Bytes

async def validate(body: Bytes) -> dict:
    if len(body) == 0:
        raise NexusHandlerError(status_code=422, body={"reason": "empty body"})
    return {"ok": True}

# DO NOT — body-status envelope on the extractor path
async def legacy_envelope(headers: Headers) -> dict:
    return {"status": 403, "error": "forbidden"}   # ← HTTP 200, not 403
```

**Why:** The body-status envelope is a common anti-pattern: it looks like a status code to the developer but is just a dict to HTTP, so the actual response is 200 with the "error" in the body. The tuple + `NexusHandlerError` primitives close that gap. See `skills/03-nexus/nexus-extractors.md` for the full extractor surface.

### 5. Legacy Handlers Map `InvalidInput → 400 INVALID_INPUT`

Pre-extractor handlers registered via the legacy `handler()` / `endpoint()` path continue to route through `NexusError`. When such a handler raises a Python `ValueError` / `TypeError` or returns a `NexusError.InvalidInput`, the response MUST be HTTP **400** with the JSON body `{"error": "...", "code": "INVALID_INPUT"}`.

Legacy handlers cannot produce a 403 or 422 without migrating to the extractor path (Rule 4).

```python
# DO — legacy handler raising ValueError → 400 INVALID_INPUT (correct for 4xx input errors)
def legacy(inputs: dict) -> dict:
    if "name" not in inputs:
        raise ValueError("name required")   # → 400 {"error":"...","code":"INVALID_INPUT"}
    return {"greeting": f"hi {inputs['name']}"}

# DO NOT — assume legacy path can emit 403
def legacy_auth(inputs: dict) -> dict:
    if not inputs.get("token"):
        raise PermissionError("forbidden")   # ← still maps to 400, NOT 403
    return {"ok": True}
# Fix: migrate to handler_extract + NexusHandlerError(status_code=403, body=...).
```

**Why:** Shipping two contradictory status-convention stories (legacy + extractor) confuses downstream teams who grep for "how do I return 403." The rule pins the legacy contract — it stays at 400 — and directs the fix upward to the extractor path.

## MUST NOT

- Add a new `NexusError` variant without updating both `status_code()` and `error_code()` in the SDK in the same commit

**Why:** A variant with no status mapping falls through to the match-exhaustiveness check at compile time (good), but a variant added to only `status_code()` without `error_code()` ships a response with a compiler-default error code that downstream dashboards cannot key on.

- Hand-roll the JSON error body shape in a handler

**Why:** Rule 2 — every 4xx/5xx body MUST come from the SDK's `NexusApiError` response construction. Hand-rolling drifts from the shape-regression test and silently breaks consumers.

- Map an upstream 5xx to your own 500

**Why:** Rule 3 — collapsing upstream into 500 destroys the operator's ability to distinguish "our bug" from "their outage."

## Related

- `skills/03-nexus/nexus-http-status-convention.md` — status/body reference patterns, examples of each status code class, deviation cases (streaming, OpenAPI-first, legacy migration).
- `skills/03-nexus/nexus-extractors.md` — extractor-based handler architecture, typed tuple returns, `NexusHandlerError` primitives.
- `skills/03-nexus/handler-status-codes.md` — 500 vs 502/503/504 decision table.
- `rules/nexus-webhook-hmac.md` — HMAC verification patterns for webhook handlers.

Origin: 2026-04-19 — Nexus extractor architecture rework codified the status taxonomy as a frozen contract.

<!-- /slot:neutral-body -->
