<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: e67304453
migrated_from: .session-notes
---

# Session Notes — 2026-07-12 (#1606 express-v3 release + forest consolidation)

## Where we are

Shipped **#1606 end-to-end**: DataFlow Express cross-DB cache bleed → v2→v3 keyspace lockstep,
3-agent redteam to convergence, merged (#1700), released **kailash-dataflow 2.15.0** (PyPI +
clean-venv verified). Filed cross-SDK **rs#1771**. Then `/sweep` + **consolidated the forest ledger
to root** (`.session-notes.shared.md` now canonical; legacy workspace monoliths retired to
pointers). Board clean, no sibling drift. Repo on `main` @ `e67304453`, tree clean. Phase 05-codify.

## Read first

1. `.session-notes.shared.md` — the authoritative root forest ledger (F1/F13/F14-FC/F23/F24). START HERE.
2. `workspaces/sdk-backlog/04-validate/sweep-2026-07-12.md` — this session's sweep + consolidation report.
3. `workspaces/sdk-backlog/journal/0028-DECISION-1606-express-v3-fix-and-2150-release.md` — #1606 fix + 2.15.0 receipt.
4. `workspaces/sdk-backlog/journal/0027-cross-repo-grant-rust-sdk-1606-credential-dsn-parity.md` — rs#1771 grant.

## Executed this session

- **Released kailash-dataflow 2.15.0** (tag `dataflow-v2.15.0`, publish-pypi success, GitHub Release, clean-venv install verified) — the #1606 Express fix.
- **Filed rs#1771** on the Rust SDK (`cross-sdk`) — #1606 `//`-less-DSN credential-in-pre-image parity (grant `journal/0027`).

## Outstanding ledger (forest)

Authoritative = root `.session-notes.shared.md` (consolidated this session). Highlights: **F13
#1532** delegate-connectors (DEFERRED, authorized grant journaled `sdk-backlog/0014` — the warm
next pick); F1 mops-onboarding (BLOCKED on its own cross-repo re-confirm); F14/FC SAFR #1514-1517
(BLOCKED on user scoping); F23 rs#1765 + F24 rs#1771 (cross-SDK, rs-side). No unblocked in-repo
item remains — next pick is the human's call.

Closed this session: `F19` #1606 → PR #1700 + release `dataflow-v2.15.0` (`journal/0028`).
Reconciled off root: F20 #1607 / F21 #1614 / F22 #1601 (verified CLOSED via gh, prior work).

## Traps

- **Root split is canonical.** Write wrapups to `.session-notes.d/esperie.md` + `.session-notes.shared.md` (repo root); the workspace `.session-notes` monoliths are now pointer-stubs (forest sections retired 2026-07-12, #669).
- **Loom-routed items are NOT kailash-py SDK forest.** sdk-backlog F5–F8 + mops-onboarding F3–F14 live loom-side (`latest.yaml` + journal anchors); do NOT migrate them into the root SDK ledger.
- **venv tool shebangs are stale** (repo moved from `~/repos/loom/kailash-py`): use `.venv/bin/python -m black|isort|pre_commit`, not the bare binaries.
- **#1532 grant is RECORDED, not standing licence** — restate+confirm+journal-before-acting per cross-repo read (`repo-scope-discipline` conds 3+4). Align to SPECS, not kailash-rs.
- **rs#1765 / rs#1771** on-remote state never verified from here (repo-scope) — spot-check from a kailash-rs-scoped session before citing as existing.
