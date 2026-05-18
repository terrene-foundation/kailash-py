# 0010 PROBE — B-2e auth orphan map

Date: 2026-05-16
Phase: /implement (Workstream-B parallel wave, shard B-2e)
Issue: #996
Test file under rewrite: `packages/kailash-dataflow/tests/unit/templates/test_saas_starter_auth.py` (1375 LOC, module-skipped via `pytestmark`)

## Why this entry

Per shard prompt phase 1 — catalog every test function in the
pytestmark-skipped Tier-1 file and verify each test's production target
exists and is reachable. The verdict drives phase 2 (rewrite vs delete).
Brief failure-layer #3 (`workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:27-28` —
"fork + asyncio incompatibility — child processes inherited an event loop
they couldn't cleanly use") is the reason the file is currently parked;
the rewrite moves it to Tier-2 where `LocalRuntime` + `WorkflowBuilder`
top-imports + real `runtime.execute(workflow)` against in-process aiosqlite
are contractually permitted.

## Production surface (under `packages/kailash-dataflow/templates/saas_starter/`)

| Module | LOC | Public symbols imported by the unit test |
|---|---|---|
| `workflows/auth.py` | 380 | `build_login_workflow`, `build_oauth_github_workflow`, `build_oauth_google_workflow`, `build_password_reset_complete_workflow`, `build_password_reset_request_workflow`, `build_registration_workflow`, `build_token_validation_workflow` |
| `middleware/tenant.py` | 230 | `build_org_switching_workflow`, `build_tenant_scoped_bulk_update_workflow`, `build_tenant_scoped_delete_workflow`, `build_tenant_scoped_list_workflow`, `build_tenant_scoped_read_workflow`, `build_tenant_scoped_update_workflow`, `inject_tenant_context` |
| `models.py` | 603 | `register_models` (registers `Organization`, `User`, `Subscription`, `APIKey`, `WebhookEvent`) |
| `auth/jwt_auth.py` | 545 | NOT imported by this test file — owned by sibling test `test_jwt.py` (already Tier-2) |

The brief framing referenced `auth/jwt_auth.py` as the production target;
empirically the unit file imports from `workflows/auth.py` and
`middleware/tenant.py` instead. `jwt_auth.py` is exercised by the sibling
Tier-2 file `tests/integration/templates/saas_starter/test_jwt.py` (the
B-2a shard already landed). This shard inherits no responsibility for
`jwt_auth.py`.

## Test → production map

### Section 1: TestSaaSDataModels (5 tests, lines 72-451)

| Test | Production target | Reachable? |
|---|---|---|
| `test_organization_model_structure` | `models.register_models` → `Organization` model | YES — `models.py:54-98` |
| `test_user_model_with_organization_fk` | `models.register_models` → `User` model | YES — `models.py` |
| `test_subscription_model_stripe_fields` | `models.register_models` → `Subscription` model | YES — `models.py` |
| `test_model_relationships` | `models.register_models` + `WorkflowBuilder` + `LocalRuntime` | YES — runs real workflows |
| `test_model_field_validation` | `models.register_models` + uniqueness constraints + real `runtime.execute` | YES |

### Section 2: TestAuthenticationWorkflows (8 tests, lines 459-961)

| Test | Production target | Reachable? |
|---|---|---|
| `test_user_registration_workflow` | `workflows.auth.build_registration_workflow` | YES — `workflows/auth.py:60-119` |
| `test_user_login_workflow` | `workflows.auth.build_login_workflow` + `build_registration_workflow` | YES — `workflows/auth.py:122-141` |
| `test_token_validation_workflow` | `workflows.auth.build_token_validation_workflow` + `build_registration_workflow` | YES — `workflows/auth.py:144-177` |
| `test_token_expiration_workflow` | `workflows.auth.build_token_validation_workflow` | YES (raises on expired token) |
| `test_password_reset_request_workflow` | `workflows.auth.build_password_reset_request_workflow` | YES — `workflows/auth.py:180-211` |
| `test_password_reset_complete_workflow` | `workflows.auth.build_password_reset_complete_workflow` | YES — `workflows/auth.py:214-238` |
| `test_oauth_google_integration_workflow` | `workflows.auth.build_oauth_google_workflow` | YES — `workflows/auth.py:241-309` |
| `test_oauth_github_integration_workflow` | `workflows.auth.build_oauth_github_workflow` | YES — `workflows/auth.py:312-380` |

