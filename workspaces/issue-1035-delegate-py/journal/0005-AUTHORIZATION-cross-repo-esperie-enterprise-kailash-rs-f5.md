# 0005 — AUTHORIZATION — Cross-Repo F5 Upstream Issue Filings (esperie-enterprise/kailash-rs)

cross-repo-authorized: esperie-enterprise/kailash-rs

Supersedes: 0004 (voided — target `terrene-foundation/kailash-rs` does not exist per live `gh api` check)

## Authorization receipt

- **Requester:** session operator (resolved via `lib/operator-id.js`)
- **Target repo:** `esperie-enterprise/kailash-rs` (verified existing + accessible + issues enabled via `gh api repos/esperie-enterprise/kailash-rs`)
- **Bounded action:** file two (2) upstream issues for cross-SDK semantic-parity gaps:
  - Issue A: principal-kind taxonomy on rust `DelegateIdentity` / `Role` / `DispatchSurface`
  - Issue B: grantee registry on rust `TenantScopedCascade` + dispatch identity-bind validation
- **Timestamp:** 2026-05-24 (session window post-12:30Z)
- **Authority chain:** `repo-scope-discipline.md` § User-Authorized Exception (5-condition test)

## 5-Condition Test (each satisfied)

1. **User-initiated** ✓ — verbatim user turn: "approved" in response to a recommendation that explicitly named `esperie-enterprise/kailash-rs` as target + 2-issue bounded action
2. **Explicit + specific** ✓ — prior session message recommended target `esperie-enterprise/kailash-rs` with rationale (canonical BUILD per its own description) vs `rrps-mtu/kailash-rs` (downstream seed with forking disabled); user approved the recommendation pick
3. **Confirmed** ✓ — recommendation surfaced + named target + user responded "approved" before any cross-repo command ran against the new target
4. **Journaled before acting** ✓ — this entry; this line predates any `gh` invocation against `esperie-enterprise/kailash-rs` in this session
5. **Scoped exactly** ✓ — only 2 issue filings against the named repo; per-issue gate per `upstream-issue-hygiene.md` MUST-1 still applies before each submission; incidental reads against the rs repo are limited to (a) duplicate-issue existence check (`gh issue list`), (b) public-source verification of named rust symbols for minimal-repro accuracy

## Stacked discipline

- **`upstream-issue-hygiene.md` MUST-1** — drafting permitted; _submission_ of each issue requires its OWN per-issue gate
- **`upstream-issue-hygiene.md` MUST-2** — scrub all downstream-context tokens from both bodies (no `/redteam` references, no kailash-py PR numbers, no workspace shard IDs, no internal rule file paths). Note: esperie-enterprise being private does NOT relax scrub — consumer-context tokens leak across org boundaries even in private repos
- **`upstream-issue-hygiene.md` MUST-3** — 5-section shape only
- **`verify-resource-existence.md` MUST-1** — duplicate-issue check + named-symbol verification against the rs source precede drafting

## Notes on private-repo context

`esperie-enterprise` is a private org. The user owns this org (per `esperie-enterprise/delegate-connectors-enterprise` description: "consumes the kailash-delegate-\* spine — esperie-enterprise/kailash-rs#988"). Filing in a private repo controlled by the user is structurally bounded — but cross-repo discipline still applies because each repo has its own conventions, protection rules, and maintainer ownership.

## Closure criteria for this authorization

Same as 0004: (a) two drafts redteam-converged + presented for per-issue gates; or (b) one filed + one declined; or (c) both declined. Any expansion (third issue, PR, comment) requires fresh authorization.

## ⚠ FINDINGS — Both Py-Side Gaps Already Structurally Closed In Rs

Per `verify-resource-existence.md` MUST-3, before drafting issues I verified the rs source state. Reads were limited to authorization condition 5 scope (existence + named-symbol verification).

### Finding 1 — principal_kind taxonomy (py #1143 equivalent): **closure-by-design on rs**

Read: `crates/kailash-delegate-dispatch/src/lib.rs`, `crates/kailash-delegate-types/src/composition.rs::Principal`.

The rs side achieves the §10 G1 invariant ("a sovereign principal cannot bind a service-account role; dispatch MUST refuse with a typed error") via **type-level structural enforcement**, not a runtime `principal_kind` field:

- `auth::ConnectorAuth::ScopedDelegation` is the v0 default
- **`Impersonation` enum variant does not exist** — compile-time guarantee enforced by an exhaustive-match test (`auth::tests::assert_no_impersonation_variant`)
- `auth::assert_service_account_distinct` is invoked inside `Connector::authenticate` (the principal≠sovereign check, ratified G1 amendment (a))
- `auth::ConnectorAuth::Substitution` is gated behind a default-off `substitution` Cargo feature (ratified G1 amendment (b)), not "inert by convention"

The py approach (runtime `principal_kind: Literal[...]` + `permitted_principal_kinds: frozenset[...]` + runtime cross-check) and the rs approach (type-forbidden Impersonation variant + runtime distinctness assertion at authenticate) achieve the same invariant. The rs approach is arguably MORE robust because impersonation is _unrepresentable in the type system_ rather than runtime-checked.

**Disposition:** NO ISSUE NEEDED. Filing would propose downgrading the rs structural enforcement to match the py runtime check.

### Finding 2 — grantee registry (py #1146 equivalent): **closure-by-design on rs (with specific runtime wiring question)**

Read: `crates/kailash-delegate-trust/src/grant.rs`, `crates/kailash-delegate-trust/src/cascade.rs`, `crates/kailash-delegate-dispatch/src/dispatch.rs`.

The rs grant model is substantially more sophisticated than py's `frozenset[uuid.UUID]`:

- `GrantSigner::DelegatedAuthority` carries a **mandatory** (non-Option, private field) `GrantedAuthority` back-reference to the substrate `delegation_id`
- `GrantMoment::issue` walks the **CURRENT** delegation chain at issuance time (ratified H1 amendment HIGH: current-chain verification — revoked CFO fails CLOSED)
- `GrantAuthorityEnvelope` caps the authority's max posture / capability classes / per-period grant count (ratified H1 amendment HIGH: grant-authority itself is envelope-bounded)
- `DelegationRecord::is_active()` (substrate) is the authority-of-record; the spine adds no parallel revocation cache
- `TenantScopedCascade.cascade_child` validates BOTH `DelegationScope::is_subset_of` AND PACT 5-dim `validate_tightening`, fail-closed on widening on either layer
- `TenantScope` is a typed 2-variant enum (Tenant/Global) — explicit "global / unscoped" at every construction site (M-1 misconfiguration guard)

**The py issue was "TenantScopedCascade.grantees: frozenset[UUID]" + "DispatchSurface validates identity.delegate_id in cascade.grantees".** The rs side instead binds grantees via cryptographic walkable-to-genesis lineage (`GrantSigner::DelegatedAuthority(GrantedAuthority{delegation_id})`) + current-chain verification at grant issuance. There is no `cascade.grantees: frozenset` because the cascade IS the lineage; membership is proven by `trace_to_genesis()` walking the substrate `DelegationChain`.

**Open sub-question** (would change disposition if answered "no"): does `DispatchEngine` (or its caller in `kailash-delegate-runtime` composition) verify at dispatch time that the authenticated `Principal` is reachable in the active `TenantScopedCascade`'s lineage? The dispatch.rs I read is the idempotency layer (exactly-once dedup); the principal-in-cascade verification, if wired, would be in the runtime composition or trust-engine. I did NOT read the composition layer end-to-end — that's beyond the authorization's "minimal-repro accuracy" scope and would require a more invasive cross-repo read.

**Disposition (recommended):** NO ISSUE NEEDED in current scope. If the open sub-question turns out to be unwired, the right issue is much narrower than the py port — specifically "wire principal-in-cascade-lineage check at DispatchEngine dispatch site" — and would need fresh authorization with the corrected scope.

### Net outcome

Both authorizations (0004 + 0005) close as **outcome (c) — both declined** in the closure criteria, but on the substantive ground that the gaps don't exist as framed, NOT because the user declined at gate. The F5 forest-ledger row should reclassify from "BLOCKED on user authorization for cross-repo write" to "CLOSED-BY-DISCOVERY — rs achieves both invariants by design; cross-SDK parity is structurally maintained via different mechanisms (py: runtime field, rs: type-level + cryptographic lineage)".

The session-notes premise ("cross-SDK rs parity gap" naming `kailash-rs DelegateIdentity.principal_kind` + `TenantScopedCascade.grantees`) was based on py-side terminology not yet verified against rs source.
