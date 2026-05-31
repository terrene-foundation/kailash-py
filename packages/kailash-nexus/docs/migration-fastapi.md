# Migrating from FastAPI to Nexus

This guide is for developers who already build HTTP services with FastAPI and
want to move handlers onto Nexus. It maps each FastAPI parity surface to its
Nexus equivalent: a ~30-line FastAPI snippet, the ~30-line Nexus equivalent, and
prose explaining the difference.

Nexus is not a FastAPI port. It is a multi-channel runtime: one handler
registration exposes the same function over HTTP, CLI, and MCP. Nexus
deliberately mirrors several FastAPI naming conventions at the parameter-extractor
surface (`Depends`, `UploadFile`, `Request`) so the migration is mostly mechanical,
but the execution model is its own — handlers are addressed by _name_, not by an
arbitrary REST verb + path, and a single registration fans out across three
channels.

## Imports

All extractor symbols live in `nexus.extractors`; the app and WebSocket
primitives live in the top-level `nexus` package:

```python
from nexus import Nexus, Connection, MessageHandler
from nexus.extractors import (
    Depends, Request, UploadFile, Multipart, Bytes, Headers, NexusHandlerError,
)
```

The shipped public surface of `nexus.extractors` is exactly:
`Depends`, `Request`, `UploadFile`, `Multipart`, `Bytes`, `Headers`,
`NexusHandlerError`, `DependencyOverrideMap`, `DependencyOverrideRuntimeMutationError`.
There is no `Body`, no `Query`, and no `register_decoder` — those are tracked as
follow-ups in section 9.

## How handlers are invoked

FastAPI binds each handler to a verb + path you choose (`@app.get("/profile")`).
Nexus registers handlers by _name_ and exposes them across all channels. Over
HTTP, an extractor-bearing handler named `me` is reached at:

```
POST /workflows/me/execute
Content-Type: application/json

{"inputs": {"name": "Alice", "greeting": "Hi"}}
```

The same `me` handler is also reachable from the Nexus CLI and as an MCP tool —
one registration, three channels. There are no bespoke `GET /profile`-style routes
to design; the channel layer derives the surface from the handler name.

---

## Section 1 — Auth via `Depends`

**FastAPI shape.**

```python
from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI()

async def get_current_user(authorization: str = Header(...)) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    user = await lookup_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return user

@app.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)) -> dict:
    return {"user_id": user["id"]}
```

**Nexus shape.**

```python
from nexus import Nexus
from nexus.extractors import Depends, Request, NexusHandlerError

app = Nexus()

async def get_current_user(request: Request) -> dict:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    user = await lookup_user(token)
    if user is None:
        raise NexusHandlerError("invalid token", status_code=401)
    return user

async def get_profile(user: dict = Depends(get_current_user)) -> dict:
    return {"user_id": user["id"]}

app.handler_extract("get_profile", get_profile)
```

**Mapping.** Same import name (`Depends`); same default-value pattern
(`param: T = Depends(callable)`). The dependency callable receives the Nexus
`Request` extractor instead of FastAPI's per-parameter `Header(...)` extractors —
read headers off `request.headers`. Auth failures raise `NexusHandlerError` with a
`status_code` rather than `HTTPException`. Registration changes from
`@app.get(path)` to the explicit `app.handler_extract(name, func)` call — Nexus is
multi-channel, so the handler is exposed by name across HTTP + CLI + MCP rather
than bound to one HTTP route.

---

## Section 2 — Typed bodies (flat-input mapping + `Bytes`)

**FastAPI shape.**

```python
from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI()

class CreateUser(BaseModel):
    name: str
    email: str

@app.post("/users")
async def create_user(body: CreateUser) -> dict:
    return {"id": body.name, "email": body.email}
```

**Nexus shape (flat-input mapping — the shipped typed-body story).**

```python
from nexus import Nexus

app = Nexus()

async def create_user(name: str, email: str) -> dict:
    # Non-extractor parameters receive HTTP-body fields by name via flat-input
    # mapping — the same semantics as register_handler. The request body
    # {"inputs": {"name": "Alice", "email": "a@example.com"}} maps name -> name,
    # email -> email.
    return {"id": name, "email": email}

app.handler_extract("create_user", create_user)
```

**Nexus shape (raw body via `Bytes` for manual decode).**

```python
import json
from nexus import Nexus
from nexus.extractors import Bytes

app = Nexus()

async def ingest(raw: Bytes) -> dict:
    # The Bytes extractor delivers the raw request body. Decode it yourself —
    # JSON, msgpack, a custom binary format, whatever the caller sent.
    payload = json.loads(raw)
    return {"received_keys": sorted(payload.keys())}

app.handler_extract("ingest", ingest)
```

