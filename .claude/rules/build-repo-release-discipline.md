---
priority: 10
scope: path-scoped
paths:
  - "pyproject.toml"
  - "packages/**/pyproject.toml"
  - "CHANGELOG.md"
  - "packages/**/CHANGELOG.md"
  - "packages/**/__init__.py"
  - "src/kailash/__init__.py"
  - ".github/workflows/publish-pypi.yml"
  - ".github/workflows/publish-*.yml"
  - ".github/workflows/release*.yml"
  - "deploy/deployment-config.md"
---

# BUILD Repo Release Discipline

<!-- slot:neutral-body -->

## Scope

ALL sessions in a BUILD repo (the SDK source repo this rule ships to) that merge code to main. Does NOT apply to downstream USE projects (template repos, application repos, external consumers) — those consume BUILD artifacts via PyPI / crates.io / gems and do not run `/release`.

## ABSOLUTE: "Done" Means Released, Not Merged

A session touching BUILD-repo source (new feature, bug fix, refactor, new test, new docs surface) MUST proceed through the full release cycle — admin-merge → `/release` → PyPI publication → installable verification — within the same session. Reporting "done" / "complete" / "shipped" at admin-merge is BLOCKED.

**Why:** Downstream consumers (USE templates, application repos, external packages like MLFP coursework, third-party integrations) consume BUILD repos only via PyPI. A PR merged to BUILD-main is invisible to everyone downstream until the release cut. Stopping at merge conflates BUILD-state with consumable-state and leaves every consumer blocked on the next scheduled release — which may be days or weeks away.

**Origin:** Session 2026-04-21 — 7 PRs of issue #567 (MLFP diagnostics upstream) merged over 3 sessions. PyPI versions held at `kailash 2.8.11` / `kailash-kaizen 2.7.5` / `kailash-ml 0.15.2` / `kailash-align 0.3.2` / `kailash-pact 0.8.2`. BUILD-main versions advanced to `2.8.25` / `2.9.0` / `0.17.0` / `0.4.0` / `0.9.0`. Downstream MLFP consumer observed "what happened??? we didn't do anything" because no PyPI release cut between the merge waves and the consumer's next template bump.

## MUST Rules

### 1. Every Merge Triggers A Release Cycle In The Same Session

When any PR merges to BUILD-main in the current session, the session MUST run `/release` for:

1. **The package directly modified** by the merged PR.
2. **Every sibling package whose main version is ahead of PyPI by ≥1 bump.** Rationale: if a prior session merged but did not release a sibling, the current session inherits the obligation — there is no external release cadence that will sweep it up.

```bash
# DO — enumerate packages whose main > pypi, include all in the release scope
for pkg in kailash kailash-dataflow kailash-nexus kailash-kaizen kailash-mcp \
           kailash-ml kailash-align kailash-pact; do
  main_version=$(grep '^version' packages/$pkg/pyproject.toml 2>/dev/null | head -1 | cut -d'"' -f2)
  [ -z "$main_version" ] && main_version=$(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)
  pypi_version=$(curl -s https://pypi.org/pypi/$pkg/json | python -c 'import sys, json; print(json.load(sys.stdin)["info"]["version"])')
  if [ "$main_version" != "$pypi_version" ]; then
    echo "RELEASE NEEDED: $pkg main=$main_version pypi=$pypi_version"
  fi
done

# DO NOT — only release the package you touched
/release kailash-kaizen  # but kailash-ml main 0.17.0 > pypi 0.15.2 is left stale
```

**Why:** Sibling packages drift over time — each session addresses its own PR's package and leaves siblings behind. The downstream consumer experiences a compounding gap. Closing siblings opportunistically (every session that releases anything sweeps every stale package) is the only way the gap converges to zero.

### 2. PyPI Installability Is The Done Gate, Not Merge

After `/release` publishes to PyPI, the session MUST verify the new version is installable AND the new surface importable:

```bash
# DO — verify from a clean venv, NOT from the build venv that has editable installs
# (pip --target is BLOCKED — it doesn't install console_scripts and confuses
#  namespace-package resolution for kailash-* sub-packages. macOS especially.)
uv venv /tmp/verify-kaizen --python 3.12
uv pip install --python /tmp/verify-kaizen/bin/python "kailash-kaizen==2.10.1"
/tmp/verify-kaizen/bin/python -c "
from kaizen.observability import AgentDiagnostics, TraceExporter
print(AgentDiagnostics, TraceExporter)
"
# Expect: class printout, no ImportError

# DO NOT — report done on merge alone
# "PR #587 merged, observability shipped" — but pip install still returns 2.7.5 (cached PyPI)

# DO NOT — `pip install --target` for verification
# (script entry points missing; namespace-package resolution wrong on macOS)
```

