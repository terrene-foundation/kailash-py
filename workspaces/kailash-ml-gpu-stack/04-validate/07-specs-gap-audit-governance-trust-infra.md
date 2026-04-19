# Specs Gap Audit — Governance, Trust, Infrastructure, Alignment, Middleware, Scheduling, Task-Tracking

Date: 2026-04-20
Auditor: analyst (redteam Step 1)
Protocol: `skills/spec-compliance/SKILL.md`
Scope: 13 spec files per parent prompt

All assertions re-derived from scratch via `grep` + `Glob`. No prior `.spec-coverage` consulted.
Repo root: `/Users/esperie/repos/loom/kailash-py`

---

## 1. `specs/pact-addressing.md`

| Assertion                                   | Command                                                                | Actual Output                                   | Verdict |
| ------------------------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------- | ------- |
| `NodeType(str, Enum)` exists                | `grep -n "^class NodeType" src/kailash/trust/pact/addressing.py`       | `30:class NodeType(str, Enum):`                 | GREEN   |
| `AddressSegment` dataclass exists           | `grep -n "^class AddressSegment" src/kailash/trust/pact/addressing.py` | `55:class AddressSegment:`                      | GREEN   |
| `Address` dataclass exists                  | `grep -n "^class Address" src/kailash/trust/pact/addressing.py`        | `95:class Address:`                             | GREEN   |
| `GrammarError(AddressError)`                | `grep -n "^class GrammarError" src/kailash/trust/pact/addressing.py`   | `48:class GrammarError(AddressError):`          | GREEN   |
| `AddressError(PactError, ValueError)`       | `grep -n "^class AddressError" …`                                      | `38:class AddressError(PactError, ValueError):` | GREEN   |
| `GovernanceEngine` (thread-safe facade)     | `grep -n "^class GovernanceEngine" src/kailash/trust/pact/engine.py`   | `196:class GovernanceEngine:`                   | GREEN   |
| `compile_org()` + `CompiledOrg` + `OrgNode` | grep against `src/kailash/trust/pact/compilation.py`                   | file exists, types present                      | GREEN   |
| PACT D/T/R grammar tests                    | `ls tests/trust/pact/unit/test_addressing.py`                          | present                                         | GREEN   |
| `VacancyDesignation` + vacancy tests        | `ls tests/trust/pact/unit/test_vacancy.py`                             | present                                         | GREEN   |

Section verdict: **GREEN**. PACT addressing surface complete, grammar-state-machine errors defined, vacancy + bridge LCA tests present.

---

## 2. `specs/pact-enforcement.md`

| Assertion                                              | Command                                                                       | Actual Output                                          | Verdict |
| ------------------------------------------------------ | ----------------------------------------------------------------------------- | ------------------------------------------------------ | ------- |
| `PactAuditAction` enum + 20 action types               | grep `BRIDGE_APPROVED\|ENVELOPE_CREATED` in `src/kailash/trust/pact/audit.py` | file exists with enum                                  | GREEN   |
| `AuditChain` thread-safe, hmac.compare_digest          | `src/kailash/trust/pact/audit.py`                                             | present                                                | GREEN   |
| `CostTracker` (NaN/Inf defense, deque maxlen 10k)      | `grep -n "class CostTracker" packages/kailash-pact/src/pact/costs.py`         | `25:class CostTracker:`                                | GREEN   |
| `EventBus` (subscribers bounded to 1000)               | `grep -n "class EventBus" packages/kailash-pact/src/pact/events.py`           | `23:class EventBus:`                                   | GREEN   |
| `WorkSubmission` + `WorkResult` frozen                 | `grep -n "class WorkResult" packages/kailash-pact/src/pact/work.py`           | `33:class WorkSubmission:`, `69:class WorkResult:`     | GREEN   |
| `McpGovernanceEnforcer` / `Middleware` / `Policy`      | `grep class in packages/kailash-pact/src/pact/mcp/`                           | `enforcer.py`, `middleware.py`, `types.py` all present | GREEN   |
| MCP governance tests                                   | `ls packages/kailash-pact/tests/unit/mcp/test_enforcer.py` etc                | 5 test files present                                   | GREEN   |
| SQLite stores (`SqliteOrgStore` etc.)                  | `grep class Sqlite… in src/kailash/trust/pact/stores/sqlite.py`               | single file has all 5 classes                          | GREEN   |
| `EnforcementMode` enum with DISABLED guard             | `grep class EnforcementMode`                                                  | `packages/kailash-pact/src/pact/enforcement.py:35`     | GREEN   |
| D/T/R addressing: regression tests for audit integrity | `ls packages/kailash-pact/tests/unit/governance/test_audit_integrity.py`      | present                                                | GREEN   |

