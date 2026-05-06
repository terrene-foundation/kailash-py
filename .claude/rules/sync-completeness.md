---
priority: 10
scope: path-scoped
paths:
  - "**/.claude/sync-manifest.yaml"
  - "**/.claude/commands/sync*.md"
  - "**/.claude/commands/sync-to-build.md"
  - "**/.claude/agents/management/sync-reviewer.md"
  - "**/.claude/agents/management/coc-sync.md"
  - "**/.claude/VERSION"
---

# Sync Completeness — Enumerate Every Template, Verify Every Landing

<!-- slot:neutral-body -->

`/sync` and `/sync-to-build` are loom's outbound paths to USE templates and BUILD repos. They distribute COC artifacts across an N-template fanout. When the fanout count is held in human memory rather than enumerated mechanically from `sync-manifest.yaml`, templates silently miss cycles — and the failure is invisible until a downstream consumer reports a stale rule weeks later.

This rule binds every `/sync*` invocation to enumerate ALL declared templates from the manifest, verify each landed at the bumped version, AND emit a per-template verification table. It also pins a uniform VERSION schema across all templates so currency comparison is a one-liner, not a dialect-translation exercise.

Pairs with `artifact-flow.md` (sync as the only outbound path), `testing.md` MUST "Verified Numerical Claims In Session Notes" (extends the principle from test counts to template counts), and `coc-sync-landing.md` (downstream BUILD-side discipline once artifacts arrive).

## MUST Rules

### 1. Every `/sync*` Invocation MUST Enumerate Templates From The Manifest

Every `/sync` (per-language: `/sync py`, `/sync rs`, `/sync rb`) AND every `/sync-to-build` invocation MUST start by enumerating `sync_targets[<lang>].templates[].repo` from `.claude/sync-manifest.yaml` and binding the resulting list to a variable for use in subsequent steps. Hand-typed lists, "the usual templates", "all 4 templates", or any count that is not produced by parsing the manifest at invocation time are BLOCKED.

```bash
# DO — parse manifest, bind to variable, iterate
TEMPLATES=$(yq -r ".sync_targets.${LANG}.templates[].repo" .claude/sync-manifest.yaml)
for t in $TEMPLATES; do
  # ... distribute to $t ...
done
echo "Templates enumerated for /sync $LANG: $(echo "$TEMPLATES" | wc -l) target(s)"

# DO NOT — hand-typed list
TEMPLATES="kailash-coc-claude-py kailash-coc-py"  # forgets to update when manifest changes

# DO NOT — partial enumeration ("the CC-only template")
for t in kailash-coc-claude-${LANG}; do  # silently skips the unified-CLI template
  ...
done
```

**BLOCKED rationalizations:**

- "I just synced these last week, the list hasn't changed"
- "The unified-CLI templates don't need this artifact"
- "I'll add the new template after the cycle"
- "The session notes say there are 4, that's the count"
- "The fanout is small, I can hold it in memory"
- "The manifest is the spec; hand-typing is faster"
- "If I miss one, the next /sync catches it"
- "The downstream consumer will pull when they need to"

**Why:** Hand-typed counts decay silently. The 2026-05-06 session-notes claim "all 4 USE templates at 2.19.0 and pushed" was wrong on TWO counts: there are FIVE templates after prism's retirement (claude-py + unified py + claude-rs + unified rs + claude-rb), AND `/sync rb` was not invoked in the 2.19.0 cycle so claude-rb landed at 2.18.0. Both errors trace to the same root cause: the count was carried from prior session memory, not derived from the manifest at sync time. The manifest is the single source of truth precisely so this mode-of-failure is mechanical to prevent — `yq -r '.sync_targets[].templates[].repo'` is the structural defense; "I remember which templates need the sync" is not. Origin: 2026-05-06 — kailash-coc-claude-rb missed the 2.19.0 sync; not surfaced until the user asked "only rs has this issue? what about the py?" during follow-up review.

### 2. Every `/sync*` MUST Emit A Per-Template Verification Table

After distribution, `/sync` MUST emit a verification table to the user with one row per enumerated template, columns: `template`, `pre_sync_version`, `post_sync_version`, `loom_sha`, `synced_at`, `landed` (✓ / ✗). Templates whose `post_sync_version` does not match the loom-side version being distributed MUST appear as ✗ AND BLOCK the sync from completing. Single-template completion claims ("kailash-coc-claude-py at 2.20.0 ✓") without the full table are BLOCKED.

