# Milestone 5: Security Verification

All 12 hardened security patterns confirmed preserved. Security regression tests pass.

## TODO-47: Run security pattern regression tests

Execute the existing security regression suite:
```bash
pytest tests/trust/plane/integration/security/ -v
```

This includes:
- `test_security_patterns.py` — validates 12 hardened patterns
- `test_static_checks.py` — static analysis for security anti-patterns

**Acceptance**: All security tests pass. Zero regressions.

---

## TODO-48: Manual security pattern checklist

Verify each of the 12 hardened patterns documented in `.claude/rules/trust-plane-security.md`:

- [ ] 1. `validate_id()` — path traversal prevention (in `_locking.py`)
- [ ] 2. `O_NOFOLLOW` via `safe_read_json()` — symlink attack prevention
- [ ] 3. `atomic_write()` — crash-safe writes (temp file + fsync + os.replace)
- [ ] 4. `math.isfinite()` on numeric constraints (in `compliance.py`, `models.py`)
- [ ] 5. Bounded collections (`maxlen=10000`) — OOM prevention (in `enforce/`)
- [ ] 6. Monotonic escalation — trust state only forward (in `posture/postures.py`)
- [ ] 7. `hmac.compare_digest()` — timing side-channel protection (in chain verification)
- [ ] 8. Key material zeroization — memory safety (in `key_manager.py`)
- [ ] 9. `frozen=True` on MultiSigPolicy + constraint dataclasses (in `signing/multi_sig.py`, `plane/models.py`)
- [ ] 10. `from_dict()` validation — JSON tampering detection (all dataclasses)
- [ ] 11. `isfinite()` on runtime costs — budget bypass prevention (in `constraints/budget_tracker.py`)
- [ ] 12. `normalize_resource_path()` — cross-platform path normalization (in `pathutils.py`)

**Acceptance**: All 12 patterns confirmed present and functional at their new paths.

---

## TODO-49: Verify _locking.py accessibility from both layers

Test that both protocol and plane code can import from `kailash.trust._locking`:

```python
# Protocol layer can use it
from kailash.trust._locking import validate_id, safe_read_json, atomic_write

# Plane layer can use it
from kailash.trust._locking import validate_id, safe_read_json, atomic_write
```

Verify no import path issues from the shared location.

**Acceptance**: Both layers import successfully. Security functions work identically.

---

## TODO-50: Run security-reviewer agent

Mandatory security review per `rules/agents.md` Rule 2 before any commit.

Scope: All files in `src/kailash/trust/`, all new `__init__.py` files, all shim files, all pyproject.toml changes.

**Focus areas**:
- No secrets in moved code
- No new eval/exec patterns
- Parameterized SQL preserved in all store modules
- No relaxed file permissions
- Lazy imports don't bypass security checks

**Acceptance**: Security reviewer signs off. Zero CRITICAL findings.

---

## TODO-51: Verify no import-time pynacl loading

Verify that `import kailash` and `from kailash.trust import GenesisRecord` do NOT trigger pynacl import:

```bash
# In a venv WITHOUT pynacl installed:
python -c "import kailash; print('OK')"
python -c "from kailash.trust.chain import GenesisRecord; print('OK')"
python -c "from kailash.trust.exceptions import TrustError; print('OK')"
# These must all succeed

# This should fail with clear message:
python -c "from kailash.trust.signing.crypto import generate_keypair"
# Expected: ImportError with "pip install kailash[trust]" message
```

**Acceptance**: Pure-type imports work without pynacl. Crypto imports fail with clear message.
