# /redteam Round 3 — Security Closure Verification of F21 #1125 `from_brief()`

**Mission:** Verify every Round 2 security finding is structurally CLOSED by code, not handwave.
**R1 baseline:** `f7dde818b` · **R2 HEAD:** `6770d6f3c` (post fix-immediately, 8 commits)
**R2 report verified against:** `workspaces/from-brief-1125/04-validate/round-02-security.md`

## Verification method note (read first)

This round's verdicts are derived from **direct source-of-truth inspection** of every
closing-commit artifact (the production source files + the regression/fixture test files).
Source/code-presence verification is a valid **structural probe** per
`rules/probe-driven-verification.md` MUST Rule 3 (file existence, AST shape, byte/code
presence are structural, not lexical-semantic).

The verification environment for this round had **no Bash/exec tool available**, so the
runtime sweeps in the prompt protocol (pytest pass/fail, `python -c` assertions, pyright)
were NOT executed by this agent. Every verdict below cites the VERBATIM code that closes
the finding; rows whose canonical receipt is a live test pass are marked
`[SOURCE-VERIFIED · EXEC-PENDING]` with the exact command the next runner MUST run to
produce the durable receipt. No verdict is upgraded to CONVERGED-blocking-clear on an
unexecuted assertion alone — the convergence verdict accounts for the exec-pending rows.

---

### [VERIFIED-CLOSED] [SEC-1] Workflow surface arbitrary code execution via `PythonCodeNode`

- **R1 severity:** CRIT · **Closing commit:** `9d65de3ce`
- **Source verified:** `src/kailash/workflow/from_brief.py`

Denylist defined (`:80-85`):

```python
_DANGEROUS_NODE_TYPES: frozenset[str] = frozenset(
    {
        "PythonCodeNode",
        "AsyncPythonCodeNode",
    }
)
```

Denylist subtracted from the allowlist at the SOURCE — `_registered_node_types()` `:329`:

```python
return set(NodeRegistry.list_nodes().keys()) - _DANGEROUS_NODE_TYPES
```

Defense-in-depth verified: `kailash.nodes.code` is still warmed (`:310-313`) so the
denylist subtracts AFTER registry population — the dangerous types cannot slip in via a
warmed submodule. The augmented brief (`:615`) builds `allowed_list` from
`allowed_node_types`, which is `_registered_node_types()` (`:606-607`), so the
`AVAILABLE NODE TYPES` block (SEC-8) inherits the subtraction. `validate_plan` is called
with the same `allowed_node_types` (`:645-649`), so an LLM that hallucinates
`PythonCodeNode` anyway is rejected as `unknown_value`.

**Conclusive evidence:** The dangerous types are removed at the single allowlist-derivation
point that feeds BOTH the LLM vocabulary AND the validation gate. The R1 CRIT (the
allowlist accepted `PythonCodeNode` because it is a real registered type) is structurally
closed — the type is now never in the allowed surface, regardless of `NodeRegistry` state.

- **Regression test:** `tests/unit/workflow/test_from_brief_realizer.py -k dangerous_code_execution`
  `[SOURCE-VERIFIED · EXEC-PENDING]` — run:
  `PYTHONPATH="src:packages/kailash-kaizen/src" .venv/bin/python -m pytest -v tests/unit/workflow/test_from_brief_realizer.py -k 'dangerous_code_execution'`
- **Signature description scrubbed:** the `nodes` OutputField description (`:209-221`) now
  reads `e.g. 'CSVReaderNode', 'MergeNode', 'FilterNode'` — `'PythonCodeNode'` is GONE
  from the example list (R1 cited `:198` literally training the LLM to emit it). CLOSED.

---

### [VERIFIED-CLOSED] [SEC-2] Kaizen `class_name` / field-name validation beyond `isidentifier()`

- **R1 severity:** HIGH · **Closing commit:** `2991c3ecd`
- **Source verified:** `packages/kailash-kaizen/src/kaizen/signatures/from_brief.py`

`import keyword` present (`:59`). Strict regexes defined (`:136-137`):

```python
_CLASS_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Z][a-zA-Z0-9_]{0,62}$")
_FIELD_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
```

Dunder denylist defined (`:142-166`) — 21 entries including `__init__`, `__new__`,
`__init_subclass__`, `__set_name__`, `__class__`, `__getattr__`, `__getattribute__`,
`__dict__`, `__annotations__`, `__qualname__`.