### Section 3: TestMultiTenantIsolation (7 tests, lines 969-1375)

| Test | Production target | Reachable? |
|---|---|---|
| `test_tenant_context_injection` | `middleware.tenant.inject_tenant_context` | YES — `middleware/tenant.py:30-41` (pure function, no workflow) |
| `test_cross_tenant_read_prevention` | `middleware.tenant.build_tenant_scoped_read_workflow` | YES — `middleware/tenant.py:44-68` |
| `test_cross_tenant_update_prevention` | `middleware.tenant.build_tenant_scoped_update_workflow` | YES — `middleware/tenant.py:71-111` |
| `test_cross_tenant_delete_prevention` | `middleware.tenant.build_tenant_scoped_delete_workflow` | YES — `middleware/tenant.py:114-154` |
| `test_tenant_scoped_list_queries` | `middleware.tenant.build_tenant_scoped_list_workflow` | YES — `middleware/tenant.py:157-179` |
| `test_organization_switching` | `middleware.tenant.build_org_switching_workflow` | YES — `middleware/tenant.py:182-203` |
| `test_tenant_isolation_in_bulk_operations` | `middleware.tenant.build_tenant_scoped_bulk_update_workflow` | YES — `middleware/tenant.py:206-230` |

## Verdict

- **20 of 20 tests** map to existing production symbols. Zero orphans.
- All targeted helpers either return real `Workflow` objects (executable
  via `runtime.execute(workflow)` against the file-backed SQLite database)
  or are pure Python functions (`inject_tenant_context`).
- The original module-skip gate was NOT due to orphan production targets
  — it was due to Tier-1 violations (bare `LocalRuntime` + `WorkflowBuilder`
  top-imports + real `runtime.execute` against aiosqlite which hangs the
  GH-runner py3.11 worker per brief failure-layer #3).
- Therefore: phase 2 rewrites all 20 tests as Tier-2 integration tests
  against real `LocalRuntime` + `WorkflowBuilder` + file-backed SQLite
  (per `tests/CLAUDE.md` template carve-out, lines 109-122). No orphan
  deletions, no follow-up removal issues.

## Side observations (non-blocking)

1. The original test file's `clear_shared_memory_connections` autouse
   fixture handles a `:memory:` isolation hazard. The rewrite uses
   file-backed SQLite per the carve-out, so this fixture is unnecessary
   and will be dropped.

2. The original test file uses `int(time.time() * 1000)` for unique IDs
   to avoid cross-test collisions. With file-backed SQLite + per-test
   tempdir teardown, this is unnecessary — each test gets a fresh DB.
   The rewrite uses deterministic IDs scoped per test for readability.

3. The `_clear_shared_memory_connections` references
   `kailash.nodes.data.async_sql.SQLiteAdapter._shared_memory_connections`
   — a private API. Dropping the fixture avoids private-API coupling.

4. `inject_tenant_context` is a pure function (no workflow); the
   rewrite calls it directly without `runtime.execute`. The original
   already did this.

## Receipts

- Probe target file: `packages/kailash-dataflow/tests/unit/templates/test_saas_starter_auth.py` @ commit `18f64a2b` (worktree HEAD)
- Production reads:
  - `packages/kailash-dataflow/templates/saas_starter/workflows/auth.py`
  - `packages/kailash-dataflow/templates/saas_starter/middleware/tenant.py`
  - `packages/kailash-dataflow/templates/saas_starter/models.py`
  - `packages/kailash-dataflow/templates/saas_starter/auth/jwt_auth.py` (out of scope, sibling shard)
- Sibling Tier-2 reference patterns:
  - `packages/kailash-dataflow/tests/integration/templates/saas_starter/conftest.py` (env-var setdefault)
  - `packages/kailash-dataflow/tests/integration/templates/saas_starter/test_jwt.py` (file-backed SQLite + tempdir teardown)
- Tier-1/Tier-2 contract: `packages/kailash-dataflow/tests/CLAUDE.md:109-122` (templates carve-out)
