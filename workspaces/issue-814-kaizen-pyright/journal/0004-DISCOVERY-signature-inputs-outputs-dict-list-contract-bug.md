---
type: DISCOVERY
date: 2026-05-04
created_at: 2026-05-04T09:52:04Z
author: agent
session_id: 86231c0f-543f-4978-bf40-389e6b01a0e2
session_turn: post-commit
project: kailash-py
topic: research/adapter.py was passing dict to Signature(inputs=, outputs=) — corruption was real and silent
phase: implement
tags: [kaizen, signature, type-safety, pyright, contract-bug, silent-corruption]
---

# `Signature.inputs/outputs` accepts dict at runtime but contract is `List[str]`; iteration order silently became the param-name list

## What was discovered

`packages/kailash-kaizen/src/kaizen/research/adapter.py:119` was passing `dict[str, str]` to `Signature(inputs=, outputs=)`. The constructor's annotation is `List[str]` but the runtime accepted dict — Python iterates `dict` keys when `list()` is implicit, so `Signature._inputs_list` was populated with dict-keys-in-iteration-order rather than the intended ordered param-name list. Every downstream consumer that read `_inputs_list` operated on dict-keys-as-list. Pyright surfaced the mismatch as `reportArgumentType`; the underlying corruption was real and behavioral.

Fix at the call site (commit `eb2c42f0`):

```python
inputs: List[str] = list(param_names) if param_names else ["input"]
outputs: List[Union[str, List[str]]] = ["result"]
```

Tier 2 behavioral regression at `tests/regression/test_issue_814_research_adapter_inputs_list.py` asserts:

- `isinstance(sig._inputs_list, list)`
- All entries are `str` (not dict-stringified)
- Canonical content matches param-name list

The test loads `adapter.py` via `importlib.util.spec_from_file_location()` to bypass the pre-existing `kaizen.research.__init__.py` orphan re-exports (those orphans were deleted in #814 Shard 2 / commit `24446c7c`); the test now imports normally.

## Why this matters beyond #814

This is a class of failure mode that Python's runtime tolerance hides:

- Constructor's type annotation says `List[str]`
- Runtime accepts dict (because `list(dict)` works)
- Internal field ends up holding the wrong shape
- Downstream consumers iterate, get something that _looks_ right (still strings, still iterable), but the meaning is wrong

Same family as `rules/zero-tolerance.md` Rule 3c (Documented Kwargs Accepted But Unused): the documented contract advertises shape A, the code accepts shape B and produces "results" that pretend to honor A. Pyright is the mechanical defense; behavioral regression tests are the second.

## Where the dict came from

Pre-fix code at `adapter.py:119` was building `inputs`/`outputs` from `Signature.from_function()` introspection helpers that returned `dict[str, type]` (param name → annotation). The author either intended to pass `dict.keys()` and forgot, or assumed `Signature.__init__` would iterate. Either way, the silent acceptance hid the mistake until pyright was tightened in #814.

## Consequences

- adapter.py: 0 errors, 0 warnings post-fix (Pyright pinned `1.1.371`)
- Closes Cluster D in #814 (per the workspace's static-analysis baseline)
- Tier 2 regression test prevents recurrence
- The historical broken behavior (dict-keys-as-positional-args) was masked because every caller passed `param_names` whose key-set matched the intended positional order — adversarial inputs (param name order ≠ key iteration order, e.g., dicts ordered before Python 3.7) would have produced wrong outputs

## Follow-up

- None for #814 — closed by #821 + 2.19.0
- Same pattern would silently break any other site that constructs `Signature` from a dict introspection helper. `grep -rn "Signature(.*inputs=" packages/kailash-kaizen/` returned only adapter.py at the time of fix; future Signature-using code should be lint-bait.

## For Discussion

- Counterfactual: if pyright had not been tightened in #814, how would this corruption have been detected? The behavioral regression test only exists _because_ pyright surfaced the warning; a customer-reported bug would have been the alternative path, with no source of truth to bisect against.
- The fix uses `list(param_names) if param_names else ["input"]` — the fallback `["input"]` is a sentinel that masks "caller forgot to pass anything." Should the fallback raise instead, given that the contract already says `List[str]` and an empty list is a valid value?
- Specific data: pyright counted 1 `reportArgumentType` warning at this site; the same pattern could exist in other repos consuming kaizen's Signature class. Was the cross-repo grep done at fix time, or is there latent risk in downstream USE templates?
