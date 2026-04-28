# Observability Rules — Extended Evidence and Examples

Companion reference for `.claude/rules/observability.md`.

## Full Endpoint Log Example

```python
# Full fleshed-out version of Mandatory Log Point §1
@router.post("/users")
async def create_user(req: CreateUserRequest):
    logger.info("create_user.start", route="/users", request_id=req.request_id)
    t0 = time.monotonic()
    try:
        user = await db.express.create("User", req.fields())
        logger.info(
            "create_user.ok",
            user_id=user["id"],
            latency_ms=(time.monotonic() - t0) * 1000,
        )
        return user
    except Exception as e:
        logger.exception(
            "create_user.error",
            error=str(e),
            latency_ms=(time.monotonic() - t0) * 1000,
        )
        raise
```

## Rule 7 — Bulk Op WARN: Evidence

Source audit (kailash-py): `packages/kailash-dataflow/src/dataflow/nodes/bulk_create.py::BulkCreate._handle_batch_error()` had `except Exception: continue` with zero logging. `BulkUpsert` used `print()` instead of a structured logger. A bulk op returning `failed: 10663` produced no WARN line in the log pipeline; alerting never fired.

See 0052-DISCOVERY §2.1 and `guides/deterministic-quality/06-observability-primitives.md` §2.

## Rule 8 — Schema-Name Hygiene: Evidence

Origin: Red team review of PR #430 (2026-04-12) flagged `packages/kailash-dataflow/src/dataflow/classification/policy.py::ClassificationPolicy.classify` emitting field names at WARN level. Because log aggregators (Datadog, Splunk, CloudWatch) are typically accessible to a broader audience than the production database (SREs, on-call engineers, support staff, third-party observability vendors), a WARN containing `field=ssn` revealed that the `users` table has an `ssn` column to every log reader — even though the VALUES never leaked.

Downgraded to DEBUG-level in commit 62d64ac7. Operators who need to audit unclassified fields enable DEBUG for the audit window.

Threat model: classification metadata is itself schema-level PII-adjacency. A schema leak is a blast-radius multiplier — it reveals WHICH data needs the most protection.

## Rule 5 — Triage Gate: Full Origin

Disposition protocol exists because early iterations reported "200 WARN entries" per run with no action taken. Agents rationally skipped the gate (200 disposition lines per run). Adding dedup (group-by-source-file + message pattern) reduced typical runs to 5-10 unique entries — tractable for per-entry disposition.

Origin traces to multiple sessions where silent-WARN patterns re-surfaced: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12) + PR #466 (63-warning sweep, 2026-04-14). The rule is now the structural defense against warning-creep.

### Full Scan Command Set

Run all that apply:

```bash
pytest --tb=short 2>&1 | grep -iE 'warn|error|deprecat|fail' | sort -u
find . -name "*.log" -mmin -120 -exec grep -HnE 'WARN|ERROR|FAIL' {} +
npm run build 2>&1 | grep -iE 'warn|error' | sort -u
cargo build 2>&1 | grep -iE 'warning|error'
pip check 2>&1
```

## Rule 6 — Mask Helper Full Code

```python
# DO — full mask helper with distinct failure sentinel
def mask_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return "<unparseable redis url>"  # grep-able failure sentinel
    if not parsed.scheme or not parsed.hostname:
        return "<unparseable redis url>"
    return f"{parsed.scheme}://***@{parsed.hostname}:{parsed.port or ''}{parsed.path}"

# DO NOT — "redis://***" on parse failure looks masked; actually "helper bailed"
def bad_mask_url(url):
    try: parsed = urlparse(url)
    except: return "redis://***"  # WRONG: indistinguishable from successful mask
```

```python
# DO — uniform mask form across helpers, grep-able via `***@`
return f"redis://***@cache:6379/0"
return f"postgres://***@db.example.com:5432/app"
return f"mysql://***@host:3306/db"

# DO NOT — strip userinfo (audit cannot find it) / partial mask (leaks username)
return f"redis://cache:6379/0"     # WRONG: userinfo stripped, audit grep misses
return f"redis://user:***@cache:6379/0"  # WRONG: leaks username
```

## Rule 7 — Bulk Op WARN: Source Audit

Source audit (kailash-py): `packages/kailash-dataflow/src/dataflow/nodes/bulk_create.py::BulkCreate._handle_batch_error()` had `except Exception: continue` with zero logging. `BulkUpsert` used `print()` instead of a structured logger. A bulk op returning `failed: 10663` produced no WARN line in the log pipeline; alerting never fired.
