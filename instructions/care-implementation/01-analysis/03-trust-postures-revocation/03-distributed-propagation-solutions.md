# Distributed Propagation Solutions for EATP Trust Revocation

## Executive Summary

This document proposes innovative solutions for reliable trust revocation propagation in distributed agentic systems. The core challenge is ensuring that when trust is revoked, all agents acting on that trust immediately stop, even across network partitions, cached state, and in-flight operations. We propose a multi-layered approach combining short-lived tokens, heartbeat verification, gossip propagation, and execution fencing.

**Recommendation**: Implement a **Hybrid Push-Pull Protocol with Execution Fencing** for SDK, leveraging Platform revocation broadcast for global coordination.

---

## 1. Solution Overview Matrix

| Solution               | Latency | Reliability | Complexity | SDK/Platform |
| ---------------------- | ------- | ----------- | ---------- | ------------ |
| Short-lived Tokens     | ~1s     | HIGH        | MEDIUM     | SDK          |
| Heartbeat Verification | ~5-30s  | MEDIUM      | LOW        | SDK          |
| Push-Pull Hybrid       | ~100ms  | HIGH        | HIGH       | Both         |
| Gossip Protocol        | ~1-5s   | MEDIUM      | HIGH       | Platform     |
| Chain Versioning       | ~10ms   | HIGH        | MEDIUM     | Both         |
| Execution Fencing      | ~1ms    | VERY HIGH   | MEDIUM     | SDK          |

---

## 2. Short-Lived Tokens with Refresh

### 2.1 Concept

Replace long-lived trust chains with short-lived execution tokens that must be periodically refreshed. If the token expires, all operations stop until a fresh token is obtained from the Platform.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent     │     │  Token Svc  │     │ Trust Store │
│             │     │  (Platform) │     │             │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ get_token(chain)  │                   │
       │──────────────────►│                   │
       │                   │ validate_chain()  │
       │                   │──────────────────►│
       │                   │◄──────────────────│
       │◄──────────────────│                   │
       │ token(ttl=60s)    │                   │
       │                   │                   │
       │═══ Execute with token for 60s ═══    │
       │                   │                   │
       │ refresh_token()   │                   │
       │──────────────────►│                   │
       │                   │ check_revoked()   │
       │                   │──────────────────►│
       │                   │◄─ REVOKED ────────│
       │◄──── DENIED ──────│                   │
       │                   │                   │
       │ All ops stop immediately              │
```

### 2.2 Token Structure

```python
@dataclass(frozen=True)
class ExecutionToken:
    token_id: str
    agent_id: str
    chain_hash: str          # Hash of trust chain at issuance
    chain_version: int       # Monotonic version for fencing
    capabilities: Set[str]   # Capabilities encoded in token
    issued_at: datetime
    expires_at: datetime
    signature: str           # Signed by Platform

    def is_valid(self) -> bool:
        return datetime.now(timezone.utc) < self.expires_at

    def time_remaining(self) -> timedelta:
        return self.expires_at - datetime.now(timezone.utc)
```

### 2.3 Implementation Details

**Token Service (Platform)**:

```python
class TokenService:
    TOKEN_TTL_SECONDS = 60  # 1 minute tokens
    REFRESH_WINDOW_SECONDS = 10  # Refresh when 10s remaining

    async def issue_token(self, agent_id: str) -> ExecutionToken:
        # Validate trust chain is active
        chain = await self.trust_store.get_chain(agent_id)
        if not chain or chain.is_revoked():
            raise TrustRevokedError(agent_id)

        token = ExecutionToken(
            token_id=str(uuid.uuid4()),
            agent_id=agent_id,
            chain_hash=chain.hash(),
            chain_version=chain.version,
            capabilities=set(c.capability for c in chain.capabilities),
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.TOKEN_TTL_SECONDS),
            signature=self._sign_token(token_payload)
        )
        return token

    async def refresh_token(self, old_token: ExecutionToken) -> ExecutionToken:
        # Re-validate chain - this catches revocations
        return await self.issue_token(old_token.agent_id)
