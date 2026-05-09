---
skill: nexus-health-monitoring
description: Health checks, monitoring, metrics, and observability for Nexus platform
priority: HIGH
tags: [nexus, health, monitoring, metrics, observability]
---

# Nexus Health and Monitoring

## Overview

Nexus provides built-in health checking, metrics collection, alerting, and observability features. These enable production monitoring through standard health endpoints, configurable metrics backends, and custom health probes for application-specific components.

## When to Use

- Deploying Nexus behind load balancers or orchestrators that require health endpoints
- Monitoring workflow execution performance and error rates
- Integrating with observability platforms (Prometheus, Grafana)
- Setting up alerting for latency spikes or error rate thresholds
- Diagnosing production issues with structured logging

## Architecture

```
Nexus Application
    |
    +-- Health Endpoint (/health)
    |       +-- Platform status
    |       +-- Registered workflow count
    |       +-- Active session count
    |       +-- Component health (custom probes)
    |
    +-- Metrics Endpoint (/metrics)
    |       +-- Request counters
    |       +-- Duration histograms
    |       +-- Error rates
    |       +-- Per-workflow breakdowns
    |
    +-- Alerting Engine
            +-- Threshold-based alerts
            +-- Custom alert handlers
```

## Capabilities

### Health Endpoints

| Endpoint           | Purpose                | Response                                                 |
| ------------------ | ---------------------- | -------------------------------------------------------- |
| `/health`          | Basic platform health  | Status, version, uptime, workflow count, session count   |
| `/health/detailed` | Component-level health | Per-component status (API, database, cache) with latency |

### Programmatic Health Check

The Nexus instance exposes a `health_check()` method that returns the current platform status, including workflow registry state and active sessions. This can be called without HTTP.

### Custom Health Probes

Register custom health check functions for application-specific components:

- Database connectivity
- Cache availability
- External service reachability
- Custom business logic validation

Each probe returns a status (healthy/unhealthy) and optional error details.

### Monitoring Configuration

| Setting             | Description                                          |
| ------------------- | ---------------------------------------------------- |
| Enable monitoring   | Toggle monitoring subsystem on/off                   |
| Monitoring interval | How frequently health checks run (seconds)           |
| Metrics backend     | Where metrics are exported (e.g., Prometheus)        |
| Metric types        | Which metrics to collect (requests, latency, errors) |

### Metrics

| Metric                       | Type      | Description                                  |
| ---------------------------- | --------- | -------------------------------------------- |
| Total requests               | Counter   | Cumulative request count per workflow        |
| Request duration             | Histogram | Latency distribution with percentile buckets |
| Error rate                   | Gauge     | Percentage of failed requests                |
| Success rate                 | Gauge     | Percentage of successful requests            |
| Per-workflow execution count | Counter   | Invocations per registered workflow          |
| Per-workflow success rate    | Gauge     | Success percentage per workflow              |

Metrics are available in Prometheus exposition format at the `/metrics` endpoint when monitoring is enabled.

### Alerting

Configure threshold-based alerts that fire when metrics exceed defined bounds:

| Alert Type       | Trigger                                        |
| ---------------- | ---------------------------------------------- |
| High error rate  | Error percentage exceeds threshold (e.g., 5%)  |
| High latency     | P95 latency exceeds threshold (e.g., 1 second) |
| Low availability | Availability drops below threshold (e.g., 99%) |

Alert handlers can dispatch notifications to external systems (email, Slack, PagerDuty) when thresholds are breached.

### Logging

| Setting    | Description                             |
| ---------- | --------------------------------------- |
| Log level  | Verbosity (DEBUG, INFO, WARNING, ERROR) |
| Log format | Output format (text, JSON)              |
| Log file   | Optional file output                    |

Structured logging (JSON format) is recommended for production deployments to enable log aggregation and search.

## Workflow Health Monitoring

Beyond platform-level health, Nexus can track the health of individual workflows:

- Test execution with minimal inputs to verify workflow availability
- Aggregate per-workflow metrics (execution count, success rate, average duration)
- Detect degradation in specific workflows without affecting overall platform health

## Best Practices

1. **Always enable monitoring in production** -- health endpoints are essential for orchestrators and load balancers
2. **Set meaningful alert thresholds** -- based on baseline performance, not arbitrary numbers
3. **Monitor all external dependencies** -- register custom probes for databases, caches, and APIs
4. **Use structured logging** -- JSON format enables log aggregation and alerting
5. **Track per-workflow metrics** -- a single failing workflow can hide behind healthy aggregate numbers
6. **Implement graceful degradation** -- unhealthy components should reduce functionality, not crash the platform

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-k8s-probes](nexus-k8s-probes.md) - Kubernetes-specific probe integration
- [nexus-enterprise-features](nexus-enterprise-features.md) - Production features
- [nexus-plugins](nexus-plugins.md) - Monitoring via plugins
