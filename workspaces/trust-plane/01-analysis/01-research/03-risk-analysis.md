# TrustPlane Risk Analysis

## Integration Risks (Monorepo)

| ID   | Risk                                                       | Likelihood | Impact   | Mitigation                                                                |
| ---- | ---------------------------------------------------------- | ---------- | -------- | ------------------------------------------------------------------------- |
| I-01 | eatp path dependency vs PyPI resolution conflict           | HIGH       | CRITICAL | Use pip editable installs in dev; pin `eatp>=0.1.0,<1.0.0` (already done) |
| I-02 | Python version mismatch: eatp >=3.11, trust-plane >=3.10   | HIGH       | HIGH     | Align trust-plane to >=3.11 (eatp requires it for `tomllib`)              |
| I-03 | fcntl dependency = POSIX-only                              | HIGH       | HIGH     | Document platform requirement or add cross-platform fallback              |
| I-04 | Test isolation: shared pytest-asyncio mode                 | MEDIUM     | MEDIUM   | Separate conftest.py per package                                          |
| I-05 | Deep eatp coupling: 15+ internal imports from 9 submodules | HIGH       | HIGH     | Define eatp public API surface; trust-plane imports only stable symbols   |
| I-06 | No unified CI runner for monorepo packages                 | MEDIUM     | MEDIUM   | Add tox/nox config at repo root                                           |

### Root Cause: I-05 (Deep Internal Coupling)

Trust-plane imports directly from eatp internal modules:

- `eatp.chain` (ActionResult, AuthorityType, CapabilityType, VerificationResult)
- `eatp.crypto` (generate_keypair)
- `eatp.enforce.strict` (HeldBehavior, StrictEnforcer, Verdict)
- `eatp.enforce.shadow` (ShadowEnforcer)
- `eatp.postures` (PostureStateMachine, PostureTransitionRequest, TrustPosture)
- `eatp.reasoning` (ConfidentialityLevel, ReasoningTrace)
- `eatp.store.filesystem` (FilesystemStore)
- `eatp.authority` (AuthorityPermission, OrganizationalAuthority)

Any eatp refactor (including the 35+ pre-existing issue fixes we just completed) could break trust-plane.

---

## Architecture Scalability Risks

| Concern               | Current State                            | At Scale                    | Mitigation Path                                  |
| --------------------- | ---------------------------------------- | --------------------------- | ------------------------------------------------ |
| Directory scanning    | `glob("*.json")` on verify/load          | O(n) reads; slow on NFS     | Index file or SQLite backing                     |
| No query capability   | Read all JSON to search                  | Unusable for analytics      | Optional SQLite index                            |
| Single-process write  | fcntl.flock (advisory, POSIX)            | NFS unreliable              | Document local-only or add advisory lock service |
| File count            | 1 file per decision + anchor + milestone | 30K+ files at 10K decisions | Subdirectory sharding                            |
| Non-filesystem stores | Tightly coupled to filesystem            | Cannot use PostgreSQL/S3    | Store abstraction layer needed (~month of work)  |

---

## Product-Market Risks

| Risk                        | Severity | Notes                                                                                         |
| --------------------------- | -------- | --------------------------------------------------------------------------------------------- |
| Solving a pain not yet felt | CRITICAL | Most teams have no AI accountability mandate today. Value is future-oriented.                 |
| MCP-only integration        | HIGH     | Limits to MCP-compatible AI tools only. VS Code Copilot, Cursor, JetBrains AI users excluded. |
| Conceptual overhead         | MEDIUM   | EATP dimensions, postures, trust chain, Mirror Thesis — unfamiliar terminology for new users. |
| No dashboard/UI             | MEDIUM   | CLI-only. Verification bundle HTML is a start but no live dashboard.                          |
| Unnamed market category     | HIGH     | No Gartner quadrant. Must educate market — expensive and benefits later entrants.             |

---

## Enterprise Adoption Gaps

| Gap                                 | Priority | Effort |
| ----------------------------------- | -------- | ------ |
| Central server / API mode           | CRITICAL | Large  |
| SSO / RBAC integration              | CRITICAL | Medium |
| Dashboard / Web UI                  | HIGH     | Medium |
| SOC2 / ISO 27001 compliance mapping | HIGH     | Medium |
| Database backing store              | HIGH     | Large  |
| SIEM integration                    | HIGH     | Medium |
| Windows support                     | MEDIUM   | Medium |
| Encryption at rest                  | MEDIUM   | Medium |
| Multi-tenancy                       | HIGH     | Large  |

---

## Developer Adoption Gaps

| Gap                                           | Priority | Effort       |
| --------------------------------------------- | -------- | ------------ |
| VS Code / Cursor / JetBrains integration      | CRITICAL | Medium-Large |
| GitHub Action (CI verification)               | HIGH     | Small        |
| "Why should I care?" documentation            | HIGH     | Small        |
| `attest quickstart` / `attest watch` commands | MEDIUM   | Small        |
| Pre-commit hook integration                   | HIGH     | Small        |
| Tutorial / walkthrough                        | HIGH     | Small        |

---

## EATP Dependency Risks

The eatp-gaps fixes we just completed directly affect trust-plane:

- **F-02 (constraint loosening)**: trust-plane's `ConstraintEnvelope.is_tighter_than()` is correct, but eatp's `ExecutionContext.with_delegation()` was broken — now fixed
- **H6 (unbounded broadcaster)**: trust-plane instantiates broadcasters in delegation — now bounded
- **C2/C3 (key manager)**: trust-plane uses `TrustKeyManager` for genesis — now hardened

These fixes strengthen trust-plane's foundation.

---

## Decision Points Requiring Input

1. **Separate PyPI package or eatp submodule?** Separate = independent adoption but coupling risk. Submodule = simpler imports but increases eatp scope.
2. **Python version floor**: Align to >=3.11 (eatp requires it)?
3. **Windows story**: POSIX-only, msvcrt fallback, or cross-platform library (`filelock`)?
4. **Store abstraction now or later?** Premature abstraction vs. harder refactor later.
5. **Multi-user strategy**: git-sync with merge resolution, central server mode, or document single-machine only?