```

**SDK Token Manager**:

```python
class TokenManager:
    def __init__(self, token_service: TokenService):
        self._token_service = token_service
        self._tokens: Dict[str, ExecutionToken] = {}
        self._refresh_tasks: Dict[str, asyncio.Task] = {}

    async def get_token(self, agent_id: str) -> ExecutionToken:
        token = self._tokens.get(agent_id)

        if token and token.time_remaining() > timedelta(seconds=10):
            return token

        # Refresh or get new token
        try:
            new_token = await self._token_service.issue_token(agent_id)
            self._tokens[agent_id] = new_token
            self._schedule_refresh(agent_id, new_token)
            return new_token
        except TrustRevokedError:
            # Remove stale token
            self._tokens.pop(agent_id, None)
            raise
```

### 2.4 Assessment

| Criteria                  | Score              | Notes                                     |
| ------------------------- | ------------------ | ----------------------------------------- |
| Revocation Latency        | A-                 | Max 60s (token TTL)                       |
| Reliability               | A                  | Token expiry guarantees eventual stop     |
| Network Overhead          | B                  | Refresh every 60s per agent               |
| Implementation Complexity | B                  | Moderate - needs token service            |
| Placement                 | **SDK + Platform** | Token service on Platform, manager in SDK |

---

## 3. Heartbeat-Based Trust Verification

### 3.1 Concept

Agents periodically "heartbeat" to verify their trust chain is still valid. Missing or failed heartbeats trigger immediate suspension.

```
┌─────────────┐     ┌─────────────┐
│   Agent     │     │  Platform   │
│             │     │ Heartbeat   │
└──────┬──────┘     └──────┬──────┘
       │                   │
       │─── heartbeat() ───►
       │◄── ACK ───────────│
       │                   │
       │ [30s later]       │
       │                   │
       │─── heartbeat() ───►
       │                   │ [revoked]
       │◄── REVOKED ───────│
       │                   │
       │ STOP ALL OPS      │
```

### 3.2 Implementation

```python
class HeartbeatManager:
    HEARTBEAT_INTERVAL = 30  # seconds
    MISS_THRESHOLD = 3  # Allow 3 missed heartbeats

    async def start_heartbeat(self, agent_id: str):
        while True:
            try:
                response = await self._send_heartbeat(agent_id)
                if response.status == "REVOKED":
                    await self._on_revocation(agent_id)
                    break
                self._consecutive_misses[agent_id] = 0
            except HeartbeatError:
                self._consecutive_misses[agent_id] += 1
                if self._consecutive_misses[agent_id] >= self.MISS_THRESHOLD:
                    await self._on_connection_lost(agent_id)
                    break

            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def _send_heartbeat(self, agent_id: str) -> HeartbeatResponse:
        return await self._platform_client.heartbeat(
            agent_id=agent_id,
            chain_hash=self._current_chain_hash(agent_id),
            active_work_count=self._active_work_count(agent_id)
        )
```

### 3.3 Assessment

| Criteria                  | Score   | Notes                             |
| ------------------------- | ------- | --------------------------------- |
| Revocation Latency        | C       | 30-90 seconds                     |
| Reliability               | B+      | Handles network issues gracefully |
| Network Overhead          | A       | One request per 30s               |
| Implementation Complexity | A       | Simple polling mechanism          |
| Placement                 | **SDK** | Agent-side heartbeat client       |

---

## 4. Push-Pull Hybrid Protocol

### 4.1 Concept

Combine immediate push notifications for revocations with periodic pull verification for reliability. Best of both worlds.

```
PUSH (Fast Path):
Platform ──── REVOKE event ────► All caches/agents via WebSocket/SSE

PULL (Backup Path):
Agent ──── periodic verify ────► Platform (catches missed pushes)
```

### 4.2 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        PLATFORM                              │
│  ┌───────────────┐    ┌───────────────┐    ┌──────────────┐│
│  │ Revocation    │    │ Event         │    │ Trust        ││
│  │ Service       │───►│ Broadcaster   │    │ Store        ││
│  └───────────────┘    └───────┬───────┘    └──────────────┘│
│                               │ SSE/WebSocket               │
└───────────────────────────────┼─────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
         ▼                      ▼                      ▼
    ┌─────────┐           ┌─────────┐           ┌─────────┐
    │ Agent A │           │ Agent B │           │ Cache   │
    │ SDK     │           │ SDK     │           │ Node    │
    └─────────┘           └─────────┘           └─────────┘
```

### 4.3 Implementation

