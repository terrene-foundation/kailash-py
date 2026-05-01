---
name: migration-scaffold
description: "Author a new numbered DataFlow migration. Use when writing an up/down migration, scaffolding a schema change, or reviewing a migration for identifier-safety and force_downgrade compliance."
---

# DataFlow Migration Scaffold

Copy-pasteable starting point for authoring a numbered DataFlow migration that complies with `rules/schema-migration.md`, `rules/dataflow-identifier-safety.md`, and the `force_downgrade` destructive-ops contract.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-migrations-quick`](dataflow-migrations-quick.md), [`dataflow-enterprise-migrations`](dataflow-enterprise-migrations.md)
> Related Subagents: `dataflow-specialist` (destructive / high-risk migrations), `testing-specialist` (Tier 2 regression tests)
> Template: `scripts/migrate.py` (Python starter; the language variant for your SDK supplies the equivalent).

## When to Use

- Adding / removing / renaming columns that `@db.model` auto-migrate cannot express safely.
- Data backfills (per `rules/schema-migration.md` MUST Rule 2, backfills are migrations).
- Schema operations that touch dynamic identifiers (tenant prefixes, dialect-aware index names).
- Any DDL that needs a reviewable, reversible, numbered file.

## File Naming Convention

Migrations live in `migrations/NNN_description.py` relative to the owning package / service root. The convention is strict — the loader discovers files by prefix and refuses to run an untracked one.

```
migrations/
  0001_initial_schema.py
  0002_add_user_email_index.py
  0003_add_user_classification_default.py
  0004_backfill_signup_source.py
  0005_drop_archived_events.py       # destructive; see § Destructive Downgrades
```

MUST:

- Zero-padded 4-digit prefix (`0042_`, not `42_`).
- Lowercase `snake_case` description — one verb + the target (`add_column`, `backfill_signup`, `drop_table`).
- One migration per file.

MUST NOT:

- Edit a migration after it lands on a shared branch. Corrections ship as a NEW higher-numbered migration (`rules/schema-migration.md` MUST Rule 4).

## Up / Down Structure

Every migration MUST define both `upgrade(conn, dialect)` and `downgrade(conn, dialect, *, force_downgrade=False)` (Python) or the language-equivalent signature. An `upgrade` without a matching reversible `downgrade` is BLOCKED — see `rules/schema-migration.md` MUST Rule 3.

The Python starter template lives at `scripts/migrate.py`. Copy it to `migrations/NNN_your_change.py` and fill in the three marked sections:

1. `MIGRATION_ID` / `DESCRIPTION` — metadata the loader reads.
2. `upgrade()` — forward DDL / backfill.
3. `downgrade()` — reverse DDL / data restoration.

## Identifier Quoting — Non-Negotiable

Per `rules/dataflow-identifier-safety.md` MUST Rule 1, every dynamic identifier interpolated into DDL MUST route through the dialect helper's `quote_identifier()` method. The helper validates, length-checks, and quotes — it refuses invalid input, it does NOT escape it.

```python
# DO — quote every identifier
from dataflow.adapters.dialect import DialectManager
from dataflow.adapters.exceptions import InvalidIdentifierError  # for Tier 2 regression tests

dialect = DialectManager.get_dialect(database_type)
table = dialect.quote_identifier("users")
column = dialect.quote_identifier("signup_source")
index = dialect.quote_identifier(f"idx_{table_name}_signup_source")
await conn.execute(f"CREATE INDEX {index} ON {table} ({column})")

# DO NOT — raw f-string interpolation
await conn.execute(f"CREATE INDEX idx_{table_name}_signup_source ON {table_name} (signup_source)")
```

**BLOCKED rationalizations:**

- "The identifier is hardcoded, interpolation is safe"
- "This value comes from a trusted source"
- "Quoting is cosmetic here"

Even hardcoded identifier lists MUST validate — a future refactor that reads the list from config silently re-opens the injection vector if the validation call was never there (`rules/dataflow-identifier-safety.md` MUST Rule 5).

## Destructive Downgrades — `force_downgrade=True`

Any `downgrade()` that drops data (DROP TABLE, DROP COLUMN, DELETE without preserved restore path) MUST:

1. Default to refusing the operation.
2. Require an explicit `force_downgrade=True` keyword argument from the caller.
3. Raise `DowngradeRefusedError` (or the dialect-equivalent typed error) if the flag is missing.
4. Include a `DESTRUCTIVE = True` module-level constant so the migration runner can gate it behind an extra confirmation prompt.

This is the orchestrator-layer sibling of `rules/dataflow-identifier-safety.md` MUST Rule 4's `force_drop=True` pattern (which sits at the DDL-primitive layer). Same discipline at both layers: the flag is the last human gate before irreversible data loss.

```python
# DO — destructive downgrade refuses by default
DESTRUCTIVE = True

