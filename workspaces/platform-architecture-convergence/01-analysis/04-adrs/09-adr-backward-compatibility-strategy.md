# ADR-009: Backward Compatibility Strategy

**Status**: ACCEPTED (2026-04-07)
**Scope**: Release process — governs all convergence changes
**Deciders**: Platform Architecture Convergence workspace

## Context

The convergence touches millions of lines of code and thousands of external consumers:

- **188 BaseAgent subclasses** across the monorepo
- **~600 tests** exercising BaseAgent surface area
- **Unknown thousands of external users** importing from `kailash.mcp_server`, `kaizen_agents.delegate.*`, `kailash.trust.chain.ConstraintEnvelope`, etc.
- **CI pipelines** that run against specific version combinations
- **Downstream projects** (dev/, terrene/, tpc/, rr/, hmi/, projects/) that pin kailash-py to specific versions
- **Demo/example code** published in docs and tutorials

The brief's hard constraint: **"Zero net regressions. Every test that passes today must pass after the rework. Existing user code must work unchanged."**

This creates tension with the convergence goals:

- ADR-001 deprecates 7 BaseAgent extension points — but tests use them
- ADR-004 moves MCP code to `packages/kailash-mcp/` — but users import from old paths
- ADR-005 splits `ai_providers.py` — but code references specific class names
- ADR-006 unifies ConstraintEnvelope — but 3 old types are in use
- ADR-007 rewrites Delegate internals — but users have `Delegate(...)` calls

**We need a deprecation strategy** that lets the convergence happen without breaking production on release day.

### What the red team said

Red team round 1 item #5:

> "`from kailash.mcp_server.client import MCPClient` is at `base_agent.py:40`. After MCP moves, this import path breaks unless backward-compat shims are published. Thousands of import sites depend on `from kailash.mcp_server import ...`. Required: shim lifetime, deprecation mechanism, removal version."

## Decision

**Backward compatibility spans TWO minor versions + ONE major version boundary. The convergence ships incrementally with explicit deprecation warnings, followed by removal in v3.0.**

### Version strategy

```
v2.current    (today, pre-convergence)
    ↓
v2.next       (convergence lands — new packages exist, old paths work via shims, deprecation warnings emitted)
    ↓
v2.next+1     (convergence stable — same shims, fewer deprecation warnings, more tests migrated)
    ↓
v2.next+2     (convergence polish — prepare for v3.0)
    ↓
v3.0          (breaking changes — old paths removed, final convergence target reached)
```

Two full minor-version lives for the shims. Typical calendar: **3-6 months** between v2.x minor releases, so shims live ~9-18 months before removal.

### Applies to all convergence changes

The same strategy applies to:

- MCP extraction (ADR-004)
- Provider split (ADR-005)
- ConstraintEnvelope unification (ADR-006)
- BaseAgent extension points (ADR-001)
- Delegate facade rewrite (ADR-007)
- Nexus auth migration (separate SPEC)

### The four layers of backward compatibility

#### Layer 1 — Re-export shims

**Purpose**: Preserve import paths that users rely on.

```python
# src/kailash/mcp_server/__init__.py (v2.x shim)
"""
DEPRECATED: This module has moved to `kailash_mcp`.

`from kailash.mcp_server import MCPClient` still works but emits a
DeprecationWarning. Migrate to `from kailash_mcp import MCPClient`.

This shim will be removed in v3.0.
"""
import warnings as _warnings

_warnings.warn(
    "kailash.mcp_server is deprecated since v2.next. "
    "Use `from kailash_mcp import ...` instead. "
    "This shim will be removed in v3.0 (earliest: 2026-10-01).",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new location
from kailash_mcp import (
    MCPClient,
    MCPServer,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcError,
    McpError,
    ServiceRegistry,
    LoadBalancer,
    HealthChecker,
    # ... full public API
)
from kailash_mcp.auth import APIKeyAuth, JWTAuth, OAuth2Auth, BasicAuth
from kailash_mcp.transports import (
    StdioTransport, HTTPTransport, SSETransport, WebSocketTransport
)

__all__ = [
    "MCPClient", "MCPServer", "JsonRpcRequest", "JsonRpcResponse",
    "JsonRpcError", "McpError", "ServiceRegistry", "LoadBalancer",
    "HealthChecker", "APIKeyAuth", "JWTAuth", "OAuth2Auth", "BasicAuth",
    "StdioTransport", "HTTPTransport", "SSETransport", "WebSocketTransport",
]
```

