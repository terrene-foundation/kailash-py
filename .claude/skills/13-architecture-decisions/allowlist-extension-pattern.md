# Allowlist Extension Pattern

When an allowlist-based validator needs to accept user extensions, the cheap fix is to open the allowlist — remove the check, accept anything that looks duck-typed-correct. That fix is wrong; it demotes the allowlist from a security boundary to a naming convention. This skill describes the correct pattern: keep the built-in allowlist closed, add an explicit `register_<thing>()` API with a registry fallback that fires only AFTER the built-in downcast fails, and gate the fallback on an identity-keyed registry so the extension is as auditable as a built-in.

Generalizes beyond any single domain — applies to plugin registries, node-type dispatchers, middleware matchers, policy adapters, codec registries, and any component where "accept this unknown thing" is a user-facing API.

## When To Apply This Pattern

Apply when:

- A validator / dispatcher has a closed set of built-in types and a user has asked to extend it
- The extension call site crosses a language or framework boundary (Rust→Python, kernel→module, host→plugin)
- The extension acceptance MUST remain auditable (which types are registered, who registered them)
- Duck-typed dispatch is tempting but would let arbitrary untrusted types flow through the validator

Do NOT apply when:

- The allowlist is purely advisory (e.g. "allowed log levels") — just widen it
- The extension set is static and known at compile time — promote the type to the built-in list

## The Pattern In Four Steps

### 1. Keep The Built-In Allowlist Closed

The fast path MUST stay closed. A registration API does NOT demote the built-in check — it runs in addition, after the built-in returns "not found."

```python
# DO — built-in allowlist first, registry fallback second
class EstimatorDispatcher:
    _BUILTIN = {
        "RandomForestClassifier": _to_rf_classifier,
        "LogisticRegression":     _to_logreg,
        "KMeans":                 _to_kmeans,
    }

    def dispatch(self, obj):
        cls_name = type(obj).__name__
        if cls_name in self._BUILTIN:
            return self._BUILTIN[cls_name](obj)
        # Fallback (step 2) — but only AFTER the built-in miss
        return self._dispatch_registered(obj)

# DO NOT — duck-typed dispatch with no registry
class EstimatorDispatcher:
    def dispatch(self, obj):
        # "if it has fit() and predict() it must be an estimator"
        if hasattr(obj, "fit") and hasattr(obj, "predict"):
            return obj  # accepts literally anything with those method names
```

### 2. Add `register_<thing>()` With Identity-Keyed Storage

The registry MUST key entries by object identity (`id()` in Python, `TypeId` in Rust, class reference not name) so that a third-party class named `LogisticRegression` cannot shadow the built-in.

```python
# DO — identity-keyed registry
class EstimatorDispatcher:
    def __init__(self):
        self._registered: dict[int, Callable] = {}  # id(class) → converter

    def register_estimator(
        self,
        cls: type,
        converter: Callable[[object], Estimator],
    ) -> None:
        """Register a non-builtin class as an estimator.

        The class is keyed by id() so that name collisions with built-ins
        never resolve to the registered version — the built-in allowlist
        always wins.
        """
        self._registered[id(cls)] = converter

    def _dispatch_registered(self, obj):
        converter = self._registered.get(id(type(obj)))
        if converter is None:
            raise UnregisteredTypeError(
                f"{type(obj).__module__}.{type(obj).__name__} is not a built-in "
                f"estimator and has not been registered. To use this type, call:\n"
                f"    dispatcher.register_estimator({type(obj).__name__}, "
                f"your_converter)"
            )
        return converter(obj)
```

### 3. Error Messages Name The Type AND The Registration Command

The `UnregisteredTypeError` MUST name:

- The fully-qualified type name (`module.ClassName`) of the unregistered value
- The exact API call needed to register it (including the class name, not a placeholder)

```python
# DO — self-healing error message
raise UnregisteredTypeError(
    f"{type(obj).__module__}.{type(obj).__name__} is not a built-in "
    f"estimator and has not been registered. To use this type, call:\n"
    f"    dispatcher.register_estimator({type(obj).__name__}, your_converter)"
)

# DO NOT — opaque error
raise ValueError(f"Unknown estimator: {obj}")
# ↑ user has no idea how to fix this
```

