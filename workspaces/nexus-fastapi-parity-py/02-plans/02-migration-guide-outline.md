# Migration guide outline — FastAPI APIRouter → Nexus handler

This outline is the table of contents the migration guide ships against. One section per FastAPI parity surface. The implementation phase fleshes each section into ~30 lines of FastAPI snippet + ~30 lines of Nexus equivalent + prose explaining the mapping.

## Section 1 — Auth via `Depends(get_current_user)`

**FastAPI shape.**

```python
from fastapi import Depends, HTTPException
async def get_current_user(token: str = Header(...)) -> User: ...
@app.get("/profile")
async def get_profile(user: User = Depends(get_current_user)) -> dict:
    return {"user_id": user.id}
```

**Nexus shape.**

```python
from kailash.nexus.extractors import Depends, Request
async def get_current_user(request: Request) -> User: ...
@app.handler("profile")
async def get_profile(user: User = Depends(get_current_user)) -> dict:
    return {"user_id": user.id}
```

**Mapping prose.** Same import name (`Depends`); same default-value pattern. The dependency callable's signature receives `Request` (Nexus extractor) instead of FastAPI-specific extractors. The handler shape is the same; the registration changes from `@app.get(path)` to `@app.handler(name)` (Nexus is multi-channel; path is one expression).

## Section 2 — Typed bodies

**FastAPI shape.**

```python
from pydantic import BaseModel
class CreateUser(BaseModel):
    name: str
    email: str
@app.post("/users")
async def create_user(body: CreateUser) -> dict: ...
```

**Nexus shape (Pydantic via canonical decoder — NEW-LOW-1, strict-mode mandatory).**

```python
from pydantic import BaseModel, ConfigDict
from kailash.nexus.extractors import Body
from kailash.nexus import register_decoder

class CreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")  # MUST — registration fails loud otherwise
    name: str
    email: str

# Canonical pydantic decoder — strict=True is MANDATORY in this example
register_decoder(CreateUser, lambda data, T: T.model_validate(data, strict=True))

@app.handler("create_user")
async def create_user(body: Body[CreateUser]) -> dict:
    return {"id": body.name}
```

**Nexus shape (dataclass — no decoder registration; introspection-based).**

```python
from dataclasses import dataclass
from kailash.nexus.extractors import Body

@dataclass
class CreateUser:
    name: str
    email: str

# No register_decoder call needed; the resolver introspects __init__ params.
# Extra keys (e.g., {"name": "x", "email": "y", "is_admin": true}) raise
# BodyExtraKeysError → HTTP 400 + {"code": "BODY_UNKNOWN_FIELDS", "unknown_fields": ["is_admin"]}.
@app.handler("create_user")
async def create_user(body: Body[CreateUser]) -> dict: ...
```

**Mapping prose.** `Body[T]` accepts a typed model `T`. Two paths are supported by default — registered decoder OR `inspect.signature(T.__init__).parameters` introspection. Both reject unknown keys structurally (mass-assignment / OWASP A04:2021 defense per `specs/nexus-fastapi-parity.md` § "Body[T] — mass-assignment policy"). The canonical Pydantic example above uses `model_validate(data, strict=True)` — strict mode is MANDATORY for the canonical shape because non-strict validation silently coerces types (e.g. `"true"` → `True`), which downstream sessions cannot distinguish from intentional input. Strict mode + `extra='forbid'` together close the silent-drop failure mode per `rules/zero-tolerance.md` Rule 3 (silent fallback BLOCKED). The migration guide's earlier `Body[dict]` immediate-path framing is superseded by this Q1 closure — typed-bodies ship with the canonical decoder example, not as a deferred-to-follow-up.

**Footgun:** if you forget `model_config = ConfigDict(extra="forbid")` on a Pydantic `T`, Nexus refuses to start with `BodyExtraPolicyError` naming the handler and the offending model. Declaring `extra='forbid'` is the structural defense against accidentally absorbing attacker-supplied fields into your model.

## Section 3 — File uploads (single)

**FastAPI shape.**

```python
from fastapi import UploadFile, File
@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    contents = await file.read()
    return {"filename": file.filename, "size": len(contents)}
```

**Nexus shape.**

```python
from kailash.nexus.extractors import UploadFile

MAX_SIZE = 10 * 1024 * 1024  # 10 MiB; bounded ceiling on read — never unbounded

@app.handler("upload")
async def upload(file: UploadFile) -> dict:
    contents = await file.read(MAX_SIZE)  # MAX_SIZE = bounded ceiling; never `await file.read()` unbounded
    return {"filename": file.filename, "size": len(contents)}
```

**Mapping prose.** Nexus's `UploadFile` is Starlette's `UploadFile` re-exported. The annotation IS the extractor (no `= File(...)` sentinel needed because `UploadFile` is unambiguous as a typed parameter). Read API (`filename`, `content_type`, `read()`, `aread()`) is byte-identical to FastAPI.

