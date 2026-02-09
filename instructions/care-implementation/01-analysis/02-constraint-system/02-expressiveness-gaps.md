# Constraint Expressiveness Gaps: What Organizations Cannot Say

## Executive Summary

This document identifies constraints that organizations legitimately need but cannot express within the current five-dimension model (Financial, Operational, Temporal, Data Access, Communication). These gaps represent the frontier of constraint specification - moving from "what" constraints to "why" and "so what" constraints.

**Key Finding**: The current constraint model is syntactic (defining permitted/blocked actions). Organizations need semantic constraints (defining intended outcomes) and pragmatic constraints (defining organizational context and relationships).

**Complexity Score**: Enterprise (28 points) - Requires fundamental extension of constraint model.

---

## Gap Category 1: Reputational Risk Constraints

### The Need

Organizations need to express: **"Don't embarrass us."**

Examples:
- Don't send communications that could become negative PR
- Don't make decisions that would be indefensible in media scrutiny
- Don't take actions that violate our brand values
- Don't create audit trails that would look bad to regulators

### Why Current Model Fails

The five dimensions can specify:
- **Communication**: Tone guidelines, escalation triggers
- **Operational**: Blocked actions

But they cannot specify:
- What constitutes "embarrassment" (context-dependent)
- How actions will be perceived by external stakeholders
- Downstream reputational consequences of permitted actions
- Media or regulatory interpretation of action sequences

### Current Workaround Limitations

```python
# Attempt to encode reputational constraints
CommunicationConstraints(
    tone_guidelines="professional, brand-aligned",
    escalation_triggers=["controversial", "political", "sensitive"]
)
```

**Why This Fails**:
- Keyword matching misses subtle reputational risks
- "Professional" is undefined and culturally variable
- Cannot anticipate novel reputation scenarios
- No connection to brand guidelines or PR history

### Proposed Extension

```python
@dataclass
class ReputationalConstraints:
    brand_values: List[str]                    # ["innovation", "integrity", "customer-first"]
    reputational_risk_threshold: float         # 0.0-1.0, ML-scored risk
    media_scrutiny_mode: Literal["assume_always", "high_profile_only"]
    pr_escalation_triggers: List[str]          # Semantic patterns, not keywords
    past_incidents_reference: str              # Link to PR incident database
    stakeholder_sensitivity: Dict[str, float]  # {"regulators": 0.9, "customers": 0.7}
    defensibility_requirement: bool            # "Would this be defensible in testimony?"
```

**Implementation Approach**:
1. Integrate with LLM-based reputational risk scoring
2. Reference organizational brand guidelines as constraint context
3. Track PR incident history for pattern matching
4. Apply "front page test" heuristic via semantic analysis

---

## Gap Category 2: Intent-Based Constraints

### The Need

Organizations need to express: **"Don't try to circumvent restrictions."**

Examples:
- Don't structure transactions to avoid approval thresholds
- Don't use intermediaries to bypass vendor limits
- Don't split actions to evade aggregate tracking
- Don't exploit reset boundaries

### Why Current Model Fails

Current constraints specify what is allowed/blocked. They cannot specify:
- Whether an action is intended to circumvent other constraints
- Whether a sequence of actions represents constraint gaming
- Agent "intent" or "motivation" behind permitted actions
- Good-faith vs. adversarial compliance

### Current Workaround Limitations

There is no current workaround. The system cannot distinguish:
- Legitimate transaction splitting (ordering from multiple vendors for valid business reasons)
- Gaming-motivated splitting (structuring to avoid approvals)

### Proposed Extension

```python
@dataclass
class IntentConstraints:
    circumvention_detection_enabled: bool
    structuring_threshold: float               # Sensitivity for structuring detection
    gaming_indicators: List[GameIndicator]     # Patterns suggesting constraint gaming
    good_faith_attestation_required: bool      # Agent must declare intent
    intent_audit_mode: Literal["log", "warn", "block"]

@dataclass
class GameIndicator:
    pattern_type: Literal["threshold_proximity", "timing_boundary", "delegation_fan_out"]
    threshold: float
    lookback_period: timedelta
    action_description: str
```

