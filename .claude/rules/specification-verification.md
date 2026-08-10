---
priority: 10
scope: path-scoped
cli_delivery: skill-channel
paths:
  - "**/*.py"
  - "**/*.rs"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.mjs"
  - "**/*.rb"
  - "**/*.go"
---

# Specification Verification — An Acceptance Criterion Is A Hypothesis, Not A Measurement

A GitHub issue, acceptance criterion, brief, plan, or hand-off note is a **claim about the code
written by someone who may not have measured it** — often before the investigation, often from a
scanner that models one shape, often from a prior session's compaction summary. Implementing it
faithfully is therefore not safe: a faithful implementation of an unmeasured specification ships a
**faithful wrong fix**, closes the issue, and records the class as handled.

The failure is quiet by construction: the fix matches the AC, the test written to the AC passes, and
the reviewer checks the diff against the AC — every gate agrees, because all of them inherit the same
unverified premise. Depth + the full BLOCKED corpora: `.claude/guides/rule-extracts/specification-verification.md`.

## MUST Rules

### 1. Re-Measure Every Load-Bearing Factual Claim Before Implementing

Before writing the fix, independently re-derive every claim in the specification that the fix
depends on: site counts, file paths, line numbers, class/function names, "which branch", "N of M",
severity, and the named root cause. Cite the command and its output. Inheriting the spec's numbers
is BLOCKED; so is inheriting them because they were "verified when filed".

```bash
# DO — re-derive, and say what the instrument was
git grep -nE 'detail=str\(e\)' -- src packages ':!*/tests/*' | wc -l   # 24, not the 27 filed
# DO NOT — implement against the issue's stated count
"Fixing the 27 sites listed in the issue."   # the count was never re-measured
```

**BLOCKED rationalizations:** "the issue says N" / "it was measured when filed" / "the reporter
works on this code" / "the AC is the contract, not a claim" / "a prior session already verified
this". Full corpus: extract.

**Why:** Counts and line numbers decay with every merge, and many were never measured at all; a fix
scoped to a stale enumeration closes the issue while leaving live instances of the exact defect.

### 2. Validate The PRESCRIBED Fix Against The NAMED Threat Before Implementing It

When a specification prescribes a remedy ("route through helper H", "add guard G"), you MUST first
demonstrate that the remedy actually defeats the failure the specification names — run the threat
input through the prescribed remedy and observe the result. A remedy that does not close the named
threat MUST NOT be implemented merely because the AC requires it; correct the AC (MUST-4) and
implement what closes the threat.

```python
# DO — test the prescribed remedy against the issue's own threat example first
mask_error_text("spawn 'npx --token=sk-live-ABCDEF123456' not in allowlist")
# -> token STILL PRESENT: the helper masks URL userinfo/query, not CLI flags. AC#1 is wrong.
# DO NOT — implement the AC's remedy and let the AC's test define success
detail = mask_error_text(str(e))   # looks fixed, still leaks, test written to AC passes
```

**BLOCKED rationalizations:** "the AC specifies the fix, my job is to implement it" / "the reporter
chose the helper deliberately" / "the test passes" / "it's strictly better than nothing". Full
corpus: extract.

**Why:** A prescribed-but-ineffective remedy is worse than no fix — it produces a green test, a
closed issue, and a documented belief that the class is handled, so no one looks again.

### 3. Re-Derive The Enumeration Instrument; Never Inherit The Spec's Grep

When a specification enumerates instances via a search, you MUST construct your own instrument and
reconcile the two counts. A search inherited from the spec reproduces exactly the blind spots that
produced the spec's number. Per `instrument-discipline.md` MUST-1, state what result would have
falsified the enumeration.

```bash
# DO — build an independent instrument, then reconcile
git grep -nE 'detail=f"[^"]*\{(e|exc|err)\}'    # the f-string spelling the issue's grep cannot see
# DO NOT — re-run the issue's own grep and treat its output as the population
```

**BLOCKED rationalizations:** "the issue's grep is the definition of the class" / "I got the same
number, so it's confirmed" / "a second instrument is redundant".

**Why:** Re-running the spec's own search confirms the spec's blind spot rather than the population —
the same-instrument agreement reads as corroboration while guaranteeing the omitted members stay
omitted (`instrument-discipline.md`).

### 4. When Measurement Contradicts The Specification, CORRECT The Specification

A contradiction between your measurement and the spec MUST be written back to the specification —
as an issue comment, spec edit, or plan amendment — in the same session, with the command and
output. Silently implementing the corrected version is BLOCKED: the next reader re-derives the
original wrong premise, and any sibling work still scoped to it stays wrong.

```markdown
# DO — post the correction, then implement against it

"Re-measured: 25 sites, not 27. Split is 1 auth-path / 24 other — the 'auth path worst'
framing points at 1 site while 10 unauthenticated routes leak DSNs. [command + output]"

# DO NOT — quietly fix the right thing and leave the issue asserting the wrong thing
```

**BLOCKED rationalizations:** "the code is what matters, not the issue text" / "I'll note it in the
PR" / "the issue closes anyway" / "correcting it is bookkeeping".

