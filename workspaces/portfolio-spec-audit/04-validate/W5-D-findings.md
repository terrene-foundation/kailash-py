# W5-D Findings — kaizen

**Specs audited:** 13
**§ subsections enumerated:** TBD
**Findings:** CRIT=0 HIGH=0 MED=0 LOW=0
**Audit completed:** 2026-04-26

---

## F-D-01 — kaizen-core § header — Spec version stale (2.7.3 vs actual 2.13.1)

**Severity:** LOW
**Spec claim:** "Version: 2.7.3" (line 3 of `specs/kaizen-core.md`)
**Actual state:** `packages/kailash-kaizen/pyproject.toml:version = "2.13.1"` — six minor versions behind.
**Remediation hint:** Bump spec header to current package version; add note that spec covers 2.13.x line.

## F-D-02 — kaizen-core § 6.1 — CoreAgent default config hardcodes "gpt-3.5-turbo"

**Severity:** HIGH
**Spec claim:** "Default config: `model="gpt-3.5-turbo"`, `temperature=0.7`, `max_tokens=1000`, `timeout=30`."
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/agents.py:104-109` — `defaults = {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 1000, "timeout": 30}`. Spec MATCHES code, but BOTH violate `rules/env-models.md` "NEVER Hardcode Model Names" — `model="gpt-3.5-turbo"` is BLOCKED in production code paths.
**Remediation hint:** Resolve default model via `os.environ.get("DEFAULT_LLM_MODEL")`; raise if unset. Update spec to reflect env-driven defaults.

## F-D-03 — kaizen-core § 4.1 — Trust posture field present but no production wiring claim verified at this layer

**Severity:** MED
**Spec claim:** "`posture: Optional[AgentPosture]` — Trust posture (immutable after construction)"
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/config.py:109` declares `posture`; `__setattr__` guard at lines 115-126 enforces immutability. Coercion present at lines 138-152. Spec assertion verified at field-declaration layer only — this finding is a placeholder for cross-spec correlation: kaizen-agents-governance.md §X.Y must wire posture into PACT clearance check on every agent step (verified separately).
**Remediation hint:** Cross-reference posture wiring assertions in `kaizen-agents-governance.md` audit (governance section).

## F-D-04 — kaizen-core § 3.4 — Spec claims 7 deprecated extension points, but checkpoint_manager added to constructor (8 ctor args beyond config/sig/strat)

**Severity:** MED
**Spec claim:** "These are deprecated in v2.5.0 -- composition wrappers (StreamingAgent, MonitoredAgent, GovernedAgent) are preferred for new code." — table lists 7 extension methods. Constructor signature in spec § 3.2 shows 9 params (config, signature, strategy, memory, shared_memory, agent_id, control_protocol, mcp_servers, hook_manager).
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/base_agent.py:60-72` — constructor adds `checkpoint_manager: Optional[Any] = None` (10th param), undocumented in spec.
**Remediation hint:** Add `checkpoint_manager` to spec § 3.2 with description (persists intermediate agent state for strategies/hooks).

## F-D-05 — kaizen-core § 28.7 — MCP/structured output mutual exclusion implemented but spec doesn't note logging path

**Severity:** LOW
**Spec claim:** "MCP/structured output mutual exclusion: When `has_structured_output` is True, MCP auto-discovery is suppressed."
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/base_agent.py:127-134` — verified, suppresses with logger.debug. Behavior matches spec; no defect.
**Remediation hint:** No action; assertion holds. Listed for completeness.

## F-D-06 — kaizen-signatures § 2.8 — `MultiModalSignature` defined in two locations

**Severity:** MED
**Spec claim:** "`MultiModalSignature`: Support for image + audio + text inputs." (single class)
**Actual state:** `packages/kailash-kaizen/src/kaizen/signatures/enterprise.py:277` AND `packages/kailash-kaizen/src/kaizen/signatures/multi_modal.py:602` — TWO classes both named `MultiModalSignature`. Whichever is exported via `signatures/__init__.py` wins; consumers depending on the other shape see silent divergence.
**Remediation hint:** Consolidate to one definition; if both have unique APIs, rename one (e.g., `EnterpriseMultiModalSignature`). Cross-reference with `kaizen-providers.md` § multi-modal exports.

## F-D-07 — kaizen-signatures § 2.x — Undocumented `SignatureOptimizer` class present

**Severity:** LOW
**Spec claim:** Spec § 2.4-2.7 enumerate Parser, Compiler, Validator, Template — no `SignatureOptimizer`.
**Actual state:** `packages/kailash-kaizen/src/kaizen/signatures/core.py:1824` — `class SignatureOptimizer:` exists but absent from spec.
**Remediation hint:** Document `SignatureOptimizer` in spec or mark as private (`_SignatureOptimizer`). If experimental, add `(Awaiting ISS-NN)` marker.

## F-D-08 — kaizen-signatures § 2.3 — Spec lists `signature_type` enum values but doesn't pin "enterprise" semantics

**Severity:** LOW
**Spec claim:** "`signature_type: str = "basic"` — basic, multi_io, complex, enterprise, multi_modal"
**Actual state:** Verified `Signature.__init__` accepts `signature_type`. Enum values not validated at constructor — any string accepted. Spec describes 5 valid values; code does not enforce.
**Remediation hint:** Add typed validation in `__post_init__` (raise on invalid) OR convert to Literal type hint. Update spec to clarify enforcement.

## F-D-09 — kaizen-signatures § 18.1 — `create_structured_output_config` exists but signature deviation

**Severity:** LOW
**Spec claim:** "`create_structured_output_config(signature=my_signature, strict=True)` → returns dict suitable for `response_format`."
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/structured_output.py:292` — verified function exists. Spec assertion holds at signature level. No defect; listed for completeness.
**Remediation hint:** No action.
