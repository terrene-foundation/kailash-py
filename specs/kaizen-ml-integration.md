# Kaizen × kailash-ml Integration — Unified Tracker Surface, Shared CostTracker, Shared TraceExporter Store

Version: 1.0.0 (draft)
Package: `kailash-kaizen`
Target release: **kailash-kaizen 2.12.0** (shipping in the kailash-ml 1.0.0 wave)
Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md`. Promotes to `specs/kaizen-ml-integration.md` after round-3 convergence.
Supersedes: none — this spec adds tracker-kwarg propagation + shared-store contracts to existing Kaizen Diagnostic adapters.
Parent domain: Kailash Kaizen (AI agent framework).
Sibling specs: `specs/kaizen-observability.md` (AgentDiagnostics + TraceExporter), `specs/kaizen-evaluation.md`, `specs/kaizen-interpretability.md`, `specs/kaizen-judges.md`, `specs/kaizen-core.md`, `specs/kaizen-providers.md`, `specs/kaizen-advanced.md` (CostTracker).

Origin: round-1 theme T2 (engine↔tracker wiring is 0/13 auto). Kaizen ships three Diagnostic adapters (`AgentDiagnostics`, `LLMDiagnostics`, `InterpretabilityDiagnostics`) that satisfy `kailash.diagnostics.protocols.Diagnostic` at runtime but do NOT emit to `km.track()`. Symmetric treatment with `DLDiagnostics` (kailash-ml) is required so a single `km.track()` run captures ml+kaizen telemetry in ONE dashboard. Also: CostTrackers in `kaizen.cost` and `kailash_pact.costs` currently use different integer units; kailash-ml's budget gate needs a single wire format. Finally: `TraceExporter`'s durable sink MUST write to the same `~/.kailash_ml/ml.db` store (or a compatible SQLite adapter) so kaizen agent traces appear in the same dashboard as ML runs.

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Four integration surfaces Kaizen 2.12.0 ships:

1. **`tracker=` kwarg on every diagnostic adapter** — `AgentDiagnostics`, `LLMDiagnostics`, `InterpretabilityDiagnostics` each accept `tracker: Optional[ExperimentRun] = None`. Default `None` reads the ambient `km.track()` run via `kailash_ml.tracking.get_current_run()` (via the compat layer — same pattern as Nexus contextvars). Symmetric with `DLDiagnostics` in kailash-ml.
2. **Auto-emission from every `record_*` / `track_*` method** — when an ambient tracker is present, every event-capture method MUST emit `tracker.log_metric(...)` or `tracker.log_param(...)` or `tracker.log_artifact(...)` as appropriate. No opt-in, no configuration flag — if there's a tracker, metrics flow.
3. **Shared CostTracker wire format** — `kaizen.cost.tracker.CostTracker` and `kailash_pact.costs.CostTracker` MUST both serialize cost deltas as integer microdollars (`microdollars: int = usd * 1_000_000`). Both sides implement `to_dict()` / `from_dict()` with identical key names.
4. **TraceExporter → shared SQLite store** — `TraceExporter` gains a `SQLiteSink` option that writes to the canonical `~/.kailash_ml/ml.db` store (or any SQLAlchemy URL). The schema is `agent_traces` + `agent_trace_events` tables inside the same DB `ExperimentTracker` uses.

### 1.2 Out of Scope (Owned By Sibling Specs)

- TraceExporter core surface (`JsonlSink`, `NoOpSink`, `CallableSink`) → `specs/kaizen-observability.md` (unchanged).
- AgentDiagnostics internals (event aggregation, rollup math) → `specs/kaizen-observability.md`.
- Judge evaluation → `specs/kaizen-judges.md`.
- Signature authoring → `specs/kaizen-signatures.md`.
- Provider abstraction → `specs/kaizen-providers.md`.
- Agent governance → `specs/kaizen-agents-governance.md`.

### 1.3 Non-Goals

- **No replacement for `km.track()`.** Kaizen does NOT ship its own tracker engine. The `km.track()` run IS the tracker surface; Kaizen adapters read it and emit to it.
- **No new diagnostic protocols.** Existing `Diagnostic` Protocol at `src/kailash/diagnostics/protocols.py` is expanded (per `kailash-core-ml-integration-draft.md` §2) — Kaizen adapters satisfy it.
- **No Langfuse / LangSmith / commercial-SDK integrations** (unchanged — `rules/independence.md`).

---

## 2. `tracker=` Kwarg On Diagnostic Adapters

### 2.1 Contract

Three adapters gain identical surfaces:

```python
# kaizen.observability.agent_diagnostics
class AgentDiagnostics:
    def __init__(
        self,
        *,
        agent_id: str,
        tenant_id: Optional[str] = None,
        tracker: Optional["ExperimentRun"] = None,  # NEW
        exporter: Optional[TraceExporter] = None,
        # ... existing kwargs ...
    ) -> None: ...

