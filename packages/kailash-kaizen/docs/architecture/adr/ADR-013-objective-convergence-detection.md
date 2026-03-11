# ADR-013: Objective Convergence Detection for Autonomous Agents

**Date**: 2025-10-22
**Status**: Accepted
**Decision Makers**: Kaizen Framework Team
**Impact**: CRITICAL - Fundamental architecture change

---

## Context

### Problem Statement

Our current autonomous agent convergence logic relies on **LLM self-assessment** (confidence scores, finish actions), which is fundamentally naive and prone to hallucination. This diverges from Claude Code's proven architecture which uses **objective detection of tool call presence**.

### Discovery

During implementation of autonomous research agents, user feedback correctly identified that our convergence detection is naive:

> "The way that you design the STOP condition is very naive, especially with using confidence which is very susceptible to LLM hallucination."

Investigation revealed we had the answer in our research documents (`docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md`) but failed to apply it:

> "The system continues executing as long as Claude's responses include tool invocations, naturally terminating only when producing plain text without tool calls—returning control to the user organically rather than artificially." (Lines 7-9)

**Claude Code's Pattern**: `while(tool_call_exists)` - completely objective, zero hallucination risk.

### Current Implementation (Naive)

**File**: `src/kaizen/agents/specialized/react.py`, Lines 280-321

```python
def _check_convergence(self, result: Dict[str, Any]) -> bool:
    # SUBJECTIVE: Trust LLM's self-report
    if result.get("action") == ActionType.FINISH.value:
        return True

    # SUBJECTIVE: Trust LLM's confidence score
    if result.get("confidence", 0) >= self.react_config.confidence_threshold:
        return True

    return False
```

**Problems**:
1. **Hallucination-prone**: LLMs can generate false confidence scores
2. **Brittle**: Depends on exact output format (`action="finish"`)
3. **Circular logic**: Asking LLM "are you confident?" and trusting the answer
4. **Arbitrary threshold**: Why 0.7? Why not 0.6 or 0.8?
5. **Opaque**: Hard to debug why LLM chose certain confidence

---

## Decision

We will **replace subjective convergence with objective detection based on tool call presence**, following Claude Code's proven `while(tool_call_exists)` pattern.

### Core Principle

**Objective convergence**: Stop when response contains no tool calls (objective signal), not when LLM reports high confidence (subjective signal).

### Implementation Pattern

```python
def _check_convergence(self, result: Dict[str, Any]) -> bool:
    """
    Objective convergence detection based on Claude Code architecture.

    Stop when:
    1. No tool calls in response → task complete (OBJECTIVE)
    2. Tool execution failed → error state (OBJECTIVE)

    LLM self-assessment (action="finish", confidence) is NOT used.
    """
    # OBJECTIVE: Check if response contains tool call requests
    if "action" in result and result["action"] == "tool_use":
        # LLM wants to use a tool → continue
        return False

    # OBJECTIVE: Check if last tool execution failed
    if "tool_result" in result and "error" in result["tool_result"]:
        # Tool failed → stop (error state)
        return True

    # OBJECTIVE: No tool calls and no errors → done
    return True
```

### Signature Changes

**Current (Subjective)**:
```python
class ReActSignature(Signature):
    thought: str = OutputField(desc="Current reasoning step")
    action: str = OutputField(desc="Action (tool_use, finish, clarify)")  # ARTIFICIAL
    action_input: dict = OutputField(desc="Input parameters")
    confidence: float = OutputField(desc="Confidence (0.0-1.0)")  # SUBJECTIVE
```

**New (Objective)**:
```python
class ReActSignature(Signature):
    thought: str = OutputField(desc="Current reasoning step")
    tool_calls: list = OutputField(
        desc="Tools to call (empty if done)",
        default=[]
    )  # OBJECTIVE

    # Removed: action, confidence (subjective), need_tool (redundant)
```

**Convergence Logic**: `len(tool_calls) == 0` → done (objective, natural, transparent)

