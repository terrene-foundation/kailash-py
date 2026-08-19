---
id: "SYNC-COMPLETENESS"
paths: ["**/.claude/sync-manifest.yaml", "**/.claude/commands/sync*.md", "**/.claude/commands/sync-to-build.md", "**/.claude/agents/management/sync-reviewer.md", "**/.claude/agents/management/coc-sync.md", "**/.claude/VERSION"]
---

# Sync Completeness — Enumerate Every Template, Verify Every Landing

See `.claude/guides/rule-extracts/sync-completeness.md` for full incident detail, JSON-dialect examples, verifying-command samples, and the v6.2 headroom-floor BLOCK condition design context.

`/sync-to-use` and `/sync-to-build` are loom's outbound paths to USE templates and BUILD repos. When the fanout count is held in human memory rather than enumerated from `sync-manifest.yaml`, templates silently miss cycles. This rule binds every `/sync-to-*` invocation to enumerate ALL declared templates from the manifest, verify each landed at the bumped version + above the per-CLI `headroom_floor_pct`, AND emit a per-template verification table. Pairs with `artifact-flow.md`, `testing.md` MUST "Verified Numerical Claims", `coc-sync-landing.md`, AND `commands/sync-to-use.md` Step 0b + `bin/check-sync-freshness.mjs` (F62, journal/0163 + 0164 — the symmetric **pre-sync** defense: local-vs-remote SHA-pair check at pre-sync time mirrors this rule's verification-table check at post-sync time). The **file-set-completeness** companion to this rule's version/headroom table is `tools/verify-overlays.sh` (#427, journal/0252 — verifies every `variants:` overlay AND every `variant_only:<lang>` addition landed byte-equal at its dest); the in-tool gate (`sync-tier-aware.mjs::expandVariantOnly` → exit 1 on a declared-but-undistributable variant_only entry) is the load-bearing half.

**BUILD-lane completeness gate (F11, journal/0339).** The per-template verification table below is the USE-lane mechanism. For `/sync-to-build` the analogue is the deterministic engine's `node .claude/bin/sync-tier-aware.mjs --build <target> --verify` — a read-only check that asserts the BUILD repo's `.claude/` == expected state (reporting every MISSING / DIFFERS / OBSOLETED-PRESENT path, exit 1 on any). It MUST pass CONSISTENT before a `/sync-to-build` is declared complete or its VERSION bumped. This is the gate that was ABSENT when two `coc-sync` agents diverged into complementary partials (py landed content but skipped the purge; rs purged but skipped the codify-anchor).

## MUST Rules

### 1. Every `/sync-to-*` Invocation MUST Enumerate Templates From The Manifest

Every `/sync-to-use` (per-language: `/sync-to-use py`, `/sync-to-use rs`, `/sync-to-use base`) AND every `/sync-to-build` invocation MUST start by enumerating `sync_targets[<lang>].templates[].repo` from `.claude/sync-manifest.yaml` and binding the resulting list to a variable for use in subsequent steps. Hand-typed lists, "the usual templates", "all 4 templates", or any count that is not produced by parsing the manifest at invocation time are BLOCKED.

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
| coc-base                | 2.18 | 2.18 | b4d2933  | (skipped)            | n/a                | ✗ |
| kailash-coc-rs          | 2.21 | 2.21 | def4567  | (emit-blocked)       | 9.81 / 9.85        | ✗ |
ERROR: ✗ rows halt sync — version-stale (base) OR headroom-floor breach (rs, v6.2 Shard 2 — see (loom-internal reference)).

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

