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

**Nexus shape (immediate path with `Body[dict]`).**

```python
from kailash.nexus.extractors import Body
@app.handler("create_user")
async def create_user(body: Body[dict]) -> dict: ...  # body is a dict
```

**Nexus shape (Pydantic — deferred, link to follow-up issue).**

The Pydantic body-parsing path is tracked at `<follow-up-issue-link>`. Until it ships, use `Body[dict]` and validate inside the handler.

**Mapping prose.** Pydantic body parsing is deferred (Risk 3 in `01-analysis/03-risks-and-cross-cutting.md`). The immediate `Body[dict]` path covers all dict-shaped bodies; structural validation moves to the handler body. The deferred Pydantic path will restore the FastAPI-shape exactly.

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
@app.handler("upload")
async def upload(file: UploadFile) -> dict:
    contents = await file.read()
    return {"filename": file.filename, "size": len(contents)}
```

**Mapping prose.** Nexus's `UploadFile` is Starlette's `UploadFile` re-exported. The annotation IS the extractor (no `= File(...)` sentinel needed because `UploadFile` is unambiguous as a typed parameter). Read API (`filename`, `content_type`, `read()`, `aread()`) is byte-identical to FastAPI.

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