**Platform - Event Broadcaster**:

```python
class RevocationBroadcaster:
    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._global_subscribers: Set[asyncio.Queue] = set()

    async def broadcast_revocation(self, agent_id: str, reason: str):
        event = RevocationEvent(
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            cascade_ids=await self._get_cascade_ids(agent_id)
        )

        # Broadcast to global subscribers (caches)
        for queue in self._global_subscribers:
            await queue.put(event)

        # Broadcast to agent-specific subscribers
        for queue in self._subscribers.get(agent_id, set()):
            await queue.put(event)

    async def subscribe_global(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._global_subscribers.add(queue)
        return queue
```

**SDK - Hybrid Receiver**:

```python
class TrustVerificationClient:
    PULL_INTERVAL = 300  # 5 minutes as backup

    async def start(self):
        # Start both push and pull
        await asyncio.gather(
            self._push_receiver(),
            self._pull_verifier()
        )

    async def _push_receiver(self):
        """Receive push notifications via SSE"""
        async for event in self._platform.subscribe_revocations():
            if event.agent_id in self._tracked_agents:
                await self._handle_revocation(event)

    async def _pull_verifier(self):
        """Periodic pull as backup"""
        while True:
            for agent_id in self._tracked_agents:
                try:
                    is_valid = await self._platform.verify_trust(agent_id)
                    if not is_valid:
                        await self._handle_revocation_detected(agent_id)
                except Exception as e:
                    logger.warning(f"Pull verification failed: {e}")

            await asyncio.sleep(self.PULL_INTERVAL)
```

### 4.4 Assessment

| Criteria                  | Score    | Notes                                    |
| ------------------------- | -------- | ---------------------------------------- |
| Revocation Latency        | A+       | ~100ms via push                          |
| Reliability               | A        | Pull backup catches failures             |
| Network Overhead          | B+       | Push is efficient, pull adds overhead    |
| Implementation Complexity | B-       | Requires WebSocket/SSE infrastructure    |
| Placement                 | **Both** | Broadcaster on Platform, receiver in SDK |

---

## 5. Gossip-Based Revocation

### 5.1 Concept

Agents propagate revocation information to peers they communicate with. Revocations spread virally through the agent network.

### 5.2 Protocol

```
Agent A revoked
    │
    ├──► Tells Agent B (next communication)
    │         │
    │         └──► Tells Agent C, D
    │                    │
    └──► Tells Agent E   └──► Tells Agent F, G
              │
              └──► etc.
```

### 5.3 Implementation

```python
class GossipRevocationProtocol:
    GOSSIP_FANOUT = 3  # Tell 3 random peers
    REVOCATION_TTL = 3600  # Remember for 1 hour

    def __init__(self):
        self._known_revocations: Dict[str, datetime] = {}
        self._peer_connections: Set[str] = set()

    async def on_agent_communication(self, peer_id: str, message: Any):
        # Piggyback revocation gossip on regular communication
        gossip = self._get_gossip_payload()
        await self._send_with_gossip(peer_id, message, gossip)

    async def receive_gossip(self, gossip: GossipPayload):
        for revocation in gossip.revocations:
            if revocation.agent_id not in self._known_revocations:
                self._known_revocations[revocation.agent_id] = revocation.timestamp
                # Check if we're affected
                if self._is_affected(revocation.agent_id):
                    await self._handle_revocation(revocation)
                # Propagate to random peers
                await self._propagate_gossip(revocation)

    async def _propagate_gossip(self, revocation: Revocation):
        peers = random.sample(self._peer_connections, min(self.GOSSIP_FANOUT, len(self._peer_connections)))
        for peer in peers:
            await self._send_gossip(peer, revocation)
```

### 5.4 Assessment

| Criteria                  | Score        | Notes                                           |
| ------------------------- | ------------ | ----------------------------------------------- |
| Revocation Latency        | B            | 1-5 seconds (depends on topology)               |
| Reliability               | B            | Eventually consistent, may miss isolated agents |
| Network Overhead          | A            | Piggybacked on existing communication           |
| Implementation Complexity | C+           | Complex protocol, debugging difficult           |
| Placement                 | **Platform** | For inter-organization agent communication      |

---

## 6. Trust Chain Versioning

### 6.1 Concept

