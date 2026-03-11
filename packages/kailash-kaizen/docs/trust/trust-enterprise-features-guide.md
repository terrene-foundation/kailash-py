# Trust System Enterprise Features Guide

This guide covers the Phase 5 P2 enterprise trust features for the EATP (Enterprise Agent Trust Protocol) trust system. These features extend the production readiness foundation (Phase 5 P1) with enterprise-grade governance, verification, and non-repudiation capabilities.

## Overview

The Phase 5 P2 features provide enterprise governance and verification:

| Feature                      | CARE ID  | Purpose                                  |
| ---------------------------- | -------- | ---------------------------------------- |
| Multi-Signature Genesis      | CARE-011 | M-of-N approval for critical agent setup |
| Merkle Tree Audit            | CARE-012 | Efficient audit log verification         |
| Certificate Revocation List  | CARE-013 | Offline-capable revocation checking      |
| External Timestamp Anchoring | CARE-014 | Non-repudiation via external TSA         |

---

## Multi-Signature Genesis (CARE-011)

Requires M-of-N signatures for critical agent establishment. Example: 3-of-5 board members must approve before an AI agent receives financial authority.

### Why Multi-Signature Matters

High-stakes agent deployments require distributed approval:

- **Separation of duties**: No single person can authorize critical agents
- **Audit requirements**: Prove multiple stakeholders approved
- **Risk reduction**: Compromised credentials alone insufficient
- **Compliance**: Meet SOX, GDPR data protection officer requirements

### MultiSigPolicy

Define the signing requirements:

```python
from kaizen.trust.multi_sig import MultiSigPolicy
from kaizen.trust.key_manager import InMemoryKeyManager

# Create key manager and generate keys for signers
key_manager = InMemoryKeyManager()
signer_keys = {}
for signer_id in ["alice", "bob", "carol", "dave", "eve"]:
    _, public_key = await key_manager.generate_keypair(signer_id)
    signer_keys[signer_id] = public_key

# Define 3-of-5 policy
policy = MultiSigPolicy(
    required_signatures=3,   # M: minimum signatures needed
    total_signers=5,         # N: total authorized signers
    signer_public_keys=signer_keys,  # Map of signer_id -> public_key
    expiry_hours=24,         # Pending operations expire after 24 hours
)

# Policy validation happens automatically
# - required_signatures must be <= total_signers
# - required_signatures must be >= 1
# - len(signer_public_keys) must equal total_signers

# Serialize for storage/transmission
policy_dict = policy.to_dict()

# Restore from dictionary
restored_policy = MultiSigPolicy.from_dict(policy_dict)
```

### MultiSigManager

Orchestrate the signing ceremony:

```python
from kaizen.trust.multi_sig import (
    MultiSigManager,
    create_genesis_payload,
)

# Create genesis payload for signing
genesis_data = {
    "agent_id": "financial-agent-001",
    "authority_id": "org-acme",
    "capabilities": ["approve_invoices", "transfer_funds"],
    "constraints": {"cost_limit": 100000},
}
genesis_payload = create_genesis_payload(genesis_data)

# Create manager with key verification
manager = MultiSigManager(key_manager=key_manager)

# Initiate signing operation
pending = manager.initiate_genesis_signing(genesis_payload, policy)
print(f"Operation ID: {pending.operation_id}")
print(f"Expires at: {pending.expires_at}")
print(f"Signatures needed: {pending.remaining_signatures()}")
print(f"Pending signers: {pending.pending_signers()}")
```

### Collecting Signatures

```python
from kaizen.trust.multi_sig import (
    UnauthorizedSignerError,
    DuplicateSignatureError,
    SigningOperationExpiredError,
)

# Each authorized signer adds their signature
for signer_id in ["alice", "bob", "carol"]:
    # In practice, each signer signs independently
    signature = await key_manager.sign(genesis_payload, signer_id)

    try:
        pending = manager.add_signature(
            operation_id=pending.operation_id,
            signer_id=signer_id,
            signature=signature,
        )
        print(f"{signer_id} signed. Remaining: {pending.remaining_signatures()}")
    except UnauthorizedSignerError:
        print(f"{signer_id} is not authorized to sign")
    except DuplicateSignatureError:
        print(f"{signer_id} already signed")
    except SigningOperationExpiredError as e:
        print(f"Operation expired at {e.expired_at}")
```