# kaizen.observability.llm_diagnostics (new file — see §2.3)
class LLMDiagnostics:
    def __init__(
        self,
        *,
        model_id: str,
        tenant_id: Optional[str] = None,
        tracker: Optional["ExperimentRun"] = None,  # NEW
        # ... existing kwargs ...
    ) -> None: ...

# kaizen.interpretability.diagnostics
class InterpretabilityDiagnostics:
    def __init__(
        self,
        *,
        target_id: str,
        tenant_id: Optional[str] = None,
        tracker: Optional["ExperimentRun"] = None,  # NEW
        # ... existing kwargs ...
    ) -> None: ...
```

**MUST**: `tracker` is typed as `Optional[ExperimentRun]` (the user-visible handle from `km.track()`), NOT `Optional[ExperimentTracker]` (the engine). This matches the approved-decisions.md implications summary: "All sibling-spec `tracker=` kwargs MUST annotate `Optional[ExperimentRun]`".

### 2.2 Ambient fallback

When `tracker=None`, the adapter reads the ambient run:

```python
from kailash_ml.tracking import get_current_run

class AgentDiagnostics:
    def __init__(self, *, tracker=None, ...):
        self._tracker = tracker  # None is valid — resolved lazily

    @property
    def _active_tracker(self) -> Optional["ExperimentRun"]:
        """Lazy resolution — explicit tracker wins, else ambient."""
        return self._tracker if self._tracker is not None else get_current_run()
```

**Why lazy, not eager?** The adapter may be constructed BEFORE the user enters `async with km.track(...)`. Lazy resolution lets the SAME adapter instance participate in multiple sequential runs (e.g., sweep parent + trial children).

### 2.3 New `LLMDiagnostics` module

`LLMDiagnostics` does NOT exist in Kaizen 2.11.x. Kaizen 2.12.0 ships it at `kaizen.observability.llm_diagnostics`. Scope: token usage, latency p50/p95, provider error rate, context-window utilization, completion-length histogram. This is the Kaizen-side mirror of kailash-ml's `DLDiagnostics`.

```python
@dataclass(frozen=True)
class LLMDiagnosticsReport:
    model_id: str
    tenant_id: Optional[str]
    request_count: int
    prompt_tokens_total: int
    completion_tokens_total: int
    latency_p50_ms: float
    latency_p95_ms: float
    error_rate: float  # 0..1
    context_window_utilization_p95: float  # 0..1
```

Satisfies `kailash.diagnostics.protocols.Diagnostic` at runtime (isinstance holds).

### 2.4 Agent Tool Discovery via `km.engine_info()`

Binding MUST clause (authoritative): `ml-engines-v2-addendum §E11.3 MUST 1`. Kaizen agents (BaseAgent, DelegateEngine, SupervisorAgent, and every descendant) MUST obtain ML-method signatures AT runtime via `km.engine_info(engine_name)` / `km.list_engines()`. Hardcoded `from kailash_ml.engines.<foo> import <Foo>` imports in an agent's tool-set construction path are BLOCKED. The authoritative declaration of `EngineInfo` / `MethodSignature` / `ParamSpec` is `ml-engines-v2-addendum §E11.1` — this subsection imports those types rather than re-declaring them (per `rules/specs-authority.md §5b` — one canonical shape across specs).

#### 2.4.1 Discovery Helpers — Re-Imported From The Authoritative Declaration

Per `ml-engines-v2-addendum §E11.2`, two module-level helpers live at `kailash_ml.engines.registry` and are re-exported from `kailash_ml/__init__.py`:

```python
# Signatures (authoritative: ml-engines-v2-addendum §E11.2)
def engine_info(engine_name: str) -> EngineInfo: ...
def list_engines() -> tuple[EngineInfo, ...]: ...
```

Kaizen agents import the helpers via the top-level `kailash_ml` namespace:

```python
import kailash_ml as km

