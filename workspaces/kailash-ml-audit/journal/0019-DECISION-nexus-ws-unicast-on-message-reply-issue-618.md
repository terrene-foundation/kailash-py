---
type: DECISION
date: 2026-04-25
created_at: 2026-04-25T10:10:04.114Z
author: agent
session_id: c8cb11ec-e2ab-40d5-95ce-947a896a84ec
project: kailash-ml-audit
topic: per-connection unicast send + on_message reply delivery (#618)
phase: implement
tags: [nexus, websocket, unicast, on-message, cross-sdk-parity, eatp-d6]
source_commit: f390651c9829f2fb5ed88ce96a48137f225c6a12
---

# DECISION — feat(nexus): add per-connection unicast send + on_message reply delivery (#618)

## What

Two empirically-verified gaps in kailash-nexus 2.2.x are closed:

### 1. `MessageHandler.on_message` return value was discarded

The class-based `_safe_on_message` did `await handler.on_message(conn, msg)` without binding the return value. Clients waiting on a synchronous reply timed out unless the handler also called `await conn.send_json(...)` explicitly, duplicating the value.

**Fix**: `on_message` / `on_text` non-`None` returns are now auto-delivered via `conn.send_json` (dict/list), `conn.send_text` (str), or UTF-8-decoded `conn.send_text` (bytes). `None` preserves the no-auto-reply contract for handlers that already send explicitly.

### 2. No per-connection unicast push from external publishers

A DataFlow change stream or message-queue consumer that knows a target `connection_id` had no way to address that one client; `websocket_broadcast` fans out to every tracked connection via `on_event`. Per-tenant push from outside the receive loop was structurally impossible.

**Fix**: `Nexus.websocket_send_to(path, connection_id, payload) -> bool` (issue #618). Tenant-safe by construction — dispatch is scoped to the named connection; no other client receives the frame. Returns `False` (no raise) for unknown path / unknown connection*id / already-closed socket. The registry-level primitive is `MessageHandlerRegistry.send_to` and reuses `Connection.send*\*`so the wire frame matches`on_message` auto-replies bit-for-bit.

## Why

Cross-SDK parity with kailash-rs#589 per EATP D6 — both halves of the API surface match the Rust semantics. The two gaps emerged from two different real consumers: an MLFP coursework integration that needed `on_message` to return a reply (the duplicate-send workaround was confusing students), and a DataFlow-driven dashboard that needed per-tenant push without broadcasting tenant data to siblings.

## Tests

95/95 websocket tests pass (43 unit + 23 transport unit + 19 existing integration + 10 new integration). NO mocking in Tier 2 per `rules/testing.md` — real aiohttp test server, real WebSocket frames.

## For Discussion

1. Returning a non-None value from `on_message` is now semantically equivalent to `await conn.send_*`. Existing handlers that ALREADY return-and-send-explicitly will now send TWICE. We added a regression test for the no-double-send contract; should we also add a runtime warning when the same handler does both?
2. Counterfactual: the `bool` return of `websocket_send_to` swallows the failure cause (unknown path vs unknown connection vs closed socket). For tenant-isolation auditing, the cause matters. Should we either (a) raise a typed exception per cause, or (b) return a richer enum? The bool-only choice was made for parity with kailash-rs#589's `Result<bool, _>` — but Python's `False` is strictly less informative than Rust's `Err`.
3. The `websocket_send_to` API is tenant-safe BY CONSTRUCTION (only the named connection receives the frame). But it does not VERIFY that the caller is authorized to send to that connection. Should the API require a tenant-scoped capability token, or is that the application layer's job?
