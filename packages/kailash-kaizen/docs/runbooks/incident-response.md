# Incident Response Runbook

## Overview

This runbook provides procedures for responding to production incidents with the Kaizen AI framework.

## Severity Levels

### P0 - Critical (15 min response)
- Service completely down
- Data breach or security incident
- Complete loss of functionality
- **Escalate immediately to on-call team**

### P1 - High (1 hour response)
- Major functionality degraded
- High error rates (>20%)
- Performance severely degraded
- **Page on-call engineer**

### P2 - Medium (4 hour response)
- Partial functionality affected
- Moderate error rates (5-20%)
- Performance issues
- **Notify team via Slack**

### P3 - Low (24 hour response)
- Minor issues
- Low impact on users
- Non-critical bugs
- **Create ticket**

## Incident Response Process

### 1. Detection (0-5 minutes)

**Alert Sources:**
- Prometheus alerts
- Grafana dashboards
- User reports
- Automated monitoring

**Initial Actions:**
1. Acknowledge alert in monitoring system
2. Verify incident is real (not false positive)
3. Assess severity level
4. Create incident channel in Slack: `#incident-YYYYMMDD-description`

### 2. Triage (5-15 minutes)

**Information Gathering:**
```bash
# Check service health
kubectl get pods -n kaizen
kubectl describe pod <pod-name> -n kaizen

# Check recent deployments
kubectl rollout history deployment/kaizen -n kaizen

# Check logs
kubectl logs <pod-name> -n kaizen --tail=100 --follow

# Check metrics
# View Grafana dashboard: http://grafana.example.com/kaizen-overview
```

**Severity Assessment:**
- Impact: How many users affected?
- Scope: Which services affected?
- Trend: Getting better or worse?
- Workarounds: Any temporary fixes available?

### 3. Escalation (if needed)

**P0/P1 Escalation Path:**
1. On-call engineer (immediate)
2. Engineering manager (if >30 min)
3. VP Engineering (if >1 hour)
4. CTO (if >2 hours or data breach)

**Communication:**
- Update incident channel every 15 minutes
- Post status to status page
- Email stakeholders for P0/P1

### 4. Mitigation (immediate)

**Quick Fixes:**

**Rollback Recent Deployment:**
```bash
# List rollout history
kubectl rollout history deployment/kaizen -n kaizen

# Rollback to previous version
kubectl rollout undo deployment/kaizen -n kaizen

# Rollback to specific revision
kubectl rollout undo deployment/kaizen -n kaizen --to-revision=<revision>

# Verify rollback
kubectl rollout status deployment/kaizen -n kaizen
```

**Scale Resources:**
```bash
# Increase replicas
kubectl scale deployment/kaizen -n kaizen --replicas=6

# Check pod status
kubectl get pods -n kaizen -w
```

**Restart Pods:**
```bash
# Restart deployment (rolling restart)
kubectl rollout restart deployment/kaizen -n kaizen

# Force delete stuck pod
kubectl delete pod <pod-name> -n kaizen --force --grace-period=0
```

**Common Issues:**

1. **High Error Rate**
   - Check recent code changes
   - Review external API status
   - Verify database connectivity
   - Check rate limits

2. **High Latency**
   - Check resource utilization
   - Review slow queries
   - Verify network connectivity
   - Scale resources if needed

3. **Pod CrashLoopBackOff**
   - Check pod logs
   - Verify configuration
   - Check resource limits
   - Review health check timeouts

### 5. Resolution (varies)

**Verify Fix:**
```bash
# Check error rates normalized
# View in Grafana or Prometheus

# Check all pods healthy
kubectl get pods -n kaizen

# Run smoke tests
curl https://api.example.com/health
```

**Document Resolution:**
1. Update incident channel with resolution
2. Close alerts in monitoring
3. Update status page
4. Notify stakeholders

### 6. Post-Mortem (within 48 hours)

**Post-Mortem Template:**

```markdown
# Incident Post-Mortem: [Date] - [Title]

## Summary
- **Date**: YYYY-MM-DD
- **Duration**: X hours
- **Severity**: PX
- **Impact**: Number of users affected

## Timeline
- HH:MM - Event occurred
- HH:MM - Alert triggered
- HH:MM - Engineer acknowledged
- HH:MM - Root cause identified
- HH:MM - Mitigation applied
- HH:MM - Incident resolved

## Root Cause
Detailed explanation of what went wrong

## Impact
- Users affected: X
- Revenue impact: $X
- Downtime: X minutes

## Resolution
What fixed the issue

## Action Items
- [ ] Fix root cause (owner, deadline)
- [ ] Improve monitoring (owner, deadline)
- [ ] Update runbook (owner, deadline)
- [ ] Add automated tests (owner, deadline)

## Lessons Learned
What went well and what needs improvement
```

## Incident Communication

### Status Page Updates

**Initial:**
```
We are investigating reports of [issue].
Updates will be provided every 15 minutes.
```

**Update:**
```
We have identified the cause as [root cause].
Working on mitigation. ETA: [time]
```

**Resolution:**
```
Issue has been resolved. All systems operational.
Post-mortem will be published within 48 hours.
```

### Stakeholder Communication

**Email Template:**
```
Subject: [P0/P1] Production Incident - Kaizen AI

Severity: [P0/P1]
Status: [Investigating/Mitigating/Resolved]
Impact: [Description]
ETA: [Time to resolution]

Details:
[What happened, what we're doing, next update time]

Engineering Team
```

## Incident Metrics

Track for continuous improvement:
- Time to detection (TTD)
- Time to acknowledgement (TTA)
- Time to mitigation (TTM)
- Time to resolution (TTR)
- False positive rate
- Repeat incidents

## References

- [Troubleshooting Runbook](./troubleshooting.md)
- [Deployment Runbook](./deployment.md)
- [Monitoring Runbook](./monitoring.md)
- [Security Policy](../SECURITY.md)
