# Skill: TrustPlane Security Patterns

11 hardened security patterns validated through 14 rounds of red teaming. MANDATORY for `packages/trust-plane/` and `packages/eatp/`. Recommended for any security-sensitive Python project.

For full code examples with DO/DON'T pairs, see `packages/trust-plane/CLAUDE.md`.

## Quick Checklist

| # | Pattern | Violation | Found |
|---|---------|-----------|-------|
| 1 | `validate_id()` before filesystem paths or SQL | `f"{user_input}.json"` without validation | R13 |
| 2 | `O_NOFOLLOW` via `safe_read_json()`/`safe_read_text()` | `open(path)` or `path.read_text()` | R3 |
| 3 | `atomic_write()` for all record writes | `with open(path, 'w')` | R4 |
| 4 | `safe_read_json()` for JSON deserialization | `json.loads(path.read_text())` | R5 |
| 5 | `math.isfinite()` on numeric constraints | Only checking `< 0` (NaN/Inf bypass) | R14 |
| 6 | Bounded collections (`deque(maxlen=)`) | Unbounded `list` in long-running processes | R6 |
| 7 | Monotonic escalation only | Any downgrade of trust state | R7 |
| 8 | `hmac.compare_digest()` for hash comparison | `==` on hashes/tokens/signatures | R14 |
| 9 | Key material zeroization | Private key persisting in scope | R12 |
| 10 | `frozen=True` on security-critical dataclasses | Mutable dataclass bypassing validation | R13 |
| 11 | `from_dict()` validates all fields | Silent defaults on required fields | R8 |

## Store Security Contract (6 Requirements)

Every `TrustPlaneStore` backend MUST satisfy ALL six:

1. **ATOMIC_WRITES** — Crash during write MUST NOT produce partial records
2. **INPUT_VALIDATION** — `validate_id()` on every external ID
3. **BOUNDED_RESULTS** — `limit` parameter on all `list_*()`, default <= 1000, clamp negatives
4. **PERMISSION_ISOLATION** — No cross-project record visibility
5. **CONCURRENT_SAFETY** — No data loss under concurrent writes
6. **NO_SILENT_FAILURES** — Named exceptions, never `None`/`False` error signals

## See Also

- `packages/trust-plane/CLAUDE.md` — Full patterns with code examples
- `.claude/skills/project/store-backend-implementation.md` — Store backend guide
