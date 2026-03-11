# Enforcement

EATP provides multiple enforcement modes for different deployment stages.

## Strict Enforcer

Blocks actions that fail verification:

```python
from eatp.enforce.strict import StrictEnforcer, Verdict

enforcer = StrictEnforcer(trust_ops=ops)
verdict = await enforcer.enforce(
    agent_id="agent-001",
    action="analyze_data",
    result=verification_result,
)
# verdict: AUTO_APPROVED, FLAGGED, HELD, or BLOCKED
```

If the verdict is BLOCKED, `StrictEnforcer` raises `EATPBlockedError`.

## Shadow Enforcer

Logs verdicts without blocking — for gradual rollout:

```python
from eatp.enforce.shadow import ShadowEnforcer

enforcer = ShadowEnforcer(trust_ops=ops)
verdict = await enforcer.check(
    agent_id="agent-001",
    action="analyze_data",
)
# Logs the verdict but never blocks

# Get enforcement metrics
metrics = enforcer.metrics
print(f"Block rate: {metrics.block_rate:.1%}")
print(enforcer.report())
```

## Decorators

Apply enforcement to functions:

```python
from eatp.enforce.decorators import verified, audited, shadow

@verified(agent_id="agent-001", action="analyze", ops=ops)
async def analyze_data():
    return {"result": "analysis complete"}

@audited(agent_id="agent-001", ops=ops)
async def process_data():
    return {"processed": True}

@shadow(agent_id="agent-001", action="analyze", ops=ops)
async def gradual_rollout():
    return {"status": "ok"}
```

## Challenge-Response

Live trust verification with replay protection:

```python
from eatp.enforce.challenge import ChallengeProtocol

protocol = ChallengeProtocol(key_manager=key_mgr)
challenge = protocol.create_challenge(agent_id="agent-001")
response = protocol.respond(challenge, signing_key_id="key-agent")
valid = protocol.verify_response(challenge, response, public_key)
```

## Selective Disclosure

Export audit records with field-level redaction:

```python
from eatp.enforce.selective_disclosure import export_for_witness, verify_witness_export

export = export_for_witness(
    audit_records=records,
    disclosed_fields=["agent_id", "action", "timestamp"],
    signing_key=priv_key,
)
result = verify_witness_export(export, pub_key)
```