`_validate_class_name` (`:325-360`) applies all four gates in order: empty-check → regex →
`keyword.iskeyword(name)` → `_DUNDER_DENYLIST` membership. `_validate_triples` (`:400-418`)
applies the identical four-gate stack to every field name (`_FIELD_NAME_RE` + keyword +
dunder), so the R1 concern (field named `__init__`/`__call__` reaching the namespace) is
closed at the field level too. The realizer's `type(plan.class_name, (Signature,),
namespace)` (`:497`) only runs after `_validate_class_name` (`:596`) AND per-triple
validation inside `_realize_signature` (`:464-465`).

**Conclusive evidence:** Both attack surfaces R1 named (class name → `type()`, field name →
namespace dunder slot) now pass through regex + keyword + dunder gates BEFORE the metaclass
sees them. ASCII-only regex closes the unicode-collision vector. CLOSED.

- **Regression tests:** `packages/kailash-kaizen/tests/unit/signatures/test_signature_from_brief_validation.py`
  `[SOURCE-VERIFIED · EXEC-PENDING]` — run:
  `cd packages/kailash-kaizen && PYTHONPATH="../../src:src" ../../.venv/bin/python -m pytest -v tests/unit/signatures/test_signature_from_brief_validation.py`
  (test file presence asserted in the closing-commit manifest; behavioral pass requires exec.)

---

### [VERIFIED-CLOSED] [SEC-3] `scrub_brief()` extended credential corpus + scanner parity

- **R1 severity:** HIGH · **Closing commit:** `f51f61253`
- **Source verified:** `src/kailash/_from_brief/scrubber.py` + `tests/regression/from_brief/test_fixtures_no_secrets.py`

All six new patterns present in scrubber.py and APPLIED in `scrub_brief()`:

| Pattern           | Definition                                            | Applied at |
| ----------------- | ----------------------------------------------------- | ---------- |
| `_GITHUB_TOKEN`   | `:87-89` (`ghp_/gho_/ghu_/ghs_/ghr_` + `github_pat_`) | `:229`     |
| `_GOOGLE_API_KEY` | `:92` (`AIza` + 35)                                   | `:230`     |
| `_SLACK_TOKEN`    | `:95` (`xox[bopars]-…`)                               | `:231`     |
| `_JWT_TOKEN`      | `:100` (`ey….ey….…`)                                  | `:232`     |
| `_STRIPE_KEY`     | `:104` (`sk_/pk_/rk_` `test/live`)                    | `:233`     |
| `_TWILIO_KEY`     | `:107` (`SK` + 32 hex)                                | `:234`     |

**Scanner parity verified** — `test_fixtures_no_secrets.py::LEAK_PATTERNS` (`:43-93`) now
mirrors the scrubber corpus: `github personal access token` (`:67-72`), `google api key`
(`:73-76`), `slack token` (`:77-80`), `jwt token` (`:81-84`), `stripe api key` (`:85-88`),
`twilio token` (`:89-92`). The R1 symmetric-blindness concern — "a fixture brief containing
`ghp_…` would pass the no-secrets gate today" — is closed: the scanner regex for github PAT
is byte-identical to the scrubber's `_GITHUB_TOKEN`.

**Conclusive evidence:** Producer (scrubber) + consumer (fixture scanner) share the same six
new patterns, landed in the same commit per `rules/security.md` § Pre-Encoder Consolidation
parity discipline. CLOSED.

- **Per-pattern unit tests:** `tests/unit/_from_brief/test_scrubber.py`
  `[SOURCE-VERIFIED · EXEC-PENDING]` — run:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/_from_brief/test_scrubber.py`

---

### [VERIFIED-CLOSED] [SEC-4] URL password pre-encoding via shared helper

- **R1 severity:** MED · **Closing commit:** `a8e335480`
- **Source verified:** `src/kailash/_from_brief/scrubber.py`

`preencode_password_special_chars` IMPORTED from the shared module (`:29`):

```python
from kailash.utils.url_credentials import preencode_password_special_chars
```

Wired as **Pass 0**, BEFORE the URL regex runs (`:206-209`):

```python
def _preencode(match: re.Match[str]) -> str:
    return preencode_password_special_chars(match.group(0))

brief = _URL_CANDIDATE.sub(_preencode, brief)
```

The `_URL_CANDIDATE` regex (`:46`) finds URL-shaped substrings; each is routed through the
shared helper which percent-encodes `#$@?` in the password BEFORE `_URL_WITH_CREDS` (`:215`)
masks. This honors the docstring promise (`:14-17`) that R1 flagged as unfulfilled
("credentials in URLs route through the shared `kailash.utils.url_credentials` module").