**PyPI cache lag**: `pypi.org/pypi/<pkg>/json` `info.version` field can show the OLD version for up to several minutes after a successful tag-push + publish-workflow-success. Retry the clean-venv install up to 3× with 60s between attempts before declaring release failure. The simple index (`pypi.org/simple/<pkg>/`) can be even slower to reflect the new wheel. If the workflow run shows success and the `.../2.10.1/json` endpoint returns metadata, the release DID happen — trust the verification retry loop.

**`uv` index-cache override**: when `pypi.org/pypi/<pkg>/<ver>/json` returns the new metadata BUT `uv pip install "<pkg>==<ver>"` reports `No solution found ... no version of <pkg>==<ver>`, the gap is `uv`'s local index cache, not PyPI. Pass `--refresh` to force a re-fetch: `uv pip install --refresh "<pkg>==<ver>"`. The pip-direct path (`/tmp/verify/bin/pip install ...`) does not need this flag because pip's index TTL is shorter, but the build-repo-release-discipline standard is `uv` per `python-environment.md` Rule 1, so `--refresh` is the documented unblocker for the install-verification step.

**Latent failures count**: When the clean-venv check fails, the broken pattern is the scope of the hotfix — NOT just the most-recent PR's diff. The same failure may have been latent in main for many sessions, hidden behind editable installs in every dev environment. "It's been working" / "this PR didn't introduce it" / "main was green" are BLOCKED rationalizations. Fix the entire broken pattern in the hotfix; file a follow-up issue ONLY if the fix exceeds one shard (per `autonomous-execution.md` Rule 1). See `dependencies.md` § "MUST: `__init__.py` Module-Scope Imports Honor The Manifest" for the structural defense that prevents the failure class.

**Why:** A release can succeed on PyPI metadata but fail on wheel upload, tag collision, or downstream dependency pinning — all of which surface only when a clean install runs the import. The installability check is the "smoke test" that proves the release reached consumers. Editable installs hide cross-package import dependency gaps; the clean-venv check is the only gate that catches them, and limiting hotfix scope to "what this PR changed" leaves the latent class of failure intact for the next release to re-discover.

### 3. Release Scope Enumerated Before First Merge Of The Session

At the start of a session that will merge code, the agent MUST enumerate every BUILD-repo package and cache (main_version, pypi_version) per package. The enumeration lives in the session's working memory for the rest of the session so release-scope decisions are not re-derived per-PR.

```markdown
# DO — enumerate once, reference throughout

Release scope for this session (at session start, before first merge):
| Package | main | PyPI | Release needed? |
|-----------------|-------|-------|-----------------|
| kailash | 2.8.25| 2.8.11| YES (14 patches)|
| kailash-dataflow| 2.0.12| 2.0.12| NO |
| kailash-kaizen | 2.9.0 | 2.7.5 | YES (minor) |
| kailash-ml | 0.17.0| 0.15.2| YES (2 minors) |
| kailash-align | 0.4.0 | 0.3.2 | YES (minor) |
| kailash-pact | 0.9.0 | 0.8.2 | YES (minor) |

Release cycle at end of session: kailash + kaizen + ml + align + pact.

# DO NOT — derive release scope only for the PR's package at merge time
```

**Why:** Without session-level scope enumeration, each merge independently asks "should I release this?" and the answer is always "only this one" — missing the sibling drift. Enumerating up-front locks in the "sweep all stale" obligation.

### 4. Release Authorization Is The Only Structural Gate

Per `rules/autonomous-execution.md` § "Structural vs Execution Gates", release authorization is a structural gate requiring human authority. The release-specialist prompts the human at `/release` time to approve PyPI publication. The human MAY authorize the entire enumerated scope or a subset; the session MUST NOT skip the prompt.

```
# DO — surface the full scope, let human approve
"I'm about to /release 5 packages: kailash 2.8.26, kailash-kaizen 2.10.1,
 kailash-ml 0.17.0, kailash-align 0.4.0, kailash-pact 0.9.0. Authorize all?"

# DO NOT — release without asking
"Running /release kailash-kaizen..." (no prompt)

# DO NOT — skip release because "human hasn't asked"
"Merged PR #587. User will release when they next cut a batch."
```

**Why:** The human owns release authorization (version increment + public-API commitment). But the agent owns scope enumeration. Splitting these correctly keeps the human's authority intact while closing the sibling-drift trap.

### 5. PR Review MUST Sweep Sub-Package Version Bumps Before Merge

