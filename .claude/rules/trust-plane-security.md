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

**Why:** Bare `open()` follows symlinks, allowing an attacker to redirect trust-plane reads to arbitrary files like `/etc/shadow`.

### 2. `validate_id()` on Every Externally-Sourced Record ID

```python
# DO:
from kailash.trust._locking import validate_id
validate_id(record_id)  # Raises ValueError on "../", "/", null bytes
path = store_dir / f"{record_id}.json"

# DO NOT:
path = store_dir / f"{user_input}.json"  # Path traversal: "../../../etc/passwd"
```

**Why:** Unvalidated record IDs allow `../../../etc/passwd` traversal to read or overwrite files outside the trust store.

### 3. `math.isfinite()` on All Numeric Constraint Fields

```python
# DO:
if self.max_cost is not None and not math.isfinite(self.max_cost):
    raise ValueError("max_cost must be finite")

# DO NOT:
if self.max_cost is not None and self.max_cost < 0:
    raise ValueError("negative")  # NaN passes, Inf passes
```

**Why:** `NaN` bypasses all numeric comparisons — constraints set to `NaN` make all checks pass silently.

### 4. Bounded Collections (`maxlen=10000`)

```python
# DO:
call_log: deque = field(default_factory=lambda: deque(maxlen=10000))

# DO NOT:
call_log: list = field(default_factory=list)  # Grows without bound -> OOM
```

**Why:** An unbounded call log in a long-running trust-plane process becomes a memory-exhaustion denial-of-service vector.

### 5. Parameterized SQL for All Database Queries

```python
# DO:
cursor.execute("SELECT * FROM decisions WHERE id = ?", (record_id,))

# DO NOT:
cursor.execute(f"SELECT * FROM decisions WHERE id = '{record_id}'")
```

**Why:** Trust-plane decision records are high-value targets — SQL injection here allows an attacker to forge, delete, or modify governance audit trails.

### 6. SQLite Database File Permissions

```python
# DO (POSIX):
db_path.touch(mode=0o600)  # Owner read/write only

# DO NOT:
db_path.touch()  # Default permissions may be world-readable
```

**Why:** Trust-plane databases contain HMAC keys, decision records, and constraint data — world-readable permissions expose governance secrets to any local user.

### 7. All Record Writes Through `atomic_write()`

```python
# DO:
from kailash.trust._locking import atomic_write
atomic_write(path, json.dumps(record.to_dict()))

# DO NOT:
with open(path, 'w') as f:  # Partial write on crash = corrupted record
    json.dump(record, f)
```

**Why:** A crash during bare `open()`/`write()` truncates the file mid-write, permanently corrupting the trust record with no recovery path.

## MUST NOT

### 1. No `==` to Compare HMAC Digests

```python
# DO:
hmac_mod.compare_digest(stored_hash, computed_hash)

# DO NOT:
stored_hash != computed_hash  # Timing side-channel for byte-by-byte forgery
```

**Why:** String `==` short-circuits on the first differing byte, leaking timing information that allows an attacker to forge valid HMACs one byte at a time.

### 2. No Trust State Downgrade

Trust state only escalates: `AUTO_APPROVED → FLAGGED → HELD → BLOCKED`. Never relax.

**Why:** Allowing state relaxation means a compromised agent could clear its own BLOCKED status and resume unauthorized operations.

### 3. No Private Key Material in Memory

```python
# DO:
key_mgr.register_key(key_id, private_key)
del private_key  # Remove reference immediately

# On revocation:
self._keys[key_id] = ""  # Clear material, keep tombstone
```

**Why:** Long-lived key material in memory is extractable via heap dumps, core dumps, or memory-disclosure vulnerabilities — minimizing residence time limits the exposure window.

### 4. Frozen Constraint Dataclasses

All constraint dataclasses (`OperationalConstraints`, `DataAccessConstraints`, `FinancialConstraints`, `TemporalConstraints`, `CommunicationConstraints`) MUST be `@dataclass(frozen=True)`. Use `object.__setattr__` in `__post_init__` if normalization needed.

**Why:** Mutable constraints allow runtime modification after governance approval, enabling an agent to widen its own operating envelope post-initialization.

### 5. No Unvalidated Cost Values

```python
# DO:
action_cost = float(ctx.get("cost", 0.0))
if not math.isfinite(action_cost) or action_cost < 0:
    return Verdict.BLOCKED

# DO NOT:
if action_cost > limit:  # NaN > limit is always False — budget bypassed!
```

**Why:** A NaN cost value silently passes all comparison-based budget checks, allowing unlimited spending with no audit trail.

### 6. No Bare `KeyError` Where `RecordNotFoundError` Is Intended

Use `RecordNotFoundError` (inherits both `TrustPlaneStoreError` and `KeyError`). Bare `except KeyError` is too broad.

**Why:** Bare `except KeyError` catches dict access errors unrelated to record lookup, silently swallowing real bugs and making missing records indistinguishable from programming errors.

### 7. Use `normalize_resource_path()` for Constraint Patterns

```python
# DO:
from kailash.trust.pathutils import normalize_resource_path
norm = normalize_resource_path(user_path)

# DO NOT:
norm = os.path.normpath(user_path)  # Platform-dependent, Windows backslashes
```

**Why:** `os.path.normpath` produces platform-dependent results (backslashes on Windows), causing constraint patterns that match on Linux to silently fail on other platforms.