**Implementation Approach**:
1. Behavioral anomaly detection on constraint boundary utilization
2. Intent declaration requirement before sensitive actions
3. Post-hoc intent verification (did declared intent match actual outcome?)
4. Gaming indicator pattern matching

---

## Gap Category 3: Outcome-Based Constraints

### The Need

Organizations need to express: **"Don't cause customer harm."**

Examples:
- Don't take actions that result in customer complaints
- Don't make decisions that reduce customer lifetime value
- Don't create situations requiring customer remediation
- Don't generate negative NPS impact

### Why Current Model Fails

Current constraints are action-focused. They cannot specify:
- Downstream consequences of permitted actions
- Customer experience impacts
- Cumulative effects over time
- Outcome causation chains

### Current Workaround Limitations

```python
# Attempt: Block actions that might harm customers
ActionConstraints(
    blocked_actions=["cancel_subscription", "reduce_service", "charge_penalty"]
)
```

**Why This Fails**:
- Overly restrictive (sometimes these actions are appropriate)
- Misses novel harm vectors
- Cannot capture "harm" as an outcome concept
- Some harm comes from inaction, not action

### Proposed Extension

```python
@dataclass
class OutcomeConstraints:
    prohibited_outcomes: List[OutcomeDefinition]
    outcome_monitoring_period: timedelta       # How long to track outcomes
    causal_attribution_threshold: float        # Min confidence for attribution
    rollback_on_negative_outcome: bool
    outcome_metrics: List[str]                 # ["nps_delta", "churn_risk", "csat"]

@dataclass
class OutcomeDefinition:
    outcome_type: str                          # "customer_harm", "revenue_loss"
    indicators: List[str]                      # Measurable signals
    threshold: float                           # When is outcome "occurred"?
    time_horizon: timedelta                    # How long after action to check
```

**Implementation Approach**:
1. Delayed outcome verification (check customer state N days after action)
2. Causal attribution modeling (did agent action cause outcome?)
3. Outcome feedback loop to constraint refinement
4. Outcome prediction before action execution

---

## Gap Category 4: Relational Constraints

### The Need

Organizations need to express: **"Maintain vendor relationships."**

Examples:
- Don't damage relationships with strategic partners
- Don't take adversarial positions with key vendors
- Don't create situations that require relationship repair
- Prioritize long-term relationship over short-term gain

### Why Current Model Fails

Current constraints focus on transactional limits. They cannot specify:
- Relationship health as a constraint dimension
- Trust and goodwill considerations
- Long-term relationship trajectory
- Relationship context for decisions

### Current Workaround Limitations

```python
# Attempt: Per-vendor limits
vendor_limits = {"Strategic Partner A": 100000}
```

**Why This Fails**:
- Higher limits don't capture relationship protection
- No consideration of communication tone with vendors
- Cannot express "don't antagonize" as a constraint
- Missing relationship state tracking

### Proposed Extension

```python
@dataclass
class RelationalConstraints:
    strategic_relationships: List[RelationshipConfig]
    default_relationship_posture: Literal["transactional", "partnership", "adversarial_caution"]
    relationship_health_monitoring: bool
    escalate_on_relationship_risk: bool

@dataclass
class RelationshipConfig:
    entity_id: str
    relationship_tier: Literal["strategic", "preferred", "standard"]
    protected_actions: List[str]               # Actions requiring special care
    relationship_owner: str                    # Human to consult
    communication_tone: str                    # "collaborative", "formal", etc.
    dispute_resolution: str                    # How to handle conflicts
```

**Implementation Approach**:
1. Relationship registry with tier classifications
2. Relationship-aware action evaluation
3. Relationship health scoring integration
4. Human relationship owner in the loop for strategic actions

