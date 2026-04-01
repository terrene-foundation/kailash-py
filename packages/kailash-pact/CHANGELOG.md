# PACT Changelog

## [0.5.0] - 2026-03-30

### Added

- **PactEngine facade**: Dual Plane bridge with progressive disclosure (v0.4.0 → v0.5.0)
- **Bridge LCA Approval** (#168): `create_bridge()` requires lowest common ancestor approval with 24h expiry
- **Vacancy Enforcement** (#169): `verify_action()` checks vacancy status before envelope checks
- **Dimension-Scoped Delegation** (#170): `DelegationRecord.dimension_scope` for delegations scoped to specific constraint dimensions
- **CostModel** (#66): Per-model cost rates wired to GovernedSupervisor and `/cost` handler
- **External HELD mechanism** (#61): `GovernanceHeldError` catch, `resolve_hold()`, `asyncio.Event` gate
- **ConstraintEnvelopeConfig** (#59): Pydantic-based configuration replacing raw dataclass
- **DataClassification → ConfidentialityLevel** (#60): CARE terminology alignment across 12+ files
- **22 governance modules** (#63): Moved to `src/kailash/trust/pact/` (api/cli/mcp stay in kailash-pact)
- **/compact and /plan handlers** (#65): Sync message pruning and GovernedSupervisor display

### Fixed

- **internal_only Enforcement** (#179): Only explicitly external actions blocked for internal-only agents
- **Session file permissions** (#68): 0o600/0o700 with atomic writes via `os.open`

### Security

- Red team converged: all HIGH/MEDIUM findings fixed (thread safety, NaN validation, bounded collections, TOCTOU, fuzzy match)
- 189 new tests, 3,243 total passing
