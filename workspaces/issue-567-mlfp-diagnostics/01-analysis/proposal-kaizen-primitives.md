# Issue #567 — Kaizen-Owned Primitives Proposal

**Scope**: `JudgeCallable`, `TraceEvent`, `AgentDiagnostics`, and the supporting
`TraceExporter` / `ROUGE/BLEU` placement decisions for the MLFP upstream at the
kailash-kaizen layer.

**Status**: Design proposal for review. Companion to
`01-analysis/failure-points.md` (§ 1.2 LLMDiagnostics + JudgeCallable, § 1.5
AgentDiagnostics + TraceEvent).

**Verified grep sources** (per `cross-sdk-inspection.md` § 5):

- `packages/kailash-kaizen/src/kaizen/core/autonomy/observability/__init__.py`
  — exports `Metric`, `LogEntry`, `AuditEntry`, `TracingManager`,
  `MetricsCollector`, `StructuredLogger`, `LoggingManager`, `AuditStorage`,
  `FileAuditStorage`, `AuditTrailManager`, `ObservabilityManager`. No
  `TraceEvent` primitive; no agent-level run record.
- `packages/kailash-kaizen/src/kaizen/core/autonomy/observability/types.py`
  — `AuditEntry` (action/result), `LogEntry` (level/message), `Metric`
  (counter/gauge/histogram). Span type is `opentelemetry.trace.Span`
  (ephemeral, not a persisted dataclass).
- `packages/kailash-kaizen/src/kaizen/cost/tracker.py` — microdollar-based
  accumulator (`_MICRODOLLARS_PER_USD = 1_000_000`), Cross-SDK-aligned with
  kailash-rs#38. THIS is the canonical cost tracker for issue-567.
- `packages/kailash-kaizen/src/kaizen/providers/cost.py` — float-USD legacy
  tracker; NOT canonical; do NOT route AgentDiagnostics through it.
- `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py:270` —
  `class Delegate` exists, is the engine-layer entry point per
  `framework-first.md`.

---

## 1. Kaizen Observability Surface Inventory (Current State)

The current observability surface is a 3-tier model; `TraceEvent` /
`JudgeCallable` / `AgentDiagnostics` are greenfield.

| Primitive                | Role                                                 | Cardinality                |
| ------------------------ | ---------------------------------------------------- | -------------------------- |
| `Metric`                 | Prometheus-style counter/gauge/histogram observation | High-frequency, bounded    |
| `LogEntry`               | Structured log line (DEBUG → CRITICAL) with trace_id | High-frequency, correlated |
| `AuditEntry`             | Immutable compliance row (SOC2/GDPR/HIPAA)           | Per-action, append-only    |
| OTel `Span`              | Distributed trace span (via `TracingManager`)        | Per-operation, ephemeral   |
| _(missing)_ `TraceEvent` | Persisted, exportable agent-run event                | Per-step within agent run  |

**What's missing**: a **persisted, exportable, agent-scoped** event record.
`LogEntry` is too coarse (a text message + context dict, no typed
event_type). `AuditEntry` is for compliance (action/result, human-readable).
OTel `Span` is the right abstraction for DISTRIBUTED tracing but spans are
ephemeral and exported via OTLP exporters — they are NOT the right medium for
local JSONL dumps, offline analysis, cost reconciliation, or replay-debugging
an agent run.

**Decision**: `TraceEvent` sits ADJACENT to the existing types. It is NOT a
replacement for any of them. The boundary:

| Event class      | Written when                                                        | Read by                                       |
| ---------------- | ------------------------------------------------------------------- | --------------------------------------------- |
| `Metric`         | Hot loops, aggregations (tool invocations per second)               | Prometheus / Grafana                          |
| `LogEntry`       | Free-text debug messages, request flow narration                    | Humans tailing logs, ELK                      |
| `AuditEntry`     | Compliance-material actions (permission grant, tool exec)           | Compliance auditors (SOC2/GDPR)               |
| OTel `Span`      | Cross-service distributed tracing                                   | Jaeger, Zipkin, OTLP collectors               |
| **`TraceEvent`** | **Every step of an agent run — tool call, LLM call, judge verdict** | **Agent replay, cost reconciliation, export** |

