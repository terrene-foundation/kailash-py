<!-- slot:neutral-body -->

Self-hosted CI runner hygiene for kailash-py (macOS + Linux self-hosted runners, `terrene-foundation/kailash-py` repo). Language-agnostic MUSTs apply to every project using GitHub Actions self-hosted runners; §6 and §7 below capture kailash-py-specific dispatcher-state remediation with concrete runner hostnames and `launchctl` / `systemctl` invocations.

For recovery protocols, service-management commands, and step-by-step troubleshooting, see `skills/10-deployment-git/ci-runner-troubleshooting.md`.

## MUST Rules

### 1. Every Toolchain-Consuming Job Includes A Toolchain Setup Step

Every job that invokes a language toolchain (`python`, `pip`, `poetry`, `uv`, `pytest`, `maturin`, `npm`, `pnpm`, `bundle`, etc.) MUST include a dedicated toolchain setup step (e.g. `actions/setup-python`, `astral-sh/setup-uv`, `actions/setup-node`) as one of its earliest steps — even if a previous job in the same workflow already installed the toolchain.

```yaml
# DO — every job re-establishes its own toolchain
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.12"
  - name: Install deps
    run: pip install -e .[dev]

# DO NOT — relying on a sibling job's toolchain install
steps:
  - uses: actions/checkout@v4
  - name: Install deps
    run: pip install -e .[dev]   # fails if PATH was re-written by an earlier job
```

**Why:** Self-hosted runners do not reset `PATH` between jobs cleanly. A sibling job that reinstalled `pyenv` or ran `uv venv` leaves the runner in a state where the proxy binary (`~/.pyenv/shims/python`, `~/.local/bin/uv`) may be missing or points to the wrong version. Each job re-establishing its own toolchain is the only structural defense.

### 2. Restart The Runner After Changing Its Environment File

After editing the runner's `.env` file (e.g. `~/actions-runner-*/.env`), the runner MUST be restarted via `launchctl unload && launchctl load` (macOS) or `systemctl restart` (Linux). Running jobs MUST be allowed to complete under the old environment before the restart.

```bash
# DO — explicit unload, wait for in-flight jobs, reload
launchctl unload ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist
# wait for any in-flight job to drain
launchctl load ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist

# DO NOT — edit .env and expect new jobs to pick up changes
vim ~/actions-runner-<name>/.env  # save
# next queued job still reads the old env because the runner process cached it at startup
```

**Why:** The runner daemon reads its `.env` once at process startup. Silent drift between "what operators edited" and "what jobs actually ran with" is invisible until a job fails with a missing variable that the operator can see in the file.

### 3. Post-lint Cascade Discovery Protocol

When `Lint` / `Format` / `ruff` (or any early short-circuiting gate) transitions from red to green for the first time in a long while, the session MUST expect multiple subsequent failures and budget for multi-wave triage. A red lint gate short-circuits the pipeline — mypy, pytest, integration tests, coverage, and build are SKIPPED, not failed. Pre-existing failures in those gates accumulate invisibly and surface one-wave-at-a-time once lint is green.

```yaml
# DO — tight triage loop until all gates green
# push → inspect failing gate → fix root cause → push → repeat
# accept that wave N+1 may reveal a failure wave N masked

# DO NOT — declare victory after lint goes green
# gh pr checks <N>  # lint: pass, 6 others: skipped (NOT green)
# git push origin feat/cleanup  # "CI is fixed" — it isn't
```

**BLOCKED rationalizations:**

- "Lint is green, CI is fixed"
- "The other gates were skipped, so they're passing"
- "We can triage the rest in parallel branches"
- "These failures are pre-existing, not our problem"

**Why:** Short-circuit semantics hide months of accumulated failures behind a single red lint. Declaring "fixed" after lint green leaves the downstream backlog to surface on the next unrelated PR, where the failures look like new regressions. Parallel triage branches also break because each wave's fix depends on the previous wave's state.

### 4. Runner Auto-Update Disconnect Recovery

If `gh api repos/terrene-foundation/kailash-py/actions/runners` returns 0 runners while the runner's stdout log tails show `Connected to GitHub` and `Listening for Jobs`, the runner auto-updated mid-session and its in-flight job is orphaned — the old worker process holds the job in GitHub's state machine but cannot report completion. The session MUST restart the runner service AND trigger a fresh run via an empty commit.

