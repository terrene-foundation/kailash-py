---
paths:
  - "**/*.py"
  - "**/*.rs"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
---

# Observability Rules

If a code path is not logged, it does not exist. Post-deployment integration failures are almost always failures to observe what was already broken in dev. Logs are not a debugging convenience — they are the contract that lets the next session know what happened.

## Mandatory Log Points

Every code change MUST emit a structured log line at each of these junctures. No exceptions.

### 1. Endpoints (HTTP, RPC, MCP, CLI commands)

Entry, exit, and error paths each get a log line. Entry captures intent; exit captures outcome and latency; error captures stack and trace ID.

```python
# DO
@router.post("/users")
async def create_user(req: CreateUserRequest):
    logger.info("create_user.start", route="/users", request_id=req.request_id)
    t0 = time.monotonic()
    try:
        user = await db.express.create("User", req.fields())
        logger.info("create_user.ok", user_id=user["id"], latency_ms=(time.monotonic()-t0)*1000)
        return user
    except Exception as e:
        logger.exception("create_user.error", error=str(e), latency_ms=(time.monotonic()-t0)*1000)
        raise

# DO NOT
@router.post("/users")
async def create_user(req: CreateUserRequest):
    return await db.express.create("User", req.fields())  # zero observability
```

**Why:** Without entry+exit+error logs, every production failure becomes a guess about which step failed. The first 30 minutes of any incident are spent recreating what the logs should have already captured.

### 2. Integration Points (outbound HTTP, DB, message queue, file IO, third-party SDKs)

Every cross-boundary call MUST log intent (what + where) and result (status + duration). This applies whether the call is real, mocked, or against a fake backend.

```python
# DO
logger.info("stripe.charge.start", customer_id=cid, amount_cents=amount)
resp = await stripe.charges.create(customer=cid, amount=amount)
logger.info("stripe.charge.ok", charge_id=resp.id, latency_ms=resp.elapsed_ms)

# DO NOT
resp = await stripe.charges.create(customer=cid, amount=amount)  # silent integration
```

**Why:** Outbound calls are where 80% of post-deploy failures live (auth changes, schema drift, network policy). Without logs at the boundary, you can't tell whether your code or the dependency failed.

### 3. Data Calls — Real, Fake, or Simulated

Every data fetch MUST log the source mode in the log line itself. This is non-negotiable. The mode field lets `grep mode=fake` find every place a fake was left in code.

```python
# DO — real
logger.info("user.fetch", user_id=uid, source="postgres", mode="real")

# DO — fake (during dev only; presence in prod logs is itself a violation)
logger.warning("user.fetch", user_id=uid, source="fixture", mode="fake")

# DO NOT
user = await fetch_user(uid)  # is this real? fake? cached? no one knows
```

**Why:** "Mock data shipped to prod" is a recurring incident class. A `mode=fake` field in every data-call log line turns a silent disaster into a single grep.

### 4. State Transitions, Auth Events, Config Loads

INFO level, once per transition. Auth events (login, logout, permission grant/revoke) MUST log subject, action, and outcome. Config loads MUST log which file/env var was used.

```python
# DO
logger.info("auth.login.ok", user_id=uid, method="password")
logger.info("config.loaded", source=".env", keys_loaded=len(loaded))

# DO NOT
# (no log at all — auth state changes invisible to ops)
```

**Why:** Auth failures and config drifts are the second-most-common production incidents and are nearly impossible to diagnose without their own log lines.

## MUST Rules

### 1. Use the Framework Logger — Never `print`

`print()`, `console.log()`, `eprintln!`, `puts` are BLOCKED in production code. MUST use the framework's structured logger (see variant rules for the per-language binding).

**Why:** `print` writes unstructured strings to stdout with no level, no field tagging, and no log routing. It cannot be filtered, aggregated, or shipped to a log aggregator, and it disappears the moment the process restarts.

### 2. Correlation ID on Every Log Line

Every log line in a request/handler/agent execution MUST carry a correlation ID (request_id, trace_id, run_id) bound for the entire scope of that execution. Use the framework's context propagation (contextvars, AsyncLocalStorage, span context).

```python
# DO
logger = structlog.get_logger().bind(request_id=req.headers["x-request-id"])
logger.info("step.1.start")
logger.info("step.2.start")

# DO NOT
logger.info("step.1.start")  # no request_id — cannot reconstruct request flow
```

**Why:** Without correlation IDs, multi-step requests interleave in logs and become impossible to trace. A log without a correlation ID is a sentence without a subject.

### 3. Log Levels Have Distinct Meanings

| Level | When                                                                            |
| ----- | ------------------------------------------------------------------------------- |
| ERROR | The operation failed and a user/caller will see the failure                     |
| WARN  | The operation succeeded but used a fallback, retry, or degraded path            |
| INFO  | A normal state transition the operator should be able to see in production      |
| DEBUG | Step-by-step detail useful only during a specific investigation; off by default |

**Why:** When everything is INFO (or everything is ERROR), filters become useless and real incidents drown in noise. The level field is the operator's most important triage tool.

