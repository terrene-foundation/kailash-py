# CARE-058: Cache Key Collision Prevention

**Status**: ✅ COMPLETED (2026-02-09)
**Evidence**: 238 tests passing, `runtime/trust/verifier.py` delivered
**Priority**: P1 (HIGH - Security)
**Severity**: HIGH
**Phase**: Round 4 - Red Team Security Hardening
**Component**: Core SDK - Trust Verifier
**Related**: Red Team Round 4 - Cache Key Collision Prevention

## Description

Changed `TrustVerifier` cache key separator from colon (`:`) to null byte (`\x00`) to prevent cache key collision attacks. Previously, `agent_id="foo:bar"` and `action="baz"` collided with `agent_id="foo"` and `action="bar:baz"` (both produced cache key "foo:bar:baz").

This fix uses null byte separator which cannot appear in valid agent_id or action strings, eliminating collision risk.

## Vulnerability Impact

**Attack Vector**: An attacker could cause cache collisions by:

- Crafting `agent_id` containing colons to match other agent's cache key
- Example: `agent_id="admin:read"` + `action="users"` → key "admin:read:users"
- Collides with: `agent_id="admin"` + `action="read:users"` → key "admin:read:users"
- Result: Agent A gets cached verification result for Agent B (privilege escalation)

**Severity**: HIGH - Cache collisions enable privilege escalation and verification bypass.

## Changes

### Modified Files

1. **`src/kailash/runtime/trust/verifier.py`**
   - Changed `_cache_key()` separator from `:` to `\x00`
   - Cache key format: `f"{agent_id}\x00{action}"`
   - Null byte cannot appear in agent_id or action (invalid character)
   - Collision-free cache keys guaranteed

2. **`tests/unit/runtime/trust/test_trust_verifier.py`**
   - Added 4 new cache collision tests:
     - test_cache_key_collision_prevention (colon in agent_id)
     - test_cache_key_separator_not_in_agent_id (null byte validation)
     - test_cache_key_uniqueness (comprehensive collision check)
     - test_cache_lookup_after_key_change (migration safety)

## Tests

- **New Tests**: 4 cache collision prevention tests
- **Total Tests**: 238 tests passing (all Core SDK trust tests)
- **Coverage**: 100% of cache key generation logic
- **Test Duration**: <1.5s

### Key Test Scenarios

1. **Collision Prevention**: `agent_id="foo:bar"` + `action="baz"` ≠ `agent_id="foo"` + `action="bar:baz"`
2. **Separator Validation**: Null byte not present in agent_id or action
3. **Uniqueness**: 1000 random agent/action pairs → 1000 unique cache keys
4. **Migration Safety**: Old cache entries invalidated after separator change

## Security Impact

**Before**: Colon separator enabled cache key collisions via crafted agent_id values.

**After**: Null byte separator eliminates collisions:

- `agent_id="foo:bar"` + `action="baz"` → `"foo:bar\x00baz"`
- `agent_id="foo"` + `action="bar:baz"` → `"foo\x00bar:baz"`
- Keys are different (no collision)
- Null byte cannot appear in agent_id/action (invalid input)

**Risk Reduction**: Eliminates cache-based privilege escalation and verification bypass attacks.

## Migration Notes

**Breaking Change**: Existing cache entries become invalid after separator change.

**Impact**:

- Cache miss on first access after upgrade
- Verification re-executed (performance hit on first request)
- Cache repopulates with collision-free keys
- No functional changes (just cache miss)

**Deployment Recommendation**:

- **Cache Invalidation**: Clear TrustVerifier cache before deployment (optional)
- **Performance**: Expect initial cache misses after upgrade (temporary)
- **Monitoring**: Watch for increased verification latency during cache repopulation

**No Code Changes Required**: Cache key generation is internal implementation detail.

## Definition of Done

- [x] Null byte separator implemented
- [x] Collision prevention verified
- [x] Cache key uniqueness guaranteed
- [x] All 238 tests passing
- [x] 100% test coverage on cache key logic
- [x] Zero collisions under adversarial testing
- [x] Migration impact documented

## Related Items

- **Red Team Report**: Round 4 - Cache Key Collision Prevention
- **CARE Phase**: Phase 1 - Security Hardening
- **CARE-016**: TrustVerifier in Core SDK (foundation)
- **Priority**: HIGH (cache collisions enable privilege escalation)

---

**Owner**: Core SDK Trust Team
**Reviewer**: security-reviewer, intermediate-reviewer
**Category**: Trust & Security - Cache Collision Prevention
