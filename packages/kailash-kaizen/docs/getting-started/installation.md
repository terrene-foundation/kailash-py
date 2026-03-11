# Installation Guide

Complete setup instructions for the Kaizen Framework, including development tools and optional dependencies.

## System Requirements

### Minimum Requirements
- **Python**: 3.9+ (3.11+ recommended)
- **Memory**: 4GB RAM minimum, 8GB+ recommended
- **Storage**: 2GB free space
- **Platform**: Linux, macOS, Windows (WSL2)

### Optional Requirements
- **Docker**: For integration testing and MCP servers
- **Git**: For development and contribution workflows
- **VS Code/PyCharm**: Recommended IDEs with Python support

## Installation Options

### Option 1: Basic Installation (Users)

```bash
# Core framework only
pip install kailash-kaizen

# Verify installation
python -c "from kaizen import Kaizen; print('✅ Kaizen installed successfully!')"
```

### Option 2: Complete Installation (Developers)

```bash
# With all optional features
pip install kailash-kaizen[all]

# Or specific feature sets
pip install kailash-kaizen[dev,mcp,enterprise]
```

### Option 3: Development Installation

```bash
# Clone the repository
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-kaizen

# Install in development mode
pip install -e .

# Install development dependencies
pip install -e .[dev]

# Verify development setup
pytest tests/unit/ -v
```

## Package Feature Sets

### Core Features (Always Included)
- Basic framework and agent creation
- Kailash SDK integration
- Local runtime execution
- Basic configuration management

### Optional Feature Sets

#### `[dev]` - Development Tools
```bash
pip install kailash-kaizen[dev]
```
Includes:
- pytest and testing utilities
- Code quality tools (black, flake8, mypy)
- Documentation building tools
- Performance profiling tools

#### `[mcp]` - Model Context Protocol
```bash
pip install kailash-kaizen[mcp]
```
Includes:
- MCP client/server libraries
- Auto-discovery capabilities
- Protocol validation tools

#### `[enterprise]` - Enterprise Features
```bash
pip install kailash-kaizen[enterprise]
```
Includes:
- Advanced security modules
- Audit trail and compliance tools
- Performance monitoring
- Distributed transparency system

#### `[all]` - Complete Installation
```bash
pip install kailash-kaizen[all]
```
Includes all feature sets above.

## Development Environment Setup

### 1. Python Environment

Using **conda** (recommended):
```bash
conda create -n kaizen python=3.11
conda activate kaizen
pip install kailash-kaizen[dev]
```

Using **venv**:
```bash
python -m venv kaizen-env
source kaizen-env/bin/activate  # On Windows: kaizen-env\Scripts\activate
pip install kailash-kaizen[dev]
```

Using **poetry**:
```bash
poetry install --extras "dev mcp enterprise"
poetry shell
```

### 2. Docker Setup (Optional)

For integration testing and MCP server development:

```bash
# Install Docker Desktop or Docker Engine
# Verify Docker installation
docker --version
docker-compose --version

# Test with Kailash infrastructure
cd tests/utils
./test-env up
./test-env status
```

### 3. IDE Configuration

#### VS Code Setup
Install recommended extensions:
```bash
code --install-extension ms-python.python
code --install-extension ms-python.black-formatter
code --install-extension ms-python.flake8
code --install-extension ms-python.mypy-type-checker
```

Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./kaizen-env/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black"
}
```

#### PyCharm Setup
1. Create new project with existing sources
2. Configure Python interpreter to use virtual environment
3. Enable pytest as test runner
4. Configure black as code formatter

## Verification Steps

### 1. Basic Import Test
```python
# Test core framework
from kaizen import Kaizen
kaizen = Kaizen()
print("✅ Framework initialized")

# Test Core SDK integration
from kailash.runtime.local import LocalRuntime
runtime = LocalRuntime()
print("✅ Kailash SDK integration working")
```

### 2. Agent Creation Test
```python
from kaizen import Kaizen

kaizen = Kaizen()
agent = kaizen.create_agent("test_agent", {
    "model": "gpt-3.5-turbo",
    "temperature": 0.7
})
print("✅ Agent creation working")
print(f"📊 Agent workflow: {agent.workflow}")
```

### 3. Development Tools Test
```bash
# Run unit tests
pytest tests/unit/ -v

# Check code quality
black --check src/
flake8 src/
mypy src/

# Performance baseline
python -m pytest tests/performance/ -v
```

## Configuration

### 1. Environment Variables (Optional)

Create `.env` file in your project root:
```bash
# AI Provider Configuration
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here

# Kailash Configuration
KAILASH_LOG_LEVEL=INFO
KAILASH_PERFORMANCE_TRACKING=true

# Kaizen-specific Configuration
KAIZEN_CACHE_ENABLED=true
KAIZEN_TELEMETRY_ENABLED=false
```

### 2. Configuration File (Optional)

Create `kaizen.yaml`:
```yaml
framework:
  signature_programming_enabled: false  # Not yet implemented
  mcp_integration_enabled: false       # Not yet implemented
  multi_agent_enabled: false          # Not yet implemented
  transparency_enabled: false         # Not yet implemented

performance:
  lazy_loading: true
  cache_enabled: true
  import_optimization: true

development:
  verbose_logging: true
  performance_tracking: true
  test_mode: true
```

## Performance Considerations

### Import Performance
The framework currently has a ~1100ms import time due to Core SDK node registration:

```python
import time
start = time.time()
from kaizen import Kaizen
end = time.time()
print(f"Import time: {(end - start) * 1000:.0f}ms")
```

**Optimization strategies**:
- Use lazy imports in production code
- Consider module-level imports only when needed
- Future releases will optimize this

### Memory Usage
- Base framework: ~50MB
- With Core SDK: ~100MB
- With all features: ~200MB

## Troubleshooting

### Common Installation Issues

#### 1. Dependency Conflicts
```bash
# Clear pip cache and reinstall
pip cache purge
pip uninstall kailash-kaizen kailash
pip install kailash-kaizen[all]
```

#### 2. Import Errors
```bash
# Verify Core SDK installation
pip install kailash[core]

# Check Python path
python -c "import sys; print('\n'.join(sys.path))"
```

#### 3. Performance Issues
```bash
# Test import performance
python -c "import time; s=time.time(); import kaizen; print(f'{(time.time()-s)*1000:.0f}ms')"

# Enable performance tracking
export KAIZEN_PERFORMANCE_TRACKING=true
```

#### 4. Docker Issues
```bash
# Reset Docker environment
docker system prune -f
cd tests/utils && ./test-env down && ./test-env up
```

### Getting Help

- **Documentation**: [Complete guides](../README.md)
- **Issues**: GitHub Issues for bugs and feature requests
- **Discussions**: Community discussions and questions
- **Enterprise**: Contact for enterprise support

## Next Steps

After successful installation:

1. [**Concepts Guide**](concepts.md) - Understand Kaizen architecture
2. [**Basic Examples**](examples.md) - Try working examples
3. [**Development Guide**](../development/contributing.md) - Contribute to the project
4. [**Advanced Topics**](../advanced/) - Explore advanced capabilities

---

**✅ Installation Complete**: You're ready to build enterprise AI workflows with Kaizen!