Every trust chain has a monotonically increasing version number. Any operation includes the expected version; if the version is stale, the operation is rejected.

### 6.2 Implementation

```python
@dataclass
class VersionedTrustChain:
    chain: TrustLineageChain
    version: int  # Monotonically increasing
    last_modified: datetime

class VersionedTrustStore:
    async def get_chain(self, agent_id: str) -> Tuple[TrustLineageChain, int]:
        record = await self._db.get(agent_id)
        return record.chain, record.version

    async def update_chain_if_version(
        self,
        agent_id: str,
        chain: TrustLineageChain,
        expected_version: int
    ) -> bool:
        """Atomic conditional update"""
        result = await self._db.update_where(
            id=agent_id,
            set={"chain": chain, "version": expected_version + 1},
            where={"version": expected_version}
        )
        return result.rows_affected > 0

    async def revoke_chain(self, agent_id: str) -> int:
        """Revoke and return new version"""
        result = await self._db.update(
            id=agent_id,
            set={"is_active": False, "version": {"$inc": 1}}
        )
        return result.version

class TrustOperations:
    async def verify_versioned(
        self,
        agent_id: str,
        expected_version: int
    ) -> VerificationResult:
        chain, current_version = await self.trust_store.get_chain(agent_id)

        if current_version != expected_version:
            return VerificationResult(
                valid=False,
                reason=f"Version mismatch: expected {expected_version}, got {current_version}"
            )

        # Continue with normal verification
        return await self._verify_chain(chain)
```

### 6.3 Assessment

| Criteria                  | Score              | Notes                                           |
| ------------------------- | ------------------ | ----------------------------------------------- |
| Revocation Latency        | A                  | Immediate on next version check                 |
| Reliability               | A                  | Strong consistency guarantee                    |
| Network Overhead          | A                  | Just version number in requests                 |
| Implementation Complexity | B+                 | Requires database support for atomic increments |
| Placement                 | **SDK + Platform** | Store on Platform, check in SDK                 |

---

## 7. Execution Fencing

### 7.1 Concept

Inspired by database fencing tokens. Every action includes a fencing token (trust chain version). The resource being accessed validates the token is current before allowing the operation.

### 7.2 Implementation

```python
@dataclass(frozen=True)
class FencingToken:
    agent_id: str
    chain_version: int
    issued_at: datetime
    capabilities: FrozenSet[str]

class FencedResource:
    """Resource that validates fencing tokens"""

    def __init__(self, fence_validator: FenceValidator):
        self._fence_validator = fence_validator
        self._last_valid_token: Dict[str, FencingToken] = {}

    async def execute_fenced(
        self,
        token: FencingToken,
        operation: Callable
    ):
        # Validate token is not stale
        is_valid = await self._fence_validator.validate(token)
        if not is_valid:
            raise StaleFenceTokenError(token)

        # Check token hasn't been superseded locally
        last_token = self._last_valid_token.get(token.agent_id)
        if last_token and last_token.chain_version > token.chain_version:
            raise OutdatedTokenError(token, last_token)

        # Execute operation
        result = await operation()

        # Update last valid token
        self._last_valid_token[token.agent_id] = token

        return result

class FenceValidator:
    """Platform service that validates fencing tokens"""

    async def validate(self, token: FencingToken) -> bool:
        current_version = await self._trust_store.get_version(token.agent_id)
        return current_version == token.chain_version
```

### 7.3 Protocol Flow

```
┌─────────┐       ┌─────────┐       ┌─────────┐       ┌─────────┐
│ Agent   │       │ Token   │       │ Resource│       │ Fence   │
│         │       │ Service │       │         │       │ Validator│
└────┬────┘       └────┬────┘       └────┬────┘       └────┬────┘
     │                 │                 │                 │
     │ get_token()     │                 │                 │
     │────────────────►│                 │                 │
     │◄────────────────│                 │                 │
     │ token(v=42)     │                 │                 │
     │                 │                 │                 │
     │ execute(token, op)               │                 │
     │─────────────────────────────────►│                 │
     │                 │                 │ validate(token) │
     │                 │                 │────────────────►│
     │                 │                 │ check version   │
     │                 │                 │◄────────────────│
     │                 │                 │ valid/invalid   │
     │◄─────────────────────────────────│                 │
     │ result or DENIED                  │                 │
```