Every PR-review gate (per `rules/agents.md` § Quality Gates row "Implementation done") MUST mechanically check: for each sub-package whose `packages/<pkg>/src/**/*.py` has changes in the diff, the SAME PR MUST also modify `packages/<pkg>/pyproject.toml::version` AND `packages/<pkg>/src/<pkg>/__init__.py::__version__`. A PR that ships sub-package src changes without a same-PR version bump is BLOCKED at PR-review time, NOT discovered later at `/release` time.

```bash
# DO — pre-merge mechanical sweep, run on every PR review
for pkg_dir in packages/*/; do
  pkg=$(basename "$pkg_dir")
  src_changed=$(git diff origin/main...HEAD -- "$pkg_dir/src/" --name-only | wc -l)
  ver_changed=$(git diff origin/main...HEAD -- "$pkg_dir/pyproject.toml" "$pkg_dir/src/*/__init__.py" \
    | grep -cE '^\+\s*(version|__version__)\s*=' )
  if [ "$src_changed" -gt 0 ] && [ "$ver_changed" -lt 2 ]; then
    echo "BLOCKED: $pkg src changed but version bump missing in same PR"
    exit 1
  fi
done

# DO NOT — defer the check to /release
# (Wave 4 PR #632 modified packages/kailash-mcp/src/.../auth/{providers,oauth}.py
#  but mcp pyproject stayed at 0.2.9. Caught only at /release-time enumeration,
#  required a separate fix-PR #634 to bump mcp 0.2.9 → 0.2.10. Net cost:
#  one extra PR, one extra CI cycle, one extra admin merge, ~15min of pacing.)
```

**BLOCKED rationalizations:**

- "The mcp changes fold into the next kailash release wave alongside #631"
- "The bump can be a follow-up PR"
- "PyPI consumers will get the fix in the dependency tree"
- "We'll catch it at /release time"
- "The PR title says 'security' so the version bump is implicit"

**Why:** Sub-package src ships as that sub-package's wheel — there is no transitive path that delivers a sub-package source change to consumers without a sub-package version bump and a new package publish. PR-review-time mechanical check converts an O(/release-time hotfix) cost into an O(grep) check; the alternative ("fold into next wave") is the exact rationalization that produces the silent sibling-drift this rule's § 1 was authored to prevent. The same atomicity applies to Cargo.toml + lib.rs version pairing in compiled-language SDKs.

Origin: 2026-04-26 — a sub-package security fix merged without bumping its version; caught at /release-time scope enumeration; required a separate fix-PR (extra CI + admin merge) to bump.

## MUST NOT

- Report "done" / "complete" / "shipped" at admin-merge for any PR that landed code

**Why:** Merged-not-released is the exact failure mode that produced the 2026-04-21 MLFP frustration. "Done" is a consumer-facing claim; consumers see PyPI, not main.

- Defer release to "next session" / "next batch" / "release-specialist follow-up"

**Why:** Every deferred release compounds the sibling-drift trap. The cheapest release is the one you run in the session that created the merge — context is warm, no re-enumeration cost.

- Release only the package modified by the PR, ignoring stale siblings

**Why:** The drift is multiplicative across sessions. Each session that releases only its own package leaves every sibling one bump further behind PyPI. Consumer experience degrades monotonically.

- Report done after `/release` returns success but before installability check

**Why:** PyPI publication can succeed on metadata and fail on wheel / tag / dependency — only a clean-venv install + import catches the full chain.

**BLOCKED rationalizations:**

- "PR merged, work complete"
- "Tests pass on main, user can install from source"
- "Release is a follow-up task, not part of implementation"
- "Waiting for user to batch releases for efficiency"
- "The consumer can add the BUILD repo as an editable dependency"
- "CI green on main means the feature is live"
- "release-specialist is a separate agent, not this session's concern"

## Relationship To Other Rules

- `rules/deployment.md` — `/release` mechanics, PyPI publishing, CI/CD. This rule mandates WHEN to invoke that machinery.
- `rules/autonomous-execution.md` § "Fix-Immediately When Review Surfaces A Same-Class Gap Within Shard Budget" — sibling rule. Both mandate closing loops within-session rather than deferring to next-session context reload.
- `rules/zero-tolerance.md` Rule 5 (Version Consistency on Release) — the atomicity requirement for pyproject.toml + **version**. This rule is the orchestration layer that ensures the consistency-checked bump reaches PyPI.
- `rules/artifact-flow.md` — separate artifact lifecycle (proposals → loom → templates). Code releases follow this rule; COC artifact proposals follow artifact-flow.

<!-- /slot:neutral-body -->
