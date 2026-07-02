---
type: RISK
date: 2026-04-02
created_at: 2026-04-02T18:30:00+08:00
author: agent
session_turn: 11
project: data-fabric-engine
topic: Zero-config mode exposes write endpoints without authentication
phase: analyze
tags: [security, endpoints, authentication, zero-config]
---

# Risk: Default-Open Endpoints in Zero-Config Mode

## Vulnerability

Option A (internal Nexus, zero-config) creates fabric endpoints including write endpoints (`POST /fabric/User/write`) without any authentication. A developer using the simplest path — `await db.start()` — exposes database write operations to anyone who can reach the server.

## Resolution

Three-part defense:

1. Option A binds to `127.0.0.1` by default (localhost only), not `0.0.0.0`
2. Write endpoints are disabled by default — require explicit `enable_writes=True`
3. Production usage requires Option B (attach to existing Nexus with auth middleware)

## For Discussion

1. Should `db.start()` emit a visible warning when running without auth middleware, even on localhost? This would catch the case where a developer deploys to production without switching to Option B.
2. Is binding to localhost sufficient protection? In Docker/Kubernetes, localhost may not mean what the developer expects — other containers in the same pod can access localhost.
3. Should health/trace endpoints also require auth by default? The security review says yes (admin role), but this means zero-config mode has no accessible observability surface.
