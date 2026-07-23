# DISCOVERY — Cross-SDK inspection for #1927: no equivalent unwired-param gap in the Rust SDK

Date: 2026-07-23. Repo class: BUILD. Author: agent. Phase: codify.
relates_to: 0012-DISCOVERY-param-completeness-guard-vs-documented-kwarg-drop

## The inspection (cross-sdk-inspection Rule 1)

User-authorized READ-only inspection of the Rust SDK (receipt:
`.claude/cross-repo-authz/2026-07-23-esperie-enterprise-kailash-rs-read-only-cross-sd.md`,
READ tier). Question: does the Rust SDK expose a `Delegate`/agent facade with
documented-but-unwired constructor params — the #1927 `signature`/`inner_agent` no-op
equivalent? **Answer: NO.** The architecture differs materially, so the class does not exist there.

## Evidence

- The Rust SDK's `Delegate` (`bindings/kailash-python/.../kaizen/__init__.pyi`) is a
  **trust-plane delegation primitive** (`"Trust-plane delegation primitive"`), NOT the Python
  kaizen-agents streaming autonomous-execution facade. Different purpose entirely.
- The Rust agent-execution facade is `GovernedAgentRuntime(agent, llm_client, spec_version)` —
  every constructor param is functional; there is no `signature`/`inner_agent` param. (The
  ungoverned `DelegateEngine` is DEPRECATED, superseded by `GovernedAgentRuntime`.)
- Where `inner_agent` appears in LIVE Rust code (`StreamingAgent::wrap(inner_agent)`,
  `GovernedAgent::new(inner_agent, ...)`, `agent.clone_inner()`) it is a FUNCTIONALLY-WIRED
  wrapped agent, never a stored-and-never-read no-op.
- `signature` in the Rust SDK refers to an agent-contract `SignatureMismatch` error
  (`crates/kailash-kaizen/src/error.rs`), a different concept from the Python Delegate's
  structured-output `signature` param.
- An ARCHIVED spec (`workspaces/_archive/.../05-spec-delegate-engine.md`) carries the ORIGINAL
  Python Delegate design with `inner_agent` intended to be wired (`if inner_agent is not None:
core = inner_agent`) — confirming the param was DESIGNED functional; the Python impl never
  wired it, the Rust SDK implements a different facade.

## Disposition

No cross-SDK issue filed (no gap → nothing to file → no separate filing authorization needed).
The #1927 documented-kwarg-drop class is Python-kaizen-agents-facade-specific. cross-sdk-inspection
Rule 1 checklist satisfied: checked, no equivalent, no file. Confirms the pre-inspection
low-value assessment. handoff-completion satisfied: the check was EXECUTED, not left implied.

## For Discussion

1. The Rust SDK reached the SAME end-state (a governed agent runtime with only functional
   constructor params) by a DIFFERENT path (GovernedAgentRuntime + trust-plane Delegate split),
   never accumulating the documented-but-unwired params the Python facade did. Is that because
   Rust's stricter constructor ergonomics (no silent `**kwargs` drop; an unused param is a
   compile warning) structurally resist the class — i.e. is the completeness-guard (journal 0012)
   a Python-specific need the Rust type system already enforces?
2. Counterfactual: had the Python Delegate been generated FROM the same spec as the Rust one
   (`05-spec-delegate-engine.md`, which wired `inner_agent`), would #1899/#1926/#1927 have
   happened at all — i.e. is the root cause a Python impl that drifted from its own spec, and does
   that argue for a spec-conformance test over (or alongside) the AST completeness-guard?