### Completing the Signing

```python
from kaizen.trust.multi_sig import InsufficientSignaturesError

# Check if quorum is reached
if pending.is_complete():
    # Complete and get combined signature
    combined_signature = manager.complete_genesis_signing(pending.operation_id)
    print(f"Combined signature: {combined_signature}")
    # Output: {"type":"multisig","threshold":"3/5","signatures":{...}}
else:
    print(f"Need {pending.remaining_signatures()} more signatures")

# Attempting to complete without quorum raises error
try:
    manager.complete_genesis_signing(pending.operation_id)
except InsufficientSignaturesError as e:
    print(f"Have {e.current}/{e.required} signatures")
```

### Verifying Multi-Signatures

```python
from kaizen.trust.multi_sig import verify_multi_sig

# Later, verify the combined signature
is_valid = verify_multi_sig(
    payload=genesis_payload,
    combined_signature=combined_signature,
    policy=policy,
    key_manager=key_manager,  # For cryptographic verification
)
assert is_valid

# Without key_manager, only structure is validated
is_valid_structure = verify_multi_sig(
    payload=genesis_payload,
    combined_signature=combined_signature,
    policy=policy,
    key_manager=None,  # Skips cryptographic verification
)
```

### PendingMultiSig Operations

```python
# Query pending operations
pending = manager.get_pending(operation_id)
if pending:
    print(f"Is complete: {pending.is_complete()}")
    print(f"Is expired: {pending.is_expired()}")
    print(f"Signers who signed: {list(pending.signatures.keys())}")
    print(f"Signers who haven't: {pending.pending_signers()}")

# List all pending operations
all_pending = manager.list_pending()
for op in all_pending:
    print(f"{op.operation_id}: {len(op.signatures)}/{op.policy.required_signatures}")

# Cancel a pending operation
cancelled = manager.cancel(operation_id)

# Clean up expired operations
removed_count = manager.cleanup_expired()
print(f"Removed {removed_count} expired operations")

# Serialize pending operation for storage
pending_dict = pending.to_dict()
restored = PendingMultiSig.from_dict(pending_dict)
```

---

## Merkle Tree Audit Verification (CARE-012)

Efficient verification of audit log integrity using Merkle proofs. Prove a specific audit entry exists without downloading the entire log.

### Why Merkle Proofs Matter

Audit logs can grow to millions of entries. Merkle trees provide:

- **O(log n) proofs**: Verify inclusion with ~20 hashes for 1M records
- **Selective disclosure**: Prove one record without revealing others
- **Tamper detection**: Any modification changes the root hash
- **Bandwidth efficiency**: Transmit proofs, not entire logs

### Building a Merkle Tree

```python
from kaizen.trust.merkle import MerkleTree, MerkleProof

# Build from a list of hashes
leaf_hashes = [
    "abc123...",  # Hash of audit record 0
    "def456...",  # Hash of audit record 1
    "ghi789...",  # Hash of audit record 2
    "jkl012...",  # Hash of audit record 3
]
tree = MerkleTree(leaves=leaf_hashes)

# Get the root hash (fingerprint of entire tree)
root_hash = tree.root_hash
print(f"Root hash: {root_hash}")
print(f"Leaf count: {tree.leaf_count}")

# Get a specific leaf
leaf = tree.get_leaf(2)  # Returns "ghi789..."
```

### Integration with AuditRecord

```python
from kaizen.trust.audit_store import AppendOnlyAuditStore, AuditRecord
from kaizen.trust.merkle import MerkleTree

# Get audit records
store = AppendOnlyAuditStore()
records = await store.list_records(limit=1000)

# Build tree from integrity hashes
tree = MerkleTree.from_audit_records(records)
print(f"Merkle root for {tree.leaf_count} audit records: {tree.root_hash}")
```