all_engines: tuple[EngineInfo, ...] = km.list_engines()
training_info: EngineInfo = km.engine_info("TrainingPipeline")
```

#### 2.4.2 `EngineInfo` Shape — Re-Imported, Not Redefined

The canonical `EngineInfo` dataclass lives at `kailash_ml.engines.registry.EngineInfo` (authoritative: `ml-engines-v2-addendum §E11.1`). Kaizen agents MUST import it rather than redefining the shape:

```python
from kailash_ml.engines.registry import (
    EngineInfo,
    MethodSignature,
    ParamSpec,
    ClearanceRequirement,  # nested axis+level dataclass per §E11.1 L488-516
)
```

Fields (re-stated for reader convenience — authoritative source is `ml-engines-v2-addendum §E11.1`):

| Field               | Type                                         | Purpose                                                                                                                                                                            |
| ------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`              | `str`                                        | Engine class name, e.g. `"TrainingPipeline"`                                                                                                                                       |
| `version`           | `str`                                        | Semver; MUST equal `kailash_ml.__version__` (§E11.3 MUST 3)                                                                                                                        |
| `module_path`       | `str`                                        | Dotted import path                                                                                                                                                                 |
| `accepts_tenant_id` | `bool`                                       | Whether the engine supports multi-tenant kwargs                                                                                                                                    |
| `emits_to_tracker`  | `bool`                                       | Whether the engine auto-wires to ambient `km.track()` run                                                                                                                          |
| `clearance_level`   | `Optional[tuple[ClearanceRequirement, ...]]` | PACT axis (D/T/R per Decision 12) + level (L/M/H per §E9.2) — nested per §E11.1 L488-516 (NOT a flat literal)                                                                      |
| `signatures`        | `tuple[MethodSignature, ...]`                | Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant. |
| `extras_required`   | `tuple[str, ...]`                            | Optional pip extras (e.g. `("dl",)`)                                                                                                                                               |

Kaizen agents derive their LLM tool-spec list by traversing `EngineInfo.signatures` — no other shape is acceptable. A Kaizen agent that constructs a tool-spec from a hand-rolled `{"name": ..., "params": ...}` dict instead of `MethodSignature` is a §5b cross-spec drift violation.

#### 2.4.3 Tenant-Scoped Lookup

A Kaizen agent's `tenant_id` flows through to the discovery call so downstream `clearance_level` filtering is tenant-aware. Agents with `tenant_id=None` (single-tenant mode) see every engine; agents with `tenant_id="acme"` see only engines admissible under acme's PACT envelope:

```python
# kaizen.agents.base
class BaseAgent:
    def __init__(self, *, tenant_id: Optional[str] = None, ...) -> None:
        self._tenant_id = tenant_id

    def _discover_ml_tools(self) -> tuple[EngineInfo, ...]:
        engines = km.list_engines()
        if self._tenant_id is None:
            return engines
        # Tenant-scoped filter: every EngineInfo.clearance_level tuple is checked
        # against the tenant's PACT envelope via kailash_pact.check_clearance(...).
        # Each ClearanceRequirement(axis, min_level) pair is validated independently;
        # an engine is admissible only if EVERY requirement in its tuple holds for
        # the tenant. The envelope decides which engines are exposed to the LLM.
        return tuple(
            e for e in engines
            if self._is_clearance_admissible(e.clearance_level)
        )
```

The `_is_clearance_admissible` check reads the tenant's PACT envelope and returns False when ANY `ClearanceRequirement(axis, min_level)` in an engine's `clearance_level` tuple exceeds the tenant's admitted clearance on that axis — the LLM simply never sees the tool in its tool-spec list. For an engine with `clearance_level = None` or `clearance_level = ()`, the check trivially passes (no PACT restriction).

#### 2.4.4 Version-Sync Invariant (Binding From §E11.3 MUST 3)

`EngineInfo.version` MUST equal `kailash_ml.__version__` at discovery time. This invariant is the mechanism by which the agent tool contract self-synchronizes with the package version — no manual refresh is required when kailash-ml releases a new version:

```python
# At kailash-ml runtime 1.0.1 (one patch after 1.0.0)
info = km.engine_info("TrainingPipeline")
assert info.version == "1.0.1"                  # not "1.0.0" (split-version BLOCKED per §E11.3 MUST 3)
assert info.version == kailash_ml.__version__   # always equal, atomically

# If a Kaizen agent compiled against 1.0.0 runs against a 1.0.1 deployment,
# the returned signatures reflect 1.0.1's actual method surface — not 1.0.0's
# frozen compiled-in types. This closes the drift failure mode where agent
# tool-specs lag package changes.
```

Rationale: agents typically live across minor upgrades of the ML package (the agent framework and the ML framework release on independent cadences). A hardcoded tool-set would drift the moment a kailash-ml patch adds, renames, or deprecates a method. The discovery path collapses that drift surface to zero.

