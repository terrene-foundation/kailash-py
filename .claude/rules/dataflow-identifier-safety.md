---
priority: 10
scope: path-scoped
paths:
  - "**/dataflow/**"
  - "**/sql*"
  - "**/dialect*"
  - "**/migrations/**"
---

# DataFlow Identifier Safety Rules


<!-- slot:neutral-body -->

SQL parameter binding works for VALUES, not for identifiers. Column names, table names, index names, and schema names cannot be passed as bound parameters — they MUST be interpolated into the SQL string. That interpolation is an injection vector if the value comes from user input, from a model name, from a tenant prefix, or from any dynamic source.

The fix is mandatory identifier quoting via a dialect helper that BOTH validates the input against a strict allowlist regex AND quotes it in a dialect-appropriate way. The regex-only approach is insufficient because some dialects have reserved words that look valid to a regex but break at execution; the quote-only approach is insufficient because quoted identifiers with escaped quote characters are still an injection vector.

This rule mandates `dialect.quote_identifier()` on every DDL path that touches a dynamic identifier. Violation is a `zero-tolerance.md` Rule 4 failure.

## MUST Rules

### 1. Every Dynamic DDL Identifier Uses `quote_identifier`

Any CREATE TABLE, ALTER TABLE, CREATE INDEX, DROP, or other DDL statement that interpolates a user-influenced identifier MUST route that identifier through `dialect.quote_identifier()` first.

```python
# DO — quoted and validated
from dataflow.adapters.dialect import get_dialect

dialect = get_dialect(database_type)
table = dialect.quote_identifier(table_name)  # raises on invalid input
index = dialect.quote_identifier(f"idx_{table_name}_active")
sql = f"CREATE INDEX {index} ON {table} (active)"
await conn.execute(sql)

# DO NOT — raw interpolation
sql = f"CREATE INDEX idx_{table_name}_active ON {table_name} (active)"
await conn.execute(sql)  # injection via table_name = '"; DROP TABLE users; --'
```

**Why:** User-influenced identifiers have been the primary DDL injection vector in DataFlow incidents — one tenant-prefix bypass nearly dropped a production table before the audit caught it. The quote helper is the single enforcement point.

### 2. `quote_identifier` Contract

Every dialect's `quote_identifier(name: str)` helper MUST:

