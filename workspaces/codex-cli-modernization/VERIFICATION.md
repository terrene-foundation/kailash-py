# Codex modernization verification — 2026-09-28

Implementation baseline: `4df93818243fec527590876c0022f6d1f8cacb5a`.
Runtime and generated-artifact review pin: `01f6344d14f61999fe1cbea6bc52d484222e8dbb`.
Final documentation candidate: `7a2d0d6bffe6189eb261916bdeb49c62afc52021`.

## Delivered implementation

Updated Codex guides, operations, architect and authoring/delegation instructions;
added the queue coordination skill and 28 native agents; regenerated 28
compatibility prompts and affected Codex/Gemini authoring copies. The emitter
preserves canonical ownership and resolves flattened specialist dependencies.
Configuration changes are comments only; the 800k example does not change active
context settings.

Native hooks use documented matcher/output contracts. Bash validation denies
malformed/invalid input, internal failures and deadlines. Post-edit hygiene
consumes actual patch/file targets with bounded reads and visible skipped-scan
feedback. It is advisory after the edit, and does not scan shell-generated writes.

## Findings fixed before landing

- Reviewer dependencies referenced an excluded Codex skill; preserve the distributed source dependency.
- Thirty relative Markdown links became invalid when categories were flattened; rebase them at emission.
- Two source references named an absent test-harness README; cite the actual probe runner.
- Unknown Bash validation returned nonblocking exit 1; return a blocking error and bound input/execution deadlines.
- A file-path-only PostToolUse checker matched Bash payloads; use edit matchers and adapt patch targets.
- Optional config examples followed an MCP table; place top-level examples before it. Remove stale size/section claims.
- Final CLI version changed from the initial observed 0.154.0 to 0.158.0; preserve evidence attribution without claiming an upgrade cause or retest.

## Checks and review receipts

- **9/9 emitter tests passed:** malformed TOML, invalid names/tool inventories, existing exclusion axes, permission defaults, source ownership, rebased links and generated dependency checks. Rejecting controls ran.
- **17/17 hook tests passed:** real validator allow/deny, malformed/type/error/deadline cases, wrapper roots/spaces/input/status, native edit findings, moves and size/count/path bounds. CC/Gemini behavior controls passed.
- Reviewers validated all 28 native configuration layers against the official schema with invalid-type/enum controls. Schema validity does not prove a child's effective permissions.
- Two emissions produced identical 56 specialist files, byte-equal to checked-in output. Seven source/emitted skill pairs and local links passed; changed-byte and missing-target controls rejected.
- Parsed project configuration equals the baseline; a modified-value control differs, and the uncommented approval example parses at top level.
- Applicable pre-commit checks passed across the complete changed-file set; commits used normal hooks. Diff whitespace checks passed.

Security reviewer `/root/codex_emitter` delivered two consecutive CLEAN rounds at
the runtime pin. Independent probes covered malformed JSON types, oversize input,
timeouts, missing targets, conflicting environment, literal arguments, canonical
path escapes, in-root symlinks, moved/deleted/duplicate targets and 100-file output.
It inspected every hunk between the runtime pin and final candidate: only three
Markdown files changed, so it explicitly carried both security verdicts forward.

Correctness reviewer `/root/codex_local_audit` delivered two distinct CLEAN closure
rounds at the final candidate after fixing the version wording. The final absolute
sweep covered the 89-file implementation union, links in 51 Markdown files, every
native agent and prompt, source/generated parity and configuration scope. It did
not substitute correctness evidence for the separate security verdict.

## Explicit limits

No trusted live Codex hook turn or interactive/headless named-agent execution was
certified. Effective child permission enforcement and standalone skill discovery
remain runtime checks. Static containment does not guarantee safety against hostile
concurrent ancestor mutation. In-root symlinks resolve to their targets; symlink
escapes are rejected. PostToolUse warnings cannot undo a completed edit. No
user-global trust or permission configuration was changed.

The final version-only probe returned `codex-cli 0.158.0`; the fetched official
changelog still ended at 0.157.1. Initial help/parser observations remain 0.154.0
evidence. This work did not invoke an upgrade.

Loom was read-only. Its port guidance, source map, acceptance matrix, patches,
file hashes and final dev/cleanup receipts are in the user-requested work-consol
pickup. Loom's extra filters, handlers, variants and ownership validators need
their own targeted port; this repository's checks do not certify that repository.

## Follow-up runtime verification

The subsequent [live verification receipt](LIVE-VERIFICATION.md) supersedes the unrun status above for the specific native paths it exercised. It also records the timeout defect discovered after this original gate, its fix and repeat checks. Preserve the original gate evidence rather than retroactively treating it as live certification.
