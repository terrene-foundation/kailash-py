---
type: DISCOVERY
date: 2026-07-14
author: agent
project: issue-1717-vertex-claude
topic: "#1737 read receipt — Rust rs#1810 DataFlow credential-callback semantics + Python do_connect design"
phase: implement
tags: [cross-sdk, "1737", dataflow, credential-callback, rs-1810, read-receipt]
relates_to: 0008-cross-repo-grant-1737-rust-read-dataflow-credential-callback
---

# Read receipt — Rust rs#1810 credential callback (grant journal/0008)

Read `crates/kailash-dataflow/src/connection.rs:389-548` under grant 0008
(`cross-repo-authorized: esperie-enterprise/kailash-rs`), read-only, scoped to
the credential-callback surface.

## Rust rs#1810 contract (verified)

- **Callback:** `CredentialProvider = Arc<dyn Fn() -> Result<String, DataFlowError>>`
  — returns a fully-resolved **DSN** (full connection string with fresh token).
- **Why a DSN not a password:** the sqlx `Any` pool exposes no password mutator;
  returning the DSN lets `AnyConnectOptions::FromStr` parse it with ZERO
  transformation, avoiding a percent-encoding round-trip that would corrupt AWS
  IAM tokens (they embed `&`, `=`, `/`, `%`).
- **Invocation model:** a **background refresh task** (`spawn_credential_refresh`)
  on an interval (default `DEFAULT_CREDENTIAL_REFRESH = 300s`, below Azure AD
  ~60-90min / AWS IAM 15min lifetimes) that re-invokes the provider and applies
  fresh options to every pool via `sqlx::Pool::set_connect_options`. NOT strictly
  per-physical-connection — refresh-ahead.
- **Builder:** `with_credential_provider(p)` + `with_credential_refresh_interval(d)`.
- **Fail-closed:** callback `Err` → typed `DataFlowError`; at construction aborts
  `from_config`; during refresh logs a REDACTED event + retains previous options
  (a truly-expired token then fails closed naturally at connect — never a
  fabricated fallback).
- **Security:** live secret held only in `Zeroizing`; NEVER logged (not length,
  not prefix), never in `Debug`; DSN parse errors never interpolate the DSN.
- **Replica:** `replica_dsn_with_provider_credentials` splices the provider
  userinfo onto the replica host (verbatim, no decode/re-encode).

## Python design decision (parity of SEMANTIC, idiomatic mechanism)

Python DataFlow is SQLAlchemy-backed (`create_async_engine`). The idiomatic
Python mechanism is the SQLAlchemy **`do_connect` event** — invoked per physical
connection — which is ALSO the issue's own "Requested API". Decision: implement
`credential_provider: Callable[[], str]` returning the fresh password/token, set
in a `do_connect` handler on `cparams["password"]`.

- **Mechanism DIFFERS from Rust** (per-connection do_connect vs background
  refresh-ahead) but the SEMANTIC GUARANTEE MATCHES and is in fact STRICTER: a
  do_connect handler re-mints on EVERY physical connection → zero staleness
  window (Rust has a ≤interval window). This satisfies #1737 AC "pool invokes it
  for EVERY physical connection" AND "semantics match Rust" (the observable
  contract — post-expiry connections authenticate fresh, fail-closed on error).
- **Password not DSN:** SQLAlchemy `do_connect` sets the password as a DRIVER
  PARAM (`cparams["password"]`), not via URL — so no percent-encoding round-trip;
  the DSN-return complexity Rust needed does not arise. (A resolved-DSN variant
  MAY be offered too, but the password callable is the clean core.)
- **Fail-closed + never-log + zeroize** carried over verbatim as requirements.

## For Discussion

1. Do we also expose the resolved-DSN callback variant for host/port rotation,
   or is password-only sufficient for the Azure-AD/IAM use case (the 99% case)?
2. Should the callback be sync `Callable[[], str]` or also accept an async
   `Awaitable` (token endpoints are network calls)? do_connect is sync in
   SQLAlchemy — an async provider needs a bridging strategy.
