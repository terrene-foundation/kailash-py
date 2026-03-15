# Trust-Plane Store Backends

## Store Protocol

`TrustPlaneStore` is a `typing.Protocol` (runtime-checkable) defining the persistence interface. All backends implement this protocol identically.

```python
from trustplane.store import TrustPlaneStore

# Any backend can be passed where TrustPlaneStore is expected
def process(store: TrustPlaneStore) -> None:
    decisions = store.list_decisions(limit=100)
    ...
```

## Backend Comparison

| Feature | SQLite | Filesystem | PostgreSQL |
|---------|--------|------------|------------|
| Default | Yes | No | No |
| Install extra | (none) | (none) | `[postgres]` |
| Concurrency | WAL mode + `BEGIN IMMEDIATE` | `filelock` | MVCC |
| Atomic writes | Transaction | temp + fsync + rename | Transaction |
| Schema versioning | `meta` table | N/A | `meta` table |
| Multi-tenancy | `WHERE project_id = ?` | Directory scoping | RLS |
| Performance | High (single file) | Moderate (many files) | High (network) |
| Git-friendly | No (binary) | Yes (JSON files) | No (external) |
| Encryption at rest | Via `crypto_utils` | Via `crypto_utils` | Via `crypto_utils` + TDE |

## SQLite Backend (Default)

```python
from trustplane.store.sqlite import SqliteTrustPlaneStore

store = SqliteTrustPlaneStore(".trust-plane/trust.db")
store.initialize()
```

- WAL journal mode for concurrent read/write
- `BEGIN IMMEDIATE` for write transactions (prevents writer starvation)
- Schema version tracked in `meta` table
- Automatic migrations on version mismatch
- File permissions: `0o600` on POSIX, DACL on Windows

### Schema Versioning

The SQLite backend auto-manages schema versions:

- `store.initialize()` checks current schema version against code version
- If DB is older: runs migrations sequentially
- If DB is newer: raises `SchemaTooNewError` (upgrade trust-plane)
- If migration fails: raises `SchemaMigrationError` (rolled back, DB untouched)

## Filesystem Backend

```python
from trustplane.store.filesystem import FileSystemTrustPlaneStore

store = FileSystemTrustPlaneStore(Path(".trust-plane"))
store.initialize()
```

- One JSON file per record in typed subdirectories
- Atomic writes via `atomic_write()` (temp file + fsync + os.replace)
- `O_NOFOLLOW` on all file operations (symlink attack prevention)
- `filelock` for concurrent process safety
- Git-committable audit trail

### Directory Layout

```
.trust-plane/
├── decisions/          # DecisionRecord JSON files
├── milestones/         # MilestoneRecord JSON files
├── holds/              # HoldRecord JSON files
├── delegates/          # Delegate JSON files
├── reviews/            # ReviewResolution JSON files
├── anchors/            # EATP audit anchors
├── manifest.json       # ProjectManifest
├── wal.json            # Cascade revocation WAL (transient)
└── keys/               # Ed25519 keypair (0o600)
```

## PostgreSQL Backend

```python
from trustplane.store.postgres import PostgresTrustPlaneStore

store = PostgresTrustPlaneStore("postgresql://user:pass@host/db")
store.initialize()
```

Requires `pip install trust-plane[postgres]` (psycopg3 + psycopg_pool).

- Connection pooling via `psycopg_pool`
- MVCC for concurrent safety
- Row-Level Security ready for multi-tenancy
- Schema versioning via `meta` table

## Store Security Contract

All backends MUST satisfy these 6 requirements. Violations are security defects.

1. **ATOMIC_WRITES** — Every write is all-or-nothing. Crash during write must not corrupt data.
2. **INPUT_VALIDATION** — Every record ID validated via `validate_id()` before filesystem/SQL use.
3. **BOUNDED_RESULTS** — Every list method honours `limit` parameter. Default <= 1000.
4. **PERMISSION_ISOLATION** — Records from other projects are invisible to the current store instance.
5. **CONCURRENT_SAFETY** — Multiple processes can read/write without data loss.
6. **NO_SILENT_FAILURES** — Errors raise named exceptions (subclass of `TrustPlaneStoreError`), never return None/False.

## Conformance Tests

New backends must pass the conformance test suite:

```python
from trustplane.conformance import run_conformance_tests

results = run_conformance_tests(MyCustomStore(path))
assert all(r.passed for r in results)
```

The suite tests all 6 security contract requirements plus all protocol methods.

## Migration Between Backends

```python
from trustplane.migrate import migrate_to_sqlite

# Filesystem -> SQLite
result = migrate_to_sqlite(".trust-plane")
```

Migration is one-way (filesystem -> SQLite). The original filesystem records are preserved as backup.
