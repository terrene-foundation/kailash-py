---
skill: handler-status-codes
description: "Opinionated HTTP status-code selection for Nexus handlers and middleware. Use when asking 'what status code', '500 vs 503', 'upstream error mapping', '429 vs 503', 'Bedrock throttling', 'LLM provider 5xx', 'NexusError mapping', or 'why is my 502 showing up as 500'."
priority: HIGH
tags:
  [
    nexus,
    http,
    status-codes,
    error-handling,
    llm-deployment,
    upstream,
    observability,
  ]
---

# Handler Status Codes

Opinionated guidance for choosing correct HTTP status codes in Nexus handlers, middleware, and upstream error adapters. Examples target the Python kailash-nexus binding; the principle applies identically across language SDKs.

## Scope

- `kailash-nexus` handlers, middleware, and channel adapters
- Downstream consumers writing custom handlers, guards, and upstream adapters
- LLM deployment-surface adapters that surface upstream provider failures through Nexus

## The Hard Rule

**5xx = US. 502 / 503 / 504 = UPSTREAM.**

Never map an upstream provider's 5xx to your own 500. The operator staring at a dashboard at 03:00 must be able to tell, from status code alone, whether **their code is broken** or **their provider is degraded**. Collapsing both into 500 is the single most common cause of misdirected on-call pages.

- 500 — **our bug**: unhandled exception, `KeyError` on a `None`, config error that should have been caught at startup.
- 502 — **upstream spoke garbage**: LLM returned a response body that did not parse, MCP peer sent an invalid JSON-RPC frame, DB driver returned a corrupt row.
- 503 — **upstream is down or we cannot reach it**: connection refused, pool exhausted, circuit breaker open, MCP transport closed.
- 504 — **upstream exceeded our timeout budget**: provider is alive but slow past the deadline.

## Decision Table

| Failure class                                      | Status  | Example                                                                                 |
| -------------------------------------------------- | ------- | --------------------------------------------------------------------------------------- |
| Validation / malformed input                       | **400** | `InvalidInput`, `MissingParam`, `Serialization` errors                                  |
| Missing / invalid auth credentials                 | **401** | custom (auth plugin surface)                                                            |
| Authenticated but not authorized                   | **403** | RBAC role rejection                                                                     |
| Resource not found                                 | **404** | `HandlerNotFound`                                                                       |
| Method not allowed                                 | **405** | routing                                                                                 |
| Duplicate / conflict                               | **409** | `DuplicateHandler`, `RouteConflict`                                                     |
| Rate-limited (by us OR surfaced from upstream)     | **429** | rate-limit middleware, Bedrock `ThrottlingException`                                    |
| **Unhandled internal bug (ours)**                  | **500** | `Internal`, `ConfigError`, `BindError`, `PluginError`, `ExecutionError` truly our fault |
| Upstream returned malformed / unparseable response | **502** | LLM body failed JSON decode, MCP frame invalid                                          |
| Upstream temporarily unavailable / dependency down | **503** | DB pool exhausted, LLM 5xx, MCP transport closed                                        |
| Upstream exceeded our timeout budget               | **504** | timeout elapsed on outbound call                                                        |

When the underlying error originated from an upstream failure (LLM provider, DB, MCP peer), the handler MUST re-classify before returning — see § "Examples" below.

## LLM Deployment Surface Example

LLM deployment abstractions surface provider errors through Nexus handlers. The mapping is non-negotiable:

| Upstream signal                                               | Status                                                                            |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Bedrock `ThrottlingException` (HTTP 400, body `__type` field) | **429**                                                                           |
| Anthropic / OpenAI HTTP 429                                   | **429**                                                                           |
| Bedrock / OpenAI / Anthropic HTTP 502 / 503 / 504             | **503**                                                                           |
| Provider timeout                                              | **504**                                                                           |
| Provider body failed JSON deserialize                         | **502**                                                                           |
| Auth missing from environment (our config)                    | **500**                                                                           |
| Auth token expired after refresh attempt failed upstream      | **503**                                                                           |
| Provider returned `InvalidCredentials`                        | **502** (provider disagrees with our config — upstream's answer, not a local bug) |

**Why the Bedrock-throttling-as-400 case matters:** Bedrock signals rate-limit by returning **HTTP 400** with a `ThrottlingException` type in the body, not HTTP 429. A naive adapter that relays the upstream status to the client emits 400, so the caller cannot implement standard `Retry-After`-style backoff. The deployment layer MUST inspect the body and upgrade to **429**.

## Observability Tie-In

Per `rules/observability.md` § 1 (Endpoints — entry / exit / error) and § 2 (Integration Points — intent + result + duration), every **5xx response** from a Nexus handler MUST emit a WARN log line with at least these fields (auth-header content MUST be pre-masked per Rule 8 before inclusion):

| Field             | Meaning                                                |
| ----------------- | ------------------------------------------------------ |
| `upstream_status` | The status code returned by the upstream (if any)      |
| `upstream_reason` | The upstream's error code / body fragment (masked)     |
| `our_status`      | What we returned to the caller (500 / 502 / 503 / 504) |
| `request_id`      | Correlation ID per `rules/observability.md` § MUST 2   |

Without `upstream_status`, an operator cannot distinguish "our 500 (bug in config loader)" from "their 503 that we correctly surfaced as 503". The field is what makes the Hard Rule auditable.

```python
logger.warning(
    "nexus.handler.upstream_degraded",
    request_id=req_id,
    our_status=503,
    upstream_status=502,
    upstream_reason="bedrock.ServiceUnavailable",
)
```

## Examples (Python kailash-nexus binding)

### DO — re-classify an upstream failure before returning

```python
from nexus import App, Response

app = App()

@app.handler("complete")
async def completion_handler(req):
    request_id = req.headers.get("x-request-id")
    try:
        return await deployment.complete(req.body)
    except LlmThrottled as e:
        # Bedrock ThrottlingException arrived as upstream-400; we correctly return 429.
        logger.warning(
            "nexus.handler.rate_limited",
            request_id=request_id,
            our_status=429,
            upstream_status=400,
            upstream_reason="bedrock.ThrottlingException",
        )
        return Response(
            status=429,
            headers={"retry-after": str(e.retry_after_seconds)},
            body={"error": "rate limited by upstream", "code": "UPSTREAM_THROTTLE"},
        )
    except LlmUpstream5xx as e:
        logger.warning(
            "nexus.handler.upstream_degraded",
            request_id=request_id,
            our_status=503,
            upstream_status=e.status,
            upstream_reason=e.body_fragment,
        )
        return Response(status=503, body={"error": "upstream unavailable"})
    except LlmTimeout:
        logger.warning(
            "nexus.handler.upstream_timeout",
            request_id=request_id,
            our_status=504,
        )
        return Response(status=504, body={"error": "upstream timeout"})
    except LlmMalformedResponse as e:
        logger.warning(
            "nexus.handler.upstream_malformed",
            request_id=request_id,
            our_status=502,
            upstream_reason=str(e),
        )
        return Response(status=502, body={"error": "upstream returned malformed response"})
    except AuthMissingError:
        # Our env loader found no credentials — operator config is broken.
        logger.error(
            "nexus.handler.config_error",
            request_id=request_id,
            our_status=500,
        )
        return Response(status=500, body={"error": "LLM auth not configured"})
```

### DO NOT — collapse every upstream error to 500

```python
@app.handler("complete")
async def completion_handler_bad(req):
    try:
        return await deployment.complete(req.body)
    except Exception as e:
        # Bedrock throttling -> 500. Bedrock 503 -> 500. Timeout -> 500.
        # Operator cannot tell "our bug" from "their outage" from "backoff needed".
        return Response(status=500, body={"error": str(e)})
```

### DO — surface 429 from a rate-limit middleware with `Retry-After`

```python
# kailash-nexus's built-in rate-limit middleware does this correctly:
#   HTTP 429 + retry-after: 60 + body { "error": "rate limit exceeded" }
# Custom rate limits MUST match the same contract.
```

## Anti-Pattern: The `test.skip(status >= 500)` Trap

A test suite that skips any assertion whose observed status is ≥ 500 turns this entire rule into a no-op. The pattern shows up as:

```python
# DO NOT
async def test_completion_returns_429_on_throttle():
    resp = await client.post("/complete", json=throttle_request)
    if resp.status_code >= 500:
        pytest.skip("test environment is flaky")  # false; we are hiding a bug
    assert resp.status_code == 429
```

Every skip on status ≥ 500 is a silent confession that the handler is returning 500 when it should return 429 / 502 / 503 / 504. The skip hides the very violation this skill exists to prevent.

See **`.claude/skills/test-skip-discipline/SKILL.md`** for the full rule on when skips are and are not acceptable.

## Relationship

- `rules/observability.md` § 2 (Integration Points) + Rule 8 (Mask HTTP Auth Headers) — 5xx responses MUST log `upstream_status` + `upstream_reason` with any auth-header content pre-masked.
- `rules/llm-auth-strategy-hygiene.md` (where present) — auth error variants and their correct status-code mapping (Missing → 500; provider rejection → 502 / 503).
- `.claude/skills/03-nexus/nexus-essential-patterns.md` — where rate-limit (429) and body-limit middleware sit in the request pipeline.
- `.claude/skills/03-nexus/nexus-troubleshooting.md` — operator-side debugging once the status code is correct.

<!-- Trigger Keywords: HTTP status code, 500 vs 503, 502 vs 503, 429 rate limit, Bedrock throttling, LLM upstream error, NexusError mapping, upstream_status, upstream_reason, Retry-After, ThrottlingException, AuthError Missing, handler error mapping, Gateway Timeout, Bad Gateway, Service Unavailable -->
