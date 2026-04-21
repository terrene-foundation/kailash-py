# Kaizen Observability — AgentDiagnostics + TraceExporter

Authoritative spec for `kaizen.observability` (PR#6 of issue #567). This is the context-managed agent-run diagnostic adapter and the single-filter-point TraceExporter that routes `kailash.diagnostics.protocols.TraceEvent` records to durable sinks with a cross-SDK-locked SHA-256 fingerprint.

## Scope

`kaizen.observability` covers three concerns:

1. **TraceExporter** — the single-filter-point sink adapter for `TraceEvent` records emitted during an agent run.
2. **AgentDiagnostics** — the context-managed `Diagnostic` Protocol adapter that aggregates captured events into a `report()` summary (counts, cost rollup, p50/p95 duration, error rate).
3. **Cross-SDK parity** — byte-identical SHA-256 fingerprints with kailash-rs (issue #468 / v3.17.1+, commit `e29d0bad`) so a Rust subscriber reading a Python-emitted event produces the same forensic correlation hash.

The cross-SDK Protocol definitions for `TraceEvent`, `TraceEventType`, `TraceEventStatus`, and `compute_trace_event_fingerprint` live in `src/kailash/diagnostics/protocols.py` (PR#0 of issue #567). This package is the concrete Kaizen-side adapter; the Protocol is the contract.

## Public API

```python
from kaizen.observability import (
    AgentDiagnostics,
    AgentDiagnosticsReport,
    TraceExporter,
    TraceExportError,
    JsonlSink,
    NoOpSink,
    CallableSink,
    SinkCallable,
    compute_fingerprint,
    jsonl_exporter,
    callable_exporter,
)
```

All names are eagerly imported from submodules (`agent_diagnostics`, `trace_exporter`) into the package `__init__` — no lazy `__getattr__`, so CodeQL resolves every `__all__` entry at module scope per `rules/zero-tolerance.md` Rule 1a and `rules/orphan-detection.md` §6.

## TraceExporter

**Contract.** Single-point-of-emission sink adapter. Every `TraceEvent` routed through `.export(event)` (or `.export_async(event)`) is:

1. Type-guarded (raises `TypeError` on a non-`TraceEvent`).
2. Fingerprinted via `compute_trace_event_fingerprint(event)` — the cross-SDK-locked helper from `kailash.diagnostics.protocols`.
3. Handed to the configured sink as `(event, fingerprint)`.
4. Counted via bounded `exported_count` / `errored_count` — no unbounded event buffer (per `rules/observability.md` bounded-buffer discipline).

Sinks are pluggable but all in-tree options are free of third-party vendor coupling:

| Sink               | Shape                                                      | Use case                                         |
| ------------------ | ---------------------------------------------------------- | ------------------------------------------------ |
| `NoOpSink()`       | discards                                                   | default; tests that only observe fingerprints    |
| `JsonlSink(path)`  | appends one JSON line per event (thread-safe via `Lock`)   | durable on-disk trace log                        |
| `CallableSink(fn)` | delegates to a sync or async callable taking `(event, fp)` | bridge to user code (OTel emitter, IPC bus, ...) |

**Error handling.** By default, sink failures are WARN-logged and swallowed (`raise_on_error=False`) per `rules/observability.md` Rule 7 carve-out for observability side paths — the agent operation itself MUST NOT break because the trace sink failed. Callers who need hard enforcement pass `raise_on_error=True`; sink failures then raise `TraceExportError`.

**Third-party vendor policy.** No Langfuse / LangSmith / commercial-SDK imports anywhere under `kaizen.observability`. `rules/independence.md` forbids commercial-SDK coupling. Users who want those sinks pass a `CallableSink` wrapping whatever they choose — the in-tree surface is strictly foundation-only.

## AgentDiagnostics

**Contract.** Context-managed adapter that satisfies `kailash.diagnostics.protocols.Diagnostic` at runtime (`isinstance(diag, Diagnostic) is True`). Wraps a `TraceExporter` so every captured event is routed to the durable sink AND retained for rollup. The rollup is complementary to the durable export, not a replacement.

**Usage.**

```python
from kaizen.observability import AgentDiagnostics
from kaizen_agents import Delegate

with AgentDiagnostics(run_id="task-42") as diag:
    agent = Delegate(model=os.environ["OPENAI_PROD_MODEL"])
    agent.attach_trace_exporter(diag.exporter)
    result = agent.run("analyze revenue trend")

report = diag.report()
# {
#   "run_id": "task-42",
#   "event_count": 2,
#   "event_counts": {"agent.run.start": 1, "agent.run.end": 1},
#   "total_cost_microdollars": 17_500,
#   "duration_ms_p50": 420.0,
#   "duration_ms_p95": 880.0,
#   "error_rate": 0.0,
#   "errored_exports": 0,
# }
```

**Rollup shape.** `AgentDiagnosticsReport` is a frozen dataclass with `to_dict()`:

- `run_id`: correlation ID for this session.
- `event_count`: total events captured.
- `event_counts`: count per `event_type` (enum `.value` keys).
- `total_cost_microdollars`: sum across all events — **integer microdollars**, never float dollars (cross-SDK alignment with `kaizen.cost.tracker` + kailash-rs#38).
- `duration_ms_p50` / `duration_ms_p95`: observed durations across events that reported one (`None` when zero did).
- `error_rate`: fraction of events whose `status` is `TraceEventStatus.ERROR` (0.0 when no events have a populated status).
- `errored_exports`: sink failures counted by the underlying exporter.

**Bounded history.** Per-event rollup data is held in a `deque(maxlen=max_history)` (default 10_000). Events beyond the bound are evicted; the exporter sees every event regardless.

**Signature-free.** `AgentDiagnostics` does NOT make LLM decisions. It is a pure data aggregator — no if-else routing, no keyword matching, no classification logic. Outside the scope of `rules/agent-reasoning.md` (which applies to code that decides what an agent should _think_ or _do_).

## BaseAgent Hot-Path Wiring

Closes `rules/orphan-detection.md` §1 for `kaizen.observability`:

- `BaseAgent._trace_exporter` — `None` by default; set via `.attach_trace_exporter(exporter)`.
- `BaseAgent.trace_exporter` — read-only property.
- `AgentLoop.run_sync` / `run_async` — emit `agent.run.start` and `agent.run.end` TraceEvents through the attached exporter (when set). Events carry:
  - Stable `run_id` across start/end per `rules/observability.md` Rule 2 (correlation ID).
  - `parent_event_id` on the end event pointing to the start event's `event_id`.
  - `duration_ms` on the end event.
  - `status="ok"` on success, `status="error"` on exception.

**Fire-and-forget.** Trace emission is structured so exporter failures WARN-log and continue — the agent's hot path MUST NOT break because a trace sink failed. The `_emit_trace_event` helper in `kaizen/core/agent_loop.py` is the single filter point.

## Cross-SDK Fingerprint Contract

**Invariant.** `compute_trace_event_fingerprint(event)` (Python) and the kailash-rs `trace_event::fingerprint(event)` helper MUST produce byte-identical 64-hex-char SHA-256 digests for the same logical input.

**Canonicalization (byte-exact).**

1. `event.to_dict()` → canonical-shape dict. Optional `None` fields preserved; Enum values as strings; timestamps as ISO-8601 with explicit `+00:00` offset (never `Z`).
2. `json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)` → compact JSON matching Rust `serde_json::to_string(&BTreeMap)` byte-for-byte.
3. SHA-256 of the UTF-8 bytes, hex-encoded lowercase.

**Comparison.** `hmac.compare_digest` (Python) / `subtle::ConstantTimeEq` (Rust) on the hex digest. Never `==` (timing side-channel per `rules/security.md`).

**Audit-chain sibling.** The PACT audit chain's `AuditAnchor.compute_hash` (`src/kailash/trust/pact/audit.py`) uses the sibling N4 canonical form — same sort-keys, compact separators, UTF-8, SHA-256 discipline, but with a colon-delimited content envelope specific to audit anchors. The two helpers are peers in the cross-SDK contract, not the same function. TraceEvent canonicalization is JSON-dict-shaped (one event in isolation); audit anchor canonicalization is chain-shaped (each anchor carries `previous_hash`).

## Tenant Isolation and Classification

**Payload hashing.** `TraceEvent.payload_hash` uses the same `"sha256:<8-hex>"` prefix format mandated by `rules/event-payload-classification.md` §2. Emitters MUST apply the classification helper (`dataflow.classification.event_payload.format_record_id_for_event` or equivalent) BEFORE constructing the event — classified string PKs hash to `payload_hash` and are EXCLUDED from `payload`. The `TraceExporter` does NOT re-hash payload contents; it trusts the emitter's classification discipline (consistent with the single-filter-point rule: the hash happens at emit, not at export).

**Tenant scope.** `TraceEvent.tenant_id` (Optional) — when populated, downstream sinks MAY partition storage and metrics by tenant per `rules/tenant-isolation.md` §§4–5. `None` is permitted only for single-tenant deployments.

**Metrics cardinality.** Sinks that emit Prometheus metrics from the trace stream MUST bound `tenant_id` label cardinality per `rules/tenant-isolation.md` §4 (top-N strategy or aggregation tier).

## Security Threats

| Threat                              | Mitigation                                                                                                                                                                                                                                          |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Prompt-injection-via-trace          | `TraceEvent.payload` is caller-supplied; sinks that render payloads to HTML/Markdown MUST apply output-encoding per `rules/security.md` § Output Encoding. The Protocol defines the field shape; payload sanitization is the sink's responsibility. |
| Classified-PK leak via payload      | Emitter MUST hash classified PKs to `payload_hash` and exclude raw values from `payload` per `rules/event-payload-classification.md` §2. `TraceExporter` trusts the emitter — a leak at the sink is a leak at the emitter.                          |
| Secrets in trace fields             | Per `rules/security.md` § No secrets in logs AND `rules/observability.md` Rule 4: never populate `payload` with tokens, passwords, or PII. Tool-call arguments routed through trace payloads MUST be redacted at the adapter.                       |
| Third-party vendor SDK coupling     | `rules/independence.md` forbids Langfuse / LangSmith / commercial-SDK imports. In-tree sinks (`NoOpSink`, `JsonlSink`, `CallableSink`) are foundation-only. Users bridge to vendors via their own `CallableSink`.                                   |
| Timing side-channel on fingerprint  | Consumers MUST use `hmac.compare_digest` (never `==`) when comparing fingerprints. Spec'd in `compute_trace_event_fingerprint` docstring.                                                                                                           |
| Mass-fingerprint DoS                | `TraceExporter` holds only bounded counters, no event buffer. Per-event SHA-256 cost is O(event-size); the `raise_on_error=False` default prevents a malicious sink from cascading failures into the agent hot path.                                |
| Log-level bleed of schema-level PII | Domain-prefixed log fields (`trace_exporter_*`, `agent_diag_*`) avoid `LogRecord`-reserved collisions (`rules/observability.md` Rule 9). Schema-revealing field names stay at DEBUG or are hashed per Rule 8.                                       |

## Testing Contract

**Tier 1 unit (`tests/unit/observability/test_trace_exporter_fingerprint.py`):** 15 tests covering determinism, hex shape, per-field sensitivity, canonicalization form (sort keys, compact separators, `+00:00`), Enum serialization, `cost_microdollars` MUST-be-int invariant, re-export parity, bounded-counter contract.

**Tier 2 integration (`tests/integration/observability/test_agent_diagnostics_wiring.py`):** 4 tests exercising a real `BaseAgent` against the mock provider:

1. `test_agent_run_invokes_trace_exporter_on_hot_path` — closes orphan-detection Rule 1 by asserting start + end TraceEvents actually fire via `AgentLoop`.
2. `test_agent_diagnostics_session_captures_rollup` — closes facade-manager-detection Rule 1 by importing through the facade (`from kaizen.observability import ...`) and asserting externally-observable rollup effects.
3. `test_detached_exporter_no_events_captured` — `attach_trace_exporter(None)` short-circuits emission.
4. `test_fingerprint_helper_reexport_matches_canonical` — `kaizen.observability.compute_fingerprint == kailash.diagnostics.protocols.compute_trace_event_fingerprint`.

## Related Specs

- `specs/kaizen-core.md` — `BaseAgent`, `AgentLoop`, `BaseAgentConfig`. `attach_trace_exporter` + `trace_exporter` property are the hot-path wiring surface for this spec.
- `specs/kaizen-judges.md` — `LLMDiagnostics` adapter (PR#5) uses the same `Diagnostic` Protocol; the same cross-SDK cost-microdollars invariant applies.
- `specs/kaizen-interpretability.md` — `InterpretabilityDiagnostics` adapter (PR#4); shares the `Diagnostic` Protocol contract.
- `specs/ml-diagnostics.md` — `DLDiagnostics` adapter (PR#1); downstream sink pattern precedent.
- `specs/alignment-diagnostics.md` — `AlignmentDiagnostics` adapter (PR#3); shares `run_id` correlation discipline.
- `specs/pact-absorb-capabilities.md` — PACT `verify_audit_chain` / `envelope_snapshot` (PR#7); the audit-chain fingerprint is the cross-SDK sibling of `compute_trace_event_fingerprint`.
- `specs/diagnostics-catalog.md` — catalog of every `Diagnostic` adapter with wiring-test file names.
- `src/kailash/diagnostics/protocols.py` — cross-SDK Protocol definitions (PR#0).
- `schemas/trace-event.v1.json` — language-neutral JSON Schema (PR#0).

## Cross-SDK Parity

- kailash-rs#468 (v3.17.1+, commit `e29d0bad`) — the Rust-side `TraceEvent` + `compute_trace_event_fingerprint` pair. 4 round-trip tests green. PR #497 on the Rust side awaits CI infra fixes.
- kailash-rs#497 — TraceExporter Kaizen-rs wiring tracker (this Python PR integrates against the byte-identical parity locked in kailash-rs#468).

## Attribution

Portions of this module were originally contributed from MLFP (Apache-2.0, `/private/tmp/pcml-run26-template/shared/mlfp06/diagnostics/agent.py` + `_traces.py`, ~1028 LOC pre-cleanup) and re-authored for the Kailash ecosystem. The reference implementation was stripped of Langfuse coupling (`rules/independence.md`), rerouted through `CostTracker` microdollars (`rules/framework-first.md`), aligned with the N4 canonical fingerprint form, and type-strengthened to Protocol-conforming.

Donation history: kailash-py issue #567, PR#6 of 7.