**Integration path**: Land `TraceEvent` alongside the existing types inside
`packages/kailash-kaizen/src/kaizen/core/autonomy/observability/` (NOT a
parallel `kaizen.observability/` top-level — that would be a
`rules/orphan-detection.md` §1 duplicate-facade violation). New sub-modules:

```
kaizen/core/autonomy/observability/
  types.py              ← add TraceEvent dataclass
  trace_event.py        ← emitter + helpers
  trace_exporter.py     ← TraceExporter protocol + NoOp/Jsonl impls
  agent_diagnostics.py  ← context manager wiring TraceEvent + CostTracker
```

`ObservabilityManager` gains a `.trace_events` accessor (defaults to a
bounded `deque`) and a `.register_exporter(exporter)` method.

---

## 2. `TraceEvent` — Canonical Protocol

### 2.1 Dataclass Definition (Python)

```python
# kaizen/core/autonomy/observability/types.py (extension)

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

TraceEventType = Literal[
    "agent.run.start",
    "agent.run.end",
    "agent.step",           # one TAOD cycle (Think/Act/Observe/Decide)
    "tool.call.start",
    "tool.call.end",
    "llm.call.start",
    "llm.call.end",
    "judge.verdict",
    "loop.suspected",
    "budget.exceeded",
    "error",
]

@dataclass(frozen=True)
class TraceEvent:
    """
    Persisted, exportable agent-run event.

    One TraceEvent is emitted per step of an agent run. Unlike OTel Spans
    (ephemeral, exported via OTLP) or LogEntry (free-text), TraceEvent is a
    structured, typed row suitable for: JSONL export, cost reconciliation,
    replay-debugging, and third-party exporter fan-out.

    Cross-SDK fingerprint contract (per rules/event-payload-classification.md):
    - `agent_id` is a free-form string; hash BEFORE emitting to external
      exporters if classified.
    - `payload` dict MUST NOT carry raw classified values; hash per the
      `format_record_id_for_event` contract.
    """

    # Required identity
    event_id: str                         # uuid4
    event_type: TraceEventType
    timestamp: datetime                   # UTC

    # Correlation
    run_id: str                           # ties all events in one agent run
    agent_id: str                         # which agent emitted this
    parent_event_id: str | None = None    # tree structure within a run
    trace_id: str | None = None           # OTel correlation (optional)
    span_id: str | None = None            # OTel correlation (optional)

    # Governance (per rules/tenant-isolation.md §5)
    tenant_id: str | None = None          # MUST be set when multi-tenant context active
    envelope_id: str | None = None        # PACT envelope ID when operating under one

    # Semantic fields (type-specific; null when not applicable)
    tool_name: str | None = None          # for tool.call.*
    llm_model: str | None = None          # for llm.call.*
    prompt_tokens: int | None = None      # for llm.call.end
    completion_tokens: int | None = None  # for llm.call.end
    cost_microdollars: int = 0            # integer, per kaizen.cost contract
    duration_ms: float | None = None      # wall-clock duration (end events)
    status: Literal["ok", "error", "timeout"] | None = None

    # Opaque payload (caller-supplied; MUST be JSON-serializable)
    # Classified values MUST be hashed before landing here.
    payload: dict[str, Any] = field(default_factory=dict)

    # Payload-hash fingerprint for cross-SDK correlation
    # (per rules/event-payload-classification.md §2 — 8 hex chars = 32 bits)
    payload_hash: str | None = None       # "sha256:XXXXXXXX" or None
```

### 2.2 Language-Neutral JSON Schema (cross-SDK)