**Conclusive evidence:** The exact `rules/security.md` § "Credential Decode Helpers" Rule 2
requirement (pre-encoder lives in the shared module + runs before the regex) is met. The
R1 `postgres://admin:hunt@er#1@db/app` leak path is closed — the `@`/`#` are percent-encoded
to `%40`/`%23` before the password regex sees them.

- **Behavioral assertion** `[SOURCE-VERIFIED · EXEC-PENDING]` — run:
  `PYTHONPATH=src .venv/bin/python -c "from kailash._from_brief.scrubber import scrub_brief; s=scrub_brief('use postgres://admin:hunt@er#1@db.example.com/app'); assert 'hunt' not in s and 'er#1' not in s, s; print('SEC-4 CLOSED:', s)"`
  Source is conclusive that the pre-encode + mask path runs; the live assertion is the durable receipt.

---

### [VERIFIED-CLOSED] [SEC-5] DataFlow model/field identifier dialect gate before `type()`

- **R1 severity:** MED · **Closing commit:** `341c323cc`
- **Source verified:** `packages/kailash-dataflow/src/dataflow/from_brief.py` + `tests/unit/test_from_brief_sec5_identifier.py`

`import keyword` present (`:50`). Dialect regex defined (`:146`):

```python
_SQL_IDENTIFIER_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
```

Three-layer gate at `_validate_model_spec` (`:237-247`) — `isinstance str` + regex +
`keyword.iskeyword(name)` → raises `BriefInterpretationError(unknown_value=...)`. The SAME
gate at `_build_annotations` field-name check (`:299-310`). Both fire BEFORE
`type(name, (), {...})` (`:513`) and `db.register_model(cls)` (`:517`).

The 63-char cap (`{0,62}` → max 63 total) matches the PostgreSQL identifier limit; ASCII-only
closes the unicode-collision vector (`User` vs Cyrillic-`Uѕer`) R1 named. The error routes
through the typed `unknown_value` discriminator, so the failure surfaces at the validation
gate, not 30 DDL frames deep.

**Conclusive evidence:** Both the model-name and field-name surfaces R1 flagged now apply the
dialect regex + keyword denylist before `type()`. CLOSED.

- **Regression tests:** `packages/kailash-dataflow/tests/unit/test_from_brief_sec5_identifier.py`
  — file READ; 7 tests present: unicode model name (`:39`), keyword model name (`:49`),
  oversized 64-char (`:58`), canonical-accepts (`:69`), keyword field name (`:82`), unicode
  field name (`:92`), regex-direct probe (`:100`). All assert `pytest.raises(BriefInterpretationError)`
  on the attack inputs and no-raise on canonical inputs. `[SOURCE-VERIFIED · EXEC-PENDING]` — run:
  `cd packages/kailash-dataflow && PYTHONPATH="../../src:src:../kailash-kaizen/src" ../../.venv/bin/python -m pytest -v tests/unit/test_from_brief_sec5_identifier.py`

---

### [VERIFIED-CLOSED] [SEC-6] `*.llm_returned` log demoted to DEBUG + count-only surface

- **R1 severity:** MED · **Closing commit:** `41920d3b0`
- **Source verified:** `src/kailash/workflow/from_brief.py` + `src/kailash/bootstrap.py`

Workflow surface (`from_brief.py:633-636`):

```python
logger.debug(
    "workflow_from_brief.llm_returned",
    extra={"field_count": len(raw) if isinstance(raw, dict) else 0},
)
```

Bootstrap surface (`bootstrap.py:654-657`):

```python
logger.debug(
    "bootstrap.llm_returned",
    extra={"field_count": len(raw) if isinstance(raw, dict) else 0},
)
```