1. **Validate** the input against a strict allowlist regex. The baseline is `^[a-zA-Z_][a-zA-Z0-9_]*$` — letters, digits, underscores, leading letter. Dialects with stricter rules (e.g., MySQL 4-byte UTF-8 identifiers) apply their own regex on top.
2. **Reject** any input that fails validation with a typed exception whose error message does NOT echo the raw input verbatim (that's a stored XSS / log poisoning vector).
3. **Check length** against the dialect's limit (PostgreSQL 63, MySQL 64, SQLite 128).
4. **Quote** the validated input with the dialect's quote character (`"` for PostgreSQL/SQLite, `` ` `` for MySQL).
5. **Not** attempt to "escape" embedded quote characters — that's the bug. Invalid inputs are rejected, not escaped.

```python
# DO — validate, reject, quote
class PostgresDialect:
    _IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    _MAX_LENGTH = 63

    def quote_identifier(self, name: str) -> str:
        if not isinstance(name, str):
            raise IdentifierError("identifier must be a string")
        if len(name) > self._MAX_LENGTH:
            raise IdentifierError(
                f"identifier exceeds {self._MAX_LENGTH}-char limit "
                f"(len={len(name)}, fingerprint={hash(name) & 0xFFFF:04x})"
            )
        if not self._IDENTIFIER_REGEX.match(name):
            raise IdentifierError(
                f"identifier failed validation "
                f"(fingerprint={hash(name) & 0xFFFF:04x})"
            )
        return f'"{name}"'

# DO NOT — escape embedded quotes
def quote_identifier(self, name: str) -> str:
    escaped = name.replace('"', '""')  # trying to "clean" the input
    return f'"{escaped}"'
# ↑ accepts identifiers that should be rejected, widening the attack surface
```

**Why:** The "reject, don't escape" rule eliminates a whole class of bypass attempts (`name", name2 := '...'`). The error-message fingerprint prevents leaking the attack payload into logs.

### 3. Every New DDL Path Has a Regression Test

When a new DDL path is added, a regression test MUST be added in the same commit that tries the standard injection payloads and asserts they are rejected:

```python
@pytest.mark.regression
def test_create_index_rejects_sql_injection():
    with pytest.raises(IdentifierError):
        dialect.quote_identifier('users"; DROP TABLE customers; --')
    with pytest.raises(IdentifierError):
        dialect.quote_identifier("name WITH DATA")
    with pytest.raises(IdentifierError):
        dialect.quote_identifier("123_starts_with_digit")
```

**Why:** The test proves the validator works against the payloads we know about. Without the test, the next refactor that "fixes" a "bug" in the validator (e.g., loosens the regex to accept UTF-8 names) silently reopens the injection vector.

### 4. DROP Statements Require Explicit Confirmation

DROP TABLE, DROP SCHEMA, DROP INDEX, DROP COLUMN — every DROP MUST require an explicit `force_drop=True` flag on the calling API. The default MUST be to refuse. This is defense against "I thought that table was empty" incidents where the identifier was valid but the intent was wrong.

```python
# DO — explicit confirmation
async def drop_model(self, model_name: str, *, force_drop: bool = False) -> None:
    if not force_drop:
        raise DropRefusedError(
            f"drop_model('{model_name}') refused — pass force_drop=True "
            f"to acknowledge data loss is irreversible"
        )
    table = self._dialect.quote_identifier(model_name)
    await self._conn.execute(f"DROP TABLE {table}")

# DO NOT — drop by default
async def drop_model(self, model_name: str) -> None:
    table = self._dialect.quote_identifier(model_name)
    await self._conn.execute(f"DROP TABLE {table}")
```

**Why:** Dropped data is unrecoverable. The explicit flag is the last human gate before destruction; without it, a typo or a mis-scoped rm-equivalent takes the production table with it.

### 5. Hardcoded Identifier Lists MUST Still Validate

Even when an identifier list is a static Python literal in the source file, every element MUST route through `_validate_identifier()` (or `dialect.quote_identifier()`) at the call site before interpolation into DDL. "The list is hardcoded, so it's safe" is BLOCKED.

```python
# DO — defense-in-depth validation on hardcoded list
from kailash.db.dialect import _validate_identifier

tables_to_drop = ["users", "roles", "permissions"]
for table in tables_to_drop:
    _validate_identifier(table)  # defense-in-depth
    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

# DO NOT — assume hardcoded means safe
tables_to_drop = ["users", "roles", "permissions"]
for table in tables_to_drop:
    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
# ↑ works today; breaks the moment someone makes the list dynamic
# (e.g., reads from config, appends from a function parameter)
```

**BLOCKED rationalizations:**

- "The list is hardcoded so there's no injection vector"
- "Adding validation is overkill for a static list"
- "We'll add validation when the list becomes dynamic"
- "This is an admin-only path, no attacker can reach it"

**Why:** Hardcoded lists become dynamic lists. A future refactor that reads the table list from a config file, or appends a caller-supplied suffix, or loops over model names from a registry, silently re-opens the injection vector with no test signal because the validation call was never there. The validation call is a permanent marker of intent that survives the refactor.

Origin: Red team review of PR #430 (2026-04-12) surfaced this in `src/kailash/nodes/admin/schema_manager.py::_drop_existing_schema` and `_get_table_row_counts` — hardcoded lists without validation. Fixed in commit 803e10e0.

### 6. Primitive-Vs-Orchestrator Layer Distinction For Destructive Operations

Per-DDL primitive callers (rule §4 above: `force_drop=True` + `DropRefusedError`) and multi-DDL orchestrator callers (e.g. `MigrationManager.apply_downgrade`, `ColumnRemovalManager`, `RollbackManager`) MUST use distinct flag names AND distinct refused-exception types. The two MUST NOT be subclasses of each other — they represent different audit trails and downstream callers MUST be able to `try/except` one without catching the other.

```python
# DO — primitive layer: per-DDL DROP
async def drop_model(self, model_name: str, *, force_drop: bool = False) -> None:
    if not force_drop:
        raise DropRefusedError(f"drop_model('{model_name}') refused — pass force_drop=True")
    ...

# DO — orchestrator layer: multi-DDL downgrade sequence
async def apply_downgrade(
    self, target_revision: str, *, force_downgrade: bool = False
) -> None:
    if not force_downgrade:
        raise DowngradeRefusedError(
            f"apply_downgrade('{target_revision}') refused — pass force_downgrade=True "
            f"to acknowledge irreversible multi-step DDL"
        )
    ...

# DO NOT — conflate the two flags / errors inside one helper
async def confirm_destructive(self, *, force: bool = False) -> None:
    if not force:
        raise DestructiveRefusedError(...)
# ↑ caller can't tell whether they're refusing one DROP or a downgrade
#   sequence; audit log can't distinguish primitive vs orchestrator
#   reject events.
```

**Per-method disposition:** "1 DDL DROP = primitive (`force_drop` + `DropRefusedError`); multi-DDL sequence = orchestrator (`force_downgrade` / `force_remove_columns` / `force_rollback` + their respective `*RefusedError`)." Existing primitive call sites: `VisualMigrationBuilder`, `NotNullHandler`. Existing orchestrator call sites: `ColumnRemovalManager`, `RollbackManager`, `AutoMigrationSystem`.

**BLOCKED rationalizations:**

- "Both ultimately drop tables, so one helper is fine"
- "We can subclass DowngradeRefusedError from DropRefusedError"
- "The caller's try/except can use isinstance() to distinguish"

**Why:** A multi-DDL orchestrator invokes the primitive layer N times. If the orchestrator catches a shared `DropRefusedError`, the wrong layer claims responsibility for the refusal — the audit trail records "downgrade refused" when in fact one of the inner primitives refused first. Distinct error types preserve the layer attribution that incident-response queries depend on.

Origin: 2026-04-19 — conflating primitive-vs-orchestrator inside an earlier `drop_confirmation.py` required splitting into distinct error types.

## MUST NOT

- Use `f"..."` or `%` formatting to interpolate a dynamic identifier into DDL

**Why:** Every non-validated interpolation is a potential injection site; relying on "this value comes from a trusted source" means the audit is O(codebase) instead of O(identifier-helper).

- "Escape" quote characters inside an identifier

**Why:** Escape-based approaches are defeated by attackers who target the escape logic itself; the reject-based approach is defeated only by a regex bug, which is a single enforcement point.

- Drop tables, indexes, or schemas without an explicit `force_drop=True` on the API

**Why:** Silent drops are irrecoverable; the explicit flag is the only structural defense against typos.

## Relationship to Other Rules

- `rules/zero-tolerance.md` Rule 4 — this rule is the DDL-specific form of "no workarounds for SDK bugs." If the dialect helper is missing a capability, fix the helper, don't inline raw interpolation.
- `rules/schema-migration.md` § "All Schema Changes Through Numbered Migrations" — DDL lives in numbered migrations; numbered migrations use `quote_identifier`.
- `rules/infrastructure-sql.md` — this rule's companion for VALUES-path parameter binding.

<!-- /slot:neutral-body -->
