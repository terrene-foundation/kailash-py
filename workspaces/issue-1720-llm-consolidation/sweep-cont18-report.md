# /sweep — Management Decision Report (cont-18)

main `454f27acc` · **7 PRs merged this session** · **10 issues closed** · 45 open · 7 of our PRs open

Every "complete" claim cites a durable receipt (merge SHA / verified file state), per
`verify-resource-existence.md` MUST-4. No self-attested completion.

---

## 1. Completion status

### The headline: the CI verification chain is closed, and the root cause under it is fixed

Four **independent** never-ran mechanisms were found and closed in one chain. Each hid the
next, so none was visible until the one above it was removed:

| #   | Mechanism                                                                         | Receipt               |
| --- | --------------------------------------------------------------------------------- | --------------------- |
| 1   | Tier 2 masked by `continue-on-error`                                              | #2038 (prior session) |
| 2   | `packages/kailash-kaizen/tests/regression/` in no pytest invocation — 855 tests   | #2144 `8a4dca737`     |
| 3   | Infra markers keyed on an **ASLR memory address**, then on **English substrings** | #2159 `454f27acc`     |
| 4   | `packages/kaizen-agents/tests/` in no pytest invocation — **812 tests**           | #2160 `995d72bc4`     |

**The root cause under #3 is fixed, not patched a third time.** Infrastructure need is now
derived from the **resolved fixture graph** (`item.fixturenames`, transitive), never the test's
name. Measured over 14,773 items, name-matching agreed with the dependency graph only **84.9%**
of the time — 2,246 false positives AND 2 false negatives. The false negatives are the half no
word-list edit could reach: two tests genuinely requested infra fixtures, went unmarked, and
**ran in infra-free CI where they could only fail or flake**.

Three guards (`tests/unit/test_infra_marker_mapping.py`) cover the three decay paths, **each
mutation-verified to RED** with the mutation confirmed present in the file first.

### The suite CI actually runs

`tests/regression/`, full infra-free filter, verified on merged main:

```
before    : 1288 passed, 342 deselected   <- 342 was a random variable, not a number
keyword   : 1494 passed, 145 deselected, 3 failed
ROOT FIX  : 1623 passed,   5 deselected, 0 failed, 0 errors
```

Plus **812 kaizen-agents tests** now running that never had (baseline established BEFORE wiring:
`812 passed, 2 deselected, 0 failed`).

### Landed this session (receipts = merge SHAs)

| PR                | Closes              | What it bought                                                                                |
| ----------------- | ------------------- | --------------------------------------------------------------------------------------------- |
| #2143 `e228c5514` | #2119, #2067        | `base_agent.py` 1068→920 by extraction; the two LOC guards can no longer diverge              |
| #2144 `8a4dca737` | #2074, #2076, #2133 | 855 green-by-absence tests wired in; 5 zero-matching gates fixed/deleted; nightly main run    |
| #2147 `decd9eb8e` | #2081, #2079        | Root regression suite completes on the runner (2403 passed / 277s) — it never finished before |
| #2137 `2e3ddd9e7` | #2112               | Two un-gated HTTP servers closed, incl. one accepting anonymous control-plane **writes**      |
| #2148 `a94aad89a` | —                   | E721 fixes with a discrimination control proving validation still fires                       |
| #2160 `995d72bc4` | —                   | Live MCP product bug; fixture shadowing; **812-test suite wired into CI**                     |
| #2159 `454f27acc` | #2152               | **Root cause**: fixture-graph markers replace name inference                                  |

### Is the product complete and visible?

**The verification substrate is now trustworthy; the auth surface is not yet closed.** Before
this session a green CI run carried almost no information about the integration suite, the
kaizen suite, or the root regression suite. It now does. That is the precondition for every
other claim — but the auth-surface work is staged in PRs, not merged.

---

## 2. ETA to completion — in autonomous cycles

**To a complete + visible product: ~4–6 cycles** for the BUG + INVEST-NOW set. Down from
7–9 at cont-17: the CI chain is closed and the auth work is built-and-reviewed, awaiting merge.

