# W5-B Findings — dataflow

**Specs audited:** 5
**§ subsections enumerated:** TBD
**Findings:** TBD
**Audit completed:** 2026-04-26 (in progress)

---

## Spec 1: dataflow-core.md

### F-B-01 — dataflow-core.md § 22 — Version mismatch (spec claims 2.0.7, actual 2.3.1)

**Severity:** LOW
**Spec claim:** `__version__ == "2.0.7"`; both `pyproject.toml` and `__init__.py` must report this version.
**Actual state:** `packages/kailash-dataflow/src/dataflow/__init__.py:110` declares `__version__ = "2.3.1"`. Package version drift; spec stale.
**Remediation hint:** Update spec § 22 to reflect actual shipped version (or vice versa). Per `specs-authority.md` § 5, code is the contract — spec MUST be re-aligned.

### F-B-02 — dataflow-core.md § 1.4 — Spec claims `db.audit_query()` triggers connection but method is absent

**Severity:** MED
**Spec claim:** § 1.4 table lists `db.audit_query()` as an operation that triggers `_ensure_connected()`.
**Actual state:** `grep -rn "def audit_query" packages/kailash-dataflow/src/` returns zero matches. The method does not exist on the DataFlow class.
**Remediation hint:** Either implement `db.audit_query()` or delete the row from § 1.4. Per `zero-tolerance.md` Rule 6, half-implemented APIs are BLOCKED — if the spec advertises it, code MUST provide it.

### F-B-03 — dataflow-core.md § 1.4 — Spec claims `db.execute_lightweight_query()` triggers connection but method is absent

**Severity:** MED
**Spec claim:** § 1.4 table lists `db.execute_lightweight_query()` as an operation triggering `_ensure_connected()`.
**Actual state:** `grep -rn "def execute_lightweight_query" packages/kailash-dataflow/src/` returns zero matches.
**Remediation hint:** Either implement or remove from spec. Same as F-B-02.

### F-B-04 — dataflow-core.md § 1.2 Constructor — `cache_enabled` and `cache_ttl` types diverge from spec

**Severity:** LOW
**Spec claim:** Constructor signature lists `cache_enabled: bool = True` and `cache_ttl: int = 3600` as defaults.
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/engine.py:120-123` shows `cache_enabled: Optional[bool] = None` and `cache_ttl: Optional[int] = None` (None means honor config; True/False overrides). Spec defaults misrepresent actual semantics — actual code uses tri-state Optional + comment "None = honour config".
**Remediation hint:** Update § 1.2 signature to `cache_enabled: Optional[bool] = None` and `cache_ttl: Optional[int] = None`, and add note: "None defers to config; explicit True/False overrides."

### F-B-05 — dataflow-core.md § 21.2 — TenantTrustManager has no facade and no production hot-path call site

**Severity:** HIGH
**Spec claim:** § 21.2 explicitly notes: "TenantTrustManager (`dataflow.trust.multi_tenant.TenantTrustManager`): Available as a standalone class for cross-tenant delegation verification. NOT attached as a `db.*` facade — no framework hot-path invokes it today (orphan-detection MUST 3). Consumers who need cross-tenant verification instantiate it directly; when a production call site lands in express.py, the facade will be wired in the same PR."
**Actual state:** Spec self-documents the orphan and excuses it. Per `rules/orphan-detection.md` MUST Rule 3 (Removed = Deleted, Not Deprecated), an orphan kept "for future wiring" is the exact failure mode the rule blocks. Spec acknowledgement does NOT exempt it.
**Remediation hint:** Either delete `TenantTrustManager` from public surface OR wire a production call site in express.py in the SAME PR — orphan-detection MUST 3 forbids deferred wiring as a structural defense. The "spec excuses the orphan" disposition is a Rule 3 violation in disguise.

### F-B-06 — dataflow-core.md § 21.2 — _trust_executor and _audit_store stored but no public facade property

**Severity:** MED
**Spec claim:** § 21.2 names `db._trust_executor` and `db._audit_store` as the trust components users access.
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/engine.py:625-651` stores `self._trust_executor` and `self._audit_store` as private attrs. No `@property` accessor exposes them as `db.trust_executor` / `db.audit_store` (verified `grep -n "def trust_executor\|def audit_store" engine.py` returns zero). Spec references private attrs — accessing `db._trust_executor` violates the no-private-API contract for downstream users.
**Remediation hint:** Either (a) add `@property` accessors `trust_executor` / `audit_store` (matching `facade-manager-detection.md` MUST Rule 1) AND wire production call sites + Tier 2 wiring tests, OR (b) rename references in spec § 21.2 to private form `_trust_executor` and document that consumers MUST NOT read them. Option (a) is safer per orphan-detection MUST 1.

---