### Generating Proofs

```python
# Generate proof for a specific leaf
index = 5  # Prove the 6th record exists
proof = tree.generate_proof(index)

print(f"Leaf hash: {proof.leaf_hash}")
print(f"Leaf index: {proof.leaf_index}")
print(f"Root hash: {proof.root_hash}")
print(f"Tree size: {proof.tree_size}")
print(f"Proof path length: {len(proof.proof_hashes)}")

# Each proof hash includes position (left or right)
for sibling_hash, position in proof.proof_hashes:
    print(f"  {position}: {sibling_hash[:16]}...")
```

### Verifying Proofs

```python
from kaizen.trust.merkle import verify_merkle_proof

# Verify using the standalone function (no tree needed)
leaf_hash = proof.leaf_hash
is_valid = verify_merkle_proof(leaf_hash, proof)
assert is_valid

# Verify against the tree (also checks tree hasn't changed)
is_valid = tree.verify_proof(proof)
assert is_valid

# If tree was modified after proof generation, verification fails
tree.add_leaf("new_hash...")
is_still_valid = tree.verify_proof(proof)  # False: root changed
```

### Incremental Tree Building

```python
# Start with empty tree
tree = MerkleTree()

# Add leaves one at a time
for record in audit_records:
    tree.add_leaf(record.integrity_hash)

# Note: Adding leaves invalidates existing proofs
# Generate new proofs after all additions
```

### Serialization

```python
# Serialize tree metadata
tree_dict = tree.to_dict()
# {
#   "root_hash": "...",
#   "leaf_count": 1000,
#   "leaves": ["hash1", "hash2", ...],
#   "version": "1.0"
# }

# Restore tree
restored_tree = MerkleTree.from_dict(tree_dict)

# Serialize proof
proof_dict = proof.to_dict()
# {
#   "leaf_hash": "...",
#   "leaf_index": 5,
#   "proof_hashes": [{"hash": "...", "position": "right"}, ...],
#   "root_hash": "...",
#   "tree_size": 1000
# }

# Restore proof
restored_proof = MerkleProof.from_dict(proof_dict)
```

### Utility Functions

```python
from kaizen.trust.merkle import compute_merkle_root, get_proof_length

# Quick root computation without building full tree
root = compute_merkle_root(["hash1", "hash2", "hash3", "hash4"])

# Calculate expected proof length for a tree size
proof_len = get_proof_length(1_000_000)  # ~20 hashes
print(f"Proof for 1M records needs {proof_len} hashes")
```

---

## Certificate Revocation List (CARE-013)

Offline-capable revocation checking through cacheable snapshots. Unlike real-time revocation broadcasting (CARE-007), CRLs can be cached and checked without network access.

### Why CRL Matters

Real-time revocation checking requires network connectivity. CRLs provide:

- **Offline operation**: Check revocations without network access
- **Reduced latency**: Cache CRL locally for fast lookups
- **Distribution**: Distribute signed CRL snapshots to edge nodes
- **Standard compliance**: Familiar pattern from X.509 PKI

### CertificateRevocationList

```python
from kaizen.trust.crl import (
    CertificateRevocationList,
    CRLEntry,
    CRLMetadata,
)
from datetime import datetime, timezone, timedelta

# Create CRL
crl = CertificateRevocationList(
    issuer_id="org-acme",
    cache_ttl_seconds=3600,  # 1 hour cache validity
)

# CRL metadata
print(f"CRL ID: {crl.metadata.crl_id}")
print(f"Issuer: {crl.metadata.issuer_id}")
print(f"Issued at: {crl.metadata.issued_at}")
print(f"Next update: {crl.metadata.next_update}")
```

### Adding Revocations

