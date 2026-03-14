# EATP Specification Addendum v0.1

Cross-SDK specification for features implemented in the Python SDK v0.1 gap-closure effort. The Rust SDK implements equivalent functionality via trait objects and enums.

---

## 1. Hook Specification

### Hook Types

Four trust-native lifecycle events. Orchestration events (tool use, subagent spawn) belong in downstream frameworks (e.g., kailash-kaizen), not in the trust protocol.

| Hook Type           | When                       | Rationale                     |
| ------------------- | -------------------------- | ----------------------------- |
| `PRE_DELEGATION`    | Before delegation creation | Intercept/deny delegations    |
| `POST_DELEGATION`   | After delegation creation  | Audit, notify                 |
| `PRE_VERIFICATION`  | Before verification        | Rate limit, context injection |
| `POST_VERIFICATION` | After verification         | Override verdict, audit       |

Omitted: ESTABLISH (one-time bootstrap, no decision to intercept), AUDIT (read-only, interception would compromise integrity).

### Hook Result

```
HookResult {
    allow: bool,              // false = abort chain (fail-closed)
    reason: Optional<string>, // required when allow=false
    modified_context: Optional<Dict<string, any>>, // merged into metadata for subsequent hooks
}
```

### Semantics

- **Abort**: Any hook returning `allow=false` immediately aborts the remaining chain.
- **Priority**: Lower number = earlier execution. Default: 100.
- **Timeout**: Default 5 seconds. Timeout = `allow=false` (fail-closed).
- **Crash**: Exception in hook = `allow=false` (fail-closed).
- **Modified context**: Only applied when `allow=true`. Merged into metadata for subsequent hooks.

---

## 2. Proximity Defaults

Constraint proximity scanning detects when agents approach their constraint limits.

### Thresholds

| Preset       | Flag                | Hold                |
| ------------ | ------------------- | ------------------- |
| Default      | 0.80 (80% utilized) | 0.95 (95% utilized) |
| Conservative | 0.70                | 0.90                |

### Escalation Rule

Monotonic escalation only — verdicts never downgrade:

```
AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED
```

A FLAGGED agent can escalate to HELD but never return to AUTO_APPROVED through proximity alone.

### Scanner Design

`ProximityScanner` is standalone and opt-in. Backward compatible: `StrictEnforcer()` with no scanner behaves identically to pre-proximity behavior.

---

## 3. Behavioral Scoring Factors

### Factor Weights (sum to 100)

| Factor               | Weight | Computation                                                  |
| -------------------- | ------ | ------------------------------------------------------------ |
| `approval_rate`      | 30     | `approved_actions / total_actions`                           |
| `error_rate`         | 25     | `1.0 - (error_count / total_actions)`                        |
| `posture_stability`  | 20     | `1.0 - (transitions_per_hour * 168 / 10)`, clamped to [0, 1] |
| `time_at_posture`    | 15     | `min(1.0, hours / 720.0)` (30-day max)                       |
| `interaction_volume` | 10     | `min(1.0, log10(total_actions) / log10(10000))`              |

### Algorithm

```
score = sum(factor_raw * factor_weight for each factor)
score = max(0, min(100, round(score)))
grade = score_to_grade(score)  // A=90+, B=80+, C=70+, D=60+, F=<60
```

### Zero-Data Behavior

`total_actions == 0` produces score 0, grade F. Fail-safe: unknown agents are not trusted.

### Combined Scoring

Structural (chain-based) and behavioral (action-based) blend at configurable weights:

- Default: 60% structural, 40% behavioral
- Weights must sum to 1.0 (tolerance: 0.01)
- No behavioral data: combined = structural (backward compatible)

---

## 4. SIEM Event Schema

### Common Fields

```
SIEMEvent {
    event_id: string,       // UUID v4
    timestamp: datetime,    // UTC ISO 8601
    agent_id: string,
    operation: string,      // ESTABLISH | DELEGATE | VERIFY | AUDIT
    result: string,         // SUCCESS | FAILURE | DENIED | FLAGGED
    severity: int,          // 0-10 (OCSF scale)
    authority_id: Optional<string>,
    metadata: Dict<string, any>,
}
```

### Operation-Specific Subclasses

- `EstablishEvent`: + `public_key`, `capabilities`
- `DelegateEvent`: + `delegatee_id`, `constraints`, `depth`
- `VerifyEvent`: + `action`, `verdict`, `violations`
- `AuditEvent`: + `action`, `resource`, `chain_hash`

### CEF Format

CEF:0|Terrene|EATP|0.1.0|{operation}|{operation} {result}|{severity}|{extensions}

Escaping: pipes (`|`) in header values escaped as `\|`, backslashes as `\\`, newlines as `\n` in extensions.

### OCSF Format

OCSF 1.1 JSON with `class_uid: 6003` (API Activity), severity mapping: 0-3=Informational, 4-6=Low, 7-8=Medium, 9=High, 10=Critical.

---

## 5. Observability Metrics

### Prometheus Metrics

```
eatp_trust_score{agent_id="..."} 85
eatp_verification_total{result="approved"} 42
eatp_posture_current{agent_id="...",posture="shared_planning"} 1
eatp_constraint_utilization{agent_id="...",dimension="api_calls"} 0.73
eatp_hook_duration_seconds{hook="rate_limiter",type="pre_verification"} 0.002
```

Zero external dependencies. Text format output for Prometheus scraping.

### OpenTelemetry

Optional adapter (`opentelemetry-api>=1.20`) wrapping the same metrics as OTel gauges/counters.

---

## 6. EATP Scope Boundary

### In EATP SDK

- Trust chain management (ESTABLISH, DELEGATE, VERIFY, AUDIT)
- Cryptographic operations (Ed25519, DualSignature with optional HMAC)
- Constraint evaluation and proximity scanning
- Trust scoring (structural + behavioral)
- Enforcement (StrictEnforcer, ShadowEnforcer, decorators)
- Hook system (4 trust-native events)
- Reasoning traces with redaction and content hashing
- RBAC (TrustRole with permission guards)
- Interop (JWT, W3C VC, DID, UCAN, SD-JWT, Biscuit)
- Export (SIEM, SOC 2 compliance, metrics)

### Out of EATP SDK (downstream)

- Circuit breaker: Pragmatically in Python SDK, canonically belongs in enforcement layer (D2)
- Orchestration hooks (tool use, subagent spawn): kailash-kaizen
- CARE posture vocabulary adapters: CARE Platform
- Agent behavioral data collection: caller responsibility
- Multi-agent coordination: kailash-kaizen

---

## 7. ReasoningTrace JSON Schema

### Required Fields

```json
{
  "decision": "string",
  "rationale": "string",
  "confidentiality": "string", // UNRESTRICTED | RESTRICTED | SECRET | TOP_SECRET
  "timestamp": "string" // ISO 8601 UTC
}
```

### Optional Fields

```json
{
  "alternatives_considered": ["string"],
  "evidence": [
    { "evidence_type": "string", "reference": "string", "summary": "string?" }
  ],
  "methodology": "string",
  "confidence": "float" // 0.0-1.0, null on redaction
}
```

### Content Hash

SHA-256 over canonical JSON of `(decision, rationale, confidentiality, timestamp)`. Used for tamper detection without exposing content.

### Redaction

All content fields replaced with `[REDACTED]` sentinel. `confidence` set to `null` to prevent information leakage. Original content hash preserved for verification that redaction happened to a specific trace.

### Signing Payload Compatibility

`to_signing_payload()` excludes `content_hash`, `is_redacted`, and redaction-related fields. Existing Ed25519 signatures remain valid after adding Phase 4 methods.
