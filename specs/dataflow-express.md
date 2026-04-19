# Kailash DataFlow — Express API (Async + Sync, Bulk, Validation, File Import)

Version: 2.0.7
Package: `kailash-dataflow`
Parent domain: DataFlow (split from `dataflow.md` per specs-authority Rule 8)
Scope: Express async API (`db.express`), Express Sync API (`db.express_sync`), low-level bulk operations, validation framework (field validators invoked on write), file import

Sibling files: `dataflow-core.md` (DataFlow class, engine, exceptions, trust, fabric), `dataflow-models.md` (`@db.model`, fields, classification/masking, multi-tenancy, schema management), `dataflow-cache.md` (cache, dialect, record ID coercion, transactions, pooling)

---

## 3. Express API (Async)

Accessed via `db.express`. Provides high-performance direct node invocation that bypasses workflow overhead (23x faster than WorkflowBuilder for single-record CRUD).

Express is the default and recommended API for all CRUD operations. Use WorkflowBuilder only for multi-step, multi-node operations.

### 3.1 `create`

```python
async def create(
    self,
    model: str,
    data: Dict[str, Any],
) -> Dict[str, Any]
```

Create a single record.

**Parameters:**

- `model` (`str`): Model name (e.g., `"User"`)
- `data` (`Dict[str, Any]`): Record data. Must include `id` field for string-PK models. For integer-PK models, `id` is auto-generated if omitted.

**Returns:** `Dict[str, Any]` -- The created record as a dictionary.

**Behavior:**

1. Runs field validators if `validate_on_write` is enabled
2. Runs trust access check if trust plane is enabled
3. Executes the model's `CreateNode`
4. Invalidates model-scoped cache entries
5. For SQLite: if the result is missing timestamps (`created_at`, `updated_at`), performs a read-back to fetch the complete record
6. Emits write event (TSG-201)
7. Records trust audit success/failure

**Error conditions:**

- `DataFlowError`: Validation failure (when `validate_on_write=True`)
- `ValueError`: Node not found (model not registered)
- Database-specific errors propagated from the adapter

**Example:**

```python
user = await db.express.create("User", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
})
```

### 3.2 `read`

```python
async def read(
    self,
    model: str,
    id: Union[str, int],
    cache_ttl: Optional[int] = None,
    use_primary: bool = False,
) -> Optional[Dict[str, Any]]
```

Read a single record by primary key.

**Parameters:**

- `model` (`str`): Model name
- `id` (`Union[str, int]`): Record ID. Accepts both string and integer IDs; DataFlow coerces the value to match the model's primary key type.
- `cache_ttl` (`Optional[int]`): Override the default cache TTL for this operation. `0` disables caching for this call.
- `use_primary` (`bool`): Force read from primary adapter instead of read replica (TSG-105). Default `False`.

**Returns:** `Optional[Dict[str, Any]]` -- The record as a dictionary, or `None` if not found.

**Behavior:**

1. Checks cache first (returns cached value on hit)
2. Runs trust access check
3. Executes the model's `ReadNode`
4. Applies trust result filter (PII/column filter)
5. Applies classification masking based on caller clearance
6. Stores result in cache
7. Returns `None` (not an exception) when record is not found

**Cache key shape:** `dataflow:v2:[tenant_id:]<model>:read:<params_hash>` (bumped from `v1` in kailash-dataflow 2.0.11 / BP-049 — classified PKs now pre-hashed before `params_hash` computation)

**Error conditions:**

- `ValueError`: Node not found
- Returns `None` for "not found" errors (not an exception)

**Example:**

```python
user = await db.express.read("User", "user-123")
user = await db.express.read("User", 42)  # integer ID
user = await db.express.read("User", "42")  # coerced to int if model PK is int
```

### 3.3 `update`

```python
async def update(
    self,
    model: str,
    id: Union[str, int],
    fields: Dict[str, Any],
) -> Dict[str, Any]
```

Update a single record.

**Parameters:**

- `model` (`str`): Model name
- `id` (`Union[str, int]`): Record ID (coerced to match model PK type)
- `fields` (`Dict[str, Any]`): Fields to update (partial update -- only specified fields are changed)

**Returns:** `Dict[str, Any]` -- The updated record.

**Behavior:**

1. Runs field validators on the update fields
2. Runs trust write access check
3. Executes the model's `UpdateNode` with `filter={"id": id}` and `fields=fields`
4. Invalidates model-scoped cache
5. Emits write event

**Example:**

