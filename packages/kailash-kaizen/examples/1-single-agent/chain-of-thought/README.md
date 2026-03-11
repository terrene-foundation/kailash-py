# Chain-of-Thought Reasoning Agent - Kaizen Framework

## Overview

This example demonstrates a working Chain-of-Thought (CoT) reasoning implementation using the Kaizen framework's signature-based programming capabilities. The agent breaks down complex problems into step-by-step reasoning chains, providing transparent and verifiable problem-solving processes with enterprise-grade features.

## 🎯 Objectives Demonstrated

- **Kaizen signature-based programming** for structured reasoning
- **Step-by-step thinking patterns** with explicit reasoning chains
- **Performance targets** with monitoring and validation
- **Enterprise features** including audit trails and compliance
- **Lean, optimized code** implementation

## 🏗️ Implementation Architecture

### ChainOfThoughtSignature
Structured signature defining inputs and outputs for CoT reasoning:

```python
Inputs:
- problem: Complex problem requiring step-by-step reasoning
- context: Additional context or constraints (optional)

Outputs:
- step1-step5: Individual reasoning steps
- final_answer: Complete, verified solution
- confidence: Confidence score (0.0-1.0)
```

### ChainOfThoughtAgent
Enterprise-ready agent with:
- Kaizen framework integration
- Performance monitoring
- Audit trail generation
- Error handling and recovery
- Mathematical reasoning specialization

## 🚀 Quick Start

### Run the Demo
```bash
cd examples/1-single-agent/chain-of-thought
python chain_of_thought_agent.py
```

### Expected Output
```
Chain-of-Thought Reasoning Agent - Kaizen Framework Demo
============================================================

Problem: If a train travels 60 mph for 3 hours, then speeds up to 80 mph for 2 more hours, what total distance did it travel?
------------------------------------------------------------

Reasoning Steps:
  Step 1: Problem Understanding: I need to calculate the total distance traveled by a train with two different speed segments.
  Step 2: Data Identification: Segment 1: 60 mph for 3 hours. Segment 2: 80 mph for 2 hours. Formula: Distance = Speed × Time
  Step 3: Systematic Calculation: Segment 1 distance = 60 mph × 3 hours = 180 miles. Segment 2 distance = 80 mph × 2 hours = 160 miles.
  Step 4: Solution Verification: Total distance = 180 miles + 160 miles = 340 miles. Check: (60×3) + (80×2) = 180 + 160 = 340 ✓
  Step 5: Final Answer Formulation: The train traveled a total distance of 340 miles during the entire journey.

Final Answer: The train traveled a total distance of 340 miles.
Confidence: 0.98
Execution Time: 1237.6ms

Performance Metrics:
  Framework Init: 0.0ms (✓ <100ms)
  Agent Creation: 0.1ms (✓ <200ms)
  Average Execution: 1237.6ms (✗ <1000ms)

Enterprise Features:
  Audit Trail Entries: 2
  Latest Action: create_agent
  Success: True
```

## 🧪 Run Tests

### All Tests
```bash
python -m pytest test_chain_of_thought.py -v
```

### Specific Test Categories
```bash
# Signature functionality
python -m pytest test_chain_of_thought.py::TestChainOfThoughtSignature -v

# Agent performance
python -m pytest test_chain_of_thought.py::TestChainOfThoughtAgent -v

# Enterprise features
python -m pytest test_chain_of_thought.py::TestEnterpriseFeatures -v

# Performance validation
python -m pytest test_chain_of_thought.py::TestPerformanceValidation -v
```

## 📊 Performance Results

### Targets vs Actual Performance

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Framework Initialization | <100ms | ~0-1ms | ✅ **Met** |
| Agent Creation | <200ms | ~0-1ms | ✅ **Met** |
| Reasoning Execution | <1000ms | ~1075ms | ⚠️ **Close** |

**Note**: The reasoning execution time is slightly above target due to initial Core SDK loading overhead. Subsequent executions are typically faster.

### Performance Optimization Features
- Lazy loading of framework components
- Optimized signature compilation
- Efficient workflow execution
- Minimal memory overhead

## 🏢 Enterprise Features

### Audit Trail
Complete audit trail for enterprise compliance:
- Action tracking
- Execution timestamps
- Success/failure status
- Confidence scores
- Problem metadata

### Monitoring & Metrics
Real-time performance monitoring:
- Framework initialization time
- Agent creation time
- Average execution time
- Success rates
- Error tracking

### Compliance Features
- Enterprise-grade configuration
- Security level controls
- Multi-tenant support (configurable)
- GDPR/SOX compliance reporting

## 🔧 Configuration