| Bucket                                                            | Items | Est. cycles           |
| ----------------------------------------------------------------- | ----- | --------------------- |
| Merge the staged auth + proxy set (#2139/#2156/#2136/#2150/#2154) | 5 PRs | 0.5                   |
| #2140 API-key auth — blocked on a co-owner CodeQL call            | 1     | 0.25 (after decision) |
| Sub-package auth surfaces (#2141, #2142)                          | 2     | 1                     |
| Session IDOR follow-through + webhook SSRF/HMAC (#2145 residue)   | —     | 0.5–1                 |
| Correctness set (#2107, #2109, #2110, #2113, #2138, #2162, #2163) | 7     | 1.5                   |
| Gemini 3.x tool loops (#2120, #2121)                              | 2     | 0.5–1                 |
| Remainder (~15 items)                                             | 15    | 1–1.5                 |

Basis: single-shard items at ~0.25 cycle; the staged PRs are already built and reviewed.

---

## 3. Prioritized immediate queue (BUG + INVEST-NOW, value-ranked)

Value-anchor: the co-owner's directives **this session** — _"continue from last session,
/autonomize in parallelized waves"_ and _"approved, root cause long term fix please"_.

1. **Merge the staged, verified set — #2139, #2136, #2154, #2161.** All green, all
   adversarially reviewed, all with HIGH findings fixed and re-verified by me:
   - #2139: refresh-token refusal present; the direct path now matches the gate's semantics.
   - #2136: IMDS bypass **closed on the default posture** — I reproduced all four wrapper forms
     refused (`metadata_service`/`link_local`) with `10.1.2.3` still ACCEPTED.
     _Implication:_ these carry the session's security fixes; leaving them staged is the only
     thing between the work and the users.
2. **#2145 — authenticated arbitrary code execution in another user's session.** Highest
   open severity. #2156 fixes it (13/13 routes guarded, 0 gaps) and is stacked on #2139.
   _Implication:_ an authenticated caller can inject and execute a workflow in another user's
   session; `GET /api/sessions` supplies the target list.
3. **#2141 / #2142 — un-gated HTTP surfaces in kailash-ml and kaizen.** #2141 is the sharper:
   an unauthenticated `DELETE /api/runs/{id}`, and `--auth` unlocks a `0.0.0.0` bind while
   installing nothing. _Implication:_ the flag that advertises security widens exposure.
4. **#2140 — API-key auth that cannot authenticate anyone.** Blocked on a co-owner decision
   (D1 below), not on engineering.
5. **#2162 — two conformance MUST checks cannot return False.** Same class as everything above:
   a check that always passes. One is a MUST at CONFORMANT level and passes a project with
   `chain_valid=False`.
6. **#2107** ten `__del__` finalizers in the documented logging-lock deadlock class ·
   **#2153** kaizen SSRF permits CGNAT while nexus blocks it · **#2138** rotation that never
   fires · **#2163** anchor tip from a capped listing.

---

## 4. Deferred-quality backlog

**Empty — `gh issue list --label deferred-quality` returns nothing.**

Sweep-N has nothing to fire on. Note this is the _label_ being unused, not an absence of
deferred work: several items below are deferred by judgment (#2044, #2106, #2127, #2146 are
CodeQL deferrals carrying runtime-safety proofs; #2118 is a documentation defer). Those follow
`zero-tolerance.md` Rule 1b's four conditions rather than the `deferred-quality` template.
**Recommendation:** leave as-is — relabelling them would be bookkeeping, not value.

---

## 5. Decision points for the co-owner

**D1 — #2140's CodeQL alert cannot be cleared from inside the repo.**
`py/weak-sensitive-data-hashing` on `hash_api_key`. Three approaches tried, two measured
non-working: the sanitizer-model path is refuted by the repo's own `sanitizers.model.yml`
(both model forms measured ineffective for in-source functions), and an inline suppression was
tried and removed. The code is now a salted `hmac.new(salt, secret, sha256)` with a per-record
CSPRNG salt.

- _Option 1 — dismiss the alert in the code-scanning UI_ with #2146's proof attached.
  **Pro:** unblocks a real security fix (an auth path that currently cannot authenticate anyone);
  the proof is sound — the input is a 256-bit CSPRNG token, and a slow KDF here would be a DoS
  amplifier since `verify_api_key` hashes every unauthenticated request.
  **Con:** a dismissed alert is invisible to future scans of that line; if the input class ever
  changes to a user-chosen secret, nothing re-flags it.
- _Option 2 — leave #2140 red._ **Pro:** no suppression on the record. **Con:** #2108/#2114 stay
  unfixed indefinitely — an API-key path that cannot authenticate anyone, and a non-ASCII key
  that produces an unauthenticated traceback per request.

**Recommendation: Option 1.** The proof is specific to the input class and would apply
identically had the alert first appeared on main. Requires your action — it is a repo-settings
mutation I will not take on your behalf.

**D2 — GPU CI (#2155): provision or retire?**
Measured: **no self-hosted runner at repo OR org level** (`total_count: 0` both), and
`gpu-smoke.yml` has never completed successfully since at least 2026-06-07 (5× cancelled).
`test-cuda`/`test-cuda-dl` are wrapped in `continue-on-error` and cannot execute.

- _Provision a runner._ **Pro:** the CUDA selector fixes become live. **Con:** recurring cost;
  no evidence anyone is waiting on GPU coverage.
- _Retire the jobs_ (as `test-gpu` already was, #2135). **Pro:** removes three permanently-masked
  jobs — the #2038 class. **Con:** forecloses GPU coverage until someone re-adds it.

**Recommendation: retire**, unless GPU coverage is on your roadmap. Masked jobs that can never
run are exactly what this session spent its length removing.

**D3 — isort is misconfigured; the fix is repo-wide.**
The repo's own hook contradicts itself (`--all-files` removes a blank line, `--from-ref` restores
it). Probable one-line cause: `kailash_mcp` missing from `known_first_party`. **Con:** fixing it
rewrites every file importing `kailash_mcp`, and this repo already sat at ~2,000
permanently-modified files for four cycles from exactly this failure (#1995).
**Recommendation: fix it in a dedicated PR with no other content**, so the diff is reviewable as
what it is. Not urgent; it blocks nothing.

**D4 — branch protection requires ZERO status checks.**
`strict: true, checks: []`, confirmed independently by two lanes. Combined with #2133 (now
fixed), a PR could merge with nothing required to pass. The exact `gh api` command is in #2144's
body under "Requires owner action", unapplied.
**Recommendation: apply it.** This is the cheapest high-value action available — it _prevents_
the stale-green merge rather than detecting it, at zero recurring cost.

**D5 — release ordering is now a hard constraint.**
`kailash.utils.network_guard` is new in core 2.63.0 (unreleased; PyPI latest 2.62.0) and BOTH
nexus and kaizen import it. **Core must publish before either dependent, or they break on clean
install.** Kaizen's floor was genuinely wrong (`>=2.56.0`, seven minors low) and is corrected on
#2150. Nine packages carry release drift and every security fix from these two sessions is
unreleased.

---

## 6. Recommendation — next steps, for ratification

1. **Merge the staged set now** — #2161 (docs), #2139, #2136, #2154. All green and verified.
   Then #2156 and #2150 auto-retarget once their bases land.
2. **Apply D4** (branch protection) — one command, prevents the failure class the whole CI
   chain was about.
3. **Decide D1** so #2140 can move; it is the last auth-surface item still blocked.
4. **Then the sub-package auth surfaces** (#2141, #2142) — same class as #2112 which just
   landed, in packages nobody had swept.
5. **Then `/release`** — the drift is now the largest unshipped risk: users on PyPI have none
   of the fail-closed auth, key-generation, SSRF, or session-ownership fixes.

**The pattern worth carrying:** eleven independent findings this session share one shape — a
control that reports success without doing its job. `verify_api_key` that cannot succeed;
rotation that never fires; `--auth` that unlocks a bind while installing nothing;
`enable_checkpointing` with no module; CI gates matching zero tests; a "signature" that is 8
characters of the secret; a marker hook keyed on memory addresses; an LOC guard raised to pass;
`run()` returning an un-awaited coroutine; an IMDS guard documented "unconditional" that no
shipped config executed; and two conformance MUSTs that cannot return False. **None are
tested-path defects. All would ship green.** Assume more exist.