```python
# Revoke a delegation
entry = crl.add_revocation(
    delegation_id="del-001",
    agent_id="agent-001",
    reason="Key compromise detected",
    revoked_by="security-admin",
    expires_at=None,  # Optional: when entry expires from CRL
)

print(f"Revoked: {entry.delegation_id}")
print(f"Agent: {entry.agent_id}")
print(f"Revoked at: {entry.revoked_at}")
print(f"Reason: {entry.reason}")
print(f"By: {entry.revoked_by}")

# Add more revocations
crl.add_revocation("del-002", "agent-002", "Policy violation", "admin")
crl.add_revocation("del-003", "agent-001", "Secondary delegation", "admin")

print(f"Total entries: {crl.entry_count}")
```

### Checking Revocation Status

```python
# Check by delegation ID
if crl.is_revoked("del-001"):
    entry = crl.get_entry("del-001")
    print(f"Delegation {entry.delegation_id} revoked: {entry.reason}")

# Check by agent ID (any delegation revoked?)
if crl.is_agent_revoked("agent-001"):
    entries = crl.get_entries_for_agent("agent-001")
    print(f"Agent has {len(entries)} revoked delegations")
    for entry in entries:
        print(f"  - {entry.delegation_id}: {entry.reason}")
```

### Convenience Function

```python
from kaizen.trust.crl import verify_delegation_with_crl, CRLVerificationResult

result = verify_delegation_with_crl("del-001", crl)

if result.valid:
    print("Delegation is not revoked")
else:
    print(f"Delegation revoked: {result.reason}")
    print(f"Entry: {result.entry}")
```

### CRL Signing and Verification

```python
from kaizen.trust.crypto import generate_keypair

# Generate signing keys for CRL issuer
private_key, public_key = generate_keypair()

# Sign the CRL
signature = crl.sign(private_key)
print(f"CRL signed: {signature[:32]}...")

# Verify CRL signature (e.g., after distribution)
is_valid = crl.verify_signature(public_key)
assert is_valid

# Modifying CRL invalidates signature
crl.add_revocation("del-004", "agent-004", "New revocation", "admin")
is_still_valid = crl.verify_signature(public_key)  # False
```

### CRL Serialization and Distribution

```python
# Serialize for distribution
crl_dict = crl.to_dict()
# {
#   "metadata": {...},
#   "entries": [...],
#   "agent_index": {...},
#   "cache_ttl_seconds": 3600,
#   "last_refresh": "...",
#   "version": "1.0"
# }

# Restore at receiving node
received_crl = CertificateRevocationList.from_dict(crl_dict)

# Human-readable format for debugging
print(crl.export_pem_style())
# -----BEGIN CERTIFICATE REVOCATION LIST-----
# CRL ID: crl-abc123...
# Issuer: org-acme
# ...
# -----END CERTIFICATE REVOCATION LIST-----
```

### Cache Management

```python
# Check cache validity
if not crl.is_cache_valid():
    print("CRL cache expired, refresh needed")
    # Fetch updated CRL from authority...

# Clean up expired entries
removed = crl.cleanup_expired()
print(f"Removed {removed} expired CRL entries")

# Remove specific revocation (for CRL maintenance)
was_removed = crl.remove_revocation("del-001")
```

### Sync with Real-Time Broadcaster

```python
from kaizen.trust.revocation.broadcaster import InMemoryRevocationBroadcaster

# CRL can sync from real-time broadcaster for hybrid approach
broadcaster = InMemoryRevocationBroadcaster()
# ... broadcaster receives real-time events ...

# Refresh CRL from broadcaster history
added = crl.refresh_from_broadcaster(broadcaster.get_history())
print(f"Added {added} entries from broadcaster")
```

### Listing and Pagination

```python
# List entries with pagination
entries = crl.list_entries(limit=100, offset=0)
for entry in entries:
    print(f"{entry.delegation_id}: {entry.reason}")
```

---

## External Timestamp Anchoring (CARE-014)

Anchor trust chain hashes to external timestamping authorities for non-repudiation. Proves a specific trust state existed at a verified point in time.

