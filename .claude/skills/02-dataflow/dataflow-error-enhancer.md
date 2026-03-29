---
name: dataflow-error-enhancer
description: "ErrorEnhancer system for actionable DataFlow error messages with DF-XXX codes, root cause analysis, and solutions. Use when debugging DataFlow errors, missing parameters, type mismatches, validation errors, or need error context and fixes."
---

# DataFlow ErrorEnhancer - Actionable Error Messages

Automatic error enhancement with DF-XXX codes, context, root causes, and actionable solutions for DataFlow applications.

> **Skill Metadata**
> Category: `dataflow/dx`
> Priority: `CRITICAL`
> Related Skills: [`dataflow-inspector`](#), [`dataflow-validation`](#), [`top-10-errors`](#)
> Related Subagents: `dataflow-specialist` (complex errors), `testing-specialist` (test errors)

## Quick Reference

- **60+ Error Codes**: DF-1XX (parameters) through DF-8XX (runtime)
- **Automatic Integration**: Built into DataFlow engine
- **Rich Context**: Node, parameters, workflow state, stack traces
- **Actionable Solutions**: Code templates with variable substitution

## CRITICAL: ErrorEnhancer is Automatic

ErrorEnhancer is **automatically integrated** into DataFlow. You do NOT need to import or configure it.

## Error Code Categories

| Range  | Category             | Common Cause                                 |
| ------ | -------------------- | -------------------------------------------- |
| DF-1XX | Parameter Errors     | Missing data, type mismatch, reserved fields |
| DF-2XX | Connection Errors    | Invalid connections, circular deps           |
| DF-3XX | Migration Errors     | Schema conflicts, constraints                |
| DF-4XX | Configuration Errors | Invalid URLs, auth failures                  |
| DF-5XX | Runtime Errors       | Sync/async conflicts, timeouts               |
| DF-6XX | Model Errors         | Invalid definitions, duplicates              |
| DF-7XX | Node Errors          | Generation failures, wrong params            |
| DF-8XX | Workflow Errors      | Validation failures, timeouts                |

## Best Practices

1. **Read Error Codes First** - DF-XXX codes immediately identify the category
2. **Use Suggested Solutions** - ErrorEnhancer provides code templates
3. **Combine with Inspector** - Use Inspector for proactive validation before errors occur
