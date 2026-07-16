# DRAFT — Cross-SDK issue for the Rust SDK four-axis LLM client (NOT YET FILED)

**Status: UNFILED.** Filing needs explicit user authorization + the five
`repo-scope-discipline` conditions (user-initiated + explicit+specific +
confirmed + journaled-before-acting + scoped). This is the scrubbed body,
ready to file on the word "go". Target repo resolves via `build.rs`
(`loom-links.local.json`), label `cross-sdk`.

Scrubbed per `upstream-issue-hygiene.md` MUST-2: SDK-API surface only — no
downstream/consumer context, internal paths, workspace IDs, or finding tags.

---

## Title

`feat(llm): validate per-request BYOK api_key for header-injection at parity across both BYOK entry points`

## Affected API

The four-axis LLM client's per-request **BYOK (bring-your-own-key)** paths that
install a caller-supplied `api_key` into an outbound HTTP header value. There are
(at least) two such entry points that MUST be at parity:

1. the direct per-request override on the completion call (the `complete(...,
api_key=...)` analogue);
2. the deployment-resolution path that accepts a caller-supplied `api_key` and
   bakes it into the deployment's auth strategy (the analogue of resolving a
   provider name → deployment with an override key).

## Summary

A per-request `api_key` is installed verbatim into an HTTP header (e.g.
`Authorization: Bearer <key>` / `api-key: <key>`). If one BYOK entry point
validates the key for control characters / CRLF / non-ASCII before header
install but the sibling entry point does not, a caller-supplied key containing
`\r\n` is a CRLF header-injection surface on the unguarded path
(`"\r\nX-Injected: value"` smuggles an extra header), while the guarded path
rejects it. The two entry points MUST fail closed identically, routing through a
SINGLE shared validator (not two copies that can drift).

## Expected vs actual

- **Expected:** every BYOK entry point that turns a caller-supplied `api_key`
  into a header value rejects — fail-closed, before install — any key containing
  a C0 control char (`\x00`–`\x1f`), DEL (`\x7f`), or a non-ASCII character
  (an HTTP header value must be ASCII). The error is typed and fingerprints the
  key, never echoing it.
- **Actual (to verify in the Rust client):** confirm whether BOTH entry points
  validate, or whether only the direct-override path does while the
  deployment-resolution path installs the raw key unvalidated.

## Severity

MEDIUM–HIGH — header-injection surface on a caller-controlled per-request key;
gated behind an application routing untrusted input into a per-request key.

## Acceptance criteria

- [ ] Both BYOK entry points reject a `\r\n` / control-char / non-ASCII
      `api_key` with the same typed error, before any header install.
- [ ] Both route through ONE shared validation function (no divergent copy).
- [ ] The error fingerprints the key (never echoes the raw secret in message/log).
- [ ] A regression test pins both entry points against a CRLF/NUL/DEL/non-ASCII
      key, plus a valid-key accept case.

## Cross-SDK alignment

Python equivalent: kailash-py #1720 (four-axis LLM consolidation); the parity
fix routed the deployment-resolution BYOK path through the same control-char
validator the direct-override path already used.
