---
type: DECISION
slug: wave1-converged-inter-wave-gate
created: 2026-06-14T09:30:00Z
---

# Wave 1 (Foundation) — converged; inter-wave gate G1–G4 receipt

Branch `feat/eatp-12-vault-binding` @ `31ebe6ad6` (+ fix commit). Wave 1 shards F1/F2/FT/C1/T1 implemented; 14 Tier-1 tests pass; 120 existing trust tests pass (F1 backward-compatible). The byte-pins reproduce the §12.2/§12.3 golden hashes EXACTLY through the production `canonical_json_dumps` (commitment `f325754c…405c`, KCV `00051364b85b0a43`).

## G1 — redteam to convergence (the `/implement` MUST gate)

Two parallel gate reviewers (durable receipts — the agent task IDs below are the external receipt per `verify-resource-existence.md` MUST-4):

- **reviewer** (task `aae95f6af2f7b4c05`): **APPROVE.** All 5 mechanical sweeps pass — encoder routes through `canonical_json_dumps` (no inline `json.dumps`); 14 tests green; all 19 `vault.__all__` symbols resolve (no orphan); `N12FT01Code` closed at exactly 25; `RESTORE_GATE_ORDER` byte-exact with §4.6; EATP conventions met. Confirmed the byte-pin suite genuinely reproduces the production path (not fixture theatre) and FT-02/FT-03 skeletons are pure/deterministic.
- **security-reviewer** (task `a70c42f949c48d164`): **APPROVE-WITH-FIXES.** Crypto core sound — constant-time `hmac.compare_digest`, fail-closed `_resolve_hash`, no secret material on any DTO / in logs / in `.details`, byte-exact JCS, closed non-collapsed 25-code taxonomy (foreign-shard → `unknown-shard`, never `corrupted-shard`).

### Findings + dispositions (all resolved or tracked)

- **MED-1 (fixed this gate):** `types.py:124` `VaultKeyHandle` docstring falsely claimed `key_id` is "bound into the commitment via N12-IN-04" — contradicted the correct `commitment.py:23-28` docstring (`zero-tolerance` Rule 3e: doc claim about code surface must be accurate). Reworded to state key-id binds at the receipt/registry layer (C2a), NOT in the §12.2 pre-image.
- **LOW-2 (fixed this gate):** `BackupReceipt` validated KCV length but not hex-shape — a non-hex receipt constructed then failed later as a confusing compare-mismatch. Added `[0-9a-f]{16}` (KCV) + `[0-9a-f]{64}` (commitment) lowercase-hex guards + 2 regression assertions.
- **C2a tracking (G3 — amended into the C2a todo):** the security-reviewer's Finding-5 verdict + LOW-1. See below.
- **LOW-3 (accepted, noted):** `KeyMetadata` is `@dataclass` (mutable), not frozen. Acceptable as-is — it is NOT a constraint dataclass (the surface `trust-plane-security` MUST NOT §4 names); the vault DTOs ARE all `frozen=True`; `kek_generation` monotonic advance is enforced at the rotation path (N12-RT-06). Freezing a pre-existing core class is out of this wave's surface.

## The N12-IN-04 disposition (institutional knowledge — the flagged cross-SDK question, RESOLVED)

The §12.2 commitment pre-image is **`vault_id`-keyed and omits `key_id`** — required to stay byte-exact with kailash-rs (the fixed pre-image IS the cross-SDK contract). The security-reviewer's adversarial Finding-5 verdict: **the disposition is SOUND, not a cross-vault/identity-confusion vector**, because:

1. **`vault_id` (in the commitment) carries the cross-vault defense** — a cross-vault re-install changes `vault_id` → changes the commitment → fails the recompute. N12-CB-01 explicitly equates the bound `vault_id` with "the resolved KEK's `vault_id` per N12-IN-04."
2. **`key_id` adds intra-vault key-identity disambiguation** (two KEKs in the same vault+generation) — that is the `key-identity-mismatch` (N12-CB-02(d)) control's job, which the spec routes through the **registry/receipt layer**, NOT the commitment hash. Binding `key_id` into the §12.2 hash would both break cross-SDK byte-exactness AND conflate two controls the spec deliberately separates.
3. **The one real risk is the deferral itself:** `KEY_IDENTITY_MISMATCH` + the `key_id` field ship in Wave 1 but the comparison does not — so they are orphaned controls until C2a wires them (`facade-manager-detection.md`). Acceptable for a substrate wave; tracked as a hard carry-in on C2a (G3).

## G2 — learning captured

This journal entry (lightweight per `wave-loop.md` G2 — full `/codify` reserved for cross-project learnings). The N12-IN-04 layering decision is the load-bearing institutional knowledge.

## G3 — later-wave todos amended

`todos/active/00-plan.md` W3-C2a gained a ⚠ Wave-1 G1 carry-in block: C2a MUST wire (a) the registry-layer `key-identity-mismatch` comparison + Tier-2 wiring test, and (b) the `map_wrapper_exception` fail-closed caller + Tier-2 deny test, before any restore path ships.

## G4 — re-rank

No change: waves are dependency-ordered; **Wave 2 (Audit substrate + Input — D1/D2/I1)** remains the next eligible wave (the producer Wave 3 consumes). Value-anchor unchanged (EATP-12 spec §4.5/§4.1).

**Wave 1 is converged.** Next: G5 launch Wave 2.
