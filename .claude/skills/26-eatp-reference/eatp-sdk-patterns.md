# EATP SDK — Implementation Patterns & Gotchas

Critical patterns, security considerations, and gotchas discovered during the EATP SDK extraction and red team validation.

**Source**: `packages/eatp/` | **Tests**: 1177 passed | **Red team**: 2 rounds, 5 agents, all critical/high resolved

## Critical Gotchas

### 1. Key Pair Order: Private FIRST

```python
from eatp.crypto import generate_keypair

private_key, public_key = generate_keypair()  # CORRECT: private first
# Both are base64-encoded strings, NOT raw bytes
```

NEVER swap the order. `generate_keypair()` returns `(private_key_base64, public_key_base64)`.

### 2. AuthorityRegistryProtocol — All 3 Methods Required

```python
from eatp.authority import AuthorityRegistryProtocol

# This protocol requires ALL THREE methods:
class MyRegistry:
    async def initialize(self) -> None: ...
    async def get_authority(self, authority_id: str, include_inactive: bool = False) -> OrganizationalAuthority: ...
    async def update_authority(self, authority: OrganizationalAuthority) -> None: ...
```

Missing `update_authority()` will fail at runtime when `CredentialRotationManager` tries to update authority keys. The canonical Protocol class lives in `eatp.authority` (not `eatp.operations`).

### 3. StrictEnforcer — No Positional or trust_operations Arg

```python
from eatp.enforce.strict import StrictEnforcer, Verdict

# CORRECT — optional keyword args only: on_held, held_callback, flag_threshold
enforcer = StrictEnforcer()
enforcer = StrictEnforcer(on_held=HeldBehavior.RAISE, flag_threshold=0.8)

# WRONG — these do NOT exist as constructor args:
# enforcer = StrictEnforcer(trust_operations=ops)   # TypeError
# enforcer.check(agent_id="...", action="...")       # AttributeError

# CORRECT usage:
result = await ops.verify(agent_id="agent-001", action="do_thing")
verdict = enforcer.classify(result)  # Returns Verdict enum
```

### 4. Signatures Are Base64, Not Hex

```python
# Signatures from eatp.crypto.sign() are base64-encoded
sig = sign(payload, private_key)  # Returns base64 string

# verify_signature() expects base64 signature
is_valid = verify_signature(payload, sig, public_key)  # Handles base64 internally

# NEVER use bytes.fromhex() on EATP signatures
```

### 5. GenesisRecord Has No .constraints Attribute

Constraints live on `CapabilityAttestation`, not `GenesisRecord`:

```python
# WRONG
genesis.constraints  # AttributeError!

# CORRECT — get constraints from capabilities
all_constraints = list(dict.fromkeys(
    c for cap in chain.capabilities for c in cap.constraints
))
```

### 6. Chain Methods Use .hash() and .to_signing_payload()

```python
# Hash
chain_hash = chain.hash()           # NOT chain.compute_hash()

# Signing payload
payload = genesis.to_signing_payload()  # NOT genesis.signing_payload (it's a method, not property)
```

## Security Patterns

### SQL Injection Prevention (ESA Database)

`eatp.esa.database` uses parameterized queries with column name validation:

```python
# Column names validated against: _ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
# Filter values are parameterized:
#   PostgreSQL: $1, $2, $3...
#   MySQL: %s
#   SQLite: ?
```

### JWT Algorithm Safety

Only asymmetric algorithms are allowed. HMAC (HS256/HS384/HS512) was removed to prevent key-confusion attacks:

```python
# eatp.interop.jwt._SAFE_ALGORITHMS
_SAFE_ALGORITHMS = {"EdDSA", "ES256", "ES384", "ES512", "RS256", "RS384", "RS512"}
# NO HS256, HS384, HS512
```

### Bounded Nonce Storage

`InMemoryReplayProtection` has a `max_nonces` parameter (default 1,000,000) to prevent memory exhaustion:

```python
from eatp.messaging.replay_protection import InMemoryReplayProtection

replay = InMemoryReplayProtection(max_nonces=100_000)
# Auto-cleanup when cap exceeded, oldest entries evicted first
```

### Path-Aware Glob Matching

`ConstraintValidator._glob_match()` treats:

- `*` as single path segment (does NOT match `/`)
- `**` as cross-segment wildcard (matches anything including `/`)

This replaces Python's `fnmatch.fnmatch()` which incorrectly lets `*` match path separators, enabling constraint bypass.

### Constraint Deduplication

When merging capability-specific + global constraints, or delegator + additional constraints, the SDK uses order-preserving deduplication:

```python
seen = set()
all_constraints = []
for c in cap_request.constraints + global_constraints:
    if c not in seen:
        seen.add(c)
        all_constraints.append(c)
```

## Architecture Patterns

### Trust Sandwich (TrustedAgent)