### 7.4 Assessment

| Criteria                  | Score   | Notes                                    |
| ------------------------- | ------- | ---------------------------------------- |
| Revocation Latency        | A+      | ~1ms - checked on every operation        |
| Reliability               | A+      | Strongest guarantee - every op validated |
| Network Overhead          | B       | Validation call per operation            |
| Implementation Complexity | B       | Resources must implement fencing         |
| Placement                 | **SDK** | Token acquisition and validation         |

---

## 8. Split-Brain Resolution

### 8.1 Scenario

```
Pre-partition:     During partition:      Post-healing:
┌─────┐           ┌─────┐  X  ┌─────┐    ┌─────┐    ┌─────┐
│DB-A │           │DB-A │  X  │DB-B │    │DB-A │====│DB-B │
└─────┘           └─────┘  X  └─────┘    └─────┘    └─────┘
                           X
Agent A revoked   A thinks revoked       Which is truth?
in DB-A           B thinks active
```

### 8.2 Resolution Protocol

```python
class SplitBrainResolver:
    """
    Resolution rules:
    1. Revocation is STICKY - once revoked, never auto-restored
    2. Higher version wins for metadata
    3. Merge revocation lists (union)
    """

    async def resolve_partition_heal(
        self,
        local_state: TrustState,
        remote_state: TrustState
    ) -> TrustState:
        merged = TrustState()

        # Union of all revoked agents (revocation is sticky)
        merged.revoked_agents = (
            local_state.revoked_agents | remote_state.revoked_agents
        )

        # For each agent, take higher version
        all_agents = set(local_state.chains.keys()) | set(remote_state.chains.keys())
        for agent_id in all_agents:
            local_chain = local_state.chains.get(agent_id)
            remote_chain = remote_state.chains.get(agent_id)

            if agent_id in merged.revoked_agents:
                # Agent revoked - mark as revoked regardless of chain
                merged.chains[agent_id] = self._mark_revoked(
                    local_chain or remote_chain
                )
            elif local_chain and remote_chain:
                # Both have chain - take higher version
                merged.chains[agent_id] = max(
                    local_chain, remote_chain,
                    key=lambda c: c.version
                )
            else:
                # Only one has chain
                merged.chains[agent_id] = local_chain or remote_chain

        return merged
```

---

## 9. Complete Distributed Revocation Protocol Specification

### 9.1 Protocol Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED REVOCATION PROTOCOL                        │
│                                                                          │
│  Layer 4: Execution Fencing (SDK)                                        │
│  ────────────────────────────────                                        │
│  Every operation validates fencing token before commit                   │
│                                                                          │
│  Layer 3: Short-Lived Tokens (SDK + Platform)                           │
│  ────────────────────────────────────────────                           │
│  60-second tokens that must be refreshed                                 │
│                                                                          │
│  Layer 2: Push-Pull Hybrid (SDK + Platform)                             │
│  ──────────────────────────────────────────                             │
│  SSE push for immediate notification + 5-minute pull backup             │
│                                                                          │
│  Layer 1: Chain Versioning (Platform)                                    │
│  ────────────────────────────────────                                    │
│  Monotonic versions for consistency                                      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Revocation Sequence

```
T0: Authority initiates revocation for Agent X
    │
    ├─► Platform: revoke_cascade(X)
    │      │
    │      ├─► Increment chain version (v=42 → v=43)
    │      ├─► Set is_active=false
    │      ├─► Record revocation event with timestamp
    │      │
    │      └─► Broadcast via SSE (Layer 2):
    │              { agent_id: X, version: 43, revoked_at: T0 }
    │
T1: SDK receives push notification (~100ms)
    │
    ├─► Invalidate cached chain for X
    ├─► Invalidate all active tokens for X
    ├─► Mark any in-flight work for abort
    │
T2: Agent X attempts action
    │
    ├─► Get token: FAILS (token invalidated)
    │   OR
    ├─► Fencing check: FAILS (version mismatch)
    │
    └─► Action DENIED

T3: Backup pull verification (if push missed)
    │
    └─► Detects revocation via version mismatch
```

### 9.3 SDK Integration API