---

## Gap Category 5: Contextual Constraints

### The Need

Organizations need to express: **"Behave differently in crisis vs. normal operations."**

Examples:
- During market volatility, reduce autonomous trading limits
- During security incidents, restrict data access further
- During regulatory audits, increase logging and approvals
- During product launches, tighten communication constraints

### Why Current Model Fails

Current constraints are static. They cannot specify:
- Organizational state awareness
- Dynamic constraint adjustment
- Context-triggered constraint profiles
- Temporary constraint overrides with automatic reversion

### Current Workaround Limitations

Organizations must manually update constraints when context changes. This is:
- Slow (crisis may be over before constraints are updated)
- Error-prone (may forget to revert after crisis)
- Incomplete (may not anticipate all contexts)

### Proposed Extension

```python
@dataclass
class ContextualConstraints:
    context_profiles: Dict[str, ConstraintEnvelope]  # "normal", "crisis", "audit"
    active_context: str
    context_triggers: List[ContextTrigger]
    automatic_reversion: bool
    context_overlap_resolution: str            # How to combine if multiple contexts active

@dataclass
class ContextTrigger:
    trigger_name: str
    conditions: List[Condition]                # External signals that activate context
    target_context: str
    duration: Optional[timedelta]              # Auto-revert after duration
    requires_human_confirmation: bool
```

**Implementation Approach**:
1. Integration with organizational state monitoring systems
2. Automatic context detection from external signals
3. Context-aware constraint envelope selection
4. Audit trail for context transitions

---

## Gap Category 6: Compositional Constraints

### The Need

Organizations need to express: **"These actions are fine individually but not together."**

Examples:
- Reading customer data is OK; sending external email is OK; doing both in sequence is NOT OK
- Creating purchase order is OK; approving payment is OK; same agent doing both is NOT OK (separation of duties)
- Accessing production is OK; running DELETE queries is OK; both at 3 AM is NOT OK

### Why Current Model Fails

Current constraints evaluate actions independently. They cannot specify:
- Action sequence prohibitions
- Action combinations that require additional approval
- Temporal proximity constraints between action types
- Agent identity constraints for action pairs

### Current Workaround Limitations

```python
# Attempt: Block the "dangerous" action entirely
blocked_actions=["send_external_email"]  # But this blocks legitimate uses
```

**Why This Fails**:
- Overly restrictive for legitimate use cases
- Cannot express conditionality ("blocked only if...")
- Missing sequence awareness

### Proposed Extension

```python
@dataclass
class CompositionalConstraints:
    prohibited_sequences: List[ActionSequence]
    separation_of_duties: List[DutyPair]
    temporal_proximity_rules: List[ProximityRule]
    cumulative_risk_threshold: float

@dataclass
class ActionSequence:
    actions: List[str]                         # ["read_customer_data", "send_external_email"]
    window: timedelta                          # Within what timeframe
    effect: Literal["block", "require_approval", "audit"]

@dataclass
class DutyPair:
    action_a: str
    action_b: str
    same_agent_allowed: bool
    same_session_allowed: bool
```

**Implementation Approach**:
1. Action history tracking per agent and per session
2. Real-time sequence matching against prohibited patterns
3. Cumulative risk scoring across action sequences
4. Separation of duties enforcement in delegation

---

## Gap Category 7: Emergent Behavior Constraints

### The Need

Organizations need to express: **"Don't develop unexpected capabilities or behaviors."**

Examples:
- Don't discover novel attack vectors through exploration
- Don't optimize for metrics in unintended ways (Goodhart's Law)
- Don't develop emergent coordination with other agents
- Don't acquire capabilities beyond original design

### Why Current Model Fails

Current constraints assume known action space. They cannot specify:
- Novelty detection in agent behavior
- Capability creep prevention
- Emergent phenomena in multi-agent systems
- Optimization pressure monitoring

