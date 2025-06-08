# Utility Nodes

**Modules**: Various utility modules
**Last Updated**: 2025-01-06

This document covers utility nodes including visualization, security, and tracking features.

## Table of Contents
- [Visualization Nodes](#visualization-nodes)
- [Security Nodes](#security-nodes)

## Visualization Nodes

### WorkflowVisualizerNode
- **Module**: `kailash.nodes.visualization`
- **Purpose**: Generate workflow visualizations
- **Output Formats**: PNG, SVG, Mermaid

### RealTimeDashboardNode
- **Module**: `kailash.nodes.visualization.dashboard`
- **Purpose**: Create real-time monitoring dashboards
- **Features**: WebSocket streaming, metric collection, Chart.js integration

### PerformanceReporterNode
- **Module**: `kailash.nodes.visualization.reports`
- **Purpose**: Generate comprehensive performance reports
- **Formats**: HTML, Markdown, JSON

## Security Nodes

### SecurityMixin
- **Module**: `kailash.nodes.mixins`
- **Purpose**: Add security features to any node
- **Features**:
  - Input validation and sanitization
  - Path traversal prevention
  - Command injection protection
  - Audit logging

### SecureFileNode
- **Module**: `kailash.nodes.security`
- **Purpose**: Secure file operations with validation
- **Features**: Path validation, size limits, extension checks

## See Also
- [Base Classes](01-base-nodes.md) - Core node abstractions
- [Security API](../api/09-security-access.yaml) - Security configuration
- [Visualization API](../api/10-visualization.yaml) - Visualization tools
