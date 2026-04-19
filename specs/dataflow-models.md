# Kailash DataFlow — Models, Classification, Multi-Tenant, Schema Management

Version: 2.0.12
Package: `kailash-dataflow`
Parent domain: DataFlow (split from `dataflow.md` per specs-authority Rule 8)
Scope: `@db.model` decorator, field types, primary keys, auto-managed fields, table name mapping, model configuration, build-time validation, field classification/masking/retention, multi-tenant support, schema management (auto-migration, schema cache)

Sibling files: `dataflow-core.md` (DataFlow class, engine, exceptions, trust, fabric), `dataflow-express.md` (async/sync Express API, bulk, file import, validation on write), `dataflow-cache.md` (cache, dialect, record ID coercion, transactions, pooling)

---

## 2. Model Definition

### 2.1 The `@db.model` Decorator

Models are registered using the `@db.model` decorator on the DataFlow instance:

```python
db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: int
    name: str
    email: str
    active: bool = True
```

The decorator:

1. Registers the model in `db._models`
2. Extracts field definitions from `__annotations__` (including inherited)
3. Generates 11 CRUD workflow nodes (Create, Read, Update, Delete, List, Count, BulkCreate, BulkUpdate, BulkDelete, Upsert, BulkUpsert)
4. Sets up table name mapping (class name to snake_case, or `__tablename__` override)
5. Registers `@classify` metadata with the classification policy
6. Parses `__validation__` dict into `@field_validator` entries
7. Registers retention policies from `__dataflow__["retention"]`
8. Attaches `cls._dataflow` and `cls._dataflow_meta` attributes

**Duplicate registration** raises `EnhancedDataFlowError` (DF-602).

### 2.2 Field Types

Fields are defined via Python type annotations. DataFlow maps Python types to SQL types through the dialect system:

| Python Type     | PostgreSQL                  | SQLite               | MySQL       |
| --------------- | --------------------------- | -------------------- | ----------- |
| `int`           | `INTEGER`                   | `INTEGER`            | `INT`       |
| `str`           | `TEXT`                      | `TEXT`               | `TEXT`      |
| `float`         | `REAL`                      | `REAL`               | `DOUBLE`    |
| `bool`          | `BOOLEAN`                   | `INTEGER` (0/1)      | `BOOLEAN`   |
| `datetime`      | `TIMESTAMP`                 | `TEXT` (ISO string)  | `TIMESTAMP` |
| `dict` / `Dict` | `JSONB`                     | `TEXT` (JSON string) | `JSON`      |
| `list` / `List` | `ARRAY` (native) or `JSONB` | `TEXT` (JSON string) | `JSON`      |
| `bytes`         | `BYTEA`                     | `BLOB`               | `BLOB`      |

### 2.3 Primary Keys

The primary key field MUST be named `id`. DataFlow convention recommends this for consistency with generated nodes.

```python
@db.model
class User:
    id: int          # Integer auto-increment PK
    name: str

@db.model
class Document:
    id: str          # String PK (caller must provide)
    title: str
```

**Validation codes (build-time):**

- **VAL-002**: Missing primary key (error in STRICT mode, warning in WARN mode)
- **VAL-003**: Primary key not named `id` (warning)
- **VAL-004**: Composite primary key (warning -- DataFlow generated nodes expect single `id`)

### 2.4 Auto-Managed Fields

DataFlow automatically manages these fields when present:

- `created_at`: Timestamp of record creation
- `updated_at`: Timestamp of last update
- `created_by`: User who created the record
- `updated_by`: User who last updated the record

**VAL-005**: User-defined columns with these names emit a warning about potential conflicts.

### 2.5 Table Name Mapping

By default, class names are converted to snake_case table names:

- `User` -> `user`
- `UserProfile` -> `user_profile`
- `APIToken` -> `api_token`

Override with `__tablename__`:

```python
@db.model
class User:
    __tablename__ = "app_users"
    id: int
    name: str
```

### 2.6 Model Configuration

Models can declare configuration via `__dataflow__`:

```python
@db.model
class User:
    __dataflow__ = {
        "use_native_arrays": True,    # PostgreSQL native TEXT[]/INTEGER[] arrays
        "retention": {
            "policy": "delete",
            "after_days": 365,
            "cutoff_field": "created_at",
        },
    }
    id: int
    name: str
    tags: list
```

### 2.7 Build-Time Validation

The `@db.model` decorator supports three validation modes:

```python
from dataflow.decorators import ValidationMode

@db.model                              # Default: WARN mode
@db.model(strict=True)                 # STRICT mode: raises ModelValidationError
@db.model(skip_validation=True)        # OFF mode: no validation
@db.model(validation=ValidationMode.STRICT)  # Explicit mode
```

**Validation codes:**

| Code    | Severity | Description                                 |
| ------- | -------- | ------------------------------------------- |
| VAL-002 | Error    | Missing primary key                         |
| VAL-003 | Warning  | Primary key not named `id`                  |
| VAL-004 | Warning  | Composite primary key                       |
| VAL-005 | Warning  | Auto-managed field conflict                 |
| VAL-006 | Warning  | DateTime without timezone                   |
| VAL-007 | Warning  | String without length                       |
| VAL-008 | Warning  | camelCase field name (should be snake_case) |
| VAL-009 | Warning  | SQL reserved word as field name             |
| VAL-010 | Warning  | Missing cascade on foreign key              |

In WARN mode (default), errors become `DataFlowValidationWarning`. In STRICT mode, errors raise `ModelValidationError`.

---

## 5. Field Classification and Data Masking

### 5.1 Classification Levels

Defined in `dataflow.classification.types.DataClassification` (ordered least to most sensitive):

| Level                 | Value                   | Default Retention                  |
| --------------------- | ----------------------- | ---------------------------------- |
| `PUBLIC`              | `"public"`              | Indefinite                         |
| `INTERNAL`            | `"internal"`            | Indefinite                         |
| `SENSITIVE`           | `"sensitive"`           | 365 days                           |
| `PII`                 | `"pii"`                 | Indefinite                         |
| `GDPR`                | `"gdpr"`                | Indefinite (until consent revoked) |
| `HIGHLY_CONFIDENTIAL` | `"highly_confidential"` | 2555 days (~7 years)               |

### 5.2 Retention Policies

Defined in `dataflow.classification.types.RetentionPolicy`:

| Policy                  | Days   |
| ----------------------- | ------ |
| `INDEFINITE`            | `None` |
| `DAYS_30`               | 30     |
| `DAYS_90`               | 90     |
| `YEARS_1`               | 365    |
| `YEARS_7`               | 2555   |
| `UNTIL_CONSENT_REVOKED` | `None` |

### 5.3 Masking Strategies

Defined in `dataflow.classification.types.MaskingStrategy`:

| Strategy    | Behavior                                       |
| ----------- | ---------------------------------------------- |
| `NONE`      | Value shown as-is                              |
| `HASH`      | SHA-256 hex digest of the string value         |
| `REDACT`    | Replaced with `"[REDACTED]"`                   |
| `LAST_FOUR` | All characters except last 4 replaced with `*` |
| `ENCRYPT`   | Read-time sentinel `"[ENCRYPTED]"`             |

### 5.4 The `@classify` Decorator

```python
from dataflow import classify, DataClassification, RetentionPolicy, MaskingStrategy

@classify("email", DataClassification.PII, RetentionPolicy.UNTIL_CONSENT_REVOKED, MaskingStrategy.REDACT)
@classify("ssn", DataClassification.HIGHLY_CONFIDENTIAL, masking=MaskingStrategy.LAST_FOUR)
@db.model
class User:
    id: int
    name: str
    email: str
    ssn: str
```

Multiple `@classify` decorators can be stacked. Metadata is stored in `__field_classifications__` on the class.

### 5.5 Fail-Closed Default

Unclassified fields default to `"highly_confidential"` (fail-closed). This means:

- If no `ClassificationPolicy` is set on the `DataFlowEngine`, all fields are treated as `"highly_confidential"`.
- If a field is not decorated with `@classify`, the policy returns `"highly_confidential"` for that field.

### 5.6 Read-Time Masking

When classification is active, Express `read`, `list`, and `find_one` apply masking automatically based on the caller's clearance level:

```python
from dataflow.core.agent_context import set_clearance
from dataflow.classification.types import DataClassification

set_clearance(DataClassification.INTERNAL)
user = await db.express.read("User", "u1")
# user["email"] -> "[REDACTED]" (PII requires higher clearance)
# user["name"] -> "Alice" (no classification or PUBLIC)
```

Clearance ordering: `PUBLIC < INTERNAL < SENSITIVE < PII < GDPR < HIGHLY_CONFIDENTIAL`. A caller can see fields at or below their clearance level.

### 5.7 ClassificationPolicy API

```python
from dataflow.classification.policy import ClassificationPolicy

policy = ClassificationPolicy()
policy.register_model(User)                    # Read @classify metadata
policy.set_field("User", "phone", DataClassification.PII)  # Programmatic
level = policy.classify("User", "email")       # -> "pii"
days = policy.get_retention_days("pii")        # -> None (indefinite)
fc = policy.get_field("User", "email")         # -> FieldClassification
fields = policy.get_model_fields("User")       # -> Dict[str, FieldClassification]
```

---

## 7. Multi-Tenant Support

### 7.1 Enabling Multi-Tenancy

```python
db = DataFlow("postgresql://...", multi_tenant=True)
```

### 7.2 Tenant Context

Every Express operation on a multi-tenant DataFlow instance requires a bound tenant context. Missing tenant raises `TenantRequiredError` -- there is no silent fallback to a default tenant.

```python
from dataflow.core.tenant_context import TenantContextSwitch

async with db.tenant_context.switch("tenant-abc"):
    users = await db.express.list("User")  # Scoped to tenant-abc
```

### 7.3 Tenant ID Validation

Tenant IDs are validated against `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`. Invalid IDs raise `InvalidTenantIdError`.

### 7.4 Isolation Guarantees

- **Cache keys** include tenant_id dimension: `dataflow:v2:<tenant_id>:<model>:<op>:<hash>` (bumped from `v1` in kailash-dataflow 2.0.11 / BP-049; classified PKs pre-hashed via `format_record_id_for_event` before the params hash is computed)
- **Cache invalidation** is tenant-scoped
- **Bulk operations** auto-inject `tenant_id` into each record
- **Audit rows** persist `tenant_id` as a column

### 7.5 TenantRequiredError

```python
from dataflow.core.multi_tenancy import TenantRequiredError

# Raised when:
# 1. DataFlow has multi_tenant=True
# 2. No tenant is bound to the current async context
# 3. An Express operation is attempted
```

---

## 8. Schema Management

### 8.1 Auto-Migration

When `auto_migrate=True` (default), DataFlow automatically creates and updates database tables when models are first accessed. Table creation is lazy -- triggered by the first operation on a model, not at registration time.

### 8.2 `ensure_table_exists`

```python
await db.ensure_table_exists("User")  # Returns bool
```

Creates the table for a model if it does not exist. With schema caching enabled (ADR-001):

1. Checks cache for table existence (~0.001ms)
2. If cached, returns immediately
3. If not cached, runs full migration checking (~1500ms)
4. Updates cache after successful check

### 8.3 Schema Cache

The schema cache avoids redundant `ensure_table_exists` checks. Configurable via:

- `schema_cache_enabled` (default: `True` when `auto_migrate=True`)
- `schema_cache_ttl` (default: configured in `DataFlowConfig.migration`)
- `schema_cache_max_size`

### 8.4 Existing Schema Mode

```python
db = DataFlow("postgresql://...", existing_schema_mode=True)
```

When enabled, DataFlow validates compatibility with existing tables but does not modify the schema. Useful for connecting to databases managed by other migration tools.