#### 2.4.5 BLOCKED Pattern — Hardcoded Imports In Agent Tool Construction

A Kaizen agent's tool-set construction MUST NOT import engine classes directly:

```python
# DO — discovery-driven, version-synchronized
import kailash_ml as km
from kailash_ml.engines.registry import EngineInfo, MethodSignature

class ChurnAnalysisAgent(BaseAgent):
    def _build_tool_set(self) -> list[ToolSpec]:
        engines = km.list_engines()
        return [
            _method_signature_to_tool_spec(sig)
            for engine in engines
            for sig in engine.signatures
            if self._is_relevant(engine.name)
        ]

# DO NOT — hardcoded imports bind the agent to a frozen package surface
from kailash_ml.engines.training_pipeline import TrainingPipeline   # BLOCKED
from kailash_ml.engines.model_registry import ModelRegistry         # BLOCKED

class ChurnAnalysisAgent(BaseAgent):
    def _build_tool_set(self) -> list[ToolSpec]:
        # This pattern defeats §E11.3 MUST 3 version-sync invariant:
        # the agent's tool-specs reflect the compile-time TrainingPipeline
        # surface, not the runtime surface.
        return [
            _introspect_to_tool_spec(TrainingPipeline),
            _introspect_to_tool_spec(ModelRegistry),
        ]
```

**BLOCKED rationalizations:**

- "Direct imports are clearer for readers"
- "Discovery adds latency on every agent construction"
- "We pin the kailash-ml version, so compile-time and runtime surfaces match"
- "Only the tool-set construction path matters — other imports are fine"
- "Hardcoded imports make the agent self-contained"

**Why:** "We pin the kailash-ml version" is exactly the failure mode the version-sync invariant exists to prevent. Pinning is a versioning policy that lasts until a security patch forces an upgrade; the moment the upgrade lands, every hardcoded-import agent has a stale tool surface and the LLM calls methods that have been renamed / deprecated / removed. Discovery is the structural defense — it costs one tuple construction per agent startup and eliminates an entire class of drift bugs.

#### 2.4.6 Canonical Integration — `kaizen.ml.MLAwareAgent`

The canonical implementation ships at `packages/kailash-kaizen/src/kaizen/ml/ml_aware_agent.py` and is re-exported from `kaizen.ml`:

```python
import kailash_ml as km
from kaizen.core.config import BaseAgentConfig
from kaizen.ml import MLAwareAgent

# Construction discovers every engine and builds one ToolDefinition per
# MethodSignature; tools are immutable for the agent's lifetime.
agent = MLAwareAgent(
    config=BaseAgentConfig(llm_provider="openai"),
    tenant_id=None,           # single-tenant mode (every engine visible)
    clearance_filter=None,    # PACT envelope filter — None = no gating
)
print(f"{len(agent.ml_tools)} ML tools registered")
print(f"{len(agent.ml_engines)} engines discovered")
```

Implementation contract (see `kaizen.ml.ml_aware_agent.MLAwareAgent` for the production source):

1. `__init__` calls `kaizen.ml.discover_ml_tools(tenant_id=..., clearance_filter=...)` — the only sanctioned entry point per §2.4.5 (no hardcoded engine imports).
2. `build_ml_tools()` walks every `EngineInfo.signatures` and converts each `MethodSignature` to a `kaizen.tools.types.ToolDefinition` named `{engine.name}.{sig.method_name}`.
3. The `ToolDefinition.description` field embeds `kailash_ml.__version__` so the §2.4.4 version-sync invariant is observable from the LLM-visible tool surface — not just from the `EngineInfo.version` field.
4. The discovered engines and tools are exposed as immutable tuples (`agent.ml_engines`, `agent.ml_tools`) so the LLM tool-spec list captured at agent start stays consistent across every turn.

Per `rules/agent-reasoning.md` Permitted Deterministic Logic clauses 1+5+6, the conversion path (`MethodSignature → ToolDefinition`) is structural plumbing — no decision logic, no input classification, no routing. The LLM still owns every decision about which tool to invoke.

#### 2.4.7 Tier 2 Wiring Test

Per `rules/facade-manager-detection.md` §2 and `ml-engines-v2-addendum §E11.3 MUST 4`, this integration surface has the Tier 2 wiring test at:

- File: `packages/kailash-kaizen/tests/integration/ml/test_kaizen_agent_engine_discovery_wiring.py`
- Constructs a real `MLAwareAgent` with `BaseAgentConfig(llm_provider="mock")`.
- Asserts the agent's `ml_tools` contains one entry per `MethodSignature` across every registered engine.
- Asserts every tool's `description` field embeds `kailash_ml.__version__` — the version-sync invariant on the observable tool surface.
- Asserts tool naming follows `{engine.name}.{method_name}` per §2.4.6.
- Asserts `ml_tools` and `ml_engines` are tuples (immutable per §2.4.6).
- Asserts `tenant_id` flows through to the discovery layer (§2.4.3).

Spec §2.4.5 contract assertion: when `kailash_ml.engine_info` / `list_engines` are not yet shipped in the installed `kailash_ml`, the test asserts `MLRegistryUnavailableError` is raised with an actionable message — no silent skip, no direct-import fallback.

The test is explicitly version-synchronized: any future `kailash_ml.__version__` bump that is NOT reflected in the tool-spec descriptions flips the test red, catching drift at the wiring boundary rather than at the next LLM invocation.

#### 2.4.8 Cross-Reference

Authoritative declaration: `ml-engines-v2-addendum §E11` (Engine Registry — Programmatic Discovery). This subsection binds Kaizen's agent-tool-construction contract to that declaration. No shape is redefined here; every type (`EngineInfo`, `MethodSignature`, `ParamSpec`) is imported from `kailash_ml.engines.registry`. Any divergence between this subsection and §E11 is a `rules/specs-authority.md §5b` violation and is resolved in favor of §E11.

---

### 2.5 Rank-0-only emission (distributed-training parity with `DLDiagnostics`)

Per approved-decisions.md Decision 4: autolog + DLDiagnostics emit ONLY when `torch.distributed.get_rank() == 0`. LLMDiagnostics / AgentDiagnostics / InterpretabilityDiagnostics inherit the same rule whenever they run in a distributed context. Non-distributed context = always rank 0 semantics = always emits.

---

## 3. Auto-Emission From `record_*` / `track_*` Methods

### 3.1 Contract

Every `record_*` / `track_*` method on the three adapters MUST:

1. Do its existing job (capture the event, append to the rollup buffer, emit to the TraceExporter sink).
2. If `self._active_tracker is not None`: emit to the tracker via the appropriate primitive:
   - Scalar numeric event → `tracker.log_metric(key, value, step=...)`.
   - Categorical / string event → `tracker.log_param(key, value)`.
   - Binary/artifact event (plot, JSON bundle) → `tracker.log_artifact(path, name=...)`.

### 3.2 Metric naming

Namespaces are locked cross-SDK (per approved-decisions.md Decision 3 discipline):

| Adapter                       | Metric prefix | Example keys                                                                     |
| ----------------------------- | ------------- | -------------------------------------------------------------------------------- |
| `AgentDiagnostics`            | `agent.*`     | `agent.turns`, `agent.cost_microdollars`, `agent.duration_ms`                    |
| `LLMDiagnostics`              | `llm.*`       | `llm.prompt_tokens`, `llm.completion_tokens`, `llm.latency_ms`, `llm.error_rate` |
| `InterpretabilityDiagnostics` | `interp.*`    | `interp.shap_sum`, `interp.attention_entropy`                                    |

**MUST**: key namespace prefixes are locked. A new adapter that picks `agent_*` instead of `agent.*` is BLOCKED.

### 3.3 Step semantics

`step=` kwarg follows kailash-ml's `log_metric` semantics (per `ml-tracking-draft.md` §4.2): optional int, monotone-non-decreasing within a single (run, key). Adapters that have a natural step counter (agent turn number, LLM request number) forward it; adapters that don't, pass `step=None` (tracker uses wall-clock timestamp).

### 3.4 Failure-mode: no tracker, no crash

If `self._active_tracker is None`, the adapter skips the emission silently and continues its existing work. Logging occurs at DEBUG only ("no ambient tracker; skipping emit"). WARN/ERROR on missing tracker is BLOCKED — tracker is optional by contract.

---

## 4. Shared CostTracker Wire Format

### 4.1 Problem statement

Kaizen (`kaizen.cost.tracker.CostTracker`) historically uses `cents: int = usd * 100`. PACT (`kailash_pact.costs.CostTracker`) uses `microdollars: int = usd * 1_000_000` for finer precision (OpenAI GPT-4 embedding = $0.00013/1k tokens — resolves to 130 microdollars, but 0.013 cents truncates to 0). kailash-ml's `AutoMLEngine` and `GuardrailConfig` (per `ml-automl-draft.md`) mandate `microdollars` because sub-cent precision is required for LLM cost gating.

### 4.2 Parity clause