```json
{
  "$id": "https://terrene.foundation/schemas/kaizen/trace-event/v1.json",
  "type": "object",
  "required": [
    "event_id",
    "event_type",
    "timestamp",
    "run_id",
    "agent_id",
    "cost_microdollars"
  ],
  "properties": {
    "event_id": { "type": "string", "format": "uuid" },
    "event_type": {
      "type": "string",
      "enum": [
        "agent.run.start",
        "agent.run.end",
        "agent.step",
        "tool.call.start",
        "tool.call.end",
        "llm.call.start",
        "llm.call.end",
        "judge.verdict",
        "loop.suspected",
        "budget.exceeded",
        "error"
      ]
    },
    "timestamp": { "type": "string", "format": "date-time" },
    "run_id": { "type": "string" },
    "agent_id": { "type": "string" },
    "parent_event_id": { "type": ["string", "null"] },
    "trace_id": { "type": ["string", "null"] },
    "span_id": { "type": ["string", "null"] },
    "tenant_id": { "type": ["string", "null"] },
    "envelope_id": { "type": ["string", "null"] },
    "tool_name": { "type": ["string", "null"] },
    "llm_model": { "type": ["string", "null"] },
    "prompt_tokens": { "type": ["integer", "null"], "minimum": 0 },
    "completion_tokens": { "type": ["integer", "null"], "minimum": 0 },
    "cost_microdollars": { "type": "integer", "minimum": 0 },
    "duration_ms": { "type": ["number", "null"] },
    "status": {
      "type": ["string", "null"],
      "enum": ["ok", "error", "timeout", null]
    },
    "payload": { "type": "object" },
    "payload_hash": {
      "type": ["string", "null"],
      "pattern": "^sha256:[0-9a-f]{8}$"
    }
  }
}
```

Schema file lives at `packages/kailash-kaizen/schemas/trace-event.v1.json`
(new directory). Kailash-rs MUST expose an identical Rust binding
(serde-serializable struct); file cross-SDK ticket on day 1.

### 2.3 Cross-SDK Fingerprint Contract

Per `rules/event-payload-classification.md` §2, the `payload_hash` field uses
the 8-hex-char SHA-256 prefix contract so a Rust service emitting a
TraceEvent and a Python subscriber produce the same fingerprint for the same
raw value. Integer cost MUST be microdollars (8-hex is bytes, not cost).

---

## 3. `JudgeCallable` Protocol

### 3.1 Signatures

```python
# kaizen/judges/types.py

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

@dataclass(frozen=True)
class JudgeInput:
    """
    Input to a JudgeCallable. Structured dataclass so new fields can land
    backwards-compatibly.

    Arbitrary `rubric` field allows per-call rubric specification without
    hardcoding the faithfulness/refusal taxonomy into the protocol.
    """
    prompt: str
    candidate_a: str                         # REQUIRED — response being judged
    candidate_b: str | None = None           # set for pairwise judging
    reference: str | None = None             # ground truth for faithfulness
    rubric: str | None = None                # free-form scoring criteria
    context: dict[str, object] = field(default_factory=dict)

@dataclass(frozen=True)
class JudgeResult:
    """
    Output from a JudgeCallable. Every field is either directly asserted by
    the structured-output signature or accumulated by the framework (cost/
    tokens).

    - `score` is always populated; its meaning depends on the judge
      (faithfulness: 0..1; pairwise: a probability; refusal: a rejection
      probability).
    - `winner` is populated ONLY when JudgeInput.candidate_b is set (pairwise).
    - `reasoning` is always populated for audit; LLM produces it via the
      Signature's OutputField(description="reasoning").
    """
    score: float                             # rubric-dependent 0..1
    winner: Literal["A", "B", "tie", None] = None   # pairwise only
    reasoning: str = ""                      # auditable explanation
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_microdollars: int = 0               # MUST match CostTracker record
    judge_model: str = ""                    # which model was invoked
    metadata: dict[str, object] = field(default_factory=dict)

@runtime_checkable
class JudgeCallable(Protocol):
    """
    Protocol for LLM-as-judge callables. All judges MUST route through
    kaizen_agents.Delegate (per rules/framework-first.md § Specialist
    Consultation). Raw OpenAI / Anthropic / litellm calls are BLOCKED.
    """
    async def __call__(self, judge_input: JudgeInput) -> JudgeResult: ...
```

### 3.2 Delegate-Routed Base Implementation (sketch)

