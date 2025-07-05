# MCP Patterns Comprehensive Test Suite

This directory contains comprehensive tests for all 10 core MCP (Model Context Protocol) patterns from the Kailash SDK patterns guide.

## Overview

The test suite validates that all MCP patterns work correctly both in isolation and when combined in real-world scenarios. It provides comprehensive coverage of:

- **Basic Patterns (1-5)**: Server setup, authentication, caching, service discovery, load balancing
- **Advanced Patterns (6-10)**: Agent integration, workflows, error handling, streaming, multi-tenancy
- **Integration Scenarios**: Real-world workflows combining multiple patterns
- **Production Validation**: Performance, reliability, and compatibility testing

## Test Files

### Core Test Suites

1. **`test_mcp_patterns_comprehensive.py`** - Tests for basic patterns 1-5:
   - Basic Server Pattern
   - Authenticated Server Pattern
   - Cached Tool Pattern
   - Service Discovery Pattern
   - Load Balanced Client Pattern

2. **`test_mcp_patterns_advanced.py`** - Tests for advanced patterns 6-10:
   - Agent Integration Pattern
   - Workflow Integration Pattern
   - Error Handling Pattern
   - Streaming Response Pattern
   - Multi-Tenant Pattern

3. **`test_mcp_patterns_integration.py`** - Integration and real-world scenarios:
   - End-to-end multi-pattern workflows
   - Production simulation
   - Cross-pattern compatibility validation

### Test Runner

4. **`run_mcp_pattern_tests.py`** - Comprehensive test runner:
   - Executes all test suites
   - Generates detailed reports
   - Provides performance metrics
   - Creates compatibility matrix

## The 10 MCP Patterns Tested

### 1. Basic Server Pattern
**Purpose**: Basic MCP server creation and tool registration
**Tests**: Server startup, tool registration, basic tool execution
**Validation**: Server lifecycle, tool discovery, execution success

### 2. Authenticated Server Pattern
**Purpose**: Secure MCP servers with various authentication methods
**Tests**: Bearer token, API key, JWT, and custom authentication
**Validation**: Auth enforcement, token validation, secure tool access

### 3. Cached Tool Pattern
**Purpose**: Performance optimization through caching
**Tests**: Cache hits/misses, TTL behavior, cache invalidation
**Validation**: Response caching, cache effectiveness, TTL expiration

### 4. Service Discovery Pattern
**Purpose**: Dynamic service registration and discovery
**Tests**: Service registration, discovery, health checks
**Validation**: Service registry, health monitoring, filtered discovery

### 5. Load Balanced Client Pattern
**Purpose**: High availability through load balancing
**Tests**: Round-robin, least connections, failover strategies
**Validation**: Request distribution, backend health, failover behavior

### 6. Agent Integration Pattern
**Purpose**: LLM agents with MCP tool access
**Tests**: Tool discovery, agent-tool interaction, multi-server support
**Validation**: Agent tool usage, dynamic tool calling, context preservation

### 7. Workflow Integration Pattern
**Purpose**: MCP integration within Kailash workflows
**Tests**: Resource access, tool usage in workflows, dynamic MCP calls
**Validation**: Workflow execution, MCP resource handling, data flow

### 8. Error Handling Pattern
**Purpose**: Robust error handling and recovery
**Tests**: Error propagation, retry logic, circuit breakers, graceful degradation
**Validation**: Error handling, resilience patterns, recovery mechanisms

### 9. Streaming Response Pattern
**Purpose**: Streaming data for large operations
**Tests**: Streaming tools, buffered responses, error handling in streams
**Validation**: Stream processing, buffering, streaming reliability

### 10. Multi-Tenant Pattern
**Purpose**: Tenant isolation and resource management
**Tests**: Tenant registration, isolation, resource separation, usage tracking
**Validation**: Tenant security, resource isolation, usage monitoring

## Running the Tests

### Quick Start

```bash
# Run all tests with default settings
python run_mcp_pattern_tests.py

# Run with verbose output
python run_mcp_pattern_tests.py --verbose

# Save detailed report to custom file
python run_mcp_pattern_tests.py --report-file my_report.json
```

### Individual Test Suites

```bash
# Run basic patterns only
python -m pytest test_mcp_patterns_comprehensive.py -v

# Run advanced patterns only
python -m pytest test_mcp_patterns_advanced.py -v

# Run integration tests only
python -m pytest test_mcp_patterns_integration.py -v
```

### With Coverage

```bash
# Run with coverage analysis
python -m pytest test_mcp_patterns_*.py --cov=kailash --cov-report=html
```

## Test Output

### Console Output
The test runner provides real-time progress and a comprehensive summary:

```
=== MCP PATTERNS COMPREHENSIVE TEST RESULTS ===
Overall Results:
  Total Patterns Tested: 10
  Total Passed: 10
  Total Failed: 0
  Success Rate: 100.0%
  All Patterns Working: True

Pattern Details:
   1. Basic Server Pattern: ✅ PASS
   2. Authenticated Server Pattern: ✅ PASS
   3. Cached Tool Pattern: ✅ PASS
   4. Service Discovery Pattern: ✅ PASS
   5. Load Balanced Client Pattern: ✅ PASS
   6. Agent Integration Pattern: ✅ PASS
   7. Workflow Integration Pattern: ✅ PASS
   8. Error Handling Pattern: ✅ PASS
   9. Streaming Response Pattern: ✅ PASS
  10. Multi-Tenant Pattern: ✅ PASS
```

