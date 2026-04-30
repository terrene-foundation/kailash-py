---
type: DISCOVERY
created: 2026-04-29
issue: 712
phase: 01-analyze
relates_to: 0001-DISCOVERY-712-may-regress-500-501-fixed-nexus-2.1.1.md
---

# #712 brief misframes the bug — real failure is timing trap + missing public API, not silent-disable

## Brief claim under scrutiny

> `kailash.servers.workflow_server.WorkflowServer.__init__` constructs the FastAPI app with `lifespan=` set, which per FastAPI/Starlette semantics silently disables any `@app.on_event("startup")` / `@app.on_event("shutdown")` decorators registered later by consumers.

## Verification result (deep-dive Round 1, 2026-04-29)

The cited general FastAPI/Starlette semantic IS true. The claim that THIS codebase exhibits it is FALSE.

`src/kailash/servers/workflow_server.py:234-237` (current at HEAD):

```python
# inside the custom lifespan @asynccontextmanager
for handler in app.router.on_startup:
    res = handler()
    if inspect.iscoroutine(res):
        await res
```

`src/kailash/servers/workflow_server.py:279-282` does the same for `on_shutdown`.

The block carries explicit comments at lines 186-202 documenting that this iteration was added to fix #500/#501/#531. So `@app.on_event("startup")` (which appends to
`app.router.on_startup` via `app.add_event_handler` → `self.router.add_event_handler`) IS picked up.

## What #712 actually surfaces

The Mediscribe reproduction (per #712 body) shows their hook silently failing. Three plausible reasons, only one of which matches the brief framing:

1. **Mediscribe is on a stale Nexus** (pre-2.1.1 — the #500/#501 fix release). Their `app.router.lifespan_context`-wrapping workaround is the same one referenced in impact-verse `f1186b28` from the #500 era. If true, the fix is "upgrade nexus" + a runtime-detection that errors loudly when consumers register `on_event` against a stale version.

2. **Timing trap**: `nexus.fastapi_app` (the property at `core.py:573-579`) returns `None` until `_initialize_gateway()` runs — and gateway init is lazy on first `nexus.register(...)` call. A consumer pattern of:

   ```python
   nexus = Nexus(...)
   @nexus.app.on_event("startup")  # AttributeError: NoneType has no on_event
   async def my_startup(): ...
   nexus.register(...)
   ```

   fails with `AttributeError` (not silently). But the consumer may have `try/except` around the decorator — turning it into a silent failure even though the SDK raised loudly.

3. **Sibling FastAPI construction sites** (5 found by deep-dive) without the router-iteration mitigation:
   - `src/kailash/middleware/communication/api_gateway.py:201-208`
   - `src/kailash/api/gateway.py:147-149`
   - `src/kailash/api/workflow_api.py:145-150`
   - `src/kailash/visualization/api.py:162-166` (no `lifespan=` — safe)
   - `src/kailash/gateway/api.py:261` (no `lifespan=` — safe)

   Of these, the first three set `lifespan=` AND likely lack the router-iteration. Per `security.md` § Multi-Site Kwarg Plumbing, fixing one site without sweeping the others ships the same failure mode at sibling surface. **This is the most-likely structural finding** — the canonical Nexus path was patched but its siblings were not.

## Most likely true root cause (revised)

**(2) + (3)**: discoverability gap (no `Nexus.add_startup_handler(func)` public API → consumers reach for `nexus.fastapi_app.on_event` and hit the timing trap) AND sibling FastAPI sites that are unpatched.

The brief's "silent disable" framing is better fitted to the SIBLING sites, not the canonical Nexus path the brief cites.

## Brief corrections to record in plan

| Brief claim                                                 | Reality                                                                       | Correction                                                                                        |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Cited `workflow_server.py:138-149` for FastAPI construction | Actual is `workflow_server.py:297-299`; lines 138-149 are docstring           | Use correct lines in plan                                                                         |
| "Silently disables `@app.on_event`"                         | Custom lifespan iterates `router.on_startup` (lines 234-237) — handlers fire  | Reframe as discoverability + timing gap, not silent disable                                       |
| Suggested fix (1): document the FastAPI semantics           | Less applicable; the codebase already mitigates the upstream FastAPI behavior | Recommend instead: ship `Nexus.add_startup_handler(func)` public API                              |
| Suggested fix (3): refuse `nexus.app.on_event` loudly       | Counterproductive; that path WORKS for late-registered consumers              | Replace with: handle the timing trap (raise loud error if `fastapi_app` is None at on_event time) |

## Implications for the architecture plan

- The Nexus fix is **two-pronged**, not single:
  - Add `Nexus.add_startup_handler(func)` / `Nexus.add_shutdown_handler(func)` public methods that route into `_startup_hooks` / `_shutdown_hooks` (already exists internally for plugins)
  - Sweep the 3 sibling FastAPI sites and either add router-iteration mitigation, mark them deprecated, or extract a shared helper (preferred, per `security.md` § Multi-Site Kwarg Plumbing)

- The Mediscribe-specific path also needs an upgrade-guidance note — if they're on a pre-2.1.1 Nexus, they need to upgrade. This is documentation only.

- The Tier-2 regression test for #712 must exercise BOTH the canonical and the sibling paths. The #500-era test (`test_issue_500_router_on_startup.py`) only covered `WorkflowServer`. Per `rules/orphan-detection.md` § "Every Manager-Shape Class Has a Tier 2 Test", every FastAPI() construction with `lifespan=` should have a wiring test.

## Reference data captured for /todos

- Canonical: `src/kailash/servers/workflow_server.py:297-299` (FastAPI), `:203-295` (lifespan), `:234-237` + `:279-282` (router iteration)
- Nexus public API path: `packages/kailash-nexus/src/nexus/core.py:1942` (`add_plugin`), `:573-579` (`fastapi_app` property), `:775-787` (lifespan wiring), `:2084-2103` (`_call_startup_hooks_async`)
- 3 sibling FastAPI sites needing audit: `middleware/communication/api_gateway.py:201`, `api/gateway.py:147`, `api/workflow_api.py:145`
- FastAPI version pins: root `fastapi>=0.115.12`; nexus `fastapi>=0.104.0` (drift)
- `nexus.fastapi_app` is reachable but NOT in `__all__`; treated as supported by deprecation pointer at `core.py:548`
