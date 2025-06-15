# Kailash SDK Scripts Directory

This directory contains development, testing, and maintenance scripts for the Kailash Python SDK. Scripts are organized by functionality for easy navigation and maintenance.

## 📁 Directory Structure

```
scripts/
├── README.md                          # This file - main navigation guide
├── development/                       # Development environment setup & management
│   ├── setup-environment.sh          # Complete SDK environment setup
│   ├── start-development.sh          # Start development services
│   ├── stop-development.sh           # Stop development services
│   ├── reset-development.sh          # Reset development environment
│   ├── check-status.sh               # Check development environment status
│   └── setup-databases.sh            # Setup test databases
├── testing/                          # Testing and validation scripts
│   ├── test-all-examples.py          # Comprehensive example testing
│   ├── test-quick-examples.py        # Quick smoke tests
│   ├── profile-tests.py              # Performance profiling
│   └── mark-slow-tests.py            # Mark slow-running tests
├── maintenance/                      # Code maintenance and fixes
│   ├── fix-imports.py                # Fix common import/code issues
│   ├── refactor-pythoncode.py        # Refactor PythonCodeNode patterns
│   ├── consolidate-outputs.py        # Consolidate output directories
│   └── fix-hardcoded-paths.py        # Fix hardcoded file paths
├── metrics/                          # Metrics and reporting
│   ├── daily-metrics.sh              # Daily GitHub activity metrics
│   ├── weekly-summary.sh             # Weekly development summaries
│   ├── github-metrics.sh             # Comprehensive GitHub metrics
│   ├── test-coverage-tracker.sh      # Test coverage analysis
│   └── feature-tracker.sh            # Feature development tracking
├── deployment/                       # Deployment and infrastructure
│   ├── deploy-tenant.sh              # Deploy tenant environments
│   ├── setup-github-projects.sh      # Setup GitHub project boards
│   └── teardown-databases.sh         # Teardown test databases
├── studio/                          # Studio-specific scripts
│   ├── start-studio.sh              # Start Kailash Studio
│   ├── start-studio-dev.sh          # Start Studio in development mode
│   └── start-runner-service.sh      # Start workflow runner service
├── collaboration/                   # Team collaboration tools
│   ├── sync-tools.py               # Sync between TODOs, Projects, and Issues
│   ├── team-status.py              # Team workload and status
│   └── claude-helper.py            # Claude Code response parser
└── utils/                          # Utility scripts
    └── start-ai-registry.py        # Start AI model registry server
```

## 🚀 Quick Start

### First Time Setup
```bash
# Setup complete development environment
./development/setup-environment.sh

# Start development services
./development/start-development.sh

# Verify everything is working
./testing/test-quick-examples.py
```

### Daily Development Workflow
```bash
# Check environment status
./development/check-status.sh

# Run comprehensive tests
./testing/test-all-examples.py

# Fix common issues if tests fail
./maintenance/fix-imports.py

# Check daily metrics
./metrics/daily-metrics.sh
```

### Maintenance Tasks
```bash
# Fix import errors and code issues
./maintenance/fix-imports.py --verbose

# Refactor PythonCodeNode string patterns
./maintenance/refactor-pythoncode.py examples/

# Consolidate scattered output directories
./maintenance/consolidate-outputs.py
```

## 📋 Script Categories

### 🔧 Development Scripts
**Purpose**: Setup and manage development environment
**Location**: `development/`
**Key Scripts**: `setup-environment.sh`, `start-development.sh`

### 🧪 Testing Scripts
**Purpose**: Test validation and performance analysis
**Location**: `testing/`
**Key Scripts**: `test-all-examples.py`, `profile-tests.py`

### 🛠️ Maintenance Scripts
**Purpose**: Code quality and cleanup
**Location**: `maintenance/`
**Key Scripts**: `fix-imports.py`, `refactor-pythoncode.py`

