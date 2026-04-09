---
paths:
  - "pyproject.toml"
  - "Cargo.toml"
  - "package.json"
  - "**/*.py"
  - "**/*.rs"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
---

# Dependency Rules

## Latest Versions Always

All dependencies MUST use the latest stable version. Do not pin to old versions out of caution.

**Why:** Defensive pinning creates a maintenance treadmill where every update requires manual cap-bumping, and the project silently falls behind on security patches, performance improvements, and API fixes.

```toml
# ✅ Uncapped or wide range
pydantic = ">=2.0"
polars = ">=1.0"

# ❌ Defensive caps
pydantic = ">=2.0,<3.0"
polars = ">=1.0,<1.5"
```

## No Caps on Transitive Dependencies

Do NOT add version constraints for packages your code does not directly import. If a package is only a transitive dependency (required by one of your direct dependencies), let the upstream package manage compatibility.

**Why:** Capping a transitive dependency you don't import is purely speculative — you have no code that could break. The upstream package already declares its own compatibility range. Your cap just blocks users from getting updates and creates resolution conflicts.

```toml
# ❌ datasets is used by trl and transformers, not by us
dependencies = ["trl>=0.12", "datasets>=3.0,<4.0"]

# ✅ Only constrain what you import
dependencies = ["trl>=0.12"]
```

**Test:** `grep -r "import datasets" src/` returns zero? Then `datasets` is not your dependency — remove it from `pyproject.toml`.

## Own the Stack — Replace or Re-Implement

If a dependency is unmaintained (no release in 12+ months, unresolved critical issues, archived repo) or constrains your architecture, re-implement it with full API parity. Do not work around a broken or stale package — own the code.

This applies equally to small utilities and large frameworks. If the reference package does X, your replacement MUST do X with identical behavior at the API surface.

**Why:** Unmaintained packages accumulate CVEs, break with new Python/Rust versions, and force the entire ecosystem to work around their bugs. Owning the implementation eliminates the external risk and gives you full control over the API surface, performance, and release cadence.

Process:

1. Identify the full API surface of the reference package that you (or your users) depend on
2. Re-implement with full parity — every public function, class, and behavior
3. Test against the reference package's own test suite where available
4. Provide a drop-in migration path (same import names or thin adapter)
5. Remove the old dependency

## Minimum Version Floors Are Fine

Lower bounds (`>=X.Y`) are appropriate when your code uses features introduced in that version.

**Why:** A floor prevents users from hitting cryptic errors when they install an old version missing the API you call.

```toml
# ✅ We use pydantic v2 model_validator
pydantic = ">=2.0"

# ✅ We use polars LazyFrame.collect_async (added in 0.20)
polars = ">=0.20"
```

## MUST NOT

- Cap a dependency you do not directly import

**Why:** You cannot know when a transitive dependency will break your code because you have no code that uses it. The cap just blocks upgrades.

- Pin exact versions in library pyproject.toml (`==X.Y.Z`)

**Why:** Exact pins in libraries create resolution conflicts for every downstream user who has a different pin.

- Keep unmaintained dependencies — re-implement instead

**Why:** Every unmaintained dependency is a ticking time bomb that will eventually block a Python/Rust version upgrade or introduce a security vulnerability. If you can build it, own it.

- Work around a broken dependency instead of replacing it

**Why:** Workarounds create parallel implementations that diverge from the reference API, doubling maintenance cost and surprising users with behavior differences.

## Declared = Imported — No Silent Missing Dependencies

Every `import X` / `from X import Y` / `use X` / `require('X')` in production code MUST resolve to a package explicitly listed in the project's dependency manifest (`pyproject.toml`, `Cargo.toml`, `package.json`). Transitive resolution through another package is NOT a declaration.

### MUST: Add manifest entry in the same commit as the import

When you add an import, you add the dependency in the same commit. There is no "I'll add it to requirements later".

```python
# DO — import + manifest entry in the same commit
# pyproject.toml: dependencies = [..., "redis>=5.0"]
import redis

# DO NOT — import exists, manifest entry does not
import redis  # works locally because something else installed it; breaks in fresh venv
```

**Why:** Missing manifest entries are invisible on the developer's machine (where the package was installed transitively or manually) and only fail on fresh installs, CI, or production deploy. Every "works locally, breaks in CI" incident traces back to this.

### MUST: Treat dependency resolution errors as blocking failures

The following errors are the SAME class as pre-existing failures in `zero-tolerance.md` Rule 1 — they MUST be fixed immediately, not suppressed:

- `ModuleNotFoundError` / `ImportError` (Python)
- `cannot find crate` / `unresolved import` (Rust)
- `Cannot find module` / `Module not found` (JS/TS)
- Peer dependency warnings during `npm install` / `yarn install`
- `pip check` failures reporting unmet or conflicting requirements

### BLOCKED Anti-Patterns

```python
# Python — BLOCKED: dodging declaration with a silent fallback
try:
    import redis
except ImportError:
    redis = None  # silently degrades; production path never works

# Python — BLOCKED: hiding a missing module from the type checker
import redis  # type: ignore[import]
```

```typescript
// TypeScript — BLOCKED: suppressing module resolution
// @ts-ignore
import { something } from "missing-package";
```

**Why:** Each of these patterns converts a loud, fixable failure ("package not declared") into a silent, cascading one ("feature doesn't work and nobody knows why"). The `try/except ImportError` pattern is particularly dangerous because it makes the import "succeed" with `None`, pushing the failure to a runtime `AttributeError` deep in a code path that only runs in production.

### Exception: Optional Extras with Loud Failure

`try/except ImportError` IS allowed for packages declared as optional extras (`[project.optional-dependencies]`) IF the fallback raises a descriptive error at the call site naming the missing extra. Silent degradation to `None` is still BLOCKED.

```python
# DO — optional extra with loud, actionable failure
try:
    import redis
except ImportError:
    redis = None

def get_cache_client():
    if redis is None:
        raise ImportError("redis backend requires the [redis] extra: pip install kailash[redis]")
    return redis.Redis(...)

# DO NOT — silent None propagation
try:
    import redis
except ImportError:
    redis = None

def get_cache_client():
    return redis.Redis(...) if redis else None  # downstream gets None, fails with AttributeError
```

This exception aligns with `infrastructure-sql.md` Rule 8 (lazy driver imports). The principle: optional dependencies are fine; silent degradation is not.

### Verification step

Before `/redteam` and `/deploy`, run the project's dependency resolver as a verification step:

```bash
# Python — pip check catches unmet/conflicting requirements
pip check

# Node
npm ls --all 2>&1 | grep -iE "missing|warn|err"

# Rust
cargo check --quiet
```

Any unmet, missing, or conflicting dependency BLOCKS the gate.
