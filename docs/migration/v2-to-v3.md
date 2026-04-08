# Migration Guide: Kailash SDK v2.x → v3.0 (Platform Architecture Convergence)

This guide walks you through migrating code from Kailash SDK v2.x to v3.0, which introduces the Platform Architecture Convergence — a major architectural refactor that improves modularity, composability, and cross-SDK parity with `kailash-rs`.

## Overview of Changes

The v3.0 convergence includes:

1. **`kailash-mcp` extracted as a real package** — All MCP code consolidated from 8+ scattered locations
2. **Provider layer split** — 5,001-line monolith broken into per-provider modules
3. **ConstraintEnvelope unification** — Single canonical envelope at `kailash.trust.envelope`
4. **Composition wrappers** — `BaseAgent` slimmed from 3,698 → 891 LOC; new wrapper agents enable composition over inheritance
5. **Delegate as composition facade** — Internal stack of `BaseAgent → L3GovernedAgent → MonitoredAgent`
6. **Audit store consolidation** — Single canonical `AuditStore` with Merkle chain
7. **Nexus auth migration** — Auth/RBAC/SSO/rate-limiting extracted to `kailash.trust.auth.*`

## Backward Compatibility

**v2.x code continues to work in v3.0.** All public APIs are preserved through:

- **Layer 1 — Re-export shims**: Old import paths emit `DeprecationWarning` and re-export from new locations
- **Layer 2 — Class aliases**: `isinstance()` checks work across old and new types
- **Layer 3 — `@deprecated` decorator**: Extension points still work but warn
- **Layer 4 — Removal in v4.0**: Deprecated paths removed in v4.0 (not v3.0)

## Recommended Import Updates

### MCP

```python
# v2.x (still works with DeprecationWarning)
from kailash.mcp_server import MCPClient, MCPServer
from kailash.mcp_server.auth import APIKeyAuth

# v3.0 (recommended)
from kailash_mcp import MCPClient, MCPServer
from kailash_mcp.auth import APIKeyAuth
```

### Providers

```python
# v2.x (still works)
from kaizen.nodes.ai.ai_providers import UnifiedAIProvider

# v3.0 (recommended)
from kaizen.providers import get_provider, get_provider_for_model
from kaizen.providers.llm import OpenAIProvider, AnthropicProvider
```

### ConstraintEnvelope

```python
# v2.x (still works — different abstractions preserved)
from kailash.trust.chain import ConstraintEnvelope
from kailash.trust.plane.models import ConstraintEnvelope
from kailash.trust.pact.config import ConstraintEnvelopeConfig

# v3.0 canonical (recommended for new code)
from kailash.trust.envelope import ConstraintEnvelope, AgentPosture
```

### Audit Store

```python
# v2.x (still works)
from kailash.trust.immutable_audit_log import AuditEntry

# v3.0 (recommended)
from kailash.trust.audit_store import (
    AuditEvent,
    AuditFilter,
    InMemoryAuditStore,
    SqliteAuditStore,
)
```

### Auth (Nexus → kailash.trust.auth)

```python
# v2.x (Nexus internal)
from nexus.auth import JWTAuthMiddleware

# v3.0 (canonical)
from kailash.trust.auth import jwt, rbac, context, session, chain
from kailash.trust.auth.sso import google, azure, github, apple
```

### Delegate (no changes needed)

The Delegate API is byte-identical between v2.x and v3.0:

```python
# Works identically in v2.x and v3.0
from kaizen_agents import Delegate

delegate = Delegate(model="gpt-4", mcp_servers=[...], budget_usd=10.0)
async for event in delegate.run("analyze this data"):
    print(event)
```

New optional parameters in v3.0:

- `signature=` — Custom signature
- `envelope=` — Governance envelope (constructs `L3GovernedAgent` internally)
- `inner_agent=` — Wrap an existing agent

### BaseAgent Extension Points (Deprecated)

The 7 extension points still work but emit `DeprecationWarning`:

- `_default_signature`
- `_default_strategy`
- `_generate_system_prompt`
- `_validate_signature_output`
- `_pre_execution_hook`
- `_post_execution_hook`
- `_handle_error`

**Migration**: Use composition wrappers instead:

```python
# v2.x — Subclass with extension points
class MyAgent(BaseAgent):
    def _pre_execution_hook(self, ctx):
        # ...

# v3.0 — Compose with wrappers
agent = StreamingAgent(
    MonitoredAgent(
        L3GovernedAgent(
            BaseAgent(model=...),
            envelope=envelope,
        ),
        budget_usd=10.0,
    )
)
```

## Removal Timeline

| Deprecated Path                                  | Replacement                          | v3.0         | v4.0        |
| ------------------------------------------------ | ------------------------------------ | ------------ | ----------- |
| `from kailash.mcp_server import ...`             | `from kailash_mcp import ...`        | Warn + works | ImportError |
| `from kaizen.nodes.ai.ai_providers import ...`   | `from kaizen.providers.* import ...` | Warn + works | ImportError |
| `BaseAgent.before_llm_call()` (extension points) | `MonitoredAgent` wrapper             | Warn + works | Removed     |
| `kaizen_agents.delegate.loop`                    | Internal — use `Delegate` directly   | Internal     | Internal    |

## sed Commands for Automated Migration

```bash
# Update MCP imports
find . -name "*.py" -exec sed -i.bak \
  -e 's/from kailash\.mcp_server import/from kailash_mcp import/g' \
  -e 's/from kailash\.mcp_server\.auth import/from kailash_mcp.auth import/g' \
  -e 's/from kailash\.mcp_server\.client import/from kailash_mcp.client import/g' \
  {} \;

# Update provider imports
find . -name "*.py" -exec sed -i.bak \
  -e 's/from kaizen\.nodes\.ai\.ai_providers import/from kaizen.providers import/g' \
  {} \;

# Clean up backup files after verifying
find . -name "*.py.bak" -delete
```

## Verifying Your Migration

Run the convergence verification script:

```bash
python scripts/convergence-verify.py --all
```

This checks that all canonical paths are in place and your code is using the v3.0 architecture.

## Cross-SDK Parity

v3.0 introduces matched `cross-sdk` GitHub issues with `kailash-rs` for every architectural change. Test vectors are shared between Python and Rust CI to ensure semantic parity. See `tests/fixtures/cross-sdk/README.md` for details.

## Need Help?

- Open an issue at `terrene-foundation/kailash-py` with the `migration` label
- See full architecture decision records at `workspaces/platform-architecture-convergence/01-analysis/04-adrs/`
