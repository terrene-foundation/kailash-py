# MCP Documentation

This directory contains comprehensive documentation for the Model Context Protocol (MCP) implementation in Kailash SDK.

## Documentation Structure

### Core Documentation
- **[index.rst](index.rst)** - Main entry point and overview
- **[overview.rst](overview.rst)** - Detailed MCP concepts and architecture
- **[quickstart.rst](quickstart.rst)** - 5-minute quick start guide
- **[server_development.rst](server_development.rst)** - Building MCP servers

### Comprehensive Guides
- **[architecture.md](architecture.md)** - MCP architecture and design decisions
- **[deployment.md](deployment.md)** - Production deployment guide
- **[monitoring.md](monitoring.md)** - Monitoring and observability
- **[security.md](security.md)** - Security best practices
- **[troubleshooting.md](troubleshooting.md)** - Common issues and solutions
- **[api-reference.md](api-reference.md)** - Complete API reference
- **[examples.md](examples.md)** - Code examples and recipes

## Quick Links

### For Developers
- [Quick Start](quickstart.rst) - Get started in 5 minutes
- [API Reference](api-reference.md) - Complete API documentation
- [Examples](examples.md) - Working code examples
- [Troubleshooting](troubleshooting.md) - Solve common problems

### For Production
- [Architecture](architecture.md) - System design and patterns
- [Deployment](deployment.md) - Deploy to production
- [Security](security.md) - Security best practices
- [Monitoring](monitoring.md) - Observability and metrics

### For Migration
- [MCP Migration Guide](/sdk-users/6-reference/migration-guides/specialized/mcp-comprehensive-migration.md) - Comprehensive MCP migration
- [All Migration Guides](/sdk-users/6-reference/migration-guides/) - Version, architectural, and specialized migrations
- [Examples](examples.md#migration-examples) - Migration patterns

## Documentation Overview

### Architecture Guide
Covers the core architectural principles, component design, integration patterns, and scalability considerations for MCP implementations.

### Deployment Guide
Comprehensive production deployment instructions including container deployment, Kubernetes orchestration, cloud deployments (AWS, GCP, Azure), and operational procedures.

### Monitoring Guide
Details metrics collection, logging strategies, distributed tracing, health checks, alerting, dashboards, and performance monitoring for MCP systems.

### Security Guide
Security best practices covering authentication, authorization, network security, data protection, secret management, input validation, and compliance (GDPR, SOC 2).

### Troubleshooting Guide
Common issues and solutions, debugging techniques, log analysis, performance optimization, and recovery procedures for MCP deployments.

### API Reference
Complete API documentation for server endpoints, client methods, transport protocols, data models, authentication, and error handling.

### Examples
Practical code examples including basic usage, authentication, tool implementations, advanced patterns, integrations, and production recipes.


## Building the Documentation

To build these docs as part of the main Kailash documentation:

```bash
cd docs/
make html
```

The MCP documentation will be available under the "MCP" section.

## Related Resources

- [MCP Patterns Guide](/sdk-users/5-enterprise/patterns/12-mcp-patterns.md)
- [MCP Development Guide](/sdk-users/3-development/22-mcp-development-guide.md)
- [MCP Cheatsheet](/sdk-users/2-core-concepts/cheatsheet/025-mcp-integration.md)
- [Example MCP Application](/apps/mcp_tools_server/)

## Test Coverage

MCP implementation has been thoroughly tested:
- **Unit Tests**: 391 tests covering all functionality
- **Integration Tests**: 14 real server tests
- **E2E Tests**: Complete workflow scenarios
- **100% pass rate** across all test suites

See [MCP Test Report](/MCP_TEST_REPORT.md) for details.

## Getting Help

1. Start with the [Troubleshooting Guide](troubleshooting.md)
2. Check the [Examples](examples.md) for working code
3. Review the [API Reference](api-reference.md) for detailed specifications
4. See [Security Best Practices](security.md) for security concerns
5. Consult the [Architecture Guide](architecture.md) for design questions

## Contributing

When contributing to MCP documentation:
1. Follow the existing documentation style
2. Include working code examples
3. Test all code samples
4. Update the relevant sections
5. Add cross-references where appropriate