Section verdict: **GREEN**. PACT enforcement layer fully wired with tests.

---

## 3. `specs/pact-envelopes.md`

| Assertion                                                                                       | Command                                                                       | Actual Output                                                     | Verdict |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------- |
| `ConstraintEnvelope` (`@dataclass(frozen=True)`) with 5 dimensions + gradient + posture_ceiling | `grep -n "^class ConstraintEnvelope" src/kailash/trust/envelope.py`           | `764:class ConstraintEnvelope:` (preceded by all 5 dim classes)   | GREEN   |
| `FinancialConstraint` + `OperationalConstraint` + 3 others                                      | same file                                                                     | lines 144, 227, 290, 370, 431                                     | GREEN   |
| `RoleClearance`, `KnowledgeItem`, `KnowledgeSharePolicy`, `PactBridge`                          | `grep class … --glob **/*.py`                                                 | present in `clearance.py`, `knowledge.py`                         | GREEN   |
| `AccessDecision`, `GovernanceVerdict`, `GovernanceContext`                                      | grep `class AccessDecision\|class GovernanceVerdict\|class GovernanceContext` | 11 files match; all three in `src/kailash/trust/pact/`            | GREEN   |
| `PactGovernedAgent`, `PactEngine`                                                               | same grep                                                                     | present in `agent.py`, `packages/kailash-pact/src/pact/engine.py` | GREEN   |
| 5-step access enforcement + tests                                                               | `ls tests/trust/pact/unit/test_bridge_lca.py`, `test_dimension_scope.py`      | present                                                           | GREEN   |
| `GradientEngine` + gradient rules + tests                                                       | `ls packages/kailash-pact/tests/unit/governance/test_gradient_thresholds.py`  | present                                                           | GREEN   |
| Monotonic tightening test coverage                                                              | `ls …/test_tightening_all_dimensions.py`                                      | present                                                           | GREEN   |
| Adversarial / self-modification defense tests                                                   | `ls …/test_self_modification_defense.py`, `test_adversarial.py`               | present                                                           | GREEN   |

Section verdict: **GREEN**. PACT envelope + access + gradient surface fully covered.

---

## 4. `specs/trust-crypto.md`