```python
# kaizen/judges/llm_judge.py

import os
from kaizen_agents import Delegate
from kaizen.core import Signature, InputField, OutputField
from kaizen.cost.tracker import CostTracker   # microdollar tracker

class PairwiseJudgeSignature(Signature):
    """
    Structured output for pairwise LLM-as-judge.
    Position-swap bias mitigation is a FRAMEWORK concern, not a signature
    concern — see LLMJudge._judge_with_swap below.
    """
    prompt: str = InputField(description="The user prompt being evaluated")
    candidate_a: str = InputField(description="Response labeled A")
    candidate_b: str = InputField(description="Response labeled B")
    rubric: str = InputField(description="Scoring rubric (may be blank)")
    winner: Literal["A", "B", "tie"] = OutputField(
        description="Which candidate is better given the rubric, or 'tie' if indistinguishable"
    )
    score_a: float = OutputField(description="Rubric score for A, 0..1")
    score_b: float = OutputField(description="Rubric score for B, 0..1")
    reasoning: str = OutputField(description="Why this verdict")

class LLMJudge:
    """
    Delegate-wrapped LLM-as-judge with position-swap bias mitigation AND
    per-judge-run budget cap routed through kaizen.cost.CostTracker.
    """
    def __init__(
        self,
        model: str | None = None,
        *,
        cost_tracker: CostTracker | None = None,
        budget_microdollars: int | None = None,     # per-run cap; raise JudgeBudgetExhausted on cross
    ) -> None:
        self._model = model or os.environ["OPENAI_PROD_MODEL"]
        self._delegate = Delegate(model=self._model, signature=PairwiseJudgeSignature)
        self._cost = cost_tracker                    # shared across calls
        self._budget = budget_microdollars
        self._spent = 0

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
        if judge_input.candidate_b is None:
            # pointwise judging — use different signature (not shown here)
            raise NotImplementedError("pointwise judging — separate sig")
        return await self._judge_with_swap(judge_input)

    async def _judge_with_swap(self, judge_input: JudgeInput) -> JudgeResult:
        # Run judge in BOTH orderings to mitigate position bias
        forward = await self._run_one(judge_input.prompt, judge_input.candidate_a, judge_input.candidate_b, judge_input.rubric or "")
        # BUDGET CHECK between the two calls — fail-closed per zero-tolerance Rule 3
        self._check_budget()
        swapped = await self._run_one(judge_input.prompt, judge_input.candidate_b, judge_input.candidate_a, judge_input.rubric or "")
        # AGGREGATION: the LLM's structured output itself disambiguates ties.
        # Framework-level logic below is NOT agent reasoning — it's result
        # parsing per rules/agent-reasoning.md "Permitted Deterministic Logic".
        return self._aggregate(forward, swapped)

    async def _run_one(self, prompt: str, a: str, b: str, rubric: str):
        result = await self._delegate.run(prompt=prompt, candidate_a=a, candidate_b=b, rubric=rubric)
        # Record cost via the microdollar tracker (the LLM call cost, not the judge's "score")
        if self._cost is not None:
            self._cost.record_usage(provider="openai", modality="text", model=self._model, cost_usd=result.cost_usd, ...)
            self._spent += int(round(result.cost_usd * 1_000_000))
        return result

    def _check_budget(self) -> None:
        if self._budget is not None and self._spent >= self._budget:
            raise JudgeBudgetExhausted(f"judge spent {self._spent} µ$ >= cap {self._budget} µ$")

    def _aggregate(self, forward, swapped):
        # Position-swap is a probe: the LLM produces a "winner" in both orderings.
        # If forward says A wins and swapped says B wins, the LLM actually picks
        # the SAME candidate both times (B in the swapped view IS the original A).
        # Consistent winner → confident verdict. Flipped winner → position bias
        # detected; return score_a/score_b AVERAGE and winner="tie" with an
        # annotated reasoning.
        ...
```

### 3.3 Position-Swap Bias Mitigation — LLM Reasoning, Not Regex

**BEFORE** (hypothetical MLFP-style — BLOCKED by `rules/agent-reasoning.md`):

```python
# BLOCKED — regex over free-text output
response_forward = openai.chat.completions.create(
    messages=[{"role": "user", "content": f"A: {cand_a}\nB: {cand_b}\nWhich is better?"}]
).choices[0].message.content
if re.search(r"\bA is (better|preferred|correct)\b", response_forward, re.I):
    forward_winner = "A"
elif re.search(r"\bB is (better|preferred|correct)\b", response_forward, re.I):
    forward_winner = "B"
else:
    forward_winner = "tie"  # regex failed → silent miscount
# repeat for swapped order...
```

