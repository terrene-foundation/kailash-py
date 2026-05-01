---
skill: nexus-extractors
description: "Extractor-based Nexus handler architecture. Use when asking about Headers, Bytes, BodyStream, Path, Query, State, Extension, TypedHeader, Json, HMAC webhooks, raw_body migration, tuple response shapes, NexusHandlerError, or migrating legacy handlers."
priority: HIGH
tags:
  [
    nexus,
    extractors,
    handlers,
    webhooks,
    migration,
    response-shape,
    status-codes,
  ]
---

# Nexus Extractors

Extractor-based handler architecture for Nexus. Replaces the legacy `ValueMap → Value` handler shape with axum-style extractors, typed response shapes, and typed HTTP errors. The surface below is the canonical Nexus extractor contract; Ruby consumers see the same shape via keyword-arg blocks.

## Quick Start (Python)

```python
import kailash
from kailash.nexus.extractors import Headers, Bytes, NexusHandlerError

app = kailash.Nexus()

async def webhook(headers: Headers, body: Bytes) -> tuple[int, dict]:
    sig = headers.get("x-signature", "")
    if not verify_hmac(sig, body):
        raise NexusHandlerError(status_code=401, body={"error": "bad signature"})
    return (200, {"ok": True})

app.handler_extract("webhook", webhook)
app.start()
```

Handlers registered via `app.handler_extract(...)` use parameter-type annotations to drive which extractors run. Each extractor pulls a specific piece of the HTTP request; the SDK runs them in declared order and short-circuits on the first rejection.

## Extractors

### `Headers` — Full header map (case-insensitive, multi-value preserving)

```python
# DO — use getall() for multi-value headers, case-insensitive get()
cookies = headers.getall("set-cookie")
auth = headers.get("authorization", "")

# DO NOT — collapse to dict, secondary values vanish
d = dict(headers)  # loses all but first Set-Cookie
```

### `Bytes` — Raw request body

```python
# DO — HMAC over the exact request bytes the provider signed
import hmac, hashlib
mac = hmac.new(secret, body, hashlib.sha256).hexdigest()

# DO NOT — re-serialize parsed JSON before HMAC
import json
mac = hmac.new(secret, json.dumps(json.loads(body)).encode(), hashlib.sha256).hexdigest()
# Re-serialized bytes never match what the provider signed.
```

### `BodyStream` — Streaming body with backpressure

Chunks pulled one at a time; bounded memory. Slow consumer throttles the reader; no internal buffer.

```python
# DO — stream to disk with bounded memory
async def upload(stream: BodyStream) -> tuple[int, dict]:
    with open("/tmp/upload", "wb") as f:
        async for chunk in stream:
            f.write(chunk)
    return (201, {"status": "ok"})

# DO NOT — declare BodyStream AND Bytes; second body-consumer sees empty
async def bad(body: Bytes, stream: BodyStream): ...  # stream will be empty
```

### `Path[T]` — URL path parameter

```python
# DO — typed path deserialization
async def user(user_id: Path[int]) -> dict:
    return find_user(user_id)

# DO NOT — parse path segments manually inside handler
async def user(request) -> dict:
    user_id = int(request.path.split('/')[-1])  # drops type checking
    return find_user(user_id)
```

### `Query[T]` — Query-string deserialization

```python
# DO — structured deserialize via typed params
from dataclasses import dataclass

@dataclass
class Filters:
    active: bool
    limit: int

async def list_users(f: Query[Filters]) -> list[dict]:
    return list_users(f)

# DO NOT — parse query string by hand
async def list_users(request) -> list[dict]:
    q = request.query_string  # drops per-field type checking
```

### `State[T]` — Shared application state

```python
# DO — access state registered at build time
async def status(pool: State[DataFlowPool]) -> dict:
    return pool.status()

# DO NOT — construct parallel state inside handler
async def status() -> dict:
    pool = DataFlowPool("...")  # new pool every request, connection leak
    return pool.status()
```

### `Extension[T]` — Per-request middleware-injected value

```python
# DO — read a value injected by auth middleware
async def profile(user: Extension[AuthedUser]) -> dict:
    return user.profile

# DO NOT — re-derive from headers when middleware already did it
async def profile(headers: Headers) -> dict:
    return decode_jwt(headers.get("authorization"))
```

