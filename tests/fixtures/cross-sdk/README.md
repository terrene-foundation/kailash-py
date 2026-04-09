# Cross-SDK Test Vectors

This directory contains shared test vectors for cross-SDK semantic parity validation
between `kailash-py` (Python) and `kailash-rs` (Rust) per EATP D6.

## Structure

- `jsonrpc/` — JSON-RPC 2.0 message round-trip vectors (SPEC-01 §7)
- `envelope/` — ConstraintEnvelope serialization vectors (SPEC-07 §5)
- `agent-result/` — Agent execution result equivalence vectors (SPEC-09 §3.3)
- `streaming/` — Streaming event vectors (SPEC-09 §2.5)
- `parser-differential/` — JSON parser differential vectors (SPEC-09 §8.2)

## Governance

Per ADR-008 cross-SDK lockstep:

1. Vector additions/changes MUST be made in matched PRs to both repos
2. CODEOWNERS protection on this directory
3. Test vector hashes recorded for tamper detection
4. Both Python and Rust CI MUST pass against the same vectors

## Format

All vectors are JSON files with explicit schema_version field:

```json
{
  "schema_version": "1.0",
  "name": "test_case_name",
  "input": { ... },
  "expected_output": { ... },
  "metadata": {
    "description": "...",
    "spec_reference": "SPEC-01 §7.1"
  }
}
```

## Loading

Python:

```python
from tests.unit.cross_sdk.conftest import load_vector
vector = load_vector("jsonrpc", "request_simple.json")
```

Rust (matched):

```rust
use kailash_test_vectors::load_vector;
let vector = load_vector("jsonrpc", "request_simple.json")?;
```
