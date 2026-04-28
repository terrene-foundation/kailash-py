---
priority: 10
scope: path-scoped
paths:
  - "**/dataflow/**"
  - "**/events*"
  - "**/domain_events/**"
  - "**/event_bus*"
---

# Event-Payload Classification Rules


<!-- slot:neutral-body -->

Every `DomainEvent` payload emitted from DataFlow write paths MUST be free of raw classified field values. Classified PK values (e.g. an `Account` keyed by `email` with `@classify("email", PII)`) MUST be hashed before emission; classified field names MUST NOT appear in event payloads that list mutated fields (`fields_changed` and friends).

The `DomainEvent` surface is strictly wider than the log surface. Every subscriber, every tracing span, every third-party observability vendor, and every downstream microservice sees event payloads. A value leaked into an event payload is strictly harder to recall than one in a log aggregator — the log-surface rule (`rules/observability.md` Rule 8) level-gates schema-revealing field names; the event-surface rule MUST filter or hash, because events have no level.

This rule is the event-surface sibling of `rules/dataflow-classification.md` (read/list/mutation-return redaction). Where that rule requires mutation return values to be redacted before being returned to the caller, this rule requires event payloads to be filtered before being published to the bus.

## MUST Rules

### 1. Event-Emission Paths Route `record_id` Through `format_record_id_for_event`

Every `_emit_write_event` / `DomainEventBus.publish` / equivalent entry point MUST pass `record_id` through `dataflow.classification.event_payload.format_record_id_for_event` (kailash-py) or the equivalent cross-SDK helper (kailash-rs v3.17.1+).

```python
# DO — single filter point at the emitter
from dataflow.classification.event_payload import format_record_id_for_event

def _emit_write_event(self, model_name, operation, record_id=None):
    policy = getattr(self, "_classification_policy", None)
    safe_record_id = format_record_id_for_event(
        policy=policy, model_name=model_name, record_id=record_id
    )
    event = DomainEvent(
        event_type=f"dataflow.{model_name}.{operation}",
        payload={"model": model_name, "operation": operation, "record_id": safe_record_id},
    )
    self._event_bus.publish(event)

# DO NOT — raw record_id into payload
event = DomainEvent(payload={"record_id": record_id})  # leaks classified PKs
```

**Why:** Placing the filter at every caller site (`create`, `update`, `upsert`, `delete`, every future mutation primitive) guarantees one of them drifts. A single filter point at the emitter is the only structural defense against drift. Evidence: kailash-rs BP-048 — every mutation path `create` / `update` / `upsert` / `delete` carried the same leak because each formatted `record_id` independently. Single-point fix closed all four in one commit.

### 2. Classified String PKs Hash, Integers Pass Through, Unclassified Strings Pass Through

The helper contract:

- `None` → `None`
- integer / float → `str(value)` (integer PK space is not classified data in itself; can't leak an email / SSN by value alone)
- unclassified string PK → `str(value)`
- classified string PK → `f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:8]}"`

8 hex chars = 32 bits of entropy: sufficient for forensic correlation across event + log + DB audit-trail streams, insufficient for rainbow-table reversal of typical PK strings.

```python
# DO — exact contract
def format_record_id_for_event(policy, model_name, record_id, pk_field="id"):
    if record_id is None:
        return None
    if isinstance(record_id, (int, float)):
        return str(record_id)
    if policy is None:
        return str(record_id)
    if policy.get_field(model_name, pk_field) is None:
        return str(record_id)
    raw = str(record_id).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:8]}"

# DO NOT — hash everything (loses grep-ability for unclassified PKs)
# DO NOT — hash only when MaskingStrategy is REDACT (classification itself is the signal)
# DO NOT — use a different hash / different prefix length than the cross-SDK contract
```

**Why:** The hash prefix and hex-length are intentionally identical across SDKs so a log line emitted by a Rust service and an event handled by a Python subscriber produce the same fingerprint for the same raw PK. Forensic correlation across polyglot deployments requires the prefix contract to be stable.

### 3. Classified Field Names MUST NOT Appear In `fields_changed` Or Equivalent

Any event payload key that lists mutated field names (`fields_changed`, `changed_columns`, `patched`, etc.) MUST partition into:

1. an **unclassified-names list** — the field names that are safe to emit as-is
2. a **classified-count scalar** — the count of classified fields that were mutated (for operational visibility: "an audit-material field changed on this record", without naming the field)

```python
# DO — partition before emit
def partition_changed_fields(policy, model_name, data):
    unclassified = []
    classified_count = 0
    for name in data.keys():
        if policy.get_field(model_name, name) is None:
            unclassified.append(name)
        else:
            classified_count += 1
    return unclassified, classified_count

event.payload["fields_changed"] = unclassified_names
event.payload["classified_fields_changed_count"] = classified_count

# DO NOT — emit raw column names
event.payload["fields_changed"] = list(data.keys())  # leaks "email", "ssn", "salary"
```

**Scope note — kailash-py today**: `packages/kailash-dataflow/src/dataflow/core/events.py` does NOT emit `fields_changed`. The Python event payload is `{model, operation, record_id}` only. The partition helper is a forward-compatible rule — anyone adding `fields_changed` in a future revision MUST land this helper in the same PR.

**Why:** Classified column names are themselves schema-level sensitive information. `observability.md` Rule 8 already mandates that schema-revealing field names stay at DEBUG / hashed in logs; event payloads reach a strictly wider audience. The partition form preserves operational visibility (the subscriber knows an audit-material change happened) without exposing which columns are classified.

### 4. Tests MUST Exercise The End-To-End Event Surface

A helper-level unit test is necessary but insufficient. Every event-emitting primitive (`create` / `update` / `delete` / `upsert` / any future mutation-event entry point) MUST have a Tier 2 integration test that:

1. Subscribes a handler to the DataFlow event bus
2. Triggers the mutation with a classified PK value (real PostgreSQL, not a mock)
3. Asserts the captured event payload contains `"sha256:"`-prefixed `record_id`
4. Asserts the raw value does NOT appear anywhere in `repr(payload)`

```python
# DO — full end-to-end exercise
received = []
db.on_model_change("Account", lambda evt: received.append(evt))
await db.express.create("Account", {"id": "alice@tenant.example", ...})
assert received[0].payload["record_id"].startswith("sha256:")
assert "alice@tenant.example" not in repr(received[0].payload)

# DO NOT — unit test only
def test_helper_hashes():
    assert format_record_id_for_event(...) == "sha256:XXX"
    # ↑ proves the helper hashes, NOT that the emitter calls the helper
```

**Why:** The orphan-detection pattern applies to event payloads exactly as to mutation returns: a helper that exists but isn't called from the emitter is the same failure mode. Only an end-to-end test against the real bus proves the emitter invokes the helper.

## MUST NOT

- Emit raw classified-PK values in any event payload field

**Why:** Event payloads have no audience gate — every subscriber, tracing span, and observability vendor sees them. A raw classified PK in an event is a permanent leak with a wider blast radius than any log entry.

- Place the hash/filter at individual mutation call sites rather than the emitter

**Why:** Every call site is one drift away from skipping the filter. Single-point enforcement at the emitter is the only structural defense against drift.

- Use a different hash shape / prefix length than the cross-SDK contract

**Why:** Cross-SDK forensic correlation relies on stable fingerprints. Diverging shape breaks the "same raw value → same fingerprint across Python + Rust" promise.

- Level-gate event payloads (`if debug:` etc.)

**Why:** `DomainEvent` has no level. Every subscriber sees every event. Filter / hash is the only option.

## Relationship To Other Rules

- `rules/dataflow-classification.md` — read/list/mutation-return redaction. Companion rule; same discipline applied to the return-value surface.
- `rules/observability.md` Rule 8 — log-surface schema-name hygiene. Stricter event-surface rule supersedes.
- `rules/tenant-isolation.md` — tenant_id dimension on every cache key, audit row, metric label. Same "apply on every return/emit path" discipline.
- `rules/orphan-detection.md` + `rules/facade-manager-detection.md` — Tier 2 tests prove the hot path calls the helper. Extended here to "prove the emitter invokes the filter".

## Origin

Issue #491 (2026-04-17) — DataFlowExpress `_emit_write_event` shipped raw `record_id` to subscribers. Cross-SDK from kailash-rs v3.17.1 BP-048 commit `2e9dbf94` (Rust `format_record_id_for_event` helper). Fix: single-point filter at `DataFlowEventMixin._emit_write_event` + helper at `dataflow.classification.event_payload`. Verified by 10/10 Tier 2 integration tests at `packages/kailash-dataflow/tests/integration/security/test_event_payload_classification.py`.

<!-- /slot:neutral-body -->
