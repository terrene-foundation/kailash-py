# R1 Redteam Cross-Check (stand-down hand-off, 2026-05-24)

**Status:** This session ran an independent R1 multi-agent redteam on shipped
`src/kailash/delegate/` THEN stood down on user direction — the parallel
`feat/1035-redteam-integration` line (verifier.py + Connector 4-primitive
rebuild + naming aliases, ~3795 LOC) is the AUTHORITATIVE line for #1035
convergence. This file preserves this session's R1 findings as a
cross-reference input for the authoritative session. It is NOT a competing
disposition.

## Provenance

- 3 parallel agents (reviewer + security-reviewer + general-purpose closure-parity), base SHA `6f22db92b` (main, pre-parallel-shards).
- Surface reviewed: the SHIPPED `src/kailash/delegate/` at v2.25.2 — i.e. BEFORE the parallel session's verifier.py / Connector-rebuild work landed on feat/1035-redteam-integration.

## Headline verdict (this session's calibration)

**0 CRIT / 0 HIGH** on the shipped surface. 4 MED + 5 LOW, predominantly
docstring-drift / cross-SDK overclaim class. 418 tests collected, 377 passed

- 1 skip (unit), 0 Tier-2/3 mocks. All 6 #1035 acceptance criteria PASS as code.

## Severity-calibration divergence vs the authoritative line (IMPORTANT)

The authoritative session's Round 1 (analyst-led) classified the API-naming
mismatch as **5 CRITICAL** and treated signature-verification absence as
**C1 + H2** (→ built `verifier.py`). This session's calibration differs:

- **API-naming mismatch:** this session rated **MINOR** (PASS-with-renamed-API
  — README §357 already publishes shipped names; renaming post-v2.24.0 is a
  breaking change). The authoritative line resolves it by ADDING ALIASES
  (`Delegate = DelegateRuntime`, etc.) — a valid resolution this session did
  not object to; merely a different disposition than "update #1035 body."
- **Signature verification (C1/H2):** this session's security agent reviewed
  the audit/crypto surface (canonical_json_dumps + 128-char hex validation +
  monotonic sequence under emit lock) and did NOT flag missing signature
  verification as CRIT/HIGH. The authoritative line treated it as CRITICAL and
  built `verifier.py` (Ed25519Verifier). **If the authoritative C1/H2 finding
  is correct, this session's security agent UNDER-classified** — the
  authoritative verifier.py work is the safer disposition. Recorded here so the
  divergence is auditable, not silently dropped.

## This session's R1 findings (cross-reference)

| Sev   | File:line                                                                      | Class                | Note for authoritative session                                                                                                         |
| ----- | ------------------------------------------------------------------------------ | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| MED   | `runtime.py:907-915`                                                           | stale docstring      | claims grantee registry is "future S7+" — already shipped #1146/#1158. May already be touched by parallel runtime.py +82 diff; verify. |
| MED   | `envelope.py:96`                                                               | misleading wording   | "only widening path" prose imprecise (bare `__init__` + `from_dict` also set fresh inner).                                             |
| MED   | `audit.py:29-34`, `dispatch.py:501-507/644-650`, `conformance/schema.py:14-16` | cross-SDK overclaim  | byte-canonical-to-rs claims lack pinned rs vectors per cross-sdk-inspection.md Rule 4.                                                 |
| MED   | `trust.py:428-463, 600-611`                                                    | cascade-as-authority | any cascade holder can register grantees; documented as #1147 territory; architectural (exceeds shard budget).                         |
| LOW   | `runtime.py:1057-1112`                                                         | deferred nonce       | `human_acknowledged_nonce` syntactic-only; needs tracking-issue link per zero-tolerance Rule 1b.                                       |
| LOW   | `dispatch.py:1425-1430`                                                        | signer attribution   | 32-char lower-bound vs strict 128; misroutes error attribution. (May be superseded by parallel verifier.py.)                           |
| LOW   | `audit.py:213,234`                                                             | parity-but-blocked   | `REASONING_SCRATCHPAD` rejection path needs a Tier-2 test asserting it fires.                                                          |
| LOW   | `trust.py:600-611`                                                             | defense-in-depth     | `cascade_child` registers parent idempotently w/o membership check; #1147 adjacent.                                                    |
| MINOR | `__init__.py`                                                                  | API naming           | shipped vs #1035-body names — RESOLVED by authoritative line's aliases.                                                                |

## loom#350 triangulation (this session, see journal/0007 for the authorization receipt)

All 7 loom#350 emit-discipline findings reproduce on this repo's synced
artifacts. NONE invalidate the delegate code disposition. Finding 2 (analyst
declares Edit/Write/Task contradicting `rules/agents.md` read-only
classification) is the systemic gap that BOTH redteam lines navigated:
this session dispatched general-purpose for closure-parity (correct per rule);
the authoritative line dispatched analyst (the agent file's wrong tools made
that path available). Disposition: loom-source fix, fix-the-class via the
#350 pre-emit validator.

## Hand-off recommendation

The authoritative line should:

1. Verify the MED docstring-drift findings above weren't masked by its own
   runtime.py/audit.py/trust.py diffs.
2. Treat the C1/H2 verifier.py work as the correct (safer) disposition — this
   session's 0-CRIT/HIGH calibration on the crypto surface was the more
   permissive read.
3. Pick ONE naming disposition (aliases — already chosen by authoritative line)
   and update #1035 body OR keep aliases; do not do both half-way.