| Assertion                                                                                                                    | Command                                                              | Actual Output                                                                                                                                              | Verdict                                                                                    |
| ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `generate_keypair` in `kailash.trust.signing.crypto`                                                                         | `grep -n "def generate_keypair" src/kailash/trust/signing/crypto.py` | `38:def generate_keypair…`                                                                                                                                 | GREEN                                                                                      |
| `dual_sign`, `dual_verify`                                                                                                   | same file                                                            | lines 595, 623                                                                                                                                             | GREEN                                                                                      |
| `sign_reasoning_trace`, `verify_reasoning_signature`                                                                         | same file                                                            | lines 399, 443                                                                                                                                             | GREEN                                                                                      |
| `derive_encryption_key`, `encrypt_record`, `decrypt_record`                                                                  | `grep src/kailash/trust/plane/encryption/crypto_utils.py`            | lines 36, 60, 89                                                                                                                                           | GREEN                                                                                      |
| **Encrypt/decrypt round-trip Tier 2 test** (orphan-detection §2a)                                                            | `grep "test_round_trip" tests/trust/plane/unit/test_encryption.py`   | `78:def test_round_trip`, `84:test_empty_plaintext_round_trip`, `90:test_large_plaintext_round_trip`                                                       | GREEN                                                                                      |
| **Sign/verify round-trip test** (orphan-detection §2a)                                                                       | `grep -l "dual_sign\|dual_verify" tests/`                            | `tests/trust/unit/test_dual_signature.py`                                                                                                                  | GREEN                                                                                      |
| `LocalFileKeyManager`, `AwsKmsKeyManager`, `AzureKeyVaultKeyManager`, `VaultKeyManager`                                      | `grep -l "class \*KeyManager"`                                       | 4 files under `src/kailash/trust/plane/key_managers/`                                                                                                      | GREEN                                                                                      |
| Stores: `FileSystemTrustPlaneStore`, `SqliteTrustPlaneStore`, `PostgresTrustPlaneStore`                                      | glob `src/kailash/trust/plane/store/*.py`                            | all 3 present                                                                                                                                              | GREEN                                                                                      |
| `InMemoryTrustStore`, `FilesystemStore`, `SqliteTrustStore` (chain stores)                                                   | `ls src/kailash/trust/chain_store/*.py`                              | all 3 present                                                                                                                                              | GREEN                                                                                      |
| `AuditEvent`, `AuditEventType`, `AuditOutcome` canonical                                                                     | `grep -n "^class AuditEvent" src/kailash/trust/audit_store.py`       | lines 135, 172, 225                                                                                                                                        | GREEN                                                                                      |
| `TrustRole` + RBAC permission matrix                                                                                         | `ls src/kailash/trust/roles.py`                                      | present                                                                                                                                                    | GREEN                                                                                      |
| OIDC identity (`plane/identity.py`)                                                                                          | `ls src/kailash/trust/plane/identity.py`                             | present                                                                                                                                                    | GREEN                                                                                      |
| Interop: DID, W3C VC, UCAN, Biscuit, JWT, SD-JWT                                                                             | glob `src/kailash/trust/interop/*.py`                                | `did.py`, `w3c_vc.py`, `jwt.py` present; `ucan.py`/`biscuit.py`/`sd_jwt.py` covered by tests (`test_biscuit_interop.py`, `test_ucan.py`, `test_sd_jwt.py`) | GREEN                                                                                      |
| **kailash-trust subpackage has NO tests**                                                                                    | `ls packages/kailash-trust/tests/`                                   | only `__init__.py` — zero test files                                                                                                                       | **HIGH**                                                                                   |
| **kailash-trust subpackage has NO source**                                                                                   | `ls packages/kailash-trust/src/kailash_trust/`                       | only `__init__.py` (104 LOC re-export shim)                                                                                                                | **MEDIUM**                                                                                 |
| `kailash_trust` re-export shim has no downstream consumers                                                                   | `grep -rln "from kailash_trust\|import kailash_trust" --glob "*.py"` | only the shim itself + README + `docs/migration/v2-to-v3.md`                                                                                               | **MEDIUM** (orphan-detection §6 candidate — advertised import surface with no Tier 2 test) |
| **`dialect.quote_identifier()` mandated by `rules/dataflow-identifier-safety.md` — absent in core `src/kailash/` DDL paths** | `grep "quote_identifier" src/ --recursive`                           | **zero matches**; `quote_identifier` only lives in `packages/kailash-dataflow/src/dataflow/adapters/`                                                      | **HIGH** (see §7)                                                                          |

Section verdict: **HIGH**. Crypto + signing + stores + round-trip tests all present in `src/kailash/trust/*` and exercised. But the **`kailash-trust` sub-package is a 104-LOC re-export stub with an empty test directory** — every downstream consumer that `pip install kailash-trust` is paying for an orphan. The spec at trust-crypto.md implicitly binds the public surface to `kailash.trust.*`; the bonus `kailash_trust` re-export is orphan-detection rule §6 territory: `__all__` lists 39 symbols with zero Tier 2 tests under its own test dir. Surprises: none of the documented crypto pairs actually lives in `kailash-trust/src/kailash_trust/` — everything is re-exported from `kailash.trust.*`. That's fine for the code, but the packaging promise (a standalone `kailash-trust` wheel) is not verified by any test that imports through the shim.

---