**Rules for shims**:

1. MUST re-export the full public API of the old module
2. MUST emit `DeprecationWarning` with:
   - Current version ("deprecated since vX.Y")
   - Replacement import path
   - Removal version ("removed in v3.0")
   - Earliest removal date (no earlier than X months after deprecation)
3. MUST use `stacklevel=2` so the warning points at user code, not the shim
4. Shim files MUST be listed in a `DEPRECATED_MODULES` constant for CI verification
5. Shim files MUST NOT be edited after being written — they only get deleted in v3.0

#### Layer 2 — Class-level aliases

**Purpose**: Preserve subclass hierarchies and `isinstance()` checks.

```python
# src/kailash/trust/chain.py (v2.x shim)
"""DEPRECATED: ConstraintEnvelope moved to kailash.trust.envelope."""
import warnings as _warnings

from kailash.trust.envelope import ConstraintEnvelope as _CanonicalConstraintEnvelope

class ConstraintEnvelope(_CanonicalConstraintEnvelope):
    """Deprecated alias for `kailash.trust.envelope.ConstraintEnvelope`.

    This class is a thin subclass that emits a deprecation warning on construction.
    It is bitwise identical to the canonical type (inherits all fields and methods).

    isinstance() checks against both old and new forms continue to work:
        isinstance(obj, chain.ConstraintEnvelope) → True
        isinstance(obj, envelope.ConstraintEnvelope) → True
    """

    def __init__(self, *args, **kwargs):
        _warnings.warn(
            "kailash.trust.chain.ConstraintEnvelope is deprecated since v2.next. "
            "Use `from kailash.trust import ConstraintEnvelope` instead. "
            "Removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
```

**Rules for class aliases**:

1. Subclass the canonical type to preserve `isinstance()` behavior
2. Override `__init__` to emit deprecation warning
3. Do NOT override any other methods — behavior must match canonical type exactly
4. If the canonical type is a frozen dataclass, use `__class_getitem__` trick or `object.__setattr__` as appropriate

#### Layer 3 — Deprecated method decorator