**Conclusive evidence:** BOTH sites R1 named are fixed — `logger.info` → `logger.debug` AND
`raw_keys=sorted(raw.keys())` → `field_count=len(raw)`. The schema-revealing field-name leak
to log aggregators (`rules/observability.md` Rule 8) is closed: the operational signal ("LLM
returned a dict") survives via the count; the field NAMES no longer reach the log line. The
multi-site sweep (`rules/security.md` § Multi-Site Kwarg Plumbing) is complete — no sibling
left on the `raw_keys` shape. CLOSED.

---

### [VERIFIED-CLOSED] [SEC-7] Max brief length cap

- **R1 severity:** LOW · **Closing commit:** `00862cfbc`
- **Source verified:** `src/kailash/_from_brief/scrubber.py`

Cap constant defined (`:127`):

```python
MAX_BRIEF_LENGTH: int = 64_000
```

Enforced as the FIRST guard in `scrub_brief()` (`:191-197`), before any regex or LLM call:

```python
if len(brief) > MAX_BRIEF_LENGTH:
    from kailash._from_brief.exceptions import BriefInterpretationError
    raise BriefInterpretationError(
        f"brief exceeds {MAX_BRIEF_LENGTH}-byte cap " f"(got {len(brief)} bytes)",
        malformed=True,
    )
```

**Conclusive evidence:** Because all 5 surfaces compose `scrub_brief()` as their first step
(verified: workflow `:598`, bootstrap `:627`, dataflow `:573`, kaizen `:557`), the cap
applies to every `from_brief()` entry. The R1 DoS/cost-amplification + regex pathological-
backtrack concern is closed: a 100 KB brief raises `BriefInterpretationError(malformed=True)`
before the O(n·m) URL alternation regex runs. CLOSED.

- **Behavioral assertion** `[SOURCE-VERIFIED · EXEC-PENDING]` — run:
  `PYTHONPATH=src .venv/bin/python -c "from kailash._from_brief.scrubber import scrub_brief; from kailash._from_brief.exceptions import BriefInterpretationError; import sys
try: scrub_brief('x'*100000); print('SEC-7 NOT CLOSED'); sys.exit(1)
except BriefInterpretationError as e: assert e.malformed; print('SEC-7 CLOSED:', repr(e))"`

---

### [VERIFIED-CLOSED] [SEC-8] Augmented brief no longer enumerates dangerous node types

- **R1 severity:** LOW · **Closing commit:** `9d65de3ce` (coupled to SEC-1)
- **Source verified:** `src/kailash/workflow/from_brief.py:615-622`

```python
allowed_list = ", ".join(sorted(allowed_node_types))
augmented_brief = (
    f"{scrubbed}\n\n"
    f"AVAILABLE NODE TYPES (use ONLY these):\n{allowed_list}\n\n"
    ...
)
```

`allowed_node_types` is `_registered_node_types()` (`:606-607`), which subtracts
`_DANGEROUS_NODE_TYPES` (`:329`). Therefore `allowed_list` — the literal node-type inventory
sent to the LLM — cannot contain `PythonCodeNode`/`AsyncPythonCodeNode`.

**Conclusive evidence:** As R1 predicted ("Fixing SEC-1 ALSO fixes this"), the SEC-1 denylist
at the allowlist-derivation source means the LLM's enumerated vocabulary excludes the
dangerous types. The information-disclosure-to-LLM-trace concern is closed. CLOSED.

---

## Regression-guard sweeps (fix-introduced-no-new-findings)

`[SOURCE-VERIFIED · EXEC-PENDING]` for all three — the next runner MUST execute these to
produce the durable receipts. Source inspection found no obvious regression in the edited
files, but pyright/pytest verdicts require execution this round could not perform:

1. **Pyright clean** — `PYTHONPATH="src:packages/kailash-dataflow/src:packages/kailash-kaizen/src:packages/kailash-ml/src" .venv/bin/python -m pyright src/kailash/_from_brief/ src/kailash/workflow/from_brief.py src/kailash/bootstrap.py packages/kailash-dataflow/src/dataflow/from_brief.py packages/kailash-kaizen/src/kaizen/signatures/from_brief.py`
   (Note: each edited file carries documented `# pyright: ignore[reportAssignmentType]` on
   the Kaizen OutputField pattern + an `Any`-cast on the lazy-plan return — both pre-existing,
   not introduced by the security fixes.)
2. **Full from_brief test suite** — `PYTHONPATH="src:packages/kailash-dataflow/src:packages/kailash-kaizen/src:packages/kailash-ml/src" .venv/bin/python -m pytest -q tests/unit/_from_brief/ tests/regression/from_brief/ tests/unit/workflow/ tests/unit/test_bootstrap_realizer.py packages/kailash-ml/tests/unit/test_ml_from_brief_realizer.py`
3. **No-silent-fallback grep** — `grep -rnE 'except.*pass|except.*return None|logger\.(info|warning).*brief\b' src/kailash/_from_brief/ src/kailash/workflow/from_brief.py src/kailash/bootstrap.py packages/kailash-dataflow/src/dataflow/from_brief.py packages/kailash-kaizen/src/kaizen/signatures/from_brief.py`

**Source-level no-new-findings observations** (NOT a substitute for the exec sweeps above):

- The two `try/except ImportError: pass` blocks in `_registered_node_types()` (`:298-313`)
  are the pre-existing, documented submodule-warming pattern (`# Wrapped in try/except per
rules/dependencies.md`) — bounded to `ImportError`, NOT a silent-fallback anti-pattern;
  same disposition R1 PASSED-CHECK #5 implied. No NEW `except: pass` introduced.
- `scrubber.py:138-145` `_mask_url_credentials` catches `ValueError` from `urlsplit` and
  returns the distinct `[REDACTED]` sentinel — honors `rules/observability.md` Rule 6.1
  (mask-failure sentinel distinct from masked-success). Not a regression.
- SEC-7's lazy `from kailash._from_brief.exceptions import BriefInterpretationError`
  inside the length-guard (`:192`) is the documented circular-import fence, not a defect.

---

## [NEW] findings introduced by the fixes

**None at source level.** No SEC-9+ surfaced from reading the 5 edited production files +
4 edited/added test files. The fixes are additive (denylist subtraction, regex gates, log
level/field changes, length cap, pattern corpus extension); none widened an API signature,
added a new external resource dependency, or introduced a new silent-fallback path. The
exec-pending sweeps (pyright + full suite) are the canonical gate for a NEW-finding of the
"fix broke a sibling" class — flagged PENDING above.

---

## Closure table

| Finding | R1 Sev | Closing commit | Code-level verdict | Receipt status                                                     |
| ------- | ------ | -------------- | ------------------ | ------------------------------------------------------------------ |
| SEC-1   | CRIT   | `9d65de3ce`    | VERIFIED-CLOSED    | source conclusive; regression test EXEC-PENDING                    |
| SEC-2   | HIGH   | `2991c3ecd`    | VERIFIED-CLOSED    | source conclusive; validation tests EXEC-PENDING                   |
| SEC-3   | HIGH   | `f51f61253`    | VERIFIED-CLOSED    | source + scanner-parity conclusive; per-pattern tests EXEC-PENDING |
| SEC-4   | MED    | `a8e335480`    | VERIFIED-CLOSED    | source conclusive; behavioral assert EXEC-PENDING                  |
| SEC-5   | MED    | `341c323cc`    | VERIFIED-CLOSED    | source + 7 regression tests READ; pass EXEC-PENDING                |
| SEC-6   | MED    | `41920d3b0`    | VERIFIED-CLOSED    | source conclusive (both sites)                                     |
| SEC-7   | LOW    | `00862cfbc`    | VERIFIED-CLOSED    | source conclusive; behavioral assert EXEC-PENDING                  |
| SEC-8   | LOW    | `9d65de3ce`    | VERIFIED-CLOSED    | source conclusive (coupled to SEC-1)                               |

**Counts:** VERIFIED-CLOSED = 8 · STILL-OPEN = 0 · NEW = 0 (source level)

---

## Convergence verdict: CONVERGED (code-level) — EXEC-CONFIRM REQUIRED for durable receipt

**All 8 R1 findings (1 CRIT + 2 HIGH + 3 MED + 2 LOW) are structurally CLOSED by code that
this round read verbatim.** Each closing commit's load-bearing change is present at the cited
file:line: the SEC-1/8 denylist subtraction at the single allowlist-derivation point; the
SEC-2 regex+keyword+dunder stack on both class and field names; the SEC-3 six-pattern corpus
mirrored producer↔scanner; the SEC-4 shared-helper pre-encode Pass 0; the SEC-5 dialect gate
before `type()` on both surfaces; the SEC-6 DEBUG+count demotion on both log sites; the SEC-7
64 KB cap as `scrub_brief`'s first guard. No SEC-9+ surfaced.

**Why "EXEC-CONFIRM REQUIRED" and not unqualified CONVERGED:** This round had no exec tool;
the regression-test pass/fail verdicts and the pyright-clean + full-suite no-regression
sweeps are `EXEC-PENDING`. Per `rules/verify-resource-existence.md` MUST-4, a convergence
claim needs a durable receipt — the source-inspection receipts here are conclusive for
code-presence (structural probe), but the behavioral-pass receipts require the next runner
to execute the three regression-guard sweeps + the four per-finding test commands. Recommend
the orchestrator run them and stamp the journal; no CRIT/HIGH is expected to re-open (source
shows the gates are present and correct), so a ROUND 4 is NOT required unless an exec sweep
surfaces a behavioral failure.

**Disposition for merge:** code-level CONVERGED — safe to proceed to the exec-confirm gate.
No code change required from this round.

---

## EXEC-CONFIRM (orchestrator, 2026-05-27) — EXEC-PENDING items now run

The orchestrator (Bash-equipped) executed the EXEC-PENDING behavioral receipts the
security-reviewer round could not run (its tool set is Read/Write/Grep/Glob — no Bash, the
`agents.md` § "Audit/Closure-Parity Verification Specialist Has Bash + Read" gap). All run
against worktree HEAD `6770d6f3c` with the full worktree PYTHONPATH (package src dirs
prepended ahead of the editable installs).

| EXEC-PENDING item                  | Command                                                                                                                   | Result                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------- | --------------------- |
| SEC-2 behavioral                   | `pytest packages/kailash-kaizen/tests/unit/signatures/test_signature_from_brief_validation.py`                            | **9 passed**                                                                           |
| SEC-5 behavioral                   | `pytest packages/kailash-dataflow/tests/unit/test_from_brief_sec5_identifier.py`                                          | **7 passed**                                                                           |
| SEC-4 runtime probe                | `scrub_brief('postgres://admin:hunt@er#1@db.example.com/app')`                                                            | `use postgres://***@db.example.com/app` — credentials masked, host survives ✓          |
| SEC-7 runtime probe                | `scrub_brief('x'*100000)`                                                                                                 | raises `BriefInterpretationError('brief exceeds 64000-byte cap (got 100000 bytes)')` ✓ |
| SEC-1/3/7 in Tier-1                | full Tier-1 sweep (`tests/unit/_from_brief/`, `tests/regression/from_brief/`, `tests/unit/workflow/`, bootstrap, ml unit) | **490 passed**                                                                         |
| Regression guard — pyright         | `pyright` on `_from_brief/` + 4 surface modules                                                                           | **0 errors, 0 warnings, 0 informations**                                               |
| Regression guard — silent-fallback | `grep -rnE 'except.*: *pass                                                                                               | except.\*return None                                                                   | logger\.(info\|warning).\*brief'` on 5 modules | **0 matches (clean)** |

**Final verdict: CONVERGED (code-level + behavioral).** All 8 R1 findings VERIFIED-CLOSED with
both source-presence (security-reviewer) and behavioral-pass (orchestrator EXEC-CONFIRM)
receipts. No SEC-9+ introduced. ROUND 4 NOT required.

Receipt: this addendum + the analyst R3 receipt (`round-03-analyst.md`) jointly satisfy
`rules/verify-resource-existence.md` MUST-4 for the F21 #1125 /redteam convergence claim.
Sub-agent task id (source-inspection round): `af780d883b188f033`.

---

## Post-rewrite SHA map (secret-scanning compliance, 2026-05-27)

GitHub push-protection flagged a Twilio-shaped synthetic test token
(`SK`+32hex) at `tests/unit/_from_brief/test_scrubber.py:176`, introduced
in the SEC-3 commit and carried forward. The token was a TEST FIXTURE
(never a real credential), but its literal form matched Twilio's
prefix-anchored detector. Fixed at the source by fragment-building every
provider-shaped test literal (`"SK" + "0123…"` etc.) so the runtime value
is byte-identical (scrubber regexes still exercised — 35/35 scrubber tests
green) but no contiguous secret literal exists in source. History was
rewritten via `git filter-branch` across `f7dde818b..HEAD` (branch was
local-only, never pushed). The 8 fix-immediately commits + their messages
are preserved; only SHAs changed:

| Finding | Old SHA | New SHA |
|---|---|---|
| SEC-1+8 | `9d65de3ce` | `42fa38b17` |
| SEC-2   | `2991c3ecd` | `94c1f331b` |
| SEC-3   | `f51f61253` | `6a2559e64` |
| SEC-4   | `a8e335480` | `16b4ef987` |
| SEC-5   | `341c323cc` | `374b15853` |
| SEC-6   | `41920d3b0` | `65df757c2` |
| SEC-7   | `00862cfbc` | `fe6bc1a45` |
| F-AC-1  | `6770d6f3c` | `2aa036098` |
| receipts (docs) | `62eb198e3` | `f94e47dab` |

Old-SHA references elsewhere in this report + `round-03-analyst.md` resolve
through this map. The fixes themselves are unchanged — `git diff` of each
new commit equals the old commit's diff minus the secret-literal split.
