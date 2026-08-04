---
owner: esperie
last_reconciled_sha: be97099ce
migrated_from: .session-notes
---

# Session Notes — 2026-08-04 (session D)

## Where we are

Workspace issue-1720-llm-consolidation, phase 05-codify, branch
`fix/issue-1720-forest-drain` @ `0da793e14` — **NOT pushed** (19 commits ahead of
the last push at `66f86b0b5`). Tree clean.

**Release is still HELD.** Round 2 has NOT converged: every round so far found
real defects, so the clean-round counter is at ZERO. Two lanes are mid-round.

## Read first

1. `.wave-tracker.d/esperie.md` § "Wave 8 reconciliation" — what NOT to re-derive.
2. This file's **Traps** + **Pending decisions**.
3. `git log --format='%h %s%n%b' 26a4509b4..HEAD` — every commit body carries its
   own evidence and the reasoning for what was NOT done.

## THE FINDING OF THIS SESSION — read before writing any test

**SIX separate instruments on this branch were cited as proof while being
structurally unable to fail.** Four were mine — including one added to FIX an
attribution problem, which introduced a worse one. This is the recurring defect,
not any individual bug:

1. W19 leak probes — derived from "which characters did we just exclude?". `"`
   was excluded in BOTH the rejected and accepted revision, so it never appeared
   as a DELTA and no probe covered it, while it leaked exactly like the others.
   **A character that SURVIVES a narrowing is invisible to a diff-derived probe.**
2. The `_URL_WITH_USERINFO_ONLY` "proof" — both vectors were fenced by an
   unrelated mechanism (the `:` of a `"<key>":`), so it passed whether or not the
   gap existed. The gap was real; one vector produced UNPARSEABLE output.
3. The dialect no-false-positive test — covered Postgres (63) only. The bug was
   in SQLite (128), numerically identical to the unknown budget. Could never
   have caught it.
4. The #1981 Site-2 fixture — `SimpleNamespace(capabilities=[...])`, a shape no
   production path can emit, with a docstring explaining why it had to be that
   shape. Shaped to the defect.
5. A mutation test that was INERT (string-replace failed on escaping) and stayed
   green — the exact state that reads as "the tests are vacuous".
6. **The 20-cell xfail grid, made INERT by its own attribution guard.** The guard
   `assert rule.search(dsn)` ran BEFORE the leak check, on the shape WITH the
   defect — asserting exactly what the defect makes false. 20/20 stopped at the
   guard, 0/20 ever reached the leak assertion, and since the guard reads a
   COMPILED REGEX the grid behaved identically against a no-op scrubber and a
   perfect one. **Added by me in response to a finding ABOUT attribution.**
   Worse, it was INVERTED at fix time: the sound fix (URL parse) leaves the
   regexes unchanged, so the pins would have stayed XFAIL forever and the
   residual would have read permanently OPEN after being closed — while the
   UNSOUND fix would have made them pass. Fixed by attributing on the PAIR-FREE
   CONTROL, which stays true after either fix. Verified: 20/20 now reach, and
   the grid reads 20-leaking vs 0-leaking across a no-op/perfect scrubber.

**Rule that came out of it: probe what the pattern CLAIMS, not what the patch
CHANGED. And assert the mutation reached the code before reading the result.**

## In-flight state

- Nothing running in the background. Tree clean.
- **Two R2 lanes mid-round**, both asked for a FINAL narrow round vs `0da793e14`.
  Security agreed with the convergence call but bounded its assent to the state
  it reviewed (`6c84f27a5`) plus my attestation; a verified-at-HEAD read is
  requested and PENDING. Correctness expects a strong clean-1 candidate.
- Version anchors UNCHANGED (only nexus at 2.16.0). Decision A/B targets remain
  ratified and verified against ground truth — see below.

## Executed this session (19 commits)

