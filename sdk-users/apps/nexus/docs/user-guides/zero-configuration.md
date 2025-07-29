# Zero Configuration Guide

**How Nexus eliminates configuration complexity while delivering enterprise-grade functionality.**

## The Zero Configuration Promise

With Nexus, this is **literally all you need**:

```python
from nexus import Nexus

app = Nexus()
app.start()
```

No configuration files. No environment variables. No setup scripts. No infrastructure dependencies.

**You immediately get**:
- ✅ **Enterprise-grade API server** on port 8000
- ✅ **Health monitoring** at `/health`
- ✅ **Auto-discovery** of workflows
- ✅ **CLI interface** with commands
- ✅ **MCP server** for AI agents on port 3001
- ✅ **Cross-channel session sync**
- ✅ **Event-driven architecture**
- ✅ **Durable workflow execution**

## How Zero Configuration Works

### **Smart Port Selection**

Nexus automatically finds available ports:

```python
app = Nexus()
# Automatically selects:
# - Port 8000 for API (or 8001, 8002, etc. if 8000 is busy)
# - Port 3001 for MCP (or 3002, 3003, etc. if 3001 is busy)
```

**If you need specific ports**:
```python
app = Nexus(api_port=8080, mcp_port=3002)
```

### **Enterprise Defaults**

Unlike other frameworks that start basic and require configuration for production, Nexus starts with **enterprise defaults**:

```python
app = Nexus()
# You automatically get:
# - Enterprise-grade server (not development server)
# - Built-in authentication support (OAuth2, API keys)
# - Monitoring and observability (Prometheus, OpenTelemetry)
# - Request/response compression
# - CORS support
# - Rate limiting capabilities
# - Health check endpoints
# - API documentation generation
```

### **Intelligent Discovery**

Nexus automatically discovers workflows in your project:

```python
# Just create workflow files and Nexus finds them
# workflows/process_payment.py
# workflows/send_email.py
# workflow_user_management.py
# my_data_workflow.py

app = Nexus()
app.start()
# All workflows automatically registered and available!
```

**Discovery patterns**:
- `workflows/*.py`
- `*.workflow.py`
- `workflow_*.py`
- `*_workflow.py`
- `src/workflows/*.py`
- `app/workflows/*.py`

## Zero Configuration Examples

### **Basic Web API**

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Create platform (zero config)
app = Nexus()

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://api.github.com/users/octocat"
})

# Register workflow
app.register("get-user", workflow.build())

# Start platform
app.start()

# Immediately available:
# 🌐 API: POST http://localhost:8000/workflows/get-user/execute
# 💻 CLI: nexus run get-user
# 🤖 MCP: Available for AI agents
```

### **Data Processing Pipeline**

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()  # Zero configuration

# ETL workflow
etl_workflow = WorkflowBuilder()
etl_workflow.add_node("CSVReaderNode", "extract", {"file_path": "data.csv"})
etl_workflow.add_node("PythonCodeNode", "transform", {"code": "return {'processed': data}"})
etl_workflow.add_node("JSONWriterNode", "load", {"output_path": "result.json"})

app.register("etl-pipeline", etl_workflow.build())
app.start()

# Zero setup, immediately production-ready!
```

### **AI Agent Platform**

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()  # Zero configuration for AI

# AI workflow
ai_workflow = WorkflowBuilder()
ai_workflow.add_node("LLMAgentNode", "chat", {
    "provider": "openai",
    "model": "gpt-4",
    "use_real_mcp": True
})

app.register("ai-assistant", ai_workflow.build())
app.start()

# AI agents can immediately connect via MCP on port 3001
# No additional setup required!
```

## When You Need Configuration

Nexus's zero-config approach covers 80% of use cases. For the remaining 20%, configuration is **optional and progressive**:

### **Constructor Options**

```python
from nexus import Nexus

# Add enterprise features
app = Nexus(
    enable_auth=True,           # OAuth2, RBAC, API keys
    enable_monitoring=True,     # Prometheus, metrics
    rate_limit=1000,           # Requests per minute
    api_port=8080,             # Custom API port
    mcp_port=3002,             # Custom MCP port
    auto_discovery=False       # Disable auto-discovery
)
```

### **Attribute Configuration**

```python
app = Nexus()

# Fine-tune authentication
app.auth.strategy = "oauth2"
app.auth.provider = "google"
app.auth.scopes = ["email", "profile"]

# Configure monitoring
app.monitoring.interval = 30
app.monitoring.exporters = ["prometheus", "datadog"]

