# Kaizen Observability Stack

Complete observability infrastructure for Kaizen agents with Grafana dashboards, Prometheus metrics, Jaeger tracing, and compliance monitoring.

## Overview

This directory contains the complete observability stack for monitoring Kaizen agents in production:

- **Grafana**: Metrics visualization with 3 pre-built dashboards
- **Prometheus**: Metrics collection and storage
- **Jaeger**: Distributed tracing visualization
- **Node Exporter**: System metrics (CPU, memory, disk)

## Architecture

```
┌─────────────────┐
│  Kaizen Agent   │
│  (Your App)     │
└────────┬────────┘
         │
         ├─── Metrics ──────────► Prometheus ──────► Grafana
         │                            │
         ├─── Traces ───────────────► Jaeger
         │
         └─── Logs ─────────────────► ELK Stack (optional)
```

## Quick Start

### 1. Start the Observability Stack

```bash
# From this directory
cd grafana/
docker-compose up -d
```

This starts:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Jaeger UI**: http://localhost:16686
- **Node Exporter**: http://localhost:9100

### 2. Enable Observability in Your Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

class QASignature(Signature):
    question: str = InputField(description="Question")
    answer: str = OutputField(description="Answer")

# Create agent
agent = BaseAgent(
    config=config,
    signature=QASignature()
)

# Enable full observability (all 4 systems)
obs = agent.enable_observability(
    service_name="qa-agent",
    jaeger_host="localhost",
    jaeger_port=4317,
    enable_metrics=True,    # Prometheus metrics
    enable_logging=True,    # Structured JSON logs
    enable_tracing=True,    # Jaeger distributed tracing
    enable_audit=True,      # Compliance audit trails
)

# Run your agent
result = agent.run(question="What is Kaizen?")
```

### 3. Expose Metrics Endpoint

To expose metrics for Prometheus scraping:

```python
from kaizen.core.autonomy.observability import ObservabilityManager

# Create observability manager
obs = ObservabilityManager(service_name="my-agent")

# Export metrics in Prometheus format
metrics_text = await obs.export_metrics()

# Serve at /metrics endpoint (using FastAPI example)
from fastapi import FastAPI

app = FastAPI()

@app.get("/metrics")
async def metrics():
    return Response(
        content=await obs.export_metrics(),
        media_type="text/plain"
    )
```

### 4. Configure Prometheus

Edit `prometheus.yml` to add your agent endpoints:

```yaml
scrape_configs:
  - job_name: 'kaizen-agents'
    static_configs:
      - targets:
        - 'localhost:8000'  # Your agent endpoint
        - 'agent-1:8000'
        - 'agent-2:8000'