### 4. Never Log Secrets, Tokens, or PII

See `rules/security.md` § "No secrets in logs". The same rule applies to structured log fields — redact tokens, never log raw credentials.

### 5. Log Triage Gate — Read Before Reporting Done

Before any of `/implement`, `/redteam`, `/deploy`, `/wrapup` reports complete, MUST scan for WARN+ entries and acknowledge each one.

**Concrete scan commands** (run all that apply to the project):

```bash
# Test runner output (most recent run)
pytest --tb=short 2>&1 | grep -iE 'warn|error|deprecat|fail' | sort -u

# Project log directory (any *.log file modified in the last 2 hours — proxy for "this session")
find . -name "*.log" -mmin -120 -exec grep -HnE 'WARN|ERROR|FAIL' {} +

# Build tool output
npm run build 2>&1 | grep -iE 'warn|error' | sort -u
cargo build 2>&1 | grep -iE 'warning|error'

# Dependency resolver
pip check 2>&1
npm ls --all 2>&1 | grep -iE 'missing|warn|err'
```

**Disposition protocol** (per unique entry, not per occurrence):

1. Group identical WARN+ entries: same source file + same message pattern = one entry. Count occurrences but state disposition once.
2. For each unique entry, state one of:
   - **Fixed** — root cause addressed in this session, with the commit SHA
   - **Deferred** — explicit reason + tracked todo + human acknowledgment
   - **Upstream** — third-party deprecation that requires a dependency update; opened upstream issue or pinned version with reason
   - **False positive** — explanation of why it does not apply
3. Unacknowledged WARN+ entries BLOCK the gate.

**Exception:** Hooks and cleanup paths where failure is expected may emit WARN entries that are pre-acknowledged in code via a comment marker. Same carve-out as `zero-tolerance.md` Rule 3.

**Why:** Logs that no one reads are worse than no logs at all — they create the illusion of observability while letting the underlying problem fester. Without dedup, a 200-warning test run becomes 200 disposition lines and the agent rationally skips the gate; with dedup, it becomes 5–10 unique entries that are tractable.

### 6. Bulk Operations MUST Log Partial Failures at WARN

Any bulk operation (BulkCreate, BulkUpdate, BulkDelete, BulkUpsert) that catches per-row exceptions MUST emit at least one WARN-level log line when `failed > 0`, including: operation name, total rows, failure count, and a sample error. Exception handlers in bulk ops MUST NOT use `except Exception: continue` or `except Exception: pass` without a WARN log.

```python
# DO — WARN on partial failure
if failed_count > 0:
    logger.warning(
        "bulk_create.partial_failure",
        attempted=total, failed=failed_count,
        first_error=str(errors[0]) if errors else "unknown",
    )

# DO NOT — silent swallow (confirmed absent in kailash-py bulk_create.py:496-498)
except Exception:
    continue  # zero logging, zero signal
```

**Why:** Source audit confirmed: `BulkCreate._handle_batch_error()` has `except Exception: continue` with zero logging; `BulkUpsert` uses `print()` instead of a structured logger. A bulk op returning `failed: 10663` with no WARN line is invisible to alerting pipelines. See 0052-DISCOVERY §2.1 and `guides/deterministic-quality/06-observability-primitives.md` §2.

**BLOCKED responses:**
- "The caller will see the return value, no log needed"
- "We return a failure list, that's enough"
- "We already log at DEBUG"

## MUST NOT

- **No log-and-continue on caught exceptions without action.** If you catch an exception, log it AND either retry, fall back, or re-raise. `logger.error(...); pass` is BLOCKED — same class as `except: pass` in `rules/zero-tolerance.md` Rule 3. **Exception:** hooks and cleanup paths where failure is expected — log at WARN and continue, same carve-out as `zero-tolerance.md` Rule 3.

**Why:** Logging an exception and discarding it produces a paper trail of failures that nothing acts on, creating the worst of both worlds: noisy logs and broken behavior.

- **No log-spam in hot loops.** Per-iteration INFO inside a tight loop floods aggregators and increases bills. Use sample-rate logging or aggregate to one summary line per N items.

**Why:** A 1M-row processing loop emitting one INFO per row produces 1M log lines per run, which both costs money in the aggregator and crowds out the real signal from other components.

- **No unstructured `f"..."` log messages.** Pass fields as keyword arguments to the structured logger, never f-string-interpolate them into the message.

```python
# DO
logger.info("user.created", user_id=uid, plan=plan)

# DO NOT
logger.info(f"User created: {uid} on {plan}")  # cannot filter, cannot aggregate
```

**Why:** F-string-interpolated log messages cannot be queried by field, which defeats the entire purpose of structured logging — operators must regex-match strings instead of filtering on `user_id`.

- **No silent log-level downgrades.** MUST NOT change a WARN/ERROR to INFO to "clean up" CI output. Fix the root cause or document the suppression in the rule itself.

**Why:** Downgrading log levels to silence noise is a Zero-Tolerance Rule 1 violation in disguise — the failure is still happening, the operator just stops seeing it.
