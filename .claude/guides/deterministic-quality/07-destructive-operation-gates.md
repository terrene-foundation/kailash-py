# Destructive Operation Gates

Patterns that require explicit confirmation before irreversible actions. Defense against typos, scope mistakes, and "I thought that table was empty."

## Principles

1. **Destructive operations require a flag** — `force_drop=True`, `confirm_delete_all=True`
2. **The default is to refuse** — calling `drop_model("users")` without the flag raises, not drops
3. **Migrations default to dry-run** — `migrate()` shows SQL without executing; `migrate(execute=True)` runs it
4. **Bulk deletion requires a filter** — `delete_all()` does not exist; `delete(filter=...)` with mandatory filter does

## Patterns

### 1. `force_drop=True` on All DROP Operations

**Status**: Already mandated in `rules/dataflow-identifier-safety.md` § 4. Verified in kailash-py source.

**The pattern**: Every DROP-class operation (table, schema, index, column) MUST require an explicit `force_drop=True` flag. The default MUST be to refuse.

```python
# DO — explicit confirmation required
async def drop_model(self, model_name: str, *, force_drop: bool = False) -> None:
    if not force_drop:
        raise DropRefusedError(
            f"drop_model('{model_name}') refused — pass force_drop=True "
            f"to acknowledge data loss is irreversible"
        )
    table = self._dialect.quote_identifier(model_name)
    await self._conn.execute(f"DROP TABLE IF EXISTS {table}")

# DO NOT — drop by default
async def drop_model(self, model_name: str) -> None:
    await self._conn.execute(f"DROP TABLE IF EXISTS {model_name}")
```

```rust
// Rust equivalent — type-level gate
pub struct DropConfirmation;

impl DataFlow {
    /// Requires explicit `DropConfirmation` token — cannot be constructed accidentally
    pub async fn drop_model(
        &self,
        model: &str,
        _confirm: DropConfirmation,
    ) -> Result<(), DataFlowError> {
        // ...
    }
}

// Usage: db.drop_model("users", DropConfirmation).await?;
// The DropConfirmation type is the "flag" — it's a conscious import
```

**Industry precedent**: AWS CLI requires `--force` on `s3 rb`. Terraform requires `plan` + `apply`. Kubernetes requires `--force --grace-period=0` (two flags, not one) for immediate pod termination.

### 2. No `delete_all()` — Mandatory Filter on Bulk Deletion

**Status**: NOT ENFORCED. `express.delete()` can accept empty filters.

**The problem**: `await db.express.delete("User")` — deletes ALL users. Was the developer testing? Was it a typo? Was it intentional? No way to tell from the code.

**The fix**: Bulk deletion requires either a filter or an explicit "I mean all" flag.

```python
# DO — mandatory filter
async def delete(self, model: str, *, filter: dict) -> DeleteResult:
    """Delete matching rows. Filter is mandatory."""
    if not filter:
        raise FilterRequiredError(
            f"delete('{model}') requires a non-empty filter. "
            f"To delete all rows, use admin.purge('{model}', confirm_purge=True)"
        )
    return await self._engine.delete(model, filter)

# Separate admin method for full purge
async def purge(self, model: str, *, confirm_purge: bool = False) -> PurgeResult:
    if not confirm_purge:
        raise PurgeRefusedError(
            f"purge('{model}') refused — pass confirm_purge=True"
        )
    return await self._engine.delete_all(model)

# DO NOT — unfiltered delete allowed
async def delete(self, model: str, filter: dict = None) -> DeleteResult:
    return await self._engine.delete(model, filter or {})
    # filter=None or filter={} deletes everything silently
```

**Industry precedent**: Django's `QuerySet.delete()` requires `.filter()` first — `User.objects.all().delete()` is intentional (you called `.all()` explicitly). Rails requires `.destroy_all` — a different method name than `.destroy` — making bulk deletion visually distinct.

### 3. Migration Dry-Run by Default

**Status**: NOT IMPLEMENTED. Migrations execute immediately.

**The problem**: `await db.migrate()` applies pending migrations. If a migration has a bug (wrong column type, missing index, bad data backfill), the damage is done before anyone reviews the SQL.

**The fix**: Default to `dry_run=True`, showing the SQL without executing.

```python
# DO — dry run by default
async def migrate(self, *, execute: bool = False) -> MigrationPlan:
    plan = await self._compute_migration_plan()
    if not execute:
        return plan  # contains SQL statements, no execution
    return await self._execute_plan(plan)

# Usage:
plan = await db.migrate()                    # shows SQL, no execution
print(plan.sql)                               # review the SQL
result = await db.migrate(execute=True)       # actually runs it

# DO NOT — execute by default
async def migrate(self) -> MigrationResult:
    plan = await self._compute_migration_plan()
    return await self._execute_plan(plan)     # runs immediately, no review
```

```rust
// Rust equivalent
pub async fn migrate(&self, execute: bool) -> Result<MigrationPlan, MigrationError> {
    let plan = self.compute_plan().await?;
    if !execute {
        return Ok(plan);  // SQL only, no execution
    }
    self.execute_plan(&plan).await
}
```

**Industry precedent**: Alembic supports `--sql` mode. Terraform separates `plan` from `apply`. Flyway has `migrate -dryRun`. Django has `sqlmigrate` (show SQL) separate from `migrate` (execute).

### 4. Idempotency Keys on Write Operations

**Status**: ABSENT. No idempotency enforcement on mutations.

**The problem**: Network retry sends `express.create("Payment", {...})` twice. Two payments are created. The user is charged double.

**The fix**: Require an idempotency key on mutations by default.

```python
# DO — idempotency key required (or explicit opt-out)
async def create(
    self, model: str, data: dict,
    *, idempotency_key: str | None = None,
    allow_duplicate: bool = False,
) -> ModelResult:
    if idempotency_key is None and not allow_duplicate:
        raise IdempotencyRequiredError(
            f"create('{model}') requires an idempotency_key for safe retries. "
            f"Pass allow_duplicate=True if duplicates are intentional."
        )
    # Check if key already processed
    if idempotency_key:
        existing = await self._idempotency_store.get(idempotency_key)
        if existing:
            return existing  # return cached result, don't re-create
    result = await self._engine.create(model, data)
    if idempotency_key:
        await self._idempotency_store.set(idempotency_key, result)
    return result

# DO NOT — no idempotency protection
async def create(self, model: str, data: dict) -> ModelResult:
    return await self._engine.create(model, data)
    # retries create duplicates
```

**Industry precedent**: Stripe requires `Idempotency-Key` header on POST requests. AWS SQS uses `MessageDeduplicationId`. Google Cloud Pub/Sub deduplicates by message ID.

**Scope**: `express.create()`, `express.update()`, `express.delete()` — all mutation operations. Read operations are inherently idempotent.

## Priority Ranking

| Rank | Pattern                            | SDK    | Effort     | Safety impact                           |
| ---- | ---------------------------------- | ------ | ---------- | --------------------------------------- |
| 1    | Mandatory filter on delete         | py, rs | 1 session  | Prevents accidental full-table deletion |
| 2    | Migration dry-run default          | py, rs | 1 session  | Prevents accidental schema damage       |
| 3    | Idempotency keys on mutations      | py, rs | 2 sessions | Prevents duplicate writes on retry      |
| 4    | `force_drop=True` (already exists) | py, rs | —          | Already enforced                        |
