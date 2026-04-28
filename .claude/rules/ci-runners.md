---
priority: 10
scope: path-scoped
paths:
  - ".github/workflows/**"
  - "**/ci/**"
  - "**/.github/**"
---

# CI Runner Rules

<!-- slot:neutral-body -->

Self-hosted CI runner hygiene. Language-agnostic — applies to every project using GitHub Actions self-hosted runners regardless of SDK language.

See `.claude/guides/rule-extracts/ci-runners.md` for the full enforcement-grep snippet, post-mortem evidence, and the kailash-rs CI cascade waves 6-18 narrative. For recovery protocols, service-management commands, and step-by-step troubleshooting, see `skills/10-deployment-git/ci-runner-troubleshooting.md`.

## MUST Rules

### 1. Every Toolchain-Consuming Job Includes A Toolchain Setup Step

Every job that invokes a language toolchain (`cargo`, `maturin`, `rustc`, `npm`, `pnpm`, `bundle`, etc.) MUST include a dedicated toolchain setup step (e.g. `dtolnay/rust-toolchain@stable`, `actions/setup-node`, `ruby/setup-ruby`) as one of its earliest steps — even if a previous job in the same workflow already installed the toolchain.

```yaml
# DO — every job re-establishes its own toolchain
steps:
  - uses: actions/checkout@v4
  - uses: dtolnay/rust-toolchain@stable
  - run: cargo build --release

# DO NOT — relying on a sibling job's toolchain install
steps:
  - uses: actions/checkout@v4
  - run: cargo build --release  # fails if PATH was re-written by an earlier job
```

**Why:** Self-hosted runners do not reset `PATH` between jobs cleanly. A sibling job that reinstalled `rustup` or ran `nvm use` leaves the runner with a missing or wrong-version proxy binary. Each job re-establishing its own toolchain is the only structural defense.

### 2. Restart The Runner After Changing Its Environment File

After editing the runner's `.env` file (`~/actions-runner-*/.env`), the runner MUST be restarted via `launchctl unload && launchctl load` (macOS) or `systemctl restart` (Linux). Running jobs MUST be allowed to complete under the old environment before the restart.

```bash
# DO — explicit unload, wait for in-flight jobs, reload
launchctl unload ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist
launchctl load   ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist

# DO NOT — edit .env and expect new jobs to pick up changes
vim ~/actions-runner-<name>/.env  # next queued job still reads the cached old env
```

**Why:** The runner daemon reads its `.env` once at process startup. Silent drift between "what operators edited" and "what jobs actually ran with" is invisible until a job fails with a missing variable.

### 3. Post-fmt Cascade Discovery Protocol

When `Format` (or any early short-circuiting gate) transitions from red to green for the first time in a long while, the session MUST expect multiple subsequent failures and budget for multi-wave triage. A red fmt gate short-circuits the pipeline — Clippy, Docs, Deny, Test, MSRV, and Integration Tests are SKIPPED, not failed. Pre-existing failures accumulate invisibly and surface one-wave-at-a-time once fmt is green.

```yaml
# DO — tight triage loop until all gates green
# push → inspect failing gate → fix root cause → push → repeat
# DO NOT — declare victory after fmt goes green (the other gates were skipped, not passing)
```

**BLOCKED rationalizations:** "Fmt is green, CI is fixed" / "The other gates were skipped, so they're passing" / "We can triage the rest in parallel branches" / "These failures are pre-existing, not our problem".

**Why:** Short-circuit semantics hide months of accumulated failures behind a single red fmt. Declaring "fixed" after fmt green leaves the downstream backlog to surface on the next unrelated PR. Parallel triage branches break because each wave's fix depends on the previous wave's state.

### 4. Runner Auto-Update Disconnect Recovery

If `gh api repos/<org>/<repo>/actions/runners` returns 0 runners while the runner's stdout log tails show `Connected to GitHub` and `Listening for Jobs`, the runner auto-updated mid-session and its in-flight job is orphaned. The session MUST restart the runner service AND trigger a fresh run via an empty commit.