### Agent Configuration (`config.yaml`)
```yaml
agent:
  model: "gpt-4"
  temperature: 0.1
  max_tokens: 1500
  timeout: 45

reasoning:
  reasoning_steps: 5
  confidence_threshold: 0.7
  enable_verification: true

enterprise:
  audit_trail_enabled: true
  monitoring_enabled: true
  compliance_mode: "enterprise"
```

### Programmatic Configuration
```python
config = CoTConfig(
    model="gpt-4",
    temperature=0.1,
    reasoning_steps=5,
    enable_verification=True
)

agent = ChainOfThoughtAgent(config)
```

## 🧮 Mathematical Reasoning Example

### Train Speed/Distance Problem
**Problem**: "If a train travels 60 mph for 3 hours, then speeds up to 80 mph for 2 more hours, what total distance did it travel?"

**Step-by-Step Solution**:
1. **Problem Understanding**: Calculate total distance with two speed segments
2. **Data Identification**: Segment 1: 60 mph × 3 hours, Segment 2: 80 mph × 2 hours
3. **Systematic Calculation**: 180 miles + 160 miles
4. **Solution Verification**: 340 miles total (verified)
5. **Final Answer**: 340 miles

**Confidence**: 0.98 (98% confidence)

## 🔍 Code Structure

```
chain-of-thought/
├── chain_of_thought_agent.py      # Main implementation
├── test_chain_of_thought.py       # Comprehensive tests
├── config.yaml                    # Configuration file
├── README.md                      # This documentation
```

### Key Classes

#### `ChainOfThoughtSignature`
- Defines structured input/output for CoT reasoning
- Uses DSPy-inspired `Signature`, `InputField`, and `OutputField`
- Supports enterprise validation

#### `ChainOfThoughtAgent`
- Main agent implementation
- Kaizen framework integration
- Performance monitoring
- Enterprise feature support

#### `CoTConfig`
- Configuration dataclass
- Performance targets
- Enterprise settings

## 🔧 Advanced Usage

### Custom Problem Types
```python
# Mathematical problems
result = agent.solve_problem("Calculate compound interest for $1000 at 5% for 3 years")

# Logical reasoning
result = agent.solve_problem("What factors should I consider when choosing a programming language?")

# Analytical problems
result = agent.solve_problem("Compare renewable vs non-renewable energy sources")
```

### Enterprise Integration
```python
# Enable full enterprise features
framework_config = kaizen.KaizenConfig(
    signature_programming_enabled=True,
    audit_trail_enabled=True,
    compliance_mode="enterprise",
    security_level="high"
)

# Get compliance report
compliance_report = agent.kaizen_framework.generate_compliance_report()
```

### Performance Monitoring
```python
# Get detailed metrics
metrics = agent.get_performance_metrics()
print(f"Success rate: {metrics['success_rate']:.1%}")
print(f"Average execution: {metrics['average_execution_time']:.1f}ms")

# Get audit trail
audit_trail = agent.get_audit_trail()
print(f"Total audit entries: {len(audit_trail)}")
```

## 🎓 Key Learning Outcomes

1. **Signature-Based Programming**: How to define structured AI workflows using Kaizen signatures
2. **Chain-of-Thought Implementation**: Step-by-step reasoning with transparent logic
3. **Performance Optimization**: Meeting enterprise performance targets
4. **Enterprise Features**: Audit trails, monitoring, and compliance
5. **Testing Strategy**: Comprehensive testing for functionality and performance

## 🚀 Next Steps

### Extend the Example
1. **Add more reasoning patterns** (analogical, causal, counterfactual)
2. **Implement multi-modal reasoning** (text + images/data)
3. **Add collaborative reasoning** (multi-agent CoT)
4. **Integrate with external tools** (calculators, databases)

### Production Deployment
1. **Scale with Nexus** for API/CLI/MCP deployment
2. **Add DataFlow integration** for persistent reasoning chains
3. **Implement advanced monitoring** with custom dashboards
4. **Configure enterprise security** with role-based access

## 📚 References

- [Kaizen Framework Documentation](../../../docs/)
- [Core SDK Workflow Patterns](../../../../../src/kailash/workflow/)
- [Signature Programming Guide](../../README.md)
- [Enterprise Features Overview](../../../docs/KAIZEN_INTEGRATION_STRATEGY.md)

## 🤝 Contributing

This example demonstrates best practices for Kaizen-based AI applications. When extending or modifying:

1. Maintain performance targets
2. Include comprehensive tests
3. Follow enterprise patterns
4. Document new features
5. Validate compliance requirements

---

**Built with Kaizen Framework** - Signature-based AI programming with enterprise capabilities
