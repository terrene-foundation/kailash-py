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

---

## FINDING (read outcome, 2026-06-20)

Read scope: `esperie-enterprise/kailash-rs` (local checkout `/Users/esperie/repos/loom/kailash-rs`), audit-chain canonical-hash surface only. READ-ONLY; no writes.

**kailash-rs is NOT on the 6-digit-microsecond form — it is on WHOLE-SECOND, and so was kailash-py before this fix.**

- The shared cross-SDK fixture `kailash-rs/test-vectors/audit-chain-canonical.json` ("Byte-for-byte identical between kailash-rs and kailash-py") pins **whole-second** timestamps: vector `anc-u1-001` = `2026-01-15T11:00:00+00:00` → `expected_sha256: 6946e734daa8279d4dc173918109995e0d10b647a7d3cd0b36aeb4114e8e12c3` — the EXACT sha256 kailash-py emitted before this fix.
- `kailash-audit-vectors/src/lib.rs::build_canonical_input` pushes `input.timestamp` **verbatim** into the canonical string (no fixed-precision normalization); rs `TieredAuditEvent.timestamp` is a stored `String` defaulting to `chrono::Utc::now().to_rfc3339()` (variable precision, elides at zero-nanos).
- No in-flight rs work aligning the audit chain to 6-digit microseconds.
- CONTRAST: the rs *trace-event* fixture IS 6-digit (`2026-04-20T12:00:00.000000+00:00`, V1 `792c1398…`) and already matches kailash-py — so the trace-event axis is in parity; only the AUDIT-CHAIN axis diverges.

**Consequence:** the #1400 timestamp-always-6-digit change to the audit chain moves kailash-py's U1 to `f1c755c8…`, breaking the shared byte contract rs (unchanged) still satisfies. The change cannot ship py-only. The other changes (#1401 tz guard, #1403/#1405 typed-scalar whitelist, #1404 extraction, allow_nan, provenance, required-names, docs) are byte-neutral on the EXISTING shared string-metadata/whole-second vectors. The fix's direction (deterministic 6-digit, aligning audit-chain to trace-event + closing the latent sub-second elision/nanos divergence) is sound but requires a coordinated cross-SDK lockstep. Disposition is the user's (manages both teams).
