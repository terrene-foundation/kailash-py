# RISK — Operator-local CI value file committed to the public repo (disclosure #260/#252)

Date: 2026-07-09
Phase: 05-codify / re-convergence #9 (/redteam)
Severity: HIGH (disclosure-hygiene violation on a PUBLIC remote; content is infra
identifiers — hostnames + a self-hosted runner label — NOT credentials/secrets)
Status: FORWARD-FIXED in working tree; TWO user-gated/follow-up tails OPEN (see below)

## What was found

`.claude/rules/ci-runners.operator.local.md` — a file whose own header declares
"**Gitignored — never committed, never synced** (issue #260 / #252)" — is in fact
**tracked and committed** to `git@github.com:terrene-foundation/kailash-py.git` (a PUBLIC
repo). It has been on `origin/main` since commit `e6144ee98` (2026-05-18, ~7 weeks).

It carries this operator's real self-hosted CI infrastructure identity (3 hostnames + a
runner label) — referenced here by location only, NOT reproduced (security.md § no-secrets):
`ci-runners.operator.local.md:17-19, :27, :33, :37`.

Two safety nets that should have caught this were BOTH absent:

1. **`.gitignore` had no pattern** for `.claude/rules/*.operator.local.md` (the sibling
   operator-local file `loom-links.local.json` IS gitignored; this class was simply missing).
2. **The disclosure scanner structurally skips it.** `scan-synced-disclosure.mjs:276`
   `if (/\.operator\.local\.md$/.test(base)) return true;` is UNCONDITIONAL — whereas the
   sibling `.local.json` skip one line below was deliberately made
   `REPO_ROOT_ACTIVE === REPO_ROOT`-conditional (issue #352) precisely so a committed copy
   at a destination IS caught. The `.operator.local.md` skip never received that parity fix,
   so the scanner reports "0 findings" while blind to this exact file. (A second skip,
   `/\.local\.md$/`, ALSO matches it.)

## Why 8 prior re-convergence rounds missed it

The file resolves to a _real_ gitignore-intent + a scanner self-skip, so no dangling-ref or
scanner sweep ever flagged it; prior rounds trusted the "gitignored" assertion and the
scanner's clean exit. Surfaced in #9 only by an adversarial disclosure agent that verified
tracked-status directly (`git ls-files --error-unmatch` exit 0, `git check-ignore` exit 1)
rather than trusting the file's self-description — the evidence-first-claims MUST-3 discipline
(an errored/blind detector is NOT an all-clear).

## Forward-fix applied this session (safe, reversible — working tree only, NOT committed)

- `.gitignore` — added `.claude/rules/*.operator.local.md` (glob correctly covers the real
  file; the committed `*.operator.local.example.md` schema sibling stays tracked — verified
  via `git check-ignore`).
- `git rm --cached .claude/rules/ci-runners.operator.local.md` — untracked (staged deletion);
  local copy preserved on disk; reversible with `git reset`.

## OPEN tails (NOT done this session)

1. **Public git-history purge — USER-GATED (irreversible).** The tip untrack does NOT remove
   the file from the ~7 weeks of public history. True remediation = `git filter-repo`/BFG +
   force-push to `origin/main`, which rewrites shared public history (every clone/fork must
   re-sync). Held for explicit owner go-ahead. Optionally rotate the runner labels/hostnames.
2. **Scanner parity fix — deferred to its own gated codify.** Making
   `scan-synced-disclosure.mjs` catch a _committed_ `.operator.local.md` (e.g. skip it ONLY
   when NOT git-tracked) is the root-cause structural fix, but `scan-synced-disclosure.mjs` is
   on the `self-referential-codify.md` allowlist (multi-agent gate) AND is a loom-distributed
   tool with subtle loom-source-vs-destination semantics — it needs its own careful codify +
   loom coordination, not an autonomous slip-in.

## Recommendation

Land the forward-fix (untrack + gitignore) via the normal /codify → codify-branch → PR path;
schedule the history purge + the scanner-parity codify as deliberate follow-ups. The gitignore
pattern restores the never-commit discipline the scanner's skip already assumes.