```

Reload Prometheus:
```bash
curl -X POST http://localhost:9090/-/reload
```

### 5. Access Dashboards

Open Grafana at http://localhost:3000 (admin/admin)

Navigate to **Dashboards → Kaizen** folder:

1. **Agent Monitoring Dashboard** - Real-time agent performance
2. **Performance Metrics Dashboard** - Resource usage and overhead
3. **Audit & Compliance Dashboard** - Governance and compliance

## Dashboards

### 1. Agent Monitoring Dashboard

**Purpose**: Real-time monitoring of agent operations and health

**Key Panels**:
- Agent Loop Duration (p95) with alerts >5s
- Agent Loop Success Rate gauge
- Tool Execution Count and Latency
- API Calls by Provider
- API Cost per Hour (USD)
- Active Agents count
- Memory Usage
- Error Rate
- Audit Events per Minute
- Permission Approval Rate

**Use Cases**:
- Monitor agent performance in real-time
- Detect performance degradation
- Track API costs
- Alert on failures and errors

### 2. Performance Metrics Dashboard

**Purpose**: Performance monitoring and overhead tracking

**Key Panels**:
- Observability Metrics Overhead (target: <2%)
- Observability Logging Overhead (target: <5%)
- Observability Tracing Overhead (target: <1%)
- Audit Append Latency (target: <10ms)
- CPU Usage by agent
- Memory Usage trends
- Operation Latency Percentile Distribution (p50/p95/p99)
- Throughput (ops/sec)
- Disk and Network I/O
- GC Pause Time
- Cache Hit Rate
- Performance Target Compliance score

**Use Cases**:
- Ensure observability overhead stays within NFR targets (ADR-017)
- Monitor system resource usage
- Optimize performance bottlenecks
- Track percentile distributions

### 3. Audit & Compliance Dashboard

**Purpose**: Compliance monitoring and governance (SOC2, GDPR, HIPAA)

**Key Panels**:
- Audit Events Volume and trends
- Audit Events by Action Type
- Audit Events by Result (success/failure/denied)
- Active Users (last hour)
- Audit Trail Completeness %
- Critical Actions count
- Top Users and Agents by activity
- Permission Requests over time
- Tool Execution Audit Trail
- Compliance Scores (SOC2, GDPR, HIPAA)
- Audit Event Timeline (last 100 events)
- Retention Policy Compliance
- Immutability Verification

**Use Cases**:
- Demonstrate SOC2/GDPR/HIPAA compliance
- Track sensitive data access (PHI for HIPAA)
- Audit user and agent activity
- Verify audit trail integrity
- Monitor retention policies

## Metrics Reference

### Agent Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `agent_loop_duration_ms_p50` | Histogram | Agent loop duration (median) |
| `agent_loop_duration_ms_p95` | Histogram | Agent loop duration (95th percentile) |
| `agent_loop_duration_ms_p99` | Histogram | Agent loop duration (99th percentile) |
| `agent_loop_total` | Counter | Total agent loop executions |
| `agent_loop_success` | Counter | Successful agent loop executions |
| `active_agents` | Gauge | Number of active agents |

### Tool Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `tool_execution_total` | Counter | Total tool executions by tool_name |
| `tool_execution_success` | Counter | Successful tool executions |
| `tool_execution_duration_ms_p50` | Histogram | Tool execution duration (median) |
| `tool_execution_duration_ms_p95` | Histogram | Tool execution duration (95th percentile) |

### API Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `api_calls_total` | Counter | Total API calls by provider |
| `api_cost_usd` | Gauge | API cost in USD |

### Performance Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `memory_bytes` | Gauge | Memory usage in bytes |
| `cpu_usage_percent` | Gauge | CPU usage percentage |
| `errors_total` | Counter | Total errors |
| `observability_metrics_overhead_percent` | Gauge | Metrics collection overhead % |
| `observability_logging_overhead_percent` | Gauge | Logging overhead % |
| `observability_tracing_overhead_percent` | Gauge | Tracing overhead % |

### Audit Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `audit_events_total` | Counter | Total audit events by action/result |
| `audit_append_duration_ms_p50` | Histogram | Audit append latency (median) |
| `audit_append_duration_ms_p95` | Histogram | Audit append latency (95th percentile) |
| `audit_append_failures_total` | Counter | Failed audit appends |
| `permission_requested` | Counter | Permission requests |
| `permission_granted` | Counter | Permissions granted |
| `permission_denied` | Counter | Permissions denied |

## Performance Targets (ADR-017)

| Component | Target | Dashboard Alert |
|-----------|--------|----------------|
| Metrics Collection | <2% overhead | ✅ Alert at >2% |
| Structured Logging | <5% overhead | ✅ Alert at >5% |
| Distributed Tracing | <1% overhead | ✅ Alert at >1% |
| Audit Trail Append | <10ms latency | ✅ Alert at >10ms |

## Alerting

The dashboards include built-in alerts for:

1. **Agent Loop Duration High** - Agent loop >5 seconds
2. **Metrics Overhead High** - Metrics collection >2%
3. **Logging Overhead High** - Logging overhead >5%
4. **Tracing Overhead High** - Tracing overhead >1%
5. **Audit Latency High** - Audit append >10ms
6. **High Failure Rate** - Audit failures >10/sec

To enable alerting, configure Grafana notification channels (email, Slack, PagerDuty, etc.) in the Grafana UI.

## Advanced Configuration

### Selective Observability

Enable only the components you need:

```python
# Lightweight: metrics + logging only
obs = agent.enable_observability(
    service_name="lightweight-agent",
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=False,  # Disable tracing
    enable_audit=False,    # Disable audit
)
```

### Custom Metrics

Record custom metrics:

```python
# Counter
await obs.record_metric(
    "custom_events_total",
    1.0,
    type="counter",
    labels={"event_type": "user_login"}
)