**Purpose**: Preserve method-level API surfaces (BaseAgent's 7 extension points).

```python
# src/kailash/_deprecation.py
from functools import wraps
import warnings
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)

def deprecated(
    since: str,
    removed_in: str,
    use_instead: str,
    category: type[Warning] = DeprecationWarning,
) -> Callable[[F], F]:
    """Mark a function/method as deprecated.

    Usage::

        @deprecated(
            since="2.next",
            removed_in="3.0",
            use_instead="pass signature= parameter to BaseAgent.__init__",
        )
        def _default_signature(self) -> Signature:
            ...
    """
    def decorator(func: F) -> F:
        message = (
            f"{func.__qualname__} is deprecated since v{since}. "
            f"Use instead: {use_instead}. "
            f"Removed in v{removed_in}."
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(message, category, stacklevel=2)
            return func(*args, **kwargs)

        wrapper.__doc__ = f"**Deprecated**: {message}\n\n" + (func.__doc__ or "")
        wrapper.__is_deprecated__ = True  # for static analysis
        return wrapper  # type: ignore

    return decorator
```

Applied to BaseAgent extension points:

```python
# src/kailash/kaizen/core/base_agent.py
class BaseAgent(Node):
    # ... slim core implementation ...

    @deprecated(
        since="2.next",
        removed_in="3.0",
        use_instead="pass signature= parameter to __init__, or use a SignatureWrapper",
    )
    def _default_signature(self) -> Optional[Signature]:
        """Extension point: provide agent-specific signature.

        DEPRECATED: Use constructor parameter instead.
        """
        return None

    @deprecated(since="2.next", removed_in="3.0", use_instead="...")
    def _default_strategy(self): ...

    @deprecated(since="2.next", removed_in="3.0", use_instead="...")
    def _generate_system_prompt(self) -> str: ...

    # ... etc for all 7 extension points
```

**Rules for deprecated methods**:

1. The deprecated method MUST still work (not just warn and raise)
2. The method body calls into the new canonical implementation where possible
3. Subclass overrides still work — the deprecation warning comes from the base class's method, which is still called by the override via `super()` or via test code that calls the deprecated method directly

#### Layer 4 — Deprecated constructor parameters

**Purpose**: Preserve constructor signatures when parameters are renamed or removed.

```python
class BaseAgent(Node):
    def __init__(
        self,
        config: BaseAgentConfig,
        *,
        signature: Optional[Signature] = None,
        tools: Optional[list] = None,
        # ... new parameters ...

        # Deprecated parameters (still accepted, warn on use)
        strategy: Optional[Any] = _SENTINEL,
        mcp_servers: Optional[list] = _SENTINEL,
        **legacy_kwargs,
    ):
        # Handle deprecated parameters
        if strategy is not _SENTINEL:
            warnings.warn(
                "BaseAgent(strategy=...) is deprecated since v2.next. "
                "Strategy selection is automatic based on config.execution_mode. "
                "Removed in v3.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Translate old API to new API
            if strategy == "multi_cycle":
                config.execution_mode = "autonomous"

        if mcp_servers is not _SENTINEL:
            warnings.warn(
                "BaseAgent(mcp_servers=...) is deprecated since v2.next. "
                "Call .configure_mcp(mcp_servers) after construction, "
                "or use Delegate(mcp_servers=...) for the engine facade. "
                "Removed in v3.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Still honor the old behavior
            self._legacy_mcp_servers = mcp_servers

        # Warn on any other unknown kwargs
        if legacy_kwargs:
            warnings.warn(
                f"BaseAgent got unknown kwargs: {list(legacy_kwargs.keys())}. "
                f"These may be legacy extension point parameters. "
                f"Removed in v3.0.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Proceed with canonical initialization
        ...
```

### Per-change deprecation matrix

| ADR        | Change                         | Old API                                                                                                                 | Deprecation shim                                | Removal |
| ---------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------- |
| 001        | BaseAgent extension points     | `_default_signature()`, `_default_strategy()`, etc.                                                                     | `@deprecated` method decorator (Layer 3)        | v3.0    |
| 002        | Node inheritance               | (none — preserved)                                                                                                      | N/A                                             | N/A     |
| 003        | Streaming via StreamingAgent   | (none — new capability)                                                                                                 | N/A                                             | N/A     |
| 004        | kailash-mcp package            | `kailash.mcp_server.*`, `kaizen_agents.delegate.mcp`                                                                    | Re-export shims (Layer 1)                       | v3.0    |
| 005        | Provider split                 | `kaizen.nodes.ai.ai_providers`                                                                                          | Re-export shim with class aliases (Layer 1 + 2) | v3.0    |
| 006        | ConstraintEnvelope unification | `trust.chain.ConstraintEnvelope`, `trust.plane.models.ConstraintEnvelope`, `trust.pact.config.ConstraintEnvelopeConfig` | Class aliases (Layer 2)                         | v3.0    |
| 007        | Delegate facade                | `kaizen_agents.delegate.*` subpackage                                                                                   | Re-export shim (Layer 1)                        | v3.0    |
| Nexus auth | Migration to kailash.trust     | `nexus.auth.*` modules                                                                                                  | Re-export shim (Layer 1) with gradual migration | v3.0    |

### CI enforcement

```yaml
# .github/workflows/deprecation-check.yml
name: Deprecation Check
on: [push, pull_request]
jobs:
  deprecation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify shims exist
        run: |
          # DEPRECATED_MODULES lists every file expected to contain a shim
          for module in $(cat .deprecated-modules); do
            grep -q "DeprecationWarning" "$module" || {
              echo "::error::Missing deprecation warning in $module"
              exit 1
            }
          done
      - name: Run tests in deprecation-strict mode
        run: |
          # Treat all DeprecationWarning as errors — but only in NEW test code
          # (test files modified in this PR)
          pytest -W error::DeprecationWarning --deprecation-strict-new-only
```

### Removal checklist (for v3.0)

When cutting v3.0, the release PR MUST:

1. Run the grep: `grep -r "from kailash.mcp_server" src/ tests/ packages/ examples/` — MUST return zero results (outside the shim file itself)
2. Run the grep for each deprecated import path — MUST return zero results
3. Delete all shim files listed in `.deprecated-modules`
4. Delete the `@deprecated` decorator usages (keep the decorator itself — it's used by future deprecations)
5. Remove deprecated constructor parameters (can delete `**legacy_kwargs` handling)
6. Update all subclasses that still use deprecated methods
7. Run full test suite with `-W error::DeprecationWarning` to verify zero deprecations remain
8. Update migration guide with removal confirmation

### Migration guide

Every minor version with deprecations ships with a migration guide at:
`docs/migration/v2.next-to-v2.next+1.md` and eventually `docs/migration/v2.next-to-v3.0.md`

Format:

````markdown
# Migrating from v2.X to v3.0

## Quick check

Run this in your codebase:

    python -m kailash.migration_check

This will scan your imports and code for v2.x patterns that don't work in v3.0.

## Breaking changes

### kailash.mcp_server → kailash_mcp

**Before**:

```python
from kailash.mcp_server import MCPClient
from kailash.mcp_server.auth import APIKeyAuth
```
````

**After**:

```python
from kailash_mcp import MCPClient
from kailash_mcp.auth import APIKeyAuth
```

**Why**: MCP protocol types consolidated into a standalone package for cross-SDK interop. See ADR-004.

### BaseAgent extension points

**Before**:

```python
class MyAgent(BaseAgent):
    def _default_signature(self):
        return MySignature()

    def _generate_system_prompt(self):
        return "You are a code reviewer."
```

**After**:

```python
agent = BaseAgent(
    config=cfg,
    signature=MySignature,
    system_prompt="You are a code reviewer.",
)
```

**Why**: Composition over extension points. See ADR-001.

### ConstraintEnvelope unification

**Before**:

```python
from kailash.trust.chain import ConstraintEnvelope as ChainEnv
from kailash.trust.plane.models import ConstraintEnvelope as PlaneEnv
from kailash.trust.pact.config import ConstraintEnvelopeConfig as PactEnv
```

**After**:

```python
from kailash.trust import ConstraintEnvelope  # ONE canonical type
```

**Why**: See ADR-006. Field-by-field semantic diff in SPEC-07.

<!-- etc for all 9 ADRs -->

```

## Rationale

1. **Zero net regressions constraint is load-bearing.** The brief explicitly requires "every test that passes today passes after the rework, existing user code works unchanged." Shims are the only way to honor this while still achieving the convergence.

2. **Two minor versions is the industry standard.** Most Python/Rust libraries give users 2 minor versions to migrate. Anything less is hostile; anything more is never removing anything.

3. **The four-layer approach handles every deprecation mode.** Import path changes → Layer 1. Class aliases → Layer 2. Method deprecations → Layer 3. Parameter deprecations → Layer 4. Any migration can be expressed as a composition of these four mechanisms.

4. **CI enforcement prevents drift.** Deprecation warnings that aren't monitored become noise users ignore. `-W error::DeprecationWarning` in strict mode for new code catches regressions.

5. **Clear removal version (v3.0) sets expectations.** Users know the deadline. Automation (e.g., `pyupgrade`) can target v3.0 as a mechanical rewrite.

6. **Matches cross-SDK lockstep (ADR-008).** Both Python and Rust deprecate in matched minor versions and remove in matched v3.0.

7. **Migration guide as first-class deliverable.** Users get concrete before/after examples, not just release notes.

## Consequences

### Positive

- ✅ Zero net regressions constraint honored
- ✅ Users get 9-18 months to migrate (2 full minor version lives)
- ✅ Clear deprecation path with explicit removal version
- ✅ CI enforces that shims exist and emit warnings correctly
- ✅ Migration guide provides concrete examples
- ✅ `python -m kailash.migration_check` tool helps users audit their codebase
- ✅ Matches cross-SDK lockstep (ADR-008)

### Negative

- ❌ Shims add maintenance burden during v2.x (2+ minor versions)
- ❌ Deprecation warnings can be noisy if users don't filter them
- ❌ `@deprecated` decorator adds tiny runtime overhead (one function call)
- ❌ Test suite runs with deprecation noise during v2.x — CI must filter or suppress
- ❌ v3.0 release is large (all shims removed at once) — "big bang" removal

### Neutral

- Shim files are ~50-200 lines each and require no ongoing logic changes once written
- Migration guide is written once during `/codify` phase and updated only if the strategy changes

## Alternatives Considered

### Alternative 1: No backward compat — v3.0 is the convergence release

**Rejected**. Violates zero-net-regressions constraint. Breaks 188 subclasses, ~600 tests, thousands of downstream users on release day. Politically untenable.

### Alternative 2: One minor version deprecation window

**Rejected**. Too short. Users often need a full release cycle just to notice the deprecation. One minor version = ~3 months = too aggressive.

### Alternative 3: Three or more minor versions

**Rejected**. Too long. Shims become permanent fixtures. The convergence never actually completes because every minor version has to maintain the shims. Two minor versions is the sweet spot.

### Alternative 4: Forever-backward-compat (no removal)

**Rejected**. Defeats the purpose of convergence. Means the codebase always has both the old and new paths. The architectural debt this workspace is solving gets re-accumulated.

### Alternative 5: Breaking changes in v2.x patch releases

**Rejected**. Violates semver. Breaks trust with users who rely on patch releases being safe.

## Implementation Notes

### Shim file inventory

During implementation, maintain a file at `.deprecated-modules` listing every shim:

```

# Format: path deprecated_since removed_in replacement

src/kailash/mcp_server/**init**.py 2.next 3.0 kailash_mcp
src/kailash/mcp_server/client.py 2.next 3.0 kailash_mcp.client
src/kailash/mcp_server/server.py 2.next 3.0 kailash_mcp.server
src/kailash/mcp_server/auth.py 2.next 3.0 kailash_mcp.auth
src/kailash/mcp_server/transports.py 2.next 3.0 kailash_mcp.transports
src/kailash/trust/chain.py#ConstraintEnvelope 2.next 3.0 kailash.trust.envelope.ConstraintEnvelope
src/kailash/trust/plane/models.py#ConstraintEnvelope 2.next 3.0 kailash.trust.envelope.ConstraintEnvelope
src/kailash/trust/pact/config.py#ConstraintEnvelopeConfig 2.next 3.0 kailash.trust.envelope (with Pydantic adapter)
packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py 2.next 3.0 kaizen.providers
packages/kaizen-agents/src/kaizen_agents/delegate/**init**.py 2.next 3.0 kaizen_agents (top-level)
packages/kaizen-agents/src/kaizen_agents/delegate/loop.py 2.next 3.0 kaizen.core.agent_loop
packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py 2.next 3.0 kailash_mcp.client
packages/kaizen-agents/src/kaizen_agents/delegate/adapters/ 2.next 3.0 kaizen.providers
packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py 2.next 3.0 kailash_mcp.tools.hydrator
packages/kailash-nexus/src/nexus/auth/jwt.py 2.next 3.0 kailash.trust.jwt
packages/kailash-nexus/src/nexus/auth/rbac.py 2.next 3.0 kailash.trust.rbac
packages/kailash-nexus/src/nexus/trust/headers.py 2.next 3.0 kailash.trust.headers
packages/kailash-nexus/src/nexus/trust/middleware.py 2.next 3.0 kailash.trust.middleware
packages/kailash-nexus/src/nexus/trust/session.py 2.next 3.0 kailash.trust.session

````

Total shim file count: ~20 files initially, growing as refactor continues.

### Migration check tool

```python
# packages/kailash-kaizen/src/kaizen/migration_check.py
"""
Scan a Python codebase for deprecated v2.x import patterns.

Usage::

    python -m kailash.migration_check [path]
    python -m kailash.migration_check --fix [path]  # auto-rewrite
"""

import ast
import sys
from pathlib import Path
from dataclasses import dataclass

DEPRECATED_IMPORTS = {
    "kailash.mcp_server": "kailash_mcp",
    "kailash.mcp_server.auth": "kailash_mcp.auth",
    "kailash.mcp_server.transports": "kailash_mcp.transports",
    "kailash.trust.chain.ConstraintEnvelope": "kailash.trust.ConstraintEnvelope",
    "kailash.trust.plane.models.ConstraintEnvelope": "kailash.trust.ConstraintEnvelope",
    "kailash.trust.pact.config.ConstraintEnvelopeConfig": "kailash.trust.ConstraintEnvelope",
    "kaizen_agents.delegate.loop": "kaizen.core.agent_loop",
    "kaizen_agents.delegate.mcp": "kailash_mcp.client",
    "kaizen_agents.delegate.adapters": "kaizen.providers",
    # ... full list
}

DEPRECATED_CLASS_USAGE = {
    "BaseAgent._default_signature": "pass signature= parameter",
    "BaseAgent._default_strategy": "use config.execution_mode",
    "BaseAgent._generate_system_prompt": "pass system_prompt= parameter",
    # ... full list
}

@dataclass
class Finding:
    file: Path
    line: int
    old_pattern: str
    new_pattern: str
    severity: str  # ERROR | WARNING

def scan(path: Path) -> list[Finding]:
    ...

def fix(path: Path, findings: list[Finding]) -> None:
    """Auto-rewrite where safe (import paths only; not method renames)."""
    ...

def main():
    ...
````

### Release gates

Before each v2.x release:

1. All new code added in the release MUST NOT emit deprecation warnings
2. Shim files MUST exist for every removal scheduled in v3.0
3. Migration guide MUST be updated with any new deprecations

Before v3.0 release:

1. All shim files listed in `.deprecated-modules` are deleted
2. No code in `src/`, `packages/`, `tests/`, `examples/` imports from deprecated paths
3. Migration guide has final "removed in v3.0" section
4. All downstream projects (dev/, terrene/, tpc/) have been updated (tracked in separate release checklist)

## Related ADRs

- **ADR-001**: Composition over extension points (deprecates 7 BaseAgent extension points)
- **ADR-004**: kailash-mcp package boundary (triggers import path shims)
- **ADR-005**: Provider capability protocol split (triggers class aliases)
- **ADR-006**: Single ConstraintEnvelope type (triggers class aliases for 3 types)
- **ADR-007**: Delegate as composition facade (triggers subpackage shim)
- **ADR-008**: Cross-SDK lockstep (deprecation windows must match across SDKs)

## Related Documents

- Brief: "zero net regressions" constraint
- `rules/zero-tolerance.md` — zero-tolerance for stubs (shims are NOT stubs, they're backward-compat forwarding)
- `rules/git.md` — branch protection (v3.0 release requires admin-bypass merge)
