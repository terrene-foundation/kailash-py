# Delegate Substrate — Security Audit (Step 5, L5_DELEGATED)

**Workspace:** `workspaces/issue-1035-delegate-py`
**Audit scope:** `src/kailash/delegate/` — 7 modules, ~6,000 LOC of trust-substrate code
**Posture:** L5_DELEGATED. **Convergence target:** zero CRITICAL/HIGH unresolved.
**Auditor stance:** skeptical — substrate every regulator argument compiles on.

---

## Summary verdict

The substrate is **defensively engineered** with strong structural primitives (frozen + slots dataclasses, type-discriminated unions, pre-intersection widening checks, hash-tagged log payloads, hmac.compare_digest seam verification, threading-lock-guarded sequence allocation, payload depth/size DoS limits, secrets-grade run_id generation, `is`-check R2 composition gate).

However, the audit surfaces **1 CRITICAL** and **2 HIGH** findings that warrant disposition before the substrate is declared regulator-ready. All three are gaps in disclosed surfaces (README #1147 + S8 roadmap reference them) BUT they are not gated structurally in the code — meaning a downstream consumer reading the public API can be fooled into thinking they have a property the substrate does not deliver.

---

## CRITICAL findings (must fix before merge)

### C1 — No cryptographic signature verification anywhere in `kailash.delegate`

**Files:** `audit.py:337-341, 722-727, 752-763`, `trust.py:721-727`, `types.py:676-681`, `dispatch.py:1411-1430`
**Severity:** CRITICAL
**Class:** "fake encryption" pattern per `zero-tolerance.md` Rule 2.

Every signature field in the substrate (`AuditChainEntry.signature`, `GrantMoment.grant_proof`, `DelegateGenesisRecord.block.signature`, dispatch-time signer return value) is validated for **hex shape only** (128 lowercase hex chars per Ed25519's byte size). **No code path anywhere in `src/kailash/delegate/` performs `ed25519.verify(public_key, signature, payload)`** — `grep -rE "verify_signature|signature\.verify|Ed25519.*verify|nacl\.|cryptography\." src/kailash/delegate/` returns zero matches.

Consequence: a malicious or compromised connector / signer that produces a deterministic 128-hex string (e.g. `hashlib.sha256(payload).hexdigest() * 2`) is structurally indistinguishable at the audit-engine boundary from a real Ed25519 signature. The audit chain claims byte-canonical cross-SDK parity with the rs verifier, but the py-emitted chain's per-entry signatures are NEVER verified within the py substrate — so a `receipts_agree(rs, py)` test that re-presents the chain to a rs verifier would surface the forgery only at the cross-SDK layer, not at any py-internal gate.

**This is precisely the S5 C2-1 "fake encryption" fix's failure mode** — that fix BLOCKED placeholder `"0" * 128` signers at construction, but it did NOT add verification on emission. The shape-only check is necessary but not sufficient: `dispatch.py:1425` rejects sub-32-char signer output but accepts any 128-hex string regardless of cryptographic provenance.

**Proposed remediation (fits one shard budget):**

1. Introduce `kailash.delegate.crypto.Verifier` ABC with `verify(payload: bytes, signature_hex: str, signer_identity: DelegateIdentity) -> None` (raises `AuditChainSignatureError`).
2. Pass a `verifier: Verifier | None` parameter to `AuditChainEngine.__init__`; when present, call `verifier.verify(entry.to_signing_bytes(), entry.signature, entry.signer_delegate_id)` inside the `_emit_lock` critical section BEFORE appending the substrate AuditAnchor.
3. Pass `verifier` parameter to `DispatchSurface.__init__` and `DelegateRuntime.__init__`; R2 composition gate adds `audit_engine._verifier is verifier` check (same `is`-identity guard as the signer check at `runtime.py:830`).
4. Update README #1147 disclosure: the runtime-injectable verifier closes the audit-trail-cryptography gap previously deferred to S8.

**Estimated:** ~250 LOC, 4 invariants (verifier-injected / verifier-shared-via-R2 / verify-before-append / typed-error-on-fail), 2 call-graph hops. Within MUST-4 same-shard fit.

---

## HIGH findings

### H1 — `LifecycleState` (D1) declared but no legal-edge enforcer in the delegate module

**Files:** `types.py:147-194` (LifecycleState enum + LifecycleError class), `dispatch.py:715-716` (only RoleLifecycleState consumed)
**Severity:** HIGH
**Class:** stub-shape-without-implementation per `zero-tolerance.md` Rule 6.

The brief mandates legal-edge enforcement for `LifecycleState`: `Proposed → Instantiated → PostureGraded → Active → Retired → Archived`, with illegal edges (e.g. `Archived → Active`, `Active → Proposed`) raising `LifecycleError`. The `LifecycleState` enum is defined with all six variants and `LifecycleError` carries a `from_state, to_state, expected` shape — BUT `grep -rE "LifecycleState\.|LifecycleError" src/kailash/delegate/` shows the enum is **only imported, never consumed**:

- `dispatch.py` uses only `RoleLifecycleState` (a sibling enum on the Role, not the Delegate's lifecycle).
- `runtime.py` enforces a separate `TAODState` machine (`initiated → thinking → acting → observing → deciding → completed`) which is the per-execute() lifecycle, NOT the Delegate-spine D1 lifecycle.

Consequence: a downstream consumer that sets `delegate.lifecycle = LifecycleState.ARCHIVED` and later transitions back to `LifecycleState.ACTIVE` (legitimately or via attribute-replacement bypass) gets no error from the delegate substrate. The `LifecycleError` class is documented in `types.py:166-194` as "Raised for illegal lifecycle transitions BEFORE any audit write" — but no code in the package raises it. A regulator reading the audit-chain documentation will assume the D1 chain is enforced; in fact only RoleLifecycleState's DRAFT/ACTIVE allowlist at dispatch time is enforced (which is a different invariant — it gates dispatch, not the spine's own lifecycle).

**Remediation:** add `LifecycleState.advance_to(next: LifecycleState) -> LifecycleState` (mirroring `TAODState.advance_to`) with a `_LEGAL_LIFECYCLE_SUCCESSORS` frozen-map constant enforcing the six-edge chain. Wire it into wherever the delegate-spine lifecycle is set (currently nowhere — this is the gap). Fits one shard (~150 LOC + tests).

### H2 — Cascade-as-authorization is structurally degenerate ("any cascade reference is authorization")

**Files:** `trust.py:368-381` (trust-boundary docstring), `trust.py:428-463` (`register_root_grantee` has no access-control gate), `trust.py:599-611` (`cascade_child` does not require parent_identity pre-registration), `trust.py:475-624` (no verification of `grant_proof` signature)
**Severity:** HIGH
**Class:** documented gap with security-critical blast radius; named in code comments as "the trust boundary is the cascade reference itself."

`register_root_grantee` accepts ANY caller holding a cascade reference — and `cascade_child` does NOT require `parent_identity.delegate_id` to be pre-registered before registering BOTH parent and child. Combined with `grant_proof` being **shape-only** validated (128 hex chars; no `Ed25519.verify` per C1), this means any caller that constructs `TenantScopedCascade.for_tenant("victim")` and holds a reference can:

1. Call `register_root_grantee(attacker_identity)` — no signature, no audit event.
2. Call `cascade_child(parent_envelope=p, child_envelope=child, parent_identity=victim, child_identity=attacker, ..., grant_proof="ab"*64)` — registers `victim.delegate_id` AND `attacker.delegate_id` even though no real grant from victim ever occurred.
3. Construct a `DispatchSurface` audited as `victim` (the H1 closure check at `dispatch.py:959` passes because `attacker.delegate_id` is now in `cascade.grantees`).

The README #1147 disclosure documents this is "the durable-attestation roadmap", but the runtime **claims** in `trust.py:350-359` to "close PR #1144 holistic /redteam HIGH finding H1" via the grantee registry. In practice, the registry has no cryptographic seeding gate, so the closure is nominal only.

**Remediation (one shard, ~300 LOC):**

- `register_root_grantee` takes a signed `RootGrantAttestation` carrying `(cascade_id, delegate_id, sovereign_signature)`; verifier (C1) verifies before registration.
- `cascade_child` requires `parent_identity.delegate_id in self.grantees` BEFORE step 4; rejects with `DispatchCascadeViolationError` if absent (forces the cascade chain to start from a properly-registered root).
- `grant_proof` is verified via the C1 verifier against `to_signing_bytes()` of the GrantMoment-pre-cascade-id payload signed by `parent_identity`.

---

## MEDIUM findings

### M1 — `_consumed` flag is `bool`-mutable on a non-frozen class (TOCTOU narrow window)

**File:** `runtime.py:1021, 1224`
The `DelegateRuntime._consumed` single-shot guard at `runtime.py:1209-1215` runs OUTSIDE an asyncio lock; two concurrent `execute()` calls on the same runtime object can both pass the `if self._consumed:` check before either sets `self._consumed = True` in the `finally`. The window is small (two `await` boundaries) but real. Remediation: wrap consumption in an `asyncio.Lock`, or use `asyncio.Event` to atomically flip.

### M2 — `to_canonical_dict` for `DelegateGenesisRecord` includes signature; signing-vs-canonical split incomplete

**File:** `types.py:700-718, 720-736`
`to_signing_dict` excludes the signature (correct, F7), BUT `to_canonical_dict` calls `to_signing_payload()` (the substrate's pre-signature method) and then appends `signature` + `signature_algorithm`. Verifiers re-presenting the canonical dict for hash-chain previous-hash recomputation include the signature in the chain hash. Audit-chain `_compute_previous_hash` at `audit.py:843-855` does `canonical_json_dumps(prior.to_canonical_dict())` — including the signature — which IS what cross-SDK expects, but means a signature-only mutation (replacing one valid signature with a different valid signature) breaks chain integrity. This is correct for tamper detection but may surprise consumers expecting signature-independent hash chains. Document the convention; no code change.

### M3 — `_check_payload_depth` lacks set support; depth limit can be bypassed via custom container

**File:** `dispatch.py:103-116`
The recursive depth check enumerates `dict`, `list`, `tuple` only. A custom collection (or a `set` of dicts, though sets are not JSON-serializable so the bypass is theoretical) would skip the check. Low-impact today; harden by switching to `isinstance(obj, (dict, list, tuple, set, frozenset))` for completeness.

### M4 — `_tenant_id_hash` uses unsalted SHA-256; small-tenant-set rainbow attack feasible

**File:** `trust.py:101-112`
The 8-char hex prefix of unsalted `sha256(tenant_id)` is rainbow-table reversible for short or guessable tenant IDs (e.g., "tenant-1" through "tenant-9999"). A log-aggregator-readable attacker can match `parent_tenant_hash` in `CascadeTenantViolationError` messages back to the raw tenant IDs by precomputing the hash table. Remediation: HMAC with a per-deployment key from `os.environ["KAILASH_TENANT_HASH_KEY"]`. Low priority because tenant IDs are not credentials.

---

## LOW findings

- **L1** — `secrets.token_bytes(16)` in `with_posture`'s `rotation_id` at `runtime.py:1129` uses `uuid.UUID(bytes=..., version=4)` but does NOT set the variant bits (compare with `_generate_run_id` at `runtime.py:844-860` which does). The resulting UUID has the version nibble correct but the variant nibble is whatever the random bytes produced. Cosmetic — UUIDs still unique — but inconsistent.
- **L2** — `DelegateGenesisRecord.__post_init__` at `types.py:689-690` snapshots the substrate block via `dataclasses.replace(self.block)`. If the block has mutable nested fields (e.g., a list of capabilities), they share references with the original. Check substrate `GenesisRecord` for deep-immutability before assuming snapshot is structural.
- **L3** — `CapabilitySet.intersect` at `types.py:450-468` is documented "order-stable: preserve order from self". This is a structural contract worth a unit test asserting `tuple(intersect(a, b).capabilities) == tuple(c for c in a if c in set(b))`.

---

## PASSED CHECKS (verified clean)

1. **Envelope monotonicity (D5):** `envelope.py:142-170` `tighten_with` performs PRE-intersection widening check via `is_tighter_than` on the OPPOSITE direction; `intersect`'s silent `min()` squashing cannot mask widening attempts. The only widening constructor is `from_genesis` gated on a `DelegateGenesisRecord`. Frozen + slots blocks attribute mutation.
2. **Tenant isolation (Option A):** `trust.py:553-560` `cascade_child` checks `child_tenant != self.tenant` FIRST, before scope-subset or envelope-tightening checks. `TenantScope` is a typed 2-variant tagged union — Global is never implicit (no `None`-default).
3. **Audit chain monotonicity (D2 + D7):** `audit.py:773-817` `emit_event` is wrapped in `threading.Lock`-guarded critical section; sequence is `len(self._entries)`, previous_hash is recomputed from prior entry's canonical JSON via `_compute_previous_hash`. Genesis (seq=0) requires empty previous_hash; non-genesis requires non-empty 64-hex SHA-256.
4. **No silent fallbacks:** Every `except` in delegate/ either re-raises a typed error, propagates verbatim, or wraps in a more-specific typed error. Zero bare `except: pass` or `except Exception: return None`.
5. **No secrets in logs:** Zero `logger.{info,debug,warning,error}` calls in `delegate/` emit signatures, salts, private keys, tokens, or raw tenant IDs. Hash-prefix tokens used per `observability.md` MUST Rule 8.
6. **Path-traversal / null-byte rejection on identity refs:** `types.py:298-311` `DelegateIdentity.__post_init__` routes every externally-sourced ref through `kailash.trust._locking.validate_id` per `trust-plane-security.md` MUST Rule 2.
7. **CSPRNG run_id generation:** `runtime.py:844-860` `_generate_run_id` uses `secrets.token_bytes(16)` (not `random`), sets UUID v4 + RFC 4122 variant bits correctly.
8. **HMAC compare_digest:** `audit.py:577` `WitnessedCrossAnchor.verify_seam` uses `hmac.compare_digest`, not `==`, for the salted-digest comparison. Module-top import (not in-method).
9. **Frozen on security-critical dataclasses:** every dataclass in `types.py`, `envelope.py`, `trust.py`, `audit.py` uses `frozen=True` (and most also `slots=True` — `TenantScopedCascade` justifies its non-slots in a docstring per #1146 H1 mutable grantee registry).
10. **`from_dict` validates all fields:** every `from_dict` classmethod (Identity, Envelope, TenantScope, ConnectorInvocationResult, DispatchResult, TAODState, RuntimeExecutionResult) validates field presence + type + structural constraints before construction. Missing fields raise typed errors; bare `KeyError` does not surface.
11. **R2 composition `is`-identity gate:** `runtime.py:783-836` `R2Composition.validate` uses `is` checks (not `==`) for envelope / cascade / signer identity. A value-equal-but-distinct substitution is caught.
12. **DoS payload limits:** `dispatch.py:99-100, 1216-1235` enforces 32-deep nesting + 1 MiB serialized-byte limits BEFORE per-field type checks. Refuses with `DispatchValidationError`.
13. **Bool-vs-int type-confusion:** `dispatch.py:1298-1313` explicitly rejects `bool` for int-declared fields (`isinstance(True, int) is True` trap closed).
14. **External-side-effect requires audit:** `dispatch.py:1359-1365` rejects `result.external_side_effect=True` with empty `audit_events` per zero-tolerance "fake-dispatch class".
15. **Audit-visibility classifier:** `audit.py:730-737` rejects non-allowlisted event types (REASONING_SCRATCHPAD excluded); allowlist is the structural defense — literal-equality check would silently admit future private variants.
16. **Posture-rotation audited before applied:** `runtime.py:1116-1155` emits POSTURE_OR_SOVEREIGN_HANDOVER audit BEFORE constructing the new runtime; emission failure refuses the rotation.
17. **Single-shot runtime:** `runtime.py:1204-1224` `_consumed` flag (with M1 narrow-window caveat) prevents retry-until-success amplification.
18. **Cascade salt-entropy floor:** `audit.py:541-548` rejects ≤2-unique-byte salts (all-zero, all-one, repeating-byte patterns).
19. **`principal_kind` G1 discriminator:** `dispatch.py:899-937` rejects service-account binding to sovereign-only role at bind AND re-validates at dispatch.
20. **No `eval()` / `exec()` / `subprocess(shell=True)`:** grep clean.
21. **No SQL string concatenation:** delegate substrate is in-memory only; no DB queries.
22. **No XSS / `innerHTML` / template injection:** no HTML rendering.

---

## Recommendations

1. **C1 MUST land before convergence.** The hex-shape-only signature check is the load-bearing failure mode for the substrate's entire audit-cryptographic claim. Until a verifier is wired, the substrate is "structurally signed" but not "cryptographically signed". Same shard.
2. **H2 SHOULD land with C1.** The cascade-as-authorization gap is C1's downstream consequence — once C1 lands, register_root_grantee can require a signed RootGrantAttestation via the same verifier. Co-shipping closes both gaps with one verifier abstraction.
3. **H1 is independent.** Add LifecycleState enforcement in a separate shard; the gap is real but does not amplify C1/H2.
4. **MEDIUM/LOW findings** can be queued for next iteration; none block regulator readiness once C1+H2 land.

**Convergence verdict:** **NOT YET CONVERGED.** C1 + H2 are blockers under L5_DELEGATED's "zero CRITICAL/HIGH" gate. Both fit one shard each (or one combined ~500 LOC shard).