# Gauge
await obs.record_metric(
    "queue_size",
    42,
    type="gauge",
    labels={"queue_name": "tasks"}
)

# Histogram
await obs.record_metric(
    "request_duration_ms",
    150.5,
    type="histogram",
    labels={"endpoint": "/api/v1/chat"}
)
```

### Custom Audit Events

Record custom audit events:

```python
await obs.record_audit(
    agent_id="my-agent",
    action="custom_action",
    details={"key": "value"},
    result="success",
    user_id="user@example.com",
    metadata={"importance": "high"}
)
```

## Troubleshooting

### Metrics Not Appearing

1. **Check Prometheus targets**: http://localhost:9090/targets
   - Ensure your agent endpoint is listed and "UP"

2. **Check metrics endpoint**: http://localhost:8000/metrics
   - Should return Prometheus-formatted metrics

3. **Check Prometheus config**: `prometheus.yml`
   - Verify `targets` includes your agent

4. **Reload Prometheus**:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

### Traces Not Appearing

1. **Check Jaeger UI**: http://localhost:16686
   - Select service name in dropdown

2. **Verify tracing enabled**:
   ```python
   obs = agent.enable_observability(enable_tracing=True)
   ```

3. **Check Jaeger host/port**:
   ```python
   obs = agent.enable_observability(
       jaeger_host="localhost",
       jaeger_port=4317  # OTLP gRPC port
   )
   ```

### Dashboard Errors

1. **No data points**: Wait 30 seconds for first scrape
2. **Query errors**: Check Prometheus has metrics
3. **Template variables**: Ensure agent_id labels exist

## Production Deployment

### ⚠️ Security Warning

**The default configuration uses development-friendly settings that are NOT secure for production:**

- ❌ Default password: `admin/admin` (publicly known)
- ❌ HTTP only (no TLS/HTTPS)
- ❌ No authentication on Prometheus and Jaeger
- ❌ All services publicly exposed

**See [Security Documentation](../docs/observability/SECURITY.md) for comprehensive hardening guide.**

### Quick Production Setup (15 minutes)

**Prerequisites**:
- Docker and Docker Compose installed
- Domain name (or localhost for testing)
- OpenSSL installed (for certificate generation)

#### Step 1: Generate SSL Certificates

```bash
cd grafana/
./scripts/generate-certs.sh grafana.example.com 365

# For localhost testing:
./scripts/generate-certs.sh localhost 365
```

#### Step 2: Configure Production Environment

```bash
# Copy environment template
cp .env.production.example .env.production

# Edit with your settings
nano .env.production
```

**Minimum required changes**:

```bash
# CRITICAL: Change these immediately!
GRAFANA_ADMIN_PASSWORD=<generate-strong-password-16+chars>
PROMETHEUS_PASSWORD=<generate-strong-password-16+chars>
ES_PASSWORD=<generate-strong-password-16+chars>

# HTTPS Configuration
GRAFANA_SERVER_PROTOCOL=https
GRAFANA_SERVER_DOMAIN=grafana.example.com  # Your domain
GRAFANA_SERVER_CERT_FILE=/etc/grafana/ssl/grafana.crt
GRAFANA_SERVER_KEY_FILE=/etc/grafana/ssl/grafana.key
```

**Generate strong passwords**:

```bash
# Generate 24-character random password
openssl rand -base64 24
```

#### Step 3: Generate Prometheus Authentication

```bash
./scripts/generate-prometheus-auth.sh prometheus <your-prometheus-password>
```

#### Step 4: Start Production Stack

```bash
# Start with production environment
docker-compose --env-file .env.production up -d

