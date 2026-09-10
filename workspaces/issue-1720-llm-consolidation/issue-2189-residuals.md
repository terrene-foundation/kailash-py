## Summary

`#2189` ("a defect class worth sweeping for: an absence rendered as a success") landed a fix for one site (`evaluator.py:196-213`, commit `73c45fa43`) and named further sites in a comment. Those named sites are **still present** and have no tracking issue of their own, so they are invisible to every sweep that reads the issue list. This issue tracks them.

All three verified against `origin/dev` this session by reading the source.

## 1. `verify_chain()` returns `True` for an empty chain — in BOTH implementations

`src/kailash/trust/audit_store.py`. Three declarations (`grep -c 'async def verify_chain'` → 3): the Protocol stub at `:459`, `InMemoryAuditStore` at `:633`, and the persisted store at `:901`. Both concrete implementations open with the same guard:

```python
events = list(self._events)     # :645  (in-memory)
if not events:
    return True

rows = await cursor.fetchall()  # :916  (persisted)
if not rows:
    return True
```

**Why this is the #2189 class and not a triviality.** An empty chain is _mathematically_ intact, so `True` looks defensible. But `verify_chain()` is not asked "is this sequence self-consistent" — it is asked **"is the audit trail sound"**, and callers read `True` as that answer. There is a user-facing `verify_chain_cmd` registered in `src/kailash/trust/cli/__init__.py:79`, and both docstrings in-repo use it as an assertion of soundness (`audit_store.py:489`, `consent.py:296` — `assert await store.verify_chain()`).

Consequence: **an attacker who deletes the audit store passes verification.** A wipe and a never-written store are indistinguishable at the return value, and the wipe is the one case audit-chain verification exists to detect. The check cannot return False for the input it most needs to catch.

**Suggested fix.** Do not overload one boolean with two different facts. Either return a three-state result (`INTACT` / `EMPTY` / `TAMPERED`), or keep the boolean and add a separate `is_empty` / `event_count` the caller must consult — with the CLI reporting EMPTY distinctly from OK. A caller that genuinely wants "empty is fine" should have to say so. Note this is a **public API shape change**, which is why this is filed rather than patched in passing.

## 2. `SuspensionRecord.all_conditions_met()` is vacuously True with no conditions

`src/kailash/trust/pact/suspension.py:159`:

```python
def all_conditions_met(self) -> bool:
    """...
        Returns True vacuously if there are no conditions (defensive).
    """
    return all(c.satisfied for c in self.resume_conditions)
```

The docstring calls the vacuous case **"defensive"**. It is the opposite: this gates whether a suspended plan may RESUME, so a record constructed with an empty `resume_conditions` tuple resumes immediately and unconditionally. `resume_conditions` is a `tuple[ResumeCondition, ...]` on a dataclass — an empty tuple is constructible.

Fail-open on a resume gate. A suspension with no stated resume conditions should be **un-resumable without an explicit override**, not auto-resumable.

## 3. Health check asserts `len(registry) >= 0`

Named in `#2189`'s comment. `len()` of any sized object is `>= 0` by definition, so the assertion cannot fail. It reports healthy for an empty registry, a full one, and a corrupt-but-nonempty one alike. Either assert the property actually intended (a minimum expected registration count, or a specific key's presence) or delete it — an assertion that cannot fail is not a weaker check, it is not a check.

## Acceptance criteria

- [ ] `verify_chain()` (or its replacement) can return a non-OK verdict for an emptied store; a test wipes a populated store and asserts the verdict is NOT "intact".
- [ ] The test asserts **both poles** — a populated intact chain verifies, an emptied one does not. A single-pole test cannot distinguish this fix from "now always False".
- [ ] Both concrete implementations are fixed in the same change. Fixing only the in-memory one leaves the persisted store — the one holding real audit data — with the defect.
- [ ] `all_conditions_met()` does not return True for an empty `resume_conditions`; the docstring stops describing fail-open as "defensive".
- [ ] The `len(registry) >= 0` assertion is replaced with a falsifiable one or removed.
- [ ] Each new test is shown capable of failing (run it against the unfixed code, or against a mutation demonstrated to reach the code under test).

## Related

- `#2189` — parent. One site fixed (`73c45fa43`); these were named in a comment and left untracked.
- `#2162` — two conformance MUST checks that cannot return False. Same class, `trust/plane/conformance`.
