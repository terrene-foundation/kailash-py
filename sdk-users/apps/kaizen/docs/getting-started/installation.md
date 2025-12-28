# Installation Guide

**Setting up Kaizen for signature-based AI development**

This guide walks you through installing Kaizen and setting up your development environment for signature-based AI programming.

## 🎯 Installation Options

### Option 1: Install with Kailash SDK (Recommended)

Install Kaizen as part of the complete Kailash ecosystem:

```bash
# Install Kailash with Kaizen support
pip install kailash[kaizen]
```

**Benefits:**
- Complete ecosystem integration
- Access to DataFlow and Nexus frameworks
- Optimized dependency resolution
- Future-proof installation

### Option 2: Standalone Kaizen Installation

Install only the Kaizen framework:

```bash
# Install standalone Kaizen
pip install kailash-kaizen
```

**Use when:**
- You only need Kaizen features
- Working with existing Kailash installations
- Minimal installation requirements

### Option 3: Development Installation

Install from source for development or latest features:

```bash
# Clone the repository
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash_python_sdk

# Install in development mode
pip install -e ".[kaizen]"
```

## 🔧 Prerequisites

### Python Environment

**Python Version:**
```bash
# Check Python version (3.8+ required)
python --version
# or
python3 --version
```

**Virtual Environment (Strongly Recommended):**
```bash
# Create virtual environment
python -m venv kaizen-env

# Activate virtual environment
# On Windows:
kaizen-env\Scripts\activate
# On macOS/Linux:
source kaizen-env/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### System Dependencies

**Windows:**
```bash
# No additional system dependencies required
# Visual Studio Build Tools may be needed for some packages
```

**macOS:**
```bash
# Install Xcode command line tools if needed
xcode-select --install
```

**Linux (Ubuntu/Debian):**
```bash
# Install build essentials
sudo apt-get update
sudo apt-get install build-essential python3-dev
```

## 📦 Core Installation

### Step 1: Install Kaizen

Choose your preferred installation method:

```bash
# Recommended: Full ecosystem
pip install kailash[kaizen]

# Alternative: Standalone
pip install kailash-kaizen
```

### Step 2: Install Optional Dependencies

**Enterprise Features:**
```bash
# For memory systems and audit trails
pip install kailash[kaizen,enterprise]
```

**Development Tools:**
```bash
# For development and testing
pip install kailash[kaizen,dev]
```

**Complete Installation:**
```bash
# Everything included
pip install kailash[kaizen,enterprise,dev,dataflow,nexus]
```

## 🔑 API Configuration

### Model Access Setup

**OpenAI (Most Common):**
```bash
# Set OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# On Windows:
set OPENAI_API_KEY=your-api-key-here
```

**Alternative Models:**
```bash
# Anthropic Claude
export ANTHROPIC_API_KEY="your-key"

# Azure OpenAI
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="your-endpoint"
```

**Configuration File (Optional):**
```yaml
# Create ~/.config/kaizen/config.yaml
api_keys:
  openai: "your-openai-key"
  anthropic: "your-anthropic-key"

default_model: "gpt-4"
enterprise_features: true
```

## ✅ Verification

### Test Basic Installation

Create a test file `test_kaizen.py`:

```python
import kaizen

# Test framework initialization
print("Testing Kaizen installation...")

try:
    # Initialize framework
    framework = kaizen.Kaizen()
    print("✅ Framework initialization: SUCCESS")

    # Test agent creation
    agent = framework.create_agent("test_agent", {"model": "gpt-3.5-turbo"})
    print("✅ Agent creation: SUCCESS")

    # Test Core SDK integration
    from kailash.runtime.local import LocalRuntime
    runtime = LocalRuntime()
    print("✅ Core SDK integration: SUCCESS")

    print("\n🎉 Kaizen installation verified successfully!")
    print(f"Framework version: {kaizen.__version__}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please check your installation")
except Exception as e:
    print(f"❌ Error: {e}")
    print("Installation may have issues")
```

Run the test:
```bash
python test_kaizen.py
```

**Expected Output:**
```
Testing Kaizen installation...
✅ Framework initialization: SUCCESS
✅ Agent creation: SUCCESS
✅ Core SDK integration: SUCCESS

🎉 Kaizen installation verified successfully!
Framework version: 0.1.0
```

### Test Signature-Based Agent

Create `test_signature.py`:

```python
import kaizen
from kailash.runtime.local import LocalRuntime

# Initialize framework with signature programming
framework = kaizen.Kaizen(signature_programming_enabled=True)

# Create signature-based agent
agent = framework.create_agent(
    "hello_agent",
    signature="name -> greeting"
)

