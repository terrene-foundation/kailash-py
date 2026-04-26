# Spec Drift Gate — Developer Flow

**Date:** 2026-04-26
**Phase:** /analyze synthesis

The gate ships to four primary personas. Each flow shows: what they do, what the gate does back, what the failure mode looks like, what the recovery path is.

## Persona 1 — Specialist editing a spec, adds a class assertion (success path)

**Trigger:** ml-specialist edits `specs/ml-engines.md` to document a newly-shipped `MLEngine.deploy()` method.

**Edit:**

```markdown
## 3. Public API

### 3.1 `MLEngine.deploy(model, *, channels)`

Deploy a registered model through the canonical serving stack...
```

**`git commit` runs pre-commit:**

```
$ git commit -m "docs(specs): add MLEngine.deploy() to public API"
spec-drift-gate.................................................Passed
[main abc1234] docs(specs): add MLEngine.deploy() to public API
```

**Why it passed:** the gate parsed `## 3. Public API` (allowlisted heading), found the backticked `MLEngine.deploy()` assertion, resolved `MLEngine` via the manifest's source-roots, AST-walked the class body in `kailash_ml/engine.py`, found `def deploy(self, model, *, channels)`, exit 0.

**Time:** ~6s on the specialist's laptop (NFR-1 budget is 30s for full corpus; one-spec edit is fast).

## Persona 2 — Specialist edits a spec, hits a false positive (override path)

**Trigger:** kaizen-specialist edits `specs/kaizen-agents-patterns.md` to add an example showing a hypothetical user-defined agent class.

**Edit:**

````markdown
## 5. Examples

Build your own agent by subclassing `BaseAgent`. For instance, imagine a
`SentimentAnalysisAgent` class that wraps a sentiment-classification model:

```python
class SentimentAnalysisAgent(BaseAgent):
    ...
```
````

```

**`git commit` fails:**

```

$ git commit -m "docs(specs): add SentimentAnalysisAgent example"
spec-drift-gate..............................................Failed

- hook id: spec-drift-gate
- exit code: 1

FAIL specs/kaizen-agents-patterns.md:122
FR-1: class SentimentAnalysisAgent — not found in any source root.
fix: add `<!-- spec-assert-skip: class:SentimentAnalysisAgent reason:"illustrative example only" -->`
immediately before the assertion, OR change "class" to "subclass" in the prose.

````

**Recovery (Option A — add override directive):**

```markdown
## 5. Examples

<!-- spec-assert-skip: class:SentimentAnalysisAgent reason:"illustrative example only" -->

Build your own agent by subclassing `BaseAgent`. For instance, imagine a
`SentimentAnalysisAgent` class that wraps a sentiment-classification model:
````

**`git commit` succeeds:**

```
$ git commit -m "docs(specs): add SentimentAnalysisAgent example"
spec-drift-gate..............................................Passed
```

**Recovery (Option B — restructure the example):**

Move the example under a clearly-deferred section heading (`## Deferred to M2` or `## Out of Scope`) — the gate skips those by default per ADR-2.

**Why the override discipline:** every `spec-assert-skip` directive requires a `reason:` field. Reviewers can grep `grep -rn spec-assert-skip specs/` to audit every override, satisfying ADR-2's failure mode D1 mitigation (gate becomes the new mock). The reason text is human-readable and surfaces intent.

## Persona 3 — Reviewer sees a baseline diff in PR

**Trigger:** dataflow-specialist opens PR #N adding new functionality to `dataflow-cache.md`. The PR also resolves one entry from `.spec-drift-baseline.jsonl` (a pre-existing F-E2-NN finding).

**PR view shows two changes to baseline:**

```
.spec-drift-baseline.jsonl

- {"spec":"specs/ml-feature-store.md","line":515,"finding":"FR-4","symbol":"FeatureGroupNotFoundError","origin":"F-E2-18","added":"2026-04-26","ageout":"2026-07-25"}
+ {"spec":"specs/dataflow-cache.md","line":89,"finding":"FR-1","symbol":"CacheKeyVersionMismatch","origin":"#N-discovery","added":"2026-04-27","ageout":"2026-07-26"}
```

**Reviewer sees:**

- (-) line: ONE existing baseline entry resolved (specialist fixed `FeatureGroupNotFoundError` cite by removing the fabricated reference).
- (+) line: ONE new baseline entry added (specialist intentionally adding a forward reference; logged with `origin:` field naming the PR).

**Reviewer rule (per ADR-3):** new baseline entries are allowed but require an `origin:` field that's either an audit finding ID OR a PR number with rationale. The PR template prompts for this.

**90-day rule:** every baseline entry has an `ageout:` field. Entries past their age-out date generate a WARN at gate-runtime ("baseline entry F-E2-19 expired; resolve or extend justification"). After 90 more days post-warn, the entry hard-fails the gate (forces resolution or explicit re-justification).

## Persona 4 — Wave 6 implementer claims a baseline entry

**Trigger:** ml-specialist starts work on Wave 6 follow-up #1 (`__getattr__` map flip per issue #640).

**They run:**

```
$ python scripts/spec_drift_gate.py --filter origin:F-E2-01 --format human

Found 1 baseline entry matching origin:F-E2-01:

specs/ml-automl.md:43
  FR-1: top-level `kailash_ml.AutoMLEngine` resolves via __getattr__ to LEGACY engines.automl_engine.AutoMLEngine
  origin: F-E2-01 / W6.5 review HIGH-2 / Wave 6 follow-up #640.1
  added:  2026-04-26
  ageout: 2026-07-25
  fix:    flip kailash_ml/__init__.py __getattr__ map entry for "AutoMLEngine" → kailash_ml.automl.engine; or document deferral
```

