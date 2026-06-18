---
type: DECISION
slug: read-authorized-mint-specs
created: 2026-06-02T02:35:00Z
---

# Cross-Repo READ authorized — mint spec status (terrene-foundation/mint)

cross-repo-authorized: terrene-foundation/mint

A per-action READ grant (repo-scope-discipline § User-Authorized Exception, all five conditions).

- **Requester:** repo co-owner (this session's user).
- **User directive (verbatim):** "i approve you to cross inspect mint"
- **Confirmed:** prior turn asked whether mint ISS-37 (Shamir↔Vault binding) + the TieredAuditDispatcher spec are finalized — those are the two specs whose status gates kailash-py #630 and #596. The user's grant authorizes inspecting mint to determine their status.
- **Target:** `terrene-foundation/mint` (PRIVATE; existence verified this session via `gh repo view` + `gh repo list terrene-foundation`).
- **Action (bounded READ only):** `gh issue view` / `gh search` against `terrene-foundation/mint` to determine the finalization status of (1) ISS-37 (Shamir-to-Trust-Vault binding contract → gates #630), and (2) the TieredAuditDispatcher design spec (→ gates #596). Read-only inspection; NO writes, NO issue creation, NO comments.
- **Scope (condition 5):** status inspection of those two specs only. No broader trawling, no mint writes, without a new gate.

## Outcome receipt (read completed — status only)

- **#596 gate — `TieredAuditDispatcher` spec = `terrene-foundation/mint#2`:** CLOSED / **COMPLETED** (2026-04-28). Spec authoring dispositioned as done ("Finalize into foundation/docs/02-standards/ once stabilized"). → kailash-py **#596 is UNBLOCKED** pending a read of the finalized spec content to implement.
- **#630 gate — Shamir↔Vault binding spec = `terrene-foundation/mint#8`** ("Shamir 3-of-5 recovery ritual — SLIP-0039 integration pattern for Trust Vault"): **OPEN**. The "ISS-37" reference in kailash-py #630 maps to this still-open spec. → kailash-py **#630 remains genuinely blocked** (binding contract not finalized).
- Scope honored: status inspection of the two gating specs only; no mint writes, no broader trawling.
