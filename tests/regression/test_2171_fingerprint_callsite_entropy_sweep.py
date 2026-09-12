"""Regression: the fingerprint sweep's entropy classification, pinned.

Issue #2171 acceptance criterion 4 -- sweep the ``fingerprint_secret`` call
sites whose input is enumerable, and decide each one. The nexus rate-limit
site was keyed in 757e18578 because its input is a client IP (PII, 2**32) and
its call-site comment promised the raw value stayed out of the log. Every
OTHER site was swept here and dispositioned the opposite way: keep the
unkeyed tag, correct the comment that over-promised.

That is not laziness, it is what the sinks need. These tags exist to JOIN --
a log line to the exception raised beside it, a Python service's record to a
Rust service's under the 8-hex cross-SDK contract in
``rules/event-payload-classification.md`` 2. Joining requires the same input
to produce the same tag in a different process, and every form of keying
destroys exactly that (measured: a per-process key defeats enumeration
completely and makes two processes disagree). The nexus site could be keyed
only because a DEPLOYMENT-scoped key preserves the correlation it needed;
there is no equivalent shared key across SDKs and languages here.

So these tests pin the CLASSIFICATION, which is the thing a future reader
could get wrong. An enumerable site's tag IS recoverable -- asserted, so
nobody later builds a confidentiality assumption on top of it. A
high-entropy site's tag is NOT -- asserted, so nobody "fixes" the working
sites by keying them and silently breaks every log join in the SDK.
"""

import itertools
import string

import pytest

from kailash.utils.command_safety import safe_command_ref
from kailash.utils.url_credentials import fingerprint_secret


@pytest.mark.regression
def test_command_ref_is_recoverable_for_a_routine_command():
    """``command_safety.safe_command_ref`` -- #2171 listed this at :132.

    The ref keeps a launcher label plus an unkeyed digest of the WHOLE
    command. For an ordinary command line that is enumerable.
    """
    target = "python3 -m http.server 8080"
    ref = safe_command_ref(target)

    candidates = [
        f"python3 -m http.server {port}" for port in (80, 443, 8000, 8080, 9000)
    ]
    assert target in candidates, "control: target must be in the search space"

    recovered = [c for c in candidates if safe_command_ref(c) == ref]
    assert recovered == [target]
    # Control: a ref for a command held OUT of the space matches nothing, so
    # the comparison discriminates rather than matching everything.
    other = safe_command_ref("python3 -m http.server 31337")
    assert [c for c in candidates if safe_command_ref(c) == other] == []


@pytest.mark.regression
def test_command_ref_never_echoes_an_argument():
    """The property that DOES hold at this sink, and is what it is for.

    Recoverability is accepted; leaking a credential verbatim is not.
    """
    ref = safe_command_ref("npx -y @vendor/server --token=s3cret-value-here")

    assert "s3cret-value-here" not in ref
    assert "--token" not in ref
    assert "@vendor/server" not in ref
    assert ref.startswith("npx#")


@pytest.mark.regression
def test_preset_name_falls_to_its_own_allowlist_alphabet():
    """``kaizen/llm/presets.py`` -- #2171 listed this at :79.

    ``_validate_preset_name`` constrains a preset name to
    ``^[a-z][a-z0-9_]{0,31}$``. A two-character name is therefore drawn from
    a space of 37*26, which is exhaustible outright -- no dictionary needed.
    """
    target = "gp"
    tag = fingerprint_secret(target)

    alphabet = string.ascii_lowercase + string.digits + "_"
    space = [a + b for a, b in itertools.product(string.ascii_lowercase, alphabet)]
    assert target in space, "control: target must be in the exhaustive space"

    recovered = [c for c in space if fingerprint_secret(c) == tag]
    assert target in recovered


@pytest.mark.regression
def test_filesystem_path_is_recoverable_from_a_dictionary():
    """``kaizen/llm/auth/gcp.py`` -- #2171 listed :410, :416, :421, :459.

    The docstring there claimed a fingerprinted path "cannot leak a
    filesystem layout". It cannot leak it VERBATIM; it does confirm a guess.
    """
    target = "/etc/gcp/service-account.json"
    tag = fingerprint_secret(target)

    candidates = [
        "/etc/gcp/service-account.json",
        "/home/app/sa.json",
        "/var/secrets/gcp.json",
        "/opt/creds/key.json",
    ]
    assert target in candidates, "control: target must be in the search space"

    assert [c for c in candidates if fingerprint_secret(c) == tag] == [target]


@pytest.mark.regression
def test_schema_field_name_is_recoverable():
    """``dataflow/core/nodes.py`` -- #2171 listed this at :1035.

    A column name comes from the schema, so anyone holding the log line and
    the schema recovers it. The VALUE is the part genuinely withheld.
    """
    target = "password"
    tag = fingerprint_secret(target)

    schema = ["id", "email", "password", "created_at", "tenant_id", "token"]
    assert target in schema, "control: target must be in the search space"

    assert [c for c in schema if fingerprint_secret(c) == tag] == [target]


@pytest.mark.regression
def test_high_entropy_credential_sites_are_not_recoverable():
    """The sites #2171 said are genuinely fine, asserted rather than assumed.

    ``auth/bearer.py``, ``auth/azure.py``, ``auth/gcp.py`` (the TOKEN calls,
    not the PATH ones) and ``kailash_mcp/auth/providers.py`` all feed this
    helper a real credential. Those are safe because the PRE-IMAGE cannot be
    enumerated -- not because the helper protects them -- which is why this
    test lives beside the ones above.
    """
    import secrets

    token = "sk-" + secrets.token_hex(32)
    tag = fingerprint_secret(token)

    guesses = ["sk-" + secrets.token_hex(32) for _ in range(2000)]
    assert [g for g in guesses if fingerprint_secret(g) == tag] == []
    # Control: the true pre-image matches, so the loop can succeed at all.
    assert fingerprint_secret(token) == tag


@pytest.mark.regression
def test_every_swept_site_still_agrees_across_processes():
    """The reason every swept site kept the unkeyed digest.

    If a future change keys any of these, this fails -- which is the point:
    keying is not a local decision, it breaks the cross-process and
    cross-SDK join these tags exist for.
    """
    import subprocess
    import sys

    probe = (
        "import sys; sys.path.insert(0, 'src');"
        "from kailash.utils.url_credentials import fingerprint_secret;"
        "from kailash.utils.command_safety import safe_command_ref;"
        "print(fingerprint_secret('/etc/gcp/sa.json'), safe_command_ref('python3 app.py'))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.split()

    assert out == [
        fingerprint_secret("/etc/gcp/sa.json"),
        safe_command_ref("python3 app.py"),
    ]