```python
class DistributedRevocationClient:
    """SDK client for distributed revocation protocol"""

    def __init__(self, platform_url: str):
        self._token_manager = TokenManager()
        self._push_receiver = PushReceiver(platform_url)
        self._fence_validator = FenceValidator(platform_url)
        self._version_cache = VersionCache()

    async def start(self):
        """Start all protocol layers"""
        await asyncio.gather(
            self._token_manager.start(),
            self._push_receiver.start(),
            self._version_cache.start_sync()
        )

    async def execute_with_trust(
        self,
        agent_id: str,
        operation: Callable
    ):
        """Execute operation with full revocation protection"""

        # Layer 3: Get short-lived token
        token = await self._token_manager.get_token(agent_id)

        # Layer 4: Create fencing token
        fence = FencingToken(
            agent_id=agent_id,
            chain_version=token.chain_version,
            capabilities=token.capabilities
        )

        # Execute with fencing
        return await self._fence_validator.execute_fenced(fence, operation)

    async def on_revocation_received(self, event: RevocationEvent):
        """Handler for push notifications"""
        # Invalidate token
        self._token_manager.invalidate(event.agent_id)
        # Update version cache
        self._version_cache.update(event.agent_id, event.version)
        # Abort in-flight work
        await self._abort_in_flight(event.agent_id)
```

### 9.4 Revocation Latency SLA and Acceptable Window

Zero-latency revocation is fundamentally impossible in distributed systems (CAP theorem). The following SLA defines acceptable bounds:

| Condition                   | Target   | Maximum           | Fallback Behavior                      |
| --------------------------- | -------- | ----------------- | -------------------------------------- |
| Normal (push succeeds)      | < 500ms  | 2s                | N/A                                    |
| Push failure, pull fallback | < 30s    | 60s               | Short-lived token expiry               |
| Network partition           | < 5 min  | Token TTL         | Operations blocked after token expires |
| Platform unavailable        | Degraded | Token TTL + grace | Cached trust with 60s reduced TTL      |

### 9.5 Degradation Hierarchy

When Platform connectivity is lost, the SDK follows a strict degradation path:

```
0-60s:    DEGRADED_CACHED     - Use last-known-good trust state
60s-5min: DEGRADED_RESTRICTED - Only QUICK verification, no new delegations
5min+:    BLOCKED             - All trust-dependent operations blocked
Admin:    OVERRIDE            - Authorized admin can extend degradation window
```

Each level is logged to the audit trail with timestamps, enabling post-incident analysis.

### 9.6 Commit-Time Re-Verification

To close the TOCTOU window, the SDK implements optimistic locking with commit-time re-verification:

```python
class CommitTimeVerifier:
    """Re-verify trust at commit time, not just request time."""

    async def execute_with_commit_verification(
        self, agent_id: str, action: str, operation: Callable,
    ):
        # 1. Request-time: verify trust and record version
        version_at_request = await self._get_trust_version(agent_id)
        chain = await self.trust_ops.verify(agent_id, action)
        if not chain.valid:
            raise PermissionError(f"Denied: {chain.reason}")

        # 2. Execute operation
        result = await operation()

        # 3. Commit-time: re-check version (optimistic lock)
        version_at_commit = await self._get_trust_version(agent_id)
        if version_at_commit != version_at_request:
            recheck = await self.trust_ops.verify(agent_id, action, level=FULL)
            if not recheck.valid:
                await self._compensating_rollback(result, agent_id, action)
                raise PermissionError("Trust revoked during execution. Rolled back.")

        return result

    async def _compensating_rollback(self, result, agent_id: str, action: str):
        """Saga-pattern compensating rollback with guaranteed delivery.

        If the primary rollback fails, the compensation is queued to a
        persistent dead-letter queue for eventual processing. This ensures
        no operation persists with revoked trust, even under failure.
        """
        try:
            await self._rollback(result)
            await self.audit.record("rollback_success", agent_id=agent_id, action=action)
        except Exception as rollback_error:
            # Primary rollback failed — queue for eventual compensation
            await self.audit.record(
                "rollback_failed",
                agent_id=agent_id, action=action,
                error=str(rollback_error), severity="CRITICAL",
            )
            # Enqueue to persistent dead-letter queue (survives process crash)
            await self._dead_letter_queue.enqueue(
                CompensatingAction(
                    operation_result=result,
                    agent_id=agent_id,
                    action=action,
                    reason="trust_revoked_during_execution",
                    original_error=str(rollback_error),
                    retry_count=0,
                    max_retries=10,
                    backoff_base_seconds=5,
                )
            )
            # Mark the operation as "pending_compensation" in the store
            await self._mark_pending_compensation(result)
            # Alert operations team
            await self._alert_ops(
                f"CRITICAL: Rollback failed for agent {agent_id}. "
                f"Operation queued for compensating action. "
                f"Manual intervention may be required."
            )
```

