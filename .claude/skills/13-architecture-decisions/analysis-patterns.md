---
name: analysis-patterns
description: "Deep analysis patterns including failure point analysis, 5-Why root cause investigation, complexity assessment, and risk prioritization. Use for 'failure analysis', 'root cause', 'complexity assessment', or 'risk prioritization'."
---

# Analysis Patterns

> **Skill Metadata**
> Category: `analysis`
> Priority: `HIGH`
> Use Cases: Feature planning, debugging, risk assessment

## Failure Point Analysis Framework

```
### Technical Risk Assessment
- **Parameter Validation**: Missing required inputs, wrong types
- **Integration Points**: Service communication failures, timeout issues
- **Resource Constraints**: Memory usage, CPU limits, connection pools
- **Concurrency Issues**: Race conditions, deadlocks, state conflicts
- **External Dependencies**: Network failures, service unavailability

### Business Logic Risks
- **Edge Cases**: Empty data, invalid inputs, boundary conditions
- **Scale Issues**: Performance degradation with large datasets
- **User Experience**: Confusing error messages, long wait times
- **Data Integrity**: Corruption, inconsistency, validation bypass
```

## Root Cause Investigation (5-Why Framework)

| Level | Question Focus | Example |
|-------|---------------|---------|
| **Why 1** | Immediate symptom | "Why did workflow fail?" → Missing parameters |
| **Why 2** | Direct cause | "Why missing?" → No validation |
| **Why 3** | System cause | "Why no validation?" → Pattern not enforced |
| **Why 4** | Process cause | "Why not enforced?" → No testing requirement |
| **Why 5** | Root cause | "Why no testing?" → Missing development standards |

**Key Insight**: Address root cause (establish testing standards) not symptom (add parameters)

## Complexity Assessment Matrix

### Scoring Dimensions

| Dimension | Low (1-2) | Medium (3-4) | High (5+) |
|-----------|-----------|--------------|-----------|
| **Technical** |
| New components | Single node | Multiple nodes | New subsystem |
| Integration points | 1-2 services | 3-4 services | 5+ services |
| Data dependencies | Single source | Multiple sources | Distributed data |
| **Business** |
| User personas | Single type | 2-3 types | Multiple roles |
| Workflow variations | Linear flow | Branching paths | Complex state machine |
| Edge cases | Well-defined | Some ambiguity | Many unknowns |
| **Operational** |
| Environments | Dev only | Dev + Prod | Multi-region |
| Monitoring | Basic logs | Metrics + alerts | Full observability |
| Security | Internal only | External access | Zero-trust required |

### Scoring Guide
- **5-10 points**: Simple implementation, single developer
- **11-20 points**: Moderate complexity, team coordination needed
- **21+ points**: Enterprise architecture, multiple teams

## Risk Prioritization Framework

| Risk Level | Probability | Impact | Action |
|------------|------------|--------|--------|
| **Critical** | High | High | Mitigate immediately |
| **Major** | High | Low | Quick fixes |
| **Significant** | Low | High | Contingency plan |
| **Minor** | Low | Low | Monitor only |

### Risk Response Strategies
1. **Avoid**: Change approach to eliminate risk
2. **Mitigate**: Reduce probability or impact
3. **Transfer**: Use external service/insurance
4. **Accept**: Document and monitor

## Common Failure Patterns

### Parameter-Related Failures

| Failure Condition | Root Cause | Prevention |
|------------------|------------|------------|
| Empty config `{}` | No defaults provided | Always provide minimal config |
| All optional params | No requirements defined | Mark critical params required |
| No param connections | Workflow design issue | Map parameters explicitly |
| Runtime params missing | User input not validated | Validate before execution |

### Integration Failure Patterns

| Failure Point | Likelihood | Mitigation |
|--------------|------------|------------|
| Network connectivity | High | Retry with backoff |
| Authentication | Medium | Token refresh logic |
| Timeout issues | High | Configure appropriately |
| Service discovery | Medium | Health checks |

### Scale-Related Failures

| Scale Issue | Detection | Prevention |
|------------|-----------|------------|
| Memory leaks | Load testing | Proper resource cleanup |
| Connection exhaustion | Pool monitoring | Connection limits |
| CPU blocking | Performance profiling | Async operations |
| Bandwidth limits | Network monitoring | Pagination/streaming |

## Analysis Output Template

```markdown
## Executive Summary

**Feature**: [Feature name and scope]

**Complexity Score**: [X]/40 ([LOW/MEDIUM/HIGH])
- Technical: [X]/16
- Business: [X]/16
- Operational: [X]/16

**Risk Assessment**:
- Critical risks: [N]
- Major risks: [N]
- Overall risk level: [LOW/MEDIUM/HIGH]

**Recommendation**: [Specific approach with framework choice]

## Detailed Findings

### Failure Points (prioritized by risk)
1. [High risk] [Description] - Mitigation: [approach]
2. [Medium risk] [Description] - Mitigation: [approach]

### Existing Solutions to Reuse
- [Component/pattern] - [How it applies]

### Implementation Phases
- **Phase 1**: Mitigate critical risks
- **Phase 2**: Deliver core functionality
- **Phase 3**: Optimize and enhance

### Success Criteria
- [Functional]: [Measurable outcome]
- [Performance]: [Response times, throughput]
- [Reliability]: [Error rates, recovery time]
```

<!-- Trigger Keywords: failure analysis, root cause, 5-why, complexity assessment, risk prioritization, risk matrix, failure patterns, deep analysis -->