W19 compact-JSON over-redaction fixed, then fixed AGAIN twice as review found
the fix itself leaked (`4fdb37fa2` → `9eb66d893` → `91e9215b1` → `6c84f27a5`).
W12b silent authz default + W13 root cause (`942bdef80`, `b9a0a4ed6`,
`0fce89856`). R2 findings F1/F3/F4/F6 (`0fce89856`, `0e2497b3b`). Residuals
documented + pinned (`73e86016d`, `6c84f27a5`). Tracker corrections
(`7c2c4a4f5`, `116b4830a`).

**Three defects I introduced and review caught:** the `{}\` exclusion (caught by
me), the `"` exclusion leaking quote-bearing credentials (F2), and the
identity-reverse-map collapsing round-robin (F6).

## PENDING DECISIONS — co-owner input needed, both surfaced, neither actioned

1. **`discovery._check_user_access` fail-open.** `TrustOperations.verify()` — the
   checker type the docstring NAMES — takes no `user_id`/`organization_id`/
   `**kwargs` (verified by `inspect.signature`). The call site passes both ⇒
   `TypeError` on the first agent ⇒ caught ⇒ **every agent granted to every user,
   always.** Not transient; the steady state for the documented integration. This
   REFUTES the in-code deferral note's premise. Recommendation: fix call-shape AND
   fail-closed together (either alone is worse). Not actioned because it changes
   behaviour for custom-checker consumers on a public API. Fix design + 7 tests in
   the w8-w12-authz report.
2. **47 unscrubbed `str(exc)` sites across 23 files** in kaizen-agents. The one
   fixed (F3) was chosen because its exception comes from a caller-supplied,
   likely DB-backed checker. Recommendation: own shard, not this branch.

## CARRY-FORWARD from redteam — OPEN, none closed, none release-blocking

Recorded verbatim in the reviewers' framing so the distinctions survive. Each is
correctly OUT of this shard; none is fixed.

1. **F4 — ESCAPED SCHEME: DOCUMENTED, NOT FIXED.** All three URL rules anchor on
   a literal `://`, so a JSON encoder escaping forward slashes (PHP
   `json_encode`, by default) emits `:\/\/` and a real credential leaks IN
   FULL. Verified live. The in-file documentation stops it being SILENT; it does
   not stop it being LIVE. Fix is named in-file so it is not re-derived: a scheme
   group admitting escaped slashes. **Needs its own row.**
2. **F5 — `tools/list` permission filtering: reachability UNVERIFIED IN BOTH
   DIRECTIONS.** The loop filters on `disabled` only, never `required_permission`,
   so this branch widened what a permission-gated tool discloses from
   name+description to its full argument surface. NOT confirmed exploitable and
   NOT confirmed safe — the reviewer never read the transport layer. **Whoever
   picks this up starts at the TRANSPORT read, not the registry.**
3. **F3 — verified BY ME, explicitly NOT reviewer-confirmed.** The three
   `str(exc)` sinks in `discovery.py` are scrubbed and I verified it behaviourally;
   the security lane declared at the time that it did not re-verify. Do not
   record it as a review verdict.
4. **The tempered token's complexity ratio (1.0x) is MY measurement.** The
   reviewer argued the class is structurally unchanged and could NOT measure it
   (no Bash). If that linearity claim is ever cited as reviewed, cite it to me.
5. **REFUTED PROOF — cite as REFUTED if cited at all.** The security lane's
   round-3 "structural proof" that `_URL_WITH_USERINFO_ONLY` needed no fence was
   REFUTED at `be97099ce`, by its own author. The proof enumerated ONE crossing
   shape (`","<key>":`, fenced by its colon) and generalised to "every
   cross-JSON-value crossing". Array elements have NO key and therefore no
   colon, so `{"a":["https://x","d@e.com"]}` crossed freely and returned
   unbalanced, unparseable output. The fence WAS necessary and was added on the
   correctness lane's F1. **If that proof is cited anywhere as
   reviewer-verified, cite it as REFUTED with the array counterexample.** A
   wrong proof is more durable than wrong prose — it reads as settled.
   Instrument #2 in the list above is this one; the refutation is the author's.