# Check logs
docker-compose logs -f
```

#### Step 5: Verify Production Deployment

**Grafana (HTTPS)**:
- URL: `https://grafana.example.com:3000`
- Login: `admin` / `<your-password>`
- ✅ Should use HTTPS (check browser lock icon)
- ✅ Should require login

**Prometheus** (Internal):
- URL: `http://localhost:9090`
- ✅ Should require basic authentication

**Jaeger** (Internal):
- URL: `http://localhost:16686`
- ℹ️ Should only be accessible via SSH tunnel or VPN

#### Step 6: Configure OAuth (Optional but Recommended)

**Google OAuth** (most common):

1. **Create OAuth credentials**: https://console.cloud.google.com/apis/credentials
   - Application type: Web application
   - Authorized redirect URIs: `https://grafana.example.com/login/generic_oauth`

2. **Update `.env.production`**:

```bash
GRAFANA_AUTH_OAUTH_ENABLED=true
GRAFANA_AUTH_OAUTH_NAME=Google
GRAFANA_AUTH_OAUTH_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
GRAFANA_AUTH_OAUTH_CLIENT_SECRET=<your-client-secret>
GRAFANA_AUTH_OAUTH_ALLOWED_DOMAINS=example.com  # Restrict to your domain
```

3. **Restart Grafana**:

```bash
docker-compose restart grafana
```

**Other providers**: See [SECURITY.md](../docs/observability/SECURITY.md) for GitHub, Okta, Azure AD

### Production Architecture

```
┌─────────────────────────────────────────────┐
│     Reverse Proxy (nginx/Traefik/ALB)      │
│              TLS Termination                │
└────────────────┬────────────────────────────┘
                 │ HTTPS
         ┌───────┴───────┐
         │               │
    ┌────▼────┐     ┌────▼────┐
    │ Grafana │     │  Apps   │
    │ (HTTPS) │     │ (Agents)│
    └────┬────┘     └────┬────┘
         │               │
    ┌────▼───────────────▼────┐
    │     Prometheus (Auth)   │
    └────────┬────────────────┘
             │
    ┌────────▼────────┐
    │ Jaeger (Private)│
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ Elasticsearch   │
    │  (Auth + TLS)   │
    └─────────────────┘
```

### Security Checklist

Before deploying to production, verify:

- [ ] **Strong passwords** configured (16+ characters)
- [ ] **SSL/TLS certificates** generated and mounted
- [ ] **HTTPS enabled** for Grafana (`GRAFANA_SERVER_PROTOCOL=https`)
- [ ] **OAuth or LDAP** configured (recommended)
- [ ] **Prometheus authentication** enabled (htpasswd generated)
- [ ] **Elasticsearch authentication** enabled (`xpack.security.enabled=true`)
- [ ] **Anonymous access disabled** (`GRAFANA_AUTH_ANONYMOUS_ENABLED=false`)
- [ ] **Security headers enabled** (HSTS, CSP, X-Frame-Options)
- [ ] **`.env.production` added to `.gitignore`**
- [ ] **Firewall rules** configured (restrict public access)
- [ ] **Backup scheduled** (Grafana dashboards, Prometheus data)
- [ ] **Monitoring alerts** configured (failed logins, certificate expiry)

### Network Isolation (Recommended)

**Restrict internal services to localhost**:

Edit `docker-compose.yml`:

```yaml
services:
  prometheus:
    ports:
      - "127.0.0.1:9090:9090"  # Localhost only

  jaeger:
    ports:
      - "127.0.0.1:16686:16686"  # Localhost only

  elasticsearch:
    ports:
      - "127.0.0.1:9200:9200"  # Localhost only
```

**Access via SSH tunnel**:

```bash
# SSH tunnel to Prometheus
ssh -L 9090:localhost:9090 user@production-server

# Now access at: http://localhost:9090
```

