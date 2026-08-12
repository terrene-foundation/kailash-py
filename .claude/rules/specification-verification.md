---
priority: 10
scope: path-scoped
cli_delivery: skill-channel
paths:
  - "**/*.py"
  - "**/*.rs"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.mjs"
  - "**/*.rb"
  - "**/*.go"
  - "**/*.sh"
  - "**/*.sql"
  - "**/*.md"
  - "**/*.yml"
  - "**/*.yaml"
  - "**/*.toml"
  - "**/*.json"
  - "**/.github/workflows/**"
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
# DO — re-derive, name the instrument, and reconcile when two disagree
git grep -nE 'detail=str\(e\)|detail=str\(exc\)' origin/main \
  -- src packages ':!*/build/*' ':!*/tests/*' | wc -l        # 25 — but 1 is a .md doc example,
                                                             # so 24 PRODUCTION .py sites (issue filed 24)
# DO NOT — implement against the issue's stated count
"Fixing the 24 sites listed in the issue."   # the count was never re-measured, and the
                                             # f-string spelling is a 25th the issue's grep cannot see
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
chose the helper deliberately" / "the test I wrote to the AC passes" / "it's strictly better than
nothing". Full corpus: extract. (The test clause is the CIRCULAR case — a test written to the AC
cannot falsify the AC. A green test from an INDEPENDENT oracle is ordinary evidence; nothing here
licenses distrusting green tests generally.)

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

"Re-measured: 24 production sites, as filed — plus a 25th the issue's grep cannot see
(f-string spelling). Split is 1 auth-path / 24 other — the 'auth path worst'
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
- **Detection mechanism:** scanner `null` — probe-only by construction, NOT by deferral: whether a
  number was MEASURED or COPIED leaves no lexical trace, so a structural scanner over the transcript
  would be the non-discriminating instrument `instrument-discipline.md` MUST-1 blocks. Fixtures
  `.claude/audit-fixtures/specification-verification/` (4 bipolar efficacy pairs, one per MUST, plus
  a surface-matched meta pair; each `.expected` is the reviewer's expected disposition). Probes
  `.claude/test-harness/probes/specification-verification.probes.json` — 10 rows / 5 pairs, registered
  probe-only (`scanner: null`) in `.claude/test-harness/eval-manifest.json`, dispatched at gate-review
  via `/test-harness-probe --artifacts` (`halt-and-report`; the semantic tier is deliberately not in
  CI — the loom↔csq boundary keeps CI LLM-free, so a green CI run is never evidence the probes
  passed). Phase 1 (manual, gate-review) — reviewer at `/implement` inspects any session implementing
  from an issue/AC/brief and confirms (a) the load-bearing claims were re-derived with a cited
  command, (b) any prescribed remedy was exercised against the named threat input before adoption,
  (c) any divergence was posted back to the specification. Phase 2 (hook detector) is NOT deferred —
  it is declined, on the discrimination ground above.
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
worst" where 1 site is auth and 10 unauthenticated routes leak DSNs, and its grep cannot see a 25th
site (f-string spelling). **#1997** framed as per-key probability what is actually preset-dependence, all four vendors
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

**Redteam receipt (Tier-1 self-referential, 2026-08-10).** Three agents — cc-architect, reviewer,
analyst — audited the first draft. **The rule failed its own MUST-1 in three places** and was
amended before merge: a fabricated comparand ("the 27 filed" — the issue filed 24), an internal
24-vs-25 contradiction, and two wrong replacement line numbers for #2013 (4813/4826; actual
4814/4825, with 4782 a status-dict key rather than any method). One reviewer correction was ITSELF
wrong — `base_agent.py` re-derived to 728/735/744, not the 734/743 proposed — so the amendments here
are the orchestrator's own re-derivation, not the redteam's numbers taken on trust. That is the rule
working on itself, and it is the strongest evidence for MUST-1 in the file.

**Scope verdict — path-scoped, MEASURED not assumed (2026-08-12).** The open question on PR #2031
was whether this ships `priority: 0` + `scope: baseline` instead. Both halves were tested rather
than argued.

_Budget._ `node .claude/bin/emit.mjs --all --dry-run` at this branch's base (`21deef321`) reports
11 baseline rules, 53168 B per lane, **13.46% headroom on codex and gemini** — already inside Rule
10's 15% proximity band, with 2128 B of slack above the 10% BLOCK floor. Re-running the identical
command with this file's frontmatter flipped to `priority: 0` / `scope: baseline` returns 12 rules,
61465 B, and **-0.04% headroom — a hard `headroom-floor BLOCK`, 6169 B under the floor** on both
lanes. Baseline is not "expensive here"; it is refused by the emitter, and would land only paired
with ~8.3 KB of extraction out of the other eleven baseline rules. The falsifying result is named:
a post-promotion headroom at or above 15% would have removed the budget objection entirely.

_Reachability._ The `issue-triage-routing.md` precedent applies when a rule's trigger moment matches
NO glob — a `gh issue` triage touches zero files. This rule's trigger is not that shape. MUST-1/2/3
have a subject only when something is IMPLEMENTED from the specification, and implementation
terminates in a file edit; the `paths:` list above was widened in `ee8274122` to md/yml/yaml/toml/
json/sh/sql/tsx/jsx + workflows precisely so the YAML-only CI case (#2023) matches. **Residual gap,
stated rather than glossed:** a MUST-4-only session — one that measures a contradiction with Bash
and `gh` alone, posts the correction, and edits no file — matches no glob and does not load this
rule. Closing it costs ~200 B of pointer inside an already-loaded baseline rule, which fits the
measured 2128 B slack but fires Rule 10's gate and therefore needs its own paired-extraction or
named-rationale receipt; that is a separate shard, not a silent omission here.

**Length rationale (per `rule-authoring.md` MUST NOT § "Rules longer than 200 lines").** 270 lines
(`wc -l`, re-derived at this edit — the prior "~217" was measured before the Detection-mechanism and
Scope-verdict blocks landed and is corrected here rather than carried, MUST-1 applied to this file's
own claim about itself). Named rationale: **four-clause contract with a mandated 8-field Wiring** —
each MUST carries the DO/DO-NOT + verbatim BLOCKED phrases + `**Why:**` the meta-rule requires, and
the canonical Trust-Posture Wiring is non-decomposable. All worked cases, the full BLOCKED corpora,
the per-issue evidence table, and the scanner-findings corollary are already EXTRACTED to
`guides/rule-extracts/specification-verification.md`; the residual is load-bearing clause text plus
the two receipt blocks (§ Redteam receipt, § Scope verdict) that record how the open questions were
settled. `priority: 10` + `scope: path-scoped`, so it pays NO baseline-emission cost and Rule 10's
proximity-band gate does not fire — measured, see § Scope verdict. Sibling precedent:
`upstream-issue-hygiene.md` + `wave-loop.md`.