```python
user = await db.express.update("User", "user-123", {"name": "Alice Updated"})
```

### 3.4 `delete`

```python
async def delete(
    self,
    model: str,
    id: Union[str, int],
) -> bool
```

Delete a single record.

**Parameters:**

- `model` (`str`): Model name
- `id` (`Union[str, int]`): Record ID

**Returns:** `bool` -- `True` if deleted, `False` if not found.

**Example:**

```python
deleted = await db.express.delete("User", "user-123")
```

### 3.5 `list`

```python
async def list(
    self,
    model: str,
    filter: Optional[Dict[str, Any]] = None,
    limit: int = 100,
    offset: int = 0,
    order_by: Optional[str] = None,
    cache_ttl: Optional[int] = None,
    use_primary: bool = False,
) -> List[Dict[str, Any]]
```

List records with optional filtering and pagination.

**Parameters:**

- `model` (`str`): Model name
- `filter` (`Optional[Dict[str, Any]]`): MongoDB-style filter criteria (see section 3.11)
- `limit` (`int`): Maximum records to return. Default: 100.
- `offset` (`int`): Skip first N records. Default: 0.
- `order_by` (`Optional[str]`): Field to sort by. Prefix with `-` for descending (e.g., `"-created_at"`).
- `cache_ttl` (`Optional[int]`): Override default cache TTL.
- `use_primary` (`bool`): Force read from primary adapter.

**Returns:** `List[Dict[str, Any]]` -- List of records as dictionaries.

**Behavior:**

1. Checks cache first
2. Applies trust constraints (additional filters, row limit tightening)
3. Executes the model's `ListNode`
4. Applies trust result filter and classification masking
5. Caches the result

**Example:**

```python
users = await db.express.list("User", filter={"active": True}, limit=50, order_by="-created_at")
```

### 3.6 `find_one`

```python
async def find_one(
    self,
    model: str,
    filter: Dict[str, Any],
    cache_ttl: Optional[int] = None,
    use_primary: bool = False,
) -> Optional[Dict[str, Any]]
```

Find a single record by non-PK filter criteria.

**Parameters:**

- `model` (`str`): Model name
- `filter` (`Dict[str, Any]`): MongoDB-style filter criteria. **Required and must not be empty.** For unfiltered queries, use `list()` with `limit=1`.
- `cache_ttl` (`Optional[int]`): Override default cache TTL.
- `use_primary` (`bool`): Force read from primary adapter.

**Returns:** `Optional[Dict[str, Any]]` -- Single record or `None`.

**Raises:** `ValueError` if `filter` is empty.

**Example:**

```python
user = await db.express.find_one("User", filter={"email": "alice@example.com"})
```

### 3.7 `count`

```python
async def count(
    self,
    model: str,
    filter: Optional[Dict[str, Any]] = None,
    cache_ttl: Optional[int] = None,
    use_primary: bool = False,
) -> int
```

Count records matching optional filter criteria. Uses `COUNT(*)` for optimal performance.

**Parameters:**

- `model` (`str`): Model name
- `filter` (`Optional[Dict[str, Any]]`): MongoDB-style filter criteria
- `cache_ttl` (`Optional[int]`): Override default cache TTL.
- `use_primary` (`bool`): Force read from primary adapter.

**Returns:** `int` -- Number of matching records.

**Example:**

```python
active_count = await db.express.count("User", filter={"active": True})
```

### 3.8 `upsert`

```python
async def upsert(
    self,
    model: str,
    data: Dict[str, Any],
    conflict_on: Optional[List[str]] = None,
) -> Dict[str, Any]
```

Insert or update a record. Uses the `id` field for conflict detection by default.

**Parameters:**

- `model` (`str`): Model name
- `data` (`Dict[str, Any]`): Record data including `id`
- `conflict_on` (`Optional[List[str]]`): Fields for conflict detection. Default: `["id"]`.

**Returns:** `Dict[str, Any]` -- The upserted record.

**Example:**

```python
result = await db.express.upsert("User", {"id": "u1", "name": "Alice", "email": "alice@example.com"})
```

### 3.9 `upsert_advanced`

```python
async def upsert_advanced(
    self,
    model: str,
    where: Dict[str, Any],
    create: Dict[str, Any],
    update: Optional[Dict[str, Any]] = None,
    conflict_on: Optional[List[str]] = None,
) -> Dict[str, Any]
```

Advanced upsert with separate where/create/update parameters.

**Parameters:**