```bash
# DO — re-register the runner and trigger a fresh run
launchctl unload ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist
launchctl load ~/Library/LaunchAgents/com.github.actions.runner.<name>.plist
git commit --allow-empty -m "chore(ci): trigger fresh run post-runner-update"
git push

# DO NOT — rerun the orphaned run; the dead worker still owns the job
gh run rerun <run-id> --failed  # the new worker can't claim the old worker's jobs
```

**BLOCKED rationalizations:**

- "The runner log says Connected, it must be fine"
- "Wait for the hung job to time out on its own"
- "Re-run the failed job, it'll get picked up"

**Why:** The GitHub Actions runner auto-update path renames and replaces the worker binary. Jobs assigned to the dead worker cannot be claimed by the new worker; GitHub's dispatcher needs a new trigger to assign the job. Without the service restart, the "Connected" log is from a fresh worker that never knew about the orphaned job, and the hung run blocks the PR for hours.

### 5. Package-CI Paths Filter Matches The Workspace Pattern

Every package-channel CI workflow (`kailash-dataflow.yml`, `kailash-nexus.yml`, `kailash-kaizen.yml`, `kailash-ml.yml`, etc.) MUST have a `paths:` filter that covers the transitive dependency graph of the core package, not just the package directory. Narrow enumerations of specific modules or sub-packages silently stop matching whenever a new transitive dependency is added.

```yaml
# DO — broad filter matches the core-package CI's pattern
on:
  pull_request:
    paths:
      - "packages/kailash-dataflow/**"
      - "src/kailash/**"
      - "pyproject.toml"
      - "uv.lock"
      - ".github/workflows/kailash-dataflow.yml"

# DO NOT — enumerate specific sub-packages
on:
  pull_request:
    paths:
      - "packages/kailash-dataflow/**"
      - "src/kailash/nodes/data/**"
      - "src/kailash/nodes/transform/**"  # misses kailash.runtime, kailash.workflow, etc.
```

**BLOCKED rationalizations:**

- "The package only depends on these modules today"
- "Broad filter triggers too many unnecessary builds"
- "We'll update the filter when we add new deps"

**Why:** Sub-packages transitively import most of the core workspace. A narrow filter means a fix to a shared module triggers the core CI but skips the sub-package CI, letting the sub-package ship broken into the next release. When a shared module change lands and the sub-package CI reports "no changes", that is the exact failure mode this rule prevents.

### 6. Zombie-Job Cancellation Protocol

When a job on a self-hosted runner (e.g. `jacks-mac-studio`, `esperies-mini`, `esperie-linux-arm`) remains `in_progress` for >2× its normal completion time, it is a zombie — the runner process is stuck (network drop, hung test, pip/poetry lock) or the worker crashed without reporting to the dispatcher. From the dispatcher's perspective the runner slot stays `busy: true`, blocking every subsequent job queued for that runner's label.

```bash
# DO — diagnose then cancel, kickstart if the worker itself is wedged
# Step 1: enumerate runner state to identify the zombie
gh api orgs/terrene-foundation/actions/runners \
  --jq '.runners[] | {name, busy, status}'

# Step 2: cross-reference with the stuck run's jobs
gh api repos/terrene-foundation/kailash-py/actions/runs/<run-id>/jobs \
  --jq '.jobs[] | {name, status, started_at, runner_name}'

# Step 3: cancel the stuck run to free the runner slot
gh run cancel <run-id>

# Step 4: if cancel is not acknowledged within 2 minutes, the runner
# process itself is deadlocked — kickstart the service agent:
# macOS:
launchctl kickstart -k "gui/$UID/actions.runner.terrene-foundation-kailash-py.<runner-name>"
# Linux (systemd):
sudo systemctl restart actions.runner.terrene-foundation-kailash-py.<runner-name>.service

# DO NOT — wait for the zombie to time out on its own
# The default job timeout is 6 hours; the queue stays blocked the entire time.
```

**BLOCKED rationalizations:**

- "The job might still be running, let me wait another 30 minutes"
- "Cancelling will lose the partial results"
- "The runner will self-recover when it notices the disconnect"
- "Restarting the service mid-session risks the other runners"
- "I'll just push a new commit to trigger a fresh run"

**Why:** A zombie job holds the runner's dispatcher-side `busy` flag indefinitely. Every queued job assigned to that runner's label waits behind the zombie until either the 6-hour timeout fires or the job is explicitly cancelled. `gh run cancel` frees the slot immediately; if the runner worker is also deadlocked at the OS level (hung test, lock contention, pip install lock), `launchctl kickstart -k` / `systemctl restart` respawns the agent. Pushing a new commit does NOT help — the new run queues behind the zombie in the same runner's job list.