### Current Workaround Limitations

There is no current workaround for emergent behavior. The constraint system is reactive (blocks known bad actions) not proactive (prevents unknown bad actions).

### Proposed Extension

```python
@dataclass
class EmergenceBehaviorConstraints:
    capability_envelope: List[str]             # Expected capabilities only
    novelty_tolerance: float                   # 0.0 = block all novel behavior
    optimization_target_bounds: Dict[str, Tuple[float, float]]  # Guardrails on metrics
    inter_agent_communication_limits: InterAgentLimits
    capability_audit_frequency: timedelta

@dataclass
class InterAgentLimits:
    max_coordination_depth: int                # How many agents can coordinate
    allowed_coordination_patterns: List[str]   # "delegation", "consultation", not "collusion"
    emergent_protocol_detection: bool          # Flag novel communication patterns
```

**Implementation Approach**:
1. Behavioral baseline establishment during training/deployment
2. Anomaly detection on capability utilization
3. Inter-agent communication monitoring
4. Optimization trajectory tracking

---

## Gap Category 8: Ethical Constraints

### The Need

Organizations need to express ethical principles as constraints:
- "Treat all customers fairly regardless of demographics"
- "Prioritize safety over efficiency"
- "Respect human dignity in all interactions"
- "Do not deceive, even by omission"

### Why Current Model Fails

Ethics are inherently value-laden and context-dependent. Current constraints are:
- Procedural (what to do) not normative (what is right)
- Objective (measurable) not subjective (value-based)
- Rule-based not principle-based

### Proposed Extension

```python
@dataclass
class EthicalConstraints:
    ethical_framework: Literal["utilitarian", "deontological", "virtue", "care"]
    core_values: List[str]                     # ["fairness", "transparency", "safety"]
    ethical_review_triggers: List[str]         # Actions requiring ethics review
    bias_detection_enabled: bool
    fairness_metrics: Dict[str, float]         # Demographic parity requirements
    human_dignity_protections: List[str]       # Specific protections
```

**Implementation Approach**:
1. Ethics board in the loop for novel situations
2. Fairness metric monitoring across demographics
3. Principle-based reasoning for edge cases
4. Human override for ethical edge cases

---

## Synthesis: The Constraint Expression Hierarchy

```
Level 1: Syntactic Constraints (Current)
  "Action X is blocked"
  "Value Y cannot exceed Z"

Level 2: Semantic Constraints (Needed)
  "Outcome O is prohibited"
  "Intent I is not permitted"

Level 3: Pragmatic Constraints (Needed)
  "Context C modifies constraint set"
  "Relationship R requires special handling"

Level 4: Normative Constraints (Aspirational)
  "Value V guides all decisions"
  "Principle P is never violated"
```

---

## Implementation Roadmap

### Phase 1: Compositional Constraints (SDK)
Most concrete and implementable. Enables sequence-aware constraint evaluation.

### Phase 2: Contextual Constraints (Platform)
Requires organizational state integration. Enables dynamic constraint profiles.

### Phase 3: Intent-Based Constraints (Platform + ML)
Requires behavioral analysis. Enables gaming detection.

### Phase 4: Outcome-Based Constraints (Platform + ML)
Requires outcome tracking integration. Enables consequence-aware constraints.

### Phase 5: Relational/Reputational (Platform + External)
Requires external system integration. Enables relationship-aware constraints.

### Phase 6: Ethical/Emergent (Research)
Requires ongoing research. Enables value-aligned constraints.

---

## Recommendations

1. **Prioritize Compositional Constraints**: Most actionable gap with clear SDK implementation path.

2. **Design Constraint Extension Protocol**: See `04-constraint-extensibility-design.md` for plugin architecture.

3. **Invest in Outcome Tracking**: Required foundation for outcome-based and intent-based constraints.

4. **Develop Gaming Detection**: Critical for intent-based constraints. See `03-mitigation-strategies.md`.
