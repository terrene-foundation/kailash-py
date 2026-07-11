# rs handoff — BH5 governance circuit-breaker (Python reference)

Status: **READY** — the Python SDK is the Foundation reference; the Rust SDK
mirrors these exact semantics + byte forms (EATP D6: independent implementation,
matching semantics / byte-identical cross-verification).

BH5 (issue #1510 acceptance criterion): a **first-class governance
circuit-breaker control (anti-runaway / rate) with matching py↔rs semantics**.
SAFR v1.0 (§ Controls Repository — Rate Limits) is a non-binding white paper —
derive with "specifies/recommends", never "requires".

> If the Rust SDK has already pinned divergent breaker semantics or an
> operational-envelope field order, flag for reconciliation BEFORE either side
> pins — the two MUST match for cross-verification (EATP D6).

---

## 1. What BH5 adds (Python reference)

The **rate** half already existed as a first-class control (`RateLimitEnforcer`,
a stateful sliding-window limiter at verify-action Step 3.5). BH5 adds the
**trip-and-hold breaker** the rate limiter is not: a limiter blocks per-window
but re-admits the instant the window slides; a breaker trips after repeated
breaches and HOLDS the `(role, action)` blocked through a cooldown.

`PactCircuitBreaker` — a per-`(role, action)` three-state machine, consulted at
verify-action **Step 3.7**, composed monotonically (tighten-only, can only
escalate a verdict):

- **CLOSED** → normal. A breach (the underlying held/blocked leaf outcome)
  appends to a sliding failure window of `circuit_window_seconds`. When the
  window holds `circuit_failure_threshold` breaches → **OPEN**.
- **OPEN** → blocks the key. While `now - opened_at < circuit_cooldown_seconds`
  every call on the key is BLOCKED (fail-closed hold). After the cooldown →
  admit exactly one probe → **HALF_OPEN**.
- **HALF_OPEN** → one probe in flight; concurrent calls are blocked. Probe
  succeeds (leaf outcome not held/blocked) → **CLOSED** (reset). Probe fails →
  **OPEN** (fresh cooldown).

Security invariants (each pinned by a py test, mirror them):

1. Fail-closed: malformed config / non-finite `now` → error → BLOCKED
   (never fail-open). `math.isfinite` on window/cooldown/now; threshold ≥ 1.
2. Bounded memory that NEVER evicts an OPEN/HALF_OPEN key (evicting a tripped
   key would reset it = fail-open); at the cap, reclaim only closed+expired
   keys, else REFUSE the new key (fail-closed capacity block).
3. Thread-safe: the whole check-then-record is one critical section.
4. Leaf-scoped breach signal: the breach fed to `record()` is the pre-Step-3.7
   underlying outcome, so the breaker never counts its OWN block (no
   self-feedback) — and, by construction, ancestor-verify / knowledge-access
   denials do not accumulate toward a trip (no exposure; those are blocked every
   call regardless).

## 2. Conformance vectors (byte-pinned, py-canonical)

Two vectors are pinned in `PACT_VECTORS.sha256` (`shasum -a256 -c` from the
vectors dir; the same check CI's cross-sdk-interop gate runs):

- `circuit_breaker.json` — drives `PactCircuitBreaker.check`/`record` through
  trip-threshold, OPEN-blocks, cooldown→HALF_OPEN, probe-success→CLOSED,
  probe-fail→reOPEN, and fail-closed-on-non-finite (the non-finite value is
  injected at runtime via an `inject_nonfinite` marker — no non-finite literal
  in the JSON, per the signing-pre-image non-finite rule).
- `rate_limit_enforcement.json` — pins the previously-vector-less
  `RateLimitEnforcer` sliding-window tally→breach + capacity-refusal semantics.

Mirror these exact event sequences and expected `(level, state, was_probe)`
outcomes on the Rust side.

## 3. Enforcement-surface parity (MUST — matches py)

The breaker fields live on the operational envelope beside the rate fields, so
BOTH enforcement surfaces MUST learn the new fail-closed dimension in lockstep,
sharing ONE restrictiveness model:

- **Eval-time intersection** (`_intersect_operational`): carry the TIGHTER
  breaker into the effective envelope (lower threshold OR longer window OR longer
  cooldown = tighter; None = widest = no breaker).
- **Re-registration / monotonic-tightening validator**: a child/re-registration
  that STRIPS a parent breaker (→ None) or LOOSENS it (raise threshold / shorten
  window / shorten cooldown) MUST be REJECTED as a widening. An unrecognized
  value ranks TIGHTEST (fail-closed). Skipping this on the Rust side lets a
  re-registration silently strip the gate — the #1456-class privilege escalation.

## 4. Signed-envelope backward compatibility (MUST — byte contract)

The breaker fields are NEW on the operational envelope, which is the signed
`SignedEnvelope` pre-image. To keep every pre-BH5 / breaker-less / cross-SDK
signed envelope verifiable (the same backward-compat contract BH3 used for its
trace unbound form), **an UNSET breaker field contributes ZERO bytes to the
signing pre-image**:

- **Breaker-LESS envelope** → the three `circuit_*` fields are pruned from the
  signing pre-image → **byte-identical to the pre-BH5 form**. Nothing changes
  for the Rust side here: a breaker-less envelope signed by rs verifies under py
  and vice-versa, unchanged. This half is byte-neutral — no lockstep needed.
- **Breaker-CONFIGURED envelope** → the three fields are present in the signing
  pre-image (cryptographically bound; cannot be silently stripped). For these
  NEW opt-in envelopes to cross-verify, the Rust SDK MUST (a) add the same three
  operational fields, (b) apply the SAME conditional exclusion — prune them from
  the signing pre-image only when unset — and (c) emit them in the same
  sorted-key positions with matching JSON number typing: `circuit_failure_threshold`
  as an int (`5`), `circuit_window_seconds` / `circuit_cooldown_seconds` as floats
  (`60.0` / `300.0`); the keys sort ahead of `max_actions_*`
  (`circuit_cooldown_seconds`, `circuit_failure_threshold`, `circuit_window_seconds`).
  Only the breaker-CONFIGURED case is a coordinated
  lockstep; verify the rs mirror is landed before any release where the two
  SDKs cross-verify signed _breaker-configured_ envelopes.

Note: `envelope_version` (the engine's version hash) is NOT affected — it hashes
contributor identifiers, not envelope content. Only the Ed25519 sign/verify
pre-image is in scope.

## 5. Field reference

`OperationalConstraintConfig` gains (all `int|float|None`, default None):
`circuit_failure_threshold` (int ≥ 1), `circuit_window_seconds` (float > 0),
`circuit_cooldown_seconds` (float > 0). All three set → breaker active; all None
→ inactive (the conformance/validator restrictiveness model treats partial as an
error — all-or-nothing).
