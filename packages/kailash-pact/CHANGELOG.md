# PACT Changelog

## [0.6.0] - 2026-04-02

### Fixed

- **API error sanitization** (P-H6): All mutation endpoints now hide internal exception details
- **Envelope adapter error handling** (P-H7): PactError vs generic Exception handled separately with sanitized messages
- **NaN/Inf on operational rate limits** (P-H8/P-H9): `max_actions_per_day` and `max_actions_per_hour` validated via `math.isfinite()`
- **AuditChain integrity on deserialization** (P-H10): `from_dict()` verifies hash chain after reconstruction
- **grant_clearance D/T/R resolution** (#215): Endpoint resolves D/T/R addresses via `engine.get_node()` before granting
- **get_node non-head role resolution** (#216): Endpoint supports suffix-based address resolution

### Security

- R2 red team converged: 0 CRITICAL, 0 HIGH findings
- 1,257 tests passing, 0 regressions

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
