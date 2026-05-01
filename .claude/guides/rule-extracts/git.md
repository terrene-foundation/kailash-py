# Git Workflow Rules — Extended Evidence and Examples

Companion reference for `.claude/rules/git.md`. Extended examples, BLOCKED rationalization lists, full Origin prose, and audit evidence.

The rule file keeps the load-bearing MUST clauses + one DO/DO-NOT pair each + a one-line Why. Everything else lives here so the always-loaded baseline stays under its per-CLI byte cap.

## Release-Prep PRs MUST Use `release/v*` Branch Convention

### Extended example

```bash
# DO — release-prep branch auto-skips PR-gate matrix
git checkout -b release/v3.23.0
# Bump versions, update CHANGELOG, edit spec anchors, push
git push -u origin release/v3.23.0
gh pr create --title "release(v3.23.0): ..."

# DO NOT — feat/ branch fires the full PR-gate matrix on metadata-only diff
git checkout -b feat/v3.23.0-release-prep
# Same diff, but PR-gate jobs (~45 min × N CI cycles) all execute
# because workflows' `if:` clauses evaluate `!startsWith(head_ref, 'release/')`
# to TRUE.
```

### BLOCKED rationalizations

- "feat/ is more descriptive of the work"
- "I'll fold real code changes into the release-prep PR, so it's not metadata-only"
- "The branch name doesn't matter, the diff does"
- "Convention is too rigid — every PR is unique"
- "Skipping CI on a release feels unsafe"

### Why (extended)

Every PR-gate workflow that adopts the `ci-runners.md` § "MUST: Release-prep skip" pattern checks `if: !startsWith(github.head_ref, 'release/')`. Branching from `release/v*` triggers the auto-skip and saves ~45 min × matrix-size of CI minutes per release-prep PR. Branching from anything else burns the full PR-gate matrix on a diff that has no code surface to verify. Evidence: kailash-rs PR #602 (2026-04-25) used `feat/v3.23.0-release-prep` and consumed ~73 min of GitHub-billable runner time on a metadata-only diff that should have skipped to ~0 min. The cross-reference exists in `ci-runners.md` but is path-scoped to `.github/workflows/**`, so it does not load when an agent is choosing a branch name. The clause cross-references the rule from `git.md` (always-loaded baseline) so branch-naming decisions surface the cost lever.

### Split discipline

If the release-prep work IS NOT metadata-only (e.g., folds in a code fix as part of the same PR), split: keep the code fix on a `feat/` or `fix/` branch with its own PR; cut the release-prep on a separate `release/v*` branch that only updates anchors + CHANGELOG. Two PRs, one with full CI, one near-zero.

Origin: 2026-04-25 kailash-rs session — PR #602 (release-prep for v3.23.0) was opened from `feat/v3.23.0-release-prep`, burning ~120 min of avoidable PR-gate CI on a metadata-heavy diff that bundled #599 + #600 fixes with version bumps. The cost was foreseeable from `ci-runners.md` MUST Rule 8 but the rule's path-scoping prevented it from loading at branch-name-decision time.

## Pre-FIRST-Push CI Parity Discipline

### Extended example

```bash
# DO — pre-flight ALL local CI commands before first push
# (See language-specific build-speed.md for the full command set)
# Rust: cargo +nightly fmt --all --check; cargo +1.95 clippy --workspace --all-targets -- -D warnings;
#       cargo nextest run --workspace; RUSTDOCFLAGS="-Dwarnings" cargo doc ...
# Python: pre-commit run --all-files; pytest tests/; mypy --strict src/
# All MUST exit 0 → push
git push -u origin feat/<branch>

# DO NOT — push, watch CI, fix-up commit, push again, repeat
git push -u origin feat/<branch>             # CI run #1 starts
# CI fails on fmt drift
git commit -am "style: fmt"
git push                                      # CI run #2 starts (#1 still billing)
# CI fails on doc warnings
git commit -am "fix: doc"
git push                                      # CI run #3 starts (#2 still billing
                                              # IF concurrency: cancel-in-progress
                                              # is not set on the workflow)
```

### BLOCKED rationalizations

- "I'll let CI catch the issue and fix it on the next push"
- "Running all local commands takes too long"
- "concurrency: cancel-in-progress will cancel the prior run"
- "The fix-up cycle is what CI is for"
- "I'll batch the fix-ups before merging — same total cost"
- "Local toolchain mismatches will trigger false positives anyway"

### Why (extended)

