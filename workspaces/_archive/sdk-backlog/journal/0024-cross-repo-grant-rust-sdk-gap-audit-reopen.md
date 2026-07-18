# 0024 — GRANT: cross-repo thorough gap-audit + conditional reopen (kailash-rs)

**Date:** 2026-07-12 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (per repo-scope-discipline § User-Authorized Exception — all five conditions)

- **Requester / authorizer:** jack@terrene.foundation (repo owner), this session.
- **Verbatim instruction:** "please read thoroughly, i authorize and REOPEN if there are gaps
  please. approved the rest."
- **Target:** `esperie-enterprise/kailash-rs` (private).
- **Action — READ (bounded, thorough):** `gh issue view` + `gh pr view/diff` on **rs#1713**
  (+ its resolving PR) and **rs#1729** (+ its resolving PR) — full thread + linked code — to
  (a) audit closure completeness for gaps, (b) extract the exact `v3` express keyspace contract
  the Rust side landed (needed to implement py #1606 byte-for-byte).
- **Action — WRITE (conditional, gap-triggered):** IF a real gap is found, `gh issue reopen <N>`
  - a scrubbed gap-explaining `gh issue comment` on rs#1713 and/or rs#1729 ONLY. Comment bodies
    MUST be SDK-public-API-only per `upstream-issue-hygiene.md` MUST-2 (no downstream/workspace
    context, no finding tags). NO other writes, NO other repos, NO other issues.
- **In-repo approvals ("the rest"):** close py #1601 if rs#1729 is gap-free; implement py #1606
  express `v2→v3` keyspace lockstep (normal /implement → /redteam → /release).
- **Timestamp (grant, pre-action):** 2026-07-12T10:22:40Z.
- **Scope guarantee:** reads + conditional reopens limited to rs#1713/rs#1729 (+ their PRs) on the
  named repo; any incidental read/write beyond this is out of scope.

## Baseline (from journal/0023, 2026-07-11)

rs#1713/1729/1732 were OPEN; re-checked 2026-07-12 all CLOSED. This grant authorizes the thorough
audit of the two forest-relevant closures (rs#1713/F2, rs#1729/F3) for completeness before py-side
disposition.

## Audit results — NO gaps, NO reopens (conditional-reopen condition NOT met)

**rs#1713 (F2)** — CLOSED **COMPLETED** via rs PR#1761 (v4.x). The 04:17Z "intentionally held /
not-started" comment was STALE: ~4 h later PR#1761 landed the full `v2→v3` keyspace (DB-instance
dimension), canonical byte-vectors, and both reviewers CLEAN (a residual `from_existing_pool` bleed
path was caught + fixed in-PR). Legitimate completion → NO reopen. The lane model is explicit:
"specs → rs implements & leads → py mirrors byte-for-byte." rs is now on v3; py express is still on v2
→ py #1606 must catch up (the implementation this unblocks).

**rs#1729 (F3)** — CLOSED **COMPLETED** via rs PR#1751 (v4.30.0). Soft-delete parity closes 4 gaps
vs the Foundation contract (`deleted_at` auto-column, tombstone+idempotency guard, `include_deleted`,
`restore`); Tier-2 tested; `versioned` explicitly aligned (stays unimplemented in both, removed
Foundation-side 2.14.0); PLUS a bonus cross-tenant read security fix surfaced by its review. Both
py #1601 acceptance criteria satisfied → NO reopen. **py #1601 CLOSED** this session (completed,
rs#1729/PR#1751 reference).

## v3 keyspace contract captured (for py #1606) + byte-exactness verified

- multi-tenant: `dataflow:v3:{db_instance}:{tenant}:{model}:{op}:{params_hash}`
- single-tenant: `dataflow:v3:{db_instance}:{model}:{op}:{params_hash}`
- `db_instance = "db" + SHA-256(normalized)[:16 lowercase hex]`, normalized = `scheme://authority/path`
  (scheme lowercased, userinfo + query + fragment stripped BEFORE hashing, no trailing slash added).
- Verified in Python against the rs canonical vectors: V1 `postgres://cache-host:5432/app_a` →
  `dbd4e3f17d35c2bb57` ✓; V3 `sqlite:///var/data/app_b.db` → `db5c74b84689218303` ✓ (2/2 match).
- Canonical vectors: rs `test-vectors/dataflow-cache-keys.json` (`dataflow-cache-keys-v3`, 6 vectors
  incl. V4 empty-hash / V5 cross-DB anti-collision / V6 credential-strip sentinels) — py MUST VENDOR
  byte-for-byte per `cross-sdk-inspection.md` Rule 4a, NOT re-author.

## Follow-on (approved "the rest") — py #1606 express keyspace implementation

Tracked as its own feature workstream (distinct PR): modify `generate_express_key` v2→v3, vendor the
canonical vectors + pin them byte-for-byte, flip `test_express_key_excludes_db_identity_segment`,
version-wildcard invalidation sweep (`tenant-isolation.md` Rule 3a), Tier-2 two-DB bleed test,
kailash-dataflow version bump → /redteam → /release.