### Why External Timestamps Matter

Local timestamps can be forged. External timestamping provides:

- **Non-repudiation**: Third-party proof of when data existed
- **Legal evidence**: Admissible in court proceedings
- **Compliance**: Meet regulatory timestamping requirements
- **Audit trail**: Prove when trust chain state was established

### TimestampAuthority Interface

```python
from kaizen.trust.timestamping import (
    TimestampAuthority,
    TimestampToken,
    TimestampRequest,
    TimestampResponse,
    TimestampSource,
)

# All authorities implement this interface
class TimestampAuthority(ABC):
    async def get_timestamp(
        self, hash_value: str, nonce: Optional[str] = None
    ) -> TimestampResponse:
        """Get a timestamp for a hash value."""

    async def verify_timestamp(self, token: TimestampToken) -> bool:
        """Verify a timestamp token."""

    @property
    def authority_url(self) -> str:
        """URL or identifier for this authority."""
```

### LocalTimestampAuthority

For development and fallback:

```python
from kaizen.trust.timestamping import LocalTimestampAuthority

# Create with auto-generated keys
authority = LocalTimestampAuthority()

# Or with specific keys
authority = LocalTimestampAuthority(
    signing_key=private_key_base64,
    verify_key=public_key_base64,
)

# Get public key for verification
print(f"Public key: {authority.public_key}")

# Get timestamp for a hash
response = await authority.get_timestamp("abc123def456...")

# Access the token
token = response.token
print(f"Token ID: {token.token_id}")
print(f"Hash: {token.hash_value}")
print(f"Timestamp: {token.timestamp}")
print(f"Source: {token.source}")  # TimestampSource.LOCAL
print(f"Authority: {token.authority}")  # "local"
print(f"Signature: {token.signature}")
print(f"Nonce: {token.nonce}")
print(f"Serial: {token.serial_number}")
print(f"Accuracy: {token.accuracy_microseconds}us")

# Verify the token
is_valid = await authority.verify_timestamp(token)
assert is_valid
```

### RFC3161TimestampAuthority

For production use with external TSA:

```python
from kaizen.trust.timestamping import RFC3161TimestampAuthority

# Configure external TSA endpoint
authority = RFC3161TimestampAuthority(
    tsa_url="https://timestamp.digicert.com",
    timeout_seconds=10,
)

# Note: This is a stub - full implementation requires additional dependencies
# The interface is ready for production TSA integration
try:
    response = await authority.get_timestamp("abc123...")
except NotImplementedError:
    print("RFC 3161 requires additional dependencies")
    print("Use LocalTimestampAuthority for development")
```

### TimestampAnchorManager

Manage timestamp anchoring with fallback chain:

```python
from kaizen.trust.timestamping import (
    TimestampAnchorManager,
    LocalTimestampAuthority,
    RFC3161TimestampAuthority,
)

# Create primary and fallback authorities
primary = RFC3161TimestampAuthority("https://timestamp.example.com")
secondary = RFC3161TimestampAuthority("https://backup-tsa.example.com")
local = LocalTimestampAuthority()

# Create manager with fallback chain
manager = TimestampAnchorManager(
    primary=primary,           # Try first
    fallbacks=[secondary],     # Try if primary fails
    local_fallback=True,       # Use local if all external fail
)

# Alternatively, simple setup for development
manager = TimestampAnchorManager()  # Uses LocalTimestampAuthority

# Query configuration
print(f"Primary: {manager.primary_authority.authority_url}")
print(f"Fallbacks: {len(manager.fallback_authorities)}")
print(f"Local fallback: {manager.has_local_fallback}")
```

### Anchoring Hashes

```python
# Anchor a hash (tries primary, then fallbacks, then local)
hash_value = "abc123def456..."
response = await manager.anchor_hash(hash_value)

print(f"Anchored at: {response.token.timestamp}")
print(f"Authority used: {response.token.authority}")
print(f"Verified: {response.verified}")
```

### Anchoring Merkle Roots