---

## Rationale

### Why Objective Detection is Superior

| Dimension | Objective (New) | Subjective (Current) |
|-----------|----------------|---------------------|
| **Signal Source** | Response structure (`tool_calls` field) | Response content (`action`, `confidence`) |
| **Hallucination Risk** | Zero (checking JSON structure) | High (LLM can hallucinate confidence) |
| **Transparency** | Easy (`if tool_calls:`) | Hard (debug confidence threshold) |
| **Reliability** | Deterministic | Probabilistic |
| **Natural Termination** | Stops when no tools | Requires explicit "finish" action |

### Claude Code Evidence

**Research Document**: `docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md`

**Line 17**:
> "The execution pattern follows a `while(tool_call_exists)` loop where Claude analyzes tasks, decides on tool usage, executes in a sandboxed environment, feeds results back, and repeats until completion."

**Line 189**:
> "Anthropic's finding: sophisticated autonomous behavior emerges from well-designed constraints and disciplined tool integration, not complex orchestration."

**Key Insight**: Autonomy emerges from **objective feedback loops**, not subjective self-assessment.

### Why LLM Self-Assessment Fails

1. **No Privileged Self-Knowledge**: LLMs don't know when they're uncertain. Asking "are you confident?" is like asking a student "do you understand?" - unreliable.

2. **Hallucination Applies to Confidence**: LLMs hallucinate confidence scores just like they hallucinate facts. A model can report confidence=0.95 even when completely wrong.

3. **Tool Calls Reveal True Intent**: If the LLM requests a tool, it needs more information. If it doesn't, it has enough context. This is **observable behavior**, not self-reported opinion.

4. **Natural vs. Artificial**: The LLM naturally stops calling tools when satisfied. Forcing it to signal "finish" explicitly is artificial.

---

## Consequences

### Benefits

1. **Reliability**: Zero hallucination risk in convergence detection
2. **Simplicity**: Clear logic (`if tool_calls: continue; else: stop`)
3. **Transparency**: Easy to debug (inspect response for tool calls)
4. **Natural**: LLM stops when it has enough information, no forced "finish"
5. **Alignment**: Matches proven Claude Code architecture

### Costs

1. **Migration**: Requires signature changes across all agents
2. **Breaking Change**: Removes `action`, `confidence`, `need_tool` fields
3. **Test Updates**: All convergence tests need refactoring
4. **Example Updates**: All autonomous examples need updates

### Risks

1. **Backward Compatibility**: Existing agents using action/confidence will break
2. **Documentation**: Need comprehensive migration guide
3. **Learning Curve**: Users familiar with ReAct pattern need to adapt

---

## Migration Path

### Phase 1: Additive (Backward Compatible, 1-2 days)

**Goal**: Add objective convergence alongside existing subjective logic

**Tasks**:
- Add `tool_calls` field to ReActSignature (optional, default=[])
- Update `_check_convergence()` to check `tool_calls` first, fallback to action/confidence
- Add tests comparing objective vs. subjective convergence

**Deliverables**:
- Backward compatible (existing code works)
- Objective detection proven more reliable

### Phase 2: Migration (1 week)

**Goal**: Make `tool_calls` the primary convergence signal

**Tasks**:
- Update all agent signatures to include `tool_calls`
- Deprecate `action`, `confidence`, `need_tool` (mark as optional)
- Update documentation and examples

**Deliverables**:
- Migration guide for users
- Deprecation warnings in logs

### Phase 3: Pure Objective (1-2 weeks)

**Goal**: Remove subjective convergence entirely

**Tasks**:
- Remove `action`, `confidence`, `need_tool` from signatures
- Remove `confidence_threshold` config
- Update all tests and examples

**Deliverables**:
- 100% objective convergence
- Performance benchmarks showing >95% accuracy

---

## Validation

### Success Criteria

