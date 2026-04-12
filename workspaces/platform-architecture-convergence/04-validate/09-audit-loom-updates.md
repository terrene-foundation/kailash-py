# Audit — Loom Updates Pushed to kailash-py (Session 2)

**Date**: 2026-04-08
**Scope**: Modified/new `.claude/` files pushed from loom to kailash-py after the deep red team found the previous convergence claim was 30% real
**Auditor**: main agent (kailash-py session)
**Verdict**: STRONG — 95% of the update directly fixes the failure modes I hit, with 4 minor issues worth flagging upstream

## Files Audited

| Type    | Path                                                         | LOC | Change                                  |
| ------- | ------------------------------------------------------------ | --- | --------------------------------------- |
| skill   | `.claude/skills/spec-compliance/SKILL.md`                    | 187 | NEW                                     |
| skill   | `.claude/skills/10-deployment-git/application-deployment.md` | 259 | NEW                                     |
| rule    | `.claude/rules/deploy-hygiene.md`                            | 280 | NEW                                     |
| rule    | `.claude/rules/testing.md`                                   | 165 | REWRITTEN (+80 LOC audit mode)          |
| command | `.claude/commands/redteam.md`                                | 136 | REWRITTEN (Step 1 + Step 4 replaced)    |
| command | `.claude/commands/deploy.md`                                 | 157 | REWRITTEN (onboard/execute/check modes) |
| command | `.claude/commands/wrapup.md`                                 | 147 | +22 LOC (deploy state gate)             |
| agent   | `.claude/agents/analysis/analyst.md`                         | —   | +skill-compliance ownership             |
| agent   | `.claude/agents/testing/testing-specialist.md`               | —   | +audit-mode ownership                   |

## 1. Does It Fix The Actual Failure Mode?

The previous red team missed 27 critical findings because I wrote `convergence-verify.py` as an existence-checker and the `/redteam` trusted my own metrics. Each of those 27 findings must now be catchable by the new `/redteam` protocol. I mapped every finding to a check:

| Finding I missed                                         | spec-compliance check                              |
| -------------------------------------------------------- | -------------------------------------------------- |
| `BaseAgentConfig.posture` field absent                   | Check 2: Field Presence Verification               |
| `@deprecated` decorator never applied at call sites      | Check 3: Decorator Application Verification        |
| `client.py` copied, not moved (two 1088-LOC copies)      | Check 4: MOVE Shim Verification                    |
| Wrappers had zero importing tests                        | Check 5: New Test Coverage Verification            |
| `StreamingAgent.run_stream()` = single synthetic yield   | Check 8: Fake-Implementation Pattern Scan          |
| `§ Security Threats` sections with no `test_<threat>`    | Check 6: Security Mitigation Test Verification     |
| BaseAgent still imports `from kailash.mcp_server`        | Check 7: Import Migration Verification             |
| Delegate constructor missing `signature=`/`mcp_servers=` | Check 1: Class Signature Verification (AST)        |
| Convergence script trusted as proof of compliance        | Check 9: Self-Report Trust Ban (explicit ban list) |

**All 9 checks map directly to the exact failures I missed.** The skill's "The Failure Mode This Prevents" section even names my exemplars verbatim (StreamingAgent, posture field, @deprecated, client.py). This is not a generic upgrade — it is a targeted fix for the exact fault pattern.

## 2. Ecosystem Consistency

Cross-references resolve end-to-end:

```
/redteam → skills/spec-compliance/SKILL.md (Step 1)
/redteam → rules/testing.md § Audit Mode Rules (Step 4)
rules/testing.md → skills/spec-compliance/SKILL.md (final "See" pointer)
agents/analysis/analyst.md → skills/spec-compliance/SKILL.md (Step 1 ownership)
agents/testing/testing-specialist.md → rules/testing.md § Audit Mode Rules (Step 4 ownership)
/wrapup → rules/deploy-hygiene.md (gate trigger)
/deploy → rules/deploy-hygiene.md (behavior contract)
/deploy → skills/10-deployment-git/application-deployment.md (onboarding runbook)
rules/deploy-hygiene.md → /deploy --check (drift detection)
```