Each push to an open PR retriggers the full PR-gate matrix. With `concurrency: cancel-in-progress: true` on the workflow, prior in-flight runs are cancelled — but **the cancelled runs are still billed for the wall-clock minutes already consumed before cancellation**. kailash-rs PR #598 (2026-04-25) had a 71-minute Workspace Tests run cancelled mid-flight by a fix-up push; those 71 min were charged. Pre-flighting the local commands takes ~5-10 minutes once + amortized seconds on incremental re-runs; the alternative is N × 45 min of billed CI per fix-up cycle. Local discipline is strictly cheaper. The rule extends to the FIRST push because by the time admin-merge is invoked, every previous fix-up cycle has already burned billable minutes.

Origin: 2026-04-25 kailash-rs session — PR #598 cycle of 5 sequential pushes (08:43Z → 10:14Z) caused 71 min of cancelled-but-billed Workspace Tests. The mid-flight cancellation was triggered by `concurrency: cancel-in-progress: true` (correctly enforced) but the billing meter does not refund cancelled-mid-run minutes.

## Branch Protection — Repository Table

| Repository                                    | Branch | Protection                                         |
| --------------------------------------------- | ------ | -------------------------------------------------- |
| `terrene-foundation/kailash-py`               | `main` | Full (admin bypass)                                |
| `terrene-foundation/kailash-coc-claude-py`    | `main` | Full (admin bypass) — legacy (archival 2026-10-22) |
| `terrene-foundation/kailash-coc-claude-rs`    | `main` | Full (admin bypass) — legacy (archival 2026-10-22) |
| `terrene-foundation/kailash-coc-py`           | `main` | Full (admin bypass)                                |
| `terrene-foundation/kailash-coc-rs`           | `main` | Full (admin bypass)                                |
| `esperie/kailash-rs`                          | `main` | Full (admin bypass)                                |
| `terrene-foundation/kailash-prism`            | `main` | Full (admin bypass)                                |
| `terrene-foundation/kailash-coc-claude-prism` | `main` | Full (admin bypass)                                |

**New multi-CLI USE repos (`kailash-coc-py`, `kailash-coc-rs`)**: created 2026-04-23 as net-new repos (not rename) per migration r3 directive. Flipped to public + branch protection applied 2026-04-23 (1 approving review required, force-push + deletion blocked, admin bypass retained). Posture matches legacy `kailash-coc-claude-{py,rs}` rows.

**Owner workflow**: Branch → commit → push → PR → `gh pr merge <N> --admin --merge --delete-branch`

**Contributor workflow**: Fork → branch → PR → 1 approving review → CI passes → merge

## `git reset --hard` MUST Verify Clean Working Tree

### Extended examples

```bash
# DO — --keep aborts loudly when working tree has changes
git reset --keep origin/main
# → "error: Entry '.session-notes' not uptodate. Cannot merge."

# DO — verify clean working tree first if --hard is genuinely needed
[ -z "$(git status --porcelain)" ] || { echo "stash or commit first"; exit 1; }
git reset --hard origin/main

# DO — if --hard with modifications present is unavoidable, stash explicitly
# so the work is recoverable from the stash list
git stash push -u -m "pre-reset safety net: <reason>"
git reset --hard origin/main
git stash pop  # restore intentionally; conflicts are loud, recoverable

# DO — for the "I committed on main by accident, want it on a feature branch"
# recovery, the safe sequence is:
git switch -c feat/<name>            # preserve the commit on a new branch
git switch main
git reset --keep origin/main         # back main out — refuses if work would be lost
```

```bash
# DO NOT — bare --hard with no working-tree check
git reset --hard origin/main         # silently wipes M files and untracked files

# DO NOT — assume the reflog covers it
git reset --hard origin/main         # unstaged work has NO reflog; gone forever
```

### BLOCKED rationalizations

- "The tree is clean, I just committed everything I wanted"
- "The reflog will save me"
- "I'm in a fresh worktree, there's nothing to lose"
- "It's only `.session-notes`, not load-bearing"
- "I'll remember to check next time"
- "`--hard` is faster than stashing"
- "`--keep` is unfamiliar, `--hard` is the canonical form"

### Why (extended)

`git reset --hard` is the most destructive git operation that doesn't rewrite history — and unlike force-push, the destruction is unrecoverable: unstaged modifications and untracked files have no reflog. `git reset --keep` exists in git specifically to provide the same commit-graph effect with structural safety; defaulting to `--keep` converts a class of silent data-loss failures into loud "refused — stash first" errors. This rule is the local-git sibling of `dataflow-identifier-safety.md` Rule 4 (DROP requires `force_drop=True`) and `schema-migration.md` Rule 7 (downgrade requires `force_downgrade=True`) — the same structural-confirmation pattern applied to the local-workspace destruction surface.

