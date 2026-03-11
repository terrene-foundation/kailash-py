# EATP SDK — Claude Code Instructions

## Package Identity

- Name: `eatp`
- Version: 0.1.0
- License: Apache 2.0 (Terrene Foundation)
- Install: `pip install eatp`

## Module Map

| Module                    | Purpose                                                       |
| ------------------------- | ------------------------------------------------------------- |
| `eatp.chain`              | Core data structures (GenesisRecord, DelegationRecord, etc.)  |
| `eatp.crypto`             | Ed25519 operations (generate_keypair, sign, verify_signature) |
| `eatp.operations`         | TrustOperations class (ESTABLISH, DELEGATE, VERIFY, AUDIT)    |
| `eatp.authority`          | AuthorityRegistry and OrganizationalAuthority                 |
| `eatp.store.memory`       | InMemoryTrustStore                                            |
| `eatp.store.filesystem`   | FilesystemStore (JSON files in ~/.eatp/chains/)               |
| `eatp.store.postgres`     | PostgresTrustStore                                            |
| `eatp.enforce.strict`     | StrictEnforcer (raises on BLOCKED/HELD)                       |
| `eatp.enforce.shadow`     | ShadowEnforcer (log-only, no blocking)                        |
| `eatp.enforce.decorators` | @verified, @audited, @shadow decorators                       |
| `eatp.enforce.challenge`  | Challenge-response protocol                                   |
| `eatp.constraints`        | Constraint dimensions, templates, evaluator                   |
| `eatp.postures`           | TrustPosture enum, PostureStateMachine                        |
| `eatp.scoring`            | Trust scoring (0-100) and reports                             |
| `eatp.merkle`             | MerkleTree for audit proofs                                   |
| `eatp.interop.jwt`        | JWT export/import                                             |
| `eatp.interop.w3c_vc`     | W3C Verifiable Credentials                                    |
| `eatp.interop.did`        | DID identity (did:eatp:, did:key:)                            |
| `eatp.interop.ucan`       | UCAN delegation tokens                                        |
| `eatp.interop.sd_jwt`     | SD-JWT selective disclosure                                   |
| `eatp.interop.biscuit`    | Biscuit authorization tokens                                  |
| `eatp.reasoning`          | ReasoningTrace dataclass, ConfidentialityLevel enum           |
| `eatp.cli`                | CLI commands (eatp init, establish, verify, etc.)             |
| `eatp.mcp`                | MCP server (5 tools, 4 resources)                             |

## Key Patterns

```python
# generate_keypair returns (private_key, public_key) — private FIRST
private_key, public_key = generate_keypair()

# TrustOperations(authority_registry, key_manager, trust_store)
ops = TrustOperations(registry, key_manager, store)
chain = await ops.establish(agent_id, authority_id, capabilities)
result = await ops.verify(agent_id, action)
delegation = await ops.delegate(from_id, to_id, capabilities)

# Delegation with reasoning trace
from eatp.reasoning import ReasoningTrace, ConfidentialityLevel
trace = ReasoningTrace(
    decision="Why", rationale="Because",
    confidentiality=ConfidentialityLevel.RESTRICTED,
    timestamp=datetime.now(timezone.utc),
)
delegation = await ops.delegate(from_id, to_id, capabilities, reasoning_trace=trace)

# Enforcement — StrictEnforcer has NO required args
enforcer = StrictEnforcer()
verdict = enforcer.classify(result)  # Returns Verdict enum
```

## Reasoning Trace Extension

- `reasoning_trace`, `reasoning_trace_hash`, `reasoning_signature` on DelegationRecord and AuditAnchor (all Optional, default None)
- `reasoning_trace_hash` IS included in `to_signing_payload()` (v2.2 dual-binding — prevents substitution attacks)
- `reasoning_trace` and `reasoning_signature` excluded from parent signing payload (have their own verification path)
- Verification: QUICK (no check), STANDARD (advisory warning), FULL (hard failure if REASONING_REQUIRED + missing trace; crypto verification)
- Crypto: `hash_reasoning_trace()`, `sign_reasoning_trace()`, `verify_reasoning_signature()` in `eatp.crypto`
- REASONING_REQUIRED constraint type on `ConstraintType` enum

## Testing

```bash
cd packages/eatp
python -m pytest tests/ -v           # Run all 1557 tests
python -m pytest tests/ --cov=eatp   # With coverage
```

## Critical Rules

- No hardcoded secrets or API keys
- No mocking in integration tests — use real InMemoryTrustStore
- All async operations use asyncio (project uses asyncio_mode=auto)
- Signatures use Ed25519 via PyNaCl
