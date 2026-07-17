# DRAFT — Cross-SDK issue for the Rust SDK creds-in-logs class (NOT YET FILED)

**Status: UNFILED.** Filing needs explicit user authorization + the five
`repo-scope-discipline` User-Authorized-Exception conditions (user-initiated,
explicit+specific, confirmed, journaled-before-acting, scoped). This is the
scrubbed body, ready to file on the word "go". Target repo resolves via
`build.rs` (`loom-links.local.json`); label `cross-sdk`.

Scrubbed per `upstream-issue-hygiene.md` MUST-2: SDK-API surface only — no
downstream/consumer context, internal paths, workspace IDs, or finding tags.

---

## Title

`fix(llm): sanitize credential-bearing exception logs across provider / MCP / connection error paths`

## Affected API

Every error-handling path in the four-axis LLM client + its provider adapters,
the MCP transport (discover/tool-call), and any connection-pool / rate-limiter /
webhook path that logs a caught exception or a connection/webhook URL.

## Summary (Python equivalent: kailash-py #1720, kaizen 2.34.1)

A provider/transport exception can embed a credential — an api-key echoed in a
401 body, a caller-supplied BYOK `base_url` with `user:pass@` userinfo, a
provider URL with a `?key=` query param, an MCP `https://user:pass@host` server
URL, a `redis://user:pass@host` DSN, or a webhook auth token in the URL path.
The Python sweep found the whole class open: error handlers logged the raw
exception (often with the equivalent of `exc_info=True`, which resurfaces the
raw provider error via the exception-cause chain even when the _re-raised_
message was already sanitized), and some paths logged a connection/webhook URL
verbatim on the success path.

## Expected vs actual (to verify in the Rust client)

- **Expected:** every log/return surface that can carry a provider/transport
  exception or a connection/webhook URL is routed through a single shared
  sanitizer (redacting api-key patterns, `Bearer` tokens, and `user:pass@` URL
  userinfo) BEFORE emission; the full backtrace/cause is NOT dumped raw on a
  credential-bearing error path.
- **Actual (verify):** confirm whether the Rust provider/MCP error handlers log
  the raw error (and/or the source-chain backtrace), and whether any
  connection/webhook URL is logged unmasked.

## Notes for the Rust side

- The credential can live in THREE URL components — userinfo (`user:pass@`),
  path (webhook token), and query (`?key=`/`?token=`) — a path-only or
  userinfo-only mask is insufficient (this was a real gap caught in the Python
  security review).
- Sanitizing the _re-raised_ message but NOT the _log_ (or dumping the cause
  chain) is the dominant failure mode — the log and the return must be at parity.

## Severity

MEDIUM — credential exposure to the log surface (log aggregators typically have
broader access than the app), gated behind an error occurring on a
credential-bearing path.

## Acceptance criteria

- [ ] All provider/MCP/connection/webhook error logs + URL logs route through the
      shared sanitizer/masker before emission.
- [ ] No raw source-chain backtrace on a credential-bearing error path.
- [ ] URL masking covers userinfo + path + query.
- [ ] Regression tests pin a credentialed input against each surface (api-key,
      `user:pass@`, webhook token, redis DSN).

## Cross-SDK alignment

Rust equivalent of kailash-py #1720 (kaizen 2.34.1 creds-in-logs sweep).
Cross-reference the Python issue by bare number.
