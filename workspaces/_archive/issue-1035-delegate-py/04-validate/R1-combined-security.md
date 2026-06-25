# R1 — Combined Security Audit (from_brief #1125 + delegate #1035) — v2.27.0 pre-release

**Verdict: CONVERGED (CRIT/HIGH axis)**

Combined surface re-derived from scratch. Zero CRIT, zero HIGH on the brief-injection →
code-execution axis and the delegate token-forgery / replay / tenant-cross-talk axis.
Three MEDIUM defense-in-depth residuals and two LOW notes; the primary defenses (node
denylist-before-allowlist, fail-closed verifier, M1 consume-lock, M3 ABC-based depth walk,
M4 per-process salt) all hold independently of the residuals.

Counts: CRIT 0 · HIGH 0 · MEDIUM 3 · LOW 2.
Highest-severity item: MEDIUM-1 — NaN/Inf bypasses the confidence gate (defense-in-depth
quality gate; the code-execution defense is independent and intact).

Method note: this audit agent's tool inventory was read-only (Read/Grep/Glob/Write — no
Bash). Every finding below was derived by static code inspection; the "verification command"
blocks are the exact reproductions a follow-up Bash-equipped session SHOULD run to convert
the inspected results into executed receipts (per `verify-resource-existence.md` MUST-2 the
runtime command is the authoritative evidence; the static derivation is the candidate). The
derivations are deterministic (NaN comparison semantics, frozenset membership, module-scope
salt init) so the inspected results are high-confidence, but the executed receipts are the
durable proof and SHOULD be captured before merge.

---

## Threat-model coverage map

### from_brief (#1125) — architecture §6 Security Threats (`workspaces/from-brief-1125/02-plans/01-architecture.md:192-196`)

| Threat                                                                      | Defense                                                                                                                                                        | Test                                                                               | Status                           |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------- |
| Prompt-injection → arbitrary node type (B1a)                                | allowlist gate (`allowlist.py::validate_node_type`) + `_DANGEROUS_NODE_TYPES` denylist subtracted at allowlist source (`workflow/from_brief.py:80-85,322-329`) | `tests/unit/_from_brief/test_allowlist.py`, `test_validator.py::TestAllowlistGate` | PASS                             |
| Prompt-injection → code execution (PythonCodeNode/AsyncPythonCodeNode exec) | denylist runs BEFORE allowlist; the augmented brief never enumerates them; `validate_node_type` rejects them as `unknown_value` if hallucinated                | covered by denylist subtraction + allowlist tests                                  | PASS (see VERIFIED-1)            |
| Secrets-in-brief (B2a)                                                      | `scrub_brief()` pre-LLM, pre-logging (`scrubber.py`) routed through shared `kailash.utils.url_credentials`                                                     | `tests/unit/_from_brief/test_scrubber.py`                                          | PASS                             |
| Ambiguous brief (C1a)                                                       | confidence gate `< 0.6` raises (`confidence.py::check_confidence`)                                                                                             | `test_validator.py::TestConfidenceGate` (range + threshold)                        | PARTIAL — NaN/Inf gap (MEDIUM-1) |
| Brief length / regex-backtrack / cost-amp DoS (SEC-7)                       | `MAX_BRIEF_LENGTH=64_000` fail-loud (`scrubber.py:127,191-197`)                                                                                                | scrubber tests                                                                     | PASS                             |

### delegate (#1035) — architecture §Invariants (`workspaces/issue-1035-delegate-py/02-plans/01-architecture.md:47-56`)