Every action through `TrustedAgent` follows:

1. **VERIFY** — Check trust before action
2. **EXECUTE** — Perform the action
3. **AUDIT** — Record in immutable trail

```python
from eatp.trusted_agent import TrustedAgent, TrustedAgentConfig

trusted = TrustedAgent(
    agent=base_agent,
    trust_ops=trust_operations,
    config=TrustedAgentConfig(agent_id="worker-001"),
)
result = await trusted.execute_async(inputs={"question": "What is AI?"})
```

### PDP/PEP Separation

The SDK is the **Policy Decision Point** (PDP) — it computes verdicts. Your application is the **Policy Enforcement Point** (PEP) — it must enforce them.

| Responsibility                           | Standalone SDK  | Host Application |
| ---------------------------------------- | --------------- | ---------------- |
| Constraint tightening at delegation time | **Enforced**    | N/A              |
| VERIFY operation (compute verdict)       | **Provided**    | Must call        |
| BLOCKED enforcement (reject action)      | Returns verdict | **Must enforce** |
| HELD enforcement (queue for human)       | Returns verdict | **Must enforce** |

### Kaizen Shim Layer

After extraction, Kaizen trust files are thin shims:

```python
# packages/kailash-kaizen/src/kaizen/trust/chain.py
from eatp.chain import *  # noqa: F401,F403
```

This means:

- Canonical code lives in `packages/eatp/src/eatp/`
- Kaizen tests exercise the same code through shim imports
- 1177 EATP tests + 1623 Kaizen trust tests = 2800 total coverage

### Store Architecture

```
TrustStore (ABC)
├── InMemoryTrustStore    — Fast, no persistence, transaction support
├── FilesystemStore       — JSON files, thread-safe writes, soft-delete
└── PostgresTrustStore    — Production (in kailash-kaizen, not standalone)
```

All stores require `await store.initialize()` before use. All stores implement `transaction()` for atomic multi-chain updates.

## Common Integration Patterns

### Implementing AuthorityRegistryProtocol for Production

```python
class PostgresAuthorityRegistry:
    """Production registry using database storage."""

    def __init__(self, connection_string: str):
        self._conn_str = connection_string
        self._pool = None

    async def initialize(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(self._conn_str)

    async def get_authority(self, authority_id: str, include_inactive: bool = False):
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM authorities WHERE id = $1", authority_id
            )
            if row is None:
                raise KeyError(f"Authority not found: {authority_id}")
            authority = OrganizationalAuthority.from_dict(dict(row))
            if not include_inactive and not authority.is_active:
                raise KeyError(f"Authority inactive: {authority_id}")
            return authority

    async def update_authority(self, authority: OrganizationalAuthority):
        async with self._pool.acquire() as conn:
            data = authority.to_dict()
            await conn.execute(
                "UPDATE authorities SET data = $1, updated_at = NOW() WHERE id = $2",
                json.dumps(data), authority.id,
            )
```

### Adding EATP to an Existing Agent Framework

```python
# 1. Setup trust infrastructure once at application startup
store = InMemoryTrustStore()  # or FilesystemStore for persistence
await store.initialize()
key_mgr = TrustKeyManager()
registry = MyAuthorityRegistry()  # Your implementation

ops = TrustOperations(
    authority_registry=registry,
    key_manager=key_mgr,
    trust_store=store,
)

# 2. ESTABLISH trust for each agent at creation time
chain = await ops.establish(
    agent_id=agent.id,
    authority_id="org-acme",
    capabilities=[...],
)

# 3. VERIFY before every action
result = await ops.verify(agent_id=agent.id, action=action_name)
if not result.valid:
    raise PermissionError(result.reason)

# 4. AUDIT after every action
await ops.audit(agent_id=agent.id, action=action_name, result=ActionResult.SUCCESS)
```

## Known Limitations (Post-v0.1.0)

These are documented for future improvement:

- **SEC-M1**: `esa.database.execute_query()` accepts raw SQL (public method should be private)
- **SEC-M2**: Clock skew tolerance hardcoded at 60s (should be configurable)
- **SEC-M3**: PBKDF2 100k iterations (OWASP recommends 600k)
- **SEC-M4**: FilesystemStore not process-safe (single process only)
- **VAL-M1**: No built-in `SimpleAuthorityRegistry` in SDK (boilerplate in every example)
- **Coverage**: ~31% line coverage in EATP-internal tests; many modules exercised through Kaizen shim tests

## Test Patterns

```bash
# Run EATP standalone tests
cd packages/eatp
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/unit/ -v                    # Unit tests
python -m pytest tests/integration/ -v             # Integration tests
python -m pytest tests/unit/test_jwt_interop.py -v # JWT interop

# Run Kaizen trust tests (exercises same code via shims)
cd packages/kailash-kaizen
python -m pytest tests/unit/trust/ -v
```
