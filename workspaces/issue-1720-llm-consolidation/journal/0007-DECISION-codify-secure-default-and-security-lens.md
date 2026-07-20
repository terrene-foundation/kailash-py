# DECISION — /codify: secure-default (security.md) + correctness-clean≠security-clean (agents.md)

Date: 2026-07-20. Repo class: BUILD (`name = "kailash"`). Author: agent (codify
receipt; the DECISION to codify was user-approved — "approved" — the clause content
is agent-derived from this session's redteam). Coordination OFF (un-enrolled public
repo). Codify lease HELD: `codify/jack-hong-2026-07-20` (scope covers security.md +
agents.md + latest.yaml + learning-codified.json).

## What was codified

Two institutional lessons from the Wave-B/3 EATP session that delivered kailash
2.58.0 / kailash-pact 0.16.0+0.16.1 / kailash-kaizen 2.38.0 (all PyPI-verified):

**1. `.claude/rules/security.md` — new section "Secure-Default For A New Security
Feature — Fail-Closed Or Loud-WARN, Never A Silent No-Op".** A NEW security feature
gated behind a config field / kwarg / injected dependency whose DEFAULT makes it a
SILENT NO-OP is a fail-OPEN default: the release ships the protection's headline claim
while every deployment that adopts the surrounding release without wiring the flag
believes it is protected and is not. The default MUST be either (a) fail-CLOSED (feature
ON by default, opt-out explicit) OR (b) — when backward-compat genuinely forbids
on-by-default (the feature needs a key/store/identity a pre-upgrade caller has not
wired) — a LOUD one-time WARN at init/first-use naming the OFF protection + the exact
wiring. Silent no-op with neither is BLOCKED.

**2. `.claude/rules/agents.md` — new § Quality-Gates section "MUST: Correctness-Review-
Clean Is Not Security-Clean".** A correctness / closure-parity reviewer returning CLEAN
is NOT evidence a change is SECURITY-clean — the two lenses find DISJOINT defect classes.
A security-critical change (auth, crypto-signing, revocation, tenant-isolation, a
fail-closed gate, any trust-boundary) MUST be redteamed by BOTH a correctness reviewer
AND an adversarial `security-reviewer` prompted to REFUTE, both returning a genuine
ran-signal, before convergence. Counting a correctness-clean verdict AS the security
round — or dispatching only a correctness reviewer — is BLOCKED.

Both clauses ship WITH canonical-8-field clause-scoped Trust Posture Wiring (grace
2026-07-20 → 2026-07-27); `posture.json::pending_verification = [security, agents]`.

## Why (the evidence — the same session, twice)

- **secure-default recurred TWICE, both caught by an ADVERSARIAL /redteam, neither by
  the feature's own tests:** pact 0.16.0 `McpGovernanceConfig.require_caller_identity`
  defaulted `False` (a deployment sets `tenant_grants`, forgets `caller_identity`,
  trusts the body tenant → zero isolation) → flipped to `True` (fail-closed), #1843;
  kailash 2.58.0 `TrustOperations(revocation_verifier=None)` skipped the signed-ledger
  gate for every un-wired caller with no signal → kept `None` for backward-compat + added
  the one-time WARN, #1842-S3.
- **correctness ≠ security:** on #1842-S3 the correctness/closure-parity reviewer returned
  CLEAN (13/13 tests, all 3 ACs MET, "Fixes #1842" justified — ground truth PR #1872 +
  commit 555875899); the adversarial security-reviewer, run in the SAME round, caught a
  CRITICAL revocation-resurrection bypass (deleting one `revocation_head.json` file
  silently un-revoked everything) + a HIGH non-monotonic high-water regression + the
  `revocation_verifier=None` fail-open — none of which the correctness lens saw.

## Alternatives considered

- **Memory vs COC artifact:** rejected memory — both lessons are cascade-valuable,
  cross-SDK, and apply to every agent (per knowledge-cascade-routing MUST-1). Routed to
  rules via /codify + a BUILD→loom proposal.
- **One combined clause vs two:** kept separate — the secure-default is a code-surface
  contract (security.md); the two-lens gate is an orchestration-review contract (agents.md).
  Distinct surfaces, distinct detection.
- **Local baseline edit vs proposal-only:** made the local edits (BUILD repo, immediate
  use) WITH full wiring already authored, unlike the prior grandfathered security.md/git.md
  entries which were proposal-only — because agents.md is on the self-referential-codify
  allowlist, mandating the local-edit + multi-agent redteam this session ran.

## Gate satisfaction

Self-referential-codify Rule 1 (agents.md is allowlisted): MANDATORY 3-lens PARALLEL
redteam ran against the proposal + this receipt + originating #1842-S3/#1843 evidence.
Verdict NO BLOCKER (3/3): CODIFY-rev PASS (rule-authoring compliance + evidence verified
against origin/main @ ca5ea6cd8); CODIFY-sec no-BLOCKER (guidance sound, disclosure grep
0 matches); CODIFY-arch PASS (canonical 8/8 fields, Violation-scope anchor present).
Two non-blocking tightenings applied: secure-default Detection now requires interrogating
whether fail-closed was genuinely infeasible before accepting the WARN path; the new clause
named in security.md's length-rationale enumeration.

## Follow-up

- BUILD→loom proposal appended (`.claude/.proposals/latest.yaml`, pending_review); Rule-10
  proximity-band headroom check is a loom Gate-1 action (BUILD emit.mjs unrunnable).
- Anchor advanced 2026-07-19T12:53:58Z → 2026-07-20T07:41:49Z.
- Carry-forward (fresh session): #1841-S2b, #1846 (BLOCKED on rs#1990), DQ backlog.
