# Cross-SDK Parity

Patterns that keep kailash-py and kailash-rs in semantic sync, catching divergence before it ships.

## Principles

1. **Parity is a continuous property, not a milestone** — checked on every PR, not annually
2. **Public API surface is the parity contract** — internal implementation may differ (Rust idioms vs Python idioms); public signatures, enum variants, and behaviors must match
3. **Divergence is a bug, not a feature** — unless documented as an intentional platform-specific adaptation

## The Problem

kailash-py implements `ProductMode.Parameterized` with full parameter threading (cache key includes params, product function receives params). kailash-rs has the `ProductMode::Parameterized` enum variant but zero implementation behind it — `execute_product()` doesn't accept params, `refresh_cascade()` doesn't thread them, and the cache key ignores them. A Parameterized product in Rust silently degrades to Materialized behavior (cache-never-hits for different param sets).

This was caught by a COC rule (`rules/cross-sdk-inspection.md`) firing manually. It should have been caught by tooling.

## Patterns

### 1. Public API Surface Extraction

**Status**: ABSENT. No automated API surface extraction exists.

**The fix**: A script that extracts the public API surface of each SDK into a normalized format.

```python
# Python API surface extraction (ast-based)
# Extracts: module.class.method(param: type) -> return_type
# Extracts: module.EnumName.VARIANT
# Output: sorted, normalized, diffable

# Expected output:
# dataflow.DataFlow.express.create(model: str, data: dict) -> ModelResult
# dataflow.DataFlow.express.list(model: str, filter: dict) -> list[ModelResult]
# dataflow.ProductMode.Materialized
# dataflow.ProductMode.Parameterized
# dataflow.ProductMode.Virtual
```

```rust
// Rust API surface extraction (syn-based or cargo doc --json)
// Extracts: crate::module::Struct::method(param: Type) -> ReturnType
// Extracts: crate::module::Enum::Variant

// Expected output:
// kailash_dataflow::DataFlow::express::create(model: &str, data: Value) -> Result<Value>
// kailash_dataflow::ProductMode::Materialized
// kailash_dataflow::ProductMode::Parameterized
// kailash_dataflow::ProductMode::Virtual
```

### 2. Normalized Diff for Parity Check

Given two API surface files, a diff tool reports:

```
MISSING IN kailash-rs (present in kailash-py):
  dataflow.DataFlow.express.create: param 'idempotency_key' missing
  dataflow.DataFlow.fabric.execute_product: param 'params' missing
  dataflow.DataFlow.fabric.refresh_cascade: param 'params' missing
  dataflow.BulkResult class: absent (kailash-rs uses raw dict)

MISSING IN kailash-py (present in kailash-rs):
  dataflow.PoolMonitor.metrics: absent

ENUM VARIANT MISMATCH:
  dataflow.ProductMode: variants match [Materialized, Parameterized, Virtual]
  BUT: kailash-rs ProductMode::Parameterized has no implementation (stub)
```

**Key distinction**: The tool checks presence of symbols AND (where possible) behavioral equivalence. A variant that exists but has no match arm in any executor is flagged as "stub variant."

### 3. CI Integration

The parity check runs on every PR to either SDK:

```yaml
# .github/workflows/parity-check.yml
name: Cross-SDK Parity
on:
  pull_request:
    paths: ["crates/**", "packages/**", "src/**"]

jobs:
  parity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: terrene-foundation/kailash-py
          path: kailash-py
      - uses: actions/checkout@v4
        with:
          repository: esperie/kailash-rs
          path: kailash-rs
      - run: python scripts/check-api-parity.py kailash-py/ kailash-rs/
      - run: |
          if [ -s parity-report.txt ]; then
            echo "::warning::Cross-SDK parity gaps found"
            cat parity-report.txt
          fi
```

**Note**: The CI check is a WARNING, not a blocker. Intentional divergence is documented with a `# parity-skip: reason` annotation.

### 4. Parity Annotations for Intentional Divergence

Some features are platform-specific by design. These are annotated.

```python
# Python-only feature (no Rust equivalent needed)
# parity-skip: Python-only — uses asyncio.gather() for concurrent fan-out
async def fan_out(self, tasks: list[Coroutine]) -> list[Result]:
    ...
```

```rust
// Rust-only feature (no Python equivalent needed)
// parity-skip: Rust-only — zero-copy buffer for high-throughput streaming
pub fn zero_copy_stream(&self) -> impl Stream<Item = &[u8]> {
    ...
}
```

The parity tool skips annotated symbols and reports unannotated divergence.

### 5. Behavioral Parity Testing

Beyond API surface matching, behavioral parity requires cross-SDK test suites:

```python
# tests/parity/test_product_mode.py
"""
Cross-SDK behavioral parity test.
Equivalent test exists in kailash-rs: crates/kailash-dataflow/tests/parity/test_product_mode.rs
"""

@pytest.mark.parity
async def test_parameterized_product_caches_independently():
    """Two calls with different params MUST produce different cache entries."""
    db = DataFlow("sqlite:///:memory:")

    @db.product(mode=ProductMode.Parameterized)
    async def price_lookup(ctx, params):
        return await ctx.fetch_price(params["currency"])

    result_usd = await db.fabric.execute_product("price_lookup", params={"currency": "USD"})
    result_eur = await db.fabric.execute_product("price_lookup", params={"currency": "EUR"})

    assert result_usd != result_eur  # different params → different results
    # If this fails in kailash-rs, ProductMode::Parameterized is a stub
```

```rust
// crates/kailash-dataflow/tests/parity/test_product_mode.rs
#[tokio::test]
async fn test_parameterized_product_caches_independently() {
    // Equivalent to Python parity test
    let db = DataFlow::new("sqlite::memory:").await.unwrap();
    // ...
    assert_ne!(result_usd, result_eur);
}
```

**Convention**: Parity tests live in `tests/parity/` in both SDKs. Each test file has a docstring pointing to its counterpart. The test name is identical across SDKs.

## Where It Would Live

| Artifact                       | Location                                                                 |
| ------------------------------ | ------------------------------------------------------------------------ |
| API surface extractor (Python) | `kailash-py/scripts/extract-api-surface.py`                              |
| API surface extractor (Rust)   | `kailash-rs/scripts/extract-api-surface.rs` or `cargo doc --json` parser |
| Parity diff tool               | `loom/scripts/check-api-parity.py` (lives in loom, reads both SDKs)      |
| CI workflow                    | `.github/workflows/parity-check.yml` in both repos                       |
| Parity tests                   | `tests/parity/` in both repos                                            |

## Priority Ranking

| Rank | Component                         | Effort     | Impact                           |
| ---- | --------------------------------- | ---------- | -------------------------------- |
| 1    | API surface extractor (both SDKs) | 2 sessions | Makes divergence visible         |
| 2    | Parity diff tool in loom          | 1 session  | Automates cross-SDK check        |
| 3    | CI integration                    | 1 session  | Catches divergence on every PR   |
| 4    | Behavioral parity tests           | Ongoing    | Proves semantic equivalence      |
| 5    | Parity annotations                | 1 session  | Documents intentional divergence |