**Why:** The specification outlives the fix and is what the next session, the sibling issue, and the
audit trail all read; an uncorrected spec re-seeds the same wrong implementation elsewhere.

## MUST NOT

- Implement from an acceptance criterion whose factual claims have not been re-derived this session

**Why:** The originating failure mode — every downstream gate inherits the unverified premise, so
none of them can catch it.

- Treat a scanner finding's framing (severity, mechanism, location) as the defect's actual shape

**Why:** A scanner reports what its queries model; it flags reachable-and-modelled lines, not risky
ones — repeatedly, here, it named a harmless sink while missing the real leak nearby.

- Close an issue as fixed when the fix addressed the AC rather than the failure the AC describes

**Why:** That is the fixed-wrongly-and-recorded-handled state this rule exists to prevent; the class
stays open with a closed ticket in front of it.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at gate-review (reviewer at `/implement` + cc-architect at
  `/codify` confirm the session re-derived the spec's load-bearing claims, validated any prescribed
  remedy against the named threat, and posted a correction where measurement diverged); `advisory`
  at the hook layer per `hook-output-discipline.md` MUST-2 — whether a claim was re-measured is
  judgment-bearing over session history, with no structural tool-call-time signal.
- **Grace period:** 7 days from rule landing (2026-08-10 → 2026-08-17).
- **Cumulative posture impact:** same-class violations (implementing against an un-re-derived count
  or root cause; implementing a prescribed remedy without testing it against the named threat;
  leaving a measured contradiction unposted) contribute to `trust-posture.md` MUST-4 cumulative-window
  math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** GENERIC `regression_within_grace` emergency trigger per
  `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated key: whether a claim was re-measured
  is a session-history judgment resolvable only at review, and minting a key would drag
  `trust-posture.md` (a `self-referential-codify.md` allowlist file) into a self-referential edit.
  Named deviation per `trust-posture.md` Rule 8; same disposition `security.md` § Enforcement-Surface
  Parity took.
- **Receipt requirement:** SessionStart soft-gate `[ack: specification-verification]` IFF
  `posture.json::pending_verification` includes the `specification-verification` rule_id.
- **Detection mechanism:** Phase 1 (manual, gate-review) — reviewer at `/implement` inspects any
  session implementing from an issue/AC/brief and confirms (a) the load-bearing claims were
  re-derived with a cited command, (b) any prescribed remedy was exercised against the named threat
  input before adoption, (c) any divergence was posted back to the specification. Phase 2 (deferred
  per `trust-posture.md` § Two-Phase Rollout) — no hook detector; a lexical detector cannot see
  whether a number was measured or copied. Audit fixtures land with the Phase-2 detector at
  `.claude/audit-fixtures/specification-verification/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST-1 (un-re-derived factual claims) + MUST-2 (prescribed remedy adopted
  untested against the named threat) + MUST-3 (inherited enumeration instrument) + MUST-4 (measured
  contradiction left unposted).
- **Origin:** See § Origin.

## Distinct From / Cross-References

- **Consumer-side sibling of `spec-accuracy.md`** — that governs what a spec may CONTAIN when
  authored; this governs what you verify before acting on one. Its `paths:` never match a GitHub
  issue, where most originating instances lived.
- **Applies `instrument-discipline.md` at the specification surface** — MUST-3 asks that rule's
  falsification question of the spec's own enumeration.
- **Inverse of `verify-claims-before-write.md`** — that governs code-claims you WRITE into a durable
  artifact; this governs claims you READ out of one and act on.
- **Feeds `product-completion-first.md`** — re-derivation precedes category classification.

## Origin

2026-08-10 — a kailash-py burn-down session. Five issues were found to have wrong SPECIFICATIONS
rather than wrong code, each of which a diligent session would have implemented faithfully and
closed wrongly:

**#2004** prescribed a remedy that provably does not redact the credential it was filed about —
tested, `mask_error_text` leaves `--token=sk-live-…` intact, and no scrubber in the monorepo covered
CLI-flag form. **#2006** blamed a branch its own repro does not take. **#2015** claimed "auth path
worst" where 1 site is auth and 10 unauthenticated routes leak DSNs, and its grep cannot see a 26th
site. **#1997** framed as per-key probability what is actually preset-dependence, all four vendors
leaking where nothing tested. **#2022** named a missing kwarg rather than the swallow that
misreports it. Three more carried stale counts or line numbers (#2013, #2023, #2002).

MUST-2's evidence is the sharpest: following the specification exactly is what produces the
vulnerability. Per-issue evidence table, worked cases, and the scanner-findings-are-specifications
corollary: extract.

Co-owner directive on codification: _"the wrong specifications is very disturbing and destructive, I
need you to /codify it so that this will never recur."_

**Self-referential-codify disposition (recorded per the omission-precedent shape).** This rule is
DELIBERATELY NOT added to `self-referential-codify.md` Rule 2's allowlist. It fires on ALL
implementation work in ALL sessions — it is a universal implementation-quality rule, not a
codify-class surface — which is the same disposition `zero-tolerance.md` carries and for the same
stated reason. It governs how a session consumes a specification, not how codification itself
operates, so a `/codify` touching it is not modifying a gate that `/codify` runs through.
