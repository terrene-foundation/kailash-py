---
priority: 10
scope: path-scoped
paths:
  - "**/dataflow/**"
  - "**/kailash-dataflow/**"
  - "**/*classification*"
  - "**/*redact*"
---

# DataFlow Classification Redaction Rules


<!-- slot:neutral-body -->

Classification-aware fields (PII, CONFIDENTIAL, SECRET) are redacted by a single helper — `apply_read_classification(model.fields, record)` — that the read path calls before returning rows to the caller. The failure mode this rule targets is silent and systemic: a framework that applies redaction on `read()` / `list()` but NOT on mutation return-paths (`create()`, `upsert()`, `bulk_create()`, any future `INSERT ... RETURNING` primitive) leaks every classified field on every write, regardless of caller clearance.

The implicit assumption "reads are the read path" is wrong the moment a mutation primitive returns a row. INSERT RETURNING, UPSERT RETURNING, UPDATE RETURNING, and DELETE RETURNING are all read surfaces dressed as mutations; each one MUST route its return value through the same redaction helper as `read()` or it re-opens the leak.

This rule extends the discipline already mandated by `rules/tenant-isolation.md` (tenant_id on every cache key and audit row) and `rules/orphan-detection.md` + `rules/facade-manager-detection.md` (Tier 2 tests prove the hot path calls the manager) to classification-aware code specifically.

## MUST Rules

### 1. Every Mutation Return-Path MUST Apply Read Redaction

Any DataFlow primitive that returns a row (`create`, `update`, `upsert`, `bulk_create`, `bulk_upsert`, any future `*_returning` variant) MUST pass the returned dict through `apply_read_classification(model.fields, record)` before returning it to the caller.

```python
# DO — mutation applies read-path redaction on its return value
async def create(self, model: ModelInfo, row: dict) -> dict:
    record = row_to_dict(row)
    apply_read_classification(model.fields, record)
    return record

# DO NOT — bare row_to_dict leaks classified fields in every create/upsert response
async def create(self, model: ModelInfo, row: dict) -> dict:
    record = row_to_dict(row)
    return record  # SECRET / PII fields returned verbatim to any caller
```

**BLOCKED rationalizations:**

- "The caller just created the row so they already know the classified field"
- "Redaction is a read concern, not a write concern"
- "We'll add redaction when we add the test"
- "INSERT RETURNING is a mutation, not a read"
- "The row came from the caller's input, redacting it is pointless"

**Why:** Caller clearance is evaluated at response time, not at write time. A caller with `clearance=Public` can legally call `create()` on a model with a SECRET field (the write goes through RBAC), but MUST NOT see the SECRET field echoed back in the response. The failure landed in the wild because `create()` and `upsert()` returned `row_to_dict(row)` directly and leaked every classified column.

### 2. Delegation-Based Redaction MUST Be Pinned With A Comment

If a mutation method achieves redaction indirectly by delegating to `self.read()` / `self.list()` / another redaction-aware method, the delegation site MUST carry a comment explaining that the delegation is load-bearing for the redaction contract.

```python
# DO — comment pins the delegation as redaction-critical
async def update(self, model: ModelInfo, pk: object, patch: dict) -> dict:
    await self._apply_update_sql(model, pk, patch)
    # NOTE: redaction contract — read() applies apply_read_classification.
    # Do NOT inline a SELECT + row_to_dict here without porting the redaction
    # call, or classified fields leak on every update response.
    return await self.read(model, pk)

# DO NOT — silent delegation; future refactor inlines SELECT + row_to_dict and reopens leak
async def update(self, model: ModelInfo, pk: object, patch: dict) -> dict:
    await self._apply_update_sql(model, pk, patch)
    return await self.read(model, pk)
```

**Why:** Delegation-only redaction is invisible at the delegation site. A future "optimization" that replaces `self.read()` with an inline `SELECT ... WHERE id = $1` + `row_to_dict()` looks correct in isolation and passes unit tests, but silently reopens the leak. The pinned comment makes the contract visible to the reviewer.

### 3. Every Mutation Return-Path MUST Have A Tier 2 Redaction Test

Every public method that returns a row MUST have a Tier 2 integration test (real Postgres/MySQL, real classification policy, real clearance) that asserts the return dict contains `"[REDACTED]"` (or the configured sentinel) for every classified field when the caller's clearance is insufficient. One test per public method — no aggregate "all methods covered by one test" passes review.

