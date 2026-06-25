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

See `.claude/guides/rule-extracts/sync-completeness.md` for full incident detail, JSON-dialect examples, verifying-command samples, and the v6.2 headroom-floor BLOCK condition design context.

<!-- slot:neutral-body -->

`/sync-to-use` and `/sync-to-build` are loom's outbound paths to USE templates and BUILD repos. When the fanout count is held in human memory rather than enumerated from `sync-manifest.yaml`, templates silently miss cycles. This rule binds every `/sync-to-*` invocation to enumerate ALL declared templates from the manifest, verify each landed at the bumped version + above the per-CLI `headroom_floor_pct`, AND emit a per-template verification table. Pairs with `artifact-flow.md`, `testing.md` MUST "Verified Numerical Claims", `coc-sync-landing.md`, AND `commands/sync-to-use.md` Step 0b + `bin/check-sync-freshness.mjs` (F62, journal/0163 + 0164 — the symmetric **pre-sync** defense: local-vs-remote SHA-pair check at pre-sync time mirrors this rule's verification-table check at post-sync time). The **file-set-completeness** companion to this rule's version/headroom table is `tools/verify-overlays.sh` (#427, journal/0252 — verifies every `variants:` overlay AND every `variant_only:<lang>` addition landed byte-equal at its dest); the in-tool gate (`sync-tier-aware.mjs::expandVariantOnly` → exit 1 on a declared-but-undistributable variant_only entry) is the load-bearing half.

## MUST Rules

### 1. Every `/sync-to-*` Invocation MUST Enumerate Templates From The Manifest

Every `/sync-to-use` (per-language: `/sync-to-use py`, `/sync-to-use rs`, `/sync-to-use rb`) AND every `/sync-to-build` invocation MUST start by enumerating `sync_targets[<lang>].templates[].repo` from `.claude/sync-manifest.yaml` and binding the resulting list to a variable for use in subsequent steps. Hand-typed lists, "the usual templates", "all 4 templates", or any count that is not produced by parsing the manifest at invocation time are BLOCKED.

```bash
# DO — parse manifest, bind to variable, iterate
TEMPLATES=$(yq -r ".sync_targets.${LANG}.templates[].repo" .claude/sync-manifest.yaml)
for t in $TEMPLATES; do
  # ... distribute to $t ...
done
echo "Templates enumerated for /sync-to-use $LANG: $(echo "$TEMPLATES" | wc -l) target(s)"

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
- "If I miss one, the next /sync-to-use catches it"
- "The downstream consumer will pull when they need to"

**Why:** Hand-typed counts decay silently. `yq -r '.sync_targets[].templates[].repo'` is the structural defense; "I remember which templates need the sync" is not. See guide § "Rule 1 — full incident detail" for the 2026-05-06 incident (5 templates, rb at 2.18.0 vs claimed-4-at-2.19.0).

### 2. Every `/sync-to-*` MUST Emit A Per-Template Verification Table

After distribution, `/sync-to-use` MUST emit a verification table to the user with one row per enumerated template, columns: `template`, `pre_sync_version`, `post_sync_version`, `loom_sha`, `synced_at`, `headroom_pct` (per cli×lang baseline emission, taken from `emit-report-<cli>.json::headroom_pct`), `landed` (✓ / ✗). Templates whose `post_sync_version` does not match the loom-side version OR whose `headroom_pct` is below the per-CLI `headroom_floor_pct` (per `sync-manifest.yaml::cli_variants.context/root.md.<cli>.headroom_floor_pct`) MUST appear as ✗ AND BLOCK the sync from completing. Single-template completion claims ("kailash-coc-claude-py at 2.20.0 ✓") without the full table are BLOCKED.

```text
# DO — full verification table emitted by /sync-to-use
| template                | pre  | post | loom_sha | synced_at            | hr% (codex/gemini) | ✓ |
| ----------------------- | ---- | ---- | -------- | -------------------- | ------------------ | - |
| kailash-coc-claude-py   | 2.19 | 2.20 | b4d2933  | 2026-05-06T14:22:00Z | 16.93 / 16.87      | ✓ |
| kailash-coc-claude-rb   | 2.18 | 2.18 | b4d2933  | (skipped)            | n/a                | ✗ |
| kailash-coc-rs          | 2.21 | 2.21 | def4567  | (emit-blocked)       | 9.81 / 9.85        | ✗ |
ERROR: ✗ rows halt sync — version-stale (rb) OR headroom-floor breach (rs, v6.2 Shard 2 — see workspaces/multi-cli-coc/02-plans/08-loom-v6.2-headroom-validator.md).