**3a. The provenance stamp MUST name the run that delivered the content (MUST — loom#1756).** `.claude/VERSION::upstream.loom_sha` and `.claude/.coc-sync-marker::loom_sha` are the freshness anchors every downstream staleness check reads. Both are enrichment-written (`coc-sync.md` Step 9; `stamp-template-version.mjs --write`), so a Gate-2 `--finalize` MUST refuse when either names a DIFFERENT commit than the loom HEAD the run distributed from. Shipping content under the PREVIOUS distribution's SHA is BLOCKED — it is strictly worse than an absent stamp, because the marker reads as a successful, dated delivery.

```text
# DO — the stamp names this run; the gate confirms it and says so
sync-gate2-worktree: provenance stamp names this run: .claude/VERSION=4b04c023…
# DO NOT — restamp skipped: 2026-08-02 provenance asserted over 2026-08-15 content
.claude/VERSION::upstream.loom_sha = b4426601 (2026-08-02)   # content delivered 2026-08-15
```

**Why:** `stamp-template-version.mjs --check` compares only the loom-tracking VERSION-STRING fields against loom's platform version and never reads `loom_sha` or `synced_at` — so whenever loom's version string is unchanged between distributions (the common case) it prints OK on an arbitrarily stale stamp. It cannot return the other answer for the freshness proposition, so it is not evidence for it (`instrument-discipline.md` MUST-1). Measured 2026-08-15: four templates carry 2026-08-02 provenance over 2026-08-15 content, and merging the stale PRs would have made the stamp *less* accurate, not more.

BLOCKED corpus + the canonical-8-field Trust-Posture Wiring for this clause: guide § "Rule 3a — provenance stamp freshness" (Rule-10 path (a) paired extraction, taken because the inline form breached the 60KiB producer budget on emission).

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

### 5. Syncs That Copy `.claude/` MUST Also Sync External Symlink Targets

A `.claude/` entry MAY be a symlink to a repo-root EXTERNAL target — the codex-mcp-guard pattern: `.claude/codex-mcp-guard` → `../.codex-mcp-guard`, whose real tree is distributed to repo-root `.codex-mcp-guard/` (manifest `paths: .codex-mcp-guard/**` + the `multi_cli_overlays.<overlay-type>.symlinks` declaration). ANY sync that copies `.claude/` — outbound (`/sync-to-use`, `/sync-to-build`) OR inbound (`/sync-from-template`) — MUST ALSO sync every declared external target tree AND recreate the symlink. Enumerate the symlink set from `sync-manifest.yaml::multi_cli_overlays.<overlay-type>.symlinks` (path + target), never from memory (same discipline as Rule 1). A `.claude/`-only copy carries the symlink but leaves the external target stale — the consuming tool then runs against stale content with NO error (for codex-mcp-guard, `extract-policies.mjs` silently no-ops, dropping Codex policy enforcement).

```bash
# DO — sync .claude/ AND every declared external symlink target, then recreate the link
rsync -a <src>/.claude/ <dst>/.claude/
for tgt in $(yq -r '.multi_cli_overlays[].symlinks[].target' sync-manifest.yaml | sed 's#^\.\./##' | sort -u); do
  case "$tgt" in ../*|/*) echo "refusing out-of-root symlink target: $tgt" >&2; exit 1;; esac  # fail-closed bound
  rsync -a "<src>/$tgt/" "<dst>/$tgt/"        # external tree, e.g. .codex-mcp-guard/
done
# recreate .claude/codex-mcp-guard → ../.codex-mcp-guard per the symlinks: declaration

# DO NOT — copy .claude/ only; the external target is left stale → dead guard
rsync -a <src>/.claude/ <dst>/.claude/        # extract-policies.mjs now a no-op
```

**BLOCKED rationalizations:**

- "I synced `.claude/`, the symlink came with it"
- "The symlink resolves, so its target must be current"
- "rsync follows symlinks" (it copies the link OR the pointed-at content per flags — neither refreshes a stale external tree at the destination)
- "codex-mcp-guard is Codex-only; this consumer is CC" (the symlink + external tree ship to every multi-CLI consumer; a stale guard is a silent enforcement gap)
- "The next sync will fix it"

**Why:** A symlink to an external (`../`) target splits the artifact across two trees; a sync scoped to `.claude/` updates one and silently strands the other — the symlink resolves, the tool starts, but reads stale bytes and no-ops. Enumerating external targets from the manifest (not memory) and syncing both halves is the only structural defense; loom's outbound path (`coc-sync.md` Step 4.5/4.6 copies the external tree, snapshot-guarded by `sync-tier-aware.mjs`, which does NOT follow symlinks) already does this via the dual manifest declaration, and inbound `/sync-from-template` (Step 4) MUST match it. Origin: 2026-06-27 — a downstream `/sync-from-template` consumer reported `extract-policies.mjs` was a no-op after a `.claude/`-only sync left `../.codex-mcp-guard` stale (journal/0352).

### 6. COC Artifacts Under `.claude/` MUST NEVER Be Untracked By A Consumer Root Ignore

A synced `.claude/**` artifact MUST stay git-TRACKED at every target. NEVER coc-artifact into a path a consumer's own `.gitignore` swallows — a delivered file that lands on disk but a fresh clone never tracks is an invisible-delivery failure identical in spirit to `coc-sync-landing.md`'s "uncommitted deliveries vanish". The structural defense is two-part and BOTH halves are MANDATORY: (a) for any `.claude/**` subtree whose basename collides with a common consumer root ignore (`lib/`, `build/`, `dist/`, `var/`, `parts/`), a `!`-re-include MUST be declared in `sync-manifest.yaml::gitignore_reincludes` (applied to USE templates AND BUILD repos — role-blind, unlike `gitignore_additions` which is consumer-only); (b) `/sync-to-use` AND `/sync-to-build` MUST run the post-sync `git check-ignore` gate (`sync-tier-aware.mjs::findSwallowedArtifacts` over every emitted `.claude/**` path) and HARD-FAIL on any swallowed artifact. Shipping a sync without the re-include for a colliding subtree, OR with the swallowed-gate disabled, is BLOCKED.

```bash
# DO — declare the re-include; the post-sync gate confirms tracked-ness
# sync-manifest.yaml::gitignore_reincludes:  - "!.claude/bin/lib/"
# → consumer .gitignore managed block carries `!.claude/bin/lib/` AFTER its broad `lib/`
# → findSwallowedArtifacts returns [] → sync completes
node .claude/bin/sync-tier-aware.mjs --build py --verify   # swallowed rows = OUT OF SYNC

# DO NOT — let a consumer's broad `lib/` swallow `.claude/bin/lib/`
# consumer .gitignore: `lib/` (Python build-artifact block, no re-include)
# → .claude/bin/lib/loom-links.mjs untracked → fresh clone: tracked
#   sync-tier-aware.mjs throws `Cannot find module './lib/loom-links.mjs'` on import
```

**Why:** loom#676 — a consumer carrying the conventional Python build-artifact block (`lib/`) silently untracked the entire `.claude/bin/lib/` directory, including `loom-links.mjs` (the canonical NAME→location resolver — `repo-scope-discipline.md` § MUST NOT; the module itself is loom/BUILD-side) + `slot-parser.mjs` + `strip-build-internal.mjs` that the tracked `sync-tier-aware.mjs` imports. It "worked" only because the files were present from the local sync; a fresh clone throws on import. The negation closes the known instance; the post-sync `git check-ignore` gate closes the CLASS for any future `.claude/**` subtree whose basename collides with a root ignore.

### 7. Every Enumerated Target's Gate-2 Distribution MUST Capture The Exact Per-File Manifest Receipt

Under the worktree-from-remote-main Gate-2 model (`artifact-flow.md` § "Exact Gate-1 / Gate-2 Tracking"; `journal/0403`), each enumerated target's distribution MUST capture the exact per-file manifest receipt the engine emits. `bin/sync-gate2-worktree.mjs::buildReceipt` returns `{loom_sha, base_sha, target, branch, manifest{added,modified,deleted}, changed_count, pr_url, merge_sha}` (plus `gate`, `lane`, the absolute `worktree` path, and `timestamp`) derived from the worktree's own `git status --porcelain` (`parseManifest`) — NOT a hand-typed file list — and the receipt MUST be recorded per enumerated target (Rule 1) in the gate-op journal receipt plus the coordination-log record, **scrubbed before the journal embed per `user-flow-validation.md` MUST-6** (the `pr_url` org/repo slug and the absolute `worktree` path are the scrub tokens, exactly as `artifact-flow.md` § "Exact Gate-1 / Gate-2 Tracking" MUST-2 requires). A completion claim citing only the version / headroom table (Rule 2) WITHOUT the per-target exact-manifest receipt is BLOCKED.

Each target's receipt comes from ITS OWN worktree. `--stage-only` CREATES that worktree and PRINTS its path; `--finalize` MUST be handed the path belonging to the SAME target. `sync-gate2-worktree.mjs` enforces this — it refuses a `--worktree` that is not a linked worktree of the resolved target's clone (both sides resolved through `realpath`) — so a shared or stale path is a loud refusal, not a mis-delivery.

```bash
# DO — one worktree PER TARGET, its path carried from --stage-only to --finalize
for t in $TEMPLATES; do   # $TEMPLATES enumerated from the manifest per Rule 1
  wt=$(node .claude/bin/sync-gate2-worktree.mjs --lane use --target "$t" --stage-only --json | jq -r .worktree)
  # …enrich in "$wt" (VERSION, SDK pins, .coc-sync-marker, derived trees)…
  node .claude/bin/sync-gate2-worktree.mjs --lane use --target "$t" --finalize --worktree "$wt" --json
done   # each receipt: {loom_sha, base_sha, target, branch, manifest{added,modified,deleted}, changed_count, pr_url, merge_sha}

# DO NOT — vary --target against ONE fixed worktree
for t in $TEMPLATES; do
  node … --target "$t" --finalize --worktree "$WT" --json   # $WT belongs to ONE target
done   # every target after the first commits and PUSHES that target's tree to its own remote

# DO NOT — record only "all N templates at 2.20.0 ✓" with no per-file manifest
# (the version table alone cannot answer "which files changed in template rs?")
```

**BLOCKED rationalizations:**

- "The version table already proves the sync landed"
- "The per-file manifest is engine-internal, not worth recording"
- "I can reconstruct the manifest from the diff later"
- "Hand-typing the changed files is close enough"
- "One worktree is fine, the loop just re-points it at each target" (it does not re-point: `--finalize` commits and PUSHES whatever tree that path holds, to the resolved target's remote)

**Why:** The per-target version row (Rule 2) answers "did the target reach the bumped version?"; only the exact per-file manifest answers "which files moved, and from which worktree base?" — the audit question a post-incident review or a partial-sync diagnosis needs. Capturing the engine's `buildReceipt` (derived from the worktree's own `git status`) makes the manifest a deterministic record, not a hand-typed reconstruction that drifts from what actually landed.

### 8. Multi-CLI Targets Re-Emit The Full Derived CLI Tree, Not Just The Scaffold

For any USE template whose `template_type` resolves to `multi-cli` (per `sync-manifest.yaml::multi_cli_overlays`), EVERY `/sync-to-use` MUST re-emit the target's FULL derived CLI tree — NOT only the post-distribute _scaffold_ (the symlinks + conditional manifest of MUST Rule 5 / `coc-sync.md` Step 4.6). The derived tree spans three emitters (the orchestration — scratch `--out` dir → placement into the target — is owned by `coc-sync.md` Steps 6.5–6.7 (the emitter half — a distinct set of steps from Step 4.6's symlink+manifest scaffold; the two write DISJOINT file sets and carry no ordering dependency on each other, so the DO block below MAY present them in either order) + `commands/sync-to-use.md` step 6, REFERENCED here per `specs-authority.md` Rule 9, not restated):