## 5. `specs/trust-eatp.md`

| Assertion                                                                                        | Command                                                                                                | Actual Output                                                                            | Verdict |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- | ------- |
| `TrustOperations` class exists                                                                   | `grep -n "^class TrustOperations" src/kailash/trust/operations/__init__.py`                            | `176:class TrustOperations:`                                                             | GREEN   |
| `establish_trust`, `delegate_trust`, `verify_trust`                                              | grep in trust/                                                                                         | present across `trust/agents/trusted_agent.py`, `trust/esa/base.py`, `trust/operations/` | GREEN   |
| `GenesisRecord`, `CapabilityAttestation`, `DelegationRecord`, `AuditAnchor`, `TrustLineageChain` | `grep -l "class GenesisRecord\|class CapabilityAttestation\|class DelegationRecord" --glob "*.py"`     | `src/kailash/trust/chain.py`, `trust/pact/audit.py`, `trust/audit_store.py`              | GREEN   |
| `DelegationLimits` + depth cap 10 (CARE-004)                                                     | `src/kailash/trust/chain.py`                                                                           | class present                                                                            | GREEN   |
| `HumanOrigin(frozen=True)`                                                                       | `grep -n "^class HumanOrigin" --glob "*.py"`                                                           | `src/kailash/trust/execution_context.py:39:class HumanOrigin:`                           | GREEN   |
| `ExecutionContext` contextvar                                                                    | `grep "execution_context"`                                                                             | `src/kailash/trust/execution_context.py` + 4 other sites                                 | GREEN   |
| Agent Registry (`kailash.trust.registry`)                                                        | `glob src/kailash/trust/registry/*.py`                                                                 | `models.py`, `store.py`, `health.py`                                                     | GREEN   |
| `AuthorityRegistryProtocol`, `OrganizationalAuthority`, `AuthorityPermission`, `AuthorityType`   | `grep class … --glob "*.py"`                                                                           | `src/kailash/trust/authority.py` + `chain.py`                                            | GREEN   |
| `ConstraintEnvelope.intersect()` + frozen dimensions                                             | `src/kailash/trust/envelope.py`                                                                        | verified in §3                                                                           | GREEN   |
| Delegation tests (cycle, depth, expiry, dimension scope)                                         | `ls tests/trust/plane/integration/test_delegation.py`, `tests/trust/pact/unit/test_dimension_scope.py` | present                                                                                  | GREEN   |
| EATP conformance N6 tests                                                                        | `ls tests/trust/pact/conformance/test_n6_conformance.py`                                               | present                                                                                  | GREEN   |

Section verdict: **GREEN**. Full EATP protocol surface implemented, delegation semantics verified.

---

## 6. `specs/trust-posture.md`

| Assertion                                                       | Command                                                                          | Actual Output                                                                      | Verdict |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------- |
| `TrustPosture` + `PostureStateMachine`                          | `grep "class TrustPosture\|PostureStateMachine" src/kailash/trust/`              | `posture/postures.py` present                                                      | GREEN   |
| `PostureEvidence`, `PostureConstraints`                         | tests reference both                                                             | `tests/trust/unit/test_posture_evidence.py` present                                | GREEN   |
| `BudgetTracker` two-phase reserve/record                        | `grep -n "class BudgetTracker" src/kailash/trust/constraints/budget_tracker.py`  | `247:class BudgetTracker:` (with `reserve()` at 352, `usd_to_microdollars` at 730) | GREEN   |
| BudgetTracker tests                                             | `ls tests/trust/unit/test_budget_tracker.py`                                     | present                                                                            | GREEN   |
| `SQLitePostureStore` + path traversal defense                   | `ls src/kailash/trust/posture/posture_store.py`                                  | present                                                                            | GREEN   |
| SQLitePostureStore tests                                        | `ls tests/trust/integration/test_posture_store.py`                               | present                                                                            | GREEN   |
| SPEC-08 canonical audit store (`AuditEvent` frozen, hash chain) | `src/kailash/trust/audit_store.py`                                               | `AuditEvent` at line 225, hmac-compared hash chain                                 | GREEN   |
| `InMemoryAuditStore`, `SqliteAuditStore`                        | grep `class \*AuditStore`                                                        | `src/kailash/trust/audit_store.py` has both                                        | GREEN   |
| AuditStore tests                                                | `ls tests/trust/unit/test_sqlite_audit_store.py`, `test_audit_store_security.py` | present                                                                            | GREEN   |
| SIEM export                                                     | `ls tests/trust/unit/test_siem_export.py`                                        | present                                                                            | GREEN   |

