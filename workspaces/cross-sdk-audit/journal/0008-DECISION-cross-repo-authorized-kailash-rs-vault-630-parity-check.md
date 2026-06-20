# DECISION — Cross-repo authorization: kailash-rs F-VAULT-630 parity check + file

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (technical leader, this session), genuine user turn.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; Rust SDK sibling BUILD repo).
- **Timestamp:** 2026-06-20T06:33:31Z
- **Verbatim instruction:** "please check kailash-rs repo and file if gap exists"
- **Bounded action authorized:**
  1. READ kailash-rs source (via `gh`) to determine whether its vault SLIP-0039
     binding has the SAME gap kailash-py just closed in F-VAULT-630 — i.e. whether
     the Rust equivalents of `recommit_vault_kek` / `retire_vault_kek_alg`
     enforce the registry-mutating-gate clearance as capability-PRESENCE-only,
     missing the CL-02a tenant/domain + CL-04 cooling-off scoping the gate name
     implies.
  2. IF the gap exists: file ONE scrubbed cross-SDK GitHub issue against
     `esperie-enterprise/kailash-rs` (per `cross-sdk-inspection.md` — `cross-sdk`
     label + a cross-reference to the kailash-py work; per `upstream-issue-hygiene.md`
     MUST-2/3 — minimal-repro shape, no kailash-py session internals beyond the
     SDK API surface). The issue body is restated to the user for a final
     confirm BEFORE submission (the outward-facing, hard-to-reverse step).
- **Scope fence (condition 5):** ONLY the gap check + at most one issue against
  the named repo. No incidental reads, no edits/PRs/comments elsewhere, no
  scope creep. The metadata access-confirmation (`gh repo view`) preceded this
  entry; all SUBSTANTIVE cross-repo actions (source inspection + filing) land
  after it.
- **Context:** kailash-py shipped the fix as 2.43.0 (PR #1408, merge `6f640cad8`,
  tag `v2.43.0`); ledger item `F-XSDK-VAULT-630`. Cross-SDK surfacing is mandated
  by `cross-sdk-inspection.md` Rule 1; the user converted the surfacing into an
  explicit file-authorization.

## Outcome (2026-06-20)

Gap CONFIRMED in kailash-rs `crates/eatp/src/vault/` — broader than kailash-py's
F-VAULT-630: N12-CL-02a tenant/domain scoping is unimplemented binding-wide
(0 tenant/domain in `clearance.rs` + `backup_restore.rs`; CL-04 cooling-off IS
wired), a fail-open the rs binding's own normative-subset spec marks a MUST; and
the recommit/retire registry-mutating ops appear unimplemented (audit-payload
types + error codes + registry-read exist; no operation fns / FT-03 gate orders).
No pre-existing rs issue. User confirmed the scrubbed body. **Filed:
`esperie-enterprise/kailash-rs#1442`** (label `cross-sdk`, cross-refs
terrene-foundation/kailash-py#1408). Internal `F-VAULT-630` tag scrubbed from the
issue body per `upstream-issue-hygiene.md` MUST-2. Scope honored: read-only source
inspection + exactly one issue; no other cross-repo action.
