# F33 issue draft — APPROVED for filing as separate issue, per-issue go-ahead still required

Target repo: terrene-foundation/kailash-py (this BUILD repo — in-repo filing).
Per upstream-issue-hygiene MUST-1: present body → explicit user go-ahead → `gh issue create`.

---

**Title:** `fix(core): register_node decorator erases node subclass types — needs generic TypeVar`

**Labels:** `bug`, `typing`, `cross-sdk`

**Body:**

## Affected API

`kailash.nodes.base.register_node` (src/kailash/nodes/base.py:2673; inner decorator at :2720)

## Problem

The inner decorator is annotated `def decorator(node_class: type[Node])` with no generic
return type. Static checkers therefore infer every `@register_node()`-decorated class as
`type[Node]`, erasing the subclass. Every subclass-specific classmethod call on a decorated
class — e.g. `PythonCodeNode.from_function(...)` — emits a (non-gating) pyright
`attr-defined` diagnostic at every call site.

## Minimal repro

```python
from kailash.nodes.base import Node, register_node

@register_node()
class MyNode(Node):
    @classmethod
    def special(cls) -> "MyNode": ...

MyNode.special()  # pyright: "special" is not a known attribute of "type[Node]"
```

## Expected vs actual

Expected: the decorated class retains its precise type (standard generic-decorator pattern).
Actual: the decorated class is erased to `type[Node]`.

## Fix (typing-only, zero runtime change)

```python
from typing import Callable, TypeVar

T = TypeVar("T", bound=Node)

def register_node(alias: str | None = None) -> Callable[[type[T]], type[T]]:
    def decorator(node_class: type[T]) -> type[T]:
        ...
        return node_class
    return decorator
```

## Severity

LOW (static-typing only). High annoyance multiplier: every `from_function` call site in
kailash-kaizen's RAG node family emits the diagnostic.

## Acceptance criteria

- [ ] `@register_node()`-decorated subclasses retain their type under pyright.
- [ ] `PythonCodeNode.from_function` call sites emit no `attr-defined` diagnostic.
- [ ] Zero runtime behavior change (`NodeRegistry.register` path untouched).
- [ ] Cross-SDK inspection: check whether the kailash-rs node-registration path has an
      equivalent type-erasure issue (cross-sdk label).