```text
# DO — full verification table emitted by /sync
| template                    | pre  | post | loom_sha | synced_at            | ✓ |
| --------------------------- | ---- | ---- | -------- | -------------------- | - |
| kailash-coc-claude-py       | 2.19 | 2.20 | b4d2933  | 2026-05-06T14:22:00Z | ✓ |
| kailash-coc-py (unified)    | 2.19 | 2.20 | b4d2933  | 2026-05-06T14:22:01Z | ✓ |

# DO — blocking ✗ row halts sync; user adjudicates
| kailash-coc-claude-rb       | 2.18 | 2.18 | b4d2933  | (skipped)            | ✗ |
ERROR: 1 template did not advance to 2.20.0 — sync BLOCKED.

# DO NOT — single-line completion claim
✓ /sync py complete (kailash-coc-claude-py at 2.20.0)

# DO NOT — table missing the "landed" column
| template | pre  | post |
| ...      | 2.19 | 2.20 |
```

**BLOCKED rationalizations:**

- "The sync git push succeeded, that proves it landed"
- "I can verify by spot-checking one template"
- "The table is overhead for a 2-template fanout"
- "VERSION currency is downstream's concern after sync"
- "The user will catch it if a template is stale"
- "The next /sync will reconcile any miss"

**Why:** Git push success is necessary but not sufficient — it proves bytes flew, not that the target's `.claude/VERSION` updated AND the artifact set is internally consistent (e.g., the rb sync at 2.18.0 left `upstream.version` at 2.17.0 because Gate 2 step 8 only bumped `upstream.template_version`; cross-template currency comparison was unverifiable until the reader knew which schema dialect to read). The verification table is the audit trail: every reader of the table can see at a glance which templates landed, which lagged, and at what SHA. Same principle as `agents.md` MUST "Reviewer Prompts Include Mechanical AST/Grep Sweep" — the structural defense is the table existing, not the agent's certainty that all templates were touched.

### 3. VERSION Schema MUST Be Uniform Across All Templates

Every USE template's `.claude/VERSION` MUST conform to a single canonical schema. The required `upstream` fields are: `name`, `type`, `version`, `synced_at`, `loom_sha`, `template_version`, `sdk_packages`. The field `upstream.version` MUST be present AND MUST match the loom version being distributed. Schema dialects (`upstream.build_version` only, `upstream.template_version` only, `upstream.version` lagging behind `upstream.template_version`) are BLOCKED.

```json
// DO — canonical schema, every field populated, version is current
{
  "version": "3.10.0",
  "type": "coc-use-template",
  "upstream": {
    "name": "loom",
    "type": "coc-source",
    "version": "2.20.0",
    "loom_sha": "abc1234",
    "synced_at": "2026-05-06T14:22:00Z",
    "template_version": "2.20.0",
    "sdk_packages": { "kailash": "2.13.4", "...": "..." }
  }
}

// DO NOT — `upstream.version` lags `template_version` (rb 2.18.0 dialect)
{
  "upstream": {
    "version": "2.17.0",        // stale
    "template_version": "2.18.0" // current
  }
}

// DO NOT — `upstream.version` field missing entirely (rs dialect pre-2.20)
{
  "upstream": {
    "build_version": "2.19.0",
    "template_version": "2.19.0"
    // (no `version` field — `jq '.upstream.version'` returns null)
  }
}
```

**BLOCKED rationalizations:**

- "rs templates use `build_version` historically, changing it is a migration"
- "The fields are equivalent, only the names differ"
- "We can normalize at read time"
- "Downstream tools handle both shapes"
- "The schema isn't documented anywhere, this is just convention"

**Why:** A `jq -r '.upstream.version'` query that returns `null` on rs-family templates and a string on py-family templates makes cross-template currency comparison impossible without per-template dialect knowledge. The 2026-05-06 audit took 5 separate `jq` invocations across two different field paths to establish that 4 of 5 templates were at 2.19.0 — the work the schema was supposed to do in O(1). Uniformity is also the structural defense for Rule 2's verification table: the table cannot be auto-generated if the field path varies per template. Ship one schema; if rs-family historically wrote `build_version`, the next /sync rs MUST write BOTH (canonical `upstream.version` + back-compat `upstream.build_version`) for one cycle, then drop `build_version` in the cycle after. Document the canonical schema in `guides/co-setup/08-versioning.md`.

### 4. Session-Notes Template-Count Claims MUST Come From A Verifying Command

Numerical claims in `.session-notes`, journal entries, or PR descriptions about template counts, sync currency, or "all N templates at version X" MUST be produced by a verifying command at the moment of writing. Hand-typed counts and recall-based claims are BLOCKED. Extends `testing.md` MUST "Verified Numerical Claims In Session Notes" from test counts to sync-fanout counts.