### `TypedHeader[H]` — Typed single-header parser

```python
# DO — parser lives in the Header type, typed rejection
async def webhook(sig: TypedHeader[StripeSignature], body: Bytes) -> dict:
    verify(sig, body)
    return {"ok": True}

# DO NOT — parse signature format inline in every handler
async def webhook(headers: Headers, body: Bytes) -> dict:
    parts = headers.get("stripe-signature").split(',')  # parser logic drifts
```

### `Json[T]` — Typed JSON body

Malformed JSON → 400 INVALID_INPUT per the status convention.

```python
# DO — typed body, automatic deserialization
from dataclasses import dataclass

@dataclass
class Login:
    user: str
    password: str

async def login(req: Json[Login]) -> dict:
    return authenticate(req.user, req.password)

# DO NOT — accept raw bytes then deserialize inside handler
async def login(body: Bytes) -> dict:
    req = json.loads(body)  # no typed validation, no automatic 400 on malformed
    return authenticate(req["user"], req["password"])
```

## Response Shapes

### Plain dict → 200 + JSON body

```python
# DO — bare dict defaults to HTTP 200 + application/json
async def status() -> dict:
    return {"ok": True}
```

### `(status, body)` tuple → explicit status + body

```python
# DO — typed tuple return (closes the "how do I return 403?" gap)
async def denied(headers: Headers) -> tuple[int, dict]:
    return (403, {"error": "forbidden"})

# DO NOT — body-status envelope; HTTP status is 200, denial hidden in body
async def denied(headers: Headers) -> dict:
    return {"status": 403, "error": "forbidden"}
```

### `(status, headers, body)` triple → status + headers + body

```python
# DO — 303 redirect with location header
async def redirect() -> tuple[int, dict, dict]:
    return (303, {"location": "/"}, {})
```

### `None` → 204 No Content

```python
async def delete(user_id: Path[int]) -> None:
    remove_user(user_id)
    # implicit 204
```

### `NexusHandlerError` → typed HTTP error

```python
# DO — typed 403 with structured body
raise NexusHandlerError(status_code=403, body={"error": "forbidden"})

# DO NOT — return dict pretending to carry status (HTTP 200, not 403)
return {"status": 403, "error": "forbidden"}
```

## Ruby Bindings

Ruby handlers use keyword-arg blocks for parameter-name-keyed introspection:

```ruby
# DO — keyword-arg block, returns [status, body] or raises NexusHandlerError
hook = ->(headers:) { [200, { ok: true }] }
app.handler_extract("noop", hook)

# DO NOT — positional args; names lost, dispatch fails
hook = ->(h, b) { [200, { ok: true }] }
```

## Performance Notes

- `Bytes` zero-copy on the SDK side; single FFI copy to Python `bytes`.
- `BodyStream` applies backpressure — slow consumer throttles reader; no internal buffer.
- Body limits enforced once at the transport layer. `Json` / `Bytes` / `BodyStream` honor the same limit — one operator knob.

## Backward Compatibility

Legacy handlers registered via `handler()` / `endpoint()` continue to route byte-identically. Registration emits a one-shot WARN at `nexus.handler.legacy_registration`.

```python
# DO — legacy handlers still work (WARN at registration)
app.handler("greet", lambda inputs: {"msg": f"hi {inputs.get('name', '')}"})

# DO NOT — assume the magic-param shape persists past the deprecation window
def legacy(raw_body: bytes, headers: dict) -> dict: ...  # will break on removal
```

Migration: switch from `handler()` to `handler_extract()`, replace magic-param signatures with extractor-typed parameters. See the deprecation timeline in the SDK's `DEPRECATION.md`.

## Related

- `.claude/rules/nexus-http-status-convention.md` — status + body shape contract (MUST rules)
- `.claude/rules/nexus-webhook-hmac.md` — HMAC verification via `Headers` + `Bytes` + `TypedHeader`
- `.claude/skills/03-nexus/handler-status-codes.md` — 500 vs 502/503/504 decision table
- `.claude/skills/03-nexus/nexus-http-status-convention.md` — reference patterns, examples per status code

Origin: 2026-04-18 → 2026-04-19 extractor-surface design; skill authored at the end of that arc.