- the per-CLI artifact trees `.codex/**` + `.gemini/**` — `node .claude/bin/emit-cli-artifacts.mjs --target <lang> --out <dir>` (Step 6.6);
- the unified `.coc/**` tree — `node .claude/bin/emit-coc.mjs --target <lang> --lane use --out <dir>` (Step 6.7);
- the repo-root CLI baselines `AGENTS.md` + `GEMINI.md` — `node .claude/bin/emit.mjs --all --lang <lang> --out <dir>` (Step 6.5).

Emitting the scaffold and treating it as the WHOLE multi-CLI obligation — skipping the derived-tree re-emit — is BLOCKED. (Flag asymmetry, verified against each tool's `parseArgs`: the two CLI-tree emitters take `--target`; `emit.mjs` takes `--lang`. The two CLI-tree emitters REQUIRE `--out`; `emit.mjs` defaults `--out` to a throwaway tmp dir — so the sync flow MUST always pass `--out` to place the derived tree into the target.) The emitters are deterministic, so re-emitting when nothing changed is a safe no-op — the unconditional mandate removes the change-detection judgment the scaffold-only reading got wrong.

```bash
# DO — multi-cli target: re-emit the full derived tree, THEN the scaffold
# $LANG is the /sync-to-use <lang> invocation's language variant (py/rs — fixed per invocation, per Rule 1);
# $OUT is the target's scratch/worktree out-dir. Run these three emits for EACH manifest-enumerated target (Rule 1):
node .claude/bin/emit-cli-artifacts.mjs --target "$LANG" --out "$OUT"   # .codex/** + .gemini/**
node .claude/bin/emit-coc.mjs --lane use --target "$LANG" --out "$OUT"  # .coc/**
node .claude/bin/emit.mjs --all         --lang   "$LANG" --out "$OUT"   # AGENTS.md + GEMINI.md
# place the derived trees into the target (coc-sync.md Steps 6.5–6.7), THEN the symlinks + manifest (Step 4.6 / MUST-5)

# DO NOT — scaffold only (symlinks + manifest), skip the derived-tree re-emit
# → 19 changed commands/skills ship stale .codex/.gemini for the multi-cli target (coc-rs #48, 67-file gap)
```

**Post-emit idempotency verification (MUST):** after the re-emit lands in the target, a SECOND emit of the same trees into a scratch dir MUST produce zero further `git status` changes at the target — the emitters are deterministic, so a non-empty second-pass diff means the first re-emit did not run OR ran against stale composition. This is the USE-lane analogue (in intent) of the BUILD-lane `sync-tier-aware.mjs --build <target> --verify` gate (F11) — mechanically performable (deterministic emit + `git status`) but **the re-emit idempotency check itself is still NOT wired** as an exit-code gate (Phase-2 detector deferred per the Rule 8 Wiring below; Phase-1 enforcement is the manual gate-review sweep) — the check that was ABSENT when two `coc-sync` agents diverged into complementary partials.

**A WEAKER but WIRED USE-lane gate now exists (loom#1756); it is NOT the idempotency check.** `sync-gate2-worktree.mjs --finalize` reads the target's `repos.<lang>.templates[].clis` and, for a multi-CLI template, exits non-zero when (a) an owed derived tree is absent/empty, or (b) the run changes a path under the corpus the CLI surfaces are DERIVED from (`.claude/{rules,agents,skills,commands}/`, `CLAUDE.md`) while changing ZERO owed derived path — the stale-but-present case a presence check cannot see, and the exact 2026-08-15 coc-base shape. Clause (b) is a CO-CHANGE coupling test: its blind spot is a corpus delta projecting into no CLI surface, where it refuses a correct run, failing SAFE. The idempotency check remains owed.

**BUILD-lane clause (#181) — a `build_multi_cli` BUILD target re-emits the SAME full derived tree at Gate-2.** For any BUILD target with `repos.<target>.build_multi_cli == true` (today `py` + `rs`; base/prism absent ⇒ false — the positive-opt-in allowlist shape), EVERY `/sync-to-build` MUST ALSO re-emit the full derived CLI tree — `.codex/**` + `.gemini/**` (`emit-cli-artifacts.mjs --target <target>`), `.coc/**` (`emit-coc.mjs --target <target> --lane build` — omitting it withholds the BUILD-bound `use_exclude` artifacts), `AGENTS.md` + `GEMINI.md` (`emit.mjs --all --lang <target>`) + the `codex-mcp-guard` symlink/external tree (MUST-5) — into the stage-only worktree via the two-phase flow (`coc-sync.md` § "BUILD multi-CLI targets" / `sync-to-build.md` Step 6), NOT only the engine's `.claude/` apply. Shipping the `.claude/` tree and skipping the derived-tree re-emit for a `build_multi_cli` target is BLOCKED — the CC-only BUILD PR the #181 gap named. The BUILD-lane check is a WIRED exit-code gate — `sync-tier-aware.mjs --build <target> --verify --assert-derived-trees --out <worktree>` asserts every derived tree PRESENT (exit 1 on any missing) and MUST be clean BEFORE `--finalize`. Since loom#1756 the driver ALSO enforces presence + corpus co-change at `--finalize` on BOTH lanes, so the two lanes carry the SAME wired floor. A non-`build_multi_cli` BUILD target ships CC-only and this clause does not apply; the USE-lane clause above is UNCHANGED.

```text
# DO — build_multi_cli target: two-phase, re-emit the full derived tree, gate it, THEN finalize
--stage-only → emit-cli-artifacts.mjs/emit-coc.mjs --lane build/emit.mjs into <scratch> → --assert-derived-trees (clean) → --finalize
# DO NOT — bare single-shot on a build_multi_cli target (the #181 gap). Since loom#1690 the
# driver REFUSES this (exit 2, before any fetch/worktree) instead of shipping CC-only silently.
node .claude/bin/sync-gate2-worktree.mjs --lane build --target py   # single-shot skips the derived-tree enrichment
```

**BLOCKED rationalizations:**

- "The step is titled 'scaffold', so symlinks + manifest IS the whole obligation"
- "The derived CLI trees are a /migrate-time concern, not a /sync-to-use one"
- "Only the CC tree (`.claude/**`) changed; the codex/gemini/.coc trees can lag one cycle"
- "The consumer's /sync-from-template will refresh the top-level overlays later"
- "The other coc-sync agent already re-emitted; mine can mirror just the scaffold"
- "19 changed commands is a small delta; the stale derived trees are close enough"

**Why:** every loom cycle that touches a composed source (`.claude/rules/`, `commands/`, `skills/`, `agents/`) changes what the multi-CLI derived trees (`.codex/**`, `.gemini/**`, `.coc/**`, `AGENTS.md`, `GEMINI.md`) should contain; a multi-cli target that receives only the scaffold ships STALE Codex/Gemini/`.coc` artifacts that silently diverge from the CC source the same cycle. This has a SECURITY dimension: `AGENTS.md` / `GEMINI.md` are the Codex/Gemini SECURITY baselines (they carry the emitted `security.md` / `zero-tolerance.md` MUST clauses), so a scaffold-only sync leaves them stale — a newly-landed security MUST clause silently never reaches the Codex/Gemini lanes, while the CC lane enforces it. (The codex-mcp-guard policy-tree — the `../.codex-mcp-guard` symlink target — is the sibling half, covered by MUST-5.) "Scaffold" reads as "symlinks + manifest only" — the literal reading that made the rs `coc-sync` agent skip the re-emit and ship 67 stale files (coc-rs #48). The unconditional re-emit + the idempotency check convert an agent-judgment call into a structural obligation with a mechanical verification.

### 9. Every Gate-2 Target's VERIFIABILITY Is Determined And Surfaced Before Its PR Is Handed Over

A Gate-2 distribution asserts "this tree landed, CI-gated". That assertion is only true if the TARGET can be gated. Before handing any Gate-2 PR to the operator, the target's base-branch verifiability MUST be DETERMINED from the target's own branch protection and SURFACED as a named verdict — `verifiable` (≥1 required status check on the base) / `unverifiable` (no protection, no status-check rule, or a rule naming zero contexts) / `unknown` (the probe errored). `sync-gate2-worktree.mjs` does this structurally: it probes `repos/<owner>/<repo>/branches/<base>/protection` BEFORE any commit/push side effect, writes the verdict to stderr, and records it in the receipt as `target_verifiability` (Rule 7's receipt gains the field). Handing over a Gate-2 PR with the verdict UNDETERMINED is BLOCKED; so is reporting a distribution complete while omitting an `unverifiable`/`unknown` verdict from the completion claim.

**Advisory on PR-open, REFUSING on auto-merge — the asymmetry is the rule, not an implementation detail.** PR-open proceeds on an `unverifiable` verdict (loud notice only): loom does not own the target's branch protection and MUST NOT edit it (`repo-scope-discipline.md`), so refusing would convert a gap loom cannot fix into a distribution outage — the target falls silently behind canon, which is worse than an informed merge. `--merge` REFUSES (exit 6, PR left OPEN) unless `--accept-unverified-target` is passed: on that path no human sits between the verdict and the merge, so the exit code is the only carrier the operator can read. `unknown` refuses on the same footing as `unverifiable` — an errored probe is ZERO evidence, never an all-clear (`evidence-first-claims.md` MUST-3).

```bash
# DO — determine, surface, and let the exit code carry the auto-merge verdict
node .claude/bin/sync-gate2-worktree.mjs --lane build --target <t> --finalize --worktree "$wt" --json
# → stderr: "target verifiability [unverifiable] <owner>/<repo>@main — no-branch-protection"
# → receipt: "target_verifiability": {"verdict":"unverifiable","reason":"no-branch-protection"}
# → --merge on that verdict: exit 6, PR left OPEN, waiver named in the message

# DO NOT — hand over the PR with the verdict undetermined, or read "no checks reported" as a pass
gh pr checks <N>   # "no checks reported on the branch" — this is NOT green, and NOT red
# DO NOT — probe with object construction; a missing key yields null and cannot
# distinguish ABSENT from PRESENT-AND-NULL (two repo states, two different remedies)
gh api repos/<o>/<r>/branches/main/protection -q '.required_status_checks.contexts | length'
```

**BLOCKED rationalizations:**

- "`gh pr checks` printed nothing, so there is nothing failing"
- "The other four targets have CI, so the fleet is gated"
- "It's a distribution PR, the content was already verified at loom"
- "Adding CI to the target is out of scope, so the verdict is not actionable" (the verdict is the HANDOVER, not the fix)
- "A 404 from the protection endpoint means the probe failed" (on that endpoint 404 IS the answer: unprotected)
- "The probe errored, so assume it's like its siblings"

**Why:** "No checks reported" is neither green nor red — it is the ABSENCE of an instrument, and an operator who reads it as either is acting on a non-discriminating signal (`instrument-discipline.md` MUST-1). The verdict converts an invisible structural property of the target into a named, recorded fact at the one moment the operator can still act on it, and the auto-merge refusal removes the only path where nobody would have read it. Measured instance: a Gate-2 PR into a target running no `validate` workflow, while four sibling targets ran one, sat unmergeable-or-unverifiable for a full session because nothing had said the target was unverifiable BY CONSTRUCTION.

## MUST NOT

- **Hand over a Gate-2 PR whose target verifiability is UNDETERMINED, treat `gh pr checks`'s "no checks reported" as green, or auto-merge into an `unverifiable`/`unknown` target without the explicit `--accept-unverified-target` waiver.**

**Why:** loom asserts a CI-gated distribution contract; a target with no required check cannot honour it, and the absence of an instrument reads identically to a clean one in `gh pr checks` output.

- **Run `/sync-to-*` without first parsing `sync-manifest.yaml::sync_targets[].templates[].repo` into a variable.**

**Why:** The manifest is the structural source of truth. Any sync that doesn't read it is operating on stale memory.

- **Claim sync completion until the per-template verification table is emitted with all rows ✓.**

**Why:** Partial completion claims ship the failure mode this rule prevents — a stale template hides behind a "✓ /sync-to-use py done" message.

- **Skip a declared template because it "rarely changes" or "isn't actively maintained".**

**Why:** Skipping is the mechanism by which rb missed 2.19.0; an inactive template is more dangerous, not less, because its drift is invisible to active workflows. Retirement is a manifest edit (`templates: []` per the prism precedent), not a per-cycle skip.

- **Write session-notes counts that exceed the verifying command's output.**

**Why:** "Round number" cognition rounds 5 templates down to 4; rounding 4 to 5 is rare. Either way, the verifying command is the truth.

- **Ship a sync that emits a `.claude/**` artifact into a path the target's `.gitignore` swallows, OR disable the post-sync `git check-ignore` gate.**

**Why:** A swallowed artifact lands on disk now but a fresh clone never tracks it — the tracked importer throws at runtime (loom#676). The re-include + the swallowed-gate are the only structural defense.

- **Ship a multi-CLI `/sync-to-use` that emits only the scaffold (symlinks + manifest) and skips the full derived-CLI-tree re-emit (`.codex/**`, `.gemini/**`, `.coc/**`, `AGENTS.md`, `GEMINI.md`).**

**Why:** The scaffold is not the tree; a scaffold-only multi-cli sync ships stale Codex/Gemini/`.coc` artifacts that silently diverge from the CC source the same cycle (coc-rs #48, 67-file gap).

- **Ship a bare single-shot `/sync-to-build` on a `build_multi_cli` target (`py`/`rs`), skipping the two-phase derived-CLI-tree re-emit (`.codex/**`, `.gemini/**`, `.coc/**`, `AGENTS.md`, `GEMINI.md`) + the `--assert-derived-trees` presence gate (#181).**

**Why:** A single-shot `build_multi_cli` sync ships a CC-only BUILD PR — `.codex/.gemini/.coc` absent, the exact #181 gap — while the CC lane silently advances; the wired `--assert-derived-trees` exit-code gate makes the omission loud before `--finalize`. Since loom#1690 BOTH halves are enforced by `sync-gate2-worktree.mjs` itself: it reads `build_multi_cli`, refuses the single-shot outright (exit 2), and re-asserts derived-tree presence at `--finalize` (exit 4) — so neither half depends on the operator remembering a step.

## Trust Posture Wiring

MUST Rules 1–4 above carry three independent Trust Posture Wiring profiles, partitioned by signal carrier: Rules 1/2(version-stale)/4 use `halt-and-report` lexical detection, Rule 3 uses `block` structural-JSON detection, and Rule 2(headroom-floor) uses `block` exit-code detection from the v6.2 validator. (MUST Rules 5–8 each carry their own canonical 8-field Wiring block below.) Only the headroom-floor sub-section binds a two-tier receipt band — it is the only MUST clause with a continuous numeric metric (`headroom_pct`) where the breach can be foreseen rather than only observed.

### Rules 1, 2 (version-stale ✗ row), 4 — enumeration + table + count discipline

- **Severity:** `halt-and-report` (agent surfaces, user adjudicates).
- **Grace period:** 7 days from rule landing (2026-05-06 → 2026-05-13, expired).
- **Regression-within-grace:** any new `/sync-to-*` invocation OR any `sync-manifest.yaml` edit that adds a template without canonical-schema VERSION field triggers emergency downgrade L5 → L4 per `trust-posture.md` MUST Rule 4.
- **Receipt:** SessionStart requires `[ack: sync-completeness]` if prior journal references `/sync-to-*` AND `posture.json::pending_verification` includes this rule_id.
- **Detection:** `cc-architect` mechanical sweep at `/codify`: (1) `grep -rn 'yq\|templates\[\]\.repo' .claude/commands/sync-to-*.md` — every `/sync-to-*` command body MUST enumerate from manifest; (2) AST sweep on `sync.md` / `sync-to-build.md` — every distribution loop MUST be preceded by manifest-enumeration. Probes `.claude/test-harness/probes/sync-completeness.probes.json` — NOT YET AUTHORED, declared in `phase2-deferrals.json::probe_authorship_deferrals`.

### Rule 3 — VERSION schema mismatch (structural)

- **Severity:** `block` — structural signal (missing JSON field, not regex). Per `hook-output-discipline.md` MUST-2, structural signals MAY carry block severity. Evidence: `"schema mismatch: <field path missing>"`.
- **Grace period:** 7 days from rule landing (expired); rs-family templates given one cycle to migrate.
- **Regression-within-grace:** any `/sync-to-use rs` invocation post-grace that writes a non-canonical schema → emergency downgrade.
- **Detection:** JSON-schema sweep on `.claude/VERSION` across every USE template post-sync — `upstream.version` field present AND value matches loom version.

### Rule 2 (headroom-floor ✗ row) — v6.2 BLOCK condition

The v6.2 plan ((loom-internal reference)) Shards 1+2 (merged PR #218, commit `75352dd`, 2026-05-15) added a `headroom_pct` column to Rule 2's verification table AND wired the per-CLI `headroom_floor_pct` as a BLOCK condition. F5 binds that structural defense to the Trust Posture system.

- **Severity:** `block` — structural signal (`emit.mjs` in default strict mode returns non-zero on breach; the exit code IS the signal, not a regex match). Per `hook-output-discipline.md` MUST-2, the structural exit is the correct carrier of `block` severity.
- **Grace period:** 7 days from PR #218 merge (2026-05-15 → 2026-05-22). During grace, the validator emits structured `headroom_floor_violations[]`; `coc-sync.md`'s `node …/emit.mjs --all --lang <py|rs>` invocations (Shard 2 wiring; cycle-2 dropped the explicit `--strict-headroom` opt-in; cycle-3 removed the legacy no-op accepting) propagate non-zero exit unconditionally for py/rs. Grace applies to operators running `emit.mjs` directly OUTSIDE `/sync-to-use`. The opt-in→opt-out flip (cycle-2) shipped 2026-05-15 (PR #230); cycle-3 (a) removed the legacy `--strict-headroom` accepting after a callsite sweep confirmed zero references.
- **Regression-within-grace:** any of (a) /sync-to-use invocation that passes `--no-strict-headroom` to the `node …/emit.mjs --all --lang <py|rs>` invocation in `coc-sync.md`'s baseline-emission step OR removes the emit invocation entirely (grep-stable on the invocation pattern, not the section number; v6.2 cycle-2 flipped strict mode to opt-out default — the regression is now passing the opt-out flag, not omitting the prior opt-in); (b) `sync-manifest.yaml` edit that adds a CLI variant OR lowers an existing `cli_variants.context/root.md.<cli>.headroom_floor_pct` value below 10 (Risk-0004 baseline) such that the current rs-lane state would ship; (c) `emit.mjs` patch that silently downgrades `validateAggregateHeadroom()` exit code OR a `coc-sync.md` invocation patched to discard the non-zero exit via `|| true`, `if`-branch, pipeline-without-`pipefail`, or `set +e` guard; (d) agent prose citing any `coc-sync.md`-listed BLOCKED-rationalization ("Pass --no-strict-headroom to unblock this sync") to bypass the validator — triggers emergency downgrade per `trust-posture.md` MUST Rule 4 (cumulative-window regression class).
- **Receipt:** SessionStart MUST require `[ack: sync-completeness]` in the agent's first response IF the most recent journal entry references `/sync-to-*` invocation AND any cli×lang headroom falls under the two-tier near-breach band: `headroom_pct < 13%` (3% above floor — covers ~2 cycles of routine emission drift, advisory band) emits the receipt as a soft signal; `headroom_pct < 11%` (1% above floor — hard near-breach) MUST emit the receipt as halt-and-report. The wider 13% band matches the routine-CRIT-rule emission swing (~500–800 B ≈ ~1% of 61,440 B cap) so the receipt fires BEFORE the breach is reached, not after. From current measured state (`journal/0074` § For Discussion #2: gemini rs 15.64% as the closest combo), 3 typical landings reach the 13% advisory; 4-5 reach the 11% halt-and-report — giving ~2-cycle / ~4-cycle lead time at present.
- **Detection:** (1) Structural — `emit.mjs` non-zero exit on any `headroom_floor_violations[]` entry (Shard 1 wired the validator at `.claude/bin/emit.mjs::validateAggregateHeadroom`; cycle-2 flipped strict mode to opt-out default — `--no-strict-headroom` is the test-harness escape, BLOCKED in production `/sync-to-use`); (2) Wiring — `coc-sync.md`'s baseline-emission step invokes emit.mjs for every py/rs distribution (Shard 2 wired; cycle-2 dropped the explicit `--strict-headroom` flag since strict is now the default); (3) `/codify` mechanical sweep — any session transcript citing `/sync-to-*` MUST show no `--no-strict-headroom` flag in the recorded invocation AND record `headroom_pct` for every cli×lang combo emitted; presence of the opt-out flag OR a missing headroom record is a HIGH finding for the `/codify` reviewer; (4) advisory hook detection of prose rationalizations is intentionally NOT added — would re-introduce the false-positive class `hook-output-discipline.md` MUST-2 blocks, and the structural exit is already authoritative. **Consequence:** prose-level rationalizations do NOT contribute to `trust-posture.md` MUST Rule 4 cumulative-window math; the structural exit code (mechanism 1) is the authoritative defense and fires BEFORE the prose rationalization can take effect. Adding an advisory hook here is BLOCKED. (5) Manifest-axis sweep at `/codify` — `yq '.cli_variants."context/root.md".codex.headroom_floor_pct, .cli_variants."context/root.md".gemini.headroom_floor_pct' .claude/sync-manifest.yaml` returns `>= 10` for both CLIs; any value below the Risk-0004 baseline is a CRIT finding. (5b) Exit-code-swallow sweep at `/codify` — `grep -nE 'emit\.mjs[^|;]*(\|\||&& :|2>/dev/null$|set \+e)' .claude/agents/management/coc-sync.md` returns 0 hits (cycle-2 regex no longer anchors on `--strict-headroom` since strict is the default; any exit-discard wrapper around the emit.mjs invocation is a HIGH finding).

### Rule 5 — external symlink target completeness

- **Severity:** `halt-and-report` at gate-review (cc-architect at `/codify` confirms every `.claude/`-copying sync command — `sync-to-*` + `sync-from-template` — carries the external-symlink-target step + this rule's clause). `advisory` at the structural layer (a post-sync external-target-freshness check is downstream-run; no loom-side block carrier per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing (2026-06-27 → 2026-07-04).
- **Cumulative posture impact:** same-class violations (a sync copying `.claude/` without syncing declared external symlink targets) contribute per `trust-posture.md` MUST-4 (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within 7 days routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated trigger key, so no self-referential `trust-posture.md` edit is required.
- **Receipt requirement:** SessionStart `[ack: sync-completeness]` IFF `posture.json::pending_verification` includes this rule_id (shared with the rule's existing ack; soft-gate).
- **Detection mechanism:** `cc-architect` mechanical sweep at `/codify` — `grep -nE 'multi_cli_overlays|symlinks|external.*target|codex-mcp-guard' .claude/commands/sync-from-template.md .claude/commands/sync-to-use.md` confirms each `.claude/`-copying sync command carries the external-symlink-target step; the downstream-run structural companion is a post-sync check that each declared external target's content == source.
- **Violation scope:** MUST Rule 5 (external symlink target completeness) fires the Wiring.
- **Origin:** journal/0352 (2026-06-27) — see Rule 5's own Origin line.

### Rule 6 — swallowed-artifact tracked-ness guarantee

- **Severity:** `block` at the structural CI/sync layer (`sync-tier-aware.mjs::findSwallowedArtifacts` is a `git check-ignore` exit-code signal — structural, so it MAY carry block per `hook-output-discipline.md` MUST-2; the post-sync gate hard-fails the run); `halt-and-report` at gate-review (cc-architect at `/codify` confirms any new `.claude/**` subtree whose basename collides with a common root ignore carries a `gitignore_reincludes` entry).
- **Grace period:** 7 days from rule landing (2026-06-28 → 2026-07-05).
- **Cumulative posture impact:** same-class violations (a sync shipping a swallowed `.claude/**` artifact, OR a colliding subtree added without a re-include) contribute per `trust-posture.md` MUST-4 (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within 7 days routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated trigger key, so no self-referential `trust-posture.md` edit is required.
- **Receipt requirement:** SessionStart `[ack: sync-completeness]` IFF `posture.json::pending_verification` includes this rule_id (shared with the rule's existing ack; soft-gate).
- **Detection mechanism:** structural — `sync-tier-aware.mjs::findSwallowedArtifacts` runs in BOTH the write path (`executePlan`, hard-fails the sync) AND the read-only `--verify` path (`verifyConsistency`, counts as OUT OF SYNC); regression-locked by `.claude/test-harness/tests/sync-tier-aware.test.mjs` § L676. Gate-review — `cc-architect` mechanical sweep at `/codify`: `grep -n 'gitignore_reincludes' .claude/sync-manifest.yaml` confirms a re-include exists for every `.claude/**` subtree whose basename matches a common root ignore.
- **Violation scope:** MUST Rule 6 (swallowed-artifact tracked-ness guarantee) fires the Wiring.
- **Origin:** loom#676 (2026-06-28) — a consumer's broad `lib/` ignore silently untracked `.claude/bin/lib/`; the negation + post-sync gate close the instance + the class.

### Rule 7 — per-target exact-manifest receipt

- **Severity:** `halt-and-report` at gate-review (cc-architect / reviewer at `/codify` confirms each enumerated target's Gate-2 distribution recorded the engine's `buildReceipt` per-file manifest, not a hand-typed list). `advisory` at the hook layer (receipt-presence is a session-history judgment property, not a single structural tool-call signal, per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing (2026-07-03 → 2026-07-10).
- **Cumulative posture impact:** same-class violations (a Gate-2 completion claim without the per-target exact-manifest receipt) contribute per `trust-posture.md` MUST-4 (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within 7 days routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated trigger key, so no self-referential `trust-posture.md` edit is required.
- **Receipt requirement:** SessionStart `[ack: sync-completeness]` IFF `posture.json::pending_verification` includes this rule_id (shared with the rule's existing ack; soft-gate).
- **Detection mechanism:** Phase 1 — `cc-architect` / reviewer mechanical sweep at `/codify`: any session transcript citing `/sync-to-build` or `/sync-to-use` MUST show a per-enumerated-target `buildReceipt` capture (`grep`-stable on the `--json` invocation of `sync-gate2-worktree.mjs` + the recorded `manifest{added,modified,deleted}` fields); a completion claim citing only the Rule-2 version table is a HIGH finding. Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout) — audit fixtures land with the detector at `.claude/audit-fixtures/exact-gate-tracking/` per `cc-artifacts.md` Rule 9 (shared with `artifact-flow.md` § "Exact Gate-1 / Gate-2 Tracking" MUST-2, its distribution-side companion).
- **Violation scope:** MUST Rule 7 (per-target exact-manifest receipt) fires the Wiring.
- **Origin:** Directive 1 (2026-07-03, co-owner-directed origination `journal/0403`) — the worktree-from-remote-main Gate-2 model's per-target manifest-receipt requirement; see the Origin line below.

### Rule 8 — multi-CLI full-derived-tree re-emit

- **Severity:** `halt-and-report` at gate-review (cc-architect / reviewer at `/codify` confirms every multi-cli `/sync-to-use` re-emitted the full derived tree — `.codex/**` + `.gemini/**` + `.coc/**` + `AGENTS.md` + `GEMINI.md` — not only the scaffold, and that the post-emit idempotency check ran). `advisory` at the hook layer for the USE-lane property (whether the FULL re-emit ran is judgment-bearing over the session's sync sequence, not a single structural tool-call signal, per `hook-output-discipline.md` MUST-2). **BUILD-lane addendum (#181):** the `build_multi_cli` BUILD lane carries the wired `sync-tier-aware.mjs --build <t> --verify --assert-derived-trees` **exit-code** gate (`block`-eligible structural signal per `hook-output-discipline.md` MUST-2 — a non-zero exit on any missing derived tree, not a prose judgment) — which coc-sync runs after emit and before `--finalize`. **USE-lane addendum (loom#1756):** `block` at the structural layer for the PRESENCE + CO-CHANGE floor — `sync-gate2-worktree.mjs --finalize` exits 4 when a template whose `templates[].clis` declares a non-`claude` CLI is missing an owed derived tree, or when the run moves the derived-FROM corpus while moving no owed derived path. That is an exit code, not a regex, so it MAY carry `block`. It does NOT cover the full-re-emit property above, which stays `advisory`/gate-review: the coupling test cannot distinguish a complete re-emit from a partial one that touched at least one derived path.
- **Grace period:** 7 days from rule landing (2026-07-11 → 2026-07-18).
- **Cumulative posture impact:** same-class violations (a multi-cli target that received the scaffold but not the full derived-tree re-emit) contribute per `trust-posture.md` MUST-4 (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within 7 days routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated trigger key, so no self-referential `trust-posture.md` edit is required.
- **Receipt requirement:** SessionStart `[ack: sync-completeness]` IFF `posture.json::pending_verification` includes this rule_id (shared with the rule's existing ack; soft-gate).
- **Detection mechanism:** Phase 1 — `cc-architect` / reviewer mechanical sweep at `/codify`: any session transcript citing `/sync-to-use` to a multi-cli target MUST show the three derived-tree emit invocations (`grep`-stable on `emit-cli-artifacts.mjs --target`, `emit-coc.mjs --target`, `emit.mjs --all --lang`) AND the post-emit idempotency check; a completion claim showing only the scaffold (symlinks + manifest) is a HIGH finding. **BUILD lane (#181):** any transcript citing `/sync-to-build` to a `build_multi_cli` target (`py`/`rs`) MUST show the same three emit invocations INTO the stage-only worktree PLUS a clean `--assert-derived-trees` exit-code gate (the structural check `sync-tier-aware.test.mjs` class N covers) AND the Step-0 `scan-synced-disclosure.mjs --check`; a bare single-shot `--lane build` on a `build_multi_cli` target is a HIGH finding. Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout) — audit fixtures land with the detector at `.claude/audit-fixtures/sync-completeness-multi-cli-reemit/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST Rule 8 (multi-CLI full-derived-tree re-emit) fires the Wiring.
- **Origin:** journal/0465 (2026-07-11, co-owner-directed `/govern` origination) — see Rule 8's Origin line below.

### Rule 9 — Gate-2 target verifiability

Ships canonical-8-field-compliant per `trust-posture.md` MUST-8 (this clause lands AT/AFTER the MUST-8 SHA); the pre-existing Wiring blocks above are unchanged.

- **Severity:** `block` at the structural layer for the AUTO-MERGE half — `sync-gate2-worktree.mjs` exits 6 on a non-`verifiable` verdict under `--merge` without `--accept-unverified-target`; that is an exit-code signal, not a regex match, so it MAY carry `block` per `hook-output-discipline.md` MUST-2. `halt-and-report` at gate-review for the SURFACING half (cc-architect / reviewer at `/codify` confirm each Gate-2 handover carried a named verdict). Deliberately NOT `block` at PR-open: loom cannot edit the target's protection (`repo-scope-discipline.md`), so blocking there would trade a verifiability gap for a distribution outage.
- **Grace period:** 7 days from clause landing (2026-08-16 → 2026-08-23).
- **Cumulative posture impact:** same-class violations (a Gate-2 PR handed over with the verdict undetermined; a completion claim omitting an `unverifiable`/`unknown` verdict; `gh pr checks`'s "no checks reported" read as green) contribute per `trust-posture.md` MUST-4 (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within 7 days routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated trigger key, so no self-referential `trust-posture.md` edit is required. Same no-dedicated-key disposition Rules 5–8 took.
- **Receipt requirement:** SessionStart `[ack: sync-completeness]` IFF `posture.json::pending_verification` includes this rule_id (shared with the rule's existing ack; soft-gate).
- **Detection mechanism:** structural — `sync-gate2-worktree.mjs::classifyTargetVerifiability` + `probeTargetProtection` run on every PR-opening path (`commitPushPrMaybeMerge`, before `stageBranchCommit`), and the `--merge` branch refuses non-`verifiable` verdicts with exit 6. Fixtures: `.claude/audit-fixtures/gate2-target-verifiability/` (19 bipolar cases, registered in `.claude/test-harness/ci-audit-fixtures.json` with `min_cases: 19`, run by `run-audit-fixtures.mjs`); its README records the five measured mutations that red it, including the `?.`-collapse mutation that reds ONLY the ABSENT-vs-PRESENT-AND-NULL discrimination case and the two source pins that red if the probe or the refusal is unwired. Gate-review — cc-architect / reviewer at `/codify`: any transcript citing `/sync-to-build` or `/sync-to-use` MUST show a `target_verifiability` verdict per enumerated target (grep-stable on the receipt field); a completion claim with no verdict, or with an `unverifiable` verdict left unreported, is a HIGH finding. Probes: the rule's existing `probe_authorship_deferrals` entry covers this clause (shared rule_id); no new probe suite is claimed, and none is asserted to exist.
- **Violation scope:** MUST Rule 9 (Gate-2 target verifiability) fires the Wiring.
- **Origin:** 2026-08-16 (loom#1745) — see Rule 9's Origin note in the § Origin line below.

Origin: 2026-05-06 (Rules 1–4) — see guide § "Origin — full prose" for the rb-missed-sync + schema-drift incident. v6.2 extension 2026-05-15 — F5 cc-architect R1 LOW from `journal/0073` closes the Trust Posture Wiring gap on the new headroom-floor BLOCK condition; cycle-2 (same-day) flipped `--strict-headroom` from opt-in to opt-out default per plan §5.1 invariant 5 (mirrors v2.13.0 `--strict-budget` rollout) after the v2.31.0 /sync-to-use cycle confirmed zero false-positive blocks across all 5 USE templates. Rule 5 added 2026-06-27 (journal/0352, co-owner-directed origination) — a downstream `/sync-from-template` consumer reported `extract-policies.mjs` was a no-op after a `.claude/`-only sync left the external `../.codex-mcp-guard` target stale. Rule 7 added 2026-07-03 (journal/0403, Directive 1 co-owner-directed origination) — the worktree-from-remote-main Gate-2 model requires capturing the engine's `buildReceipt` per-file manifest per enumerated target, the distribution-completeness companion to `artifact-flow.md` § "Exact Gate-1 / Gate-2 Tracking". Rule 8 added 2026-07-11 (journal/0465, co-owner-directed `/govern` origination) — the F2 divergence where two `coc-sync` agents split: the rs agent read the step-6 "scaffold" wording literally and skipped the derived-CLI-tree re-emit for a multi-cli target (67-file gap, coc-rs #48); the USE-lane analogue of the F11 BUILD-lane `--verify` completeness gate. Rule 9 added 2026-08-16 (loom#1745) — a Gate-2 PR into a target with NO required status check on `main`, while four sibling targets ran a `validate` workflow: `gh pr checks` reported "no checks reported on the branch", which is neither green nor red, and the PR sat unmergeable-or-unverifiable for a session. The root cause was NOT the target's missing workflow but loom asserting a CI-gated distribution contract it never checked the target could honour; the fix determines and surfaces the verdict at handover and refuses only the auto-merge path. Depth: `guides/rule-extracts/sync-completeness.md` § "Rule 9 — target verifiability".

**Length rationale (per `rules/rule-authoring.md` MUST NOT § "Rules longer than 200 lines").** Rule body exceeds the 200-line guidance. Named rationale: **sync-distribution-completeness scope** — the rule codifies nine MUST rules spanning the full `/sync-to-*` completeness contract (enumerate-every-template, per-target version + headroom-floor, structural-JSON manifest, verified-command session-notes counts, external-symlink-target trees, gitignore-swallowed-artifact tracked-ness, the per-target exact-manifest receipt, the multi-CLI full-derived-tree re-emit, and the Gate-2 target-verifiability verdict), each carrying the DO/DO-NOT + `**Why:**` `rules/rule-authoring.md` MUST-3/4 require, plus eight Trust-Posture-Wiring blocks (Rules 1–4 share three signal-carrier-partitioned profiles per § Trust Posture Wiring; Rules 5–9 each carry their own canonical 8-field block — Rule 8's being the `trust-posture.md` MUST-8-compliant post-cutoff one). The rule is `priority: 10` + `scope: path-scoped`, so it pays NO baseline-emission cost (loaded only in sessions matching its `paths:` globs) and `rules/rule-authoring.md` Rule 10's proximity-band gate does NOT fire. Splitting the nine completeness invariants across sibling rules would fragment the "every template reached, every landing verified" contract and force cross-rule lookups at every `/sync-to-*`. Per `rules/rule-authoring.md` MUST NOT § "Rules longer than 200 lines": overage is permitted with named rationale anchored at Origin. Sibling precedent: `artifact-flow.md` + `upstream-issue-hygiene.md` length rationales.