```python
from kaizen.trust.merkle import MerkleTree

# Build Merkle tree from audit records
tree = MerkleTree.from_audit_records(audit_records)

# Anchor the root hash
response = await manager.anchor_merkle_root(tree)

print(f"Anchored Merkle root: {tree.root_hash}")
print(f"Timestamp: {response.token.timestamp}")

# This proves all records in the tree existed at the timestamp
```

### Verifying Anchors

```python
# Verify a timestamp anchor
is_valid = await manager.verify_anchor(response)
assert is_valid

# Uses the appropriate authority based on token source
# Returns False for unknown authorities
```

### Anchor History

```python
# Get all anchors
history = manager.get_history()
for resp in history:
    print(f"{resp.token.timestamp}: {resp.token.hash_value[:16]}...")

# Get most recent anchor
latest = manager.get_latest_anchor()
if latest:
    print(f"Last anchor: {latest.token.timestamp}")

# Clear history
manager.clear_history()
```

### Serialization

```python
# Serialize token
token_dict = token.to_dict()
restored_token = TimestampToken.from_dict(token_dict)

# Serialize full response
response_dict = response.to_dict()
restored_response = TimestampResponse.from_dict(response_dict)
```

### Standalone Verification

```python
from kaizen.trust.timestamping import verify_timestamp_token

# Verify token directly with an authority
is_valid = await verify_timestamp_token(token, authority)
```

---

## Integration Example

This example demonstrates using all Phase 5 P2 features together:

```python
import asyncio
from datetime import datetime, timezone
from kaizen.trust.key_manager import InMemoryKeyManager
from kaizen.trust.multi_sig import (
    MultiSigPolicy,
    MultiSigManager,
    create_genesis_payload,
    verify_multi_sig,
)
from kaizen.trust.merkle import MerkleTree, verify_merkle_proof
from kaizen.trust.crl import (
    CertificateRevocationList,
    verify_delegation_with_crl,
)
from kaizen.trust.timestamping import (
    LocalTimestampAuthority,
    TimestampAnchorManager,
)
from kaizen.trust.audit_store import AppendOnlyAuditStore
from kaizen.trust.chain import AuditAnchor, ActionResult


async def enterprise_trust_demo():
    """Demonstrate Phase 5 P2 enterprise trust features."""

    # ==========================================================
    # 1. Multi-Signature Genesis - Board approval for AI agent
    # ==========================================================
    print("=== Multi-Signature Genesis ===")

    # Set up key manager with board members
    key_manager = InMemoryKeyManager()
    board_members = ["ceo", "cfo", "cto", "ciso", "legal"]
    signer_keys = {}
    for member in board_members:
        _, public_key = await key_manager.generate_keypair(member)
        signer_keys[member] = public_key

    # Define 3-of-5 approval policy
    policy = MultiSigPolicy(
        required_signatures=3,
        total_signers=5,
        signer_public_keys=signer_keys,
        expiry_hours=72,  # 3 days for board to approve
    )

    # Create genesis payload for financial agent
    genesis_data = {
        "agent_id": "financial-agent-001",
        "authority_id": "acme-corp",
        "capabilities": ["approve_invoices", "process_payments"],
        "constraints": {"cost_limit": 500000, "daily_limit": 100000},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    genesis_payload = create_genesis_payload(genesis_data)

    # Initiate multi-sig signing
    manager = MultiSigManager(key_manager=key_manager)
    pending = manager.initiate_genesis_signing(genesis_payload, policy)
    print(f"Operation initiated: {pending.operation_id}")
    print(f"Requires {pending.remaining_signatures()} of {policy.total_signers} signatures")

    # Collect signatures (in practice, each member signs independently)
    approvers = ["ceo", "cfo", "ciso"]
    for member in approvers:
        signature = await key_manager.sign(genesis_payload, member)
        pending = manager.add_signature(pending.operation_id, member, signature)
        print(f"  {member.upper()} approved")

    # Complete multi-sig
    combined_sig = manager.complete_genesis_signing(pending.operation_id)
    print(f"Genesis approved with combined signature")

    # Verify multi-sig (can be done later by any party)
    is_valid = verify_multi_sig(genesis_payload, combined_sig, policy, key_manager)
    print(f"Multi-sig verification: {'VALID' if is_valid else 'INVALID'}")

    # ==========================================================
    # 2. Audit with Merkle Tree Verification
    # ==========================================================
    print("\n=== Merkle Tree Audit Verification ===")

    # Create audit store and record agent actions
    _, agent_public = await key_manager.generate_keypair("financial-agent-001")
    audit_store = AppendOnlyAuditStore()

    # Simulate agent actions
    actions = [
        ("approve_invoice", "inv-001", 15000),
        ("approve_invoice", "inv-002", 25000),
        ("process_payment", "pay-001", 15000),
        ("approve_invoice", "inv-003", 8500),
        ("process_payment", "pay-002", 25000),
    ]

    for action, resource, amount in actions:
        anchor = AuditAnchor(
            id=f"aud-{resource}",
            agent_id="financial-agent-001",
            action=action,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="chain-hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=await key_manager.sign(f"{action}:{resource}", "financial-agent-001"),
            resource=resource,
            context={"amount": amount},
        )
        await audit_store.append(anchor)

    # Build Merkle tree from audit records
    records = await audit_store.list_records(limit=100)
    tree = MerkleTree.from_audit_records(records)
    print(f"Built Merkle tree with {tree.leaf_count} records")
    print(f"Root hash: {tree.root_hash[:32]}...")

    # Generate proof for specific record (e.g., auditor wants proof of inv-002)
    proof = tree.generate_proof(1)  # Second record
    print(f"Generated proof for record at index 1")
    print(f"Proof path length: {len(proof.proof_hashes)} hashes")

    # Verify proof (auditor can verify without full log)
    is_valid = verify_merkle_proof(proof.leaf_hash, proof)
    print(f"Proof verification: {'VALID' if is_valid else 'INVALID'}")

    # ==========================================================
    # 3. Certificate Revocation List
    # ==========================================================
    print("\n=== Certificate Revocation List ===")

    # Create and populate CRL
    crl = CertificateRevocationList(issuer_id="acme-corp")

    # Revoke a compromised delegation
    crl.add_revocation(
        delegation_id="del-legacy-001",
        agent_id="legacy-agent-001",
        reason="Agent deprecated - replaced by financial-agent-001",
        revoked_by="cto",
    )

    crl.add_revocation(
        delegation_id="del-temp-001",
        agent_id="temp-contractor-agent",
        reason="Contract ended",
        revoked_by="hr-system",
    )

    print(f"CRL has {crl.entry_count} entries")

    # Sign CRL for distribution
    _, crl_public = await key_manager.generate_keypair("crl-issuer")
    crl_private, _ = key_manager.get_key("crl-issuer"), crl_public
    crl.sign(key_manager._keys["crl-issuer"])
    print(f"CRL signed by issuer")

    # Check delegation status
    result = verify_delegation_with_crl("del-legacy-001", crl)
    print(f"del-legacy-001: {'REVOKED' if not result.valid else 'VALID'}")
    if not result.valid:
        print(f"  Reason: {result.reason}")

    result = verify_delegation_with_crl("del-financial-001", crl)
    print(f"del-financial-001: {'REVOKED' if not result.valid else 'VALID'}")

    # ==========================================================
    # 4. External Timestamp Anchoring
    # ==========================================================
    print("\n=== External Timestamp Anchoring ===")

    # Create timestamp manager (using local for demo)
    ts_authority = LocalTimestampAuthority()
    ts_manager = TimestampAnchorManager(primary=ts_authority)

    # Anchor the Merkle root for non-repudiation
    anchor_response = await ts_manager.anchor_merkle_root(tree)
    print(f"Merkle root anchored at: {anchor_response.token.timestamp}")
    print(f"Authority: {anchor_response.token.authority}")
    print(f"Token ID: {anchor_response.token.token_id}")

    # Verify the anchor
    is_valid = await ts_manager.verify_anchor(anchor_response)
    print(f"Timestamp verification: {'VALID' if is_valid else 'INVALID'}")

    # Anchor the multi-sig genesis for proof of approval time
    genesis_anchor = await ts_manager.anchor_hash(combined_sig)
    print(f"\nGenesis approval timestamped at: {genesis_anchor.token.timestamp}")

    # ==========================================================
    # Summary
    # ==========================================================
    print("\n=== Summary ===")
    print(f"1. Genesis approved by {len(approvers)} of {policy.total_signers} board members")
    print(f"2. {tree.leaf_count} audit records in Merkle tree (root: {tree.root_hash[:16]}...)")
    print(f"3. CRL contains {crl.entry_count} revoked delegations")
    print(f"4. Trust state anchored at {anchor_response.token.timestamp}")

    print("\nPhase 5 P2 Enterprise Trust Demo Complete!")


if __name__ == "__main__":
    asyncio.run(enterprise_trust_demo())
```

