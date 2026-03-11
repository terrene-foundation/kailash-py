# Monitoring Runbook

## Alert Handling

### HighErrorRate Alert

**Severity**: Warning
**Threshold**: Error rate > 5% for 5 minutes

**Investigation:**
1. Check Grafana dashboard for error types
2. Review recent deployments
3. Check external API status
4. Review application logs

**Resolution:**
- If deployment-related: Rollback
- If API-related: Enable circuit breaker
- If transient: Monitor for 10 more minutes

### ServiceDown Alert

**Severity**: Critical
**Threshold**: Service unreachable for 1 minute

**Investigation:**
1. Check pod status: `kubectl get pods -n kaizen`
2. Check recent events: `kubectl get events -n kaizen --sort-by='.lastTimestamp'`
3. Check infrastructure health

**Resolution:**
1. Restart pods if needed
2. Scale up if capacity issue
3. Check infrastructure provider status

## Dashboard Guide

### Kaizen Overview Dashboard

**Panels:**
1. Request Rate - Normal: 10-100 req/s
2. Error Rate - Normal: <1%
3. Latency P95 - Normal: <2s
4. Success Rate - Normal: >99%

**Alert Conditions:**
- Error rate >5%: Investigate
- Latency >5s: Scale or optimize
- Success rate <95%: Check dependencies
