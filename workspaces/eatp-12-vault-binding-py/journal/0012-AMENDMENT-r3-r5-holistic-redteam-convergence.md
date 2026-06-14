---
type: AMENDMENT
slug: r3-r5-holistic-redteam-convergence
created: 2026-06-15T00:00:00Z
relates_to: 0011-DECISION-wave6-converged-terminal-redteam
---

# R3→R5 holistic redteam — true 2-consecutive-clean convergence (amends 0011)

Branch `feat/eatp-12-vault-binding`. This amends 0011's "Wave 6 CONVERGED" verdict.
0011's terminal redteam ran R1 (3 findings → fixed in `3f153328c`) → R2, but **R2 was
security-reviewer ONLY — a single clean round**. The convergence bar
(`commands/redteam.md` § Convergence #3) requires **2 consecutive clean rounds across
all agents**. This session ran that bar to completion: a fresh holistic R3 (all 3
reviewers) surfaced new findings the single-agent R2 missed; they were fixed +
regression-tested; R4 + R5 are the two consecutive clean rounds.

**All edits this session are UNCOMMITTED working-tree changes** — kailash-py is a BUILD
repo, so per the operating envelope (`feedback_build_repo_release`) commits stay with the
user. Baseline at session start: 183 vault tests pass / 1 skipped. End state: **193 pass
/ 4 skipped, ruff clean** (re-derived, not trusted).

## R3 — holistic round, 3 parallel reviewers across the union of all 6 waves

Durable receipts (agent task IDs per `verify-resource-existence.md` MUST-4):

- **security-reviewer** (`aa9ee7a314dfd99ef`): FINDINGS — **HIGH-R3-1**: `restore_vault_key`
  resolves the KEK (backup.py:873) then runs the `_find_distribution_anchor` + dist-anchor
  extraction span (885-897) OUTSIDE any try/finally, BEFORE the first zeroize. A raise there
  (attacker-shapeable recovery-tier engine state — `dispatcher._engines.get`, `entry.event_payload`,
  `list(dist_anchor.get("holders"))`) leaks the resolved KEK un-zeroized. The exact N12-IN-05
  residency class R1 HIGH-1 closed for the X1 block, on a SIBLING span the R1 fix did not cover;
  also correctly re-judged the R2-accepted-LOW as too narrow.
- **reviewer** (`a223f27b88de1a4e9`): GAPS-FOUND — 3 orphaned-control siblings of the R1 PP-01
  class (declared codes, zero raise sites) + 1 LOW coverage gap (below).
- **closure-parity** (`a06f949ec1d29f313`): GAPS-FOUND — 4 GAP-HIGH; 0011's "54/54 VERIFIED,
  zero orphans" self-report did not hold under fresh Bash-backed re-verification (50/54; R1
  dispositions confirmed real, but the R1 sibling-sweep for orphaned controls was incomplete).

Consolidated R3 findings (all spec-verified against `briefs/eatp-12-v1.0-spec.md` before disposition):

| #         | Sev                 | Finding                                                                                                                                                                                        |
| --------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HIGH-R3-1 | HIGH                | KEK residency leak on the distribution-source span (backup.py:885-897)                                                                                                                         |
| GAP-1     | HIGH                | `kcv-mismatch` orphaned — `verify_kcv` zero production call sites; spec §4.4.1/V6/N12-CB-04(d) mandate it                                                                                      |
| GAP-2     | HIGH                | `too-many-shards`(step3) + `mixed-shard-set`(step5) dead gates → fell through to `corrupted-shard`/`parameter-mismatch`; spec §4.6/V5(f)(g)(h)/F-XSDK-13 mandate distinct codes at those steps |
| GAP-3     | HIGH (test)         | cross-delegate replay-denial regression missing (binding real at complete.py:135/156/313, regression absent)                                                                                   |
| GAP-4     | HIGH (Complete-opt) | `side_channel_hardened=true` Complete-path unenforced — a fake-classification risk per zero-tolerance Rule 2                                                                                   |
| LOW-1     | LOW                 | `recommit-binding-mismatch` reachable (registry_ops.py:253), zero test                                                                                                                         |

## Dispositions (all fixed same-session per autonomous-execution Rule 4 — implementer `a1a24ede396a200e2`)

All spec-faithful WIRE (the spec mandates every contested code; deletion would make py
non-conformant to the published EATP-12 v1.0 spec):

1. **HIGH-R3-1** — wrapped the dist-source span (backup.py:969-983) in `try/except
BaseException: resolved.zeroize(); raise`; `zeroize()` idempotent so it composes with the
   X1-block explicit zeroizes + the main finally. Every post-resolution exit now zeroizes.
