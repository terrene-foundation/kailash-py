# specification-verification audit fixtures

Per `rules/cc-artifacts.md` Rule 9 + `rules/coc-artifact-eval-coverage.md` MUST-1:
one bipolar fixture pair per detection predicate. `rules/specification-verification.md`
carries 4 MUST predicates, so 4 efficacy pairs (8 `.txt` + 8 `.expected`) plus one
meta-compliance pair (2 `.md` + 2 `.expected`).

**Detection layer.** The load-bearing detector is the REVIEW layer (reviewer at
`/implement`, cc-architect at `/codify`). No hook detector exists and none is
planned for Phase 1 — whether a number was MEASURED or COPIED leaves no lexical
trace, so a regex detector would itself be the non-discriminating instrument
`instrument-discipline.md` MUST-1 blocks. Each `.expected` is therefore the
**reviewer's expected disposition** (`FLAG <MUST-clause> — <reason>` or
`CLEAN — <reason>`), never a hook JSON return.

**Origin-incident reproduction** (per `rule-authoring.md` Rule 9 — fixtures
reproduce the originating incident's conditions, not idealized versions where the
agent has already been told what to look for):

| Fixture                              | Predicate  | Expect | Origin incident reproduced                                     |
| ------------------------------------ | ---------- | ------ | -------------------------------------------------------------- |
| `flag-inherited-count`               | MUST-1     | FLAG   | #2015 — implemented to the filed count and "auth path worst"     |
| `clean-rederived-count`              | MUST-1     | CLEAN  | #2015 corrected — count and framing both re-derived, then posted |
| `flag-prescribed-remedy-untested`    | MUST-2     | FLAG   | #2004 — `mask_error_text` adopted, never run on the threat input |
| `clean-prescribed-remedy-tested`     | MUST-2     | CLEAN  | #2004 corrected — remedy exercised first, AC corrected           |
| `flag-inherited-grep`                | MUST-3     | FLAG   | #2015 — issue's own grep re-run, agreement read as corroboration |
| `clean-independent-instrument`       | MUST-3     | CLEAN  | #2015 corrected — defect-keyed instrument, 25th site reconciled  |
| `flag-silent-correction`             | MUST-4     | FLAG   | #2013 — measured the contradiction, implemented it silently      |
| `clean-correction-posted`            | MUST-4     | CLEAN  | #2013 corrected — divergence posted before implementing          |
| `meta-compliant-release-note-rule`   | meta-compl | COMPL  | synthetic rule meeting every applicable meta-rule                |
| `meta-violation-release-note-rule`   | meta-compl | N-COMPL| same skeleton, surface-matched, 6 breaches in CONTENT            |

**Why the flag poles are not trivially separable.** Each violating transcript is a
session doing everything else right: it plans, it edits, it writes a test, and the
test passes. `flag-inherited-grep` even runs a command and quotes its output —
the defect is that the command is the specification's own, so agreement is
guaranteed rather than informative. `flag-silent-correction` re-derives correctly
and still fails, on MUST-4 alone. A judge that separates this corpus by looking
for "did the transcript run a command" scores at chance on three of the four pairs.

**Meta pair parity.** Both poles share frontmatter, level-2 section skeleton,
intro paragraph, the MUST NOT clause, Origin, and the Wiring block, and sit 3.05%
apart on size (3275 B vs 3175 B — `wc -c`). Every affordance the meta-rules
mandate is PRESENT on both sides; the violation pole's six defects live in what
those affordances contain (a "should" modal under a MUST heading, a paraphrased
rather than verbatim BLOCKED corpus, a DO-only example block, a four-sentence
`Why:`, hedging inside the clause, and a Wiring block missing `Violation scope`).
A judge cannot separate the pair on shape.

**Answer keys are in the sidecars, never in the candidates.** Every `.expected`
file is an answer key and is structurally excluded from the rendered judge prompt
by `.claude/test-harness/lib/artifact-probe-adapter.mjs` (`buildPlan` reads only
the schema's `judgeContract`, the governing-doc paths, and the candidate text).
The adapter additionally REFUSES to dispatch any candidate containing an
answer-key marker (`<!--`, `EXPECTED ANSWER`, `ANSWER KEY`, or a schema field
name), so a leak fails the row closed rather than passing it more convincingly.
No candidate in this directory carries one.

**Probe suite.** The bipolar LLM-judge suite is
`.claude/test-harness/probes/specification-verification.probes.json` (efficacy +
no-false-positive across all four MUST clauses, plus a bipolar meta-compliance
pair), registered in `.claude/test-harness/eval-manifest.json` as a probe-only
entry (`scanner: null`). Every row pins `judge_model: claude-sonnet-5` and a
`pair_id`. The model pin is deliberate and follows the `evidence-first-claims`
precedent: these fixtures were authored by Opus 5, and the evaluating model should
differ from the generating one. Without the pin, judge selection is
per-invocation and no two runs are comparable.

Rule cross-reference: `rules/specification-verification.md` (MUST-1 through MUST-4
plus Trust Posture Wiring).