### 7. Idle-But-Not-Accepting Runner Protocol — De-Register, Don't Restart

When a self-hosted runner reports `busy: false` + `status: online` yet refuses to accept queued jobs (queue depth > 0 for > 5 minutes while the runner sits idle with matching labels), the agent is NOT restartable from outside the host. MUST de-register the runner via `gh api -X DELETE` so the dispatcher redistributes pending jobs to the remaining healthy runners.

This is DISTINCT from §6 (zombie-job): a zombie has `busy: true` + a specific `in_progress` run stuck for hours. An idle-not-accepting runner has `busy: false` and NO assigned job, but the dispatcher has decided it's "reserved" for queued work that never dispatches. Both block the queue; the remediations differ.

```bash
# DO — de-register the idle-not-accepting runner
# Step 1: confirm the diagnosis — idle + online + queue depth > 0
gh api orgs/terrene-foundation/actions/runners \
  --jq '.runners[] | {name, busy, status, labels: [.labels[].name]}'
# If exactly one runner shows busy=false + status=online AND a PR has
# jobs QUEUED for minutes, you have an idle-not-accepting runner.

# Step 2: confirm queue depth on the affected PR
gh pr view <PR-NUM> --json statusCheckRollup \
  --jq '[.statusCheckRollup[] | select(.conclusion == null or .conclusion == "")] | length'

# Step 3: de-register the idle runner — ID is from step 1's response
RUNNER_ID=$(gh api orgs/terrene-foundation/actions/runners \
  --jq '.runners[] | select(.name == "<runner-name>") | .id')
gh api -X DELETE orgs/terrene-foundation/actions/runners/$RUNNER_ID

# Step 4: verify — queued jobs should start dispatching to the remaining
# runners within 30-60 seconds
gh pr view <PR-NUM> --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select(.status == "IN_PROGRESS") | .name'

# DO NOT — wait for the runner to self-recover
# A runner in this state is deadlocked at the job-pickup poll; it will
# continue heartbeating "online" indefinitely without accepting work.
```

**BLOCKED rationalizations:**

- "Let me restart the runner agent — that always works"
- "I'll wait another 10 minutes, maybe it'll pick up the next poll cycle"
- "De-registration loses capacity permanently"
- "The runner is online, the dispatcher must be about to dispatch"
- "This is a dispatcher-side bug, not mine to fix"
- "Restarting risks interfering with runs on the other runners"

**Why:** A runner in the idle-not-accepting state has a registered listener process that passes the heartbeat (hence `online`) but whose job-acceptance loop is wedged (hence `busy: false` while queued work exists). Restart requires physical/SSH access to the host, which may be unavailable mid-incident. `gh api -X DELETE` works entirely from the orchestrator side, removes the runner from the dispatcher's label-match pool immediately, and queued jobs re-dispatch to the remaining runners within the next poll cycle (usually <60 seconds). The runner can be re-registered later once the host is reachable; the capacity loss is temporary and recovered without a live-incident SSH session.

**Relationship to §6:** §6 is "job stuck, runner held busy"; §7 is "runner stuck idle, queue held waiting". Together they cover both failure modes of self-hosted dispatcher state. If you can't tell which state you're in, check `busy:` — `true` → §6, `false` with queue depth → §7.

### 8. Tag-Gated Release Jobs Require A Non-Tag `workflow_dispatch` Dry-Run Proxy

Every job inside `release.yml` (or any workflow) whose trigger is `on: push: tags:` MUST have a sibling `workflow_dispatch:` input path that exercises the same build + upload steps on a non-tag ref. Relying on release tags as the first integration test is BLOCKED — tag-time is too late for the error to be cheap to fix.