- `model` (`str`): Model name
- `where` (`Dict[str, Any]`): Fields to identify the record
- `create` (`Dict[str, Any]`): Fields to use when creating a new record
- `update` (`Optional[Dict[str, Any]]`): Fields to use when updating an existing record. Default: same as `create`.
- `conflict_on` (`Optional[List[str]]`): Fields for conflict detection. Default: keys from `where`.

**Returns:** `Dict[str, Any]` -- Dict with `created` (bool), `action` (str), `record` (dict).

**Example:**

```python
result = await db.express.upsert_advanced(
    "User",
    where={"email": "alice@example.com"},
    create={"id": "u1", "email": "alice@example.com", "name": "Alice"},
    update={"name": "Alice Updated"},
    conflict_on=["email"],
)
```

### 3.10 Bulk Operations

#### `bulk_create`

```python
async def bulk_create(
    self,
    model: str,
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]
```

Create multiple records in bulk. Returns list of created records. Logs `WARN` on partial failure.

#### `bulk_update`

```python
async def bulk_update(
    self,
    model: str,
    records: List[Dict[str, Any]],
    key_field: str = "id",
) -> List[Dict[str, Any]]
```

Update multiple records. Each record dict must contain `key_field` (default `"id"`) to identify which record to update. Remaining fields are the values to set. Internally calls `update()` per record. Logs `WARN` on partial failure.

#### `bulk_delete`

```python
async def bulk_delete(
    self,
    model: str,
    ids: List[str],
) -> bool
```

Delete multiple records by ID list. Uses `$in` filter internally. Returns `True` if all deletions succeeded.

#### `bulk_upsert`

```python
async def bulk_upsert(
    self,
    model: str,
    records: List[Dict[str, Any]],
    conflict_on: Optional[List[str]] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]
```

Bulk upsert using database-native `INSERT ... ON CONFLICT`. Validates `conflict_on` fields against model schema.

**Returns:** `{"records": [...], "created": int, "updated": int, "total": int}`