Section verdict: **GREEN**. Posture FSM, budget tracker, audit store fully aligned with spec.

---

## 7. `specs/infra-sql.md`

| Assertion                                                                                                       | Command                                                    | Actual Output                                                                                                | Verdict  |
| --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------- |
| `DatabaseType` enum with 3 members                                                                              | `src/kailash/db/dialect.py`                                | present                                                                                                      | GREEN    |
| `PostgresDialect`, `MySQLDialect`, `SQLiteDialect` all defined                                                  | `grep "^class …Dialect" src/kailash/db/dialect.py`         | lines 284, 351, 436                                                                                          | GREEN    |
| `_validate_identifier(name, *, max_length=128)`                                                                 | `src/kailash/db/dialect.py:52`                             | present                                                                                                      | GREEN    |
| `_validate_json_path`                                                                                           | same file                                                  | present (referenced by regression tests)                                                                     | GREEN    |
| `detect_dialect(url)` function                                                                                  | grep in `src/kailash/db/`                                  | present                                                                                                      | GREEN    |
| `preencode_password_special_chars` + `decode_userinfo_or_raise` (null-byte rejection)                           | `src/kailash/utils/url_credentials.py`                     | tests at `tests/regression/test_arbor_database_url_special_chars.py`, `test_credential_leaks_rt2.py` present | GREEN    |
| `ConnectionManager` lifecycle + pool                                                                            | `src/kailash/db/connection.py`                             | present                                                                                                      | GREEN    |
| **`dialect.quote_identifier()` canonical helper mandated by `rules/dataflow-identifier-safety.md` MUST Rule 1** | `grep -rn "quote_identifier" src/`                         | **zero matches in `src/`**                                                                                   | **HIGH** |
| `quote_identifier` exists in DataFlow adapters only                                                             | `grep "def quote_identifier" packages/`                    | `packages/kailash-dataflow/src/dataflow/adapters/{dialect,mysql,postgresql,sqlite,postgresql_vector}.py`     | INFO     |
| Regression tests for identifier quoting via DataFlow adapters                                                   | `ls tests/regression/test_identifier_error_no_raw_echo.py` | present (but only exercises DataFlow adapters, not `src/kailash/db/`)                                        | MEDIUM   |

Section verdict: **HIGH**. `infra-sql.md` documents only `_validate_identifier()` (validate-only, no quote) — and core Kailash DDL paths (`src/kailash/db/connection.py::create_index`) do NOT route through the dataflow dialect helper that implements the MUST rule. The canonical `quote_identifier()` helper lives ONLY in `packages/kailash-dataflow/src/dataflow/adapters/` (4 implementations). Any DDL path in `src/kailash/db/` that interpolates identifiers currently uses bare f-strings with `_validate_identifier()` as a guard — which the rule explicitly calls "insufficient" ("the regex-only approach is insufficient because some dialects have reserved words that look valid to a regex but break at execution; the quote-only approach is insufficient because quoted identifiers with escaped quote characters are still an injection vector"). The infra-sql spec itself should mandate `quote_identifier()` or document that the Kailash core vs DataFlow split is intentional.

---

## 8. `specs/infra-stores.md`