```yaml
# DO — workflow_dispatch dry-run proxy exercises the same steps
on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Build + upload but skip twine/pypi publish"
        type: boolean
        default: true
      target:
        description: "publish-sdist | publish-wheels | publish-testpypi"
        type: choice
        options:
          - publish-sdist
          - publish-wheels
          - publish-testpypi

permissions:
  contents: write        # needed for gh release upload (§5)

jobs:
  publish-wheels:
    if: |
      startsWith(github.ref, 'refs/tags/v') ||
      (github.event_name == 'workflow_dispatch' &&
       github.event.inputs.target == 'publish-wheels')
    runs-on: esperie-linux-arm
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install build deps (runner base image is minimal)
        run: pip install build twine
      - name: Install gh CLI (runner base image is minimal)
        run: ...
      - name: Build wheels
        run: python -m build --wheel
      - name: Upload to release
        if: startsWith(github.ref, 'refs/tags/v')
        run: gh release upload "${{ github.ref_name }}" dist/*.whl
      - name: Dry-run verify (no upload)
        if: github.event.inputs.dry_run == 'true'
        run: ls -la dist/*.whl && echo "Build OK; skipping publish"

# DO NOT — tag-only trigger with no dispatch proxy
on:
  push:
    tags: ["v*"]
jobs:
  publish-wheels:
    runs-on: esperie-linux-arm
    steps:
      - uses: actions/checkout@v4
      - run: python -m build --wheel
      - run: twine upload dist/*.whl
# First integration test of the runner + Python + twine install sequence
# happens at tag time, blocking the release on whatever was missing.
```

**BLOCKED rationalizations:**

- "Release.yml is only exercised at release, that's the point"
- "A dispatch input duplicates the tag trigger"
- "We'll fire a manual dry-run when we think something changed"
- "CI already builds on every PR, that's the dry-run"
- "The rescue-workflow pattern covers this"

**Why:** Tag-gated jobs on a self-hosted or GitHub-hosted-larger runner interact with the runner's image, PATH, installed Python state, `gh` CLI availability, `twine` availability, and `contents: write` permission. None of these are exercised on PR CI (which runs on different workflows, different runners, different permissions). Each tag-time bug (missing build deps, missing gh CLI, missing `contents: write`) only surfaces when the `release.yml` tag-push path is first exercised. A `workflow_dispatch` dry-run path that builds + conditionally uploads to a release on a non-tag ref turns tag-time into a re-run of a known-green dispatch run. The dispatch proxy IS the Layer 2 prevention plan; the rescue-workflow pattern is Layer 3 recovery, not Layer 2 prevention.

**Enforcement grep:** For every workflow with a `tags:` trigger, assert a `workflow_dispatch:` trigger is declared in the same `on:` block, AND every job gated by `startsWith(github.ref, 'refs/tags/v')` has a sibling `github.event_name == 'workflow_dispatch'` branch that exercises the build steps. Mechanical — the rule is grep-auditable per release-cycle codify pass.

Origin: Mirrored from `variants/rs/rules/ci-runners.md` § Rule 8 (kailash-rs 2026-04-22 — three tag-time bugs in three consecutive releases v3.20.3 / v3.20.4 / v3.20.5). Cross-SDK principle — applies to every language's release pipeline; the failure mode is runner-state drift between PR CI and release CI, not language-specific. Pre-authored at loom for kailash-py BEFORE the equivalent codify pass surfaces it organically, per same-bug-class prevention discipline.

## MUST NOT Rules

### 1. Never Commit Registration Tokens

Runner registration tokens expire after 1 hour and become credentials once committed. MUST NOT commit hardcoded tokens to version control. Always use placeholder `RUNNER_TOKEN="REPLACE_WITH_FRESH_TOKEN"` in setup scripts.

**Why:** A token committed to a public branch is harvested by token scanners within minutes and used to register unauthorized runners into the repository's job queue.

### 2. Every `upload-artifact` Step MUST Use `continue-on-error: true`

GitHub Actions artifact storage has a per-account quota that recalculates every 6-12 hours. When exhausted, `upload-artifact` returns `Failed to CreateArtifact: Artifact storage quota has been hit` and fails the job even though the underlying build succeeded. This masks real build success with an infrastructure billing problem.

Every `actions/upload-artifact@v*` step across ALL workflows MUST include `continue-on-error: true`:

```yaml
# DO
- uses: actions/upload-artifact@v7
  continue-on-error: true
  with:
    name: wheel-${{ matrix.python-version.label }}
    path: dist/*.whl

# DO NOT
- uses: actions/upload-artifact@v7
  with:
    name: wheel-${{ matrix.python-version.label }}
    path: dist/*.whl
```

**BLOCKED rationalizations:**

- "The upload failure is a legitimate build failure"
- "Adding continue-on-error hides real problems"
- "We'll fix it when the quota resets"
- "This only affects release.yml"

**Why:** The failure mode re-surfaces every ~12h on PR CI until someone re-discovers the fix. Codify once, apply everywhere.

Origin: Mirrored from rs variant — cross-language failure mode. Recovery protocols live in `skills/10-deployment-git/ci-runner-troubleshooting.md`.

<!-- /slot:neutral-body -->
