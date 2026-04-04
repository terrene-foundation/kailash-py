---
paths:
  - "**/trust/**"
---

# Trust-Plane Security Rules

### 1. No Bare `open()` or `Path.read_text()` for Record Files

```python
# DO:
from kailash.trust._locking import safe_read_json, safe_open
data = safe_read_json(path)

# DO NOT:
with open(path) as f:           # Follows symlinks — attacker redirects to arbitrary file
    data = json.load(f)
```

**Why**: `safe_read_json()` uses `O_NOFOLLOW` to prevent symlink attacks.

### 2. `validate_id()` on Every Externally-Sourced Record ID

```python
# DO:
from kailash.trust._locking import validate_id
validate_id(record_id)  # Raises ValueError on "../", "/", null bytes
path = store_dir / f"{record_id}.json"

# DO NOT:
path = store_dir / f"{user_input}.json"  # Path traversal: "../../../etc/passwd"
```

**Why**: Regex `^[a-zA-Z0-9_-]+$` prevents directory traversal and SQL injection via IDs.

### 3. `math.isfinite()` on All Numeric Constraint Fields

```python
# DO:
if self.max_cost is not None and not math.isfinite(self.max_cost):
    raise ValueError("max_cost must be finite")

# DO NOT:
if self.max_cost is not None and self.max_cost < 0:
    raise ValueError("negative")  # NaN passes, Inf passes
```

**Why**: `NaN` bypasses all numeric comparisons. Constraints set to `NaN` make all checks pass silently.

### 4. Bounded Collections (`maxlen=10000`)

```python
# DO:
call_log: deque = field(default_factory=lambda: deque(maxlen=10000))

# DO NOT:
call_log: list = field(default_factory=list)  # Grows without bound -> OOM
```

### 5. Parameterized SQL for All Database Queries

```python
# DO:
cursor.execute("SELECT * FROM decisions WHERE id = ?", (record_id,))

# DO NOT:
cursor.execute(f"SELECT * FROM decisions WHERE id = '{record_id}'")
```

### 6. SQLite Database File Permissions

```python
# DO (POSIX):
db_path.touch(mode=0o600)  # Owner read/write only

# DO NOT:
db_path.touch()  # Default permissions may be world-readable
```

### 7. All Record Writes Through `atomic_write()`

```python
# DO:
from kailash.trust._locking import atomic_write
atomic_write(path, json.dumps(record.to_dict()))

# DO NOT:
with open(path, 'w') as f:  # Partial write on crash = corrupted record
    json.dump(record, f)
```

**Why**: `atomic_write()` uses temp file + `fsync` + `os.replace()` for crash safety + `O_NOFOLLOW`.

## MUST NOT

### 1. No `==` to Compare HMAC Digests

```python
# DO:
hmac_mod.compare_digest(stored_hash, computed_hash)

# DO NOT:
stored_hash != computed_hash  # Timing side-channel for byte-by-byte forgery
```

### 2. No Trust State Downgrade

Trust state only escalates: `AUTO_APPROVED → FLAGGED → HELD → BLOCKED`. Never relax.

### 3. No Private Key Material in Memory

```python
# DO:
key_mgr.register_key(key_id, private_key)
del private_key  # Remove reference immediately

# On revocation:
self._keys[key_id] = ""  # Clear material, keep tombstone
```

### 4. Frozen Constraint Dataclasses

All constraint dataclasses (`OperationalConstraints`, `DataAccessConstraints`, `FinancialConstraints`, `TemporalConstraints`, `CommunicationConstraints`) MUST be `@dataclass(frozen=True)`. Use `object.__setattr__` in `__post_init__` if normalization needed.

### 5. No Unvalidated Cost Values

```python
# DO:
action_cost = float(ctx.get("cost", 0.0))
if not math.isfinite(action_cost) or action_cost < 0:
    return Verdict.BLOCKED

# DO NOT:
if action_cost > limit:  # NaN > limit is always False — budget bypassed!
```

### 6. No Bare `KeyError` Where `RecordNotFoundError` Is Intended

Use `RecordNotFoundError` (inherits both `TrustPlaneStoreError` and `KeyError`). Bare `except KeyError` is too broad.

### 7. Use `normalize_resource_path()` for Constraint Patterns

```python
# DO:
from kailash.trust.pathutils import normalize_resource_path
norm = normalize_resource_path(user_path)

# DO NOT:
norm = os.path.normpath(user_path)  # Platform-dependent, Windows backslashes
```