```bash
# DO — re-register the runner and trigger a fresh run
launchctl unload ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist
launchctl load   ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist
git commit --allow-empty -m "chore(ci): trigger fresh run post-runner-update"
git push

# DO NOT — rerun the orphaned run; the dead worker still owns the job
gh run rerun <run-id> --failed
```

**BLOCKED rationalizations:** "The runner log says Connected, it must be fine" / "Wait for the hung job to time out on its own" / "Re-run the failed job, it'll get picked up".

**Why:** Auto-update renames and replaces the worker binary. Jobs assigned to the dead worker cannot be claimed by the new worker; GitHub's dispatcher needs a new trigger. Without the service restart, the "Connected" log is from a fresh worker that never knew about the orphaned job, and the hung run blocks the PR for hours.

### 5. Release-Upload Jobs Declare `contents: write` Permission

Every workflow job invoking `gh release upload`, `gh release create`, or `actions/upload-release-asset` MUST declare `permissions: contents: write` at workflow- or job-level. Relying on the default `GITHUB_TOKEN` scope is BLOCKED.

```yaml
# DO    permissions: { contents: write }  # at workflow- or job-level
# DO NOT rely on default GITHUB_TOKEN (silent 403; looks like transport error)
```

**BLOCKED rationalizations:** "The default token has always worked on this repo" / "Adding the permission explicitly is noise" / "We'll add it when we hit the 403" / "The failure is a network issue, not a permission issue" / "Tag-push triggers get contents: write automatically".

**Why:** Default `GITHUB_TOKEN` permissions are repository-scoped AND trigger-scoped. The failure manifests as a `403` on the HTTP call, not a clear error at parse time. Explicit `permissions: contents: write` is the single structural defense. See guide for the enforcement-grep snippet.

### 6. Binding-CI Paths Filter Matches The Core-Lang Pattern

Every binding-channel CI workflow (`python.yml`, `nodejs.yml`, `ruby.yml`, `wasm.yml`) MUST have a `paths:` filter covering the transitive dependency graph of the core language, not just the binding directory. Narrow enumerations of specific packages or crates silently stop matching whenever a new transitive dependency is added.

```yaml
# DO — broad filter matches the core-language CI's pattern
on:
  pull_request:
    paths: ["bindings/python/**", "crates/**", "Cargo.toml", "Cargo.lock", ".github/workflows/python.yml"]

# DO NOT — enumerate specific crates (misses kailash-core, kailash-nexus, etc. when new deps added)
on:
  pull_request:
    paths: ["bindings/python/**", "crates/kailash-capi/**", "crates/kailash-ml*/**"]
```

**BLOCKED rationalizations:** "The binding only depends on these packages today" / "Broad filter triggers too many unnecessary builds" / "We'll update the filter when we add new deps".

**Why:** Bindings transitively link most of a workspace. A narrow filter means a fix to a shared dependency triggers core CI but skips the binding CI, letting the binding ship broken.

### 6a. Binding-CI `paths-ignore` Covers ALL Doc-Only Surfaces

Every binding-channel CI workflow MUST include a `paths-ignore` filter excluding ALL doc-only surfaces — not just `**/*.md`. Edits to `.claude/`, `docs/`, `specs/`, `workspaces/`, `memory/` cannot affect compiled wheels. See guide for full `paths-ignore` block.

```yaml
# DO — paths-ignore covers ["**/*.md", ".claude/**", "docs/**", "specs/**", "workspaces/**", "memory/**", ".github/ISSUE_TEMPLATE/**"]
# DO NOT — partial paths-ignore: ["**/*.md"] (misses .claude/agents/bar.json firing CI redundantly)
```

**BLOCKED rationalizations:** "`**/*.md` already covers most doc files" / "Catch-all paths-ignore might mask real changes" / "Adding more excludes is over-optimization" / "The cost is small per PR" / "Each doc-only PR only burns 1 minute per workflow".

**Why:** Doc-only PRs trigger ALL binding workflows, each billed at 1-minute minimum on `ubuntu-latest`. ~150-200 min/month of pure overhead recoverable for zero correctness cost. See guide for 2026-04-25 kailash-rs gh-manager audit (66 of 580 GHA-billable minutes were doc-only triggers).

### 7. Workflow Crons MUST Have Explicit Cost Footer

