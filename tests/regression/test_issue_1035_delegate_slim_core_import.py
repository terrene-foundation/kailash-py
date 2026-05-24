"""Regression: `from kailash.delegate import ...` must work on slim-core.

Issue #1035 follow-up — kailash 2.26.0 shipped `kailash.delegate.verifier`
with a MODULE-SCOPE `from cryptography...` import. Because the delegate
package is inside the slim-core import closure, a bare `pip install kailash`
(which does NOT ship cryptography — it lives in the [trust]/[server] extras)
raised `ModuleNotFoundError: No module named 'cryptography'` on the documented
`from kailash.delegate import Delegate, ...` line.

The fix moves the cryptography import to be lazy inside `Ed25519Verifier.__init__`
(loud `ModuleNotFoundError` at construction if the extra is absent; the
established "loud failure at call site" pattern for extras-gated capability).
`NullVerifier` — the default — needs no cryptography.

These are BEHAVIORAL regression tests (subprocess + sys.modules introspection),
not source-grep, so they survive refactors per `rules/testing.md`.
"""

import subprocess
import sys

import pytest


@pytest.mark.regression
def test_delegate_import_does_not_eager_load_cryptography():
    """`import kailash.delegate` MUST NOT pull cryptography into sys.modules.

    This is the slim-core invariant: the delegate package is importable on a
    bare `pip install kailash` where cryptography is absent. Asserting that
    cryptography is NOT in sys.modules after the import proves the crypto
    import is lazy (deferred to Ed25519Verifier construction), without
    requiring a cryptography-free environment to run the test in.
    """
    code = (
        "import sys; import kailash.delegate; "
        "assert 'cryptography' not in sys.modules, "
        "'kailash.delegate eager-loaded cryptography — slim-core broken'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"slim-core import invariant broken:\n{result.stderr}"


@pytest.mark.regression
def test_delegate_1035_import_line_resolves():
    """The literal #1035 acceptance import line MUST resolve.

    Run in a subprocess so the assertion exercises a fresh import of the
    delegate package, not the already-imported test-session state.
    """
    code = (
        "from kailash.delegate import ("
        "Delegate, ConstraintEnvelope, PrincipalDirectory, "
        "GenesisRecord, PostureState, AuditChain, Connector); "
        "from kailash.delegate import Verifier, NullVerifier, Ed25519Verifier; "
        "assert NullVerifier().verify(b'm', b's', 'x') is False"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"#1035 delegate import line failed:\n{result.stderr}"