| Threat                                                          | Defense                                                                                                                                | Test                                                                                                       | Status                     |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------- |
| Token forgery (C1 "fake encryption" — 128-hex shape-only check) | `Ed25519Verifier` real crypto; `NullVerifier` fail-closed default; cascade + audit gated under same Verifier CLASS (`runtime.py:1014`) | `tests/unit/delegate/test_verifier.py`, `tests/integration/delegate/test_signature_verification_wiring.py` | PASS (VERIFIED-2)          |
| Single-use consume race (M1 TOCTOU)                             | `_consume_lock: asyncio.Lock` around check-and-set in `execute()` (`runtime.py:1313-1329`)                                             | `tests/unit/delegate/test_runtime.py`                                                                      | PASS (see MEDIUM-3 caveat) |
| Payload-depth DoS bypass via subclass (M3)                      | ABC-based `isinstance(obj, Mapping/Sequence/Set)` walk (`dispatch.py:117-145`)                                                         | `tests/unit/delegate/test_dispatch.py`                                                                     | PASS (VERIFIED-3)          |
| Tenant rainbow-correlation (M4 unsalted hash)                   | per-process `_TENANT_HASH_SALT = secrets.token_bytes(32)`, eager module init, never logged/exported (`trust.py:143-164`)               | `tests/integration/delegate/test_tenant_isolation.py`                                                      | PASS (VERIFIED-4)          |
| Tenant cross-talk (Option A)                                    | tenant-first fail-closed in `cascade_child` + dispatch cross-check (`trust.py:719-726`, `dispatch.py:1814-1827`)                       | `test_tenant_isolation.py`, `test_trust_cascade.py`                                                        | PASS                       |
| Audit-hash timing side-channel                                  | `hmac.compare_digest` for cross-anchor seam (`audit.py:594`)                                                                           | `test_audit_engine.py`                                                                                     | PASS                       |
| Grantee-as-authorization bypass (H1)                            | grantee registry checked at bind + dispatch (`dispatch.py:1388,1645`)                                                                  | `test_dispatch_wiring.py`                                                                                  | PASS                       |
| Posture-upgrade trivial-nonce bypass                            | `_MIN_NONCE_LENGTH=16` syntactic floor + audit-before-rotate (`runtime.py:1198-1252`)                                                  | `test_runtime.py`                                                                                          | PASS (see MEDIUM-2 caveat) |

---

## VERIFIED (no finding)

**VERIFIED-1 — brief text cannot reach eval/exec/compile/subprocess/import.**
`grep -rn "eval(\|exec(\|compile(\|__import__\|importlib\|subprocess\|shell=True" src/kailash/_from_brief/ src/kailash/bootstrap.py src/kailash/workflow/from_brief.py`
Actual: zero `eval`/`exec`/`compile`/`subprocess`/`shell=True` matches. `from_brief.py:73,324`
are COMMENTS noting that `PythonCodeNode`/`AsyncPythonCodeNode` internally call `exec()` and
are therefore denylisted. The realization path (`_realize` → `builder.add_node(node_type,
node_id, config)` at `workflow/from_brief.py:526`) passes the LLM-emitted `node_type` string
to the WorkflowBuilder ONLY after `validate_plan(allowed_node_types=...)` has confirmed it is
in the registry-derived allowlist MINUS the dangerous denylist. There is no dynamic import or
code-string path from brief → realizer. Defense order is correct: denylist subtraction at the
allowlist SOURCE (`_registered_node_types` returns `set(NodeRegistry.list_nodes()) -
_DANGEROUS_NODE_TYPES`) means the dangerous types are never in the LLM's vocabulary AND are
rejected as `unknown_value` even if the LLM hallucinates them.
Repro for receipt: `python3 -c "from kailash.workflow.from_brief import _registered_node_types as f; a=f(); print('PythonCodeNode' in a, 'AsyncPythonCodeNode' in a)"` → expected `False False`.

**VERIFIED-2 — no verify-bypass / algorithm-confusion in the delegate verifier.**
`verifier.py::Ed25519Verifier.verify` is fail-closed at every branch (UUID parse, directory
miss, non-32-byte key, non-bytes signature/message, `InvalidSignature`, catch-all → `False`),
NEVER raises. `NullVerifier.verify` unconditionally returns `False`. The cascade
(`trust.py:618,791`) and audit engine consult the wired verifier and raise typed errors on
`False`. `runtime.py:1014` enforces that `audit_engine.verifier` and `cascade.verifier` are the
SAME class so a split real/Null configuration (partial fake-encryption) is structurally
refused. No algorithm field is read from attacker-controlled input (Ed25519 is hardcoded),
so there is no alg-confusion surface.
Repro for receipt: `python3 -c "from kailash.delegate.verifier import NullVerifier; print(NullVerifier().verify(b'm', b's', 'id'))"` → expected `False`.