Every `.github/workflows/*.yml` with `schedule: cron:` MUST include a comment block stating: cadence in plain English, worst-case monthly billing footprint at `ubuntu-latest` rates, and failure-mode behavior (fast-exit on no-op or always-full-body). Workflows with cadence ≥ once-per-hour AND no fast-exit short-circuit are BLOCKED. See guide for full COST FOOTPRINT comment template.

```yaml
# DO — cost-footer (e.g. cron: "*/30 * * * *" → 1,440 min/month worst case, fast-exit YES)
# DO NOT — uncosted "*/5 * * * *" silently consumes ~8,640 min/month at 1-min minimum
```

**BLOCKED rationalizations:** "Cron is cheap, the workflow exits in seconds" / "GitHub bills exact runtime, not minimum" (FALSE — billing is per-job, 1-min minimum) / "We can audit cost later when usage pattern stabilizes" / "The monitor is critical — frequency reflects priority" / "Higher cadence catches issues faster".

**Why:** GitHub Actions bills a 1-minute minimum per job invocation regardless of actual runtime. A workflow on `*/5 * * * *` consumes ~8,640 min/month — exceeds 2× the 3,000-min free tier alone. See guide for 2026-04-25 kailash-rs `ci-queue-monitor.yml` evidence.

### 8. Release PRs MUST Skip The PR-Gate Suite

Pull requests from a `release/v*` branch contain ONLY version anchors + CHANGELOG updates — zero code surface. Every PR-gate job in every workflow MUST gate its `if:` to also exclude `release/*` head refs.

```yaml
# DO — PR-gate jobs exclude release branches
jobs:
  fmt:
    if: github.event_name == 'pull_request' && !startsWith(github.head_ref, 'release/')

# DO NOT — PR-gate fires on release/v* PRs (re-runs whole suite against version-only diff)
jobs:
  fmt:
    if: github.event_name == 'pull_request'
```

**BLOCKED rationalizations:** "The version bump might have broken something; defense-in-depth" / "Running CI on release PRs is the standard release gate" / "We want to verify the lockfile regeneration didn't break compile" / "Admin-merge with bypass is safer than baking skip into the workflow" / "Next contributor might add real code changes to a release branch" / "release.yml's source-protection-audit is a different gate; we still need PR CI".

**Why:** Release PRs under `release/v*` are by contract metadata-only. Re-running the full suite against a pure-metadata diff adds no coverage and wastes ~45 min of runner wall-clock per release cycle. Cross-references `git.md` § "Release-Prep PRs MUST Use `release/v*` Branch Convention". See guide for the `/redteam` enforcement-grep snippet.

## MUST NOT Rules

### 1. Never Commit Registration Tokens

Runner registration tokens expire after 1 hour and become credentials once committed. MUST NOT commit hardcoded tokens to version control. Always use placeholder `RUNNER_TOKEN="REPLACE_WITH_FRESH_TOKEN"` in setup scripts.

**Why:** A committed token is harvested by token scanners within minutes and used to register unauthorized runners into the repository's job queue.

### 2. Every `upload-artifact` Step MUST Use `continue-on-error: true`

GitHub Actions artifact storage has a per-account quota that recalculates every 6-12 hours. When exhausted, `upload-artifact` returns `Failed to CreateArtifact: Artifact storage quota has been hit` and fails the job even though the underlying build succeeded.

```yaml
# DO
- uses: actions/upload-artifact@v7
  continue-on-error: true
  with: { name: wheel-${{ matrix.label }}, path: target/wheels/*.whl }
# DO NOT — without continue-on-error, build success masked by infrastructure billing problem
```

**BLOCKED rationalizations:** "The upload failure is a legitimate build failure" / "Adding continue-on-error hides real problems" / "We'll fix it when the quota resets" / "This only affects release.yml".

**Why:** The failure mode re-surfaces every ~12h on PR CI until someone re-discovers the fix. Codify once, apply everywhere.

Origin: kailash-rs CI cascade waves 6-18 (commits `ecc50c4e..5429928c`, 2026-04-16/17). See guide for full wave-by-wave evidence + recovery protocols at `skills/10-deployment-git/ci-runner-troubleshooting.md`.

<!-- /slot:neutral-body -->
