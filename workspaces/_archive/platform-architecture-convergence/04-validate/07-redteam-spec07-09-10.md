# Red Team Audit: SPEC-07 / SPEC-09 / SPEC-10

**Date**: 2026-04-08
**Auditor**: analyst (red team mode, second-look)
**Branch**: feat/platform-architecture-convergence
**Working dir**: /Users/esperie/repos/loom/kailash-py
**Specs audited**:

- SPEC-07 (ConstraintEnvelope Unification)
- SPEC-09 (Cross-SDK Parity)
- SPEC-10 (Multi-Agent Patterns Migration)

## Executive Summary

The previous convergence report (`04-validate/03-final-convergence.md`)
declared **zero CRITICAL/HIGH findings**. This audit corroborates an
earlier draft on this same path (which itself contradicted the
convergence verdict) and extends it with additional CRITICAL findings.

The state on this branch is:

| Severity     | Count | Theme                                                                                                                                         |
| ------------ | ----- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **CRITICAL** | 6     | SPEC-10 not migrated, capability router uses substring matching, signing fields silently dropped, top-level alias still points to chain class |
| **HIGH**     | 9     | Posture enum semantically wrong, no schema_version, hollow JSON-RPC parity test, metadata field mutable, consumer migration incomplete        |
| **MEDIUM**   | 7     | Missing test vectors, missing security mitigations, hypothesis tests on wrong type, `kid` rotation missing                                    |
| **MINOR**    | 4     | Confused exports, issue template gaps, missing pattern exports                                                                                |

The canonical envelope file exists, the wrappers compose, the cross-SDK
fixtures directory was created. But the migration of consumers, the
deprecation of old types, the architectural redesign of the multi-agent
patterns, and the security postures spec'd in §9 / §10 are largely
absent. The "5958 tests passing" headline number is meaningless because
SPEC-10 was not implemented and the SPEC-09 round-trip tests do not
exercise the production classes they claim to validate.

---

## CRITICAL Findings

### CRIT-01: SPEC-10 multi-agent pattern migration was not performed

**Spec**: SPEC-10 §3 (Migration Strategy), §6 (Migration Order), §7 (Test Plan)

**Finding**: SPEC-10 mandates that the 7 patterns be refactored to use
SPEC-03 wrapper-based primitives (`SupervisorAgent` and `WorkerAgent` as
wrappers, `LLMBased` routing). None of this happened.

Evidence:

- `packages/kaizen-agents/src/kaizen_agents/patterns/patterns/supervisor_worker.py`
  lines 113, 462, 575: `class SupervisorAgent(BaseAgent)`,
  `class WorkerAgent(BaseAgent)`, `class CoordinatorAgent(BaseAgent)` are
  still **BaseAgent inheritance**, not SPEC-03 wrappers.
- `SupervisorAgent.__init__(config, shared_memory, agent_id)` —
  signature is **NOT** `SupervisorAgent(workers, routing=LLMBased(...))`
  per SPEC-10 §3 Phase 1.
- No `LLMBased` routing class exists anywhere in the package
  (`grep -r "class LLMBased\|LLMBased(" packages/kaizen-agents` → empty).
- No `worker_agent.py` or `supervisor_agent.py` module exists at the
  package root (per SPEC-10 §6 step 1).
- All 11 pattern-specific subclasses still exist with **zero
  deprecation warnings** (`grep "DeprecationWarning\|warnings.warn"
packages/kaizen-agents/src/kaizen_agents/patterns/patterns/` → empty):
  - `consensus.py`: `ProposerAgent`, `VoterAgent`, `AggregatorAgent`
  - `sequential.py`: `PipelineStageAgent`
  - `handoff.py`: `HandoffAgent`
  - `debate.py`: `ProponentAgent`, `OpponentAgent`, `JudgeAgent`
  - `supervisor_worker.py`: `SupervisorAgent`, `WorkerAgent`, `CoordinatorAgent`
- The "200 pattern tests pass" claim is meaningless: the tests pass
  because the legacy classes are unchanged.

**Impact**: Users cannot pass wrapped agents (`MonitoredAgent(BaseAgent(...))`)
into a `SupervisorAgent`, because the constructor takes a config, not a
list of agents. SPEC-10 §5 ("New Capability: Wrapped Agents in Patterns")
is impossible in the current shape.

**Required**: Implement SPEC-10 §3 Phases 1–7 in full. Until then SPEC-10
should be marked DRAFT, not converged.

---

### CRIT-02: Capability router uses substring matching (violates `agent-reasoning.md` Rule 5)