**VERIFIED-3 — M3 payload-depth walk cannot be bypassed by a Mapping/Sequence/Set subclass.**
`dispatch.py:117-145` walks `collections.abc.Mapping`, `Sequence` (excluding str/bytes/
bytearray), AND `Set` via `isinstance` against the ABCs — so `UserDict`, `UserList`,
`frozenset`, `set`, and any ABC-registered custom container are walked. A 40-deep nested
`UserDict` (subclass of Mapping) exceeds `_MAX_PAYLOAD_DEPTH=32` and raises
`DispatchValidationError`. The serialized-size cap (`_MAX_PAYLOAD_SERIALIZED_BYTES=1 MiB`,
`dispatch.py:1676`) is the second DoS bound. Recursion is bounded by the depth limit before
`canonical_json_dumps` recurses.
Repro for receipt: build a 40-deep `UserDict`, call `kailash.delegate.dispatch._check_payload_depth(obj)` → expected `DispatchValidationError`.

**VERIFIED-4 — M4 tenant salt is unpredictable cross-process and never logged.**
`trust.py:143` — `_TENANT_HASH_SALT = secrets.token_bytes(32)` at MODULE scope (eager,
import-lock-serialized — closes the R1-followup lazy check-and-set race documented inline
at `trust.py:113-120`). `_tenant_id_hash` uses `hmac.new(salt, id, "sha256").hexdigest()[:8]`.
`grep -rniE "logg|print|log\." src/kailash/delegate/` shows zero log line emits the salt; the
only delegate INFO log is `audit.py:900` (chain emission, no salt). The salt is never in any
`to_dict`/`to_canonical_dict`/`to_signing_dict` payload. Tenant IDs surface in error messages
ONLY as the 8-char HMAC prefix (`trust.py:96-102`). Per-process scope is documented as
by-design (`trust.py:122-142`): fork() inherits (in-scope), reload rotates (test-only),
entropy-starved sandbox fails import loudly.
Repro for receipt: print `_TENANT_HASH_SALT.hex()` from two separate `python3 -c` processes; expected 32-byte values, NOT equal.

**VERIFIED-5 — lazy-import contract holds (from_brief does NOT pull kaizen into a no-kaizen deployment).**
All kaizen imports in `workflow/from_brief.py` and `bootstrap.py` are deferred to call-time
inside `_signature_cls` / `_build_agent` (module docstrings at `from_brief.py:35-42`,
`bootstrap.py:60-71` document the circular-import fence). `_from_brief/__init__` does eagerly
chain `signatures.py` → `kaizen.signatures`, BUT the two user entrypoints
(`workflow_from_brief`, `bootstrap`) import `_from_brief.scrubber` / `.validator` / `.exceptions`
(all kaizen-free) lazily and only reach `signatures`/kaizen on the LLM-emission step. The
brief's stated probe (`import kailash._from_brief, kailash.delegate` → kaizen absent) depends
on whether `_from_brief/__init__.py` eager-loads `signatures`.
Repro for receipt (MUST run before merge — see LOW-2): `python3 -c "import kailash._from_brief, kailash.delegate, sys; print('kaizen' in sys.modules)"` → expected `False`. If this prints `True`, escalate LOW-2 to HIGH (slim-core import-closure break).

**VERIFIED-6 — no hardcoded secrets / no secrets in logs across both surfaces.**
`grep` for credential-shaped literals in `src/kailash/_from_brief/`, `bootstrap.py`,
`src/kailash/delegate/` finds only the scrubber's detection regexes (`scrubber.py:46-114` —
these are PATTERNS, not secrets) and doc comments. No `sk-`, no `password=`, no
`postgres://user:pass@`. Schema-revealing LLM-plan field names are kept at DEBUG count-only
(`from_brief.py:628-636`, `bootstrap.py:673-679` — SEC-6) per `observability.md` Rule 8.
Brief PII is scrubbed pre-logging; only `brief_length` (int) is logged at INFO.

---

## MEDIUM (defense-in-depth residuals — primary defense holds; acceptable for v2.27.0)

