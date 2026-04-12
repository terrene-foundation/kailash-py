# Migration Guide: Kailash SDK v2.x to v3.0 (Platform Architecture Convergence)

This guide covers migrating code from Kailash SDK v2.x to v3.0. The v3.0
release is the output of the Platform Architecture Convergence (SPEC-01
through SPEC-10), which restructured the SDK for modularity, cross-SDK
parity with `kailash-rs`, and full PACT governance conformance.

## Overview of Changes

| Area             | What Changed                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| **MCP**          | Extracted as standalone `kailash-mcp` package; old `kailash.mcp_server` emits deprecation warnings   |
| **Providers**    | 5,001-line monolith split into per-provider modules under `kaizen.providers`                         |
| **Trust / PACT** | N4/N5/N6 conformance types added; `kailash-trust-shim` removed; audit/observation/suspension modules |
| **Envelopes**    | Canonical `ConstraintEnvelope` unified at `kailash.trust.envelope`                                   |
| **Kaizen**       | `BaseAgent` slimmed (3,698 to 891 LOC); composition wrappers replace extension points                |
| **Audit**        | Single canonical `AuditStore` with Merkle chain at `kailash.trust.audit_store`                       |
| **Auth**         | Nexus auth extracted to `kailash.trust.auth.*`                                                       |
| **ML**           | `DriftMonitor.set_reference()` renamed to `set_reference_data()` (shim removed)                      |
| **Runtime**      | New `EventLoopWatchdog` and `ProgressUpdate` / `ProgressRegistry`                                    |
| **Security**     | Credential decode consolidated to `kailash.utils.url_credentials`                                    |
| **DataFlow**     | Modular architecture; progressive configuration system                                               |

## Backward Compatibility

**v2.x code continues to work in v3.0.** All public APIs are preserved through:

- **Layer 1 -- Re-export shims**: Old import paths emit `DeprecationWarning` and re-export from new locations
- **Layer 2 -- Class aliases**: `isinstance()` checks work across old and new types
- **Layer 3 -- `@deprecated` decorator**: Extension points still work but warn
- **Layer 4 -- Removal in v4.0**: Deprecated paths removed in v4.0 (not v3.0)

**Exception**: `DriftMonitor.set_reference()` has been removed with no shim.
Use `set_reference_data()` instead. See the ML section below.

---

## 1. Module Renames and Moves

### MCP

```python
# v2.x (emits DeprecationWarning in v3.0)
from kailash.mcp_server import MCPClient, MCPServer
from kailash.mcp_server.auth import APIKeyAuth

# v3.0
from kailash_mcp import MCPClient, MCPServer
from kailash_mcp.auth import APIKeyAuth
```

```bash
# sed — update MCP imports
find . -name "*.py" -exec sed -i.bak \
  -e 's/from kailash\.mcp_server import/from kailash_mcp import/g' \
  -e 's/from kailash\.mcp_server\.auth import/from kailash_mcp.auth import/g' \
  -e 's/from kailash\.mcp_server\.client import/from kailash_mcp.client import/g' \
  {} +
```

### Providers (Kaizen)

```python
# v2.x (emits DeprecationWarning)
from kaizen.nodes.ai.ai_providers import UnifiedAIProvider

# v3.0
from kaizen.providers import get_provider, get_provider_for_model
from kaizen.providers.llm import OpenAIProvider, AnthropicProvider
```

```bash
find . -name "*.py" -exec sed -i.bak \
  -e 's/from kaizen\.nodes\.ai\.ai_providers import/from kaizen.providers import/g' \
  {} +
```

### ConstraintEnvelope

```python
# v2.x (multiple locations, all still work)
from kailash.trust.chain import ConstraintEnvelope
from kailash.trust.plane.models import ConstraintEnvelope
from kailash.trust.pact.config import ConstraintEnvelopeConfig

# v3.0 canonical
from kailash.trust.envelope import ConstraintEnvelope, AgentPosture
```

### Audit Store

```python
# v2.x
from kailash.trust.immutable_audit_log import AuditEntry

# v3.0
from kailash.trust.audit_store import (
    AuditEvent,
    AuditEventType,
    AuditFilter,
    AuditOutcome,
    AuditStoreProtocol,
    InMemoryAuditStore,
)
```

### Auth (Nexus to kailash.trust.auth)

```python
# v2.x (Nexus internal)
from nexus.auth import JWTAuthMiddleware

# v3.0 (canonical location)
from kailash.trust.auth import jwt, rbac, context, session, chain
from kailash.trust.auth.sso import google, azure, github, apple
```

### Middleware (moved off top-level kailash)

```python
# v2.x (emits DeprecationWarning)
from kailash import AgentUIMiddleware, APIGateway, RealtimeMiddleware

# v3.0
from kailash.middleware import AgentUIMiddleware, APIGateway, RealtimeMiddleware
```

### WorkflowGraph (removed alias)

