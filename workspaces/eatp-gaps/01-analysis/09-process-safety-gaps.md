# Process Safety Gaps — FilesystemStore

**Date**: 2026-03-14
**Source**: Cross-SDK comparison (kailash-py vs kailash-rs vs TrustPlane)
**Status**: NEW — discovered after main analysis

---

## The Problem

kailash-py has thread-safety (`threading.RLock`) but not process-safety. Two separate processes (two CLI sessions, a CI pipeline and a human) hitting the same trust-plane directory can corrupt state via TOCTOU races.

kailash-rs already solved this with `fs4` cross-process file locking. kailash-py is the lagging implementation.

---

## SDK Comparison

| Capability                 | kailash-py                      | kailash-rs                  | TrustPlane                          |
| -------------------------- | ------------------------------- | --------------------------- | ----------------------------------- |
| Thread-level locking       | `threading.RLock`               | `tokio::sync::Mutex`        | None                                |
| Cross-process file locking | **No**                          | `fs4` (exclusive + shared)  | `fcntl.flock` in project.py only    |
| Atomic writes              | `os.replace` (temp-then-rename) | write + flush + unlock      | No                                  |
| TransactionContext         | Yes (InMemoryStore only)        | No                          | No                                  |
| Path traversal prevention  | **Not found**                   | Yes (regex `[a-zA-Z0-9_-]`) | Just added via `posixpath.normpath` |

---

## New Gaps (Python EATP SDK)

### PS1: Cross-Process File Locking (CRITICAL)

**File**: `FilesystemStore` (likely in `store/` or trust store implementation)

- Upgrade from `threading.RLock` to `fcntl.flock` for all disk writes
- Keep `RLock` as fast path for single-process use
- `fcntl.flock` must be acquired for all disk writes (ESTABLISH, DELEGATE, VERIFY, AUDIT operations that touch filesystem)
- Match kailash-rs's `fs4` behavior

**TOCTOU scenario**:

```
Process 1: reads parent → active
Process 2: reads parent → active (TOCTOU!)
Process 1: writes parent → revoked, cascades children
Process 2: writes child → active under revoked parent (CORRUPTION)
```

### PS2: Export Locking Utility (HIGH)

- Export `file_lock()` as a public context manager, or
- Make `FilesystemStore.transaction()` work for filesystem (currently `TransactionContext` only supports `InMemoryTrustStore`)
- TrustPlane and future SDK consumers shouldn't reinvent cross-process locking

### PS3: Path Traversal Prevention (HIGH — Security)

- kailash-rs validates IDs against `[a-zA-Z0-9_-]` and canonicalizes paths
- kailash-py has no equivalent validation
- Same vulnerability class that was just fixed in TrustPlane exists in the SDK
- Must validate all ID parameters (agent_id, key_id, delegation_id, etc.) before constructing filesystem paths

---

## Impact on Implementation Plan

These gaps should be added to **Phase 1** (Production Safety) since:

- PS1 and PS3 are active safety/security issues, not new features
- PS3 is a security vulnerability (path traversal)
- They follow the same "fix production issues first" rationale as G5/G8/G9/G11
- Low design risk — kailash-rs is the reference implementation

**Revised Phase 1 scope**: G5/G5+, G8/G8+, G9, G11, PS1, PS2, PS3
**Revised Phase 1 effort**: 2 days → **3-4 days** (+1-2 days for process safety)

---

## Implementation Notes

### PS1: fcntl.flock approach

```python
import fcntl
from contextlib import contextmanager

@contextmanager
def file_lock(path: str, exclusive: bool = True):
    """Cross-process file lock using fcntl.flock."""
    lock_path = f"{path}.lock"
    with open(lock_path, 'w') as lock_file:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(lock_file.fileno(), mode)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

### PS3: Path validation

```python
import re

_VALID_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

def validate_id(id_value: str, id_name: str = "id") -> str:
    """Validate ID for filesystem safety. Raises ValueError on invalid input."""
    if not _VALID_ID_PATTERN.match(id_value):
        raise ValueError(f"Invalid {id_name}: must match [a-zA-Z0-9_-], got: {id_value!r}")
    return id_value
```

### Platform considerations

- `fcntl` is Unix-only. For cross-platform support, consider `msvcrt.locking` on Windows or a dependency like `filelock`
- If `filelock` (pip package) is acceptable as a dependency, it handles cross-platform transparently
- Decision needed: Unix-only (`fcntl`) vs cross-platform (`filelock` dependency)
