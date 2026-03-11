"""
Security tests for the Kaizen trust framework.

This module contains tests for constraint gaming prevention,
ensuring the trust system cannot be manipulated or bypassed.

CARE-040 Part 1: Key extraction resistance tests validate that cryptographic
key material is protected from exposure through common attack vectors:
- String representation (str/repr)
- Serialization (to_dict/JSON)
- Memory cleanup
- Storage encryption
- Logging
- Exception messages

CARE-040 Part 2: Delegation chain manipulation tests validate that:
- Agents cannot delegate capabilities they don't own
- Constraints can only be tightened, never weakened
- Expirations cannot be extended beyond parent
- Tampered signatures are rejected
- Injected delegations are rejected
- Hash chain integrity is verified
"""