# DO NOT — single-line completion claim, OR table missing landed/hr% column
✓ /sync-to-use py complete (kailash-coc-claude-py at 2.20.0)
| template | pre | post |
```

**BLOCKED rationalizations:**

- "The sync git push succeeded, that proves it landed"
- "I can verify by spot-checking one template"
- "The table is overhead for a 2-template fanout"
- "VERSION currency is downstream's concern after sync"
- "The user will catch it if a template is stale"
- "The next /sync-to-use will reconcile any miss"

**Why:** Git push success is necessary but not sufficient — it proves bytes flew, not that the target's `.claude/VERSION` updated AND the artifact set is internally consistent (e.g., the rb sync at 2.18.0 left `upstream.version` at 2.17.0 because Gate 2 step 8 only bumped `upstream.template_version`; cross-template currency comparison was unverifiable until the reader knew which schema dialect to read). The verification table is the audit trail: every reader of the table can see at a glance which templates landed, which lagged, and at what SHA. Same principle as `agents.md` MUST "Reviewer Prompts Include Mechanical AST/Grep Sweep" — the structural defense is the table existing, not the agent's certainty that all templates were touched.

### 3. VERSION Schema MUST Be Uniform Across All Templates

Every USE template's `.claude/VERSION` MUST conform to a single canonical schema. The required `upstream` fields are: `name`, `type`, `version`, `synced_at`, `loom_sha`, `template_version`, `sdk_packages`. The field `upstream.version` MUST be present AND MUST match the loom version being distributed. Schema dialects (`upstream.build_version` only, `upstream.template_version` only, `upstream.version` lagging behind `upstream.template_version`) are BLOCKED.

```json
// DO — canonical schema: upstream.version present, matches loom version, all required fields populated.
// DO NOT — rb 2.18.0 dialect: upstream.version lags template_version.
// DO NOT — rs pre-2.20 dialect: upstream.version field absent; jq returns null.
// See guide § "Rule 3 — full JSON-dialect examples" for the three concrete shapes.
```

**BLOCKED rationalizations:**

- "rs templates use `build_version` historically, changing it is a migration"
- "The fields are equivalent, only the names differ"
- "We can normalize at read time"
- "Downstream tools handle both shapes"
- "The schema isn't documented anywhere, this is just convention"

**Why:** A `jq -r '.upstream.version'` query that returns `null` on rs-family templates and a string on py-family templates makes cross-template currency comparison impossible without per-template dialect knowledge. The 2026-05-06 audit took 5 separate `jq` invocations across two different field paths to establish that 4 of 5 templates were at 2.19.0 — the work the schema was supposed to do in O(1). Uniformity is also the structural defense for Rule 2's verification table: the table cannot be auto-generated if the field path varies per template. Ship one schema; if rs-family historically wrote `build_version`, the next /sync-to-use rs MUST write BOTH (canonical `upstream.version` + back-compat `upstream.build_version`) for one cycle, then drop `build_version` in the cycle after. Document the canonical schema in `guides/co-setup/08-versioning.md`.

### 4. Session-Notes Template-Count Claims MUST Come From A Verifying Command

Numerical claims in `.session-notes`, journal entries, or PR descriptions about template counts, sync currency, or "all N templates at version X" MUST be produced by a verifying command at the moment of writing. Hand-typed counts and recall-based claims are BLOCKED. Extends `testing.md` MUST "Verified Numerical Claims In Session Notes" from test counts to sync-fanout counts.

```bash
# DO — verifying command emits the count + currency (see guide § "Rule 4 — verifying-command fanout sample")
$ for t in $(yq -r '.sync_targets[].templates[].repo' .claude/sync-manifest.yaml); do
    v=$(jq -r '.upstream.version // .upstream.build_version // "?"' "../$t/.claude/VERSION"); echo "$t: $v"
  done
# → session notes line: "5/5 USE templates at 2.20.0 (verified 2026-05-06)"

