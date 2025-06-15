# Utility Scripts

Miscellaneous utility scripts for the Kailash SDK development environment.

## 📁 Scripts Overview

| Script | Purpose | Service | Port |
|--------|---------|---------|------|
| `start-ai-registry.py` | Start AI model registry server | Registry API | 8765 |

## 🚀 Quick Start

### AI Model Registry
```bash
# Start the registry server
./start-ai-registry.py

# Registry available at http://localhost:8765
```

## 📋 Script Details

### `start-ai-registry.py`
**Purpose**: Start the AI model registry server for managing and discovering AI models

**Features**:
- **Model Discovery** - Find available AI models
- **Registry API** - REST API for model management  
- **Health Monitoring** - Model status and availability
- **Configuration Management** - Model parameters and settings

**Usage**:
```bash
# Start with default configuration
./start-ai-registry.py

# Custom port
./start-ai-registry.py --port 9000

# Debug mode
./start-ai-registry.py --debug

# Custom config file
./start-ai-registry.py --config /path/to/config.yaml
```

**API Endpoints**:
- `GET /health` - Service health check
- `GET /models` - List available models
- `POST /models` - Register new model
- `GET /models/{id}` - Get model details
- `DELETE /models/{id}` - Unregister model

**Configuration**:
```yaml
# config.yaml
registry:
  port: 8765
  host: "0.0.0.0"
  models_dir: "/models"
  
logging:
  level: "INFO"
  format: "%(asctime)s - %(levelname)s - %(message)s"

models:
  default_timeout: 30
  health_check_interval: 60
```

## 🔧 Integration

### With SDK Development
```python
# In your workflows
from kailash.nodes.ai import LLMAgentNode

# Registry automatically discovers models
agent = LLMAgentNode(
    name="smart_agent",
    model="registry://gpt-4"  # Uses registry to find model
)
```

### With Development Environment
The registry integrates with the development environment started by `scripts/development/start-development.sh`.

### Health Checks
```bash
# Check if registry is running
curl http://localhost:8765/health

# List available models
curl http://localhost:8765/models
```

## 🐛 Troubleshooting

### Common Issues

**Port conflicts**:
```bash
# Check what's using port 8765
lsof -i :8765

# Start on different port
./start-ai-registry.py --port 9000
```

**Model discovery issues**:
```bash
# Check models directory
ls -la /models

# Verify permissions
chmod -R 755 /models
```

**API connectivity**:
```bash
# Test basic connectivity
curl -v http://localhost:8765/health

# Check firewall settings
sudo ufw status
```

### Service Integration

**Not discovering models**:
- Verify models directory configuration
- Check model file formats
- Review registry logs for errors

**Performance issues**:
- Increase health check intervals
- Monitor memory usage
- Consider caching strategies

## 💡 Usage Patterns

### Development Workflow
```bash
# Start development environment
../development/start-development.sh

# Start AI registry
./start-ai-registry.py

# Registry now available for SDK examples
../testing/test-quick-examples.py
```

### Model Management
```bash
# Register new model
curl -X POST http://localhost:8765/models \
  -H "Content-Type: application/json" \
  -d '{"name": "custom-llm", "endpoint": "http://localhost:11434"}'

# Check model status
curl http://localhost:8765/models/custom-llm
```

## 🤝 Contributing

### Adding New Utilities
1. Create new script in `utils/` directory
2. Follow naming convention: `start-service-name.py`
3. Include proper documentation and help
4. Add integration instructions

### Extending AI Registry
1. Add new API endpoints as needed
2. Implement model validation
3. Add configuration options
4. Update integration documentation

---

**Dependencies**: Python 3.8+, FastAPI (for AI registry)  
**Integration**: SDK development environment  
**Last Updated**: Scripts directory reorganization