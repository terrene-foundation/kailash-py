---
name: security-attack-chains
description: "Multi-step attack chains discovered in v2.1.0 red team: pickle+Redis RCE, eval/__import__ injection, auth degradation, PACT governance bypass. Use when reviewing security, auditing deserialization, or checking for chained vulnerabilities."
---

# Security Attack Chains — v2.1.0 Red Team Findings

Documented multi-step attack chains found during 2 rounds of red teaming (30+ findings). These patterns are the highest-severity vulnerabilities because they combine individually moderate issues into critical exploit chains.

## Chain 1: Redis URL Injection + pickle.loads = RCE (CRITICAL)

**Attack**: Attacker controls Redis URL -> points to malicious Redis -> injects crafted pickle payload -> `pickle.loads()` executes arbitrary code.

**Prevention pattern**:

```python
# NEVER: pickle.loads on data from external stores
data = pickle.loads(redis_client.get(key))  # RCE if Redis is attacker-controlled

# ALWAYS: JSON deserialization with schema validation
raw = redis_client.get(key)
data = json.loads(raw)
validate_schema(data)  # Additional validation for critical data

# ALWAYS: Validate Redis URLs before use
ALLOWED_SCHEMES = {"redis", "rediss"}
parsed = urllib.parse.urlparse(redis_url)
if parsed.scheme not in ALLOWED_SCHEMES:
    raise ValueError(f"Invalid Redis URL scheme: {parsed.scheme}")
```

## Chain 2: eval()/exec() with Exposed `__import__` = Code Injection (CRITICAL)

**Prevention pattern**:

```python
# NEVER: __import__ in exec/eval globals
exec(user_code, {"__builtins__": {"__import__": __import__}})  # Full code exec

# ALWAYS: Use ast.literal_eval for safe expression evaluation
import ast
result = ast.literal_eval(user_expr)  # Only literals: strings, numbers, dicts, lists
```

## Chain 3: Auth Degradation + Timing Attack (CRITICAL)

**Prevention pattern**:

```python
# NEVER: Fallback to plaintext comparison on crypto failure
try:
    return pbkdf2_verify(password, stored_hash)
except:  # Catches ImportError AND verification errors!
    return password == stored_hash  # Plaintext + timing attack

# ALWAYS: Fail-closed on crypto unavailability
try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    raise AuthenticationError("Cryptography library required for authentication")

# ALWAYS: Constant-time comparison
import hmac
if not hmac.compare_digest(computed_hash.encode(), stored_hash.encode()):
    raise AuthenticationError("Invalid credentials")
```

## Chain 4: PACT Governance Bypass via Backup Restore (HIGH)

**Prevention pattern**:

```python
# NEVER: Write to envelope store directly
store.save_role_envelope(address, attacker_controlled_envelope)  # No validation!

# ALWAYS: Route through GovernanceEngine which validates
engine.set_role_envelope(address, envelope)  # Validates monotonic tightening

# NEVER: Fail-open on parse errors in governance code
try:
    addr = Address.parse(role_address)
except Exception:
    return (None, "")  # "No ancestor blocks" = fail-open

# ALWAYS: Fail-closed
try:
    addr = Address.parse(role_address)
except Exception:
    return (BLOCKED, "Failed to parse address")  # Deny on error
```

## Chain 5: 0.0.0.0 + Missing Headers + Wildcard CORS (HIGH)

**Attack**: Default server binds to all interfaces + no security headers + wildcard CORS = any machine on the network can interact with the server with no restrictions.

## Cross-Cutting: NaN/Inf Bypass in Governance (MEDIUM)

**Prevention**: `math.isfinite()` on EVERY numeric value BEFORE any comparison.

## Red Team Statistics

| Metric          | Value                                                                     |
| --------------- | ------------------------------------------------------------------------- |
| Rounds          | 2                                                                         |
| Agents deployed | 4 (security-reviewer, deep-analyst, coc-expert, gold-standards-validator) |
| Total findings  | 30+                                                                       |
| CRITICAL        | 4 (pickle RCE, eval injection, auth degradation, PACT fail-open)          |
| HIGH            | 9 (header forwarding, info disclosure, timing attacks, CORS, etc.)        |
| MEDIUM          | 10                                                                        |
| LOW             | 6                                                                         |

<!-- Trigger Keywords: attack chain, RCE chain, pickle RCE, eval injection, auth bypass, timing attack, Redis poisoning, PACT bypass, governance bypass, deserialization, code execution, security audit -->