Kaizen 2.12.0 MUST migrate `kaizen.cost.tracker.CostTracker` to microdollars wire format:

```python
# kaizen.cost.tracker
@dataclass(frozen=True)
class CostDelta:
    microdollars: int                    # was: cents
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    at: datetime
    tenant_id: Optional[str]
    actor_id: Optional[str]

    @classmethod
    def from_usd(cls, usd: float, **kwargs) -> "CostDelta":
        if not math.isfinite(usd) or usd < 0:
            raise ValueError(f"invalid usd: {usd!r}")
        return cls(microdollars=int(round(usd * 1_000_000)), **kwargs)

    def to_dict(self) -> dict:
        return {
            "microdollars": self.microdollars,
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "at": self.at.isoformat(),
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CostDelta":
        return cls(
            microdollars=d["microdollars"],
            provider=d["provider"],
            model=d["model"],
            prompt_tokens=d["prompt_tokens"],
            completion_tokens=d["completion_tokens"],
            at=datetime.fromisoformat(d["at"]),
            tenant_id=d.get("tenant_id"),
            actor_id=d.get("actor_id"),
        )
```

`kailash_pact.costs.CostTracker.CostDelta` MUST use the IDENTICAL schema. A `CostDelta` serialized by Kaizen MUST deserialize by PACT and vice versa.

### 4.3 Migration for 2.11.x users

Kaizen 2.11.x users who read `delta.cents` directly get an AttributeError at 2.12.0. Per approved-decisions.md Decision 14 (1.0.0 signals API stability), this is acceptable for Kaizen's 2.x line since Kaizen does NOT hit 3.0 here; the migration is explicit in CHANGELOG. A 2.11→2.12 shim property `@property def cents(self) -> int: return self.microdollars // 10_000` is added to ease the transition but logs a `DeprecationWarning` at first access.

**Why:** Financial-field precision is a security concern (`rules/security.md` — `math.isfinite` on all budget fields). Silent truncation of sub-cent charges creates free-tier quota leaks.

### 4.4 Auto-emit into tracker

When a CostDelta is appended AND an ambient tracker exists, emit:

```python
tracker.log_metric("agent.cost_microdollars", delta.microdollars, step=None)
tracker.log_metric(f"agent.cost_by_provider.{delta.provider}", delta.microdollars, step=None)
```

Provider-dimensional metric MUST use bounded cardinality per `rules/tenant-isolation.md` §4.

---

## 5. TraceExporter — Shared SQLite Store

### 5.1 New sink: `SQLiteSink`

```python
# kaizen.observability.trace_exporter
class SQLiteSink:
    """Persistent sink that writes TraceEvent records to a SQLite store.
    Default path is ~/.kailash_ml/ml.db — the SAME canonical store used by
    ExperimentTracker, so agent traces appear in the MLDashboard alongside
    ML runs."""

    def __init__(
        self,
        *,
        db_url: Optional[str] = None,   # default: sqlite:///~/.kailash_ml/ml.db
        table_prefix: str = "_kml_agent_",
    ) -> None: ...

    def export(self, event: TraceEvent, fingerprint: str) -> None: ...
    async def export_async(self, event: TraceEvent, fingerprint: str) -> None: ...
    def close(self) -> None: ...
```

### 5.2 Schema

