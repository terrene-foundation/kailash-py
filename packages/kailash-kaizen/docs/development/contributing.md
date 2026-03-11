# Contributing to Kaizen Framework

Guidelines for contributing to the Kaizen Framework development, including development setup, coding standards, testing requirements, and contribution workflows.

## Quick Start for Contributors

### 1. **Development Setup**
```bash
# Clone repository
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-kaizen

# Create development environment
python -m venv kaizen-dev
source kaizen-dev/bin/activate  # On Windows: kaizen-dev\Scripts\activate

# Install in development mode
pip install -e .[dev]

# Verify setup
pytest tests/unit/ -v
```

### 2. **Make Your Changes**
- Follow coding standards and patterns
- Write comprehensive tests
- Update documentation
- Validate with quality checks

### 3. **Submit Contribution**
- Create feature branch
- Test thoroughly
- Submit pull request
- Respond to review feedback

## Development Environment

### Prerequisites

**Required**:
- Python 3.9+ (3.11+ recommended)
- Git 2.0+
- pip 21.0+

**Optional but Recommended**:
- Docker and Docker Compose (for integration testing)
- VS Code or PyCharm (with Python extensions)
- Pre-commit hooks

### Development Installation

```bash
# Clone and enter directory
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-kaizen

# Create isolated environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e .[dev,test,mcp]

# Install pre-commit hooks (optional but recommended)
pre-commit install

# Verify development setup
python -c "from kaizen import Kaizen; print('✅ Development setup complete')"
pytest tests/unit/ --verbose
```

### IDE Configuration

#### VS Code Setup
```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true
}
```

#### PyCharm Setup
1. Open project directory in PyCharm
2. Configure Python interpreter: Settings → Project → Python Interpreter → Add → Existing Environment → `./venv/bin/python`
3. Enable pytest: Settings → Tools → Python Integrated Tools → Default test runner → pytest
4. Configure code style: Settings → Editor → Code Style → Python → Set from → Black

## Project Structure

Understanding the codebase organization:

```
kailash-kaizen/
├── src/kaizen/              # Source code
│   ├── core/               # Framework core (Kaizen, Agent, Config)
│   ├── signatures/         # Signature programming system
│   ├── nodes/              # Enhanced AI nodes
│   ├── memory/             # Memory system interfaces
│   ├── optimization/       # Auto-optimization framework
│   ├── integrations/       # Framework integrations
│   └── utils/              # Common utilities
├── tests/                  # Test suite
│   ├── unit/               # Unit tests (fast, isolated)
│   ├── integration/        # Integration tests (real infrastructure)
│   └── e2e/                # End-to-end tests (full workflows)
├── docs/                   # Documentation
│   ├── getting-started/    # User guides
│   ├── development/        # Development guides
│   ├── enterprise/         # Enterprise features
│   ├── integration/        # Integration guides
│   ├── advanced/           # Advanced topics
│   ├── reference/          # API reference
│   └── research/           # Research findings
├── examples/               # Working examples
│   ├── 1-single-agent/    # Basic patterns
│   ├── 2-multi-agent/     # Coordination patterns
│   ├── 3-enterprise-workflows/  # Enterprise use cases
│   └── shared/             # Common utilities
├── adr/                    # Architecture Decision Records
├── tracking/               # Implementation status tracking
└── scripts/                # Development utilities
```

## Development Workflow

### 1. Issue Selection and Assignment

