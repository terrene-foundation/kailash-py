---
type: AMENDMENT
date: 2026-06-15
author: agent
project: issue-1316-eatp08-marker-regime-py
topic: Terminal-gate convergence receipt — holistic redteam (T1) + cross-SDK parity (T2) + user-flow walk (T3) across all #1316 PRs; release plan 2.34.0
phase: redteam
tags: [eatp-08, terminal-gate, holistic-redteam, convergence, release]
relates_to: 0006-DISCOVERY-no-marker-store-3b-reshard
---

# 0007 — AMENDMENT: terminal-gate convergence (#1316 Wave-2 close)

Receipt for the terminal gate (todos T1/T2/T3) after all six #1316 PRs merged to
main (#1324 Shard 1, #1325 inter-wave docs, #1326 Shard 4, #1327 Shard 2, #1328
Shard 3A + review-fix, #1329 Shard 5). Union base `63532704d`.

## T1 — holistic post-multi-wave redteam (agents.md § Holistic Post-Multi-Wave Redteam)

Three parallel agents scoped to the UNION of all #1316 shards on main (not the
latest diff). All converged; every finding fixed in-PR before the release cut.

| Agent             | Verdict                    | Findings → disposition                                                                                                                                                                                                                                                                                                                                                                         |
| ----------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| reviewer          | APPROVE                    | 6442 passed, 0 fail; D2 dispatch precedence clean across all 9 composition paths; signed_marker_payload↔verify contract consistent; 5-site threading complete; CHANGELOG accurate. MED-1 (D2dVerifierKeys + d2d_legacy_acceptance_count not re-exported) → fixed PR #1330. MED-2/LOW-1 (§32.1 stale citations) → fixed PR #1330. LOW-2 (§32.4 framing) → clarified PR #1330.                   |
| security-reviewer | APPROVE                    | No CRIT/HIGH. Composed bypass analysis clean (monotonic gate unbypassable, precedence correct); first_v2_seen signed-bytes integrity sound (no attacker-supplied-witness path); fail-closed across all error paths; §7.1 principal hashed not leaked; V6(iii) backdating defense intact. 2 LOW non-actionable (intentional expiry-inclusive semantics; pre-existing migration-counter global). |
| closure-parity    | CONVERGED (AC1-7 VERIFIED) | 184 passed, 0 fail. V4-V7+V9 pass at stated levels (V7=Complete); D2c 5-check gate; §7.1 WARN+hash+counter; monotonic threaded 5 sites; composed e2e regression; scope decisions honored (3 OUT-of-scope §5.3 codes absent, no marker-store, 3B re-shard documented); CHANGELOG present. AC8 (2 stale citations) → fixed PR #1330.                                                             |

Round 1 surfaced only spec-citation + public-surface-re-export findings (no
behavioral/security defects); all fixed in PR #1330 (re-export D2dVerifierKeys +
d2d_legacy_acceptance_count + corrected every §32 `algorithm_id.py:NNN` citation +
LOW-2 clarification + a public-surface regression test). Post-fix broad sweep:
6443 passed, 0 fail. The gate is converged — no second adversarial round needed
(no defect class remained open; the findings were doc/surface accuracy, fixed and
re-verified by the surface-guard test + the citation grep-resolution sweep).

## T2 — cross-SDK parity

kailash-py is the CANONICAL AUTHOR of `tests/test-vectors/eatp08-alg-id-canonical.json`
(per the file header + journal 0001 Cluster 4). Byte/behaviour parity is enforced
by `test_eatp08_alg_id_canonical_vectors.py::test_registry_canonical_member_and_sha_reproduce`
which re-derives every `canonical_member` + `expected_sha256` from the live
implementation (5/5 registry tokens reproduce). The kailash-rs vendor-pull of this
file is a DOWNSTREAM `esperie-enterprise/kailash-rs` session (ISS-33), NOT performed
from this repo per `repo-scope-discipline.md`. No cross-repo dependency blocks the
py release. T2 satisfied: the canonical surface is self-consistent + byte-pinned.

## T3 — user-flow walk (user-flow-validation.md) — verbatim receipt

Exercised every documented decode path through the canonical public import path
(`from kailash.trust.signing import ...`) as a downstream verifier would. Receipt
(scrubbed — `chain:acme` is a test fixture, `cd1d750f` is an 8-char sha256 hash,
not PII):

```
WALK 1 — conformant v2 record (D2c):
  decode {'alg_id':'eatp-v1'} -> eatp-v1
WALK 2 — D2d legacy nested form + signed pre-adoption marker:
  decode nested+witness -> eatp-v1
  legacy acceptances counted (§7.1): 1
  [§7.1 WARN fired: principal_hash=cd1d750f (hashed, not raw), counter=1]
WALK 3 — D2b post-adoption record missing alg_id (reject):
  rejected -> missing-alg-id-post-adoption
WALK 4 — backdating attack: pre-registry form, unsigned marker (reject):
  rejected -> implicit-v1-witness-failure
WALK 5 — strip attack on prior-v2 chain (monotonic reject):
  rejected -> monotonic-upgrade-violation
WALK 6 — prior-v2 via signed first_v2_seen marker (monotonic reject):
  rejected -> monotonic-upgrade-violation
```

Disposition: every documented path behaves as the spec + CHANGELOG promise; typed
codes throughout, no crash; the §7.1 logging hygiene (hashed principal at WARN)
confirmed live during WALK 2. The walk also validated MED-1's fix — the public
`kailash.trust.signing` import path resolves all D2d symbols.

## Release plan (BUILD-repo discipline)

Scope enumeration (Rule 3): NO sibling drift — every package main == PyPI. The
only release is core `kailash` 2.33.1 → **2.34.0** (minor: new D2c/monotonic/
V-vector public surface). After PR #1330 merges, cut `release/v2.34.0`
(version bump pyproject + `__init__.py` + CHANGELOG [Unreleased]→[2.34.0]) →
PyPI publish (human-authorized structural gate per build-repo-release-discipline
Rule 4) → clean-venv install + import verify.
