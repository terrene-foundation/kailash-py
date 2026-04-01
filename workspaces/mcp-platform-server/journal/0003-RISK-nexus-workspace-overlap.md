---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T00:00:00Z
author: agent
session_turn: 1
project: mcp-platform-server
topic: Overlap with nexus-transport-refactor workspace on MCP code deletion
phase: analyze
tags: [mcp, nexus, workspace-overlap, coordination]
---

# RISK: Workspace Overlap with nexus-transport-refactor

## Background

The mcp-platform-server workspace plans to delete `packages/kailash-nexus/src/nexus/mcp/server.py`, `transport.py`, and `mcp_websocket_server.py` as part of MCP consolidation (TSG-500). A separate workspace (`nexus-transport-refactor`) exists at `workspaces/nexus-transport-refactor/` that also works on Nexus transport refactoring.

## Risk

If both workspaces modify or delete the same Nexus MCP files:

1. Git merge conflicts are guaranteed
2. One workspace's changes may invalidate the other's assumptions
3. Test migration could be duplicated or missed

## Likelihood

HIGH -- the files overlap directly. Both workspaces touch Nexus MCP transport code.

## Mitigation

Sequence the workspaces:

1. mcp-platform-server TSG-500 deletes the Nexus MCP files first
2. nexus-transport-refactor is informed that these files no longer exist
3. nexus-transport-refactor focuses on the remaining Nexus transport (HTTP, WebSocket, non-MCP)

Alternative: complete nexus-transport-refactor first. But MCP consolidation is the mcp-platform-server's core task and cannot be deferred.

## For Discussion

1. What is the current status of the nexus-transport-refactor workspace? Is it in /analyze, /todos, or /implement? If it has active todos touching the MCP files, coordination must happen immediately.

2. If nexus-transport-refactor has already been implemented on a branch, would merging that branch first reduce the conflict risk? Or does it create a different set of conflicts?

3. Should there be a workspace-level coordination mechanism in COC that detects overlapping file modifications across active workspaces?
