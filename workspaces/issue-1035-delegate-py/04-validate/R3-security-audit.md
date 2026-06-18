---
type: CONVERGENCE-INPUT
round: 3
agent: security-reviewer
target_ref: ca552101d365408eb1ea713cf196be4b006e166d
session_date: 2026-05-26
parent_pr: 1176
merged_commit: f8c6c5b619b7c25bc4778c87d4bdcca3cd72be83
parent_convergence: R2-convergence.md + 11-post-merge-convergence.md (cycle 2 post-merge)
read_source: git show origin/main:<path> ONLY (working tree is ~30 commits behind under F3 LEAVE-ALONE)
prior_round_status: R2 security-reviewer FALSIFIED-and-discarded (read working tree instead of origin/main)
---

# /redteam Round 3 — Security Audit (post-PR-#1176 merge to origin/main)

## Mission

Verify on origin/main `ca552101d`:

1. #1177 framing (empty-crypto orphan defaults on `Connector.write/read/authenticate`) is still accurate
2. #1178 framing (`Principal(tenant_id=None)` multi-tenant footgun) is still accurate
3. Any NEW HIGH/CRIT findings beyond #1177/#1178
4. Same-bug-class sweep: other unconsumed empty-crypto orphans, other `tenant_id=None` slip surfaces, other concrete defaults from PR #1176 shipping cryptographically-empty objects
5. Verifier subsystem — does `verifier.py` HARD-REJECT empty-signature envelopes today?
6. `hmac.compare_digest` constant-time compare in audit.py + verifier.py
7. `_tenant_id_hash` routing — no raw `tenant_id` bleed in logger calls

---

## Read-source validation

```
$ git -C /Users/esperie/repos/loom/kailash-py rev-parse origin/main
ca552101d365408eb1ea713cf196be4b006e166d
```

Matches the expected anchor. Sample read pipe-through:

```
$ git show origin/main:src/kailash/delegate/dispatch.py | head -5
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportUnnecessaryIsInstance=false
"""Connector ABC + Dispatch surface for ``kailash.delegate`` (S5 of #1035).
```

Confirms `git show origin/main:` read path (NOT working-tree). All findings below are anchored to this read.

---

## #1177 framing-still-accurate table (empty-crypto orphan defaults)

