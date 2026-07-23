# Cross-SDK Inspection — checkpoint-dir cwd-litter analog (kailash-rs)

**Date:** 2026-07-23 (cont-15). **Authorization:** READ-tier receipt
`.claude/cross-repo-authz/2026-07-23-*-read-only-inspecti.md` (user-approved).
**Scope:** read-only (`gh search code`), no writes, no issue filing.

## Question

Does the Rust SDK's autonomous-agent equivalent create a checkpoint/state
directory in the caller's cwd on construction — the Rust analog of the
kaizen-agents defect fixed in 0.11.8 (construct-time `./checkpoints` mkdir) /
0.12.0 (run-time writes relocated off cwd)?

## Finding — NO equivalent defect

The Rust SDK's checkpoint model is architecturally different: an explicit
**`CheckpointStore`** abstraction, not a `checkpoint_dir` that defaults to
`./checkpoints` and is mkdir'd in a constructor.

Evidence (quoted from the read):

- `ffi/kailash-go/checkpoint.go`: `CheckpointStoreSQLite(path)` takes an
  **explicit path**; `CheckpointStoreMemory()` is **in-memory**. The store is
  constructed by the caller with an explicit backing, not auto-defaulted to cwd.
- `crates/kaizen-agents/src/l3_runtime/plan/executor.rs::checkpoint(...)` is a
  plan-executor quiesce/timeout method, not filesystem dir creation.
- **Zero hits** for `checkpoint_dir`, `"./checkpoints"`, or
  `create_dir_all checkpoints`.
- Every `create_dir_all` site is an explicit-path context (file-write parent,
  `build.rs` output, `sandbox.rs` test dirs, `genesis_store.rs`,
  `trust-plane/holds.rs`) — none is an agent constructor creating a cwd-relative
  checkpoint dir.

## Disposition

No cross-SDK issue filed (nothing to file — no gap). The documented-default /
cwd-litter class is Python-facade-specific — same conclusion the cont-14 #1927
cross-SDK inspection reached (the Python facade patterns don't map to the Rust
architecture). Cross-sdk-inspection Rule 5 checklist: "Does the other SDK have
this issue? → NO (verified, read-only)."