**Mapping.** Nexus ships two typed-body paths today. The first — flat-input
mapping — is the everyday path: any handler parameter that is _not_ an extractor
(not `Depends`, `Request`, `UploadFile`, `Multipart`, `Bytes`, or `Headers`)
receives its value from the corresponding key in the request body's `inputs`
object, the same way `register_handler` maps inputs. Declare the fields you want
as ordinary typed parameters. The second path — the `Bytes` extractor — hands you
the raw request body so you can decode any format yourself.

Pydantic-model extraction (a single `body: CreateUser` parameter that Nexus
validates and constructs) is a deferred follow-up — see section 9. Until it ships,
prefer flat-input parameters for structured JSON and `Bytes` for formats you
parse by hand.

---

## Section 3 — Single file upload (`UploadFile`)

**FastAPI shape.**

```python
from fastapi import FastAPI, File, UploadFile

app = FastAPI()

@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    contents = await file.read()
    return {"filename": file.filename, "size": len(contents)}
```

**Nexus shape.**

```python
from nexus import Nexus
from nexus.extractors import UploadFile

app = Nexus()

MAX_SIZE = 10 * 1024 * 1024  # 10 MiB — bounded read ceiling, never unbounded

async def upload(file: UploadFile) -> dict:
    contents = await file.read(MAX_SIZE)
    return {"filename": file.filename, "size": len(contents)}

app.handler_extract("upload", upload)
```

**Mapping.** The `UploadFile` annotation _is_ the extractor — no `= File(...)`
sentinel is needed, because a typed `UploadFile` parameter is unambiguous. The
read API (`filename`, `content_type`, `read()`) mirrors FastAPI's. Cap reads with
an explicit `MAX_SIZE` ceiling rather than calling `await file.read()` unbounded;
an unbounded read is a memory-exhaustion vector. Nexus enforces a body-level cap at
the resolver, and capping symmetrically in the handler is defense-in-depth so the
secure pattern is the one you copy from this guide.

---

## Section 4 — Multiple file uploads (`Multipart`)

**FastAPI shape.**

```python
from typing import List
from fastapi import FastAPI, File, UploadFile

app = FastAPI()

@app.post("/upload-multi")
async def upload_multi(files: List[UploadFile] = File(...)) -> dict:
    return {"count": len(files), "names": [f.filename for f in files]}
```

**Nexus shape.**

```python
from nexus import Nexus
from nexus.extractors import Multipart

app = Nexus()

async def upload_multi(files: Multipart) -> dict:
    return {"count": len(files), "names": [f.filename for f in files]}

app.handler_extract("upload_multi", upload_multi)
```

**Mapping.** `Multipart` is the typed alias for a list of uploaded files. The
annotation is the extractor; iterate it to get each file (each item exposes the
same `filename` / `content_type` / `read()` surface as a single `UploadFile`).
Apply the same per-file `MAX_SIZE` read ceiling from section 3 when reading file
contents.

---

## Section 5 — Server-Sent Events (`register_sse`)

**FastAPI shape (with `sse-starlette`).**

```python
import asyncio
import json
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

@app.get("/events")
async def events(request: Request):
    async def event_stream():
        for i in range(10):
            yield {"data": json.dumps({"i": i})}
            await asyncio.sleep(1)
    return EventSourceResponse(event_stream())
```

**Nexus shape.**

```python
import asyncio
from nexus import Nexus

app = Nexus()

async def on_subscribe(request):
    for i in range(10):
        yield {"i": i}
        await asyncio.sleep(1)

app.register_sse("/events", on_subscribe)
```

**Mapping.** `app.register_sse(path, on_subscribe)` takes an `on_subscribe` async
generator that receives the request and yields plain dicts; each yielded dict
serializes to one SSE frame. You do not construct an `EventSourceResponse` —
Nexus handles the framing. Keepalive comments fire every 15 seconds by default;
pass `keepalive_interval=` to change it. Additional production controls are
available as keyword arguments: `max_queue_depth` (default 1000),
`max_event_bytes` (default 65536), and `slow_consumer_timeout` (default 30.0
seconds) bound resource use against slow or stalled clients, and `dependencies=`
accepts a list of `Depends` callables resolved before the stream opens.

---

## Section 6 — WebSocket (`register_websocket`)

Nexus supports two WebSocket shapes: a lightweight callback shape and a
class-based shape for per-connection state and lifecycle.

**FastAPI shape.**

```python
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        msg = await websocket.receive_json()
        await websocket.send_json({"echo": msg})
```

**Nexus shape (callback).**

```python
from nexus import Nexus, Connection

app = Nexus()

async def on_message(conn: Connection, msg: dict) -> None:
    await conn.send_json({"echo": msg})

app.register_websocket("/ws", on_message=on_message)
```

**Nexus shape (class-based).**

```python
from nexus import Nexus, Connection, MessageHandler

app = Nexus()

class EchoHandler(MessageHandler):
    async def on_connect(self, conn: Connection) -> None:
        conn.state.count = 0

    async def on_message(self, conn: Connection, msg: dict) -> None:
        conn.state.count += 1
        await conn.send_json({"echo": msg, "seen": conn.state.count})

app.register_websocket("/ws", EchoHandler)
```