### Reverse Proxy (Production Best Practice)

**nginx example** (TLS termination + basic auth):

```nginx
# /etc/nginx/sites-available/grafana
server {
    listen 443 ssl http2;
    server_name grafana.example.com;

    # Let's Encrypt certificates
    ssl_certificate /etc/letsencrypt/live/grafana.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/grafana.example.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload";
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";

    # Proxy to Grafana
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for live updates)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name grafana.example.com;
    return 301 https://$server_name$request_uri;
}
```

**Enable nginx config**:

```bash
sudo ln -s /etc/nginx/sites-available/grafana /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl reload nginx
```

### Let's Encrypt (Automated TLS)

**Recommended for production**: Free, automated certificate renewal.

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx  # Ubuntu

# Generate certificate
sudo certbot --nginx -d grafana.example.com

# Auto-renewal (runs twice daily)
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

# Test renewal
sudo certbot renew --dry-run
```

### High Availability (Enterprise)

**Multi-instance Grafana** with shared database:

```yaml
# docker-compose.yml
services:
  grafana-1:
    image: grafana/grafana:latest
    environment:
      - GF_DATABASE_TYPE=postgres
      - GF_DATABASE_HOST=postgres:5432
      - GF_DATABASE_NAME=grafana
      - GF_DATABASE_USER=grafana
      - GF_DATABASE_PASSWORD=${DB_PASSWORD}

  grafana-2:
    image: grafana/grafana:latest
    environment:
      - GF_DATABASE_TYPE=postgres
      - GF_DATABASE_HOST=postgres:5432

  postgres:
    image: postgres:14
    environment:
      - POSTGRES_DB=grafana
      - POSTGRES_USER=grafana
      - POSTGRES_PASSWORD=${DB_PASSWORD}

  nginx-lb:
    image: nginx:alpine
    # Load balancer config
```

### Compliance

**SOC 2, GDPR, HIPAA requirements**:

- **Encryption in transit**: TLS/HTTPS (mandatory)
- **Encryption at rest**: Encrypted volumes (recommended)
- **Audit trails**: Grafana audit logs (mandatory)
- **Access control**: OAuth/LDAP with MFA (mandatory)
- **Data retention**: Configure Prometheus retention (30 days recommended)

See [SECURITY.md](../docs/observability/SECURITY.md) for detailed compliance guide.

### Backup & Recovery

**What to backup**:

```bash
# Grafana database
docker exec kaizen-grafana grafana-cli admin export > grafana-backup.json

# Prometheus data
docker exec kaizen-prometheus promtool tsdb snapshot /prometheus

# Elasticsearch snapshots
curl -X PUT "localhost:9200/_snapshot/backup/snapshot_$(date +%Y%m%d)" \
  -u elastic:${ES_PASSWORD}

# Configuration files
tar -czf observability-config.tar.gz \
  .env.production \
  grafana/prometheus.yml \
  grafana/dashboards/ \
  grafana/datasources/
```

**Automate backups** (cron):

```bash
# Daily backup at 2 AM
0 2 * * * /opt/scripts/backup-observability.sh
```

### Scaling

For production workloads:

1. **Use external Prometheus**:
   - Deploy separate Prometheus cluster
   - Configure remote write to long-term storage (Thanos, Cortex)

2. **Use external Jaeger**:
   - Deploy Jaeger with Elasticsearch backend
   - Configure sampling for high-volume traces

3. **Configure retention**:
   ```yaml
   # prometheus.yml
   storage:
     tsdb:
       retention.time: 30d
       retention.size: 50GB
   ```

## References

- **ADR-017**: Observability & Performance Monitoring architecture
- **Integration Tests**: `tests/integration/observability/test_baseagent_observability.py`
- **Unit Tests**: `tests/unit/observability/`
- **Documentation**: See main Kaizen docs for detailed API reference

## Support

For issues or questions:
- Check troubleshooting section above
- Review integration tests for usage examples
- Consult ADR-017 for architecture decisions