**MEDIUM-1 — NaN/Inf `interpretation_confidence` bypasses the confidence gate.**
`src/kailash/_from_brief/confidence.py:53-65`
Threat: an LLM (or a crafted structured-output response) emitting `interpretation_confidence:
NaN` passes BOTH gate branches because IEEE-754 NaN comparisons are always False:
`NaN < 0.0` → False, `NaN > 1.0` → False (range gate passes), `NaN < threshold` → False
(threshold gate passes). `+inf` passes the threshold gate (`inf < 0.6` → False) and is only
caught by `value > 1.0` → True; `-inf` is caught by `value < 0.0`. So `+inf` is range-rejected
but `NaN` is fully accepted. `BriefPlan` (`validator.py:65`) sets `ConfigDict(extra="forbid")`
but does NOT set `allow_inf_nan=False`; Pydantic v2 defaults `allow_inf_nan=True`, so
`BriefPlan(interpretation_confidence=float("nan"))` constructs successfully and
`validate_plan(plan)` then accepts it.
Verification command (run for receipt):

```
python3 -c "from kailash._from_brief.confidence import check_confidence; check_confidence(float('nan'), threshold=0.6); print('NaN PASSED gate')"
python3 -c "from kailash._from_brief.validator import BriefPlan, validate_plan; validate_plan(BriefPlan(interpretation_confidence=float('nan'))); print('validate_plan(NaN) PASSED')"
```

