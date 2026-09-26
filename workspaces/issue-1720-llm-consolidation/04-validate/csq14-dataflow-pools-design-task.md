# DataFlow pool overrides — separate design task

Status: open design task; explicitly excluded from CSQ14 promotion by the user.

User decision on 2026-09-26: “Record separately; finish promotion (Recommended)”. This is the explicit exception to fixing the documented-but-unused argument in this promotion; it does not assert that the argument works.

The constructor declares `pools: Optional[Dict[str, Dict[str, Any]]] = None` and describes per-database pool overrides, but the constructor does not load or forward this argument (`packages/kailash-dataflow/src/dataflow/core/engine.py:281-283`; constructor contract `specs/dataflow-core.md:50`). The prior AST review found zero argument loads and rejected a positive-control load. Existing pool behavior therefore does not apply caller overrides.

The separate design must define supported primary/read keys, accepted driver options, validation of unknown keys and types, precedence against global constructor settings, and ownership/lifetime behavior. Then implement forwarding to every primary/read consumer, update the authoritative specification, and verify real driver configuration and resource cleanup. Cover distinct overrides, invalid inputs, default compatibility, and an opposing control proving ignored overrides fail the tests.

Do not infer a dictionary contract from this task. A design/plan approval is required before implementing the new contract. This task concerns this repository only; no cross-repository action is authorized.