```python
# v2.x (emits DeprecationWarning -- "use Workflow instead")
from kailash import WorkflowGraph

# v3.0 -- use the canonical name
from kailash.workflow.graph import Workflow
```

### kailash-trust-shim (removed entirely)

If any code imports from `kailash_trust_shim`, replace with the canonical
`kailash.trust` path. The shim package no longer exists.

```bash
# Find stale shim imports
grep -rn 'from kailash_trust_shim' .
grep -rn 'import kailash_trust_shim' .

# Replace with canonical paths
find . -name "*.py" -exec sed -i.bak \
  -e 's/from kailash_trust_shim/from kailash.trust/g' \
  -e 's/import kailash_trust_shim/import kailash.trust/g' \
  {} +
```

---

## 2. API Renames

### DriftMonitor.set_reference() to set_reference_data()

The old `set_reference()` method has been **removed with no backward-compat
shim**. This is the only breaking rename in v3.0.

```python
# v2.x
await monitor.set_reference("model_v1", reference_df, feature_cols)

# v3.0
await monitor.set_reference_data("model_v1", reference_df, feature_cols)
```

```bash
find . -name "*.py" -exec sed -i.bak \
  -e 's/\.set_reference(/\.set_reference_data(/g' \
  {} +
```

**Signature is identical** -- only the method name changed. The parameters
(`model_name`, `data`, `feature_columns`) are unchanged.

---

## 3. New Features

### EventLoopWatchdog (`kailash.runtime.watchdog`)

Detects asyncio event loop stalls (blocked callbacks) in long-running
workflows. Uses a heartbeat coroutine + watchdog thread architecture.

```python
from kailash.runtime import EventLoopWatchdog, StallReport

def on_stall(report: StallReport):
    logger.warning("Loop stalled for %.1fs", report.stall_duration_s)
    for stack in report.task_stacks:
        logger.warning("  %s", stack)

async with EventLoopWatchdog(stall_threshold_s=3.0, on_stall=on_stall) as wd:
    await run_long_workflow()
    if wd.is_stalled:
        print("Loop is currently stalled")
```

### ProgressUpdate / ProgressRegistry (`kailash.runtime.progress`)

Structured progress reporting from inside node execution. Fully backward
compatible -- `report_progress()` is a no-op when no registry is active.

```python
# Inside a custom node
from kailash.runtime.progress import report_progress

class MyNode(Node):
    def run(self, **kwargs):
        items = kwargs["items"]
        for i, item in enumerate(items):
            process(item)
            report_progress(current=i + 1, total=len(items), message=f"Processed {item}")
        return {"processed": len(items)}

# Consumer side
from kailash.runtime.progress import ProgressRegistry, ProgressUpdate

registry = ProgressRegistry()
registry.register(lambda u: print(f"{u.node_id}: {u.fraction:.0%}"))
```

### PACT N4/N5/N6 Conformance Types

New types added to `kailash.trust.pact`:

| Conformance            | Types                                                       | Module                            |
| ---------------------- | ----------------------------------------------------------- | --------------------------------- |
| **N4 -- Tiered Audit** | `TieredAuditDispatcher`                                     | `kailash.trust.pact.audit`        |
| **N5 -- Observation**  | `Observation`, `ObservationSink`, `InMemoryObservationSink` | `kailash.trust.pact.observation`  |
| **N5 -- EATP Emitter** | `PactEatpEmitter`, `InMemoryPactEmitter`                    | `kailash.trust.pact.eatp_emitter` |
| **N6 -- Suspension**   | `SuspensionTrigger`, `ResumeCondition`, `SuspendedPlan`     | `kailash.trust.pact.suspension`   |
| **Compilation**        | `VacancyDesignation`                                        | `kailash.trust.pact.compilation`  |
| **Envelopes**          | `check_gradient_dereliction`, `check_passthrough_envelope`  | `kailash.trust.pact.envelopes`    |

All N4/N5 types are re-exported from `kailash.trust.pact` and from the
`pact` (kailash-pact) top-level package. N6 suspension types are available
at `kailash.trust.pact.suspension`.

```python
from kailash.trust.pact import (
    # N4
    TieredAuditDispatcher,
    # N5
    Observation,
    ObservationSink,
    InMemoryObservationSink,
    PactEatpEmitter,
    InMemoryPactEmitter,
    # Envelope safety
    check_gradient_dereliction,
    check_passthrough_envelope,
    VacancyDesignation,
)

# N6 (direct import)
from kailash.trust.pact.suspension import (
    SuspensionTrigger,
    ResumeCondition,
)
```

### Credential Decode Helper (`kailash.utils.url_credentials`)

All connection-string credential decoding consolidated into a single helper
to prevent null-byte auth-bypass drift between adapters.

```python
from kailash.utils.url_credentials import (
    decode_userinfo_or_raise,
    preencode_password_special_chars,
)
```

This is used internally by all five dialect parsers. If you had custom
`unquote(parsed.password)` calls, replace them:

```python
# v2.x
from urllib.parse import unquote
user = unquote(parsed.username or "")
password = unquote(parsed.password or "")

# v3.0
from kailash.utils.url_credentials import decode_userinfo_or_raise
user, password = decode_userinfo_or_raise(parsed)
```

### DataFlow Progressive Configuration

```python
from dataflow.configuration import zero_config, basic_config, production_config, enterprise_config

# Zero-config (no arguments needed)
db = DataFlow("sqlite:///app.db")

# Production (explicit pool tuning)
db = DataFlow("postgresql://...", config=production_config(pool_size=20))
```

---

## 4. Removed / Replaced

| What                                                                   | Disposition                                                    |
| ---------------------------------------------------------------------- | -------------------------------------------------------------- |
| `kailash-trust-shim` package                                           | Removed. Use `kailash.trust` directly.                         |
| `DriftMonitor.set_reference()`                                         | Removed. Use `set_reference_data()`.                           |
| `WorkflowGraph` class                                                  | Deprecated alias for `Workflow`. Will be removed in v4.0.      |
| `BaseAgent` extension points (7 methods)                               | Deprecated. Use composition wrappers. Will be removed in v4.0. |
| Top-level middleware imports (`from kailash import AgentUIMiddleware`) | Deprecated. Import from `kailash.middleware`.                  |

### BaseAgent Extension Points Migration

The 7 deprecated extension points (`_default_signature`, `_default_strategy`,
`_generate_system_prompt`, `_validate_signature_output`, `_pre_execution_hook`,
`_post_execution_hook`, `_handle_error`) still work in v3.0 but emit
`DeprecationWarning`. They will be removed in v4.0.

```python
# v2.x -- subclass with extension points
class MyAgent(BaseAgent):
    def _pre_execution_hook(self, ctx):
        log_start(ctx)
    def _post_execution_hook(self, ctx, result):
        log_end(ctx, result)

# v3.0 -- compose with wrappers
agent = StreamingAgent(
    MonitoredAgent(
        L3GovernedAgent(
            BaseAgent(model=os.environ["LLM_MODEL"]),
            envelope=envelope,
        ),
        budget_usd=10.0,
    )
)
```

---

## 5. Configuration Changes

### New Environment Variables

| Variable                       | Purpose                                     | Default |
| ------------------------------ | ------------------------------------------- | ------- |
| `KAILASH_WATCHDOG_THRESHOLD_S` | EventLoopWatchdog stall threshold (seconds) | `5.0`   |
| `KAILASH_PROGRESS_ENABLED`     | Enable progress reporting from nodes        | `true`  |

### Package Versions (v3.0 Release)

| Package            | Version |
| ------------------ | ------- |
| `kailash`          | 2.8.2   |
| `kailash-dataflow` | 2.0.4   |
| `kailash-nexus`    | 2.0.1   |
| `kailash-kaizen`   | 2.7.2   |
| `kailash-pact`     | 0.8.1   |
| `kailash-ml`       | 0.8.1   |
| `kailash-align`    | 0.3.1   |
| `kailash-mcp`      | 0.2.1   |
| `kaizen-agents`    | 0.9.1   |

---

## 6. Removal Timeline

| Deprecated Path                                  | Replacement                                        | v3.0         | v4.0        |
| ------------------------------------------------ | -------------------------------------------------- | ------------ | ----------- |
| `from kailash.mcp_server import ...`             | `from kailash_mcp import ...`                      | Warn + works | ImportError |
| `from kaizen.nodes.ai.ai_providers import ...`   | `from kaizen.providers.* import ...`               | Warn + works | ImportError |
| `BaseAgent._pre_execution_hook()` (and 6 others) | `MonitoredAgent` / composition wrappers            | Warn + works | Removed     |
| `from kailash import AgentUIMiddleware`          | `from kailash.middleware import AgentUIMiddleware` | Warn + works | ImportError |
| `WorkflowGraph`                                  | `Workflow`                                         | Warn + works | Removed     |
| `DriftMonitor.set_reference()`                   | `DriftMonitor.set_reference_data()`                | **Removed**  | --          |
| `kailash_trust_shim`                             | `kailash.trust`                                    | **Removed**  | --          |

---

## 7. Automated Migration

Run the sed commands above, then verify with the convergence script:

```bash
uv run python scripts/convergence-verify.py
```

This checks for stale imports, version consistency, PACT export completeness,
stub markers, and import hygiene.

## 8. Cross-SDK Parity

v3.0 introduces matched `cross-sdk` GitHub issues with `kailash-rs` for
every architectural change. Test vectors are shared between Python and Rust
CI to ensure semantic parity per EATP D6 (independent implementation,
matching semantics).

## Need Help?

- Open an issue at `terrene-foundation/kailash-py` with the `migration` label
- Architecture decision records: `workspaces/platform-architecture-convergence/01-analysis/04-adrs/`
