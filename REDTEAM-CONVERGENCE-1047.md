# /redteam Convergence Note — issue #1047

Branch: `test/issue-1047-sanitizer-contract`
Scope: test-authoring only (no production change; `nodes.py` read-only).

## Result: CONVERGED — zero CRIT/HIGH in delivered test code

`14 passed, 2 xfailed, 0 failed in 0.44s` (file); `19 passed, 2 xfailed`
across the whole `unit/security/` dir (pre-existing canary unaffected).

## Rounds

### Round 1 — Non-vacuity (PASS)
Each contract assertion proven to FAIL under the exact regression
`rules/security.md` forbids:
- Rule 1: quote-escape regression → `STATEMENT_BLOCKED` absent AND `''`
  present → both Rule-1 assertions fail. Non-vacuous.
- Rule 2: gate-removed regression → `pytest.raises(ValueError)` does not
  raise → test fails. Non-vacuous. (The set/tuple xfail(strict=True) IS
  a live non-vacuity proof: it currently DID-NOT-RAISE.)
- Rule 3: premature `json.dumps` regression → `isinstance(out, dict)`
  False → test fails. Non-vacuous.

### Round 2 — No mocking of the thing under test (PASS)
Zero `mock`/`patch`/`MagicMock`/`monkeypatch` primitives. The only
`mock` substring is the word "mocked" in the module docstring (prose).
`sanitize_sql_input` + the type-confusion gate run real, exercised
through the same `express._create_node(model, "Create")` construction
path the production express layer uses.

### Round 3 — Collection + Tier-1 compliance (PASS)
`--collect-only` clean (21 tests in dir, no errors). Every test
`@pytest.mark.unit`, SQLite `:memory:` fixture, < 1s each (0.44s total).

## HEADLINE FINDING — CONTRACT VIOLATION (HIGH; route as production fix)

`rules/security.md` § Sanitizer Contract **Rule 2** explicitly
enumerates `set`/`tuple` (alongside `dict`/`list`) as MUST-raise
`ValueError("parameter type mismatch: …")` for declared-`str` fields.
The implementation **silently `str()`-coerces `set`/`tuple`** — the
exact "Silent `str(value)` coercion is BLOCKED" failure mode the rule
prohibits.

Root cause (file:line):
- `packages/kailash-dataflow/src/dataflow/core/nodes.py:903` —
  `validate_inputs` runs `sanitize_sql_input(value, field_name)` on
  every field FIRST.
- `nodes.py:805-816` — `sanitize_sql_input` `safe_types` tuple is
  `(int, float, bool, datetime, date, time, Decimal, dict, list)` —
  **`set`/`tuple` are NOT listed**.
- `nodes.py:822-823` — non-safe, non-str values fall through to
  `value = str(value)`. `set`/`tuple` hit this and become strings.
- `nodes.py:920-922` — the type-confusion gate then tests
  `isinstance(value, (dict, list, set, tuple))`; the value is now a
  `str` → `False` → **no `ValueError` raised**. `dict`/`list` survive
  the sanitize pass (they ARE in `safe_types`) so the gate sees them
  and raises correctly — that is why `dict`/`list` conform and only
  `set`/`tuple` violate.

Same defect exists on the bulk path (`nodes.py:971-1002`): bulk records
also run `sanitize_sql_input` before the bulk type-confusion gate at
`nodes.py:985-995`, so bulk `set`/`tuple` for str fields are equally
silently coerced. (Not exercised by these unit tests — flagged for the
production-fix workstream's regression coverage.)

Suggested production fix (for the routed workstream, NOT applied here):
add `set, tuple` to the `safe_types` short-circuit's *sibling* — i.e.
let `sanitize_sql_input` return `set`/`tuple` unchanged (as it does
`dict`/`list`) so the downstream type-confusion gate can see and reject
them; OR move the type-confusion gate BEFORE the sanitize pass. Either
fix makes the 2 xfail tests XPASS, which (under `strict=True`) forces
them to be un-xfailed in the same fix PR.

Tests assert the CONTRACT (MUST raise), held under
`@pytest.mark.xfail(strict=True)` so the suite is green while the gap is
open and auto-flips to a hard failure the instant production is fixed —
the gap cannot silently re-close or be forgotten.
