# 0011 — Cross-repo grant: file Rust-SDK mirror issues for #1710 + #1713

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn — user replied `approved` to the orchestrator's
   AskUserQuestion whose "Cross-SDK" question offered "File both mirror issues".
2. **Explicit + specific:** the question named the exact target (the Rust SDK BUILD repo)
   and the exact action (file `cross-sdk`-labelled mirror issues for the #1710 mint-gate
   and #1713 DoS-bound parity).
3. **Confirmed:** user `approved` (2026-07-15).
4. **Journaled before acting:** this entry, written BEFORE the `gh issue create` commands.
5. **Scoped exactly:** two issue filings on `esperie-enterprise/kailash-rs` ONLY — no other
   action, no incidental reads/writes.

- **Requester:** user (tabula.rasa.integra@gmail.com)
- **Target:** esperie-enterprise/kailash-rs (verified exists, private=true, 2026-07-15)
- **Action:** create 2 issues, label `cross-sdk`
- **Timestamp:** 2026-07-15
- **Verbatim instruction:** user answered `approved` to the question
  "File the Rust-SDK cross-SDK mirror issues? #1710 and #1713 both have Rust siblings …"
  with recommended option "File both mirror issues".

## What is filed

- **Mirror of #1710** (EATP capability/lineage/audit mint fail-closed gate): the Rust SDK's
  EATP `delegate()`/`audit()` mint path should verify chain integrity + reject expired grant
  - require a genesis issuer before producing any signature (EATP D6 matching semantics).
    Landed py-side in kailash 2.52.0 (py PR #1750).
- **Mirror of #1713** (BH3 origin-digest unauthenticated DoS bound): the Rust SDK's BH3
  origin-digest / subject-hash ingress should carry the same fail-closed resource bounds
  (depth/nodes/children/cumulative-bytes) before canonicalization+hash. The BH3 module
  already references the `rs#1707` handoff. Landed py-side in kailash 2.52.0 (py PR #1749).

Per cross-sdk-inspection.md Rule 2: each issue cross-references the originating py issue
number and carries the `cross-sdk` label.

## Result (filed 2026-07-15, verified created)

- **rs#1829** — mirror of #1710 (mint fail-closed gate): https://github.com/esperie-enterprise/kailash-rs/issues/1829
- **rs#1830** — mirror of #1713 (BH3 origin-digest DoS bounds): https://github.com/esperie-enterprise/kailash-rs/issues/1830

Both created with `cross-sdk` label, cross-referencing kailash-py #1710/#1713 (released in kailash 2.52.0).