This reduces the TOCTOU window from ~5 minutes (cache TTL) to ~1-5ms (database round trip).

**Rollback failure handling**: If the primary rollback fails (database unavailable, constraint violation, network partition), the operation is enqueued to a persistent dead-letter queue with exponential backoff retry (up to 10 attempts). The operation is marked `pending_compensation` in the data store, preventing it from being treated as committed. Operations teams are alerted for manual intervention if automated compensation fails.

**Dead-Letter Queue Persistence Specification**:

The dead-letter queue (DLQ) MUST survive process crashes and container restarts. Implementation options (in priority order):

| Option                      | Persistence                          | Ordering               | Recommended For                               |
| --------------------------- | ------------------------------------ | ---------------------- | --------------------------------------------- |
| PostgreSQL table            | ACID-durable, WAL-backed             | FIFO via `enqueued_at` | Default (trust store already uses PostgreSQL) |
| Redis Streams with AOF      | Append-only file, configurable fsync | FIFO via stream ID     | High-throughput deployments                   |
| Cloud-native (SQS, Pub/Sub) | Managed durability                   | At-least-once          | Cloud-native deployments                      |

**PostgreSQL DLQ schema** (recommended default — co-located with trust store):

```sql
CREATE TABLE trust_compensation_queue (
    id              BIGSERIAL PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    action          TEXT NOT NULL,
    operation_result JSONB NOT NULL,
    reason          TEXT NOT NULL,
    original_error  TEXT,
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 10,
    next_retry_at   TIMESTAMPTZ NOT NULL,
    status          TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'dead')),
    enqueued_at     TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    CONSTRAINT valid_retry CHECK (retry_count <= max_retries)
);

CREATE INDEX idx_dlq_next_retry ON trust_compensation_queue (next_retry_at)
    WHERE status = 'pending';
```

A background worker polls this table every 5 seconds, processing entries whose `next_retry_at <= NOW()`. After `max_retries` exhausted, the entry transitions to `status = 'dead'` and a CRITICAL alert is raised for manual resolution. Backoff formula: `next_retry_at = NOW() + (backoff_base_seconds * 2^retry_count)` (capped at 1 hour).

### 9.7 Partition Recovery and Trust Restoration

The original design stated "revocation is STICKY" with no unrevoke mechanism. The hardened design adds a controlled restoration path:

1. **Detection**: Partition healing detected via heartbeat restoration
2. **Reconciliation**: Both sides exchange revocation logs
3. **Conflict resolution**: Revocation wins (conservative) unless:
   - The revocation was issued by the partitioned side only
   - AND no operations occurred using the revoked trust during partition
   - AND multi-party approval (2+ admins) authorizes restoration
4. **Audit**: All restoration events logged with full justification

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

- [ ] Implement chain versioning in TrustStore
- [ ] Add version field to verification results
- [ ] Implement version check in execute_async

### Phase 2: Short-Lived Tokens (Week 3-4)

- [ ] Design token structure and signing
- [ ] Implement TokenManager in SDK
- [ ] Implement TokenService on Platform
- [ ] Add token refresh logic

### Phase 3: Push-Pull Hybrid (Week 5-6)

- [ ] Implement SSE endpoint on Platform
- [ ] Implement PushReceiver in SDK
- [ ] Add pull verification backup
- [ ] Integrate cache invalidation

### Phase 4: Execution Fencing (Week 7-8)

- [ ] Define FencingToken structure
- [ ] Implement FenceValidator
- [ ] Add fencing to TrustedAgent.execute_async
- [ ] Document fencing requirements for resources

### Phase 5: Integration & Testing (Week 9-10)

- [ ] Integration testing with simulated partitions
- [ ] Chaos testing for revocation scenarios
- [ ] Performance benchmarking
- [ ] Documentation and runbooks