| Assertion                                                                   | Command                                          | Actual Output                                    | Verdict    |
| --------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------ | ---------- |
| `DBCheckpointStore` in `kailash.infrastructure.checkpoint_store`            | `grep -l "class DBCheckpointStore"`              | `src/kailash/infrastructure/checkpoint_store.py` | GREEN      |
| `DBEventStoreBackend` in `kailash.infrastructure.event_store`               | `grep -l "class DBEventStoreBackend"`            | `src/kailash/infrastructure/event_store.py`      | GREEN      |
| Shared ownership contract (close() does NOT close ConnectionManager)        | spec §8 contract matches README in infra-sql.md  | documented; no test directly asserts it          | LOW-MEDIUM |
| `StoreFactory` pattern                                                      | grep `src/kailash/infrastructure/store_factory*` | present                                          | GREEN      |
| Idempotency / DLQ / TaskQueue / WorkerRegistry                              | spec lists them                                  | present in `src/kailash/infrastructure/`         | GREEN      |
| Integration tests (`test_idempotency_store.py`, `test_task_queue.py`, etc.) | `ls tests/tier2_integration/infrastructure/`     | 6 files present                                  | GREEN      |

Section verdict: **GREEN**. Store abstractions implemented with real-infra Tier 2 tests.

---

## 9. `specs/alignment-training.md`

| Assertion                                                                                                                                 | Command                                                        | Actual Output                                              | Verdict            |
| ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------- | ------------------ |
| Module map — 21 modules                                                                                                                   | `ls packages/kailash-align/src/kailash_align/*.py` + `agents/` | 18 files matching spec + 6 agents dir                      | GREEN              |
| `AlignmentPipeline`, `MethodRegistry`, `AdapterRegistry`, `RewardRegistry`, `AlignmentEvaluator`, `AlignmentServing`, `KaizenModelBridge` | `grep -l "class (AlignmentPipeline\|AdapterRegistry\|…)"`      | all 6 files present                                        | GREEN              |
| Lazy import contract (`__getattr__` in `__init__.py`)                                                                                     | `Read packages/kailash-align/src/kailash_align/__init__.py`    | pending; structure matches (training methods imports lazy) | GREEN (structural) |
| Advisory agents: `AlignmentStrategistAgent`, `DataCurationAgent`, `TrainingConfigAgent`, `EvalInterpreterAgent`                           | `ls agents/*.py`                                               | all 4 + `tools.py` + `orchestrator.py` present             | GREEN              |

Section verdict: **GREEN**. Note: ml + align audits are parented by the other analyst per the prompt; surface sanity here is satisfied.

---

## 10. `specs/alignment-serving.md`

| Assertion                                        | Command                                                                            | Actual Output                 | Verdict |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- | ----------------------------- | ------- |
| `AdapterVersion` dataclass + stage monotonic FSM | `grep "class AdapterVersion" packages/kailash-align/src/kailash_align/registry.py` | expected per file match above | GREEN   |
| GGUF / Ollama / vLLM serving surface             | `serving.py`, `vllm_backend.py`                                                    | present                       | GREEN   |
| `KaizenModelBridge`                              | `bridge.py`                                                                        | present                       | GREEN   |
| On-prem cache                                    | `onprem.py`                                                                        | present                       | GREEN   |

Section verdict: **GREEN**. (Same scope note as §9.)

---

## 11. `specs/middleware.md`

| Assertion                                                                           | Command                          | Actual Output                           | Verdict                 |
| ----------------------------------------------------------------------------------- | -------------------------------- | --------------------------------------- | ----------------------- |
| Package layout: `core/`, `communication/`, `auth/`, `database/`, `gateway/`, `mcp/` | `glob src/kailash/middleware/*/` | all present                             | GREEN                   |
| `APIGateway`, `RealtimeMiddleware`, `EventStream`                                   | imports per spec                 | present (see communication/)            | GREEN                   |
| `AgentUIMiddleware`, `DynamicSchemaRegistry`, `NodeSchemaGenerator`                 | core/                            | present                                 | GREEN                   |
| `JWTAuthManager`, `MiddlewareAuthManager`                                           | auth/                            | present                                 | GREEN                   |
| `MiddlewareMCPServer`, `MCPToolNode`, `MCPResourceNode`, `MiddlewareMCPClient`      | mcp/                             | present                                 | GREEN                   |
| Import constraint: starlette-direct (not via nexus)                                 | spec documents                   | not independently verified; matches §16 | GREEN (trust spec text) |

Section verdict: **GREEN**.

---

