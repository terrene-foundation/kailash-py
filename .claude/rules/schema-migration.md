---
paths:
  - "**/migrations/**"
  - "**/db/**"
  - "**/*.sql"
  - "**/models.py"
  - "**/schema.py"
  - "**/dataflow/**"
  - "**/*.py"
  - "**/*.rb"
---

# Schema & Data Migration Rules

The schema is the contract between code and data. Every change to that contract MUST go through a numbered, reviewable, reversible migration. Direct DDL and ad-hoc data fixes are how schemas drift from code, and how production silently breaks.

## MUST Rules

### 1. All Schema Changes Through Numbered Migrations

`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `CREATE INDEX`, and any other DDL MUST live in a numbered migration file managed by the project's migration framework (DataFlow auto-migrate, Alembic, ActiveRecord, sqlx, etc.). DDL string literals in **application code** are BLOCKED outside of migration files.

**Scope clarification:** "Application code" means services, controllers, handlers, models, and rake/management tasks. DDL is permitted in: (a) numbered migration files, (b) the dialect helper layer of the Kailash SDK source tree itself (`src/kailash/db/…` patterns like `dialect.blob_type()` and bootstrap table-creation helpers — BUILD repos only, not downstream USE projects), and (c) test fixtures that create and tear down test schemas.

```python
# DO — DataFlow @db.model drives auto-migration; the schema lives in code
@db.model
class User:
    id: int = field(primary_key=True)
    email: str

# DO — explicit numbered migration when not using auto-migrate
# migrations/0042_add_user_email_index.py

# DO NOT — DDL string in application code
await conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
```

**Why:** DDL outside the migration framework runs once on whichever environment the agent happens to touch and never on the others. The schemas drift, the next deploy fails on the un-migrated environment, and the failure looks like a code bug because the migration was never recorded.

### 2. Data Fixes Are Migrations, Not One-Off SQL

If runtime data needs to be corrected (backfills, reclassifications, deduplication), the fix MUST be a numbered migration with the same review and rollback discipline as schema changes. Ad-hoc `INSERT` / `UPDATE` / `DELETE` statements run against production are BLOCKED.

```python
# DO — backfill as a numbered migration
# migrations/0043_backfill_user_signup_source.py
def upgrade(conn):
    conn.execute("UPDATE users SET signup_source = 'organic' WHERE signup_source IS NULL")

def downgrade(conn):
    conn.execute("UPDATE users SET signup_source = NULL WHERE signup_source = 'organic'")

# DO NOT — hotfix SQL in a notebook, ticket comment, or one-off script
# psql> UPDATE users SET signup_source = 'organic' WHERE signup_source IS NULL;
```

**Why:** A hotfix run by hand has no record, no rollback, and no audit trail. The next environment never gets the same fix, and six months later the team cannot reconstruct why production rows differ from staging.

### 3. Every Migration Has a Reversible Path

`upgrade()` MUST have a corresponding `downgrade()` that returns the schema to its prior state. Migrations marked irreversible (e.g., destructive column drops with no preserved data) MUST be flagged in code and require explicit human acknowledgement before running.

```python
# DO
def upgrade(conn):
    conn.execute("ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'free'")

def downgrade(conn):
    conn.execute("ALTER TABLE users DROP COLUMN tier")

# DO NOT — silent irreversibility
def upgrade(conn):
    conn.execute("DROP TABLE archived_events")  # data gone, no path back, no warning
def downgrade(conn):
    pass  # placeholder
```

**Why:** Migrations are deployed, and deployed code rolls back. Without `downgrade()`, a failed deploy cannot return to a known-good schema and the system is stuck mid-migration with neither old nor new code able to run.

### 4. Migration Files Are Append-Only

Once a migration file is committed to a shared branch, it MUST NOT be edited. Mistakes are corrected by adding a new migration that reverses or supersedes the prior one.

**Why:** Editing a committed migration file means environments that already ran it have a different schema than environments that run the edited version, and the framework's "this migration ran" tracking lies. The drift is undetectable until something breaks.

### 5. Test the Migration on Real Schema, Not :memory:

Migration tests MUST run against a copy of the production schema dialect (PostgreSQL → PostgreSQL test instance, MySQL → MySQL test instance). `sqlite:///:memory:` is acceptable for unit tests but NOT for migration validation.

**Why:** PostgreSQL and SQLite accept different DDL — `BLOB` vs `BYTEA`, `AUTOINCREMENT` vs `SERIAL`, `IF NOT EXISTS` quirks. A migration that passes against SQLite can syntax-error against production PostgreSQL on first deploy.

### 6. Production Schema Sync Is a Deploy Gate

`/deploy` MUST verify the production migration head matches the code's expected migration head before publishing the new bundle. If they diverge, deploy STOPS until the migrations are reconciled. This check MUST be declared as a gate in `deploy/deployment-config.md` (see `deploy-hygiene.md` § "Pre-deploy gates run before every deploy").

**Why:** Code that assumes a column exists, deployed against a database where the column does not exist yet, throws on first request. The deploy command returns 0; the application is broken; users see errors. Same failure class as `deploy-hygiene.md` § "Verify deploy state before stacking more production commits".

## MUST NOT

- **No "I'll write the migration later" data fixes.** If you change runtime data, you write the migration in the same commit. Period.

**Why:** "Later" means a different session, a different agent, and a high probability of "later" never arriving — the production environment stays patched-by-hand and the staging environment doesn't match.

- **No raw SQL in application code as a workaround for missing schema.** If the schema doesn't have the column you need, add a migration. Do not coerce the data with a runtime SQL hack.

**Why:** Runtime SQL hacks calcify into "the way it works" and the missing schema column never gets added. Two years later, every read of that table has a CASE WHEN around the missing column.

- **No `DROP` of a table or column without a preserved-data plan.** Either back the data up to a parking table within the same migration, or explicitly mark the migration as destructive and require human acknowledgement.

**Why:** Dropped data is unrecoverable, and a one-line migration mistake during refactor has wiped years of customer history more than once.

- **No bypassing the migration framework via `psql` / `mysql` / `sqlite3` shells against production.** All DDL goes through the framework, every time, no exceptions for "just one quick fix".

**Why:** The framework's tracking table is the only ground truth for which migrations have run. Manual DDL leaves the table out of sync, and the next automated migration either re-runs or skips changes incorrectly.

## Relationship to Other Rules

- `rules/infrastructure-sql.md` covers query safety (parameterization, dialect portability) inside both application code and migrations.
- `rules/zero-tolerance.md` Rule 4 (no SDK workarounds) applies — if DataFlow's auto-migration is missing a feature, fix DataFlow, do not write raw DDL around it.
- `rules/framework-first.md` — DataFlow's `@db.model` is the highest-abstraction migration path for Kailash apps. Drop to a primitive migration framework only when the model layer cannot express the change.