Origin: kailash-py session 2026-04-28 (PR #691 sync-PR rebase) — `.session-notes` modifications wiped by `git reset --hard 7ce2d2eb` during a "move commit off main" recovery. Content was only recovered because the file had been read into the agent's conversation context earlier in the session; without that, the prior session's hand-off would have been permanently lost. The agent had earlier seen `M .session-notes` in `git status` output but did not re-check working-tree state before the reset. Cross-language principle — applies to every SDK and every language; `git reset --hard` semantics are universal. Sibling destructive ops (`git checkout --force`, `git checkout -- <path>`, `git clean -fd`) are out of scope for this rule per `rule-authoring.md` Rule 6 focus discipline; the system prompt's "destructive operations" guardrail covers them at session level.

## Atomic Commits + Body Discipline — Extended Example

```
# DO — explains why
feat(dataflow): add WARN log on bulk partial failure

BulkCreate silently swallowed per-row exceptions via
`except Exception: continue` with zero logging. Operators
saw `failed: 10663` in the result dict but no WARN line
in the log pipeline, so alerting never fired.

# DO NOT — restates the diff
feat(dataflow): add logging to bulk create

Added logger.warning call in _handle_batch_error method.
Updated BulkResult to emit WARN in __post_init__.
```

Mixed commits are impossible to revert cleanly, leaked secrets require immediate key rotation across all environments, and large binaries permanently bloat the repo since git never forgets them. Commit bodies that explain "why" are the cheapest form of institutional documentation — co-located with the code, versioned, searchable via `git log --grep`, and never stale (they describe a point in time). See 0052-DISCOVERY §2.10.

## Issue Closure Discipline — Extended Examples

```bash
# DO — close with delivered-code reference
gh issue close 351 --comment "Fixed in #412 (commit a1b2c3d)"
gh issue close 370 --comment "Resolved by PR #415 — kailash 2.8.1"

# DO NOT — close with no code proof
gh issue close 351 --comment "Resolved"
gh issue close 374 --comment "Covered by recent refactor"
```

### BLOCKED rationalizations

- "Already covered in another PR"
- "Will reference later"
- "Obsoleted by refactor"
- "Resolved without code change"

## Pre-Commit Hook Workarounds — Extended Example

```bash
# DO — document the bypass in the commit body and file a todo
git -c core.hooksPath=/dev/null commit -m "$(cat <<'EOF'
fix(security): add null-byte rejection to credential decode

Pre-commit auto-stash fails to restore staged changes when
hooks modify the working tree. Bypassed via core.hooksPath=/dev/null.
TODO: fix pre-commit stash/restore interaction (#NNN).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"

# DO NOT — silent --no-verify with no documentation
git commit --no-verify -m "fix(security): add null-byte rejection"
# no record of why hooks were skipped; next session repeats discovery
```

### BLOCKED rationalizations

- "Hooks passed when I ran them manually"
- "--no-verify is faster and the CI will catch it"
- "The auto-stash bug is a known issue"

### Why (extended)

Recurring across sessions; without documentation each session re-discovers the workaround at high cost. With documentation the next agent finds it via `git log --grep`.

## Commit-Message Claim Accuracy — Extended Examples

```bash
# DO — body describes exactly what the diff contains
fix(dataflow): clamp user-SQL $N index at MAX_PARAMS = 65535

Unclamped Vec resize on a parsed `$N` allows a malicious SQL string
containing `$999999999` to trigger a 4GB allocation before PostgreSQL's
int16 rejection fires. Clamp at the parser.

# DO — follow-up commit corrects an earlier over-claiming body
fix(dataflow): actually drop the unused `second_start` binding

The prior commit's body claimed this cleanup but the diff only contained
the MAX_PARAMS clamp. This commit truly removes the unused-binding
suppression.

# DO NOT — claim a change the diff does not contain
fix(dataflow): clamp MAX_PARAMS and drop unused `second_start` binding
# (diff only contains the clamp; the binding is still there)
```

### BLOCKED rationalizations

- "No one reads commit bodies anyway"
- "The claim describes the intent, the diff is close enough"
- "I'll amend it in a follow-up that actually does the refactor"
- "The body describes the PR as a whole, not this specific commit"
- "Over-claiming is better than under-claiming"

### Why (extended)

`git log --grep` is the cheapest institutional-knowledge search across a repo — a body that claims something the diff doesn't contain poisons every future search that lands on it. The next session reads "dropped the warning-suppression" in the log, assumes it happened, and bases later decisions on a diff that never existed. Amending is BLOCKED because it loses the audit trail of the over-claim; a follow-up commit preserves both the original claim AND the correction so anyone tracing the history sees the full sequence.

Origin: 2026-04-20 kailash-rs self-correction — a commit body claimed "also dropped the `let _ = second_start;` warning-suppression" but the actual diff only contained the MAX_PARAMS clamp. Caught during self-verification; follow-up commit truly dropped the binding. Cross-language principle — applies to every SDK and every language; `git log --grep` accuracy is universal.
