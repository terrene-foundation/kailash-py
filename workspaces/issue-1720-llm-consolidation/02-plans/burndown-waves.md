# Burn-down wave plan — maximum velocity via file-disjoint parallel lanes

Authored 2026-08-10. Basis: the `/sweep` PCF triage in `.session-notes` (14 BUG, 3 INVEST-NOW,
6 deferred-quality).

**Velocity claim: ~4–5 autonomous cycles parallel, against 12–15 serial.** The constraint is not
agent count — it is _file disjointness_. Two lanes touching one file serialize whatever the plan
says, so lanes below are partitioned by the files each issue actually modifies.

## Gate 0 — CLEARED (2026-08-10)

**PR #2028 merged as `a101c81f9`**; #1995 closed with the SHA; 1,819 files changed.

- The `Test DataFlow Infra Regression (Postgres/Redis)` blocker **cleared on its own** on the
  final run — a flake, not a regression. The local pass was right.
- **CodeQL's "377 new alerts including 6 high severity" was an ARTIFACT**, disproved rather than
  waived. CodeQL keys its new-vs-existing diff on alert LOCATION; the reorder shifted nearly
  every line. Diffing the full alert sets on the location-INDEPENDENT key
  `(rule, severity, path)` — line granularity could not discriminate, since line is exactly what
  the reorder perturbs — gave `comm -23 pr main` EMPTY (PR ⊆ main) and `comm -13` = 26
  `unused-import` alerts the PR REMOVES. Totals reconcile: 2345 − 2319 = 26.

### ⚠ Consequence for every lane: all pre-merge line numbers are STALE

Every `file.py:NNN` in this plan and in the bodies of #1997–#2030 predates the merge and has
shifted. Drift is **per-file, not uniform** (`gateway/security.py` `:205 → :211`; `sso.py`
`:924 → :926`; `base_agent.py` `:743` unshifted), so no global offset applies. Anchor on
grep-stable symbols and re-derive.

## Verified corrections (measured on `a101c81f9` before the lanes launched)

- **#2013 — CONFIRMED REAL.** `def set_auth_manager` has **ZERO definitions repo-wide**; the only
  mentions are the guard and call at `nexus/plugins.py:103-104`. So `hasattr(gateway,
"set_auth_manager")` is permanently False and `enable_auth=True` installs nothing. The
  identical dead-`hasattr` shape for `enable_monitoring` is at `nexus/core.py:4828` (**not**
  4826 — drifted). Both in one PR.
- **#2015 — CONFIRMED at 24** `detail=str(e)` sites. Separately there are **43** `detail=f"`
  sites; those are NOT all leaks and MUST be triaged for which interpolate an exception. The
  issue's grep finds only the first spelling.
- **#2000 (lane 3D) — THE PLAN'S FIX SHAPE IS WRONG.** The correct file is
  `src/kailash/security.py` (not `nodes/api/security.py`), and its `torch` (`:536`) and `sklearn`
  (`:595`) imports are **already function-local and cached**, so "lazy-import them out" is a
  no-op. Root cause: `sanitize_input()` → `_get_cached_allowed_types()` builds a **type
  allowlist** out of the real `torch.Tensor` / `BaseEstimator` class objects, which forces the
  import on first call and costs the 9–11s. Correct fix is to stop needing the import at all —
  match on `type(value).__module__` / qualname rather than on imported class identity. Lane 3D
  must re-derive this itself and not adopt the original prescription.

## Standing rules for every lane

1. **Apply `specification-verification.md` FIRST.** Every issue below has been re-measured once by
   this session, but the lane MUST re-derive the load-bearing claims itself and test any prescribed
   remedy against the named threat before adopting it. Five of these issues had wrong specs.
2. **Worktree-isolated per lane** (`worktree-isolation.md`); one branch, one PR each.
3. **Security lanes need BOTH reviewers** — correctness AND an adversarial security-reviewer
   prompted to refute, each with a genuine ran-signal (`agents.md` § Correctness-Review-Clean Is
   Not Security-Clean).
4. Regression test per fix, fail-first verified.

## Wave 1 — security (5 parallel lanes)