### 📊 Metrics Scripts
**Purpose**: Development metrics and reporting
**Location**: `metrics/`
**Key Scripts**: `daily-metrics.sh`, `github-metrics.sh`

### 🚀 Deployment Scripts
**Purpose**: Infrastructure and deployment
**Location**: `deployment/`
**Key Scripts**: `deploy-tenant.sh`, `setup-github-projects.sh`

### 🎨 Studio Scripts
**Purpose**: Kailash Studio management
**Location**: `studio/`
**Key Scripts**: `start-studio.sh`, `start-runner-service.sh`

### 🤝 Collaboration Scripts
**Purpose**: Team coordination and workflow
**Location**: `collaboration/`
**Key Scripts**: `sync-tools.py`, `team-status.py`

### ⚙️ Utility Scripts
**Purpose**: Miscellaneous utilities
**Location**: `utils/`
**Key Scripts**: `start-ai-registry.py`

## 🔧 Prerequisites

### Required Tools
- **Docker** - For development environment
- **Python 3.8+** - For Python scripts
- **Bash** - For shell scripts
- **GitHub CLI** (`gh`) - For metrics and project management
- **curl** - For health checks

### Installation
```bash
# macOS
brew install gh jq

# Ubuntu/Debian
sudo apt install gh jq curl

# Verify installations
docker --version
python3 --version
gh --version
```

## 📖 Usage Patterns

### Running Scripts
```bash
# From project root
./scripts/category/script-name.sh

# With arguments
./scripts/testing/test-all-examples.py --verbose

# Get help
./scripts/maintenance/fix-imports.py --help
```

### Common Workflows

#### 🔄 Daily Development Cycle
1. `./development/check-status.sh` - Verify environment
2. `./testing/test-quick-examples.py` - Quick validation
3. `./maintenance/fix-imports.py` - Fix any issues
4. `./metrics/daily-metrics.sh` - Check progress

#### 🧹 Weekly Maintenance
1. `./testing/test-all-examples.py` - Full test suite
2. `./maintenance/refactor-pythoncode.py` - Code improvements
3. `./metrics/weekly-summary.sh` - Progress report
4. `./maintenance/consolidate-outputs.py` - Cleanup

#### 🚀 Release Preparation
1. `./testing/test-all-examples.py` - Comprehensive testing
2. `./metrics/github-metrics.sh` - Release metrics
3. `./deployment/setup-github-projects.sh` - Project board
4. `./collaboration/sync-tools.py` - Sync collaboration tools

## 🐛 Troubleshooting

### Common Issues

**Scripts don't execute**
```bash
# Make scripts executable
chmod +x scripts/**/*.sh
```

**Docker not running**
```bash
# Start Docker and retry
docker info
./development/start-development.sh
```

**GitHub CLI not authenticated**
```bash
# Authenticate with GitHub
gh auth login
```

**Python import errors**
```bash
# Fix common import issues
./maintenance/fix-imports.py --verbose
```

### Getting Help
- Each script supports `--help` flag for usage information
- Check individual category READMEs for detailed documentation
- Review script headers for specific requirements and examples

## 🤝 Contributing

### Adding New Scripts
1. Choose appropriate category directory
2. Follow naming conventions:
   - Shell scripts: `kebab-case.sh`
   - Python scripts: `snake_case.py`
3. Include comprehensive header documentation
4. Add entry to category README
5. Update main README if needed

### Script Standards
- Include `#!/usr/bin/env python3` or `#!/bin/bash` shebang
- Add descriptive docstring/comment header
- Support `--help` flag
- Use consistent error handling
- Include usage examples

## 📚 Related Documentation
- [SDK Development Guide](../sdk-users/developer/)
- [Testing Guide](../sdk-users/essentials/)
- [Troubleshooting](../sdk-users/developer/07-troubleshooting.md)
- [Contributing Guidelines](../CONTRIBUTING.md)

---

**Last Updated**: Created during scripts directory reorganization
**Maintainer**: Kailash SDK Team
**Next Review**: When new script categories are added