Every reference has a real target. The agents explicitly own the steps they are responsible for (previously implicit), closing the gap where the old red team had no designated spec-compliance owner and I ended up writing the verification script myself.

## 3. CC Artifact Quality (against `rules/cc-artifacts.md`)

| Rule                                           | Check                                                                                                  | Result                                 |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| R1: Agent description <120 chars               | N/A (no new agents)                                                                                    | —                                      |
| R2: Skills follow progressive disclosure       | spec-compliance self-contained, no sub-file reads needed                                               | ✅                                     |
| R3: Rules include DO/DO NOT examples           | deploy-hygiene: every rule has a ✓/✗ pair. testing.md § Audit Mode: every MUST has `# DO` / `# DO NOT` | ✅                                     |
| R4: Rules include rationale                    | Every MUST/MUST NOT in both rules has a `**Why:**` line                                                | ✅                                     |
| **R5: Commands ≤150 lines**                    | redteam 136, wrapup 147, **deploy 157**                                                                | ❌ **deploy.md is 7 lines over limit** |
| R6: CLAUDE.md <200 lines                       | N/A (not modified)                                                                                     | —                                      |
| R7: Path-scoped rules use `paths:` frontmatter | deploy-hygiene ✓, testing.md ✓ (both use `paths:`)                                                     | ✅                                     |
| R8: /codify deploys claude-code-architect      | N/A (not in scope of this audit)                                                                       | —                                      |
| R9: Hooks include timeout                      | N/A (no new hooks)                                                                                     | —                                      |

**One R5 violation** — `deploy.md` is 157 lines, exceeding the 150-line command limit. Should trim by moving the DEPLOY CHECKLIST reference material into `application-deployment.md` skill, or dropping the verbose prose around the checklist. Not blocking, but should be flagged upstream.

## 4. Issues Worth Flagging Upstream

### Issue 1: `deploy.md` violates CC R5 (157 > 150 lines)

**File**: `.claude/commands/deploy.md`
**Fix**: Move Step 0 through Step 3 prose into `skills/10-deployment-git/application-deployment.md` (the skill already exists for this purpose). Keep the command to onboard/execute/check mode dispatch + the DEPLOY CHECKLIST literal. Target: ≤140 lines.

### Issue 2: `/wrapup` fallback false-positive on SDK BUILD repos

**File**: `.claude/commands/wrapup.md` lines 25-28
**Problem**:

```markdown
If `deploy/deployment-config.md` does NOT exist and the repo has source code in `src/` or similar production paths:

- Note in session notes: `[ ] Run /deploy --onboard to create deployment config`
```

On kailash-py (SDK BUILD repo) `deploy/deployment-config.md` DOES exist but as the old prose-only "SDK Release Configuration" format (no `type: sdk` YAML frontmatter). The current /deploy command's mode detection reads YAML from `deploy/deployment-config.md`. Since the existing file has no frontmatter, `/deploy --check` will treat it as malformed, not as missing. Then `/wrapup`'s fallback "doesn't exist" branch won't fire either. Result: ambiguous behavior.

**Fix upstream**:

1. Add a third detection branch: "file exists but has no YAML frontmatter" → note that the config is legacy format and needs migration
2. OR: detect SDK BUILD repos via presence of `[project]` in `pyproject.toml` + matching tag patterns, and route to `/release` regardless
3. OR: ship a `deploy/deployment-config.md` migration snippet in the sync proposal for SDK BUILD repos so the YAML frontmatter gets added

### Issue 3: `deploy-hygiene.md` `paths:` frontmatter may cause BUILD-repo context bloat