**Mapping.** Both shapes register through `app.register_websocket(path, ...)`. The
callback shape passes `on_message=` (and optionally `on_connect=` /
`on_disconnect=`) — ergonomically light, no class needed. The class shape passes a
`MessageHandler` subclass positionally; it supports per-connection state
(`conn.state`) and lifecycle hooks (`on_connect` / `on_disconnect`). Both replace
FastAPI's manual `await websocket.accept()` + receive/send loop — Nexus drives the
loop and dispatches each frame to your handler. Origin restrictions and
subprotocols are configured via `allowed_origins=` and `subprotocols=`, and
`dependencies=` resolves `Depends` callables at connection time.

---

## Section 7 — Tests via `dependency_overrides`

**FastAPI shape.**

```python
def test_protected_endpoint(client):
    app.dependency_overrides[get_current_user] = lambda: {"id": "test"}
    response = client.post("/profile")
    assert response.json() == {"user_id": "test"}
    app.dependency_overrides.clear()
```

**Nexus shape (context-manager — recommended).**

```python
def test_protected_endpoint(client):
    with app.dependency_overrides.override(get_current_user, lambda: {"id": "test"}):
        response = client.post("/workflows/get_profile/execute", json={"inputs": {}})
        assert response.json()["user_id"] == "test"
    # override automatically restored at block exit
```

**Nexus shape (imperative).**

```python
def test_protected_endpoint(client):
    app.dependency_overrides.set(get_current_user, lambda: {"id": "test"})
    response = client.post("/workflows/get_profile/execute", json={"inputs": {}})
    assert response.json()["user_id"] == "test"
    app.dependency_overrides.clear(get_current_user)
```

**Mapping.** FastAPI's `dependency_overrides` is a plain mutable dict
(`overrides[real] = mock`). Nexus's is a typed `DependencyOverrideMap` with named
methods instead of dict-item assignment:

- `app.dependency_overrides.override(real, mock)` — a context manager that installs
  the override for the block and auto-restores at exit. This is the recommended
  testing pattern.
- `app.dependency_overrides.set(real, mock)` — imperative install (you clear it
  yourself).
- `app.dependency_overrides.clear(real)` — remove one override.
- `app.dependency_overrides.clear_all()` — remove every override.

The context-manager form is preferred because it cannot leak an override into the
next test even if an assertion raises mid-block.

---

## Section 8 — PEP 563 gotcha (footgun avoidance)

**The trap.** Any module that defines Nexus handlers using extractors MUST NOT use
`from __future__ import annotations`. PEP 563 (deferred annotations) turns every
type annotation into a string at runtime. The Nexus extractor resolver inspects
handler annotations at registration time to identify which parameters are
extractors (`Depends`, `UploadFile`, `Bytes`, and so on); when those annotations
are stringified by PEP 563, the resolver cannot resolve them to extractor types.

**The error.** Registering an extractor-bearing handler from a module that imported
`from __future__ import annotations` raises a typed error at registration time
naming the module — it fails loud, not silent.

**The fix.** Remove `from __future__ import annotations` from any module that
defines Nexus handlers. The annotations stay real types and runtime introspection
works as designed.

```python
# DO — real annotations, resolver can introspect
from nexus import Nexus
from nexus.extractors import UploadFile

app = Nexus()

async def upload(file: UploadFile) -> dict:
    return {"filename": file.filename}

app.handler_extract("upload", upload)

# DO NOT — PEP 563 stringifies annotations; registration raises a typed error
from __future__ import annotations   # <-- remove this line
from nexus.extractors import UploadFile

async def upload(file: UploadFile) -> dict:   # `UploadFile` is now the string "UploadFile"
    ...
```

---

## Section 9 — What's not yet ported

These FastAPI surfaces are tracked as follow-ups (see issue #1174 and its linked
items). They are not available today; the sections above show the shipped
alternative for each.

- **Typed-model body extraction (`Body[T]`).** Declaring a single
  `body: MyModel` parameter that Nexus validates and constructs from the request
  body. Today, use flat-input parameters (section 2) for structured JSON or the
  `Bytes` extractor for manual decode. Decoder registration for arbitrary model
  types is part of this follow-up.
- **`Query` extractor.** Typed query-string parameters. Today, read query values
  off the `Request` extractor.
- **Cross-transport `NexusRequest` context object.** A unified request object that
  presents the same surface across HTTP, CLI, and MCP. Today the `Request`
  extractor covers the HTTP channel.
- **OpenAPI generation from extractor-annotated handlers.** Auto-generated OpenAPI
  schema derived from handler signatures.

This section bounds what you cannot port today; everything outside this list has a
shipped equivalent above.
