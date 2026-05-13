# 0004 DECISION — Red-Team Convergence Verdict

Date: 2026-05-13
Phase: /analyze (expanded with expert team + pentest, /redteam to
convergence per user directive)
Issue: #979

## Convergence target

User directive: "/redteam to convergence". Self-imposed target:
two consecutive rounds with zero new CRIT/HIGH against the working
plan.

## Rounds executed

| Round | Agents | New CRIT | New HIGH | Verdict       |
| ----- | ------ | -------- | -------- | ------------- |
| R1    | 3      | 2        | 5        | NOT-CONVERGED |
| R2    | 2      | 0        | 1        | NOT-CONVERGED |
| R3    | 1      | 0        | 0        | **CONVERGED** |

Total: 6 adversarial / verification agents across 3 rounds.

## R1 outcomes

- Falsified: HIGH-D (DNS-rebinding) — code DOES resolve DNS via
  `socket.getaddrinfo` (`ssrf.py:73-110`). Pentest adversary
  verified.
- Falsified: HIGH-F ("Engine API ZERO tier-1 coverage") —
  `tests/unit/test_engine_validate_record_bp049.py:25` imports
  `DataFlowEngine`. Tech adversary verified.
- Falsified: HIGH-C catastrophic claim — tier-2 sanitizer tests
  exist at `test_connection_sql_injection_protection.py:82-91,
356, 366`. Tier-1 gap remains but downgraded.
- Reframed: CRIT-A — `pytest-forked` is NOT archived (release
  specialist was wrong about archived status). Still drop because
  zero consumer in `packages/kailash-dataflow/`.
- New CRIT: ATTACK-2 — DEFENSE-2 sanitizer test as drafted imports
  a nested closure that isn't module-importable. Public-API path
  required.
- New CRIT: ATTACK-6 — `test_saas_tenancy.py` move to integration
  enables silent regression because `unified-ci.yml` doesn't run
  integration on PRs.
- Value-rank adversary: 55% of expert findings claimed pre-existing
  → after R1 falsifications, ~11%. Original OPTION-C basis weakens
  but split remains viable.

## R2 outcomes

- ATTACK-2 VERIFIED empirically. `sanitize_sql_input` is nested
  closure at `nodes.py:787`; Rule-2 ValueError is at `nodes.py:923`
  via `validate_inputs`. DEFENSE-2 must use public API.
- ATTACK-6 VERIFIED. `unified-ci.yml:8-26, 137-145` confirms
  `tests/integration/` fires NEITHER on push NOR PR. Tenancy file
  is 100% mocked and pure-Python; meets tier-1 today.
- Gap-1 (strict-markers race) FALSIFIED — markers registered in
  `tests/unit/conftest.py:162-171::pytest_configure`.
- Gap-2 VERIFIED (HIGH) — dual coverage-config drift between
  `pytest.ini` and `pyproject.toml`. Consolidate in S1.
- Gap-3 VERIFIED (HIGH) — asyncio scope keys only in pytest.ini;
  preservation required during CRIT-C consolidation.
- OPTION-C feasibility revision: original OPTION-C missed AC#2 and
  HIGH-B. Revised to OPTION-C′ with S-EV (AC#2 owner) and S6
  DEFENSE-3 placeholder.

## R3 outcomes (convergence)

All 6 amendment-v2 items VERIFIED:

1. ATTACK-2 fix — public-API path test design (verified)
2. ATTACK-6 fix — tenancy KEEPS in tier-1 (verified)
3. Coverage consolidation — pytest.ini canonical (verified)
4. Asyncio scope preservation (verified)
5. AC#2 owner — S-EV shard (verified)
6. HIGH-B fabric compensation — `test_fabric_smoke_invariants.py`
   in S6 (verified)

Five LOW polish findings (N1-N5). N1 actioned in this entry —
fabric smoke is now mandatory in BOTH OPTION-A and OPTION-C′ (not
"C′ only" as initial amendments-v2 said).

## Pentest artifact summary

Three files at `01-analysis/02-pentest/`:

- `00-security-coverage.md` — coverage audit + COVERAGE-LOSS rows
- `01-adversarial-scenarios.md` — 5 canary PR specs, 4 move-time
  risks, 2 sanitizer regressions, 4 fabric integration scenarios,
  6 structural defenses
- `02-security-test-inventory.md` — 18 security-purposeful tier-1
  files; mapping vs proposed moves

Net security posture (per the post-R1+R2 amendments):

- Tier-1 security test count: 18 today → 17-18 after Workstream-A
  (tenancy KEEPS; fabric moves with smoke compensation)
- Pre-existing gaps documented but most are out of brief scope:
  - HIGH-C tier-1 sanitizer contract (Workstream-C separate issue)
  - HIGH-D FALSIFIED, struck
- New canary tests authored against the gate itself (S6):
  test_sanitizer_public_api + test_fabric_smoke_invariants

## Plan state for /todos

Authoritative documents (in reading order):

1. `briefs/00-brief.md` — user's brief
2. `02-plans/02-amendments-v2-post-redteam-r1r2.md` — final
   shard list (this is the authoritative plan)
3. `journal/0003` — expert findings reconciliation
4. `journal/0004` — this entry (convergence)
5. `01-analysis/02-pentest/` — pentest artifact (3 files)
6. `specs/testing-tiers.md` — domain spec

The user gate at `/todos` has three paths to choose between:
OPTION-A (full integrated, ~14 shards, ~7-10 sessions),
OPTION-B (tier-1 floor only, ~6 shards, ~3 sessions, fails AC#2

- AC#6), OPTION-C′ (split with corrections, Workstream-A ~8
  shards + Workstream-B ~5 shards + Workstream-C separate).

Recommendation in synthesis at next user turn.

## Convergence receipt

Per `rules/verify-resource-existence.md` MUST-4 (round-verdict
claims MUST cite durable receipts): this journal IS the receipt.
The R1/R2/R3 agent transcripts are at:

- R1: agents `a083dd001fc816691` (tech), `ade1ed2cf67f63851` (pentest),
  `a54c9f85098a21700` (value-rank)
- R2: agents `ab850b8a08f9588d1` (empirical), `a13c647174d5c0f1f` (OPTION-C)
- R3: agent `abcdabfff6fb9f261` (convergence verify)