| Acceptance criterion (from #1177)                                                                                                                  | Verification command                                                                                                                                                                            | Outcome                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Connector.write` default emits `SignedActionEnvelope(signature=b"")`                                                                              | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '700,712p'`                                                                                                                    | MATCH — line 706: `signature=b"",  # legacy connector did not sign` (default `write`).                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `Connector.read` default emits `AttestedReadReceipt(attestation=b"")`                                                                              | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '735,745p'`                                                                                                                    | MATCH — line 741: `attestation=b"",` (default `read`).                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `Connector.authenticate` default returns `Principal(tenant_id=None)`                                                                               | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '670,680p'`                                                                                                                    | MATCH — line 675: `tenant_id=None,` inside the default `authenticate` `Principal(...)` constructor.                                                                                                                                                                                                                                                                                                                                                                                                               |
| Defaults are unconsumed orphans in the delegate substrate (the "treat-as-unverifiable" contract is docstring-only, not enforced at consumer site). | `git grep -nE "\.write\(\|\.read\(\|\.authenticate\(\|Principal\(" origin/main -- 'src/kailash/delegate/*.py'`                                                                                  | MATCH — `Principal(...)` is constructed at exactly ONE site (`dispatch.py:673`, the default itself). Zero consumers of `connector.write` / `connector.read` / `connector.authenticate` exist in the delegate substrate; the runtime hot path uses `connector.invoke(...)` only. Defaults are pure shape-bearing anchors (rs-trait mirrors), not active code.                                                                                                                                                      |
| The verifier subsystem rejects empty-signature envelopes (contract route).                                                                         | `git show origin/main:src/kailash/delegate/verifier.py \| grep -n "len(signature)\|len(sig)\|signature.*== b\"\""` AND `git show origin/main:src/kailash/delegate/audit.py \| sed -n '85,100p'` | PARTIAL MATCH — verifier.py has NO explicit `len(signature) > 0` or `len(signature) == 64` check; it relies on `cryptography.Ed25519PublicKey.verify()` raising `InvalidSignature` on wrong-length signatures (functionally fail-closed but undocumented as the empty-sig rejection contract). audit.py's `_validate_hex` (line 89-100) DOES hard-reject empty `signature` STR at `emit_event` entry, but the Connector primitives emit `bytes` (`b""`), so they never reach `_validate_hex` even hypothetically. |

**Framing verdict for #1177:** STILL ACCURATE. The empty-crypto defaults exist exactly as the issue describes; they are unconsumed (no live runtime path inspects them); the verifier subsystem's empty-rejection is real but indirect (delegated to `cryptography` lib's `InvalidSignature` raise path, not an explicit length check). The MEDIUM severity is accurate — defense-in-depth gap, not an exploit.

---

## #1178 framing-still-accurate table (Principal tenant_id=None footgun)

| Acceptance criterion (from #1178)                                                          | Verification command                                                                                                             | Outcome                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `LegacyOnly().authenticate(...)` returns `Principal(tenant_id=None)` (per minimal repro)   | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '660,680p'`                                                     | MATCH — `async def authenticate(...)` default at line 660 constructs `Principal(delegate_id=str(identity.delegate_id), tenant_id=None, claims={})` at lines 672-676.                                                                                                                                                                                                                                             |
| No `Principal.UNSCOPED` sentinel exists                                                    | `git show origin/main:src/kailash/delegate/dispatch.py \| grep -nE "UNSCOPED\|Principal\.\(UNSCOPED\|Principal\..*=.*Principal"` | MATCH — zero occurrences of `UNSCOPED`. No sentinel class attribute, no class constant, no module constant. The footgun fix path is unimplemented.                                                                                                                                                                                                                                                               |
| `authenticate()` does NOT raise `_legacy_unsupported`                                      | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '660,680p' \| grep "_legacy_unsupported"`                       | MATCH — no `_legacy_unsupported(...)` call inside the `authenticate` default body. The 3 ACCESSORS (`revocation`/`ledger`/`auth_verifier`) raise it (lines 642, 647, 652); the 3 PRIMITIVES (`authenticate`/`write`/`read`) do NOT (lines 660, 679, 711). Asymmetric treatment — the issue's "decide (a) raise or (b) sentinel" question is unresolved.                                                          |
| `Principal` is NOT exported from `kailash.delegate.__init__.__all__`                       | `git show origin/main:src/kailash/delegate/__init__.py \| grep -n "Principal\b"`                                                 | MATCH — zero occurrences. Principal exists only at `dispatch.py:374` (class def) and `dispatch.py:673` (the default constructor). External consumers cannot import it from `kailash.delegate` — bounding the blast radius to internal-only code paths. This is a partial structural mitigation: a consumer cannot accidentally compare `principal.tenant_id` from the public API because there is no public API. |
| TenantScope's `_is_global=True` is structurally distinct from Principal's `tenant_id=None` | `git show origin/main:src/kailash/delegate/trust.py \| sed -n '270,300p'`                                                        | MATCH — `TenantScope.global_()` returns `cls(_is_global=True, _tenant_id=None)` with explicit discriminator AND `__post_init__` enforcement (`_is_global xor _tenant_id is not None`). `Principal` has no such discriminator — `tenant_id=None` is structurally ambiguous (could mean "global-scoped" OR "unset"). The footgun is unique to Principal; TenantScope does NOT share the shape.                     |

**Framing verdict for #1178:** STILL ACCURATE. The `tenant_id=None` return on the default `authenticate` exists exactly as described; the asymmetry between accessors (raise) and primitives (return-empty) is preserved; the issue's recommended fix paths (sentinel OR raise) are both unimplemented. MEDIUM severity is accurate — exploit requires both a legacy `invoke()`-only connector AND a tenant-scoped authorization check; defense-in-depth gap, not active exploit. The fact that `Principal` is not in `__all__` is a partial mitigation worth noting in the issue (could be cited as a "wait for explicit consumer surface" deferral rationale).

---

## Per-finding table (NEW findings beyond #1177 + #1178)

| ID     | Severity | Surface                                                                                       | Literal command                                                                | Literal output                                                                                                                                                                                                                                                           | Disposition                                                                                                                                                                                                                                                                  |
| ------ | -------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R3-S-1 | INFO     | `verifier.py` empty-signature rejection contract is implicit, not explicit                    | `git show origin/main:src/kailash/delegate/verifier.py \| sed -n '270,295p'`   | No `len(signature) != 64` or `len(signature) > 0` check; relies on `cryptography.Ed25519PublicKey.verify(bytes(signature), ...)` raising `InvalidSignature` for wrong-length input.                                                                                      | DEFER-OK / cross-reference with #1177. Subsumed by #1177 acceptance criterion (b) — "make the verifier subsystem hard-reject empty-signature envelopes at the audit-chain boundary". No additional issue needed; resolution path is the existing #1177 acceptance criterion. |
| R3-S-2 | INFO     | `Principal` is undocumented as a non-public symbol (not in `__all__`)                         | `git show origin/main:src/kailash/delegate/__init__.py \| grep -n "Principal"` | (no output)                                                                                                                                                                                                                                                              | DEFER-OK. Mitigation worth surfacing in #1178 closure rationale, NOT a new issue. The non-export bounds the footgun's blast radius — consumers cannot reach `principal.tenant_id` through the public API; only internal delegate code can.                                   |
| R3-S-3 | LOW      | `Connector.__init_subclass__` metadata validation re-runs `isinstance` on inherited cls attrs | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '553,595p'`   | `if not isinstance(cls.connector_id, str) or not cls.connector_id:` etc. — runs for every subclass instantiation including legitimately-abstract intermediates. The `is_concrete` guard at line 562 correctly defers; metadata checks only fire for concrete subclasses. | DEFER-OK. Correctness verified — `is_concrete = invoke_attr is not None and not getattr(invoke_attr, "__isabstractmethod__", False)` gates the metadata checks. Abstract intermediates pass through silently. No security implication; design is correct.                    |

---

## B1–B4 spot-checks (preserved from post-merge convergence)

| Probe | Surface                                                  | Literal command                                                                                                         | Outcome                                                                                                                                                                                                                                                               |
| ----- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1    | `audit.py` uses `hmac.compare_digest` for HMAC compare   | `git show origin/main:src/kailash/delegate/audit.py \| grep -nE "hmac\.compare_digest"`                                 | PASS — line 594: `if not hmac.compare_digest(recomputed, self.cross_anchor_hash):` (cross-anchor seam verification, constant-time).                                                                                                                                   |
| B2    | `verifier.py` uses constant-time crypto verify (no `==`) | `git show origin/main:src/kailash/delegate/verifier.py \| grep -nE "==.*signature\|signature.*==\|compare_digest"`      | PASS — zero `==` comparisons on signature bytes; `public_key.verify()` is the only verification path (cryptographically safe — raises `InvalidSignature`, not `==`).                                                                                                  |
| B3    | `Ed25519Verifier` enforces 32-byte public key length     | `git show origin/main:src/kailash/delegate/verifier.py \| sed -n '270,275p'`                                            | PASS — line 271: `if len(pk_bytes) != 32: return False`. Defense-in-depth re-check even though `PrincipalDirectory.__post_init__` enforces the same invariant on construction.                                                                                        |
| B4    | No `logger.*tenant_id` raw bleed in delegate modules     | `git grep -nE "logger\.[a-z]+\([^)]*tenant_id\|logger\.[a-z]+\([^)]*tenant" origin/main -- 'src/kailash/delegate/*.py'` | PASS — zero matches. All `tenant_id` log refs route through `_tenant_id_hash` or `<global>` sentinel per M4 fix.                                                                                                                                                      |
| B5    | `CascadeTenantViolationError` user-facing message hashed | `git show origin/main:src/kailash/delegate/trust.py \| sed -n '85,105p'`                                                | PASS — `super().__init__(f"... parent_tenant_hash={_tenant_id_hash(parent_tenant)} != child_tenant_hash={_tenant_id_hash(child_tenant)} ...")`. Raw `parent_tenant`/`child_tenant` remain on `self.attrs` per documented design trade-off (B5 DEFER-OK from cycle 2). |

---

## Same-bug-class sweep

**Goal:** find OTHER unconsumed empty-crypto orphans / other `tenant_id=None` slip surfaces / other concrete defaults from PR #1176 shipping cryptographically-empty objects.

### Empty-bytes signature/attestation occurrences across delegate

```
$ git grep -nE "signature=b\"\"|attestation=b\"\"|signature=b''" origin/main -- 'src/kailash/delegate/*.py'
origin/main:src/kailash/delegate/dispatch.py:706:            signature=b"",  # legacy connector did not sign
origin/main:src/kailash/delegate/dispatch.py:741:            attestation=b"",
```

**Sweep result:** EXACTLY 2 sites, both inside the `Connector` primitive defaults. No additional empty-crypto orphans elsewhere in the delegate substrate. Both are covered by #1177.

### `tenant_id=None` occurrences across delegate

```
$ git grep -nE "tenant_id\s*=\s*None" origin/main -- 'src/kailash/delegate/*.py'
origin/main:src/kailash/delegate/dispatch.py:675:            tenant_id=None,
origin/main:src/kailash/delegate/trust.py:297:        return cls(_is_global=True, _tenant_id=None)
```

**Sweep result:** 2 sites. Site 1 (dispatch.py:675) is the `Connector.authenticate` default (#1178). Site 2 (trust.py:297) is `TenantScope.global_()` which is STRUCTURALLY DIFFERENT — explicit `_is_global=True` discriminator + `__post_init__` enforcing `_is_global xor _tenant_id is not None`. The footgun is unique to `Principal`; no additional finding.

### Other concrete defaults from PR #1176

```
$ git show b069ef7e1 -- src/kailash/delegate/dispatch.py | grep -E "^\+" | grep -iE "password|secret|key|token|signature|attestation|crypto|verify|principal" | wc -l
13
```

All 13 added lines reference exactly the 3 named primitives (`authenticate`/`write`/`read`) and their docstring narrative. No NEW empty-secret / empty-key / empty-token defaults added by the refactor. No additional security surface.

### Other surfaces inside the substrate

```
$ git grep -lE "\.write\(|\.read\(|\.authenticate\(" origin/main -- 'src/kailash/delegate/*.py'
(no output)
```

Zero files in the delegate substrate call any of the 3 primitive methods. They are pure rs-mirror anchors today — confirms #1177's "unconsumed orphans" framing structurally.

**Same-bug-class sweep verdict:** NO ADDITIONAL FINDINGS. The 2 MEDIUM issues (#1177, #1178) capture the complete set of empty-crypto / tenant-footgun surface introduced by PR #1176.

---

## Verdict

| Severity | Count                                                                                                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CRIT     | 0                                                                                                                                                                                     |
| HIGH     | 0                                                                                                                                                                                     |
| MED      | 0 NEW (the 2 pre-existing MEDs from R2 are now formally tracked as #1177 + #1178 — issue bodies still accurately frame the surface on `ca552101d`)                                    |
| LOW      | 1 (R3-S-3 — `__init_subclass__` metadata validation; correctness verified, no security implication, DEFER-OK)                                                                         |
| INFO     | 2 (R3-S-1 verifier empty-sig contract is implicit — subsumed by #1177 (b); R3-S-2 Principal not in `__all__` is a partial structural mitigation — surface in #1178 closure rationale) |

**Result: APPROVE — 0 CRIT / 0 HIGH.**

Convergence criteria (0 CRIT / 0 HIGH) MET on R3.

---

## Disposition notes

- **#1177 and #1178 remain OPEN** with accurate framing on the post-merge origin/main. No additional issues need filing for the connector-ABC concrete-defaults work.
- **Empty-signature rejection contract** (R3-S-1) is functionally fail-closed today via `cryptography.Ed25519PublicKey.verify()` raising `InvalidSignature` on wrong-length inputs. The acceptance-criterion path (b) on #1177 (add explicit `len(signature) == 64` check before the crypto call) would convert this from implicit to explicit defense-in-depth.
- **Principal not in `__all__`** (R3-S-2) is a partial structural mitigation for the `tenant_id=None` footgun — external consumers cannot import `Principal` from `kailash.delegate`, bounding the blast radius to internal-only paths. This is worth noting in the #1178 closure rationale and might be cited as a "wait for explicit consumer surface" deferral argument if the issue is downgraded from MEDIUM to LOW after the Connector primitive consumer surface lands.
- **Per `rules/autonomous-execution.md` MUST-4** (Fix-Immediately when review surfaces same-class gap within shard budget): neither R3-S-1 nor R3-S-2 surfaces a SAME-CLASS gap requiring immediate fix. R3-S-1 is subsumed by #1177's existing acceptance criterion path (b); R3-S-2 is a clarification, not a new defect. No same-shard fix obligation triggered.

---

## Cross-CLI neutrality

All commands above use generic `git`, `grep`, `sed` invocations with no CLI-specific syntax. Verification reproducible from any CC / Codex / Gemini variant runner.

---

## Receipt-source provenance

- `origin/main` HEAD: `ca552101d365408eb1ea713cf196be4b006e166d` (verified at audit start via `git rev-parse origin/main`)
- PR #1176 merge commit: `f8c6c5b619b7c25bc4778c87d4bdcca3cd72be83`
- PR #1176 refactor commit: `b069ef7e18a2caa1827e9967f56873df6b62420b`
- Issues verified live: `gh issue view 1177` + `gh issue view 1178`
- Parent convergence receipts: `workspaces/issue-1035-delegate-py/04-validate/R2-convergence.md` + `11-post-merge-convergence.md`
- Tool inventory used: Bash (git, gh, grep, sed), Read — all reads piped through `git show origin/main:<path>` per the brief's anchor protocol.

Round 3 security audit COMPLETE. Verdict feeds into convergence aggregation alongside parallel spec-compliance + closure-parity agents.