### 4. Built-In Wins Over Registered (Never The Reverse)

If step 1 is kept strict (built-in returns a match before the registry is consulted), this invariant holds automatically. Tests MUST assert the invariant explicitly so a future refactor cannot invert the lookup order.

```python
# DO — regression test that pins the ordering
def test_builtin_wins_over_registered():
    """A user-registered class named the same as a built-in MUST NOT shadow it."""
    class LogisticRegression:  # deliberately shadows sklearn's name
        pass

    dispatcher = EstimatorDispatcher()
    dispatcher.register_estimator(LogisticRegression, _fake_converter)

    real_logreg = sklearn.linear_model.LogisticRegression()
    result = dispatcher.dispatch(real_logreg)

    # Built-in converter ran, not the fake one
    assert isinstance(result, Estimator)
    assert not _fake_converter.called
```

## When The Pattern Adds A Registry API (Not Just A Check)

The pattern opens exactly one new API — `register_<thing>()`. It does NOT open:

- An "accept anything with these methods" duck-typed fast path
- A per-call `allow_unknown=True` flag (once, per-type is stronger than per-call)
- An env-var or config-file override that bypasses the registry

```python
# DO NOT — per-call escape hatch
dispatcher.dispatch(obj, allow_unknown=True)
# ↑ every call site now makes a security decision; registry is bypassed

# DO NOT — config-file override
# config.yaml:
#   allowed_extensions:
#     - foo.MyEstimator
# ↑ registration-by-string; no identity check, typo = silent acceptance
```

**Why:** Escape hatches destroy auditability. The registry IS the audit log — listing `dispatcher._registered` tells you exactly which extensions are trusted. A per-call flag or config string moves the decision out of the code's control flow into prose, and the security reviewer has nothing to grep for.

## Cross-Language Notes

### Rust (TypeId-keyed)

The same pattern in Rust uses `TypeId::of::<T>()` as the key and the registered converter is a boxed closure. The fallback runs after the built-in `downcast_ref` chain fails:

```python
# Pattern translated to Python — in Rust, substitute:
#   id(cls)        → TypeId::of::<T>()
#   dict           → HashMap<TypeId, Box<dyn Fn(...) -> ...>>
#   isinstance     → downcast_ref
```

### Plugin Registries (Native cdylib, WASM)

Plugin registries already register by URI or symbol. The pattern applies at the plugin's own type-dispatcher surface, not at the plugin-host boundary — the host already enforces a signature/capability allowlist.

## Related Patterns & Rules

- `rules/agent-reasoning.md` — "explicit intent" mandate; register\_<thing>() is the explicit intent form
- `rules/zero-tolerance.md` Rule 2 — a `register_<thing>()` with no call site in the framework is a stub (see `rules/orphan-detection.md` for the facade/wiring contract)
- `rules/orphan-detection.md` — every public API needs a production call site within 5 commits; `register_<thing>()` is documented usage at minimum

## Example Applications

| Domain                | Built-in Allowlist         | register\_\*() API                               |
| --------------------- | -------------------------- | ------------------------------------------------ |
| ML estimator dispatch | sklearn built-ins          | `register_estimator(cls, converter)`             |
| Node registry         | core workflow node types   | `register_node_type(cls, factory)`               |
| Middleware matcher    | framework middleware       | `register_middleware(cls, matcher)`              |
| Codec registry        | built-in json/msgpack/yaml | `register_codec(mime, serializer, deserializer)` |
| Policy adapter        | built-in RBAC/ABAC         | `register_policy(cls, adapter)`                  |

Origin: 2026-04-17 — `kailash.ml.Pipeline` / `FeatureUnion` / `ColumnTransformer` shared dispatch helpers; a hardcoded allowlist rejected user-defined estimators with no extension path. Fixed by adding `register_estimator()` with a fallback that runs after the built-in downcast fails, identity-keyed so name collisions never shadow built-ins. The pattern generalizes to any framework with an allowlist-based dispatcher.