2. **GAP-2** — real pre-reconstruction predicates: step-3 `shard-count` (k from SLIP-0039
   member-threshold via `Share.from_mnemonic`; `<k`→insufficient-shards, `>k`→too-many-shards
   — **py pins the N12-FT-02 REJECT branch**, recorded for the XSDK gate) + step-5
   `mixed-identifier` (`.identifier` distinctness → mixed-shard-set, fires before step-6
   foreign-shard). errors.py `_WRAPPER_TEXT_MAP` remap "identifier parameters don't
   match"→MIXED_SHARD_SET (defense-in-depth).
3. **GAP-1** — `expected_kcv` param on `restore_vault_key`; recompute `key_check_value`
   post-reconstruction in commitment-auth gate, `hmac.compare_digest` → KCV_MISMATCH.
4. **GAP-4** — `side_channel_hardened=True` rejected at the `back_up_vault_key` entry gate
   (userspace `combine_mnemonics` cannot truthfully back the claim; spec N12-CRY-SC).
5. **GAP-3 + LOW-1** — cross-delegate replay-denial test + recommit-binding-mismatch test.
6. **Spec truth-update (`specs-authority.md` Rule 5)** — `specs/trust-crypto.md` §30 gate-order
   summary updated to include the now-active steps 3/5 + the offline kcv-mismatch; Security
   Caveat updated to state side_channel_hardened=true is rejected. `security-data.md §10`
   sibling re-derived (Rule 5b) — no stale claim (it defers to §30). Spec-accuracy self-audit:
   zero split-state hits, all citations grep-resolve.

10 new tests added (the 4 formerly-orphaned codes + LOW-1 + cross-delegate + side_channel
positive/negative). Two pre-existing tests corrected (canonical_vectors wrapper-map assertion;
quickstart foreign-shard set genuine+foreign→homogeneous-foreign) — spec-faithful per the
now-active step-5 mixed gate, verified by all R4 agents, NOT tests-bent-to-code.

## R4 — first clean round (3 parallel reviewers, current working-tree state)

- **security-reviewer** (`a94e54c25867d870b`): **CONVERGED 0 CRIT/0 HIGH** — re-traced every
  post-resolution exit zeroizes; all new fixes fail-closed, no secret leak; all unchanged
  invariants PASS.
- **reviewer** (`adcfa78e32a705811`): **APPROVE 0 CRIT/0 HIGH** — orphan re-sweep all 25 codes
  have raise+test; gate-order regression clean; no new stubs/fallbacks.
- **closure-parity** (`a3e0e999c0176f475`): **CONVERGED** — all 4 GAPs + LOW-1 closed with
  command receipts; zero remaining orphans; suite 193/4; pre-existing-test changes spec-faithful.

## R5 — second clean round (spec-accuracy + regression, current working-tree state)

- **reviewer** (`aa2e4a0a8f87e8112`): **CLEAN** — §30 gate-order prose byte-matches
  `RESTORE_GATE_ORDER` + `check()` codes; all citations grep-resolve (zero phantoms); zero
  split-state ("XSDK reconciliation deferred" is a legitimate out-of-scope boundary per
  spec-accuracy Rule 3, not a gap-tracker); zero code regression since R4 (src+tests
  byte-identical, only the 2 documented §30 doc edits); suite 193/4 green; 4 codes still wired+tested.

## Convergence verdict

**CONVERGED.** R4 (3 agents, 0 CRIT/0 HIGH) + R5 (clean) = two consecutive clean rounds.
Criteria 1-6 met: 0 CRIT, 0 HIGH, 2 consecutive clean, spec 100% AST/grep-verified (54 IDs +
25 codes + §30 accurate), new code has new tests, no frontend. The holistic round earned its
keep: R3 surfaced 1 HIGH (security) + 4 orphaned-control gaps that the per-wave G1 gates AND
0011's single-agent R2 all missed.

## Remaining before release (unchanged from 0011 — NOT this session's scope)

- **Working-tree edits are UNCOMMITTED** (BUILD repo; commits stay with the user). 7 src+test
  files + `specs/trust-crypto.md` modified.
- **XSDK-1/2/3 cross-SDK parity gate** still the release gate — now ALSO must reconcile py's
  N12-FT-02 REJECT-branch choice (does kailash-rs reject or canonical-trim on over-supply?) +
  the new `mixed-shard-set` step-5 classification + the `expected_kcv` offline check. Requires a
  separate user-authorized cross-repo grant (`repo-scope-discipline.md`). Neither SDK releases
  vault binding before this confirms.