Problems: (a) raw OpenAI call bypasses Delegate (framework-first violation),
(b) regex on LLM output is exactly the anti-pattern
`rules/agent-reasoning.md` § Detection Patterns #1 and #2 prohibit, (c)
silent miscount when regex doesn't match.

**AFTER** (Kaizen-compliant):

```python
# DO — structured output via Signature; LLM itself decides the winner
class PairwiseJudgeSignature(Signature):
    prompt: str = InputField(...)
    candidate_a: str = InputField(...)
    candidate_b: str = InputField(...)
    rubric: str = InputField(...)
    winner: Literal["A", "B", "tie"] = OutputField(description="Which is better, or 'tie'")
    score_a: float = OutputField(description="Score for A, 0..1")
    score_b: float = OutputField(description="Score for B, 0..1")
    reasoning: str = OutputField(description="Why")

delegate = Delegate(model=os.environ["OPENAI_PROD_MODEL"], signature=PairwiseJudgeSignature)
forward = await delegate.run(prompt=p, candidate_a=a, candidate_b=b, rubric=r)
swapped = await delegate.run(prompt=p, candidate_a=b, candidate_b=a, rubric=r)
# forward.winner is typed Literal — no regex, no miscount
# swapped.winner in {"A","B","tie"} — the SWAPPED position
# If forward.winner == "A" and swapped.winner == "B", the LLM picked the
# SAME candidate both times (the underlying response A) → consistent verdict.
# If forward.winner == swapped.winner, position bias detected → tie.
```

### 3.4 Calibration / Rubrics — No Hardcoded Taxonomy

The protocol MUST NOT hardcode faithfulness / refusal / harmfulness into
`JudgeResult`. `JudgeInput.rubric` is a free-form string; the LLM reads it as
part of the prompt and applies it. For specialized judges
(`FaithfulnessJudge`, `RefusalCalibrator`), a Kaizen library ships canned
rubric strings and thin wrappers that set `rubric=` before calling the
underlying `LLMJudge`. These wrappers contain NO decision logic —
they're pre-built prompts.

---

## 4. `AgentDiagnostics` Integration Pattern

### 4.1 Scope & Wiring

**Pattern**: agent-instance-scoped context manager, NOT a wrapper around
`agent.run()`. This gives consumer code the flexibility to capture a single
run, a batch of runs, or a scoped transaction across multiple agents.