# Configure API behavior
app.api.cors_enabled = True
app.api.cors_origins = ["https://myapp.com"]
app.api.max_request_size = 50 * 1024 * 1024  # 50MB
```

### **Plugin System**

```python
app = Nexus()

# Add optional capabilities
app.enable_auth()                    # Method chaining
app.enable_monitoring()
app.use_plugin("custom-auth-plugin")

app.start()
```

## No Configuration Files Needed

Unlike traditional frameworks, Nexus doesn't require configuration files:

**Traditional Framework**:
```yaml
# settings.yaml (required)
server:
  host: 0.0.0.0
  port: 8000
  workers: 4

database:
  url: postgresql://...
  pool_size: 20

auth:
  provider: oauth2
  client_id: ...

monitoring:
  enabled: true
  exporter: prometheus

# ... 100 more lines
```

**Nexus**:
```python
# No files needed!
from nexus import Nexus

app = Nexus()
app.start()
```

**Optional configuration file** (if you really want one):
```python
# nexus.yaml (optional)
api:
  port: 8080
auth:
  enabled: true

# Use with:
app = Nexus.from_config("nexus.yaml")
```

## Environment Variables (Optional)

Nexus works without any environment variables, but supports them for deployment flexibility:

```bash
# All optional
export NEXUS_API_PORT=8000
export NEXUS_MCP_PORT=3001
export NEXUS_AUTH_ENABLED=true
export NEXUS_MONITORING_ENABLED=true
```

```python
from nexus import Nexus

# Automatically reads environment variables if present
app = Nexus()
app.start()
```

## Docker Deployment (Zero Config)

**Dockerfile**:
```dockerfile
FROM python:3.12-slim
RUN pip install kailash-nexus
COPY . /app
WORKDIR /app
EXPOSE 8000 3001
CMD ["python", "main.py"]
```

**main.py**:
```python
from nexus import Nexus

app = Nexus()
app.start()
```

**Run**:
```bash
docker build -t my-app .
docker run -p 8000:8000 -p 3001:3001 my-app
```

No configuration files, no environment setup, no complex orchestration.

## Zero Configuration Benefits

### **Faster Development**

```python
# Traditional: 30 minutes of configuration
# - Create config files
# - Set up database connections
# - Configure authentication
# - Set up monitoring
# - Configure logging
# - Set up development server
# - Configure CORS
# - Set up health checks

# Nexus: 30 seconds
from nexus import Nexus
app = Nexus()
app.start()
# Everything already configured!
```

### **Fewer Bugs**

No configuration means no configuration bugs:
- ✅ No typos in YAML files
- ✅ No missing environment variables
- ✅ No port conflicts
- ✅ No authentication misconfiguration
- ✅ No monitoring setup errors

### **Better Security**

Enterprise defaults mean secure defaults:
- ✅ HTTPS-ready server
- ✅ Secure session management
- ✅ Built-in CSRF protection
- ✅ Rate limiting enabled
- ✅ Security headers included

### **Easier Deployment**

Zero configuration means:
- ✅ No config files to manage
- ✅ No environment-specific settings
- ✅ No configuration drift between environments
- ✅ Immutable deployments

### **Simplified Testing**

```python
# Test setup is trivial
def test_my_workflow():
    app = Nexus()  # Zero setup
    app.register("test", my_workflow)

    # Test immediately
    result = app.execute_workflow("test", {})
    assert result.success
```

## Progressive Configuration

When you do need configuration, Nexus makes it **progressive**:

**Level 1: Zero config** (most users)
```python
app = Nexus()
```

**Level 2: Constructor options** (some customization)
```python
app = Nexus(enable_auth=True, api_port=8080)
```

**Level 3: Attribute configuration** (fine-tuning)
```python
app = Nexus()
app.auth.strategy = "custom"
app.monitoring.exporters = ["prometheus", "datadog"]
```

**Level 4: Plugin system** (advanced features)
```python
app = Nexus()
app.use_plugin("custom-auth")
app.use_plugin("advanced-monitoring")
```

**Level 5: Configuration file** (enterprise deployment)
```python
app = Nexus.from_config("production.yaml")
```

## Zero Configuration Philosophy

**Why zero configuration matters**:

1. **Cognitive Load**: Fewer decisions = more focus on business logic
2. **Time to Value**: Immediate productivity, no setup time
3. **Error Reduction**: No configuration bugs
4. **Better Defaults**: Enterprise-grade from day one
5. **Easier Onboarding**: New team members productive immediately

**When configuration is needed**:
- Specific organizational requirements
- Integration with existing systems
- Advanced performance tuning
- Compliance requirements

**Nexus principle**: **Make the common case trivial, make the advanced case possible.**
