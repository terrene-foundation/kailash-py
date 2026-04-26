---
id: W6-002
title: Add Tier-2 test for MCP ElicitationSystem
priority: P1
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-F-32
severity: HIGH
spec: specs/mcp-server.md
domain: mcp
specialist: mcp-specialist
wave: W1
---

## Why

W5-F finding F-F-32: `tests/integration/mcp_server/test_elicitation_integration.py` is named in `specs/mcp-server.md` but the file does NOT exist. This is `rules/orphan-detection.md` §1 — a spec-cited test that doesn't exist breaks the contract that the spec's §11 Test Contract section describes shipped behavior.

## What changes

- Create `packages/kailash-mcp/tests/integration/mcp_server/test_elicitation_integration.py` with Tier-2 coverage of the ElicitationSystem (real MCP server, real client, real elicitation request/response flow).
- Cover: happy-path elicitation, server-side validation rejection, client-side timeout, cancellation.
- Verify spec § 11 assertions match the test file.

## Capacity check

- LOC: ~150 (single test file)
- Invariants: 4 (one per assertion in spec §11)
- Call-graph hops: 2 (test → MCPServer → ElicitationSystem)
- Describable: "Create the spec-cited Tier-2 test file for ElicitationSystem."

## Spec reference

- `specs/mcp-server.md` § ElicitationSystem + § 11 Test Contract
- `rules/orphan-detection.md` § 1 + § 2

## Acceptance

- [ ] File exists at the spec-cited path
- [ ] Test imports through MCP facade (real server, NOT mocked) per `rules/testing.md` § Tier 2
- [ ] All 4 elicitation scenarios covered
- [ ] `pytest --collect-only` exits 0 against new file
- [ ] CHANGELOG entry in kailash-mcp

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-F-findings.md` F-F-32
