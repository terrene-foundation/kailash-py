---
description: "Canonical JSON module (trust._json) for cross-SDK parser parity — DuplicateKeyError, NaN/Inf rejection, sorted-key deterministic output. Use when asking about 'canonical JSON', 'duplicate keys', 'cross-SDK JSON', 'parser differential', 'DuplicateKeyError', or 'canonical_json_loads'."
---

# Cross-SDK Canonical JSON

Per EATP D6, both Python and Rust SDKs must reach the same conclusion on every JSON input. Python's `json.loads()` silently uses last-wins for duplicate keys; Rust's `serde_json` rejects duplicates by default. This module closes the differential.

## Module: `kailash.trust._json`

```python
from kailash.trust._json import (
    canonical_json_loads,   # Parse with duplicate-key rejection + NaN/Inf rejection
    canonical_json_dumps,   # Deterministic sorted-key output
    DuplicateKeyError,      # Raised on duplicate keys (inherits ValueError)
)
```

## `canonical_json_loads(text: str) -> Any`

Strict JSON parsing that rejects:

- **Duplicate keys** at any nesting level (raises `DuplicateKeyError`)
- **NaN/Infinity/-Infinity** literals (raises `ValueError`) — not valid JSON per RFC 8259
- All `json.loads(strict=True)` rejections (control characters in strings, etc.)

```python
# Duplicate key — Python json.loads silently keeps last value
canonical_json_loads('{"a": 1, "a": 2}')
# → DuplicateKeyError: duplicate key 'a'

# NaN — Python json.loads accepts by default
canonical_json_loads('{"value": NaN}')
# → ValueError: Invalid JSON constant 'NaN'
```

## `canonical_json_dumps(obj: Any) -> str`

Deterministic serialization:

- Keys sorted alphabetically at every nesting level
- Compact separators (`,` `:`) — no whitespace
- `ensure_ascii=False` — UTF-8 passes through

```python
canonical_json_dumps({"b": 2, "a": 1})
# → '{"a":1,"b":2}'
```

## `DuplicateKeyError`

```python
class DuplicateKeyError(ValueError):
    key: str   # The duplicate key name
    path: str  # JSON path location (e.g., "$.nested")
```

## When to Use

- All cross-SDK deserialization paths (trust records, EATP envelopes, PACT verdicts)
- Any JSON round-trip where Python→Rust or Rust→Python parity matters
- Audit log serialization (deterministic output for HMAC verification)

## Parser Differential Edge Cases

| Input                 | Python `json.loads`     | Rust `serde_json` | `canonical_json_loads` |
| --------------------- | ----------------------- | ----------------- | ---------------------- |
| `{"a":1,"a":2}`       | `{"a": 2}` (last wins)  | Error             | `DuplicateKeyError`    |
| `NaN`                 | `float('nan')`          | Error             | `ValueError`           |
| `Infinity`            | `float('inf')`          | Error             | `ValueError`           |
| `"\x00"` in string    | Accepted (strict=False) | Accepted          | Rejected (strict=True) |
| Trailing comma `[1,]` | Error                   | Error             | Error                  |
| Comments `// ...`     | Error                   | Error             | Error                  |
| Single quotes `'a'`   | Error                   | Error             | Error                  |
| BOM prefix            | Accepted                | Error             | Rejected (strict=True) |