1. **Correctness**: Convergence accuracy >95% (vs. unknown for current subjective approach)
2. **Hallucination Resistance**: Zero false convergence due to LLM confidence hallucination
3. **Natural Termination**: Agents stop when they have enough information (no forced "finish")
4. **Alignment**: Matches Claude Code's `while(tool_call_exists)` pattern

### Test Scenarios

| Scenario | Expected Behavior | Objective Detection | Subjective Detection |
|----------|------------------|--------------------|--------------------|
| Task requires 3 tool calls | Continue for 3 cycles | ✅ Correct | ❌ May stop early (false confidence) |
| Task complete after 2 cycles | Stop at cycle 2 | ✅ Correct | ❌ May continue (low confidence) |
| Tool execution fails | Stop immediately | ✅ Correct | ⚠️ Depends on LLM response |
| No tools available | Stop after 1 cycle | ✅ Correct | ❌ May continue unnecessarily |

### Benchmark

Run 100 diverse tasks, compare:
- **False Positives** (premature stop): Target <5%, Current unknown (likely 10-20%)
- **False Negatives** (unnecessary cycles): Target <5%, Current unknown (likely 10-20%)
- **Overall Accuracy**: Target >95%, Current unknown

---

## Alternatives Considered

### Alternative 1: Hybrid Approach (Objective + Subjective)

**Approach**: Use tool_calls as primary, confidence as secondary signal

```python
def _check_convergence(self, result: Dict[str, Any]) -> bool:
    # Primary: Objective detection
    if len(result.get("tool_calls", [])) == 0:
        return True  # No tools → done

    # Secondary: Confidence fallback
    if result.get("confidence", 0) >= 0.9:  # Higher threshold
        return True

    return False
```

**Rejected Because**:
- Still prone to hallucination (confidence fallback)
- Adds complexity without clear benefit
- Deviates from Claude Code's pure objective approach
- Makes debugging harder (which signal caused stop?)

### Alternative 2: Keep Current Approach, Add Calibration

**Approach**: Keep confidence-based convergence, but calibrate thresholds dynamically

**Rejected Because**:
- Doesn't fix fundamental issue (hallucination)
- Adds complexity (calibration logic)
- Still subjective (just with better tuning)
- Claude Code proves objective detection works better

### Alternative 3: Add Verification Step

**Approach**: After LLM reports "finish", ask it to verify the answer

**Rejected Because**:
- Doubles token usage
- Still relies on LLM self-assessment
- Adds latency
- Doesn't solve hallucination problem (just asks twice)

---

## References

### Research Documents

1. **`docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md`**
   - Lines 7-9: Natural termination via tool call absence
   - Line 17: `while(tool_call_exists)` pattern
   - Line 189: Simplicity enables autonomy

2. **`docs/research/CONVERGENCE_STOP_CONDITION_ANALYSIS.md`**
   - Comprehensive analysis of objective vs. subjective convergence
   - Evidence of hallucination risks
   - Implementation path and success criteria

### Implementation Files

1. **`src/kaizen/agents/specialized/react.py`** (Lines 280-321)
   - Current naive convergence logic

2. **`src/kaizen/strategies/multi_cycle.py`** (Lines 267-303)
   - Multi-cycle execution with convergence checks

### Related ADRs

- **ADR-011**: Control Protocol for Bidirectional Communication
- **ADR-012**: BaseAgent Tool Integration

---

## Decision Outcome

**ACCEPTED** - We will implement objective convergence detection following Claude Code's `while(tool_call_exists)` pattern.

**Timeline**:
- **Phase 1** (Additive): 1-2 days
- **Phase 2** (Migration): 1 week
- **Phase 3** (Pure Objective): 1-2 weeks

**Success Metric**: Convergence accuracy >95%, zero hallucination-driven false convergence.

**Owner**: Kaizen Framework Team
**Reviewers**: Architecture Team, User Community
**Next Review**: After Phase 1 completion (benchmark results)

---

**Last Updated**: 2025-10-22
**Supersedes**: None (first ADR on convergence)
**Superseded By**: None (active)
