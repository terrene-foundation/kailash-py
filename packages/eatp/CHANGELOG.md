# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-11

### Added

- Core EATP protocol implementation with 5 chain elements (GenesisRecord, CapabilityAttestation, DelegationRecord, ConstraintEnvelope, AuditAnchor) and 4 operations (ESTABLISH, DELEGATE, VERIFY, AUDIT)
- Ed25519 cryptography via PyNaCl for signing, verification, and key generation
- `TrustOperations` class implementing all four trust lifecycle operations
- `TrustKeyManager` for in-memory key management with signing and verification
- `InMemoryKeyManager` (CARE-005) with HSM/KMS interface abstraction and security protections against accidental key exposure
- `InMemoryTrustStore` with transaction support (CARE-008) for atomic chain re-signing
- `FilesystemStore` for persistent local trust chain storage
- Constraint system with 5 dimensions (scope, financial, temporal, communication, data access) and `MultiDimensionEvaluator`
- 6 built-in constraint templates: governance, finance, community, standards, audit, minimal
- Spend tracking and commerce constraints for financial operations
- Constraint inheritance validation with tightening-only rule (CARE-009)
- `StrictEnforcer` for production enforcement with configurable BLOCKED/HELD/FLAGGED/AUTO_APPROVED verdicts
- `ShadowEnforcer` for observation-mode enforcement with metrics collection and reporting
- Enforcement decorators (`@verified`, `@audited`, `@shadow`) for 3-line function integration
- Trust postures: 5-level state machine (FULL_AUTONOMY, ASSISTED, SUPERVISED, HUMAN_DECIDES, BLOCKED) with transition rules
- Trust scoring: deterministic 0-100 composite score across chain completeness, delegation depth, constraint coverage, posture level, and chain recency
- Interoperability: JWT export/import (RFC 7519), W3C Verifiable Credentials, DID (Decentralized Identifiers), UCAN v0.10.0 delegation tokens, SD-JWT selective disclosure, Biscuit attenuation tokens
- MCP server for AI agent integration via standard MCP tool calls
- CLI with 10 commands: init, establish, delegate, verify, revoke, status, audit, export, verify-chain, version
- Challenge-response protocol for live trust verification
- Selective disclosure for privacy-preserving audit exports
- Merkle tree audit verification for efficient integrity checking
- Wire format JSON Schemas for protocol interoperability
- Maximum delegation depth enforcement (CARE-004) to prevent DoS via deep chains
- Human-origin traceability through `ExecutionContext` and `HumanOrigin` propagation
- Cryptographic chain hashing with per-chain salts (CARE-001) for rainbow table protection
- Key rotation support with verification grace periods
- Certificate Revocation List (CRL) support
- Circuit breaker pattern for resilient trust verification
- Comprehensive test suite with pytest-asyncio and Hypothesis property testing
