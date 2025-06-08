# Workflows Guide

This directory contains comprehensive workflow documentation for development, validation, and release processes in the Kailash Python SDK.

## Contents

### Core Workflows
- **[phases.md](phases.md)** - 🎯 The 5-phase development workflow (START HERE)
- **[development-workflow.md](development-workflow.md)** - Legacy 23-step workflow (reference)
- **[task-checklists.md](task-checklists.md)** - Task-specific checklists

### Process Guides
- **[mistake-tracking.md](mistake-tracking.md)** - 🐛 How to track and learn from mistakes
- **[validation-checklist.md](validation-checklist.md)** - ✅ All validation commands
- **[release-checklist.md](release-checklist.md)** - 🚀 Release process step-by-step

## Quick Start: 5-Phase Workflow

```
Phase 1: Discovery & Planning (PLAN MODE)
    ↓
Phase 2: Implementation & Learning (EDIT MODE)
    ↓
Phase 3: Mistake Analysis (PLAN MODE)
    ↓
Phase 4: Documentation Updates (EDIT MODE)
    ↓
Phase 5: Final Release (EDIT MODE)
```

See [phases.md](phases.md) for complete details.

## Key Principles

1. **Track Mistakes Immediately**: Use `guide/sessions/current-mistakes.md`
2. **Clear Context Between Phases**: Optimize memory usage
3. **Examples First**: Write and validate examples before implementation
4. **Learn from Errors**: Analyze mistakes to improve documentation
5. **Validate Continuously**: Run checks throughout development

## Quick Reference

### Starting a New Task
1. Enter PLAN MODE
2. Read [phases.md](phases.md)
3. Check `guide/todos/000-master.md`
4. Create implementation plan

### During Implementation
1. Create `guide/sessions/current-mistakes.md`
2. Write examples first
3. Track all errors as they occur
4. Run validation frequently

### Before Release
1. Analyze all mistakes (Phase 3)
2. Update documentation (Phase 4)
3. Run full validation suite
4. Follow [release-checklist.md](release-checklist.md)

## Context Management

### What to Load per Phase:
- **Phase 1**: References, ADRs, existing features
- **Phase 2**: Examples, source code, mistake tracker
- **Phase 3**: All mistake logs, patterns
- **Phase 4**: Documentation files
- **Phase 5**: Validation tools, release checklist

## See Also
- `guide/reference/` - API references and patterns
- `guide/features/` - Feature implementation guides
- `guide/mistakes/` - Historical mistake database
- `guide/sessions/` - Session-specific logs