**Spec**: SPEC-10 §3 ("routing is LLM-based over capability cards, never
keyword match"); `rules/agent-reasoning.md` MUST Rule 5; ANTI-PATTERN 1
(keyword routing); ANTI-PATTERN 5 (embedding similarity with thresholds).

**Finding**: `SupervisorAgent.select_worker_for_task`
(`patterns/patterns/supervisor_worker.py:153`) calls
`Capability.matches_requirement` to score workers. That function lives
at `packages/kailash-kaizen/src/kaizen/nodes/ai/a2a.py:95-115` and is
pure substring/keyword matching:

```python
def matches_requirement(self, requirement: str) -> float:
    requirement_lower = requirement.lower()
    if self.name.lower() in requirement_lower:        # substring match
        return 0.9
    if self.domain.lower() in requirement_lower:      # substring match
        return 0.7
    keyword_matches = sum(
        1 for keyword in self.keywords if keyword.lower() in requirement_lower
    )                                                  # keyword tally
    if keyword_matches > 0:
        return min(0.6 + (keyword_matches * 0.1), 0.8)
```

When A2A scoring fails or returns no match, the supervisor falls back
to `available_workers[0]` (round-robin), which is also forbidden by
SPEC-10 §3.

This is exactly ANTI-PATTERN 1 ("keyword routing") and ANTI-PATTERN 5
("embedding similarity with hardcoded thresholds for routing"). There
is **no LLM in the routing path**.

The earlier draft of this report also flagged a separate
`_simple_text_similarity` Jaccard implementation in `patterns/runtime.py`
as a parallel violation; both are R2-001 and both are still live.

**Impact**: Every routing decision in the existing supervisor pattern
violates the LLM-first rule. This is the most serious agent-reasoning
violation in the codebase given the visibility of the SupervisorWorker
pattern.

**Required**: Replace `select_worker_for_task` with an LLM-based router
(an internal `BaseAgent` reasoning over capability card JSON), per
SPEC-10 §3 / `LLMBased`. Delete the substring-matching code path or move
it out of the agent decision surface.

---

### CRIT-03: Signing fields silently dropped on `from_dict()` round-trip

**Spec**: SPEC-07 §2 (`signed_by`, `signed_at`, `signature` are direct
fields on `ConstraintEnvelope`); §9.3 (signing key management); §9.5
(envelope as audit evidence — must produce a deterministic canonical
form that survives serialization).

**Finding**: `_KNOWN_FIELDS` at `src/kailash/trust/envelope.py:656-671`
includes `signed_by`, `signed_at`, `envelope_id`, `envelope_hash`, but
the `@dataclass` declaration at lines 674-694 has none of these as
fields. `from_dict()` (lines 939-988) only reads `financial`,
`operational`, `temporal`, `data_access`, `communication`,
`gradient_thresholds`, `posture_ceiling`, `metadata` and silently
ignores the rest.

A wire payload that arrives with a signature, gets parsed through
`from_dict()`, then re-serialized via `to_dict()` will:

1. Drop `signed_by`, `signed_at`, `signature` on the way in.
2. Compute a new `envelope_hash` on the way out.
3. Verify against itself trivially because no signature is present.

**Impact**: SPEC-07's signing story is non-functional for the wire
format. Cross-SDK signed envelopes cannot round-trip. Audit evidence
(§9.5) cannot be reconstructed because the canonical form lacks the
signing block.

**Required**: Add `signed_by: Optional[str]`, `signed_at: Optional[datetime]`,
`signature: Optional[str]`, and a `kid` field for key rotation (§9.3
mitigation 3) as actual dataclass fields. Wire them through
`from_dict`/`to_dict`/`to_canonical_json`. Add a regression test that
signs an envelope, round-trips it through dict, and re-verifies.

---

### CRIT-04: `kailash.trust.ConstraintEnvelope` still resolves to the OLD chain class

**Spec**: SPEC-09 §2.4 ("Constraint Envelope: `kailash.trust.ConstraintEnvelope`
(frozen dataclass)"); SPEC-07 §6 step 3 ("Replace `trust.chain.ConstraintEnvelope`
with deprecated alias").

**Finding**: `src/kailash/trust/__init__.py:58-77`:

```python
from kailash.trust.chain import (
    ...
    ConstraintEnvelope,   # ← OLD chain class
    ...
)
```

and lines 173-189 import the canonical envelope under a **different
name**:

```python
from kailash.trust.envelope import (
    ...
    ConstraintEnvelope as CanonicalConstraintEnvelope,
    ...
)
```

`__all__` exports BOTH `"ConstraintEnvelope"` and
`"CanonicalConstraintEnvelope"`. Net result:
`from kailash.trust import ConstraintEnvelope` returns the legacy chain
aggregate (with `agent_id`, `active_constraints: List[Constraint]`,
mutable, no `intersect()`, no `posture_ceiling`).

`scripts/convergence-verify.py:230-231` even acknowledges the deviation
in a comment:

> Note: Legacy types in chain.py, plane/models.py, pact/config.py are
> different abstractions preserved with converter functions per Phase 2b
> agent design.

This was a deliberate decision to NOT implement SPEC-07 §4 / §6 step 3.
The convergence verdict was achieved by changing the verification
script, not the code.

**Impact**: SPEC-09 §2.4 is silently broken. Any cross-SDK consumer
reading the spec and writing `from kailash.trust import ConstraintEnvelope`
will get an incompatible class. The Rust side that was specced to align
with the Python `kailash.trust.ConstraintEnvelope` is aligned with the
wrong class.

**Required**: Decide one of two paths and document the decision:

1. **Implement SPEC-07 as written**: convert
   `chain.ConstraintEnvelope`, `plane.models.ConstraintEnvelope`,
   `pact.config.ConstraintEnvelopeConfig` into deprecated aliases that
   delegate to the canonical type. Migrate consumers (CRIT-06).
2. **Amend SPEC-07 and SPEC-09**: explicitly state that the canonical
   type lives at `kailash.trust.envelope.ConstraintEnvelope` only, that
   the top-level `kailash.trust.ConstraintEnvelope` is the legacy chain
   aggregate, and update SPEC-09 §2.4 to reference the canonical path.

Either is acceptable. The current "do neither" state is not.

---

### CRIT-05: SPEC-09 cross-SDK round-trip tests are hollow

**Spec**: SPEC-09 §3.1 (round-trip test for `JsonRpcRequest`); §3.2
(round-trip test for `ConstraintEnvelope`); §6 (CIs run interop test
vectors).

**Finding**: `tests/unit/cross_sdk/test_jsonrpc_round_trip.py:24-37`:

```python
def test_jsonrpc_canonical_json_matches_fixture(load_vector, filename):
    vector = load_vector("jsonrpc", filename)
    input_obj = vector["input"]                       # plain dict
    expected = vector["expected_canonical_json"]
    actual = json.dumps(input_obj, sort_keys=True, separators=(",", ":"))
    assert actual == expected
```

This test never instantiates `kailash_mcp.protocol.JsonRpcRequest`,
never calls its serialization method, and never asserts that the
production class produces the expected bytes. It just round-trips a
Python dict through `json.dumps`. The test passes trivially regardless
of whether the production class even exists.

A grep for `JsonRpcRequest` in `tests/unit/cross_sdk/` returns zero
matches.

The companion test `test_envelope_round_trip.py` has the same problem:
it serializes a dict via `json.dumps`, not via
`ConstraintEnvelope.to_canonical_json()`. Worse, it imports the
canonical envelope by **filesystem path**:

```python
envelope_path = "/Users/esperie/repos/loom/kailash-py/src/kailash/trust/envelope.py"
spec = importlib.util.spec_from_file_location("kailash_trust_envelope", envelope_path)
```

This is a hardcoded absolute path; CI on any other host will fail.

**Impact**: SPEC-09 §3.1, §3.2, §3.3 all claim round-trip parity testing
that does not exist. The Rust side could be silently divergent and these
tests would still pass.

**Required**:

1. Replace dict-based serialization with calls to the production class
   under test (`JsonRpcRequest.to_canonical_json()`,
   `ConstraintEnvelope.to_canonical_json()`).
2. Remove the absolute filesystem path import.
3. Add `from_canonical_json` parsing in the test so that
   `parse(serialize(parse(fixture))) == parse(fixture)`.
4. Add a CI job that exercises these tests on a clean machine and fails
   on the absolute path issue (currently green only because the file
   exists on the developer's box).

---

### CRIT-06: Consumer migration to canonical envelope is largely undone

**Spec**: SPEC-07 §6 step 6 ("Update all consumers — GovernanceEngine,
PactEngine, TrustProject, L3GovernedAgent, PACTMiddleware").

**Finding**: A grep for old envelope imports in `src/kailash/trust/`
returns 30+ files still importing from `pact.config`, `plane.models`,
or `chain`. Selected:

| File                                              | Import                                                                |
| ------------------------------------------------- | --------------------------------------------------------------------- |
| `src/kailash/trust/pact/engine.py`                | `from kailash.trust.pact.config import (...)`                         |
| `src/kailash/trust/pact/envelope_adapter.py`      | `from kailash.trust.pact.config import ConstraintEnvelopeConfig`      |
| `src/kailash/trust/pact/envelopes.py`             | `from kailash.trust.pact.config import (...)` (`intersect_envelopes`) |
| `src/kailash/trust/pact/agent.py`                 | `from kailash.trust.pact.config import TrustPostureLevel`             |
| `src/kailash/trust/pact/stores/sqlite.py`         | `from kailash.trust.pact.config import ConstraintEnvelopeConfig`      |
| `src/kailash/trust/pact/stores/backup.py`         | `from kailash.trust.pact.config import (...)`                         |
| `src/kailash/trust/interop/biscuit.py`            | `from kailash.trust.chain import ... ConstraintEnvelope ...`          |
| `src/kailash/trust/plane/conformance/__init__.py` | `from kailash.trust.plane.models import ConstraintEnvelope`           |

Only `kaizen_agents/governed_agent.py` and `kaizen_agents/delegate/delegate.py`
import from the canonical `kailash.trust.envelope`.

**Impact**: Three parallel envelope worlds coexist. PACT engine, PACT
stores, biscuit interop, and plane conformance all run on the OLD
types. Code that bridges (e.g., `governed_agent` taking a canonical
envelope but flowing through PACT engine that expects the Pydantic
config) will break in subtle ways at the seams. The "single source of
truth" goal of SPEC-07 §1 is unmet.

**Required**: Migrate every consumer in the table above (and any other
match) to import the canonical type. Where a real shape difference
exists (PACT's required-dimension Pydantic model vs the canonical
optional form), write an adapter at the boundary, NOT inside business
logic.

---

## HIGH Findings

### HIGH-01: `AgentPosture` enum has wrong members and wrong type

**Spec**: SPEC-07 §9.4 mitigation 1: "AgentPosture enum values MUST be
frozen: PSEUDO=1, TOOL=2, SUPERVISED=3, AUTONOMOUS=4, DELEGATING=5. A
regression test asserts these exact values."

**Reality** (`src/kailash/trust/envelope.py:549-572`):

```python
class AgentPosture(str, Enum):
    PSEUDO_AGENT = "pseudo_agent"
    SUPERVISED = "supervised"
    SHARED_PLANNING = "shared_planning"
    CONTINUOUS_INSIGHT = "continuous_insight"
    DELEGATED = "delegated"
```

Discrepancies:

1. **Type**: spec says IntEnum (numeric ordering), code says
   `(str, Enum)`.
2. **Members**: spec lists `PSEUDO, TOOL, SUPERVISED, AUTONOMOUS,
DELEGATING`; code has `PSEUDO_AGENT, SUPERVISED, SHARED_PLANNING,
CONTINUOUS_INSIGHT, DELEGATED`.
3. `TOOL` and `AUTONOMOUS` are missing entirely.
4. The implementation introduces `SHARED_PLANNING` and
   `CONTINUOUS_INSIGHT` which appear nowhere in SPEC-07.
5. There is no regression test asserting "exact values" —
   `tests/trust/unit/test_canonical_envelope.py:236` only checks
   ordering, not the values themselves.

`ConstraintEnvelope.posture_ceiling` is typed `str | None` (line 693)
and validated against `{p.value for p in AgentPosture}`, not
`AgentPosture | None`. SPEC-07 §2 specifies `Optional[AgentPosture]`.

**Impact**: SPEC-07 §9.4 (the R2-013 mitigation) is missing. The
cross-SDK contract for posture ceiling values (SPEC-09 §3.2) is
**inconsistent with the spec** — Rust implementations following SPEC-07
§9.4 verbatim will emit `"tool"` / `"autonomous"` and Python will
reject those as unknown values, and vice versa.

**Required**: Reconcile SPEC-07 §9.4 with the actual member set, in
writing, in the spec. Then either rename the enum members or amend the
spec. Add a regression test asserting the canonical member list and
values. Type `posture_ceiling` as `AgentPosture | None`.

---

### HIGH-02: `ConstraintEnvelope` has no `schema_version` field (SPEC-09 §8.3)

**Spec**: SPEC-09 §8.3 mitigation 1: "Every wire type has a
`schema_version: u32` field, verified at deserialization. Versions that
do not match raise explicitly (not silently degrade)."

**Finding**: Grep for `schema_version` in
`src/kailash/trust/envelope.py` returns zero matches. The fixture files
have a top-level `"schema_version": "1.0"` key but it is not part of
the envelope wire format — it is a fixture metadata field.

**Impact**: Wire format drift between Python and Rust cannot be
detected. The §8.3 attack ("send an old-reader payload to bypass new
constraints") is open.

**Required**: Add `schema_version: int = 1` to the canonical envelope
and reject mismatched versions in `from_dict()`. Document the bump
policy.

---

### HIGH-03: `ConstraintEnvelope.metadata` is a mutable `dict`

**Spec**: SPEC-07 §9.5 mitigation 1: "All `ConstraintEnvelope` fields
MUST be either primitive types or frozen nested dataclasses. No `dict`,
`list`, `set`, or other mutable types."

**Finding**: `src/kailash/trust/envelope.py:694`:

```python
metadata: dict[str, Any] = field(default_factory=dict)
```

The `__post_init__` "freeze" comment (lines 705-707) does
`object.__setattr__(self, "metadata", dict(self.metadata))` — copying a
mutable dict into another mutable dict. The result is still mutable:

```python
env = ConstraintEnvelope(metadata={"a": 1})
env.metadata["a"] = 999          # works, no error
env.metadata["b"] = "injected"   # works
```

**Impact**: SPEC-07 §9.5 ("envelope as audit evidence") is violated. An
audit log entry that records an envelope by reference can be
retroactively modified. The "frozen dataclass" promise is hollow on the
`metadata` field.

**Required**: Replace `dict[str, Any]` with `tuple[tuple[str, str], ...]`
or a frozen `MappingProxyType` wrapper. Update `to_dict`/`from_dict`
accordingly.

---

### HIGH-04: `from_yaml()` uses bare `open()` (symlink follow)

**Spec**: `rules/trust-plane-security.md` Rule 1: "No bare `open()` or
`Path.read_text()` for record files. Bare `open()` follows symlinks,
allowing an attacker to redirect trust-plane reads to arbitrary files."

**Finding**: `src/kailash/trust/envelope.py:1014-1023`:

```python
if is_file:
    try:
        with open(path_or_str) as f:
            data = yaml.safe_load(f)
```

Bare `open()` on a path-like input. If `path_or_str` is a symlink to
`/etc/shadow`, `open()` happily follows it. The trust plane has
`safe_open` / `safe_read_json` helpers using `O_NOFOLLOW`; this
function does not use them.

**Impact**: Envelope YAML loading is a confused-deputy gadget. A user
who can control filenames in the envelope load path (config-driven
governance, multi-tenant) can read arbitrary files via symlink.

**Required**: Use `kailash.trust._locking.safe_open` (or equivalent
`O_NOFOLLOW` open) instead of bare `open()`.

---

### HIGH-05: SPEC-10 §10.1 unbounded delegation depth — no `max_total_delegations`

**Spec**: SPEC-10 §10.1 mitigation 1: "`SupervisorAgent` MUST accept a
`max_total_delegations` parameter (default 20) in addition to
`max_delegation_depth`. Any delegation beyond the count cap raises
`DelegationCapExceeded`."

**Finding**: Grep for `max_total_delegations|DelegationCapExceeded` in
`packages/kaizen-agents/` returns zero matches. There is no delegation
count cap anywhere. The 100x100x100 attack (10,000 leaf executions) is
open. `OperationalConstraint` also lacks a `max_delegations` field.

**Required**: Add `max_delegations` to `OperationalConstraint`. Wire it
into the supervisor's delegation loop. Add the regression test from
SPEC-10 §10.1 mitigation 4.

---

### HIGH-06: SPEC-10 §10.2 capability card sanitizer missing (prompt injection)

**Spec**: SPEC-10 §10.2 mitigation 1: "Multi-agent patterns MUST
construct workers through a factory that runs a sanitizer on
`capabilities` strings before creating the `WorkerAgent`. Sanitizer
checks: no control characters, no 'IGNORE' / 'OVERRIDE' / 'SYSTEM:'
markers, no nested JSON, length cap (1000 chars)."

**Finding**: Grep for `sanitize.*capabilit|capability_card` returns
zero matches. There is no sanitizer.

**Required**: Implement the sanitizer per spec. Even with the keyword
router from CRIT-02, prompt injection through capability cards into
LLMs elsewhere in the chain is exploitable.

---

### HIGH-07: SPEC-10 §10.3 worker name uniqueness/regex not enforced

**Spec**: SPEC-10 §10.3 mitigations 1-2: "Worker names MUST be unique
within a `SupervisorAgent` — duplicates raise `DuplicateWorkerNameError`.
Worker names MUST match `^[a-z][a-z0-9_-]{2,63}$`."

**Finding**: Grep for `DuplicateWorkerNameError` returns zero matches.
The current `SupervisorAgent` doesn't take a workers list at
construction, so there's no place to enforce uniqueness.

**Required**: After CRIT-01 is implemented, enforce worker name regex
and uniqueness at `SupervisorAgent.__init__`.

---

### HIGH-08: SPEC-10 §10.4 handoff cycle detection missing

**Spec**: SPEC-10 §10.4 mitigations 1-2: "Handoff pattern MUST track
visited agents in a per-request set. A handoff target that is already
in the set raises `HandoffCycleError`."

**Finding**: Grep for `HandoffCycleError|cycle_detection|visited_agents`
returns zero matches. The `HandoffPattern` has tier-based escalation
but no cycle protection.

**Required**: Add visited-set tracking. Add tests with intentional
`A → B → A` loops.

---

### HIGH-09: SPEC-10 §10.5 per-worker budget partitioning missing

**Spec**: SPEC-10 §10.5 mitigation 1: "`SupervisorAgent` MUST wrap each
worker in its own `MonitoredAgent` with a per-worker budget (default:
`total_budget / num_workers`). A worker that exhausts its budget is
removed from the routing pool for the rest of the request."

**Finding**: Grep for `VoterBudgetExhausted|DebateEndedEarly` returns
zero matches. The patterns don't isolate budget per agent.

**Required**: Implement after CRIT-01.

---

## MEDIUM Findings

### MED-01: Test vector counts below spec

| Vector dir                                      | Spec count                      | Actual                     |
| ----------------------------------------------- | ------------------------------- | -------------------------- |
| `tests/fixtures/cross-sdk/jsonrpc/`             | 5 (SPEC-01 §7)                  | 4 (missing the 5th vector) |
| `tests/fixtures/cross-sdk/envelope/`            | ≥2 + signing/intersection cases | 2 (minimal + posture only) |
| `tests/fixtures/cross-sdk/agent-result/`        | ≥1 (§3.3)                       | **directory missing**      |
| `tests/fixtures/cross-sdk/streaming/`           | ≥1 (§2.5)                       | **directory missing**      |
| `tests/fixtures/cross-sdk/parser-differential/` | ≥1 (§8.2)                       | **directory missing**      |

`tests/fixtures/cross-sdk/README.md` lists all 5 directories but only
`jsonrpc/` and `envelope/` have content.

**Required**: Add the missing fixture directories with at least the
minimum vectors per spec. SPEC-09 §8.2 specifically requires a "shared
corpus of differential test payloads".

---

### MED-02: `tests/fixtures/envelope/` does not exist (SPEC-07 reference)

**Spec**: SPEC-07 §6 step 2 implies an envelope test fixtures directory.

**Finding**: No such directory. The closest is
`tests/trust/fixtures/wire_format/` which has one fixture
(`constraint-envelope.fixture.json`) and is not the location the spec
referenced.

**Required**: Decide canonical location, update spec to match, ensure
both Python and Rust load from the same place.

---

### MED-03: `json.loads(strict=True)` does not actually reject duplicate keys

**Spec**: SPEC-09 §8.2 mitigation 4: "Duplicate keys MUST be explicitly
rejected by both parsers."

**Finding**: `tests/unit/cross_sdk/conftest.py:35`:

```python
return json.loads(text, strict=True)
```

Python's `json.loads` `strict` parameter only controls **whitespace
within strings** (`strict=True` rejects unescaped control characters
inside string literals). It does NOT control duplicate-key handling.
Python's stdlib silently uses last-wins for duplicate keys regardless
of the `strict` flag.

The test `test_strict_parser_rejects_duplicate_keys` in
`test_jsonrpc_round_trip.py:40` is also misleading: it doesn't actually
test rejection of duplicate keys, it just loads a fixture and asserts
on `schema_version`. The test name promises a check that the body does
not perform.

**Required**: Implement actual duplicate-key rejection:

```python
def _no_dup_pairs(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate keys not allowed")
    return dict(pairs)
json.loads(text, object_pairs_hook=_no_dup_pairs)
```

Update the test to assert this actually raises.

---

### MED-04: Hypothesis property tests target the WRONG envelope type

**Spec**: SPEC-07 §9.1 mitigation 5: "A property-based test (hypothesis)
generates random dicts and verifies that `from_dict()` either returns
a valid envelope or raises — never silently accepts invalid data."

**Finding**: `tests/trust/pact/unit/test_envelope_properties.py:21-35`
imports from `kailash.trust.pact.config` and
`kailash.trust.pact.envelopes` — the OLD Pydantic types, not the
canonical dataclass. Grep `from hypothesis|@given` in
`tests/trust/unit/test_canonical_envelope.py` returns zero matches.

**Impact**: The property tests validate the wrong type. The canonical
envelope's `from_dict()` is not exercised by hypothesis.

**Required**: Add a hypothesis test module at
`tests/trust/unit/test_canonical_envelope_properties.py` targeting the
canonical type per SPEC-07 §9.1 mitigation 5.

---

### MED-05: SPEC-07 §9.2 mitigation 4 lint rule missing

**Spec**: SPEC-07 §9.2 mitigation 4: "Static analysis: add a lint rule
that flags any `ConstraintEnvelope(...)` construction outside
allowlisted root modules."

**Finding**: Grep for `ConstraintEnvelope.*construction|allowlisted` in
`scripts/` returns zero matches. No lint rule, no AST check. Any
module can construct a wide envelope and bypass the `intersect()`
discipline.

**Required**: Add a `scripts/lint-envelope-construction.py` AST check
or a ruff custom rule.

---

### MED-06: SPEC-07 §9.3 `kid` rotation missing

**Spec**: SPEC-07 §9.3 mitigation 3: "Key rotation uses a `kid` (key
identifier) embedded in the signed envelope. Verification tries the
current key first, then the previous key within a configurable window."

**Finding**: `sign_envelope` (line 1270) and `verify_envelope` (line 1291) take a single `SecretRef`. There is no `kid` in the wire format,
no multi-key verification, no rotation window.

**Required**: Add `kid` to the wire format, implement
"current+previous within window" verification.

---

### MED-07: SPEC-07 §9.3 mitigation 4 — `envelope_signing_required` not enforceable

**Spec**: SPEC-07 §9.3 mitigation 4: "Envelopes without signatures MUST
NOT be accepted in production contexts (enforced at PACT engine load
time via `envelope_signing_required=True`)."

**Finding**: Because signing fields are not actually on the dataclass
(see CRIT-03), there is no way for a downstream check to ask "is this
envelope signed?". `is_signed()` is in the spec §2 but not in the
implementation. The PACT engine has no `envelope_signing_required`
flag.

**Required**: Implement after CRIT-03 lands.

---

## MINOR Findings

### MIN-01: `__all__` in `kailash.trust` exposes both names confusingly

The export list contains both `"ConstraintEnvelope"` (old chain) and
`"CanonicalConstraintEnvelope"` (new). Users will pick whichever they
hit first in autocomplete and the wrong choice is silent.

**Required**: After CRIT-04 is decided, remove one or rename for
clarity.

---

### MIN-02: `cross-sdk-convergence.md` issue template lacks `schema_version` checklist

The template (`.github/ISSUE_TEMPLATE/cross-sdk-convergence.md`) has a
generic acceptance criteria list but no checkboxes for "schema_version
bumped in both SDKs", "test vector hashes recorded", or "CODEOWNERS
reviewers from both repos confirmed". SPEC-09 §8 mitigations won't be
enforced consistently.

**Required**: Add §8.1 / §8.3 / §8.5 checkboxes to the template body.

---

### MIN-03: SPEC-10 §4 — `BlackboardPattern` and `ParallelPattern` not exported

`packages/kaizen-agents/src/kaizen_agents/__init__.py:38-65` and
`patterns/patterns/__init__.py:59-93` export only 5 patterns:
`SupervisorWorkerPattern`, `ConsensusPattern`, `DebatePattern`,
`HandoffPattern`, `SequentialPipelinePattern`.

`parallel.py` and `blackboard.py` exist as files but are not in either
`__init__`. SPEC-10 §4 implies all 7 are exportable; SPEC-09 §2.2 also
implicitly requires both patterns to be top-level.

**Required**: Add to both `__all__` lists.

---

### MIN-04: `kaizen_agents.SupervisorAgent` / `WorkerAgent` / `MonitoredAgent` / `L3GovernedAgent` / `StreamingAgent` not exported at top level

**Spec**: SPEC-09 §2.2 maps `kaizen_agents.SupervisorAgent`,
`kaizen_agents.WorkerAgent`, `kaizen_agents.MonitoredAgent`,
`kaizen_agents.L3GovernedAgent`, `kaizen_agents.StreamingAgent`.

**Finding**: `kaizen_agents/__init__.py` does not import or export any
of these. Users following SPEC-09 §2.2 verbatim will get
`ImportError`.

**Required**: Add to `__init__.py`. (Note: `SupervisorAgent` /
`WorkerAgent` only become useful exports after CRIT-01.)

---

## Cross-Reference Audit

Documents that conflict with the audit findings:

- `workspaces/platform-architecture-convergence/04-validate/03-final-convergence.md`
  declares "0 CRITICAL, 0 HIGH". The 6 CRITICAL and 9 HIGH findings
  above contradict that judgment. Either the spec is wrong about what
  is required (and should be amended), or the convergence verdict is
  wrong.
- `scripts/convergence-verify.py:230-231` documents the deliberate
  decision to NOT implement SPEC-07 §4. That decision needs to be
  reflected in the spec, not just in a comment.
- `docs/migration/v2-to-v3.md` references `L3GovernedAgent` and the
  canonical envelope as if they were the user-facing type. This is
  consistent for `L3GovernedAgent` (which exists at
  `packages/kaizen-agents/src/kaizen_agents/governed_agent.py`) but
  inconsistent with the `kailash.trust.ConstraintEnvelope` import path
  that resolves to the legacy chain class.
- An earlier draft of this red team file (preserved in git history)
  also flagged `_simple_text_similarity` Jaccard routing in
  `packages/kaizen-agents/src/kaizen_agents/patterns/runtime.py:545-619`
  as a parallel violation of `agent-reasoning.md` Rule 5. That earlier
  finding is corroborated by this audit's CRIT-02 (substring matching
  in `Capability.matches_requirement`). Both code paths are still live.

---

## Implementation Roadmap

Phase A (architecture decisions, 1 session — human gate):

- Decide CRIT-04 path: implement deprecated aliases vs amend specs.
- Decide HIGH-01 posture enum: rename members to spec or amend spec.
- Decide MED-02 fixture location.

Phase B (canonical envelope hardening, 1-2 sessions, parallel agents):

- CRIT-03: add signing fields, wire through serialization, add tests.
- HIGH-02: add `schema_version`.
- HIGH-03: replace `metadata: dict` with frozen mapping.
- HIGH-04: use `safe_open` in `from_yaml`.
- MED-04: hypothesis tests on canonical type.
- MED-05: AST lint for envelope construction.
- MED-06 / MED-07: `kid` rotation and `envelope_signing_required`.

Phase C (consumer migration, 2 sessions):

- CRIT-06: migrate every PACT, plane, biscuit, conformance consumer to
  the canonical envelope. One module per agent.

Phase D (cross-SDK test rigor, 1 session):

- CRIT-05: rewrite hollow round-trip tests against the production
  classes. Remove absolute path imports.
- MED-01: add the 3 missing fixture directories.
- MED-03: implement actual duplicate-key rejection.

Phase E (multi-agent SPEC-10 implementation, 3-4 sessions):

- CRIT-01: refactor SupervisorWorker to wrapper-based design with
  `LLMBased` routing.
- CRIT-02: replace keyword-based capability matching with LLM router.
  Delete or move out the `Capability.matches_requirement` and
  `_simple_text_similarity` code paths.
- HIGH-05 through HIGH-09: security mitigations §10.1-§10.5.
- Simplify Sequential/Parallel/Debate/Consensus/Handoff/Blackboard
  per SPEC-10 §3 Phase 2.
- Deprecate the 11 pattern subclasses with `DeprecationWarning`.
- Add MIN-03 / MIN-04 exports.

Phase F (documentation, 0.5 session):

- Update `04-validate/03-final-convergence.md` with the corrected
  verdict.
- Issue template improvements (MIN-02).

Human gate after Phase A: which CRIT-04 / HIGH-01 path?

---

## Success Criteria

- [ ] `from kailash.trust import ConstraintEnvelope` returns the
      canonical type (or specs are amended and SPEC-09 §2.4 reflects
      the new path).
- [ ] `ConstraintEnvelope.from_dict(env.to_dict())` preserves signing
      fields when present.
- [ ] `AgentPosture` member list matches SPEC-07 §9.4 (or spec
      amended); regression test asserts exact values.
- [ ] `tests/unit/cross_sdk/test_jsonrpc_round_trip.py` actually
      instantiates `JsonRpcRequest` and asserts `to_canonical_json`
      output equals fixture.
- [ ] `tests/unit/cross_sdk/test_envelope_round_trip.py` actually
      instantiates `ConstraintEnvelope` and asserts `to_canonical_json`
      output equals fixture; no absolute filesystem paths.
- [ ] `tests/fixtures/cross-sdk/agent-result/`, `streaming/`,
      `parser-differential/` directories exist with at least 1 vector
      each.
- [ ] `SupervisorAgent(workers, routing=LLMBased(config=...))` works
      as documented in SPEC-10 §3 Phase 1; no
      `Capability.matches_requirement` or `_simple_text_similarity` in
      the routing path.
- [ ] All 11 pattern subclasses emit `DeprecationWarning` on
      construction.
- [ ] `MonitoredAgent(BaseAgent(...))` can be passed transparently as
      a worker into `SupervisorAgent` and budget is tracked per
      worker.
- [ ] Grep `from kailash.trust.pact.config import` in
      `src/kailash/trust/` returns only the legitimate pact-internal
      types; no `ConstraintEnvelopeConfig` consumers outside the pact
      package.
- [ ] `convergence-verify.py` checks that ALL of the above are true
      and the next round produces 0 CRITICAL and 0 HIGH for real.

---

## Files Referenced (absolute paths)

Spec sources:

- /Users/esperie/repos/loom/kailash-py/workspaces/platform-architecture-convergence/01-analysis/03-specs/07-spec-constraint-envelope-unification.md
- /Users/esperie/repos/loom/kailash-py/workspaces/platform-architecture-convergence/01-analysis/03-specs/09-spec-cross-sdk-parity.md
- /Users/esperie/repos/loom/kailash-py/workspaces/platform-architecture-convergence/01-analysis/03-specs/10-spec-multi-agent-patterns.md

Implementation:

- /Users/esperie/repos/loom/kailash-py/src/kailash/trust/envelope.py (canonical type — has the bugs in CRIT-03, HIGH-01, HIGH-02, HIGH-03, HIGH-04)
- /Users/esperie/repos/loom/kailash-py/src/kailash/trust/**init**.py (CRIT-04 confused exports)
- /Users/esperie/repos/loom/kailash-py/src/kailash/trust/chain.py (still native, line 443)
- /Users/esperie/repos/loom/kailash-py/src/kailash/trust/plane/models.py (still native, line 228)
- /Users/esperie/repos/loom/kailash-py/src/kailash/trust/pact/config.py (still native, line 239)
- /Users/esperie/repos/loom/kailash-py/scripts/convergence-verify.py (lines 230-231 acknowledge deviation)
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/governed_agent.py
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/wrapper_base.py
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/patterns/patterns/supervisor_worker.py (CRIT-01, CRIT-02)
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/patterns/patterns/handoff.py
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/patterns/patterns/debate.py
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/patterns/patterns/consensus.py
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/patterns/patterns/sequential.py
- /Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/**init**.py (MIN-03, MIN-04)
- /Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/nodes/ai/a2a.py (CRIT-02 keyword routing, lines 95-115)

Tests:

- /Users/esperie/repos/loom/kailash-py/tests/unit/cross_sdk/test_jsonrpc_round_trip.py (CRIT-05, MED-03)
- /Users/esperie/repos/loom/kailash-py/tests/unit/cross_sdk/test_envelope_round_trip.py (CRIT-05 absolute path)
- /Users/esperie/repos/loom/kailash-py/tests/unit/cross_sdk/conftest.py (MED-03)
- /Users/esperie/repos/loom/kailash-py/tests/trust/unit/test_canonical_envelope.py
- /Users/esperie/repos/loom/kailash-py/tests/trust/pact/unit/test_envelope_properties.py (MED-04 wrong type)

Fixtures:

- /Users/esperie/repos/loom/kailash-py/tests/fixtures/cross-sdk/jsonrpc/ (4 vectors, expected 5)
- /Users/esperie/repos/loom/kailash-py/tests/fixtures/cross-sdk/envelope/ (2 vectors)
- /Users/esperie/repos/loom/kailash-py/tests/fixtures/cross-sdk/README.md (lists missing dirs)

Governance:

- /Users/esperie/repos/loom/kailash-py/.github/CODEOWNERS (good — covers cross-sdk fixtures and envelope.py)
- /Users/esperie/repos/loom/kailash-py/.github/ISSUE_TEMPLATE/cross-sdk-convergence.md (MIN-02)