6. **CROSS-SDK CONSIDERATION — co-owner decision, NOT self-authorizable.** The
   F2/F7 class (a character-class exclusion in a credential scrubber that fences
   a structural boundary and silently stops claiming real credential shapes) is a
   BUG CLASS, not a bug, and nothing about it is Python-specific.
   `cross-sdk-inspection.md` Rule 1 would normally trigger an inspection of the
   sibling SDK; `repo-scope-discipline.md` makes any sibling-repo read or filing a
   USER-AUTHORIZED action. Neither the agent nor a reviewer can self-authorize it.
   **Surfaced to the co-owner; no action taken.**

## Convergence status — READ BEFORE CLAIMING DONE

**NOT CONVERGED.** Every round so far found real defects, so the clean-round
counter is at ZERO. Two lanes each ran three rounds, each finding strictly less
than the one before, and both are on a final narrow round at `be97099ce`.

**SECURITY LANE: VERIFIED-AT-`be97099ce` — CLEAN, AND THE RECEIPT IS BOUNDED.**
It covers `credential_scrub.py` + its 1974e suite **at `be97099ce` ONLY**. It does
NOT extend to `50fe78c25` (the two prose fixes), which the reviewer has not read.
Both were prose and there is no reason to expect anything else in that commit —
but "no reason to expect" is not a read, and the receipt exists precisely so that
difference is stated rather than assumed. The reviewer bounded this itself,
unprompted, twice. The reviewer re-read the
final state rather than resting on my attestation (it raised that distinction
unprompted, and was right to). Verdict: residual lists TRUE and complete against
stated coverage; exhaustiveness claim TRUE; re-scoped pin complete across all
three rules with a sound attribution guard. Only remaining defects were two prose
nits, both fixed. Every attack it had was exhausted.

**CORRECTNESS LANE: STILL OPEN — and my own inline check does NOT close it.**
After its F10 fix landed I ran the narrow follow-up inline (does the
control-based guard hold for the right reason?) and found nothing: the guard
calls the named rule directly with no `_CREDENTIAL_PATTERNS` involvement, is
stable under both fix directions, and is delimiter-insensitive by design.

**That is NOT clean round 1 and must not be recorded as one.** It is the author
checking his own instrument with the instrument that has now missed this class
SIX times — four of them mine. The correctness lane caught it at the parameter
layer, the confound layer AND the reachability layer; my inline pass caught it at
none. A self-attested convergence verdict is exactly what
`verify-resource-existence.md` MUST-4 blocks, and on this branch of all branches
it would be the punchline. Convergence needs an external receipt.

Prior status: Its last round found three instrument-layer
defects (frozen position axis; positional secret-slice satisfiable by a partial
fix; markup pin confounded into a duplicate of its neighbour). All three fixed in
`b8bc03eed`; a final round is requested and PENDING. The module is NOT converged
until that returns.

**FOR THE CODIFY PASS — the sharpest generalisation this branch produced, and it
is the reviewer's, not mine:**

> A reviewer's FINDING and a reviewer's REMEDY carry different evidentiary
> weight. The remedy is a HYPOTHESIS TO TEST, not an instruction to apply.

Three remedies were retracted on this branch (two by the security lane, one by
the correctness lane) plus one refuted PROOF. **Every single underlying finding
was correct and load-bearing.** Trusting the findings was right; applying any of
the remedies unexamined would have shipped a half-fix, re-imported a
just-removed leak, or asserted in a code comment that a live crossing could not
happen.

Note what did NOT catch these: skepticism. What caught them was (a) a second lane
finding the same gap from a different direction, and (b) testing each remedy
before applying it. That is process, and process is what generalises — an
instruction to "be appropriately skeptical" would have caught none of them.

Two companion lines from the same branch:
- Derive probes from what the pattern CLAIMS, not from what the patch CHANGED —
  a diff-derived probe set is blind to whatever the diff did not touch.
