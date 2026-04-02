---
type: DISCOVERY
date: 2026-04-02
created_at: 2026-04-02T17:00:00+08:00
author: co-authored
session_turn: 9
project: data-fabric-engine
topic: The fabric is a runtime system, not a code library
phase: analyze
tags: [architecture, mental-model, runtime, system-design]
---

# Discovery: The Fabric Is a Runtime System, Not a Code Library

## Finding

Previous analysis treated the fabric as a library — call functions, get results. The user's challenge ("how does monitoring work? how are endpoints consumed? how do sources send to it?") revealed that calling `db.start()` starts a RUNNING SYSTEM with:

1. **Background workers** — pollers, file watchers, webhook listeners, stream consumers
2. **State machines** — each source has a lifecycle (configured → active → paused → error)
3. **Event processing** — change detection → pipeline → cache update, all asynchronous
4. **A monitoring surface** — health endpoints, structured logs, metrics, pipeline traces
5. **An API serving layer** — auto-generated endpoints with freshness metadata

This is more like starting PostgreSQL than calling a function. The developer configures it, starts it, and it runs — handling requests, managing state, processing events continuously.

## Implications for Design

- `db.start()` is not "warm the cache." It is "start the system."
- `db.stop()` must cleanly shut down all background workers, close connections, flush metrics.
- Error handling is not try/except in user code. It is circuit breakers, staleness policies, degradation modes — system-level resilience.
- Observability is not optional logging. It is health endpoints, structured traces, Prometheus metrics — a monitoring surface that ops teams depend on.

## Implications for Documentation

The documentation should describe the fabric as a runtime, not as an API:

- "What is running after db.start()?" not "What methods can I call?"
- "What happens when a source goes down?" not "What exceptions are raised?"
- "How do I debug stale data?" not "How do I read cache entries?"

## For Discussion

1. If the fabric is a runtime system, should it have its own process? Or is running inside the application process (alongside Uvicorn) the right model? Separate process means better isolation but more deployment complexity.
2. How does the fabric runtime interact with Gunicorn workers? Multiple workers = multiple fabric runtimes = duplicate polling. The distributed lock handles this, but is there a "leader election" pattern that's cleaner?
3. Should the fabric expose a management API (start/stop/restart sources, pause products, force refresh) separate from the data API? This is the difference between a library and a service.