```python
# DO — Tier 2 test per mutation method, real database, real clearance
@pytest.mark.integration
async def test_create_redacts_classified_fields_for_public_clearance(test_suite):
    db = DataFlow(test_suite.config.url)

    @db.model
    class Document:
        title: str
        body: str = field(classify=("SECRET", "REDACT"))

    set_clearance(ClassificationLevel.PUBLIC)
    returned = await db.express.create("Document", {
        "title": "public title",
        "body": "SECRET body content",
    })
    assert returned["body"] == "[REDACTED]"

# DO NOT — Tier 1 unit test mocking the redaction helper
def test_create_calls_redaction_helper():
    record = {"body": "SECRET"}
    apply_read_classification(_fields(), record)
    assert record["body"] == "[REDACTED]"
# ↑ proves the helper redacts, NOT that create() calls it
```

**Why:** Tier 1 tests prove the helper works in isolation. The exact failure mode this rule prevents is "the mutation method never calls the helper" — Tier 1 cannot detect that. Real-database Tier 2 tests exercise the same code path a caller hits in production, which is the only surface where the leak manifests.

### 4. Scalar Aggregate Returns Are Exempt

Methods that return computed scalars — `count()`, `sum_by(field)`, `aggregate()`, `exists()` — are NOT subject to this rule. They return derived values, not column values, and the classification helper does not apply. This carve-out MUST be documented at the method site so a future rule-strict refactor does not add pointless redaction that breaks the method's contract.

```python
# DO — explicit carve-out comment
async def count(self, model: ModelInfo, filter: dict) -> int:
    # Classification carve-out: scalar aggregate, no column values returned.
    # apply_read_classification is not applicable (no record dict to redact).
    sql = build_count_sql(model, filter)
    return await self._conn.fetchval(sql)

# DO NOT — wrap the scalar in a fake dict just to run the redaction helper
async def count(self, model: ModelInfo, filter: dict) -> int:
    n = await self._conn.fetchval(build_count_sql(model, filter))
    pseudo = {"count": n}
    apply_read_classification(model.fields, pseudo)  # no-op, just noise
    return pseudo["count"]
```

**Why:** Without an explicit carve-out, a future `/redteam` sweep sees "no redaction call on return path" and flags a false positive, or worse, "fixes" it by restructuring the return type. The comment makes the exemption surviving-the-refactor explicit.

## MUST NOT

- Return `row_to_dict(row)` from a mutation method without first calling `apply_read_classification`

**Why:** Every non-redacted return is a leak on the happy path, not an edge case — it fires on every create/upsert regardless of filter, clearance, or tenant.

- Cover a mutation return-path with Tier 1 unit tests alone

**Why:** Tier 1 mocks the framework's call into the helper; the orphan failure mode is "the framework never calls the helper," which Tier 1 cannot detect.

- Remove delegation-based redaction (e.g., replace `self.read()` with inline SQL) without porting the redaction call AND keeping the pinned comment

**Why:** Silent refactor of a delegation-redacted method is the #1 reintroduction vector for this leak; the pinned comment + explicit port is the only structural defense.

- Treat classification as a purely read-time concern

**Why:** Every write primitive that returns a row IS a read surface; classification is a property of the field, not of the verb.

## Relationship to Other Rules

- `rules/tenant-isolation.md` — mandates tenant_id on every cache key, audit row, and metric label. Same "must apply on every return path" discipline, applied to tenant dimension instead of classification.
- `rules/orphan-detection.md` + `rules/facade-manager-detection.md` — require Tier 2 tests prove the framework's hot path actually calls the manager. This rule extends that to "prove the framework's mutation paths actually call the redaction helper."
- `rules/testing.md` § Tier 2 — the test tier mandated by rule 3 above.
- `rules/zero-tolerance.md` Rule 2 — a redaction helper that exists but isn't called from the mutation path is the exact "fake classification" failure mode Rule 2 enumerates.

Origin: kailash-rs commit 2e9dbf94 (2026-04-17) + gh-coc-claude-rs#51 item 3e. Pre-fix, `create()` and `upsert()` leaked classified fields in every return dict regardless of caller clearance. Cross-SDK principle — kailash-py DataFlow Express has the same architecture and is expected to carry the same gap (cross-SDK verification ticket filed separately).

<!-- /slot:neutral-body -->