| Lane   | Issue          | Primary files                                                                                                                                         | Notes                                                                                           |
| ------ | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **1A** | #2025 CRITICAL | `src/kailash/servers/workflow_server.py`                                                                                                              | Auth dependency + path allowlist + method allowlist. NOT an SSRF fix — see the issue.           |
| **1B** | #2024 CRITICAL | `src/kailash/gateway/security.py`                                                                                                                     | Encrypt-at-rest vs delete-the-class is a **user decision**; surface it, don't self-decide.      |
| **1C** | #2026 HIGH     | `src/kailash/nodes/auth/sso.py`, `mfa.py`                                                                                                             | Delete the `oauth.example.com` branch; stop logging the OTP body.                               |
| **1D** | #2030 + #2022  | `packages/kailash-kaizen/src/kaizen/core/base_agent.py`                                                                                               | **Same file — must be one lane.** #2030 is lines 727/735 (I/O at INFO); #2022's swallow is 743. |
| **1E** | #2027 HIGH/MED | `resource_resolver.py`, `parameter_injector.py`, `dataflow/core/nodes.py`, nexus `rate_limit/middleware.py`, `trust/plane/integration/cursor/hook.py` | Touches `dataflow/core/nodes.py` → **blocks #2006 until merged.**                               |

## Wave 2 — remaining BUG (5 parallel lanes)

| Lane   | Issue | Primary files                                                      | Notes                                                                                                                             |
| ------ | ----- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| **2A** | #2013 | `packages/kailash-nexus/src/nexus/core.py`, `plugins.py`           | Fix `enable_monitoring`'s identical dead branch (`core.py:4826`) in the same PR. Security-adjacent.                               |
| **2B** | #2015 | new `src/kailash/utils/http_errors.py` + 25 sites                  | Includes the 4 dataflow template sites (they propagate into user apps) and the f-string site at `durable_workflow_server.py:480`. |
| **2C** | #1997 | `packages/kailash-kaizen/src/kaizen/utils/credential_scrub.py`     | Drop xAI from scope. Pin the **conservative preset** — that's where all four leak. Remove the xfail-strict marker.                |
| **2D** | #2014 | `.../kaizen/core/autonomy/hooks/security/isolation.py`             | Module-scope worker + explicit `get_context("spawn")` + delete the silent fallback.                                               |
| **2E** | #2004 | `packages/kailash-mcp/src/kailash_mcp/security.py`, `discovery.py` | Fix at the **raise site**, not the three call sites. The issue's own AC does not work.                                            |

## Wave 3 — INVEST-NOW + trivia (4 parallel lanes)

| Lane   | Issue                 | Notes                                                                          |
| ------ | --------------------- | ------------------------------------------------------------------------------ |
| **3A** | #2006                 | **Sequenced after 1E** (shared `dataflow/core/nodes.py`).                      |
| **3B** | #2002 + #2023         | Both `.github/workflows/**`. 3-PR sequence for #2002; #2023 is 8 steps, not 5. |
| **3C** | #2011 + #2010 + #2029 | Trivia batch: a `git mv`, a 3-line deletion, a flaky-test rewrite.             |
| **3D** | #2000                 | Lazy-import `torch`/`sklearn` out of `security.py`.                            |

## Wave 4 — convergence

1. **Holistic post-multi-wave redteam** across ALL merged shards on main
   (`agents.md` § Holistic Post-Multi-Wave Redteam) — per-shard reviews cannot see cross-shard
   invariant breaks. ≥3 parallel reviewers scoped to the union of merged PRs.
2. **CodeQL**: verify the remaining 23 dismissals individually, then dismiss with per-alert
   evidence. Sample hit rate for "scanner flagged the wrong line" was 1-in-2.
3. **Sweep-N** on the deferred-quality backlog (#2017–#2021 at 2nd cycle → "still wanted?" gate).
4. `/release` — BUILD-repo discipline: merged ≠ released.

## Deliberate sequencing constraints

- 1E → 3A (`dataflow/core/nodes.py`)
- #2030 and #2022 share `base_agent.py` → one lane (1D)
- #2013 is security-adjacent but touches nexus only → safe to parallelize with Wave 1 if capacity
  allows; placed in Wave 2 to keep the security review pool focused.