async def downgrade(conn, dialect, *, force_downgrade: bool = False):
    if not force_downgrade:
        raise DowngradeRefusedError(
            "migration 0005 downgrade drops archived_events and is "
            "irreversible — pass force_downgrade=True to acknowledge data loss"
        )
    table = dialect.quote_identifier("archived_events")
    await conn.execute(f"DROP TABLE {table}")

# DO NOT — silent destructive downgrade
async def downgrade(conn, dialect):
    await conn.execute("DROP TABLE archived_events")  # no gate, no safety
```

**BLOCKED rationalizations:**

- "The operator knows the migration is destructive, they wouldn't call downgrade by accident"
- "force_downgrade is ceremony, the migration framework already logs the operation"
- "The table is empty in staging, the flag is overkill"

## Regression Test Requirement

Every new DDL path ships with a Tier 2 integration test in the same commit (`rules/dataflow-identifier-safety.md` MUST Rule 3 + `rules/testing.md` Tier 2). Tier 1 unit tests mocking the dialect helper are NOT sufficient — they prove the helper validates in isolation, not that the migration's call sites actually invoke it.

The test MUST:

- Run against real PostgreSQL / MySQL (per `rules/schema-migration.md` MUST Rule 5; `:memory:` SQLite is NOT acceptable for migration validation).
- Assert the forward migration produces the expected schema shape.
- Assert the reverse migration restores the prior shape.
- Assert standard injection payloads are rejected by `dialect.quote_identifier`.

## Example 1 — Add Column With Classified Default

Scenario: add an `audit_channel` column to `user_events` with a classified default value. The classification metadata comes from the model's `@classify` decorator — the migration only seeds a default so the NOT NULL add is safe on existing rows.

**`migrations/0043_add_user_events_audit_channel.py`**

```python
"""Add audit_channel column to user_events with classified default."""

from dataflow.adapters.dialect import DialectManager
from dataflow.adapters.exceptions import InvalidIdentifierError  # for Tier 2 regression tests

MIGRATION_ID = "0043_add_user_events_audit_channel"
DESCRIPTION = "Add NOT NULL audit_channel column to user_events."
DESTRUCTIVE = False


async def upgrade(conn, database_type: str) -> None:
    dialect = DialectManager.get_dialect(database_type)
    table = dialect.quote_identifier("user_events")
    column = dialect.quote_identifier("audit_channel")
    # Step 1 — add nullable column with safe default for existing rows.
    await conn.execute(
        f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT 'internal'"
    )
    # Step 2 — backfill then enforce NOT NULL.
    await conn.execute(
        f"UPDATE {table} SET {column} = 'internal' WHERE {column} IS NULL"
    )
    await conn.execute(
        f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"
    )


async def downgrade(conn, database_type: str, *, force_downgrade: bool = False) -> None:
    # Dropping the column is destructive (loses the classification default per row).
    # DowngradeRefusedError is defined in `scripts/migrate.py` as a
    # `class DowngradeRefusedError(RuntimeError)` — each migration copies the
    # definition or imports it from the project's shared migration helpers.
    if not force_downgrade:
        raise DowngradeRefusedError(
            f"{MIGRATION_ID} downgrade drops user_events.audit_channel and is "
            f"irreversible — pass force_downgrade=True to acknowledge data loss"
        )
    dialect = DialectManager.get_dialect(database_type)
    table = dialect.quote_identifier("user_events")
    column = dialect.quote_identifier("audit_channel")
    await conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
```

**`tests/integration/migrations/test_0043_add_user_events_audit_channel.py`**

```python
import pytest
from dataflow.adapters.dialect import DialectManager
from dataflow.adapters.exceptions import InvalidIdentifierError
from migrations import _0043_add_user_events_audit_channel as migration


@pytest.mark.integration
async def test_upgrade_adds_not_null_column_with_default(pg_conn, pg_dialect):
    # Precondition: user_events exists without audit_channel.
    await migration.upgrade(pg_conn, "postgresql")
    columns = await pg_conn.fetch(
        "SELECT column_name, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'user_events' AND column_name = 'audit_channel'"
    )
    assert columns[0]["is_nullable"] == "NO"
    assert "internal" in columns[0]["column_default"]


@pytest.mark.integration
async def test_downgrade_without_force_refuses(pg_conn):
    await migration.upgrade(pg_conn, "postgresql")
    with pytest.raises(migration.DowngradeRefusedError, match="force_downgrade=True"):
        await migration.downgrade(pg_conn, "postgresql")