**Finding Work**:
- Check [GitHub Issues](https://github.com/terrene-foundation/kailash-py/issues) for open tasks
- Look for issues labeled `good-first-issue` for beginners
- Review [Gap Analysis](../tracking/KAIZEN_GAPS_ANALYSIS.md) for high-priority items
- Check [Implementation Roadmap](../KAIZEN_IMPLEMENTATION_ROADMAP.md) for planned features

**Before Starting**:
- Comment on issue to indicate interest
- Discuss approach with maintainers if needed
- Ensure issue isn't already assigned

### 2. Branch Creation and Development

```bash
# Create feature branch from main
git checkout main
git pull origin main
git checkout -b feature/your-feature-name

# Make your changes
# ... development work ...

# Commit changes with clear messages
git add .
git commit -m "feat: implement signature programming core interfaces

- Add SignatureBase and SignatureCompiler classes
- Implement basic signature parsing and validation
- Add unit tests for signature compilation
- Update documentation with signature patterns

Resolves #123"
```

### 3. Testing Requirements

**All contributions must include comprehensive tests**:

```bash
# Run unit tests (required for all changes)
pytest tests/unit/ -v

# Run integration tests (required for Core SDK integration changes)
pytest tests/integration/ -v

# Run end-to-end tests (required for major features)
pytest tests/e2e/ -v

# Run specific test files
pytest tests/unit/test_framework.py -v
pytest tests/integration/test_agent_workflow.py -v

# Run with coverage reporting
pytest tests/ --cov=src/kaizen --cov-report=html
```

**Test Types Required**:
- **Unit Tests**: For all new classes and functions
- **Integration Tests**: For Core SDK integration features
- **End-to-End Tests**: For complete user workflows
- **Performance Tests**: For optimization changes

### 4. Code Quality Checks

**Automated Quality Checks**:
```bash
# Code formatting
black src/ tests/ examples/

# Import sorting
isort src/ tests/ examples/ --profile black

# Linting
flake8 src/ tests/ examples/

# Type checking
mypy src/kaizen/

# Security scanning
bandit -r src/kaizen/

# Run all quality checks
pre-commit run --all-files
```

**Quality Standards**:
- **Code Coverage**: Minimum 90% for new code
- **Type Hints**: Required for all public APIs
- **Documentation**: Docstrings for all public classes and functions
- **Security**: No security vulnerabilities in dependencies or code

### 5. Documentation Requirements

**Documentation Updates Required**:
- **API Documentation**: For new public interfaces
- **User Guides**: For new features or significant changes
- **Examples**: Working examples for new capabilities
- **ADRs**: Architecture Decision Records for design changes

```bash
# Generate API documentation
sphinx-build -b html docs/ docs/_build/

# Validate documentation links
linkchecker docs/_build/index.html

# Test code examples in documentation
python scripts/test_documentation_examples.py
```

## Coding Standards

### Python Style Guide

**Code Formatting**:
- Use **Black** for code formatting (line length: 88 characters)
- Use **isort** for import sorting (profile: black)
- Follow **PEP 8** conventions
- Use **type hints** for all public APIs

**Example Code Style**:
```python
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from kaizen.core.base import KaizenConfig
from kailash.workflow.builder import WorkflowBuilder


@dataclass
class AgentConfig:
    """Configuration for AI agents with validation and defaults."""

    model: str
    temperature: float = 0.7
    max_tokens: int = 1000
    system_prompt: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"Temperature must be between 0.0 and 2.0, got {self.temperature}")

        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")


class Agent:
    """AI agent with workflow generation and Core SDK integration."""

    def __init__(
        self,
        name: str,
        config: AgentConfig,
        kaizen_instance: "Kaizen"
    ) -> None:
        """Initialize agent with configuration and framework reference.

        Args:
            name: Unique agent identifier
            config: Agent configuration and parameters
            kaizen_instance: Reference to parent framework instance

        Raises:
            ValueError: If name is empty or config is invalid
        """
        if not name.strip():
            raise ValueError("Agent name cannot be empty")

        self._name = name
        self._config = config
        self._kaizen = kaizen_instance
        self._workflow = self._build_workflow()

    @property
    def name(self) -> str:
        """Agent unique identifier."""
        return self._name

    @property
    def config(self) -> AgentConfig:
        """Agent configuration."""
        return self._config

    @property
    def workflow(self) -> WorkflowBuilder:
        """Generated Core SDK workflow."""
        return self._workflow

    def _build_workflow(self) -> WorkflowBuilder:
        """Build Core SDK workflow from agent configuration.

        Returns:
            Configured WorkflowBuilder instance ready for execution
        """
        workflow = WorkflowBuilder()

        # Add enhanced LLM node
        workflow.add_node("KaizenLLMAgentNode", self._name, {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "system_prompt": self._config.system_prompt
        })

        return workflow
```

### Framework-Specific Standards

**Kailash SDK Integration**:
```python
# ✅ CORRECT: Follow Core SDK patterns
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "node_id", config_dict)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# ❌ INCORRECT: Don't use alternative patterns
# workflow.execute(runtime)  # Wrong execution pattern
# workflow.addNode(...)      # Wrong method name
```

**Error Handling**:
```python
# ✅ CORRECT: Comprehensive error handling
from kaizen.core.exceptions import KaizenError, ConfigurationError

def create_agent_safely(name: str, config: Dict[str, Any]) -> Optional[Agent]:
    """Create agent with proper error handling."""
    try:
        validated_config = AgentConfig(**config)
        return Agent(name, validated_config, self)

    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        raise ConfigurationError(f"Invalid agent configuration: {e}")

    except Exception as e:
        logger.error(f"Unexpected error creating agent: {e}")
        raise KaizenError(f"Agent creation failed: {e}")

# ❌ INCORRECT: Silent failures or generic exceptions
def create_agent_badly(name: str, config: Dict[str, Any]) -> Agent:
    try:
        return Agent(name, config, self)
    except:  # Too broad exception handling
        return None  # Silent failure
```

**Testing Standards**:
```python
# ✅ CORRECT: Comprehensive test structure
import pytest
from unittest.mock import Mock, patch

from kaizen.core.framework import Kaizen
from kaizen.core.agents import Agent
from kaizen.core.exceptions import ConfigurationError


class TestAgent:
    """Test suite for Agent class with comprehensive coverage."""

    def setup_method(self) -> None:
        """Setup for each test method."""
        self.kaizen = Kaizen()
        self.valid_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 1000
        }

    def test_agent_creation_success(self) -> None:
        """Test successful agent creation with valid configuration."""
        agent = self.kaizen.create_agent("test_agent", self.valid_config)

        assert agent is not None
        assert agent.name == "test_agent"
        assert agent.config.model == "gpt-3.5-turbo"
        assert agent.config.temperature == 0.7
        assert agent.workflow is not None

    def test_agent_creation_invalid_config(self) -> None:
        """Test agent creation fails with invalid configuration."""
        invalid_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 5.0,  # Invalid temperature
            "max_tokens": 1000
        }

        with pytest.raises(ConfigurationError):
            self.kaizen.create_agent("invalid_agent", invalid_config)

    def test_agent_creation_empty_name(self) -> None:
        """Test agent creation fails with empty name."""
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            self.kaizen.create_agent("", self.valid_config)

    @patch('kaizen.core.agents.WorkflowBuilder')
    def test_workflow_generation(self, mock_workflow_builder: Mock) -> None:
        """Test workflow generation with mocked WorkflowBuilder."""
        mock_workflow = Mock()
        mock_workflow_builder.return_value = mock_workflow

        agent = self.kaizen.create_agent("test_agent", self.valid_config)

        # Verify workflow builder was called correctly
        mock_workflow_builder.assert_called_once()
        mock_workflow.add_node.assert_called_once_with(
            "KaizenLLMAgentNode",
            "test_agent",
            {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 1000,
                "system_prompt": None
            }
        )
```

## Testing Strategy

### 3-Tier Testing Approach

**Tier 1: Unit Tests** (Fast, Isolated)
- Test individual classes and functions in isolation
- Mock external dependencies
- Focus on logic correctness and edge cases
- Target: <1 second execution time per test

**Tier 2: Integration Tests** (Real Infrastructure)
- Test integration with Core SDK components
- Use real Kailash infrastructure (NO MOCKING)
- Test workflow execution and node interaction
- Target: <10 seconds execution time per test

**Tier 3: End-to-End Tests** (Complete Workflows)
- Test complete user workflows and scenarios
- Real AI models and external services
- Performance and reliability validation
- Target: <60 seconds execution time per test

### Test Organization

```bash
tests/
├── unit/                   # Tier 1: Unit tests
│   ├── test_framework.py   # Framework core tests
│   ├── test_agents.py      # Agent system tests
│   ├── test_config.py      # Configuration tests
│   └── test_nodes.py       # Enhanced node tests
├── integration/            # Tier 2: Integration tests
│   ├── test_core_sdk_integration.py
│   ├── test_workflow_execution.py
│   └── test_node_compatibility.py
├── e2e/                    # Tier 3: End-to-end tests
│   ├── test_agent_workflows.py
│   ├── test_multi_agent_scenarios.py
│   └── test_performance_baselines.py
├── fixtures/               # Test data and fixtures
└── utils/                  # Test utilities and helpers
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific tier
pytest tests/unit/ -v          # Unit tests only
pytest tests/integration/ -v   # Integration tests only
pytest tests/e2e/ -v           # End-to-end tests only

# Run with coverage
pytest tests/ --cov=src/kaizen --cov-report=html --cov-report=term

# Run performance tests
pytest tests/performance/ -v --benchmark-only

# Run specific test file
pytest tests/unit/test_framework.py -v

# Run specific test method
pytest tests/unit/test_framework.py::TestKaizen::test_framework_initialization -v
```

## Documentation Standards

### Documentation Requirements

**All Public APIs Must Have**:
- **Docstrings**: Complete parameter and return value documentation
- **Type Hints**: Full type annotations for all parameters and returns
- **Examples**: Working code examples for complex functions
- **Error Documentation**: Documented exceptions and error conditions

**Documentation Example**:
```python
def create_agent(
    self,
    name: str,
    config: Dict[str, Any]
) -> Agent:
    """Create a new AI agent with specified configuration.

    Creates an AI agent that automatically generates a Core SDK workflow
    based on the provided configuration. The agent can be executed using
    any Kailash runtime.

    Args:
        name: Unique identifier for the agent. Must be non-empty and unique
            within this framework instance.
        config: Agent configuration dictionary containing model parameters.
            Required keys: 'model'. Optional keys: 'temperature', 'max_tokens',
            'system_prompt'.

    Returns:
        Configured Agent instance ready for workflow execution.

    Raises:
        ValueError: If name is empty or already exists.
        ConfigurationError: If config is invalid or missing required keys.
        KaizenError: If agent creation fails for any other reason.

    Example:
        ```python
        kaizen = Kaizen()
        agent = kaizen.create_agent("text_processor", {
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        })

        # Execute with Core SDK runtime
        from kailash.runtime.local import LocalRuntime
        runtime = LocalRuntime()
        results, run_id = runtime.execute(agent.workflow.build())
        ```

    Note:
        The generated workflow follows Core SDK patterns and is compatible
        with all Kailash runtimes. Agent configuration is validated at
        creation time to catch errors early.
    """
```

### Documentation Building

```bash
# Build documentation
sphinx-build -b html docs/ docs/_build/

# Live documentation server
sphinx-autobuild docs/ docs/_build/ --open-browser

# Check documentation links
linkchecker docs/_build/index.html

# Validate code examples
python scripts/validate_documentation_examples.py
```

## Contribution Process

### 1. Fork and Clone

```bash
# Fork repository on GitHub
# Clone your fork
git clone https://github.com/YOUR_USERNAME/kailash-kaizen.git
cd kailash-kaizen

# Add upstream remote
git remote add upstream https://github.com/terrene-foundation/kailash-py.git
```

### 2. Create Feature Branch

```bash
# Update main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name

# For bug fixes
git checkout -b fix/issue-description

# For documentation
git checkout -b docs/documentation-improvement
```

### 3. Development and Testing

```bash
# Make your changes
# ... development work ...

# Run comprehensive tests
pytest tests/ -v

# Run quality checks
black src/ tests/ examples/
isort src/ tests/ examples/ --profile black
flake8 src/ tests/ examples/
mypy src/kaizen/

# Update documentation if needed
# ... documentation updates ...
```

### 4. Commit and Push

```bash
# Stage changes
git add .

# Commit with clear message
git commit -m "feat: implement signature programming parser

- Add SignatureParser class for function signature analysis
- Implement type hint extraction and validation
- Add comprehensive unit tests with edge cases
- Update documentation with parser usage examples

Resolves #123"

# Push to your fork
git push origin feature/your-feature-name
```

### 5. Create Pull Request

**Pull Request Template**:
```markdown
## Description
Brief description of changes and motivation.

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Changes Made
- Specific change 1
- Specific change 2
- Specific change 3

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] End-to-end tests added/updated
- [ ] All tests pass locally

## Documentation
- [ ] Code documentation updated
- [ ] User guides updated (if applicable)
- [ ] API reference updated (if applicable)

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Tests added for new functionality
- [ ] Documentation updated
- [ ] No breaking changes (or breaking changes documented)

## Related Issues
Closes #123
```

### 6. Respond to Review

- Address reviewer feedback promptly
- Make requested changes in additional commits
- Update tests and documentation as needed
- Squash commits before merge if requested

## Common Contribution Areas

### High-Priority Features (Current Gaps)

**Signature Programming System** (P0):
- Signature parsing and validation
- Workflow compilation from signatures
- Type checking and contract enforcement
- Automatic optimization integration

**MCP First-Class Integration** (P0):
- MCP client implementation
- Server auto-discovery
- Capability-based configuration
- Tool integration framework

**Multi-Agent Coordination** (P0):
- Agent communication primitives
- Coordination patterns (debate, consensus, etc.)
- Team workflow creation
- Message routing and state management

**Transparency System** (P1):
- Workflow monitoring interfaces
- Audit trail implementation
- Performance metrics collection
- Real-time introspection capabilities

### Documentation Improvements

**User Guides**:
- Additional getting-started tutorials
- Integration pattern examples
- Best practices documentation
- Troubleshooting guides

**API Documentation**:
- Complete API reference
- Configuration option documentation
- Error handling guides
- Migration guides

### Testing and Quality

**Test Coverage**:
- Additional unit tests for edge cases
- Integration tests for Core SDK compatibility
- Performance benchmarks and baselines
- Security testing and validation

**Quality Improvements**:
- Performance optimization
- Memory usage optimization
- Error message improvements
- Code quality enhancements

## Getting Help

### Communication Channels

**GitHub Issues**:
- Bug reports and feature requests
- Technical discussions
- Design proposals and RFCs

**Development Support**:
- Code review and feedback
- Architecture guidance
- Implementation assistance

### Resources

**Documentation**:
- [Architecture Guide](architecture.md) - Technical architecture details
- [Design Patterns](patterns.md) - Implementation patterns and best practices
- [API Reference](../reference/api.md) - Complete API documentation

**Codebase Navigation**:
- [Gap Analysis](../tracking/KAIZEN_GAPS_ANALYSIS.md) - Current implementation status
- [Implementation Assessment](../tracking/COMPREHENSIVE_IMPLEMENTATION_ASSESSMENT.md) - Detailed feature analysis
- [Examples Directory](../../examples/) - Working examples and patterns

---

**🎯 Ready to Contribute**: You now have all the information needed to contribute effectively to the Kaizen Framework. Thank you for helping build the future of enterprise AI development!
