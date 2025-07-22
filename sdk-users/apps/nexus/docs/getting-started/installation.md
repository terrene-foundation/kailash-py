# Installation Guide

**Install Nexus and get ready to build workflow-native applications.**

## Requirements

- **Python**: 3.8+ (3.12+ recommended)
- **Operating System**: Linux, macOS, Windows
- **Memory**: 256MB minimum, 1GB recommended
- **Dependencies**: Automatically installed

## Quick Install

### Install via pip

```bash
pip install kailash-nexus
```

### Install from source

```bash
git clone https://github.com/kailash/nexus.git
cd nexus
pip install -e .
```

### Verify Installation

```python
from nexus import Nexus
print("✅ Nexus installed successfully!")

# Quick test
app = Nexus()
health = app.health_check()
print(f"Platform: {health['platform_type']}")
print(f"Server Type: {health['server_type']}")
```

## Development Environment

### Option 1: Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv nexus-env
source nexus-env/bin/activate  # On Windows: nexus-env\Scripts\activate

# Install Nexus
pip install kailash-nexus

# Verify
python -c "from nexus import Nexus; print('Ready!')"
```

### Option 2: Poetry

```bash
# Install Poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Create new project
poetry init
poetry add kailash-nexus

# Activate environment
poetry shell

# Verify
python -c "from nexus import Nexus; print('Ready!')"
```

### Option 3: Conda

```bash
# Create conda environment
conda create -n nexus-env python=3.12
conda activate nexus-env

# Install Nexus
pip install kailash-nexus

# Verify
python -c "from nexus import Nexus; print('Ready!')"
```

## Production Environment

### Docker Installation

Create a `Dockerfile`:

```dockerfile
FROM python:3.12-slim

# Install dependencies
RUN pip install kailash-nexus

# Copy your application
COPY . /app
WORKDIR /app

# Expose ports
EXPOSE 8000 3001

# Run Nexus
CMD ["python", "main.py"]
```

Create `main.py`:

```python
from nexus import Nexus

app = Nexus(
    enable_auth=True,
    enable_monitoring=True
)

# Auto-discover workflows
app.start()
```

Build and run:

```bash
docker build -t my-nexus-app .
docker run -p 8000:8000 -p 3001:3001 my-nexus-app
```

### Kubernetes Deployment

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nexus-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nexus-app
  template:
    metadata:
      labels:
        app: nexus-app
    spec:
      containers:
      - name: nexus
        image: my-nexus-app:latest
        ports:
        - containerPort: 8000
        - containerPort: 3001
        env:
        - name: NEXUS_API_PORT
          value: "8000"
        - name: NEXUS_MCP_PORT
          value: "3001"
---
apiVersion: v1
kind: Service
metadata:
  name: nexus-service
spec:
  selector:
    app: nexus-app
  ports:
  - name: api
    port: 8000
    targetPort: 8000
  - name: mcp
    port: 3001
    targetPort: 3001
  type: LoadBalancer
```

Deploy:

```bash
kubectl apply -f deployment.yaml
```

## Optional Dependencies

### For AI/ML Workflows

```bash
pip install kailash-nexus kailash[ai]
```

Includes:
- OpenAI integration
- Ollama support
- Vector databases
- Embedding generators

### For Enterprise Features

```bash
pip install kailash-nexus kailash[enterprise]
```

Includes:
- OAuth2 providers
- Advanced monitoring
- Enterprise connectors
- Compliance tools

### For Development

```bash
pip install kailash-nexus kailash[dev]
```

Includes:
- Testing utilities
- Development servers
- Debug tools
- Code generators

## Configuration

### Environment Variables (Optional)

Nexus works with zero configuration, but you can customize:

```bash
# API Configuration
export NEXUS_API_PORT=8000
export NEXUS_API_HOST=0.0.0.0

# MCP Configuration
export NEXUS_MCP_PORT=3001

# Security
export NEXUS_SECRET_KEY=your-secret-key

# Monitoring
export NEXUS_MONITORING_ENABLED=true
```

### Configuration File (Optional)

Create `nexus.yaml`:

```yaml
api:
  port: 8000
  host: "0.0.0.0"
  cors_enabled: true

mcp:
  port: 3001
  transport: "stdio"

auth:
  enabled: true
  strategy: "oauth2"

monitoring:
  enabled: true
  interval: 30
```

Use with:

```python
from nexus import Nexus

app = Nexus.from_config("nexus.yaml")
app.start()
```

## Verification

### Quick Health Check

```python
from nexus import Nexus

app = Nexus()
health = app.health_check()

print(f"Status: {health['status']}")
print(f"Platform: {health['platform_type']}")
print(f"Workflows: {health['workflows']}")
```

### Test Multi-Channel Access

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Create platform
app = Nexus()

# Create test workflow
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "test", {
    "url": "https://httpbin.org/get"
})

# Register and start
app.register("test-workflow", workflow)
app.start()

print("✅ Nexus is ready!")
print("🌐 API: http://localhost:8000")
print("💻 CLI: nexus run test-workflow")
print("🤖 MCP: Available for AI agents")
```

## Troubleshooting

### Import Errors

```bash
# Check Python version
python --version  # Should be 3.8+

# Check installation
pip show kailash

# Reinstall if needed
pip uninstall kailash-nexus
pip install kailash-nexus
```

### Port Conflicts

```python
from nexus import Nexus

# Use different ports
app = Nexus(api_port=8080, mcp_port=3002)
```

### Permission Issues

```bash
# Linux/macOS: Use user install
pip install --user kailash-nexus

# Or fix permissions
sudo chown -R $USER ~/.local/
```

### Docker Issues

```bash
# Check Docker
docker --version

# Test Python image
docker run -it python:3.12-slim python -c "print('OK')"

# Check port availability
netstat -an | grep 8000
```

## Next Steps

- **[Quick Start](quick-start.md)** - Get running in 1 minute
- **[First Workflow](first-workflow.md)** - Create your first workflow
- **[Basic Usage](basic-usage.md)** - Learn essential patterns

## Support

- **Documentation**: [docs.nexus.dev](https://docs.nexus.dev)
- **Issues**: [GitHub Issues](https://github.com/kailash/nexus/issues)
- **Community**: [GitHub Discussions](https://github.com/kailash/nexus/discussions)