Two tables, `_kml_` prefix (aligned with ML's canonical internal-system-table convention per `ml-tracking.md §6.3` + `rules/dataflow-identifier-safety.md` Rule 2 — the leading underscore distinguishes framework-owned internal tables from user-facing tables):

```sql
CREATE TABLE IF NOT EXISTS _kml_agent_traces (
    trace_id        TEXT    PRIMARY KEY,
    run_id          TEXT,                    -- FK to _kml_run.run_id (ml-tracking canonical table; see ml-tracking.md §6.3), NULL allowed
    agent_id        TEXT    NOT NULL,
    tenant_id       TEXT,
    actor_id        TEXT,
    started_at      TIMESTAMP NOT NULL,
    ended_at        TIMESTAMP,
    status          TEXT    NOT NULL,        -- RUNNING / FINISHED / FAILED / KILLED (Decision 3)
    cost_microdollars INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS _kml_agent_traces_tenant_idx ON _kml_agent_traces(tenant_id);
CREATE INDEX IF NOT EXISTS _kml_agent_traces_run_idx    ON _kml_agent_traces(run_id);

CREATE TABLE IF NOT EXISTS _kml_agent_trace_events (
    event_id        TEXT    PRIMARY KEY,
    trace_id        TEXT    NOT NULL REFERENCES _kml_agent_traces(trace_id),
    seq             INTEGER NOT NULL,         -- monotone within trace
    event_type      TEXT    NOT NULL,
    event_status    TEXT    NOT NULL,
    fingerprint     TEXT    NOT NULL,         -- sha256:<8hex>
    at              TIMESTAMP NOT NULL,
    payload_json    TEXT                      -- redacted per rules/event-payload-classification.md
);
CREATE INDEX IF NOT EXISTS _kml_agent_trace_events_trace_idx ON _kml_agent_trace_events(trace_id, seq);
```

### 5.3 Cross-SDK status enum

`status` column MUST use the 4-member enum `{RUNNING, FINISHED, FAILED, KILLED}` per approved-decisions.md Decision 3. Legacy `SUCCESS` / `COMPLETED` values are BLOCKED.

### 5.4 Run correlation

When a `km.track()` run is ambient at `TraceExporter` construction time (read via `get_current_run()`), `SQLiteSink` sets `run_id` to the ambient run's `run_id`. Dashboards can then join `_kml_run` to `_kml_agent_traces` on `run_id` to show "this ML run used these agent traces."

### 5.5 TraceExporter default sink

`TraceExporter()` with no explicit `sink=` and an ambient tracker defaults to `SQLiteSink(db_url=<tracker's store>)`. Without an ambient tracker, default remains `NoOpSink()` (backward-compatible).

---

## 6. Error Taxonomy

All errors inherit from `kailash_kaizen.exceptions.KaizenError`:

```python
class KaizenError(Exception):
    """Base for every Kaizen exception."""

class CostTrackerError(KaizenError):
    """Raised on invalid CostDelta inputs (negative usd, non-finite, etc.)."""

class TrackerIntegrationError(KaizenError):
    """Raised when an adapter fails to emit to its ambient tracker
    (e.g. tracker closed between construction and emit)."""

class TraceExportError(KaizenError):
    """Existing (from kaizen.observability). Now also raised by SQLiteSink
    on schema-init failure."""
```

---

## 7. Test Contract

### 7.1 Tier 1 (unit)

- `test_agent_diagnostics_tracker_kwarg.py` — `AgentDiagnostics(tracker=explicit)` → explicit wins over ambient.
- `test_agent_diagnostics_ambient_fallback.py` — `tracker=None` inside `km.track()` → ambient resolves.
- `test_cost_delta_from_usd_rounds_correctly.py` — `from_usd(0.00013) == 130 microdollars`.
- `test_cost_delta_negative_usd_raises.py` — `from_usd(-1.0) → ValueError`.
- `test_cost_delta_nan_usd_raises.py` — `from_usd(float("nan")) → ValueError`.
- `test_sqlitesink_rejects_invalid_status.py` — direct insert with `status="COMPLETED"` → rejected.
- `test_rank0_only_emission.py` — mock `torch.distributed.get_rank()` returns 1 → no emission.

### 7.2 Tier 2 (integration wiring, per `rules/facade-manager-detection.md` §2)

File naming:

- `tests/integration/test_agent_diagnostics_tracker_wiring.py` — real `km.track()` run + `AgentDiagnostics` → `agent.turns` metric appears in `_kml_metric` table.
- `tests/integration/test_llm_diagnostics_tracker_wiring.py` — real run + `LLMDiagnostics` → `llm.prompt_tokens` appears.
- `tests/integration/test_interpretability_diagnostics_tracker_wiring.py` — real run + `InterpretabilityDiagnostics` → `interp.*` metrics appear.
- `tests/integration/test_cost_tracker_cross_sdk_parity_wiring.py` — Kaizen `CostDelta.to_dict()` → PACT `CostDelta.from_dict()` → equality holds.
- `tests/integration/test_sqlitesink_shared_store_wiring.py` — TraceExporter + SQLiteSink + ambient `km.track()` → agent trace row correlates to run row via `run_id` FK.

### 7.3 Regression tests

- `tests/regression/test_issue_NNN_cost_microdollar_truncation.py` — `from_usd(0.000005)` produces `microdollars=5`, not `0` (previous `cents` truncation).
- `tests/regression/test_issue_NNN_tracker_kwarg_type_is_experiment_run.py` — `inspect.signature(AgentDiagnostics).parameters["tracker"].annotation` matches `Optional[ExperimentRun]`.

---

## 8. Cross-SDK Parity Requirements

Kaizen exists in kailash-rs at `crates/kailash-kaizen/`. Cross-SDK parity targets:

- `CostDelta` struct: identical field names, identical microdollar units, identical `to_json()` shape.
- `TraceEvent` fingerprint: identical SHA-256 hash format (already specified in `specs/kaizen-observability.md` cross-SDK parity section).
- `SQLiteSink` table schema: identical column names and types.
- Rank-0-only emission rule: identical discipline (Rust equivalent: check `torch::distributed::get_rank()` via pyo3 bridge or analogue).

Cross-SDK follow-up is deferred until kailash-rs scopes a Rust-side Kaizen surface. The parity contract above (CostDelta + SQLiteSink + rank-0 discipline) is the baseline. No tracking issue required until Rust-side scoping begins.

---

## 9. Industry Comparison

| Capability                                     | Kaizen 2.12.0 | LangChain callbacks | OpenTelemetry semantic conventions | MLflow Traces (2.15+) |
| ---------------------------------------------- | ------------- | ------------------- | ---------------------------------- | --------------------- |
| Ambient-context tracker fallback               | Y             | N (manual wiring)   | Y (via tracer provider)            | Y (since 2.15)        |
| Cross-adapter metric-name namespacing locked   | Y             | N                   | Y (stable semconv)                 | Partial               |
| CostTracker microdollar precision              | Y             | N (USD floats)      | N (uncoupled)                      | N                     |
| Durable SQLite sink colocated with ML runs     | Y             | N                   | N (vendor sinks only)              | Partial               |
| Rank-0-only emission in distributed training   | Y             | N                   | N                                  | N                     |
| Frozen CostDelta + `sha256:<8hex>` fingerprint | Y             | N                   | N                                  | N                     |

**Position:** Kaizen is the only agent framework that auto-emits into the SAME run-tracker store used by the ML training lifecycle. A researcher running "train classical RF + use RAG agent for feature engineering + fine-tune LLM reranker" sees all three in one dashboard, one run tree, one cost rollup.

---

## 10. Migration Path (kailash-kaizen 2.11.x → 2.12.0)

2.11.x users:

- `AgentDiagnostics.__init__` — gains `tracker=` kwarg as OPTIONAL. Existing calls continue to work.
- `CostTracker.CostDelta.cents` → DeprecationWarning shim for one release cycle (see §4.3). Removed at Kaizen 3.0 per approved-decisions.md Decision 11 analogy.
- `TraceExporter()` default sink — was `NoOpSink`, now `SQLiteSink(ambient store)` IF an ambient tracker exists. Pure-NoOp mode still available via `TraceExporter(sink=NoOpSink())` explicit.
- `LLMDiagnostics` — NEW class, no migration.
- `InterpretabilityDiagnostics.__init__` — gains `tracker=` kwarg.

No breaking removal in 2.12.0. One deprecation (CostDelta.cents) with a one-release shim.

---

## 11. Release Coordination Notes

Part of the kailash-ml 1.0.0 wave release (see `pact-ml-integration-draft.md` §10 for the full wave list).

**Release order position:** after kailash 2.9.0 (needs expanded `Diagnostic` Protocol from `src/kailash/diagnostics/protocols.py`). Parallel with kailash-pact 0.10.0, kailash-nexus 2.2.0, kailash-dataflow 2.1.0.

**Parallel-worktree ownership:** kaizen-specialist agent owns `packages/kailash-kaizen/pyproject.toml`, `packages/kailash-kaizen/src/kailash_kaizen/__init__.py::__version__`, and `packages/kailash-kaizen/CHANGELOG.md`. Every other agent's prompt MUST exclude these files.

---

## 12. Cross-References

- kailash-ml specs consuming this surface:
  - `ml-tracking-draft.md` §10 — ambient contextvar discipline.
  - `ml-diagnostics-draft.md` — `DLDiagnostics` symmetric contract.
  - `ml-automl-draft.md` — `GuardrailConfig.max_llm_cost_usd` read in microdollars via shared CostTracker.
- Kaizen companion specs:
  - `specs/kaizen-observability.md` — TraceExporter + AgentDiagnostics core (unchanged in shape).
  - `specs/kaizen-advanced.md` — existing CostTracker (migrated here).
  - `specs/kaizen-interpretability.md` — InterpretabilityDiagnostics (gains tracker kwarg).
- Rule references:
  - `rules/tenant-isolation.md` §4 — bounded label cardinality on per-provider metrics.
  - `rules/event-payload-classification.md` §2 — fingerprint format for payloads.
  - `rules/facade-manager-detection.md` §2 — Tier 2 wiring tests.
  - `rules/independence.md` — no commercial-SDK coupling.
  - `rules/security.md` — `math.isfinite` on financial fields.