```bash
# DO — verifying command emits the count + currency
$ for t in $(yq -r '.sync_targets[].templates[].repo' .claude/sync-manifest.yaml); do
    v=$(jq -r '.upstream.version // .upstream.build_version // "?"' "../$t/.claude/VERSION")
    echo "$t: $v"
  done
kailash-coc-claude-py: 2.20.0
kailash-coc-py: 2.20.0
kailash-coc-claude-rs: 2.20.0
kailash-coc-rs: 2.20.0
kailash-coc-claude-rb: 2.20.0
# → session notes line: "5/5 USE templates at 2.20.0 (verified 2026-05-06)"

# DO NOT — hand-typed count
"all 4 USE templates at 2.19.0 and pushed"
# (manifest declares 5 post-prism-retirement; rb actually at 2.18.0)
```

**BLOCKED rationalizations:**

- "I just ran /sync, the count is current by construction"
- "Counting templates is a 5-second mental task"
- "The manifest hasn't changed since last week"
- "If a template is stale, /sync will surface it"
- "Session notes are scratch space, not audit-grade"
- "The verifying command is overhead for a small fanout"

**Why:** Session notes propagate across `/clear` boundaries and are inherited by the next session as ground truth. A wrong count there reproduces as the next session's framing — exactly the failure mode `zero-tolerance.md` Rule 1c blocks for "pre-existing" claims after context boundaries. Per `testing.md`'s "Verified Numerical Claims" rule (originally for test counts), a 2-second `yq | jq` pipeline converts memory-bug into script. The 2026-05-06 session-notes claim "all 4 USE templates at 2.19.0" propagated through SessionStart into the follow-up session's framing and was only caught when the user asked a probing question. The verifying command would have caught it in the original session.

## MUST NOT

- **Run `/sync*` without first parsing `sync-manifest.yaml::sync_targets[].templates[].repo` into a variable.**

**Why:** The manifest is the structural source of truth. Any sync that doesn't read it is operating on stale memory.

- **Claim sync completion until the per-template verification table is emitted with all rows ✓.**

**Why:** Partial completion claims ship the failure mode this rule prevents — a stale template hides behind a "✓ /sync py done" message.

- **Skip a declared template because it "rarely changes" or "isn't actively maintained".**

**Why:** Skipping is the mechanism by which rb missed 2.19.0; an inactive template is more dangerous, not less, because its drift is invisible to active workflows. Retirement is a manifest edit (`templates: []` per the prism precedent), not a per-cycle skip.

- **Write session-notes counts that exceed the verifying command's output.**

**Why:** "Round number" cognition rounds 5 templates down to 4; rounding 4 to 5 is rare. Either way, the verifying command is the truth.

## Trust Posture Wiring

- **Severity:** `halt-and-report` for Rule 1, 2, 4 violations (the agent surfaces and the user adjudicates). Rule 3 is structural — VERSION schema mismatch detected at sync-completion time MUST emit `block` with the structural-signal `evidence: "schema mismatch: <field path missing>"` (per `hook-output-discipline.md` MUST-2, this IS a structural signal — a missing JSON field, not a regex match).
- **Grace period:** 7 days from rule landing. During grace, `/sync` emits the verification table but does NOT block on schema mismatch (Rule 3) — gives existing rs-family templates one cycle to migrate to canonical schema.
- **Regression-within-grace:** any new `/sync*` invocation OR any `sync-manifest.yaml` edit that adds a template without simultaneously adding the canonical-schema VERSION field requirement triggers emergency downgrade L5 → L4 per `trust-posture.md` MUST Rule 4.
- **Receipt requirement:** SessionStart MUST require `[ack: sync-completeness]` in the agent's first response IF the most recent journal entry references `/sync*` invocation AND `posture.json::pending_verification` includes this rule_id (set by `/codify` at land-time, cleared after grace expires).
- **Detection mechanism:** `cc-architect` mechanical sweep at `/codify` validation:
  1. `grep -rn 'TEMPLATES\|templates' .claude/commands/sync*.md` — every `/sync*` command body MUST cite `yq` against the manifest before iterating.
  2. AST sweep on `sync.md` and `sync-to-build.md` — every distribution loop MUST be preceded by a manifest-enumeration step.
  3. JSON schema sweep on `.claude/VERSION` across all USE templates after each `/sync` — `upstream.version` field present AND value matches loom version.

Origin: 2026-05-06 — user follow-up review revealed (a) kailash-coc-claude-rb missed the 2.19.0 sync entirely (one cycle stale); (b) the 2026-05-06 session-notes claim "all 4 USE templates at 2.19.0" was wrong on enumeration (5 templates post-prism) AND on currency (rb at 2.18.0); (c) VERSION schema diverged in three dialects across py / rs / rb families. Pre-rule, every defense was implicit in `commands/sync.md` Gate 2 prose and `sync-manifest.yaml` declarations; nothing forced the enumeration to be mechanical at invocation time, and nothing forced post-sync verification beyond `git push` exit code. Rule lifts the implicit invariants into explicit MUST clauses and pins them with Trust Posture Wiring so regression triggers downgrade.

<!-- /slot:neutral-body -->
