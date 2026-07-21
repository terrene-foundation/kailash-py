---
name: dataflow-validation-layers
description: "4-layer validation system architecture for DataFlow: Models → Parameters → Connections → Workflows. Use when understanding DataFlow's validation pipeline, implementing custom validators, or debugging validation issues."
---

# DataFlow Validation Layers - Architecture Guide

Complete reference for DataFlow's 4-layer validation system that validates models, parameters, connections, and workflows before execution.

> **Skill Metadata**
> Category: `dataflow/architecture`
> Priority: `MEDIUM`

## Quick Reference

- **Layer 1 (Model)**: Validates model schema and field definitions
- **Layer 2 (Parameter)**: Validates node parameters before workflow execution
- **Layer 3 (Connection)**: Validates connections between workflow nodes
- **Layer 4 (Workflow)**: Validates complete workflow structure
- **Execution Order**: Models → Parameters → Connections → Workflows (bottom-up)
- **Performance**: Build-time validation only (<5ms overhead)

## Validation Overhead

| Layer                | Timing                | Overhead | When                      |
| -------------------- | --------------------- | -------- | ------------------------- |
| Layer 1 (Model)      | Model decoration      | ~0.5ms   | One-time per model        |
| Layer 2 (Parameter)  | add_node() call       | ~0.5ms   | Per node added            |
| Layer 3 (Connection) | add_connection() call | ~0.5ms   | Per connection added      |
| Layer 4 (Workflow)   | workflow.build() call | ~2ms     | One-time per workflow     |
| **Total**            | **Build time**        | **~4ms** | **Zero runtime overhead** |
