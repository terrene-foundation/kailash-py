# DECISION — Cross-repo authorization: kailash-rs audit-chain canonical-hash conformance read

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (technical leader, this session), genuine user turn.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; Rust SDK sibling BUILD repo).
- **Timestamp:** 2026-06-20T18:00:00Z
- **Verbatim instruction:** "i authorize you to check kailash-rs"
- **Bounded action authorized (READ-ONLY):**
  1. READ the kailash-rs audit-chain canonical-hashing source (the Rust
     equivalent of `AuditAnchor::compute_hash` / its canonical-input builder, and
     the trace-event fingerprint / signing serializer) to determine whether
     kailash-rs ALREADY emits the conformant canonical form that kailash-py was
     just brought into on branch `fix/audit-chain-canonical-conformance`
     (commits `9b9e01d3e`/`a529f94e8`/`e00f07872`):
     (a) timestamp rendered with six fixed microsecond digits (always), vs
     microsecond-eliding at `microsecond == 0`;
     (b) typed-scalar metadata via a deterministic whitelist (no
     implementation-defined `str()` / `default=str` analogue).
  2. The purpose is to resolve the release-sequencing question I surfaced: if
     Rust is already on the 6-digit-microsecond + typed-scalar form, releasing
     the Python fix CLOSES the cross-SDK divergence; if not, the rs#449 lockstep
     must be coordinated before the Python PyPI release.
- **Scope fence (condition 5):** ONLY the read described above against the named
  repo. NO writes, NO PRs, NO comments, NO issue filings against kailash-rs in
  this authorization. (Any subsequent issue filing — e.g. the rs#449 lockstep
  follow-up — would require its OWN explicit user authorization + a new
  receipt-before-acting entry per `upstream-issue-hygiene.md` MUST-1.) Repo
  discovery / metadata access (locating the on-disk checkout or `gh repo view`)
  is the minimal setup preceding the source read.
- **Context:** kailash-py `fix/audit-chain-canonical-conformance` resolves the
  7-issue audit-chain canonical-hash cluster (#1400/#1401/#1402/#1403/#1404/
  #1405/#1407) — a documented cross-SDK byte contract (`kailash-rs#449 §2`).
  `cross-sdk-inspection.md` Rule 1 mandates the sibling-SDK inspection; the user
  converted the surfacing into an explicit read-authorization. The byte-contract
  change is what makes the rs conformance status load-bearing for release
  sequencing.