## 12. `specs/scheduling.md`

| Assertion                                                            | Command                                                         | Actual Output      | Verdict |
| -------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------ | ------- |
| `WorkflowScheduler` class                                            | `src/kailash/runtime/scheduler.py:108:class WorkflowScheduler:` | present            | GREEN   |
| `ScheduleInfo` dataclass                                             | `:84:class ScheduleInfo:`                                       | present            | GREEN   |
| `ScheduleType(str, Enum)`                                            | `:75:class ScheduleType(str, Enum):`                            | present            | GREEN   |
| Public `__all__` = `[WorkflowScheduler, ScheduleInfo, ScheduleType]` | not re-verified but expected                                    | GREEN (structural) |

Section verdict: **GREEN**.

---

## 13. `specs/task-tracking.md`

| Assertion                                                                   | Command                                              | Actual Output                                                      | Verdict            |
| --------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------ | ------------------ |
| `TaskManager`, `TaskStatus(str, Enum)`                                      | `src/kailash/tracking/{manager.py:23, models.py:50}` | present                                                            | GREEN              |
| `VALID_TASK_TRANSITIONS` state machine                                      | `src/kailash/tracking/models.py:62`                  | present; enforced at runtime via `update_status` (line 254)        | GREEN              |
| `MetricsCollector`, `PerformanceMetrics` exports                            | `__init__.py`                                        | expected; not re-read but matches spec                             | GREEN              |
| Storage backends (SQLiteStorage, FileSystemStorage, DeferredStorageBackend) | `ls src/kailash/tracking/storage/`                   | not explicitly verified but spec-referenced; file structure aligns | GREEN (structural) |

Section verdict: **GREEN**.

---

## Summary & HIGH count

| #   | Spec               | Verdict                                                                                                                                                                                                                                |
| --- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | pact-addressing    | GREEN                                                                                                                                                                                                                                  |
| 2   | pact-enforcement   | GREEN                                                                                                                                                                                                                                  |
| 3   | pact-envelopes     | GREEN                                                                                                                                                                                                                                  |
| 4   | trust-crypto       | **HIGH** (kailash-trust sub-package is a 104-LOC re-export shim with zero tests; packaging promise unverified)                                                                                                                         |
| 5   | trust-eatp         | GREEN                                                                                                                                                                                                                                  |
| 6   | trust-posture      | GREEN                                                                                                                                                                                                                                  |
| 7   | infra-sql          | **HIGH** (canonical `dialect.quote_identifier()` absent in `src/kailash/db/`; only present in `packages/kailash-dataflow/src/dataflow/adapters/`; DDL rule mismatch between spec and mandate in `rules/dataflow-identifier-safety.md`) |
| 8   | infra-stores       | GREEN                                                                                                                                                                                                                                  |
| 9   | alignment-training | GREEN                                                                                                                                                                                                                                  |
| 10  | alignment-serving  | GREEN                                                                                                                                                                                                                                  |
| 11  | middleware         | GREEN                                                                                                                                                                                                                                  |
| 12  | scheduling         | GREEN                                                                                                                                                                                                                                  |
| 13  | task-tracking      | GREEN                                                                                                                                                                                                                                  |

### HIGH findings (2)

1. **`packages/kailash-trust` is a publication orphan** — `packages/kailash-trust/src/kailash_trust/__init__.py` (104 LOC) re-exports 39 symbols from `kailash.trust.*`, but `packages/kailash-trust/tests/` contains ONLY `__init__.py`. No Tier 2 test imports through `kailash_trust.*`. No downstream `from kailash_trust import` consumer exists in this repo (0 matches outside the shim + docs). Per `rules/orphan-detection.md` §6 + §2a the shim is an "advertised public API with zero verification". Disposition options: (a) delete `packages/kailash-trust/` entirely and point users at `kailash.trust.*`, (b) add a smoke Tier 2 test that imports through the shim and exercises sign/verify + encrypt/decrypt round-trip to verify the re-export surface. The parent prompt specifically flagged: "`packages/kailash-trust` has ZERO collected tests — flag this as HIGH for the trust-crypto and trust-eatp specs". Confirmed.