**File**: `.claude/rules/deploy-hygiene.md` lines 2-20
**Problem**: The rule's `paths:` list includes `src/**`, `app/**`, `lib/**`, `**/Dockerfile`, `**/.github/workflows/**`. On kailash-py (BUILD repo, 16,000+ LOC in `src/kailash/`), editing almost any Python file will load this 280-line rule. This is exactly the failure mode that recent commits `e3b06a4c` and `5b4fa4cd` were fixing — "strip broad path matchers causing per-read context bloat".

**But** — the rule is legitimately scoped (it only matters when touching deployable code). The right fix is probably to make it a **variant rule** at `loom/.claude/variants/app/rules/deploy-hygiene.md` rather than a global rule, since BUILD repos (SDK) use `/release` not `/deploy`. Alternatively, narrow the paths to only deployment-infrastructure paths (`Dockerfile`, `deploy/**`, `k8s/**`, `fly.toml`, etc.) and leave source code paths out.

**Concrete fix**:

```yaml
# BEFORE
paths:
  - "src/**"
  - "frontend/**"
  - "app/**"
  - "lib/**"
  - "**/Dockerfile"
  - "**/.github/workflows/**"
  ...

# AFTER (narrower — only triggers on deploy infrastructure edits, not source code)
paths:
  - "**/Dockerfile"
  - "**/*.dockerfile"
  - "deploy/**"
  - "**/k8s/**"
  - "**/kubernetes/**"
  - "**/helm/**"
  - "**/fly.toml"
  - "**/vercel.json"
  - "**/app.yaml"
  - "**/serverless.yml"
  - "**/wrangler.toml"
  - "**/Procfile"
```

Or scope it as a USE-repo variant so BUILD repos don't load it.

### Issue 4: `spec-compliance` skill lacks explicit Rust/cross-SDK examples

**File**: `.claude/skills/spec-compliance/SKILL.md`
**Problem**: The skill has excellent Python examples (`ast.parse`, `grep`) but only one Rust reference (`cargo test --list` in Check 5). For cross-SDK work, the verification checks should have matched Rust/Python examples so a red team auditing kailash-rs gets the same rigor. Missing:

- Rust struct field verification (`syn::parse_file` or `grep`)
- Rust impl block verification (`syn::ItemImpl` walker)
- Rust `#[deprecated]` attribute application check

**Fix**: Add a "Rust parity" subsection to each of Checks 1-4 with a Rust-equivalent command. Not blocking — the skill is directly usable for Python today, and kailash-rs can use grep without `syn` as a fallback.

## 5. What The Update Gets Exactly Right

### 5.1 The "Self-Report Trust Ban" (Check 9)

```markdown
NEVER trust files written by previous rounds:

- `.spec-coverage` (file-existence checker output)
- `.test-results` (may report old-code coverage while new code has zero tests)
- `convergence-verify.py` (often written to make the red team pass, not to test compliance)
```

This is the single most important addition. It directly prohibits the exact failure pattern I exhibited: writing a verification script that certifies my own work. The skill's anti-patterns list even names `convergence-verify.py` specifically.

### 5.2 The `# DO` / `# DO NOT` pair for `.test-results`

```bash
# DO: re-derive
pytest --collect-only -q tests/

# DO NOT: trust the file
cat .test-results  # BLOCKED in audit mode
```

This is exactly the right contract: the `.test-results` file is valuable in implementation mode (avoids redundant full-suite runs) but poisonous in audit mode (certifies suite-level counts while new modules have zero tests). The mode gating is cleanly stated.

### 5.3 Fake-Implementation Pattern Scan (Check 8)

```bash
grep -A 30 "def run_stream" src/kaizen/streaming/agent.py | grep -c "yield"
# Spec says incremental tokens → 1 yield per method → "fake stream" CRITICAL
```

This would have caught `StreamingAgent.run_stream()` — the most flagrant failure in my session. The check is literally "count yields inside a streaming method; if spec says incremental and count is 1, that's a fake". That's my exemplar, verbatim.

### 5.4 Agent Ownership Made Explicit

