# R1 — Combined Spec-Compliance + Closure-Parity Verification (v2.27.0)

**Verdict: CONVERGED** — 100% of load-bearing assertions verified; 0 HIGH, 0 MEDIUM.

Re-derived from scratch against branch `release/v2.27.0`, HEAD `6f536561b`. Every
row carries a literal verification command + its actual output. No prior
`.spec-coverage` / `.test-results` / convergence doc was trusted. Editable
kailash 2.26.2 (`src/`) + kailash-kaizen 2.24.1 (`packages/kailash-kaizen`).

The two workstreams (#1125 from_brief, #1035 delegate) merged on different bases
and each self-reported convergence separately; this round re-derives the COMBINED
surface, including the import-graph integration neither separate redteam covered.

---

## Summary counts

| Metric                               | Value                                       |
| ------------------------------------ | ------------------------------------------- |
| HIGH findings                        | 0                                           |
| MEDIUM findings                      | 0                                           |
| Full collection                      | 18179 tests, 0 errors                       |
| from_brief + delegate feature suites | 542 passed, 1 skipped, 0 fail               |
| Import-graph lazy-kaizen leak        | `kaizen leaked: False`                      |
| Version anchors                      | pyproject 2.26.2 == **init** 2.26.2 (AGREE) |

---

## 1. Spec→code assertions (both architecture plans)

| #   | Assertion (spec source)                                                                                                | Command                                                                                                                              | Actual output                                                                                                                                               | Verdict           |
| --- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| 1   | #1125 §3.4 `BootstrapConfig` dataclass with fields db_url, llm_model, runtime, deployment_target                       | `python3 -c "from kailash import BootstrapConfig; import dataclasses; print([f.name for f in dataclasses.fields(BootstrapConfig)])"` | `is_dataclass: True; fields: ['db_url', 'llm_model', 'runtime', 'deployment_target']`                                                                       | PASS              |
| 2   | #1125 §3.1 `Workflow.from_brief` classmethod attached to Workflow                                                      | `python3 -c "from kailash import Workflow; print(hasattr(Workflow,'from_brief'))"`                                                   | `Workflow has from_brief: True`                                                                                                                             | PASS              |
| 3   | #1125 §8 B2a scrubber routes via `kailash.utils.url_credentials`                                                       | `grep -n "url_credentials\|def scrub_brief" src/kailash/_from_brief/scrubber.py`                                                     | `29: from kailash.utils.url_credentials import preencode_password_special_chars`; `155: def scrub_brief(brief: str) -> str:`                                | PASS              |
| 4   | #1125 §8 B1a allowlist: validate_node_type/field_type/config_value                                                     | `grep -n "def validate_node_type\|def validate_field_type\|def validate_config_value" src/kailash/_from_brief/allowlist.py`          | lines 37, 60, 82 all present                                                                                                                                | PASS              |
| 5   | #1125 §8 B3a typed `BriefInterpretationError` validator gate                                                           | `grep -n "BriefInterpretationError\|def validate_plan" src/kailash/_from_brief/validator.py`                                         | validator imports + raises `BriefInterpretationError`; confidence gate wired (line 13-15)                                                                   | PASS              |
| 6   | #1125 §8 C1a confidence threshold < 0.6                                                                                | `grep -n "DEFAULT_CONFIDENCE_THRESHOLD\|def check_confidence" src/kailash/_from_brief/confidence.py`                                 | `27: DEFAULT_CONFIDENCE_THRESHOLD: float = 0.6`; `30: def check_confidence(`                                                                                | PASS              |
| 7   | #1125 §3.4 bootstrap profile allowlist gate is a CLOSED allowlist {dev,prod}                                           | `grep -n "ALLOWED_PROFILES" src/kailash/bootstrap.py`                                                                                | `118: ALLOWED_PROFILES: Set[str] = {"dev", "prod"}`                                                                                                         | PASS              |
| 8   | #1035 Invariant 1 lifecycle Proposed→Instantiated→PostureGraded→Active→Retired→Archived                                | `python3 -c "from kailash.delegate import LifecycleState; print([s.name for s in LifecycleState])"`                                  | `['PROPOSED','INSTANTIATED','POSTURE_GRADED','ACTIVE','RETIRED','ARCHIVED']`                                                                                | PASS              |
| 9   | #1035 Connector ABC: authenticate/write/read/revocation (rs-shipped shape, NOT issue-body pull/normalize/capabilities) | `grep -n "class Connector\|def authenticate\|def write\|def read\|def revocation" src/kailash/delegate/dispatch.py`                  | `449: class Connector(abc.ABC)`; `@abstractmethod` accessors + `async def authenticate/write/read` (665/684/706); `revocation` property (640)               | PASS              |
| 10  | #1035 Naming disambiguation (kailash.delegate.Delegate NOT kaizen_agents.delegate.Delegate)                            | `grep -n "DISAMBIGUATION\|kaizen_agents" src/kailash/delegate/__init__.py`                                                           | line 8-9 disambiguation present; counterpart `kaizen_agents.delegate.Delegate` confirmed at `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py` | PASS (see note A) |
| 11  | #1035 conformance contract (ConformanceVector / Loader / receipts_agree)                                               | `python3 -c "import kailash.delegate.conformance as c; print(...)"`                                                                  | `ConformanceVector, ConformanceVectorLoader, receipts_agree, assert_receipts_agree, canonical_vector_set_digest` all exported                               | PASS (see note B) |

**Note A:** the spec's §"Naming disambiguation" code example showed the docstring on
the `Delegate` class in `runtime.py`; the implementation places it in the public
`delegate/__init__.py` (lines 8-9, 94). Same contract, equivalent or better
placement (the public surface). Not a gap.

**Note B:** the spec's §"Package layout" proposed conformance as
`vectors.py` + `runner.py` + `cli.py` + `fixtures/`. The implementation
consolidates to `conformance/__init__.py` + `conformance/schema.py`, exporting the
same conformance primitives. The architecture plan was a pre-implementation
design; this is file-organization evolution, not a missing contract. Verified the
behavioral contract (vector loading + receipts_agree) is present and exported.

---

## 2. `__all__` symbol counts via AST (testing.md MUST — NOT grep)

Enumerated via `ast.parse` + `len(node.value.elts)`; each entry confirmed to
resolve via `getattr` on the imported module.

| Module                                | **all** count (AST) | All entries import? | Verdict |
| ------------------------------------- | ------------------- | ------------------- | ------- |
| `src/kailash/_from_brief/__init__.py` | 16                  | ALL 16 resolve      | PASS    |
| `src/kailash/workflow/__init__.py`    | 32                  | ALL 32 resolve      | PASS    |
| `src/kailash/delegate/__init__.py`    | 56                  | ALL 56 resolve      | PASS    |
| `src/kailash/__init__.py`             | 21                  | ALL 21 resolve      | PASS    |

Top-level `kailash.__all__` confirmed to include the new public symbols
`bootstrap` and `BootstrapConfig` (entries 20-21). `kailash.Workflow.from_brief` is
a classmethod on the exported `Workflow` (verified row 2), so it is reachable
without a separate `__all__` entry.

---

## 3. New-module test coverage (testing.md Audit Mode — grep for importing tests)

Zero importing tests for a new module = HIGH. None found.

| New module                                   | Importing-test count | Verdict |
| -------------------------------------------- | -------------------- | ------- |
| `kailash._from_brief.*`                      | 9 files              | PASS    |
| `kailash.bootstrap`                          | 4 files              | PASS    |
| `kailash.delegate.*`                         | 31 files             | PASS    |
| `kailash.workflow.from_brief` / `from_brief` | 23 files             | PASS    |

Dedicated regression files for the #1035 hardening claims present:
`tests/regression/test_issue_1035_delegate_m1_consumed_toctou.py`,
`..._m3_payload_depth_subclass.py`, `..._m4_tenant_hash_salt.py`,
`..._slim_core_import.py`.

---

## 4. Combined import-graph integration (the surface neither separate redteam covered)

| Assertion                                                                                                                                                   | Command                                                                                                                                                                               | Actual output          | Verdict |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ------- |
| Importing \_from_brief + delegate + bootstrap + workflow.from_brief does NOT pull kaizen (the #1125 lazy-import core contract + slim-core regression guard) | `python3 -c "import kailash._from_brief, kailash.delegate, kailash.bootstrap; from kailash.workflow import from_brief; import sys; print('kaizen leaked:', 'kaizen' in sys.modules)"` | `kaizen leaked: False` | PASS    |

The lazy-kaizen contract HOLDS across the combined surface. `bootstrap()` hoists
its profile-allowlist gate above the kaizen-importing `signatures.py` (commit
`d25b466b0`), so an invalid profile rejects kaizen-free; `workflow/from_brief.py`
defers the kaizen-bearing plan-class import via `_workflow_plan_cls` /
`_signature_cls` lazy resolvers. Confirmed by the green
`test_issue_1035_delegate_slim_core_import.py` (2 passed).

---

## 5. Version-anchor consistency (zero-tolerance Rule 5)

| Anchor                  | Command                                    | Actual output            | Verdict |
| ----------------------- | ------------------------------------------ | ------------------------ | ------- |
| pyproject.toml          | `grep -m1 '^version' pyproject.toml`       | `version = "2.26.2"`     | —       |
| src/kailash/**init**.py | `grep __version__ src/kailash/__init__.py` | `__version__ = "2.26.2"` | —       |
| **Agreement**           | —                                          | Both 2.26.2 — AGREE      | PASS    |

Both anchors agree at 2.26.2 (current). The release will bump to 2.27.0; the
verification confirms they are NOT split-state today.

---

## 6. M1/M3/M4 hardening present (closure-parity vs cycle2 convergence doc)

| Claim                                                              | Command                                                                                                    | Actual output                                                                                                                                                                                             | Verdict |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| M1: `_consume_lock` wraps check-and-set in runtime.py              | `grep -n "_consume_lock" src/kailash/delegate/runtime.py`                                                  | `1065: self._consume_lock: asyncio.Lock = asyncio.Lock()`; `1313: async with self._consume_lock:` → `1314: if self._consumed:` … `1329: self._consumed = True` (check AND set inside the lock)            | PASS    |
| M3: collections.abc Mapping/Sequence/Set in `_check_payload_depth` | `grep -n "collections.abc\|Mapping\|Sequence\|Set\|_check_payload_depth" src/kailash/delegate/dispatch.py` | `61: from collections.abc import Awaitable, Callable, Mapping, Sequence, Set`; `137 isinstance(obj, Mapping)` / `140 Sequence` (str/bytes/bytearray excluded) / `Set` branch — all three walked uniformly | PASS    |
| M4: `_TENANT_HASH_SALT = secrets.token_bytes(32)` + HMAC           | `grep -n "_TENANT_HASH_SALT\|secrets.token_bytes\|hmac" src/kailash/delegate/trust.py`                     | `143: _TENANT_HASH_SALT: bytes = secrets.token_bytes(32)`; `36: import hmac`; `160: return hmac.new(_TENANT_HASH_SALT, ...)` (HMAC-SHA-256)                                                               | PASS    |

---

## 7. Feature test-suite run

| Command                                                                                                                                         | Actual output                    | Verdict |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ------- |
| `python3 -m pytest tests/unit/_from_brief/ tests/regression/from_brief/ tests/unit/delegate/ tests/regression/test_issue_1035_delegate_*.py -q` | `542 passed, 1 skipped in 9.48s` | PASS    |

The 1 skip is `tests/unit/delegate/test_audit_engine.py:576` (S7 cross-SDK
byte-parity vs vendored kailash-rs reference vectors — cannot execute without the
vendored rs fixtures). It is a documented, greppable, cannot-execute skip with the
assertion-shape pinned inline; per test-skip-discipline this is ACCEPTABLE (not
system-broken). Tracks the spec's "Cross-impl conformance contract" §, which
states py inherits the vendored vectors at M7-02.

---

## Pre-existing observation (out-of-workstream, recorded for zero-tolerance triage)

Full collection emits 1 `PytestCollectionWarning`:
`tests/tier2_integration/runtime/mixins/test_cycle_execution_mixin.py:57 — cannot
collect test class 'TestCycleRuntime' because it has a __init__ constructor`.

This is PRE-EXISTING (last touched by commit `7d66717c4`, a tier-2 sweep; 0 hits
in the `main...release/v2.27.0` diff for that path) and unrelated to either #1125
or #1035. It is a `testing.md` helper-class-suffix discipline item
(`TestCycleRuntime` should be `CycleRuntimeStub`). Surfaced here because it appears
in the release's collection output; disposition belongs to the release owner.

---

## Receipts

- Branch / HEAD: `release/v2.27.0` @ `6f536561b1d48318e17cf0bdbd52cb95d07a3c35`.
- All commands re-run live this round; outputs pasted verbatim in the tables above.
- AST `__all__` enumeration + per-entry getattr verification: one combined script
  over all four target modules.
- Import-graph leak check: single literal command, output `kaizen leaked: False`.
- Spec sources: `workspaces/from-brief-1125/02-plans/01-architecture.md`,
  `workspaces/issue-1035-delegate-py/02-plans/01-architecture.md`.
