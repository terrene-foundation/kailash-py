# Trust-Plane Security Rules

## Scope

These rules apply when editing:

- `packages/trust-plane/**`
- `packages/eatp/src/eatp/store/**`

These rules supplement `.claude/rules/security.md`. Both apply to trust-plane files.
Violations during code review by intermediate-reviewer are BLOCK-level findings.

## MUST Rules

### 1. No Bare `open()` or `Path.read_text()` for Record Files

```python
# DO:
from trustplane._locking import safe_read_json, safe_open
data = safe_read_json(path)

# DO NOT:
with open(path) as f:           # Follows symlinks — attacker redirects to arbitrary file
    data = json.load(f)
data = json.loads(path.read_text())  # No symlink protection, no fd safety
```

**Why**: `safe_read_json()` and `safe_open()` use `O_NOFOLLOW` to prevent symlink attacks. Bare `open()` and `Path.read_text()` bypass all protections.

### 2. `validate_id()` on Every Externally-Sourced Record ID

```python
# DO:
from trustplane._locking import validate_id
validate_id(record_id)  # Raises ValueError on "../", "/", null bytes, etc.
path = store_dir / f"{record_id}.json"

# DO NOT:
path = store_dir / f"{user_input}.json"  # Path traversal: "../../../etc/passwd"
cursor.execute(f"SELECT * FROM records WHERE id = '{record_id}'")  # SQL injection
```

**Why**: The regex `^[a-zA-Z0-9_-]+$` prevents directory traversal and SQL injection via IDs. Every method that accepts a record ID or query parameter MUST validate before use.

### 3. `math.isfinite()` on All Numeric Constraint Fields

```python
# DO (in __post_init__ or from_dict):
if self.max_cost is not None and not math.isfinite(self.max_cost):
    raise ValueError("max_cost must be finite")

# DO NOT:
if self.max_cost is not None and self.max_cost < 0:
    raise ValueError("negative")  # NaN passes, Inf passes
```

**Why**: `NaN` and `Inf` bypass numeric comparisons (`NaN < 0` is `False`, `Inf < 0` is `False`). Constraints set to `NaN` make all checks pass silently.

### 4. Bounded Collections (`maxlen=10000`)

```python
# DO:
call_log: deque = field(default_factory=lambda: deque(maxlen=10000))

# DO NOT:
call_log: list = field(default_factory=list)  # Grows without bound -> OOM
```

**Why**: Unbounded collections in long-running processes lead to memory exhaustion. Trim oldest 10% when at capacity.

### 5. Parameterized SQL for All Database Queries

```python
# DO:
cursor.execute("SELECT * FROM decisions WHERE id = ?", (record_id,))
cursor.execute("INSERT INTO decisions (id, data) VALUES (?, ?)", (id, data))

# DO NOT:
cursor.execute(f"SELECT * FROM decisions WHERE id = '{record_id}'")
cursor.execute("INSERT INTO decisions VALUES (" + id + ", " + data + ")")
```

**Why**: f-string interpolation into SQL enables injection. Even validated IDs should use parameterized queries as defense-in-depth.

### 6. SQLite Database File Permissions

```python
# DO (on POSIX):
import os, stat
db_path.touch(mode=0o600)  # Owner read/write only
os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

# DO NOT:
db_path.touch()  # Default permissions may be world-readable
```

**Why**: SQLite database files (`.db`, `-wal`, `-shm`) contain all trust records. Default permissions may expose them to other users on shared systems.

### 7. All Record Writes Through `atomic_write()`

```python
# DO:
from trustplane._locking import atomic_write
atomic_write(path, json.dumps(record.to_dict()))

# DO NOT:
with open(path, 'w') as f:  # Partial write on crash = corrupted record
    json.dump(record, f)
```

**Why**: `atomic_write()` uses temp file + `fsync` + `os.replace()` for crash safety. The `O_NOFOLLOW` flag also prevents symlink attacks during writes.

## MUST NOT Rules

### 1. MUST NOT Use `==` to Compare HMAC Digests

```python
# DO:
import hmac as hmac_mod
if not hmac_mod.compare_digest(stored_hash, computed_hash):
    raise TamperDetectedError(...)

# DO NOT:
if stored_hash != computed_hash:  # Timing side-channel for byte-by-byte forgery
    raise TamperDetectedError(...)
```

**Why**: String equality (`==`) leaks timing information. An attacker can measure comparison time to determine how many bytes match.

### 2. MUST NOT Downgrade Trust State

```python
# CORRECT: Monotonic escalation only
# AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED (only forward)

# FORBIDDEN:
if some_condition:
    verdict = Verdict.AUTO_APPROVED  # Downgrading from HELD is forbidden
```

**Why**: Trust state can only escalate, never relax. A HELD action cannot become AUTO_APPROVED — it must be explicitly resolved through the hold workflow.

### 3. MUST NOT Write Records Without `atomic_write()`

Any filesystem record write that bypasses `atomic_write()` is a security defect. See MUST Rule 7.

### 4. MUST NOT Leave Private Key Material in Memory

```python
# DO:
key_mgr.register_key(key_id, private_key)
del private_key  # Remove reference immediately

# On revocation:
self._keys[key_id] = ""  # Clear material, keep tombstone

# DO NOT:
key_mgr.register_key(key_id, private_key)
# private_key persists in scope — visible to memory dumps
```

**Why**: Private key material in memory is vulnerable to debugger inspection and memory dumps.

### 5. MUST NOT Construct `MultiSigPolicy` as Mutable

```python
# DO:
@dataclass(frozen=True)
class MultiSigPolicy:
    required_signatures: int
    ...

# DO NOT:
@dataclass  # Mutable — fields can be changed after __post_init__ validation
class MultiSigPolicy:
    ...
```

**Why**: Without `frozen=True`, an attacker with object reference can bypass `__post_init__` validation by directly setting fields.

### 8. MUST: Use `normalize_resource_path()` for All Constraint Pattern Storage and Comparison

All constraint patterns and resource paths MUST be normalized via `normalize_resource_path()` before storage or comparison. Direct use of `posixpath.normpath`, `os.path.normpath`, or `Path.as_posix()` for constraint patterns is FORBIDDEN.

```python
# DO:
from trustplane.pathutils import normalize_resource_path
norm = normalize_resource_path(user_path)

# DO NOT:
norm = os.path.normpath(user_path)  # Platform-dependent, Windows produces backslashes
norm = Path(user_path).as_posix()   # Doesn't collapse double slashes
```

**Why**: `os.path.normpath` produces backslashes on Windows, breaking cross-platform constraint matching. `Path.as_posix()` doesn't collapse double slashes. `normalize_resource_path()` provides consistent forward-slash normalization on all platforms.

## Cross-References

- `packages/trust-plane/CLAUDE.md` — Full security pattern inventory (11 patterns) and Store Security Contract
- `packages/trust-plane/src/trustplane/store/__init__.py` — Store Security Contract as protocol docstring (created in TODO-09)
- `.claude/rules/security.md` — Global security rules (secrets, injection, input validation)
- `.claude/rules/eatp.md` — EATP SDK conventions (dataclasses, error hierarchy, cryptography)
