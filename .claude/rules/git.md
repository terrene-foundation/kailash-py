---
priority: 0
scope: baseline
---

# Git Workflow Rules

<!-- slot:neutral-body -->

## Conventional Commits

```
type(scope): description
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

```
feat(auth): add OAuth2 support
fix(api): resolve rate limiting issue
```

**Why:** Non-conventional commits break automated changelog generation and make `git log --oneline` useless for release notes.

## Branch Naming

Format: `type/description` (e.g., `feat/add-auth`, `fix/api-timeout`)

**Why:** Inconsistent branch names prevent CI pattern-matching rules and make `git branch --list` unreadable across contributors.

### Release-Prep PRs MUST Use `release/v*` Branch Convention (MUST)

Any PR whose diff is metadata-only — version anchors (`pyproject.toml` / `Cargo.toml`, `__init__.py::__version__` / lib.rs `pub const VERSION`), `CHANGELOG.md`, spec/doc version-line updates, and CHANGELOG-paired spec updates — MUST be opened from a branch named `release/v<X.Y.Z>`. Using `feat/`, `fix/`, `chore/`, or any other prefix on a release-prep PR is BLOCKED.

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

**BLOCKED rationalizations:**

- "feat/ is more descriptive of the work"
- "I'll fold real code changes into the release-prep PR, so it's not metadata-only"
- "The branch name doesn't matter, the diff does"
- "Convention is too rigid — every PR is unique"
- "Skipping CI on a release feels unsafe"

**Why:** Every PR-gate workflow that adopts the `ci-runners.md` § "MUST: Release-prep skip" pattern checks `if: !startsWith(github.head_ref, 'release/')`. Branching from `release/v*` triggers the auto-skip and saves ~45 min × matrix-size of CI minutes per release-prep PR. Branching from anything else burns the full PR-gate matrix on a diff that has no code surface to verify. Evidence: kailash-rs PR #602 (2026-04-25) used `feat/v3.23.0-release-prep` and consumed ~73 min of GitHub-billable runner time on a metadata-only diff that should have skipped to ~0 min. The cross-reference exists in `ci-runners.md` but is path-scoped to `.github/workflows/**`, so it does not load when an agent is choosing a branch name. This clause cross-references the rule from `git.md` (always-loaded baseline) so branch-naming decisions surface the cost lever.

**If the release-prep work IS NOT metadata-only** (e.g., folds in a code fix as part of the same PR), split: keep the code fix on a `feat/` or `fix/` branch with its own PR; cut the release-prep on a separate `release/v*` branch that only updates anchors + CHANGELOG. Two PRs, one with full CI, one near-zero.

Origin: 2026-04-25 kailash-rs session — PR #602 (release-prep for v3.23.0) was opened from `feat/v3.23.0-release-prep`, burning ~120 min of avoidable PR-gate CI on a metadata-heavy diff that bundled #599 + #600 fixes with version bumps. The cost was foreseeable from `ci-runners.md` MUST Rule 8 but the rule's path-scoping prevented it from loading at branch-name-decision time.

### Pre-FIRST-Push CI Parity Discipline (MUST)

Before the FIRST `git push` that creates a remote branch (which opens the door to PR-gate CI), the agent MUST run the project's local CI parity command set. The discipline already exists in language-specific rules (`build-speed.md` § "Run Full CI Job-Set Locally Before Admin-Merge" for Rust; equivalents for Python: `pre-commit run --all-files` + `mypy --strict` + `pytest`) — this clause extends the same gate to the FIRST push, not just admin-merge.

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

**BLOCKED rationalizations:**

- "I'll let CI catch the issue and fix it on the next push"
- "Running all local commands takes too long"
- "concurrency: cancel-in-progress will cancel the prior run"
- "The fix-up cycle is what CI is for"
- "I'll batch the fix-ups before merging — same total cost"
- "Local toolchain mismatches will trigger false positives anyway"

**Why:** Each push to an open PR retriggers the full PR-gate matrix. With `concurrency: cancel-in-progress: true` on the workflow, prior in-flight runs are cancelled — but **the cancelled runs are still billed for the wall-clock minutes already consumed before cancellation**. kailash-rs PR #598 (2026-04-25) had a 71-minute Workspace Tests run cancelled mid-flight by a fix-up push; those 71 min were charged. Pre-flighting the local commands takes ~5-10 minutes once + amortized seconds on incremental re-runs; the alternative is N × 45 min of billed CI per fix-up cycle. Local discipline is strictly cheaper. The rule extends to the FIRST push because by the time admin-merge is invoked, every previous fix-up cycle has already burned billable minutes.

Origin: 2026-04-25 kailash-rs session — PR #598 cycle of 5 sequential pushes (08:43Z → 10:14Z) caused 71 min of cancelled-but-billed Workspace Tests. The mid-flight cancellation was triggered by `concurrency: cancel-in-progress: true` (correctly enforced) but the billing meter does not refund cancelled-mid-run minutes.

## Branch Protection

All protected repos require PRs to main. Direct push is rejected by GitHub.

**Why:** Direct pushes bypass CI checks and code review, allowing broken or unreviewed code to reach the release branch.

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

## PR Description

CC system prompt provides the template. Additionally, always include a `## Related issues` section (e.g., `Fixes #123`).

**Why:** Without issue links, PRs become disconnected from their motivation, breaking traceability and preventing automatic issue closure on merge.

## Rules

- Atomic commits: one logical change per commit, tests + implementation together
- No direct push to main, no force push to main
- No secrets in commits (API keys, passwords, tokens, .env files)
- No large binaries (>10MB single file)
- Commit bodies MUST answer **why**, not **what** (the diff shows what)

**Why:** Mixed commits are impossible to revert cleanly, leaked secrets require immediate key rotation across all environments, and large binaries permanently bloat the repo since git never forgets them. Commit bodies that explain "why" are the cheapest form of institutional documentation — co-located with the code, versioned, searchable via `git log --grep`, and never stale (they describe a point in time). See 0052-DISCOVERY §2.10.

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

## Issue Closure Discipline

Closing a GitHub issue as "completed" MUST include a commit SHA, PR number, or merged-PR link in the close comment. Closing with no code reference is BLOCKED.

```bash
# DO — close with delivered-code reference
gh issue close 351 --comment "Fixed in #412 (commit a1b2c3d)"
gh issue close 370 --comment "Resolved by PR #415 — kailash 2.8.1"

# DO NOT — close with no code proof
gh issue close 351 --comment "Resolved"
gh issue close 374 --comment "Covered by recent refactor"
```

**BLOCKED rationalizations:**

- "Already covered in another PR"
- "Will reference later"
- "Obsoleted by refactor"
- "Resolved without code change"

**Why:** Issues closed with zero delivered code references break traceability; the next session cannot verify whether the fix actually shipped.

## Pre-Commit Hook Workarounds

When pre-commit auto-stash causes commits to fail despite hooks passing in direct invocation, the workaround `git -c core.hooksPath=/dev/null commit ...` MUST be documented in the commit body, AND a follow-up todo MUST be filed against the pre-commit configuration. Silent re-tries with `--no-verify` are BLOCKED.

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

**BLOCKED rationalizations:**

- "Hooks passed when I ran them manually"
- "--no-verify is faster and the CI will catch it"
- "The auto-stash bug is a known issue"

**Why:** Recurring across sessions; without documentation each session re-discovers the workaround at high cost. With documentation the next agent finds it via `git log --grep`.

## Commit-Message Claim Accuracy

Commit bodies MUST describe ONLY changes actually present in the diff. Claiming a refactor, deletion, or side-effect that the diff does NOT contain is BLOCKED. If the claim was made in error, push a FOLLOW-UP commit that actually does what the prior message said — do NOT amend, do NOT ignore.

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

**BLOCKED rationalizations:**

- "No one reads commit bodies anyway"
- "The claim describes the intent, the diff is close enough"
- "I'll amend it in a follow-up that actually does the refactor"
- "The body describes the PR as a whole, not this specific commit"
- "Over-claiming is better than under-claiming"

**Why:** `git log --grep` is the cheapest institutional-knowledge search across a repo — a body that claims something the diff doesn't contain poisons every future search that lands on it. The next session reads "dropped the warning-suppression" in the log, assumes it happened, and bases later decisions on a diff that never existed. Amending is BLOCKED because it loses the audit trail of the over-claim; a follow-up commit preserves both the original claim AND the correction so anyone tracing the history sees the full sequence.

Origin: 2026-04-20 kailash-rs self-correction — a commit body claimed "also dropped the `let _ = second_start;` warning-suppression" but the actual diff only contained the MAX_PARAMS clamp. Caught during self-verification; follow-up commit truly dropped the binding. Cross-language principle — applies to every SDK and every language; `git log --grep` accuracy is universal.

<!-- /slot:neutral-body -->