---

## API Reference

### Quick Import Reference

| Component                      | Import Path                 |
| ------------------------------ | --------------------------- |
| `MultiSigPolicy`               | `kaizen.trust.multi_sig`    |
| `PendingMultiSig`              | `kaizen.trust.multi_sig`    |
| `MultiSigManager`              | `kaizen.trust.multi_sig`    |
| `verify_multi_sig`             | `kaizen.trust.multi_sig`    |
| `create_genesis_payload`       | `kaizen.trust.multi_sig`    |
| `MultiSigError`                | `kaizen.trust.multi_sig`    |
| `InsufficientSignaturesError`  | `kaizen.trust.multi_sig`    |
| `SigningOperationExpiredError` | `kaizen.trust.multi_sig`    |
| `UnauthorizedSignerError`      | `kaizen.trust.multi_sig`    |
| `DuplicateSignatureError`      | `kaizen.trust.multi_sig`    |
| `OperationNotFoundError`       | `kaizen.trust.multi_sig`    |
| `MerkleTree`                   | `kaizen.trust.merkle`       |
| `MerkleNode`                   | `kaizen.trust.merkle`       |
| `MerkleProof`                  | `kaizen.trust.merkle`       |
| `verify_merkle_proof`          | `kaizen.trust.merkle`       |
| `compute_merkle_root`          | `kaizen.trust.merkle`       |
| `get_proof_length`             | `kaizen.trust.merkle`       |
| `CertificateRevocationList`    | `kaizen.trust.crl`          |
| `CRLEntry`                     | `kaizen.trust.crl`          |
| `CRLMetadata`                  | `kaizen.trust.crl`          |
| `CRLVerificationResult`        | `kaizen.trust.crl`          |
| `verify_delegation_with_crl`   | `kaizen.trust.crl`          |
| `TimestampAuthority`           | `kaizen.trust.timestamping` |
| `LocalTimestampAuthority`      | `kaizen.trust.timestamping` |
| `RFC3161TimestampAuthority`    | `kaizen.trust.timestamping` |
| `TimestampAnchorManager`       | `kaizen.trust.timestamping` |
| `TimestampToken`               | `kaizen.trust.timestamping` |
| `TimestampRequest`             | `kaizen.trust.timestamping` |
| `TimestampResponse`            | `kaizen.trust.timestamping` |
| `TimestampSource`              | `kaizen.trust.timestamping` |
| `verify_timestamp_token`       | `kaizen.trust.timestamping` |

---

## See Also

- [Trust Production Readiness Guide](./trust-production-readiness-guide.md) - Phase 5 P1 features
- [EATP Architecture](../architecture/eatp-architecture.md) - Full EATP protocol specification
- [Trust System Overview](../trust/README.md) - Trust module documentation
- [Security Best Practices](../guides/eatp-security-best-practices.md) - Security recommendations