```python
# kaizen/core/autonomy/observability/agent_diagnostics.py

from contextlib import asynccontextmanager
from collections import deque
from typing import Iterator
from kaizen.cost.tracker import CostTracker  # microdollar
from .types import TraceEvent

class AgentDiagnostics:
    """
    Context-managed capture of TraceEvents, cost, and loop-detection across
    one or more agent runs.

    Integration points:
    - CostTracker: shared instance; every LLM/tool call records through it.
      The diagnostics object takes a `cost_tracker=` kwarg to join an existing
      tracker (per run) OR creates its own (per diagnostic scope).
    - GovernanceContext (PACT): when active, all TraceEvents carry the frozen
      envelope_id from GovernanceContext.current(). Diagnostics does NOT
      reach into the engine's audit chain (rules/pact-governance.md MUST #1);
      it reads envelope_id from the ContextVar-propagated GovernanceContext.
    - Tenant isolation: tenant_id propagated via ContextVar; every TraceEvent
      stamps tenant_id from get_tenant_id() at emit time.
    - Loop detection: windowed heuristic at the trace-event level —
      N repeated (tool_name, payload_hash) tuples within a sliding window of
      K events → emit `loop.suspected` TraceEvent. Canonical algorithm:
      `deque(maxlen=K)` of recent (tool_name, payload_hash); on every tool
      call, count occurrences of the current tuple; if ≥N, emit
      loop.suspected and raise `LoopSuspectedWarning`. K=20, N=5 defaults.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        cost_tracker: CostTracker | None = None,
        exporters: list[TraceExporter] | None = None,
        max_events: int = 10_000,
        loop_window_size: int = 20,
        loop_threshold: int = 5,
    ) -> None:
        self.agent_id = agent_id
        self.cost_tracker = cost_tracker or CostTracker()
        self._events: deque[TraceEvent] = deque(maxlen=max_events)
        self._exporters = exporters or []
        self._loop_window: deque[tuple[str, str | None]] = deque(maxlen=loop_window_size)
        self._loop_threshold = loop_threshold

    @asynccontextmanager
    async def capture(self, run_id: str) -> Iterator["AgentDiagnostics"]:
        """Mark the start of an agent run; flush exporters on exit."""
        self.emit(TraceEvent(event_type="agent.run.start", run_id=run_id, ...))
        try:
            yield self
        finally:
            self.emit(TraceEvent(event_type="agent.run.end", run_id=run_id, ...))
            await self._flush_exporters()

    def emit(self, event: TraceEvent) -> None:
        self._events.append(event)
        if event.event_type == "tool.call.start":
            self._check_loop(event.tool_name, event.payload_hash)

    def _check_loop(self, tool_name: str, payload_hash: str | None) -> None:
        self._loop_window.append((tool_name, payload_hash))
        if self._loop_window.count((tool_name, payload_hash)) >= self._loop_threshold:
            self.emit(TraceEvent(event_type="loop.suspected", ...))
            # WARN per observability.md Rule 3 — framework chose not to raise
            logger.warning("agent.loop.suspected", agent_id=self.agent_id, tool_name=tool_name, occurrences=self._loop_threshold)

    @property
    def total_cost_microdollars(self) -> int:
        # Routes through CostTracker — zero custom accumulation
        return self.cost_tracker.total_cost_microdollars

    async def _flush_exporters(self) -> None:
        events = list(self._events)
        for exporter in self._exporters:
            await exporter.export(events)
```

### 4.2 Key Invariants

- `total_cost_microdollars` ALWAYS routes through `CostTracker`. No local
  accumulation. Regression test: `assert diag.total_cost_microdollars ==
tracker.total_cost_microdollars` after every run.
- `tenant_id` stamped from `ContextVar` at emit time; no defaulting.
- PACT `envelope_id` read-only from `GovernanceContext.current()`.
- Loop detection runs at trace-event level (windowed heuristic), NOT
  intercepting retries inside Delegate. Delegate already tracks retries;
  AgentDiagnostics detects semantic loops (same-tool-same-arg thrashing).

---

## 5. ROUGE / BLEU / BERTScore — Placement

**Decision**: separate namespace `kaizen.evaluation.*`.

**Rationale**: ROUGE / BLEU / BERTScore are pure algorithmic metrics over
string/embedding pairs — they take no LLM and thus are NOT `JudgeCallable`.
Mixing them into `kaizen.judges.*` would conflate two distinct surfaces:

- `kaizen.judges.*` — LLM-backed, Delegate-routed, cost-tracked, budget-capped,
  requires API key.
- `kaizen.evaluation.*` — pure NumPy/torch math, deterministic, no cost,
  no keys.

The distinction matters because users frequently want `kaizen.evaluation.*`
installed without `kaizen[judges]` (no API key footprint); and separating
them keeps the `[judges]` extra small.

```
kaizen/
  judges/              ← LLM-based, requires kaizen[judges]
    __init__.py
    types.py           ← JudgeInput, JudgeResult, JudgeCallable
    llm_judge.py       ← LLMJudge (Delegate-wrapped)
    faithfulness.py    ← FaithfulnessJudge (LLMJudge + rubric)
    refusal.py         ← RefusalCalibrator (LLMJudge + rubric)

  evaluation/          ← Algorithmic, requires kaizen[evaluation]
    __init__.py
    rouge.py           ← ROUGE-1/2/L (pure python)
    bleu.py            ← sacrebleu wrapper
    bertscore.py       ← bert-score wrapper (transformers)
```

Optional extras: `kaizen[judges]` (no heavy deps — just LLM stack), and
`kaizen[evaluation]` (`rouge-score`, `sacrebleu`, `bert-score` — pulls
torch+transformers). Users can install only the half they need.

