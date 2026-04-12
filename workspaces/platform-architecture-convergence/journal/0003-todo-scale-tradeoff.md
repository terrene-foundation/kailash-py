# TRADE-OFF: 450 tasks across 12 files vs fewer coarser tasks

**Date**: 2026-04-08
**Phase**: 02 (todos)

## Context

The `/todos` command says "write ALL todos for the ENTIRE project" and "each todo should be detailed enough to implement independently." The platform convergence touches 10 SPECs across 6 phases with cross-SDK lockstep, backward compat, and 40+ security threats. The result is 450 discrete tasks.

## Options evaluated

1. **450 fine-grained tasks** (chosen): one task per Build, Wire, Delete, Test, and Security Mitigation. Each task has specific file paths, acceptance criteria, and test names. An implementer can pick up any task without reading the full spec.

2. **~80 coarser tasks**: one task per SPEC section (e.g., "Implement SPEC-03 §2.4 routing strategy" as a single task). Fewer tasks to track, but each requires spec reading before starting.

3. **~150 medium tasks**: one per component (e.g., "Build + Wire StreamingAgent" as a single task). Middle ground but violates the Build/Wire pair discipline from `/todos` command.

## Decision

Option 1 (450 fine-grained). Reasons:
- Build/Wire pair discipline catches exactly the "unwired component" bug class
- Security mitigation tasks with explicit test names prevent "we'll add tests later" drift
- Cross-SDK lockstep needs per-component matched issues, not per-SPEC
- The `/implement` phase processes tasks one at a time; fine-grained tasks give better progress tracking
- Red team can validate per-task (and did — 27 findings across 450 tasks is a 6% finding rate)

## Trade-off

- Tracking 450 tasks requires tooling discipline (move to `todos/completed/` as each finishes)
- Cross-file references (TASK-03-NN depending on TASK-01-MM) are harder to follow
- Red team validation takes longer but catches more
