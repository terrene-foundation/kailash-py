# Milestone 6: Publishing & Release

All packages published to PyPI in correct order. Clean install verified.

## TODO-52: Full test suite — final gate

Run the complete test suite across all packages:

```bash
pytest  # All tests
```

Verify:
- Core kailash tests pass
- Trust protocol tests pass (`tests/trust/`)
- Trust plane tests pass (`tests/trust/plane/`)
- Kaizen tests pass
- DataFlow tests pass
- Nexus tests pass
- Shim backward compat tests pass

**Acceptance**: All tests green. Zero failures.

---

## TODO-53: TestPyPI validation — kailash 2.0.0

Per deployment rules (mandatory for major releases):

```bash
python -m build
twine upload --repository testpypi dist/kailash-2.0.0*.whl
```

Verify clean install:
```bash
python -m venv /tmp/verify --clear
/tmp/verify/bin/pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ kailash==2.0.0
/tmp/verify/bin/python -c "from kailash.trust.chain import GenesisRecord; print('OK')"

/tmp/verify/bin/pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ "kailash[trust]==2.0.0"
/tmp/verify/bin/python -c "from kailash.trust.signing.crypto import generate_keypair; print('OK')"
```

**Acceptance**: Clean venv install + import verification passes.

---

## TODO-54: Publish kailash 2.0.0 to production PyPI

```bash
twine upload dist/kailash-2.0.0*.whl  # Wheels only per deployment rules
```

**Acceptance**: `pip install kailash==2.0.0` works from PyPI.

---

## TODO-55: Build and publish eatp 0.3.0 (shim)

```bash
cd packages/eatp
python -m build
twine upload dist/eatp-0.3.0*.whl
```

**Acceptance**: `pip install eatp==0.3.0` pulls in kailash[trust]. Old imports work with DeprecationWarning.

---

## TODO-56: Build and publish trust-plane 0.3.0 (shim)

```bash
cd packages/trust-plane
python -m build
twine upload dist/trust_plane-0.3.0*.whl
```

**Acceptance**: `pip install trust-plane==0.3.0` pulls in kailash[trust]. Old imports work with DeprecationWarning.

---

## TODO-57: Build and publish kailash-kaizen 2.0.0

```bash
cd packages/kailash-kaizen
python -m build
twine upload dist/kailash_kaizen-2.0.0*.whl
```

**Acceptance**: `pip install kailash-kaizen==2.0.0` installs. `from kaizen.trust import TrustOperations` works.

---

## TODO-58: Publish kailash-dataflow and kailash-nexus minor bumps

Only if upper version bound was changed:

```bash
cd packages/kailash-dataflow && python -m build && twine upload dist/*.whl
cd packages/kailash-nexus && python -m build && twine upload dist/*.whl
```

**Acceptance**: Both install with kailash 2.0.0.

---

## TODO-59: End-to-end clean install verification

In a completely fresh environment:

```bash
python -m venv /tmp/e2e --clear

# Test 1: Core only
/tmp/e2e/bin/pip install kailash==2.0.0
/tmp/e2e/bin/python -c "from kailash import Workflow, LocalRuntime; print('Core OK')"
/tmp/e2e/bin/python -c "from kailash.trust.chain import GenesisRecord; print('Types OK')"

# Test 2: Trust
/tmp/e2e/bin/pip install "kailash[trust]==2.0.0"
/tmp/e2e/bin/python -c "from kailash.trust.signing.crypto import generate_keypair; print('Crypto OK')"

# Test 3: Kaizen
/tmp/e2e/bin/pip install kailash-kaizen==2.0.0
/tmp/e2e/bin/python -c "from kaizen.trust import TrustOperations; print('Kaizen OK')"

# Test 4: Shim backward compat
/tmp/e2e/bin/pip install eatp==0.3.0
/tmp/e2e/bin/python -c "from eatp import TrustOperations; print('Shim OK')"

# Test 5: CLI
/tmp/e2e/bin/eatp --help
/tmp/e2e/bin/attest --help
```

**Acceptance**: All 5 tests pass.

---

## TODO-60: Create GitHub Release

Create a GitHub release for kailash 2.0.0:

```bash
gh release create v2.0.0 --title "kailash 2.0.0 — Trust Integration" \
    --notes "EATP protocol and trust-plane platform merged into kailash.trust.*"
```

**Acceptance**: Release visible on GitHub with release notes.