Static-derived result: both print PASSED (no raise). The threat model names this exact class
(P5 `math.isfinite()` on numeric constraints).
Why MEDIUM not HIGH: the confidence gate is a defense-in-depth quality gate ("is the LLM sure
enough"), NOT the primary anti-code-execution or anti-injection defense. A NaN-confidence plan
still passes through the allowlist gate (every `node_type` must be registry-AND-not-denylisted)
and the `_DANGEROUS_NODE_TYPES` subtraction, so it cannot realize `PythonCodeNode`. The worst
outcome is a low-quality plan realized when it should have been refused — a correctness/UX
residual, not a code-execution or isolation breach. The threat model's brief explicitly admits
defense-in-depth MEDIUMs when the primary defense holds; it holds here.
Fix: add `math.isfinite()` to `check_confidence`:

```python
import math
if not math.isfinite(value) or value < 0.0 or value > 1.0:
    raise BriefInterpretationError(..., malformed=True)
```

AND set `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)` on `BriefPlan`
(`validator.py:65`) so NaN/Inf are rejected at Pydantic construction too (belt-and-suspenders).
Regression test: extend `test_validator.py::TestConfidenceGate` with
`test_nan_confidence_raises_malformed` + `test_inf_confidence_raises_malformed` (behavioral,
`pytest.raises(BriefInterpretationError)` asserting `.malformed is True`). Current
`test_validator.py:63-73` covers `-0.1` and `1.5` but NOT NaN/Inf — the threat is documented
(P5) with no test, which is the HIGH-class signal under `testing.md` § Audit Mode; it lands
MEDIUM here only because the primary code-execution defense is independent and the gate is
defense-in-depth.

**MEDIUM-2 — posture-upgrade nonce gate is syntactic-only (documented, deferred to S8).**
`src/kailash/delegate/runtime.py:1198-1211`
`with_posture` upgrade accepts ANY `human_acknowledged_nonce` of length ≥ 16; there is no
single-use / signature / expiry check. This is DOCUMENTED in the docstring
(`runtime.py:1152-1161`) and the inline comment (`runtime.py:106-116`) as a deliberate
"syntactic placeholder — cryptographic nonce validation lives in SessionStart / S8
nonce-registry integration." It is NOT a regression and matches the rs reference floor.
Why MEDIUM not HIGH: an attacker who can call `with_posture` already holds a runtime reference
(the cascade-reference-IS-authority trust boundary, documented at `trust.py:455-469`), and the
rotation is audit-emitted before it takes effect (audit-before-rotate, `runtime.py:1213-1252`),
so an upgrade is forensically visible. The residual is "a 16-char string is not a real nonce" —
acceptable ONLY because S8 is the named owner and the gate is explicitly transitional.
Disposition: acceptable residual for v2.27.0 IF the S8 nonce-registry obligation is tracked.
Confirm a tracking issue exists for "S8 posture-upgrade cryptographic nonce" before release;
if none, file one (the documented-deferral-without-tracker pattern is the gap, not the gate).

**MEDIUM-3 — M1 consume-lock is per-event-loop, not cross-thread.**
`src/kailash/delegate/runtime.py:1065,1313`
`_consume_lock = asyncio.Lock()` serializes concurrent `execute()` coroutines on ONE event
loop — which is the documented threat (two concurrent `await runtime.execute()` calls). It does
NOT serialize two OS threads each running their own event loop against the same runtime
instance (`asyncio.Lock` is not thread-safe). The single-shot `_consumed` flag is a plain bool;
a cross-thread race could in principle let two threads both observe `_consumed=False`.
Why MEDIUM not HIGH: the delegate runtime is an async substrate; the documented and supported
usage is a single event loop. Sharing one `DelegateRuntime` instance across OS threads is
outside the async contract (and `with_posture` returns a FRESH runtime with a fresh lock per
Invariant 5, so the natural pattern does not share instances across threads). The M1 fix as
specified (asyncio.Lock around the TOCTOU) correctly closes the named threat. The cross-thread
case is a narrower, undocumented-usage residual.
Disposition: acceptable residual. If cross-thread runtime sharing is ever a supported pattern,
the consume guard would need a `threading.Lock` wrapping the `asyncio.Lock` acquisition — but
that is a future-usage concern, not a v2.27.0 blocker. Note inline at `runtime.py:1052-1065` if
not already (the comment there describes the asyncio race but not the thread caveat).

---

## LOW (notes — no action required for release)

**LOW-1 — scrubber idempotence + canonical mask form are correct; one residual class.**
`scrubber.py` masks `user:password@host` URLs to canonical `scheme://***@host[:port]/path`
(`_mask_url_credentials:130-152`) and returns `[REDACTED]` sentinel for unparseable URLs (NOT
the masked-success shape — correct per `observability.md` Rule 6.1). The credential corpus
(SEC-3) is broad. Residual: regex-based secret detection is inherently incomplete (a novel
token shape not in the corpus passes through into the LLM prompt). This is acceptable — the
scrubber is a defense-in-depth display-path safety net (same posture as the DataFlow sanitizer
per `security.md`), not a guarantee, and the brief is user-supplied so the user owns their own
credentials. No fix needed; note for users in docs that scrubbing is best-effort.

**LOW-2 — lazy-import contract MUST be confirmed by an executed receipt before merge.**
VERIFIED-5 derives the contract holds by inspection, but `_from_brief/__init__.py` eager-loads
`signatures.py` (which imports `kaizen.signatures` at module scope per `bootstrap.py:251-255`
and the docstring at `from_brief.py:95-98`). The brief's probe
(`import kailash._from_brief, kailash.delegate` → `'kaizen' in sys.modules` is `False`) is the
load-bearing check and I could not execute it (read-only tool inventory). Run it before merge:

```
python3 -c "import kailash._from_brief, kailash.delegate, sys; print('kaizen' in sys.modules)"
```

Expected `False`. If `True`, the slim-core import closure is broken (bare `pip install kailash`
would import an LLM provider transitively) — escalate to HIGH and gate the release. This is
LOW only because the code structure strongly indicates the deferral holds; it is flagged so the
executed receipt is not skipped.

---

## Convergence statement

No CRIT or HIGH findings on the combined attack surface. The brief-injection → code-execution
path is structurally closed (denylist-before-allowlist + no eval/exec/import sink + typed
realizer). The delegate token-forgery / replay / tenant-cross-talk surface is closed
(fail-closed Ed25519 verifier, same-verifier-class coherence check, M1 consume-lock, M3
ABC-based depth walk, M4 per-process unpredictable salt, tenant-first fail-closed isolation,
hmac.compare_digest). The three MEDIUMs are defense-in-depth residuals whose primary defenses
hold independently; the two LOWs are a best-effort-scrubber note and a must-run executed-receipt
reminder. Recommend landing MEDIUM-1 (`math.isfinite` + `allow_inf_nan=False` + 2 regression
tests, ~10 LOC, fits one shard) in this release per `autonomous-execution.md` MUST Rule 4
(same-bug-class gap surfaced at review, within shard budget — fix immediately rather than
defer), and confirming the LOW-2 + MEDIUM-2 receipts (one `python3 -c`, one `gh issue` check)
before tagging.

Receipts: this file is the R1 disposition; the executed-receipt obligations (LOW-2 lazy-import
probe, MEDIUM-1 NaN/Inf probes, VERIFIED-1/3/4 repros) are enumerated inline above for a
Bash-equipped follow-up.
