# Kailash Kaizen -- Domain Specification — Error Handling

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers error handling — BaseAgent's `_handle_error` extension point, retry via RetryMixin, the fallback strategy, and provider-error wrapping. Split from `kaizen-providers.md` (specs-authority.md Rule 8 — the original file exceeded the 300-line split threshold). Sibling sub-files covering the rest of the parent domain: `kaizen-providers.md` (index), `kaizen-providers-provider-system.md`, `kaizen-providers-execution-strategies.md`, `kaizen-providers-tool-integration.md`, `kaizen-providers-memory-system.md`, `kaizen-providers-error-handling.md`, `kaizen-providers-streaming.md`. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## 20. Error Handling

### 20.1 BaseAgent Error Handling

The `_handle_error` extension point controls error behavior:

- When `error_handling_enabled=True` (default): logs error, returns `{"error": str, "type": class_name, "success": False}`.
- When `error_handling_enabled=False`: re-raises the exception.

### 20.2 Retry via RetryMixin

Applied when `error_handling_enabled=True` in config. Wraps execution with configurable retry logic.

### 20.3 Fallback Strategy

`FallbackStrategy` provides sequential fallback:

```python
strategy = FallbackStrategy(strategies=[
    primary_strategy,
    degraded_strategy,
    minimal_strategy,
])
```

Tries each strategy in order. First success wins.

### 20.4 Provider Errors

All provider-specific exceptions are wrapped into the `ProviderError` hierarchy (`kaizen-providers-provider-system.md` § 8.4). Consumers never need to depend on provider SDK exception types.