@pytest.mark.integration
async def test_downgrade_with_force_drops_column(pg_conn):
    await migration.upgrade(pg_conn, "postgresql")
    await migration.downgrade(pg_conn, "postgresql", force_downgrade=True)
    columns = await pg_conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'user_events' AND column_name = 'audit_channel'"
    )
    assert columns == []


@pytest.mark.regression
def test_dialect_rejects_injection_payloads():
    dialect = DialectManager.get_dialect("postgresql")
    with pytest.raises(InvalidIdentifierError):
        dialect.quote_identifier('user_events"; DROP TABLE users; --')
    with pytest.raises(InvalidIdentifierError):
        dialect.quote_identifier("audit channel")  # space rejected
```

## Example 2 — Destructive Downgrade

Scenario: migration `0005_drop_archived_events` drops an archive table whose data is preserved out-of-band (S3 cold storage). The upgrade is destructive by design; the downgrade recreates the table structure but cannot restore row data — operators MUST acknowledge with `force_downgrade=True`.

**`migrations/0005_drop_archived_events.py`**

```python
"""Drop archived_events table — data already preserved in cold storage."""

from dataflow.adapters.dialect import DialectManager
from dataflow.adapters.exceptions import InvalidIdentifierError  # for Tier 2 regression tests

MIGRATION_ID = "0005_drop_archived_events"
DESCRIPTION = "Drop archived_events after cold-storage export."
DESTRUCTIVE = True


async def upgrade(conn, database_type: str, *, force_downgrade: bool = False) -> None:
    # force_downgrade is reused here for symmetry: destructive upgrades
    # also refuse unless the operator acknowledges. The migration runner
    # injects force_downgrade=True when the CLI is invoked with --force.
    if not force_downgrade:
        raise DowngradeRefusedError(
            f"{MIGRATION_ID} upgrade drops archived_events and is irreversible — "
            f"pass force_downgrade=True to acknowledge"
        )
    dialect = DialectManager.get_dialect(database_type)
    table = dialect.quote_identifier("archived_events")
    await conn.execute(f"DROP TABLE {table}")


async def downgrade(conn, database_type: str, *, force_downgrade: bool = False) -> None:
    # Recreates the shape but does NOT restore rows. Operators MUST acknowledge
    # the partial restore before the reverse runs.
    if not force_downgrade:
        raise DowngradeRefusedError(
            f"{MIGRATION_ID} downgrade recreates archived_events shape only — "
            f"rows are not restored; pass force_downgrade=True to acknowledge"
        )
    dialect = DialectManager.get_dialect(database_type)
    table = dialect.quote_identifier("archived_events")
    ts_col = dialect.quote_identifier("event_ts")
    await conn.execute(
        f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, {ts_col} TIMESTAMP NOT NULL)"
    )
```

## Checklist Before Committing A Migration

- [ ] File named `migrations/NNNN_description.py` with zero-padded prefix.
- [ ] `upgrade()` present.
- [ ] `downgrade()` present and reversible, OR `DESTRUCTIVE = True` with `force_downgrade` gate.
- [ ] Every dynamic identifier routed through `dialect.quote_identifier()`.
- [ ] No raw `f"..."` DDL interpolation anywhere in the file.
- [ ] Tier 2 integration test against real PostgreSQL / MySQL lives in `tests/integration/migrations/`.
- [ ] Regression test asserts `quote_identifier` rejects at least 3 standard injection payloads.
- [ ] Commit message explains **why** the schema change is needed (per `rules/git.md`).

## Related Rules

- `rules/schema-migration.md` — numbered migration contract, up/down reversibility, append-only files, real-dialect test requirement, § 7 force_downgrade orchestrator-layer gate.
- `rules/dataflow-identifier-safety.md` — `quote_identifier` mandatory on every DDL path + `force_drop=True` contract for DROP statements at the DDL-primitive layer.
- `rules/testing.md` Tier 2 — real infrastructure for integration tests.
- `rules/zero-tolerance.md` Rule 4 — if the dialect helper is missing a capability, fix the helper; do not inline raw DDL around it.
- `rules/framework-first.md` — raw SQL is BLOCKED in application code; migrations are the sanctioned DDL surface.

## Keywords for Auto-Trigger

<!-- Trigger Keywords: migration scaffold, new migration, numbered migration, up down migration, force_downgrade, quote_identifier migration, ALTER TABLE migration, DROP COLUMN migration, migration template, DataFlow migration authoring -->