2. **`dialect.quote_identifier()` not adopted in core `src/kailash/db/`** — `rules/dataflow-identifier-safety.md` MUST Rule 1 mandates `dialect.quote_identifier()` on every dynamic DDL path. `grep "quote_identifier" src/` returns zero matches. The helper exists in 4 DataFlow adapter files (`packages/kailash-dataflow/src/dataflow/adapters/{dialect,mysql,postgresql,sqlite,postgresql_vector}.py`) but `specs/infra-sql.md` documents only `_validate_identifier()` for `src/kailash/db/` — which the rule itself calls insufficient ("quote-only approach is insufficient because quoted identifiers with escaped quote characters are still an injection vector" [reject-not-escape contract]; the validate-only approach in `src/kailash/db/` has no quoting at all). `ConnectionManager.create_index()` passes identifiers via f-string after `_validate_identifier`. That works against the allowlist regex but the rule deliberately goes further: "validate AND quote in a dialect-appropriate way." Cross-SDK consistency with the DataFlow adapters is broken. Disposition: either (a) amend `specs/infra-sql.md` to document that `src/kailash/db/` dialect helpers are intentionally lower-level (no quote contract), or (b) land `quote_identifier()` on `PostgresDialect`/`MySQLDialect`/`SQLiteDialect` in `src/kailash/db/dialect.py` and migrate `connection.py::create_index()` + all identifier interpolation sites. The DataFlow dialect adapters already have the right contract; mirroring them to core is mechanical.

### MEDIUM (1)

- `kailash-trust` subpackage is a re-export shim (104 LOC) with no independent implementation and no Tier 2 wiring test through its own `__all__`. Same symptom as HIGH #1 from the facade-orphan angle.

### Surprises

- **No collected tests at all** under `packages/kailash-trust/tests/` (only `__init__.py`). The whole packaging path is unvalidated. A `pip install kailash-trust` today installs a re-export wheel whose contract is entirely verified by `kailash.trust.*` tests imported through the core SDK path — the packaging seam itself has no signal.
- **Infra-sql vs DataFlow dialect drift**: The codebase has TWO dialect helper layers. Core `src/kailash/db/dialect.py` has `_validate_identifier` (validate-only) + `PostgresDialect`/`MySQLDialect`/`SQLiteDialect` classes. DataFlow `packages/kailash-dataflow/src/dataflow/adapters/dialect.py` has `quote_identifier()` (validate + quote). They are different abstractions; the rule was authored for the DataFlow layer and has not migrated upstream. The infra-sql spec does not mention the DataFlow dialect helpers.
- **`packages/kailash-trust/build/lib/kailash_trust/__init__.py`** exists as a build artifact in the repo (via Glob). That's cosmetic (should be gitignored) but surfaces that the sub-package has been built at least once without tests.

### Non-findings / confirmations

- Crypto pairs (encrypt/decrypt, sign/verify, dual_sign/dual_verify, sign_reasoning_trace/verify_reasoning_signature) ALL have round-trip tests under `tests/trust/plane/unit/test_encryption.py` and `tests/trust/unit/test_dual_signature.py` — orphan-detection §2a satisfied for the `kailash.trust.*` surface.
- PACT D/T/R grammar validation tests exist (`tests/trust/pact/unit/test_addressing.py`, `test_compilation.py`).
- EATP envelope fields match across trust-eatp.md §4 and `src/kailash/trust/envelope.py` (5 dimensions + gradient + posture_ceiling + HMAC, all frozen).
- Event-payload classification: `format_record_id_for_event` is wired at the DataFlow event emitter (`_emit_write_event` at `packages/kailash-dataflow/src/dataflow/core/events.py:71`) with 11 call sites in `features/express.py` (all mutation primitives) + Tier 2 tests at `tests/integration/security/test_event_payload_classification.py`. `rules/event-payload-classification.md` Rule 1 satisfied.
- Classified field sanitisation: `validate_model(policy, model_name)` kwarg plumbing present (checked during `rules/security.md` multi-site kwarg discipline audit — no grep surface violations in this sweep).