### JSON Report
Detailed JSON report includes:

```json
{
  "test_execution": {
    "start_time": "2024-01-15T10:30:00Z",
    "end_time": "2024-01-15T10:35:30Z",
    "total_duration_seconds": 330.5
  },
  "overall_summary": {
    "total_patterns_tested": 10,
    "total_passed": 10,
    "total_failed": 0,
    "overall_success_rate": "100.0%",
    "all_patterns_working": true
  },
  "pattern_coverage": {
    "pattern_1": {
      "name": "Basic Server Pattern",
      "tested": true,
      "passed": true,
      "test_details": {...}
    },
    ...
  },
  "compatibility_matrix": {
    "pattern_interactions": {
      "auth_caching": true,
      "multitenant_streaming": true,
      "service_discovery_load_balancing": true,
      "error_handling_resilience": true,
      "agent_workflow_mcp": true,
      "all_patterns_together": true
    },
    "compatibility_score": {
      "overall": "100.0%"
    }
  },
  "performance_metrics": {
    "execution_times": {...},
    "performance_summary": {
      "total_execution_time_seconds": 330.5,
      "average_time_per_test_seconds": 2.1,
      "performance_rating": "Good"
    }
  },
  "recommendations": [
    "✅ All MCP patterns are working correctly!",
    "🚀 Consider adding more real-world integration scenarios"
  ]
}
```

## Test Architecture

### Mock Infrastructure
The tests use comprehensive mock infrastructure to simulate real MCP environments:

- **MockMCPServer**: Simulates MCP servers with tools and resources
- **MockMCPClient**: Simulates MCP clients with connection management
- **Service Registries**: Mock service discovery systems
- **Load Balancers**: Mock load balancing implementations
- **Multi-tenant Servers**: Mock tenant isolation and management

### Test Patterns
Each pattern test follows a consistent structure:

1. **Setup**: Create mock infrastructure
2. **Configuration**: Configure pattern-specific settings
3. **Execution**: Run pattern operations
4. **Validation**: Assert expected behavior
5. **Cleanup**: Clean up resources

### Integration Testing
Integration tests validate:

- **Pattern Combinations**: Multiple patterns working together
- **Real-world Scenarios**: End-to-end workflows
- **Production Simulation**: Load testing and failover
- **Cross-pattern Compatibility**: Interaction validation

## Extending the Tests

### Adding New Patterns
To add tests for new MCP patterns:

1. Add pattern test method to appropriate test class
2. Follow the established test structure
3. Include mock infrastructure for the pattern
4. Add pattern to the test runner
5. Update documentation

### Adding Integration Scenarios
To add new integration scenarios:

1. Create scenario method in `MCPPatternsIntegrationTest`
2. Combine multiple patterns in realistic workflow
3. Validate end-to-end behavior
4. Include performance and reliability checks

### Custom Mock Components
To create custom mock components:

1. Inherit from base mock classes
2. Implement required interfaces
3. Add pattern-specific behavior
4. Include error simulation capabilities

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure proper Python path
export PYTHONPATH="${PYTHONPATH}:/path/to/kailash_python_sdk/src"
```

**Test Failures**:
```bash
# Run with verbose output for debugging
python run_mcp_pattern_tests.py --verbose
```

**Performance Issues**:
```bash
# Run individual test suites to isolate issues
python -m pytest test_mcp_patterns_comprehensive.py::MCPPatternTests::test_basic_server_pattern -v
```

### Test Environment
- Python 3.8+
- asyncio support
- pytest for test execution
- Mock components for isolation

## Contributing

When contributing to the MCP patterns test suite:

1. **Follow Test Patterns**: Use established mock infrastructure
2. **Include Documentation**: Document new patterns and scenarios
3. **Validate Coverage**: Ensure comprehensive test coverage
4. **Performance Aware**: Consider test execution time
5. **Real-world Focus**: Test realistic scenarios

## Related Documentation

- [MCP Patterns Guide](../../sdk-users/patterns/12-mcp-patterns.md) - Complete pattern documentation
- [Kailash SDK Documentation](../../sdk-users/) - SDK usage guides
- [Test Documentation](../README.md) - General testing guidelines

## Success Criteria

The test suite validates that:

✅ All 10 MCP patterns work correctly in isolation
✅ Patterns can be combined without conflicts
✅ Real-world scenarios execute successfully
✅ Error handling and recovery work properly
✅ Performance meets acceptable standards
✅ Multi-tenant isolation is enforced
✅ Authentication and security work correctly
✅ Streaming and caching provide benefits
✅ Service discovery and load balancing function
✅ Agent and workflow integration is seamless

This comprehensive test suite ensures that the Kailash SDK's MCP implementation is production-ready and reliable for real-world use cases.