- Ask what a parametrized pin HOLDS CONSTANT, not what it varies — the uncovered
  axis is exactly where the next instance hides (it hid there three times).
- **Then ask which of its assertions can ever be REACHED.** The last frozen axis
  was not a parameter at all — it was ORDER OF ASSERTION. Every cell held "guard
  precedes leak check" constant, so varying delimiter, rule and position could
  never expose it, and widening the grid 4 -> 12 -> 20 only multiplied cells that
  all stopped at the same line. A guard encoding the defect's ABSENCE as a
  precondition converts the whole grid into a no-op, and no amount of widening
  reveals it.
- **Guard on the CONTROL, never on the defective shape.** An attribution guard
  must assert something that stays true after the fix; asserting the defect's
  negation makes the pin unreachable now and mis-signalling later.

## Ratified decisions — EXECUTE after convergence, do not re-surface

Ordering constraint UNCHANGED and still binding: W19 ✅ → **Round 2 convergence
(NOT met)** → version anchors + MCP pin → `/release`.

- **Decision A** — verified against ground truth this session: kaizen 2.45.0,
  kaizen-agents 0.12.0, dataflow 2.19.1, core 2.62.0, ml 2.2.2, nexus already
  2.16.0. Targets: 2.46.0 / 0.13.0 / 2.20.0 / 2.63.0 / 2.2.3.
  **TRAP: `kailash-ml` keeps its version in `_version.py`, NOT `__init__.py`.**
  The obvious bump pattern ships a split version state (zero-tolerance Rule 5).
- **Decision B** — verified: nexus's only `mcp` mention in pyproject is a
  KEYWORD, not a dependency. It imports `fastmcp` at `transports/mcp.py:79` —
  but that import IS already guarded (try/except → INFO → return), so **#1996's
  "unguarded import" premise needs revisiting rather than implementing as
  written.**
- **Decision C** — measured: **~7 genuine findings of 70**, range 5-20. NOT the
  20-25 first estimated; that sample came entirely from the Class-B-richest spec.
  Class B runs ~40% true, Class A ~8% — never pool the strata. Sizing 2-3 cycles.
  **BLOCKER FIRST:** `specs/spec-drift-gate.md` + `tests/spec_drift_gate/` may
  already implement a more mature gate that subsumes `tools/sweep-redteam.py`.
  Resolve before investing.

## Traps

- **ALL SIX agents went idle without delivering.** Four had COMPLETE work written
  as final text, never sent. **Query, never re-dispatch** — re-dispatching would
  have discarded four full investigations. An idle signal is ZERO evidence.
- **Inline re-derivation while waiting reached the WRONG conclusion on both W12
  and W13.** It is a hedge against never getting a report, not a substitute.
- **Check `Bash` in the agent's tool inventory BEFORE dispatch.** `analyst` and
  `security-reviewer` are read-only; both correctly refused work needing a shell.
  The security lane's hand-traces were still excellent — it disclosed the
  limitation and supplied falsifying commands. Run them.
- Run heavy suites SERIALLY. Two concurrent suites produce self-inflicted
  sqlite/perf failures (session-C finding, re-confirmed).
- `packages/kailash-kaizen` and `packages/kaizen-agents` **cannot be collected in
  one pytest invocation** — conftest module-name collision. Run separately.
- **Pre-existing failures, measured with the branch-point control, NOT inherited:**
  9 in kaizen-agents integration (4 Ollama-loopback, 5 missing `OPENAI_API_KEY`)
  and 18 in `tests/unit/db` + `tests/regression`. Identical at `26a4509b4`.
  Do NOT bucket them all as "Ollama" — one sits on the exact surface `b9a0a4ed6`
  refactored, so mislabelling would hide a code-caused failure.
- `.venv/bin/python -m pytest` always. Bare `python` dies at conftest.
- Do NOT install `fastmcp` — breaks the pinned fastapi/starlette.
- New credential-shaped test vectors MUST be assembled at runtime from fragments.
