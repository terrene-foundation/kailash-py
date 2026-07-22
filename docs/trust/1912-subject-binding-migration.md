# #1912 Migration Guide — Subject-Binding + Chain-State Signing (Wave 3, fail-closed)

Issue #1912 hardened the trust plane against a store-writer (an adversary with
write access to persisted trust chains). It landed in three waves; **Wave 3 (A1)
is a breaking change** to `TrustOperations.verify()`. This guide is the upgrade
path for any deployment that persists trust chains.

## What changed

| Wave | Defense                                                                                                                                                                             | verify() behavior after Wave 3                                         |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| 1    | Capabilities bind the holder subject (`v1-subject-bound`) — a transplanted capability no longer verifies on another chain.                                                          | A **legacy** (pre-#1912, un-subject-bound) capability is **REJECTED**. |
| 2    | One genesis-authority `chain_state_signature` over the chain-state pre-image detects whole-capability-set deletion (MED-1) and constraint/`REASONING_REQUIRED` suppression (MED-2). | A chain with **no chain-state signature** is **REJECTED**.             |

Before Wave 3, both cases were _accepted with a WARN_ (secure-default, verify-if-
present). Wave 3 flips them to **fail-closed** so the installed-base residual —
and the "strip the signature to downgrade a tampered chain to legacy" bypass —
is closed.

## Who is affected

Any deployment whose trust store holds chains **established before this release**.
Those chains carry legacy capabilities and no chain-state signature, so under the
new default they are rejected until re-signed.

Chains established _after_ upgrading are already at the Wave-3 posture
(`establish` / `delegate` mint `v1-subject-bound` caps and issue a chain-state
signature) and need no migration.

## The two migration-window opt-outs

`TrustOperations` accepts two independent keyword flags, each defaulting to
`False` (fail-closed). Each gates a distinct security dimension — a deployment
MAY enforce one while still migrating the other:

```python
ops = TrustOperations(
    authority_registry=registry,
    key_manager=key_manager,
    trust_store=store,
    allow_unbound_legacy_capabilities=True,  # Wave-1 axis: accept legacy caps
    allow_unsigned_chain_state=True,          # Wave-2 axis: accept unsigned chains
)
```

Each opt-out that is `True` emits ONE loud WARN naming the OFF protection. They
are for the **migration window only** — leave them `False` in steady state.

## Upgrade path (recommended)

1. **Deploy with both opt-outs ON.** No existing agent breaks; verify still
   accepts legacy/unsigned chains, loudly warning that the defenses are OFF.

   ```python
   ops = TrustOperations(
       authority_registry=registry, key_manager=key_manager, trust_store=store,
       allow_unbound_legacy_capabilities=True, allow_unsigned_chain_state=True,
   )
   ```

2. **Dry-run the migration** to see what will change and what cannot be migrated
   locally, without writing anything:

   ```python
   from kailash.trust.migrations.subject_binding_1912 import SubjectBindingMigration

   migration = SubjectBindingMigration(registry, key_manager, store)
   report = await migration.migrate(dry_run=True)
   print(report.to_dict())
   ```

3. **Run the migration from a TRUSTED store state.** Promoting a legacy
   capability requires an explicit `trust_store_placement=True` acknowledgment.
   A legacy capability carries no holder subject in its signed bytes (the Wave-1
   vulnerability), so the migration cannot cryptographically verify a legacy
   cap's original holder — it binds the cap to the chain it _currently_ sits in.
   A store-writer who transplanted a genuine legacy capability into another
   chain _before_ the migration would otherwise have that transplant blessed
   into a valid v1 cap. Set `trust_store_placement=True` **only** when running
   against a trusted store state — a snapshot taken before the store was exposed
   to untrusted writers, or a locked-down maintenance window. (Post-migration,
   every cap is `v1-subject-bound`, so the runtime transplant defense is fully in
   force and any _future_ transplant is rejected by `verify()`.)

   ```python
   report = await migration.migrate(trust_store_placement=True)
   assert report.fully_migrated, report.unmigratable  # nothing left un-migrated
   ```

   With `trust_store_placement=False` (the default) every write is _reported_ as
   requiring the acknowledgment and nothing is re-signed — a safe default in the
   shape of `force_drop` / `force_downgrade`. The acknowledgment covers **both**
   legacy-capability promotion **and** fresh chain-state signing (adding a
   signature where a chain has none): the latter re-signs over the chain's
   current, unverifiable constraint envelope, so a store-writer who stripped a
   constraint _and_ the old signature must not have it silently re-blessed. A
   chain that already carries a _valid_ chain-state signature is left untouched,
   so idempotent re-runs need no acknowledgment.

   The migration is **idempotent** (re-running changes nothing once a chain is
   current), **failure-atomic** (a mid-apply error restores every changed chain
   to its pre-migration state), and **reversible** — keep the returned `report`
   and call `await migration.rollback(report)` for a byte-exact restore.

4. **Handle un-migratable items.** `report.unmigratable` lists anything the local
   genesis key could not re-sign — never silently dropped:

   - **External-attester capability** (`kind == "capability"`): the capability was
     attested by a _different_ authority. The local genesis key cannot re-sign
     for it; the owning attester must re-sign it (or the capability must be
     re-issued). Until then, verifying that chain requires
     `allow_unbound_legacy_capabilities=True`.
   - **Un-resolvable / key-absent chain** (`kind == "chain"`): the chain's genesis
     authority could not be resolved, or its signing key is absent from the local
     `TrustKeyManager`. Register the key (or resolve the authority) and re-run.

5. **Enforce.** Once `report.fully_migrated` is `True` (or the residual
   un-migratable items are accepted and tracked), remove BOTH opt-outs so
   `TrustOperations` is constructed fail-closed:

   ```python
   ops = TrustOperations(authority_registry=registry, key_manager=key_manager,
                         trust_store=store)  # both flags default False → enforced
   ```

## If you do not migrate

A deployment that upgrades **without** migrating and **without** setting the
opt-outs will have its legacy chains **rejected** by `verify()`. This is
intentional fail-closed behavior — a rejected verify denies the action rather
than authorizing a transplantable/unsigned chain. Set the opt-outs to keep
running while you migrate.

## Report fields

`MigrationReport` (`.to_dict()` for a serializable summary):

| Field                          | Meaning                                            |
| ------------------------------ | -------------------------------------------------- |
| `total_chains`                 | chains enumerated                                  |
| `migrated_chains`              | chains changed (or would-change under `dry_run`)   |
| `promoted_capabilities`        | legacy caps promoted to `v1-subject-bound`         |
| `added_chain_state_signatures` | chains that gained a chain-state signature         |
| `already_current_chains`       | chains already at the Wave-3 posture (no change)   |
| `unmigratable`                 | items the local key could not re-sign (see step 4) |
| `fully_migrated`               | `True` iff `unmigratable` is empty                 |

## Cross-SDK note

The capability and chain-state signatures are deployment-local (they bind random
per-deployment UUIDs signed by the deployment's own key), so this fix ships
independently per SDK. The canonical pre-image _encodings_ are pinned as cross-
SDK tripwires; a sibling SDK must land the equivalent subject-binding + chain-
state fix before its trust plane interoperates on these artifacts.
