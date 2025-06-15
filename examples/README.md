# Kailash SDK Examples - Development & Feature Validation

This directory contains **SDK development tools and feature validation examples**. These are for SDK contributors working on core functionality.

> **Looking for production workflows?** Check out [sdk-users/workflows/](../sdk-users/workflows/) for business-focused, production-ready solutions.

## 📁 Purpose

**SDK Development Only**: Feature testing, validation utilities, and development infrastructure.

**Business Workflows**: All moved to [sdk-users/workflows/](../sdk-users/workflows/)

## Structure

### feature_examples/
SDK feature validation organized by component:
- **nodes/** - Individual node testing and validation
- **workflows/** - Workflow construction and execution testing
- **runtime/** - Runtime behavior and performance testing
- **integrations/** - SDK integration testing with external systems
- **ai/** - AI component feature testing
- **security/** - Security feature validation
- **mcp/** - MCP protocol testing
- **middleware/** - Middleware feature testing

### utils/
Development utilities and shared tools:
- **data_paths.py** - Path management for testing
- **maintenance.py** - SDK maintenance utilities

### test-harness/
Testing infrastructure and frameworks for SDK development.

## For SDK Contributors

These examples help validate individual SDK features and components during development. They are **not** intended as user-facing solutions.

**For Production Use**: See [sdk-users/workflows/](../sdk-users/workflows/) for complete business solutions.