**They flip the map entry, run pre-commit:**

```
spec-drift-gate..............................................Passed
- 1 baseline entry resolved: F-E2-01 / kailash_ml.AutoMLEngine
- run `python scripts/spec_drift_gate.py --refresh-baseline` to remove resolved entries
```

**They refresh and commit:**

```
$ python scripts/spec_drift_gate.py --refresh-baseline
$ git add .spec-drift-baseline.jsonl kailash_ml/__init__.py
$ git commit -m "fix(automl): flip top-level export to canonical engine (#640.1)"
```

**Resolved entries are journaled** (per ADR-3 — `--refresh-baseline` writes `.spec-drift-resolved.jsonl` with the entry + the SHA of the resolving commit) so audit trail survives the deletion.

## Failure flow — what `failed: <X>` looks like for the W6.5 CRIT-1 case

**Scenario:** the spec drafting analyst (round 1 of the FeatureStore re-spec) writes:

```markdown
## 10. Errors

### 10.2 Forward Compatibility

The taxonomy in `kailash_ml.errors` ALSO defines `FeatureGroupNotFoundError`,
`FeatureVersionNotFoundError`, `FeatureEvolutionError`, `OnlineStoreUnavailableError`,
`CrossTenantReadError`. These are deferred-feature placeholders ...
```

**Gate runs:**

```
$ python scripts/spec_drift_gate.py specs/ml-feature-store-v2-draft.md

FAIL specs/ml-feature-store-v2-draft.md:515
  FR-4: class FeatureGroupNotFoundError — not found in src/kailash/ml/errors.py.
  fix:  delete the assertion, OR define the class in errors.py + add eager re-export per rules/orphan-detection.md MUST 6.

FAIL specs/ml-feature-store-v2-draft.md:515
  FR-4: class FeatureVersionNotFoundError — not found in src/kailash/ml/errors.py.
  fix:  delete the assertion, OR define the class.

FAIL specs/ml-feature-store-v2-draft.md:515
  FR-4: class FeatureEvolutionError — not found in src/kailash/ml/errors.py.
  fix:  delete the assertion, OR define the class.

FAIL specs/ml-feature-store-v2-draft.md:515
  FR-4: class OnlineStoreUnavailableError — not found in src/kailash/ml/errors.py.
  fix:  delete the assertion, OR define the class.

FAIL specs/ml-feature-store-v2-draft.md:515
  FR-4: class CrossTenantReadError — not found in src/kailash/ml/errors.py.
  fix:  delete the assertion, OR define the class.

FAIL specs/ml-feature-store-v2-draft.md:538
  FR-7: file packages/kailash-ml/tests/integration/test_feature_store_wiring.py — not found.
  fix:  rename the assertion to an existing test, OR create the file (see rules/facade-manager-detection.md MUST 1).

6 failures. Run with --format json for CI annotations.
```

**The reviewer's job (W6.5 round 1) was to do this manually.** The gate does it in <1s, with no agent budget consumed.

## Edge case — spec with no class citations (failure mode F4)

**Trigger:** philosophy-style spec like `specs/co-philosophy.md` (hypothetical, illustrative) — pure prose, no class assertions.

**Gate runs:**

```
$ python scripts/spec_drift_gate.py specs/co-philosophy.md
PASS specs/co-philosophy.md (0 assertions found in allowlisted sections)
```

**Why this matters:** F4 says "specs with no class citations must not error". The gate emits PASS + an INFO line acknowledging zero assertions. Authors confirm coverage was intentional, not silently un-swept.

## Edge case — section-heading drift (failure mode A3 / R1)

**Trigger:** specialist renames `## Surface` to `## Public Interface` in `specs/dataflow-core.md`. The new heading is NOT in ADR-2's allowlist.

**Gate runs:**

```
$ python scripts/spec_drift_gate.py specs/dataflow-core.md
PASS specs/dataflow-core.md
INFO sections scanned for assertions: ['## 1. Scope']
WARN no allowlisted assertion sections found. Did you mean ## Surface or ## Public API?
       (See ADR-2 section-name allowlist or use <!-- spec-assert: ... --> markers.)
```

**Recovery:** specialist either renames the heading back, OR adds explicit `<!-- spec-assert: ... -->` directives in the renamed section, OR explicitly opts the section into scanning via a new directive `<!-- spec-assert-section: -->` (deferred — out of scope for v1.0).

**Why the WARN matters:** silently un-swept sections are the failure mode A3 mitigation requires. The WARN line surfaces the coverage gap immediately.

## Cross-SDK flow — kailash-rs sibling

**Trigger:** ml-specialist updates `specs/ml-automl.md` AND wants the same change reflected in kailash-rs's spec corpus.

**Today (M1, day 1):** the gate is scoped to kailash-py only. The specialist runs `python scripts/spec_drift_gate.py` against kailash-py specs. kailash-rs has its own gate (per ADR-5 manifest-driven design).

**At M2 (deferred):** a single config (`workspaces/.cross-sdk-spec-drift.toml`) names both repos; the gate runs against both source trees from a single invocation. Today's gate is forward-compatible with this evolution by reading source roots from manifest, not hardcoded paths.

**Why deferred:** failure-points.md § E2 (cross-SDK) is explicitly M2. Today's gate flags cross-SDK assertions as `WARN unverified — cross-SDK reference, see kailash-rs/specs/X` rather than failing.