print("✅ Signature-based agent created successfully!")
print("Ready for quickstart tutorial!")
```

## 🚨 Troubleshooting

### Common Installation Issues

**1. Python Version Conflicts**
```bash
# Error: Python 3.7 or lower
# Solution: Upgrade Python
pyenv install 3.8.10  # Using pyenv
# Or download from python.org
```

**2. Permission Errors**
```bash
# Error: Permission denied during pip install
# Solution: Use user installation
pip install --user kailash[kaizen]
```

**3. Build Errors**
```bash
# Error: Microsoft Visual C++ 14.0 is required (Windows)
# Solution: Install Visual Studio Build Tools
# Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

**4. Module Not Found**
```bash
# Error: ModuleNotFoundError: No module named 'kaizen'
# Solutions:
# 1. Check virtual environment is activated
# 2. Verify installation: pip list | grep kaizen
# 3. Try reinstalling: pip uninstall kailash-kaizen && pip install kailash[kaizen]
```

**5. Import Errors**
```bash
# Error: ImportError: No module named 'kailash'
# Solution: Install Core SDK
pip install kailash
```

### Performance Issues

**1. Slow Import Times**
```python
# Issue: Framework takes >5 seconds to import
# Check: Use lazy loading
import kaizen
framework = kaizen.Kaizen(lazy_runtime=True)
```

**2. Memory Usage**
```python
# Issue: High memory usage
# Solution: Configure memory limits
framework = kaizen.Kaizen(config={
    'memory_enabled': False,  # Disable if not needed
    'optimization_enabled': True
})
```

### API Key Issues

**1. Invalid API Key**
```bash
# Error: Authentication failed
# Solutions:
# 1. Verify key: echo $OPENAI_API_KEY
# 2. Check key format (should start with sk-)
# 3. Verify account has credits
```

**2. Rate Limiting**
```python
# Issue: Rate limit exceeded
# Solution: Configure rate limiting
agent_config = {
    "model": "gpt-3.5-turbo",  # Use cheaper model
    "max_tokens": 100,         # Limit tokens
    "temperature": 0.7
}
```

### Platform-Specific Issues

**Windows:**
```bash
# Long path issues
git config --system core.longpaths true

# PowerShell execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**macOS:**
```bash
# SSL certificate issues
/Applications/Python\ 3.x/Install\ Certificates.command
```

**Linux:**
```bash
# Package manager conflicts
sudo apt-get install python3-distutils
```

## 🔧 Development Environment

### IDE Configuration

**VS Code Extensions:**
- Python
- Python Docstring Generator
- GitLens (for version control)

**PyCharm Configuration:**
1. Set Python interpreter to your virtual environment
2. Enable auto-import for kaizen modules
3. Configure code style for PEP 8

### Environment Variables

Create `.env` file in your project:
```bash
# API Keys
OPENAI_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here

# Kaizen Configuration
KAIZEN_DEBUG=true
KAIZEN_ENTERPRISE_FEATURES=true
KAIZEN_LOG_LEVEL=INFO
```

Load in Python:
```python
from dotenv import load_dotenv
load_dotenv()

import kaizen
framework = kaizen.Kaizen()
```

## 📁 Project Structure

Recommended project structure:
```
my-kaizen-project/
├── .env                    # Environment variables
├── requirements.txt        # Dependencies
├── agents/                 # Agent definitions
│   ├── __init__.py
│   └── text_processor.py
├── workflows/              # Workflow definitions
│   ├── __init__.py
│   └── analysis_workflow.py
├── config/                 # Configuration files
│   └── kaizen.yaml
└── tests/                  # Test files
    └── test_agents.py
```

**requirements.txt:**
```
kailash[kaizen]>=0.9.0
python-dotenv>=0.19.0
pytest>=7.0.0
```

## 🎯 Next Steps

After successful installation:

1. **[Quickstart Tutorial](quickstart.md)** - Create your first agent in 5 minutes
2. **[First Agent Guide](first-agent.md)** - Detailed agent creation walkthrough
3. **[Signature Programming Guide](../guides/signature-programming.md)** - Learn declarative AI patterns

## 🛠️ Advanced Installation

### Docker Installation

**Dockerfile:**
```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Kaizen
RUN pip install kailash[kaizen]

# Set environment variables
ENV KAIZEN_ENTERPRISE_FEATURES=true

WORKDIR /app
COPY . .

CMD ["python", "your_app.py"]
```

### Production Deployment

**Requirements for production:**
```bash
# Production dependencies
pip install kailash[kaizen,enterprise,monitoring]

# Optional: Database support
pip install kailash[kaizen,dataflow]

# Optional: Multi-channel deployment
pip install kailash[kaizen,nexus]
```

**Configuration for production:**
```python
# Production configuration
import kaizen

framework = kaizen.Kaizen(config={
    'enterprise_features': True,
    'audit_trail_enabled': True,
    'monitoring_enabled': True,
    'security_level': 'high'
})
```

---

**Installation complete?** Continue to the **[Quickstart Tutorial](quickstart.md)** to create your first Kaizen agent!