**Secure-defaults note (LOW-S2).** Handler code MUST cap the read with an explicit `MAX_SIZE` ceiling — unbounded `await file.read()` is a memory-DoS vector. The Nexus resolver already enforces a body-level cap (`Nexus(max_upload_file_bytes=...)`, default 10 MiB per HIGH-S1), but per `rules/zero-tolerance.md` Rule 6 ("Implement Fully") + `rules/security.md` § Input Validation, defense-in-depth: handlers cap reads symmetrically. The migration guide showcases the explicit-MAX_SIZE pattern as the canonical shape so SDK users learn the secure default on the first read.

## Section 4 — File uploads (multiple)

**FastAPI shape.**

```python
from fastapi import UploadFile, File
from typing import List
@app.post("/upload-multi")
async def upload_multi(files: List[UploadFile] = File(...)) -> dict:
    return {"count": len(files), "names": [f.filename for f in files]}
```

**Nexus shape.**

```python
from kailash.nexus.extractors import Multipart, UploadFile
@app.handler("upload_multi")
async def upload_multi(files: Multipart) -> dict:
    return {"count": len(files), "names": [f.filename for f in files]}
```

**Mapping prose.** `Multipart` is the typed alias for `list[UploadFile]`. Annotation is the extractor; iterating gives each file.

## Section 5 — Server-Sent Events (SSE)

**FastAPI shape (with `sse-starlette`).**

```python
from sse_starlette.sse import EventSourceResponse
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
from kailash.nexus.extractors import Request
async def on_subscribe(request: Request):
    for i in range(10):
        yield {"i": i}
        await asyncio.sleep(1)
nexus.register_sse("/events", on_subscribe=on_subscribe)
```

**Mapping prose.** Nexus's `register_sse(path, on_subscribe)` accepts an `on_subscribe` callable that returns an async iterator of dicts; each dict serializes to one SSE frame. Keepalive comments (`: keepalive`) fire every 15 seconds by default; pass `keepalive_interval=` to override. No need to construct an `EventSourceResponse` — Nexus handles framing.

## Section 6 — WebSocket (callback shape)

**FastAPI shape.**

```python
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        msg = await websocket.receive_json()
        await websocket.send_json({"echo": msg})
```

**Nexus shape (callback).**

```python
from kailash.nexus import Connection
async def on_message(conn: Connection, msg: dict) -> None:
    await conn.send_json({"echo": msg})
nexus.register_websocket("/ws", on_message=on_message)
```

**Nexus shape (class-based, existing).**

```python
from kailash.nexus import MessageHandler, Connection
@nexus.websocket("/ws")
class EchoHandler(MessageHandler):
    async def on_message(self, conn: Connection, msg: dict) -> None:
        await conn.send_json({"echo": msg})
```

**Mapping prose.** Two shapes coexist. The callback shape is ergonomically lighter; the class shape supports per-connection state and lifecycle (`on_connect` / `on_disconnect`). Both register against the same internal `MessageHandlerRegistry`.

## Section 7 — Tests with `dependency_overrides`

**FastAPI shape.**

```python
def test_protected_endpoint():
    app.dependency_overrides[get_current_user] = lambda: User(id="test")
    response = client.get("/profile")
    assert response.json() == {"user_id": "test"}
    app.dependency_overrides.clear()
```

**Nexus shape (context-manager).**

```python
def test_protected_endpoint():
    with nexus.dependency_overrides.override(get_current_user, lambda: User(id="test")):
        response = client.get("/profile")
        assert response.json() == {"user_id": "test"}
    # override automatically restored after the block
```

**Nexus shape (imperative).**

```python
def test_protected_endpoint():
    nexus.dependency_overrides.set(get_current_user, lambda: User(id="test"))
    response = client.get("/profile")
    assert response.json() == {"user_id": "test"}
    nexus.dependency_overrides.clear(get_current_user)
```

**Mapping prose.** FastAPI's `dependency_overrides` is a mutable dict; Nexus's is a typed `DependencyOverrideMap` with both context-manager and imperative APIs. The context-manager form is the recommended testing pattern because it auto-restores.

## Section 8 — PEP 563 gotcha (footgun avoidance)

**The trap.** Any file that imports from `kailash.nexus.extractors` MUST NOT use `from __future__ import annotations`. PEP 563 deferred annotations turn type expressions into strings; the Nexus extractor resolver inspects annotations at runtime to identify extractor types. With PEP 563, those strings cannot be resolved.

**The error.** Importing extractors in a file with PEP 563 raises at handler-registration time with a typed error naming the file. The error message points to this section of the migration guide.

**The fix.** Remove `from __future__ import annotations` from any module that defines Nexus handlers. The annotations stay real types; runtime introspection works as designed.

## Section 9 — What's not yet ported

A standing section pointing to the follow-up issues:

- Pydantic body parsing (issue link).
- Cross-transport `NexusRequest` context object (issue link).
- `Headers` / `Query` / `Body` extractors beyond the immediate set (issue link).
- OpenAPI generation from extractor-annotated handlers (issue link, if any).

This section makes the deferred surface explicit so users know what they cannot port today.
