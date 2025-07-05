# MCP Deployment Testing Framework

This directory contains comprehensive testing tools for validating MCP (Model Context Protocol) deployment configurations.

## Overview

The deployment testing framework ensures that all MCP applications can be successfully deployed using Docker and Docker Compose with proper security, performance, and operational practices.

## Test Components

### 1. Configuration Validation (`test_deployment_configs.py`)

**Purpose**: Validates deployment configurations without requiring Docker builds

**Features**:
- Dockerfile syntax and best practices validation
- Docker Compose configuration validation
- Environment variable security checks
- Resource limits and health check validation
- Required files verification

**Usage**:
```bash
# Test all deployments
python tests/deployment/test_deployment_configs.py

# Test specific deployment
python tests/deployment/test_deployment_configs.py --test mcp-basic
```

### 2. CI/CD Integration (`ci_deployment_test.py`)

**Purpose**: Lightweight tests for continuous integration environments

**Features**:
- Docker Compose syntax validation
- Dockerfile syntax validation
- Required files verification
- CI-friendly reporting

**Usage**:
```bash
# Run CI tests
python tests/deployment/ci_deployment_test.py

# Run in CI environment (sets CI=true)
CI=true python tests/deployment/ci_deployment_test.py
```

### 3. Full Deployment Validation (`test_deployment_validation.py`)

**Purpose**: Comprehensive testing including Docker builds

**Features**:
- Full Docker build testing
- Docker Compose validation
- Environment variable handling
- Service dependency testing
- Performance and security validation

**Usage**:
```bash
# Run all tests including Docker builds
python tests/deployment/test_deployment_validation.py

# Skip Docker builds (faster)
python tests/deployment/test_deployment_validation.py --no-build

# Test specific deployment
python tests/deployment/test_deployment_validation.py --test mcp-basic
```

## Tested Applications

The framework validates the following MCP applications:

1. **mcp-basic** (`apps/mcp/`)
   - Basic MCP server with PostgreSQL and Redis
   - Nginx reverse proxy
   - Prometheus and Grafana monitoring

2. **mcp-ai-assistant** (`apps/mcp_ai_assistant/`)
   - AI assistant server with Redis caching
   - Nginx load balancer

3. **mcp-tools-server** (`apps/mcp_tools_server/`)
   - Production MCP tools server
   - High availability setup with load balancing
   - Optional monitoring stack

4. **mcp-data-pipeline** (`apps/mcp_data_pipeline/`)
   - Data processing pipeline
   - Kafka and Zookeeper integration
   - PostgreSQL storage

5. **mcp-enterprise-gateway** (`apps/mcp_enterprise_gateway/`)
   - Enterprise-grade gateway
   - Authentication and authorization
   - Audit logging and monitoring

6. **mcp-integration-patterns** (`apps/mcp_integration_patterns/production/docker_deployment/`)
   - Production integration patterns
   - Multi-server architecture
   - Service discovery with Consul

## Validation Criteria

### Security
- ✅ No hardcoded secrets in environment variables
- ✅ Non-root user execution in containers
- ✅ Proper secret management with environment variables
- ✅ SSL/TLS configuration support

### Performance
- ✅ Resource limits defined for all services
- ✅ Health checks configured
- ✅ Restart policies set
- ✅ Optimized Docker images (multi-stage builds)

### Operational
- ✅ Proper logging configuration
- ✅ Monitoring integration
- ✅ Service dependencies handled correctly
- ✅ Volume persistence configured

### Development
- ✅ All required files present
- ✅ Valid Dockerfile syntax
- ✅ Valid Docker Compose syntax
- ✅ Environment variable documentation

## Configuration Fixes Applied

### 1. Basic MCP Application (`apps/mcp/docker-compose.yml`)

**Fixed Issues**:
- Added health checks for all services
- Added resource limits
- Changed hardcoded secrets to environment variables
- Added proper health check endpoints

**Environment Variables**:
```bash
# Required for production
POSTGRES_PASSWORD=your-secure-password
GRAFANA_PASSWORD=your-secure-password
MCP_JWT_SECRET=your-jwt-secret
```

### 2. Template Configuration (`tests/deployment/docker-compose-fixes.yml`)

**Provides**:
- Best practices template for Docker Compose
- Proper resource limits
- Security configurations
- Health check examples
- Environment variable patterns

## Running Tests

### Local Development
```bash
# Quick configuration validation
python tests/deployment/test_deployment_configs.py

# Full validation with Docker builds (requires Docker)
python tests/deployment/test_deployment_validation.py
```

### CI/CD Pipeline
```bash
# Add to your CI pipeline
python tests/deployment/ci_deployment_test.py
```

### GitHub Actions Example
```yaml
name: Deployment Validation
on: [push, pull_request]

jobs:
  deployment-tests:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install pyyaml docker
    - name: Run deployment tests
      run: |
        python tests/deployment/ci_deployment_test.py
    - name: Upload test results
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: deployment-test-results
        path: deployment_ci_report.txt
```

## Test Reports

The framework generates detailed reports:

1. **Configuration Report** (`deployment_config_validation_report.md`)
   - Detailed validation results
   - Warnings and recommendations
   - Fix suggestions

2. **CI Report** (`deployment_ci_report.txt`)
   - Simple pass/fail status
   - Critical issues only
   - CI-friendly format

## Best Practices

### Docker Compose
1. Always include health checks
2. Set resource limits
3. Use environment variables for secrets
4. Include restart policies
5. Use proper network isolation

### Dockerfiles
1. Multi-stage builds for optimization
2. Non-root user execution
3. Health check instructions
4. Proper cache cleanup
5. Security scanning

### Environment Variables
1. Use `.env.example` files for documentation
2. Never commit actual secrets
3. Use `${VAR:-default}` syntax for defaults
4. Validate required variables at startup

### Monitoring
1. Include Prometheus metrics
2. Set up health check endpoints
3. Configure proper logging
4. Use structured logging formats

## Troubleshooting

### Common Issues

1. **Missing Docker Compose file**
   ```
   Error: Docker Compose file not found
   Solution: Ensure docker-compose.yml exists in the app directory
   ```

2. **Hardcoded secrets**
   ```
   Warning: Hardcoded secret detected
   Solution: Use environment variables instead
   ```

3. **Missing health checks**
   ```
   Warning: Service missing healthcheck
   Solution: Add healthcheck configuration to docker-compose.yml
   ```

4. **Missing resource limits**
   ```
   Warning: Service missing resource limits
   Solution: Add deploy.resources section to docker-compose.yml
   ```

### Docker Build Issues

1. **Permission denied**
   ```
   Error: Docker daemon permission denied
   Solution: Add user to docker group or use sudo
   ```

2. **Build timeout**
   ```
   Error: Docker build timeout
   Solution: Increase timeout or optimize Dockerfile
   ```

3. **Missing base image**
   ```
   Error: Base image not found
   Solution: Check FROM instruction and image availability
   ```

## Contributing

When adding new MCP applications:

1. Create proper Dockerfile with multi-stage build
2. Add docker-compose.yml with all services
3. Include requirements.txt and other dependencies
4. Add environment variable documentation
5. Update the test framework to include your app
6. Run validation tests before submitting

## References

- [Docker Best Practices](https://docs.docker.com/develop/best-practices/)
- [Docker Compose Best Practices](https://docs.docker.com/compose/production/)
- [Container Security](https://kubernetes.io/docs/concepts/security/)
- [Health Check Patterns](https://docs.docker.com/engine/reference/builder/#healthcheck)
