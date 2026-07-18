# 0027 — GRANT: cross-repo issue filing (kailash-rs) — #1606 //-less-DSN credential parity

**Date:** 2026-07-12 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (per repo-scope-discipline § User-Authorized Exception — all five conditions)

- **Requester / authorizer:** jack.hong@esperie.com (repo owner), this session, genuine user turn ("approved both").
- **Confirmed:** agent asked "authorize the Rust SDK cross-SDK issue filing? (yes / skip)"; user replied "approved both". Restated target + action below before acting.
- **Target:** `esperie-enterprise/kailash-rs` (private).
- **Action — WRITE (bounded, single):** `gh issue create` ONE issue on `esperie-enterprise/kailash-rs`
  with label `cross-sdk`, reporting the `//`-less credential-bearing DSN edge case in the express
  `db_instance` fingerprint (the rs sibling of the py #1606 L1 hardening). Body is SDK-public-API-only
  per `upstream-issue-hygiene.md` MUST-2 — no downstream/workspace context, no finding tags. NO other
  writes, NO other repos, NO other issues.
- **Timestamp (grant, pre-action):** 2026-07-12 (this session).
- **Scope guarantee:** exactly one issue on the named repo; any incidental read/write beyond this is out
  of scope.

## Context

The py #1606 Express v2→v3 keyspace fix (PR #1700, kailash-dataflow 2.15.0) added
`express_db_instance_fingerprint`. A security review found that a `//`-less credential-bearing DSN
(`postgres:user:pass@host/db`) leaves `urlparse` netloc empty with the userinfo in `path`, so the
netloc `@`-strip never fires and credential bytes enter the SHA-256 pre-image. py hardened this to
fail closed (return `None`). Per `cross-sdk-inspection.md` Rule 1, the rs `db_instance_fingerprint`
(the byte-for-byte contract leader for `dataflow-cache-keys-v3`) likely shares the same parsing shape
and should be inspected + hardened in lockstep. Exposure is low (one-way digest; malformed DSN rarely
connects) but it breaks the "no credential byte in the pre-image" defense-in-depth guarantee.

## Result

Filed **rs#1771** (`esperie-enterprise/kailash-rs`, label `cross-sdk`, 2026-07-12) — the //-less-DSN
credential-in-pre-image edge case in the express `db_instance` fingerprint, cross-referencing the py
#1606 hardening. Body SDK-public-API-only. Action complete, in scope.