---

## 6. Langfuse Strip Strategy — `TraceExporter` Protocol

Per `rules/independence.md`, Langfuse MUST NOT appear in
`pyproject.toml`. AgentDiagnostics ships with a tiny exporter protocol and
two in-tree implementations; third-party exporters (Langfuse, Honeycomb,
OpenTelemetry) live in user code.

```python
# kaizen/core/autonomy/observability/trace_exporter.py

from typing import Protocol, runtime_checkable
from .types import TraceEvent

@runtime_checkable
class TraceExporter(Protocol):
    """
    Protocol for exporting TraceEvents to a backing store.
    Implementations MUST be non-blocking at the call site; heavy IO happens
    inside the implementation's own task.
    """
    async def export(self, events: list[TraceEvent]) -> None: ...

class NoOpTraceExporter:
    """Default exporter — discards all events (used when no exporters registered)."""
    async def export(self, events: list[TraceEvent]) -> None:
        pass

class JsonlTraceExporter:
    """
    Append-only JSONL exporter to disk.
    Use for local replay-debugging and offline analysis.
    """
    def __init__(self, path: Path) -> None:
        self._path = path

    async def export(self, events: list[TraceEvent]) -> None:
        async with aiofiles.open(self._path, mode="a") as f:
            for e in events:
                await f.write(json.dumps(dataclasses.asdict(e), default=str) + "\n")
```

**Third-party exporters** (Langfuse, Honeycomb, Datadog APM, OTel/OTLP):
users implement the protocol in their own code OR install a
**third-party package** like `kaizen-exporter-langfuse` published by that
vendor or a community contributor. Not our concern.

```python
# user code, in a hypothetical kaizen-exporter-langfuse package:
from langfuse import Langfuse

class LangfuseExporter:
    def __init__(self, client: Langfuse) -> None:
        self._client = client

    async def export(self, events: list[TraceEvent]) -> None:
        for e in events:
            self._client.event(...).end()
```

---

## 7. Summary — Deliverables Per PR

Per the PR sequence in `failure-points.md` § 3, the following primitives
land at kailash-kaizen layer:

| PR                             | New files                                                              | Optional extras          |
| ------------------------------ | ---------------------------------------------------------------------- | ------------------------ |
| #3 LLMDiagnostics              | `kaizen/judges/*.py`, `schemas/pairwise-judge.v1.json`                 | NEW `kaizen[judges]`     |
|                                | `kaizen/evaluation/*.py`                                               | NEW `kaizen[evaluation]` |
| #5 AgentDiagnostics+TraceEvent | `kaizen/core/autonomy/observability/types.py` (+ TraceEvent dataclass) | (none new — in-tree)     |
|                                | `kaizen/core/autonomy/observability/trace_event.py`                    |                          |
|                                | `kaizen/core/autonomy/observability/trace_exporter.py`                 |                          |
|                                | `kaizen/core/autonomy/observability/agent_diagnostics.py`              |                          |
|                                | `schemas/trace-event.v1.json`                                          |                          |

**Cross-SDK ticket**: file `esperie/kailash-rs` issue for Rust
`TraceEvent` / `JudgeCallable` bindings using the JSON Schema as the shared
contract, labelled `cross-sdk`.

**Spec sweep** (per `rules/specs-authority.md` MUST #5b): editing
`specs/kaizen-advanced.md` for judges/traces triggers full-sibling
`specs/kaizen-*.md` re-derivation (core, signatures, providers,
llm-deployments, agents-core, agents-patterns, agents-governance).

**Regression test coverage (MUST — per `facade-manager-detection.md` MUST
Rule 1)**:

- `tests/integration/test_llm_judge_wiring.py` — real `.env` model, real
  Delegate, real `CostTracker`, assert position-swap agreement AND
  microdollar fidelity.
- `tests/integration/test_agent_diagnostics_wiring.py` — real agent run,
  assert `diag.total_cost_microdollars == tracker.total_cost_microdollars`
  AND `JsonlTraceExporter` writes parseable events.
- Medical-metaphor grep regression test (per failure-points §2.3).
- Independence grep test: `assert "langfuse" not in pyproject.toml`.