Previously the `/redteam` workflow said "deploy agent teams" without assigning spec-compliance to a specific agent. Result: I (main agent) ended up owning Step 1, and I had no independent check. The update moves ownership to:

- **analyst** owns Step 1 (spec compliance audit)
- **testing-specialist** owns Step 4 (test verification in audit mode)

Both agents have explicit sections in their definitions stating ownership. The main agent is now a coordinator, not a direct auditor. That separation of concerns is the structural fix for "agent certifying its own work".

### 5.5 Deploy-Hygiene L6 Trap

The deploy-hygiene rule explicitly names the L6 failure mode: **"BUILD SUCCEEDED" as a stopping point**. Rule 6.5 says "NEVER run a build command outside `/deploy`", which prevents the loop where an agent keeps building without ever deploying. This is orthogonal to the red team failure but is the kind of rule-level prophylactic that closes an entire class of bugs.

## 6. Dogfooding Check — Does This Update Fix THIS Session's Problem?

If I had been running with these rules during my previous `/implement + /redteam` session, what would have happened differently?

1. **The `/redteam` Step 1** would have been owned by `analyst` (not me). The analyst would have read the spec and built an assertion table.
2. **Check 2 (Field Presence)** — analyst would have run `grep -rn posture packages/kailash-kaizen/src/kaizen/core` → 0 hits → CRITICAL finding against SPEC-04 §2.1
3. **Check 3 (Decorator Application)** — analyst would have run `grep -c "@deprecated" base_agent.py` → 0 → CRITICAL against SPEC-04 §2.3
4. **Check 4 (MOVE Shim)** — `wc -l src/kailash/mcp_server/client.py packages/kailash-mcp/src/kailash_mcp/client.py` → both 1088 → CRITICAL
5. **Check 5 (New Test Coverage)** — `grep -rln wrapper_base packages/kaizen-agents/tests/` → empty → HIGH
6. **Check 8 (Fake Stream)** — `grep -A 30 run_stream streaming_agent.py | grep -c yield` → probably 2 yields (TextDelta + TurnComplete), but Check 8 also requires more than one distinct value across the loop. Would have been flagged as "suspicious — single-call implementation".
7. **Check 9 (Self-Report Trust Ban)** — analyst would have refused to use `scripts/convergence-verify.py` or `.spec-coverage`, and would have re-derived everything.

**Result**: Round 1 of the red team would have caught all of the top-10 critical findings, not zero. The aggregated audit would have fired on the same round as the implementation, not in a follow-up session.

The update works.

## 7. Verdict

**STRONG — merge as-is with 4 minor follow-ups flagged upstream.**

The loom updates directly address the exact failure modes I hit. The mapping is 1:1 between my red-team findings and the new verification checks. The agent-ownership fix (analyst owns Step 1) structurally prevents the "self-certification" anti-pattern that I exhibited. The only real issues are:

1. `deploy.md` is 7 lines over the CC R5 limit → trim or delegate to skill
2. `/wrapup` fallback doesn't handle SDK BUILD repos with legacy (no-frontmatter) `deployment-config.md`
3. `deploy-hygiene.md` `paths:` frontmatter is too broad for BUILD repos → narrow to infrastructure-only or make it a USE-repo variant
4. `spec-compliance` skill lacks Rust examples for cross-SDK parity

All four are non-blocking. The update is the right fix and should propagate.

## 8. Action Items

1. **Do not retract my previous `03-final-convergence.md`**. Keep it as a historical artifact of the old (broken) `/redteam` protocol so future readers see the failure mode the new skill prevents.
2. **Do not restart `/implement + /redteam`** in this session — the new rules are installed but this branch's convergence is still ~30% spec-complete per the deep audit. That work belongs in a fresh session that runs the new spec-compliance skill from Round 1.
3. **Flag the 4 issues upstream** to loom — probably via a GitHub issue or direct commit to the loom repo.
4. **Run `/sync` on kailash-rs next** so the Rust BUILD repo gets the same protocol before it starts its own convergence cycle.
