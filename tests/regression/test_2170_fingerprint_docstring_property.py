"""Regression: the fingerprint helpers' docstrings describe what they DO.

Issue #2170 (zero-tolerance Rule 3e): ``fingerprint_secret`` and
``fingerprint_value`` each opened with "Generate a short non-reversible ...",
and ``fingerprint_secret`` additionally justified its algorithm choice with
"BLAKE2b is a fast keyed-hash that CodeQL does not flag for this rule" --
25 lines above the *correct* sentence saying there is "no secret keying
material". A reader hitting the first claim stops there.

Both halves of that justification were measured false:

* **unkeyed** -- no ``key=`` reaches ``hashlib.blake2b``; two independent
  interpreters produce the identical digest.
* **"CodeQL does not flag"** -- ``py/weak-sensitive-data-hashing`` alert
  11474 landed on this exact function (``url_credentials.py:731``) and was
  re-minted as 11556 at ``:732`` after a one-line shift. It was dismissed
  because the rule's store-then-verify premise fails, NOT because the hash
  is strong.

The BEHAVIOUR is accepted as-is (co-owner decision recorded on #2170,
2026-08-17): an unkeyed 32-bit tag is what buys cross-process and cross-SDK
log correlation, and keying it destroys exactly that. Only the documentation
was wrong. So these tests pin the PROPERTIES the corrected docstrings now
claim, not the docstring prose -- prose pins rot, and a property pin fails
the moment someone "hardens" the helper and silently breaks every log join
in the SDK.
"""

import hashlib
import itertools
import subprocess
import sys

import pytest

from kailash.utils.url_credentials import fingerprint_secret, fingerprint_value


@pytest.mark.regression
def test_digest_is_unkeyed_so_independent_processes_agree():
    """The corrected docstring says UNKEYED. Unkeyed means reproducible.

    This is the property the whole design rests on: a tag emitted by one
    service must join a tag emitted by another. A keyed variant -- which the
    old "keyed-hash" wording advertised -- could not do this, so this test
    fails if anyone ever makes the wording true by keying the function.
    """
    probe = (
        "import sys; sys.path.insert(0, 'src');"
        "from kailash.utils.url_credentials import fingerprint_secret, fingerprint_value;"
        "print(fingerprint_secret('join-me'), fingerprint_value('join-me'))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert out == [fingerprint_secret("join-me"), fingerprint_value("join-me")]


@pytest.mark.regression
def test_digest_equals_plain_unkeyed_blake2b():
    """Structural pin on "no ``key=`` is passed", asserted through behaviour.

    A keyed BLAKE2b of the same input yields a different digest, so equality
    with the bare construction is only possible when the call is unkeyed.
    """
    value = "https://metadata.google.internal/computeMetadata/v1/"
    expected = hashlib.blake2b(value.encode("utf-8"), digest_size=4).hexdigest()[:8]

    assert fingerprint_secret(value) == expected
    assert fingerprint_value(value) == expected
    # Control: a KEYED digest of the same input differs, so the assertion
    # above could have failed. Without this the test proves nothing.
    keyed = hashlib.blake2b(
        value.encode("utf-8"), digest_size=4, key=b"k" * 16
    ).hexdigest()[:8]
    assert keyed != expected


@pytest.mark.regression
def test_tag_is_reversible_for_an_enumerable_input():
    """The word removed from both docstrings was "non-reversible". It is false.

    Recovering the plaintext from the tag by enumeration is the exact
    capability the old wording denied, so demonstrating it IS the pin. If a
    future change makes the tag genuinely non-reversible (keying it), this
    test fails and the docstrings must be revisited together with every
    caller that relies on cross-process correlation.
    """
    target = "https://metadata.google.internal/computeMetadata/v1/"
    tag = fingerprint_value(target)

    schemes = ["http://", "https://"]
    hosts = ["metadata.google.internal", "169.254.169.254", "localhost"]
    paths = ["/", "/computeMetadata/v1/", "/latest/meta-data/"]
    candidates = [f"{s}{h}{p}" for s, h, p in itertools.product(schemes, hosts, paths)]
    assert target in candidates, "control: the target must be in the search space"

    recovered = [c for c in candidates if fingerprint_value(c) == tag]

    assert recovered == [target]
    # Control: a target held OUT of the candidate space is not recovered, so
    # the loop above is discriminating rather than matching everything.
    absent_tag = fingerprint_value("https://not-in-the-candidate-list.example/")
    assert [c for c in candidates if fingerprint_value(c) == absent_tag] == []


@pytest.mark.regression
@pytest.mark.parametrize("length", [4, 8, 16, 32])
def test_the_two_helpers_stay_byte_identical(length):
    """#2150 kept them as separate bodies ON PURPOSE, to keep the two CodeQL
    taint graphs separate. Nothing in the call graph enforces the identity the
    docstrings promise -- only this kind of test does, and the correlation
    between ``url_safety``'s log line and ``errors``' exception depends on it.
    """
    for value in [
        "",
        "x",
        "https://svc:pw@api.example.com/v1?api_key=abc",
        "npx -y @vendor/server --token=s3cret",
        "openai_prod",
    ]:
        assert fingerprint_secret(value, length=length) == fingerprint_value(
            value, length=length
        ), f"drifted on {value!r} at length={length}"


@pytest.mark.regression
def test_high_entropy_input_is_not_recoverable_by_enumeration():
    """The scoping claim the corrected docstring adds: what protects a real
    credential is the PRE-IMAGE's entropy, not the 32-bit width.

    A random 256-bit key is not in any enumerable space, so the same attack
    that recovers a URL above returns nothing here.
    """
    import secrets

    secret = secrets.token_hex(32)
    tag = fingerprint_secret(secret)

    guesses = [secrets.token_hex(32) for _ in range(2000)]
    assert [g for g in guesses if fingerprint_secret(g) == tag] == []
    # Control: the real pre-image DOES match, so the comparison works at all.
    assert fingerprint_secret(secret) == tag