# DO NOT — hand-typed count: "all 4 USE templates at 2.19.0 and pushed"
# (manifest declares 5 post-prism-retirement; rb actually at 2.18.0)
```

**BLOCKED rationalizations:**

- "I just ran /sync-to-use, the count is current by construction"
- "Counting templates is a 5-second mental task"
- "The manifest hasn't changed since last week"
- "If a template is stale, /sync-to-use will surface it"
- "Session notes are scratch space, not audit-grade"
- "The verifying command is overhead for a small fanout"

**Why:** Session notes propagate across `/clear` boundaries and are inherited by the next session as ground truth. A wrong count there reproduces as the next session's framing — exactly the failure mode `zero-tolerance.md` Rule 1c blocks for "pre-existing" claims after context boundaries. Per `testing.md`'s "Verified Numerical Claims" rule (originally for test counts), a 2-second `yq | jq` pipeline converts memory-bug into script. The 2026-05-06 session-notes claim "all 4 USE templates at 2.19.0" propagated through SessionStart into the follow-up session's framing and was only caught when the user asked a probing question. The verifying command would have caught it in the original session.

## MUST NOT

- **Run `/sync-to-*` without first parsing `sync-manifest.yaml::sync_targets[].templates[].repo` into a variable.**

**Why:** The manifest is the structural source of truth. Any sync that doesn't read it is operating on stale memory.

- **Claim sync completion until the per-template verification table is emitted with all rows ✓.**

**Why:** Partial completion claims ship the failure mode this rule prevents — a stale template hides behind a "✓ /sync-to-use py done" message.

- **Skip a declared template because it "rarely changes" or "isn't actively maintained".**

**Why:** Skipping is the mechanism by which rb missed 2.19.0; an inactive template is more dangerous, not less, because its drift is invisible to active workflows. Retirement is a manifest edit (`templates: []` per the prism precedent), not a per-cycle skip.

- **Write session-notes counts that exceed the verifying command's output.**

**Why:** "Round number" cognition rounds 5 templates down to 4; rounding 4 to 5 is rare. Either way, the verifying command is the truth.

## Trust Posture Wiring

The four MUST Rules above carry three independent Trust Posture Wiring profiles, partitioned by signal carrier: Rules 1/2(version-stale)/4 use `halt-and-report` lexical detection, Rule 3 uses `block` structural-JSON detection, and Rule 2(headroom-floor) uses `block` exit-code detection from the v6.2 validator. Only the headroom-floor sub-section binds a two-tier receipt band — it is the only MUST clause with a continuous numeric metric (`headroom_pct`) where the breach can be foreseen rather than only observed.

### Rules 1, 2 (version-stale ✗ row), 4 — enumeration + table + count discipline

- **Severity:** `halt-and-report` (agent surfaces, user adjudicates).
- **Grace period:** 7 days from rule landing (2026-05-06 → 2026-05-13, expired).
- **Regression-within-grace:** any new `/sync-to-*` invocation OR any `sync-manifest.yaml` edit that adds a template without canonical-schema VERSION field triggers emergency downgrade L5 → L4 per `trust-posture.md` MUST Rule 4.
- **Receipt:** SessionStart requires `[ack: sync-completeness]` if prior journal references `/sync-to-*` AND `posture.json::pending_verification` includes this rule_id.
- **Detection:** `cc-architect` mechanical sweep at `/codify`: (1) `grep -rn 'yq\|templates\[\]\.repo' .claude/commands/sync-to-*.md` — every `/sync-to-*` command body MUST enumerate from manifest; (2) AST sweep on `sync.md` / `sync-to-build.md` — every distribution loop MUST be preceded by manifest-enumeration.

### Rule 3 — VERSION schema mismatch (structural)

- **Severity:** `block` — structural signal (missing JSON field, not regex). Per `hook-output-discipline.md` MUST-2, structural signals MAY carry block severity. Evidence: `"schema mismatch: <field path missing>"`.
- **Grace period:** 7 days from rule landing (expired); rs-family templates given one cycle to migrate.
- **Regression-within-grace:** any `/sync-to-use rs` invocation post-grace that writes a non-canonical schema → emergency downgrade.
- **Detection:** JSON-schema sweep on `.claude/VERSION` across every USE template post-sync — `upstream.version` field present AND value matches loom version.

### Rule 2 (headroom-floor ✗ row) — v6.2 BLOCK condition

The v6.2 plan (`workspaces/multi-cli-coc/02-plans/08-loom-v6.2-headroom-validator.md`) Shards 1+2 (merged PR #218, commit `75352dd`, 2026-05-15) added a `headroom_pct` column to Rule 2's verification table AND wired the per-CLI `headroom_floor_pct` as a BLOCK condition. F5 binds that structural defense to the Trust Posture system.

- **Severity:** `block` — structural signal (`emit.mjs` in default strict mode returns non-zero on breach; the exit code IS the signal, not a regex match). Per `hook-output-discipline.md` MUST-2, the structural exit is the correct carrier of `block` severity.
- **Grace period:** 7 days from PR #218 merge (2026-05-15 → 2026-05-22). During grace, the validator emits structured `headroom_floor_violations[]`; `coc-sync.md`'s `node …/emit.mjs --all --lang <py|rs>` invocations (Shard 2 wiring; cycle-2 dropped the explicit `--strict-headroom` opt-in; cycle-3 removed the legacy no-op accepting) propagate non-zero exit unconditionally for py/rs. Grace applies to operators running `emit.mjs` directly OUTSIDE `/sync-to-use`. The opt-in→opt-out flip (cycle-2) shipped 2026-05-15 (PR #230); cycle-3 (a) removed the legacy `--strict-headroom` accepting after a callsite sweep confirmed zero references.
- **Regression-within-grace:** any of (a) /sync-to-use invocation that passes `--no-strict-headroom` to the `node …/emit.mjs --all --lang <py|rs>` invocation in `coc-sync.md`'s baseline-emission step OR removes the emit invocation entirely (grep-stable on the invocation pattern, not the section number; v6.2 cycle-2 flipped strict mode to opt-out default — the regression is now passing the opt-out flag, not omitting the prior opt-in); (b) `sync-manifest.yaml` edit that adds a CLI variant OR lowers an existing `cli_variants.context/root.md.<cli>.headroom_floor_pct` value below 10 (Risk-0004 baseline) such that the current rs-lane state would ship; (c) `emit.mjs` patch that silently downgrades `validateAggregateHeadroom()` exit code OR a `coc-sync.md` invocation patched to discard the non-zero exit via `|| true`, `if`-branch, pipeline-without-`pipefail`, or `set +e` guard; (d) agent prose citing any `coc-sync.md`-listed BLOCKED-rationalization ("Pass --no-strict-headroom to unblock this sync") to bypass the validator — triggers emergency downgrade per `trust-posture.md` MUST Rule 4 (cumulative-window regression class).
- **Receipt:** SessionStart MUST require `[ack: sync-completeness]` in the agent's first response IF the most recent journal entry references `/sync-to-*` invocation AND any cli×lang headroom falls under the two-tier near-breach band: `headroom_pct < 13%` (3% above floor — covers ~2 cycles of routine emission drift, advisory band) emits the receipt as a soft signal; `headroom_pct < 11%` (1% above floor — hard near-breach) MUST emit the receipt as halt-and-report. The wider 13% band matches the routine-CRIT-rule emission swing (~500–800 B ≈ ~1% of 61,440 B cap) so the receipt fires BEFORE the breach is reached, not after. From current measured state (`journal/0074` § For Discussion #2: gemini rs 15.64% as the closest combo), 3 typical landings reach the 13% advisory; 4-5 reach the 11% halt-and-report — giving ~2-cycle / ~4-cycle lead time at present.
- **Detection:** (1) Structural — `emit.mjs` non-zero exit on any `headroom_floor_violations[]` entry (Shard 1 wired the validator at `.claude/bin/emit.mjs::validateAggregateHeadroom`; cycle-2 flipped strict mode to opt-out default — `--no-strict-headroom` is the test-harness escape, BLOCKED in production `/sync-to-use`); (2) Wiring — `coc-sync.md`'s baseline-emission step invokes emit.mjs for every py/rs distribution (Shard 2 wired; cycle-2 dropped the explicit `--strict-headroom` flag since strict is now the default); (3) `/codify` mechanical sweep — any session transcript citing `/sync-to-*` MUST show no `--no-strict-headroom` flag in the recorded invocation AND record `headroom_pct` for every cli×lang combo emitted; presence of the opt-out flag OR a missing headroom record is a HIGH finding for the `/codify` reviewer; (4) advisory hook detection of prose rationalizations is intentionally NOT added — would re-introduce the false-positive class `hook-output-discipline.md` MUST-2 blocks, and the structural exit is already authoritative. **Consequence:** prose-level rationalizations do NOT contribute to `trust-posture.md` MUST Rule 4 cumulative-window math; the structural exit code (mechanism 1) is the authoritative defense and fires BEFORE the prose rationalization can take effect. Adding an advisory hook here is BLOCKED. (5) Manifest-axis sweep at `/codify` — `yq '.cli_variants."context/root.md".codex.headroom_floor_pct, .cli_variants."context/root.md".gemini.headroom_floor_pct' .claude/sync-manifest.yaml` returns `>= 10` for both CLIs; any value below the Risk-0004 baseline is a CRIT finding. (5b) Exit-code-swallow sweep at `/codify` — `grep -nE 'emit\.mjs[^|;]*(\|\||&& :|2>/dev/null$|set \+e)' .claude/agents/management/coc-sync.md` returns 0 hits (cycle-2 regex no longer anchors on `--strict-headroom` since strict is the default; any exit-discard wrapper around the emit.mjs invocation is a HIGH finding).

Origin: 2026-05-06 (Rules 1–4) — see guide § "Origin — full prose" for the rb-missed-sync + schema-drift incident. v6.2 extension 2026-05-15 — F5 cc-architect R1 LOW from `journal/0073` closes the Trust Posture Wiring gap on the new headroom-floor BLOCK condition; cycle-2 (same-day) flipped `--strict-headroom` from opt-in to opt-out default per plan §5.1 invariant 5 (mirrors v2.13.0 `--strict-budget` rollout) after the v2.31.0 /sync-to-use cycle confirmed zero false-positive blocks across all 5 USE templates.

<!-- /slot:neutral-body -->