**SQL safety (issue #492):** All VALUES are bound through driver parameters, never string-escaped. The internal helper `BulkUpsertNode._build_upsert_query(...)` returns `(sql, params)` where the SQL contains dialect-appropriate placeholders (`$N` for PostgreSQL, `?` for SQLite, `%s` for MySQL) and `params` is a flat list bound by the driver. Hand-rolled `value.replace("'", "''")` is BLOCKED — see `rules/security.md` § Parameterized Queries.

**Failure semantics:** A batch that raises during execution propagates as `NodeExecutionError` with the underlying driver error in the message AND a structured WARN log line `bulk_upsert.batch_error: <error>` per `rules/observability.md` Rule 7 (no silent partial failure).

### 3.11 Filter Syntax

Express operations accept MongoDB-style filter dictionaries:

**Equality:**

```python
{"status": "active"}                          # status = 'active'
{"age": 25}                                   # age = 25
```

**Comparison operators:**

```python
{"age": {"$gt": 18}}                          # age > 18
{"age": {"$gte": 18}}                         # age >= 18
{"age": {"$lt": 65}}                          # age < 65
{"age": {"$lte": 65}}                         # age <= 65
{"status": {"$ne": "deleted"}}                # status != 'deleted'
```

**Set membership:**

```python
{"role": {"$in": ["admin", "editor"]}}        # role IN ('admin', 'editor')
{"status": {"$nin": ["deleted", "archived"]}} # status NOT IN (...)
```

**`$in` / `$nin` edge cases:**

- Empty list: `$in` with `[]` matches nothing (`1 = 0`); `$nin` with `[]` matches everything (`1 = 1`).
- `None` values in the list are filtered out (SQL `IN` does not handle `NULL`).
- Duplicates are removed for efficiency.
- Maximum 10,000 items per `$in`/`$nin` (raises `ValueError` if exceeded).

**Multiple conditions** are combined with `AND`:

```python
{"status": "active", "age": {"$gte": 18}}    # status = 'active' AND age >= 18
```

### 3.12 File Import

```python
async def import_file(
    self,
    model_name: str,
    file_path: str,
    column_mapping: Optional[Dict[str, Any]] = None,
    type_coercion: Optional[Dict[str, str]] = None,
    upsert: bool = True,
    batch_size: int = 1000,
    **kwargs: Any,
) -> Dict[str, Any]
```

Import records from a file (CSV, JSON, etc.) into a model. Returns `{"imported": int, "errors": [...]}`.

---

## 4. Express Sync API

Accessed via `db.express_sync`. Provides synchronous equivalents of all async Express methods for use in CLI scripts, synchronous handlers, and pytest without asyncio.

Internally maintains a single persistent event loop in a background daemon thread so that database connections (which are bound to an event loop) survive across multiple sync calls.

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str

user = db.express_sync.create("User", {"id": "u1", "name": "Alice"})
user = db.express_sync.read("User", "u1")
users = db.express_sync.list("User", filter={"name": "Alice"})
count = db.express_sync.count("User")
db.express_sync.delete("User", "u1")
```

All methods have identical signatures and return types to the async Express API. Methods available:

| Method                                                                 | Signature matches         |
| ---------------------------------------------------------------------- | ------------------------- |
| `create(model, data)`                                                  | `express.create`          |
| `read(model, id, cache_ttl, use_primary)`                              | `express.read`            |
| `update(model, id, fields)`                                            | `express.update`          |
| `delete(model, id)`                                                    | `express.delete`          |
| `list(model, filter, limit, offset, order_by, cache_ttl, use_primary)` | `express.list`            |
| `find_one(model, filter, cache_ttl, use_primary)`                      | `express.find_one`        |
| `count(model, filter, cache_ttl, use_primary)`                         | `express.count`           |
| `upsert(model, data, conflict_on)`                                     | `express.upsert`          |
| `upsert_advanced(model, where, create, update, conflict_on)`           | `express.upsert_advanced` |
| `bulk_create(model, records)`                                          | `express.bulk_create`     |
| `bulk_update(model, records, key_field)`                               | `express.bulk_update`     |
| `bulk_delete(model, ids)`                                              | `express.bulk_delete`     |
| `bulk_upsert(model, records, conflict_on, batch_size)`                 | `express.bulk_upsert`     |

---

## 11. Validation Framework

### 11.1 `@field_validator` Decorator

```python
from dataflow.validation.decorators import field_validator
from dataflow.validation.field_validators import email_validator, length_validator

@field_validator("email", email_validator)
@field_validator("name", length_validator(min_len=1, max_len=100))
@db.model
class User:
    id: int
    name: str = ""
    email: str = ""
```

Validators are stored in `__field_validators__` on the class. A validator is a callable `(value) -> bool` that returns `True` if the value is valid.

### 11.2 Built-In Validators

| Validator                            | Import                | Purpose                         |
| ------------------------------------ | --------------------- | ------------------------------- |
| `email_validator`                    | `dataflow.validation` | Validates email format          |
| `url_validator`                      | `dataflow.validation` | Validates URL format            |
| `uuid_validator`                     | `dataflow.validation` | Validates UUID format           |
| `length_validator(min_len, max_len)` | `dataflow.validation` | Validates string length bounds  |
| `range_validator(min_val, max_val)`  | `dataflow.validation` | Validates numeric range         |
| `pattern_validator(regex)`           | `dataflow.validation` | Validates against regex pattern |
| `phone_validator`                    | `dataflow.validation` | Validates phone number format   |

### 11.3 `__validation__` Dictionary DSL

Models can declare validation via a `__validation__` dict (parsed at `@db.model` time via `apply_validation_dict`):

```python
@db.model
class User:
    __validation__ = {
        "email": "email",
        "name": {"length": {"min": 1, "max": 100}},
    }
    id: int
    name: str
    email: str
```

### 11.4 `validate_model`

```python
from dataflow.validation.decorators import validate_model

result = validate_model(user_instance)
assert result.valid             # True if all validators pass
assert len(result.errors) == 0  # List of ValidationError
```

### 11.5 Automatic Validation on Write

When `validate_on_write=True` (default), Express `create`, `update`, and `upsert` automatically run field validators before writing. Failed validation raises `DataFlowError`.

### 11.6 ValidationResult

```python
from dataflow.validation.result import ValidationResult

result.valid       # bool
result.errors      # List[FieldValidationError]
result.add_error(field_name="email", message="...", validator="...", value="...")
```

---

## 16. Bulk Operations (Low-Level)

The `BulkOperations` class (`features/bulk.py`) provides direct database bulk operations used internally by the generated bulk nodes. It handles:

- **Batch processing**: Records are split into batches of `batch_size` (default: 1000)
- **Parameter serialization**: Dicts are JSON-serialized for SQL binding; lists are serialized to JSON unless `use_native_arrays=True` (PostgreSQL native arrays)
- **Filter building**: MongoDB-style operators are translated to SQL WHERE clauses with dialect-appropriate parameter placeholders
- **Tenant injection**: In multi-tenant mode, `tenant_id` is auto-injected into each record
