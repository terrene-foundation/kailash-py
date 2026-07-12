"""#1606 EXPRESS v3 cross-SDK byte-for-byte CONFORMANCE (Tier 1).

The Rust SDK LEADS the express cache keyspace contract (issue #1606 / the Rust
SDK's #1713, contract ``dataflow-cache-keys-v3``): it DEFINES the v3 keyspace,
generates the canonical byte-vectors, and kailash-py MUST reproduce every
``physical`` string byte-for-byte for the same inputs.

Per ``rules/cross-sdk-inspection.md`` Rule 4a, the canonical fixture is
VENDORED byte-for-byte from the Rust SDK (NOT re-authored) at
``tests/fixtures/dataflow-cache-keys.json`` and consumed here directly. Rule 4
requires >=3 real sibling-SDK byte vectors PLUS sentinels (empty params_hash,
cross-DB anti-collision, credential-strip) — all six V1-V6 are exercised below.

This is the exhaustive byte contract; ``test_issue_1606_keyspace_tripwire.py``
pins the common shapes as a loud drift tripwire.

Tier: 1 (Unit — no external dependencies).
"""

import json
from pathlib import Path

import pytest

from dataflow.cache.key_generator import (
    CacheKeyGenerator,
    express_db_instance_fingerprint,
)

# The vendored canonical fixture (byte-identical to the Rust SDK's
# test-vectors/dataflow-cache-keys.json). tests/unit/cache/ -> tests/fixtures/.
_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "dataflow-cache-keys.json"
)


def _load_fixture() -> dict:
    with _FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _vectors() -> list:
    return _load_fixture()["vectors"]


def test_fixture_is_the_vendored_v3_contract():
    """Guards that the vendored fixture is the expected v3 contract, not drift."""
    fixture = _load_fixture()
    assert fixture["contract"] == "dataflow-cache-keys-v3"
    # Rule 4 minimum: >=3 real vectors + the empty/cross-DB/credential sentinels.
    ids = [v["id"] for v in fixture["vectors"]]
    assert ids == ["V1", "V2", "V3", "V4", "V5", "V6"], (
        f"canonical vector set drifted: {ids}. The fixture is vendored "
        f"byte-for-byte from the Rust SDK — do not edit it locally; re-vendor."
    )


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: v["id"])
def test_express_db_instance_fingerprint_matches_canonical(vector):
    """express_db_instance_fingerprint reproduces the canonical db_instance."""
    got = express_db_instance_fingerprint(vector["input"]["db_target"])
    assert got == vector["db_instance"], (
        f"{vector['id']}: db_instance fingerprint drifted for "
        f"{vector['input']['db_target']!r}: got {got!r}, "
        f"expected {vector['db_instance']!r}. This is a byte-for-byte cross-SDK "
        f"contract — a drift breaks cross-DB cache-key parity with the Rust SDK."
    )


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: v["id"])
def test_express_physical_key_matches_canonical(vector):
    """The full v3 physical key reproduces the canonical byte-string.

    Reproduces ``physical`` end-to-end from ``input``: fingerprint the
    ``db_target``, then assemble the key with the vector's pre-computed
    ``params_hash`` (the assembly seam ``_assemble_express_key`` is the py
    equivalent of the Rust SDK's ``BackendKey::to_physical`` — it takes an
    already-computed params_hash, exactly as the canonical vectors provide).
    """
    inp = vector["input"]
    db_instance = express_db_instance_fingerprint(inp["db_target"])
    gen = CacheKeyGenerator(express_db_instance=db_instance)

    physical = gen._assemble_express_key(
        inp["model"],
        inp["op"],
        inp["params_hash"],  # canonical pre-computed hash (incl. "" for V4)
        inp["tenant"],
    )
    assert physical == vector["physical"], (
        f"{vector['id']}: physical key drifted: got {physical!r}, "
        f"expected {vector['physical']!r}. Changing express bytes is a cross-SDK "
        f"LOCKSTEP (#1606/the Rust SDK's #1713) — re-pin v3 in BOTH SDKs."
    )


def test_v5_cross_database_anti_collision():
    """SENTINEL V5: identical tenant+model+op+params, DIFFERENT db -> DIFFERENT key.

    This is the exact #1606 bug the keyspace closes: without the db_instance
    segment, V2 (app_a) and V5 (app_b) would collide and one tenant would read
    the other database's cached row.
    """
    by_id = {v["id"]: v for v in _vectors()}
    v2, v5 = by_id["V2"], by_id["V5"]

    # Same everything except the database target.
    assert v2["input"]["tenant"] == v5["input"]["tenant"]
    assert v2["input"]["model"] == v5["input"]["model"]
    assert v2["input"]["op"] == v5["input"]["op"]
    assert v2["input"]["params_hash"] == v5["input"]["params_hash"]
    assert v2["input"]["db_target"] != v5["input"]["db_target"]

    # Distinct db_instance -> distinct physical keys (no cross-DB bleed).
    assert express_db_instance_fingerprint(
        v2["input"]["db_target"]
    ) != express_db_instance_fingerprint(v5["input"]["db_target"])
    assert v2["physical"] != v5["physical"]


def test_v6_credentials_stripped_before_hashing():
    """SENTINEL V6: userinfo (credentials) is stripped BEFORE hashing.

    V6 has the same normalized target as V1 but with ``svc_user:s3cr3t@``
    userinfo; the credential is removed before hashing so db_instance and the
    physical key are byte-identical to V1 (no credential reaches the keyspace).
    """
    by_id = {v["id"]: v for v in _vectors()}
    v1, v6 = by_id["V1"], by_id["V6"]

    assert "svc_user" in v6["input"]["db_target"]  # credentials present in input
    assert express_db_instance_fingerprint(
        v6["input"]["db_target"]
    ) == express_db_instance_fingerprint(v1["input"]["db_target"])
    assert v6["physical"] == v1["physical"]
    # No credential byte ever appears in the emitted key.
    assert "svc_user" not in v6["physical"]
    assert "s3cr3t" not in v6["physical"]


def test_unparseable_and_empty_urls_fail_closed():
    """A falsy or scheme-less URL yields None (caller warns; isolation INACTIVE).

    Hashing a garbage constant would collapse every such instance into one
    identity — the silent-fallback failure mode (``zero-tolerance.md`` Rule 3).
    """
    assert express_db_instance_fingerprint(None) is None
    assert express_db_instance_fingerprint("") is None
    assert express_db_instance_fingerprint("not-a-url-no-scheme") is None


def test_query_string_and_fragment_stripped_before_hashing():
    """py-local: query string + fragment are excluded from the fingerprint.

    Not a canonical vector (the rs-led fixture pins the credential-strip
    sentinel V6 but no query-string case). A query string can itself carry a
    credential (``?password=...``), so it MUST NOT reach the keyspace pre-image
    (`security.md` § No secrets in logs). Two URLs differing ONLY in query /
    fragment therefore share ONE db-instance (same database location), and no
    query byte appears in the fingerprint pre-image.
    """
    base = "postgres://cache-host:5432/app_a"
    with_query = "postgres://cache-host:5432/app_a?sslmode=require&password=leak"
    with_fragment = "postgres://cache-host:5432/app_a#frag"

    fp_base = express_db_instance_fingerprint(base)
    assert fp_base is not None
    # Query string and fragment do not change the database-location identity.
    assert express_db_instance_fingerprint(with_query) == fp_base
    assert express_db_instance_fingerprint(with_fragment) == fp_base
    # And it equals the canonical V1 db_instance (same normalized target).
    assert fp_base == "dbd4e3f17d35c2bb57"


def test_userinfo_variants_stripped_consistently():
    """py-local: userinfo (incl. an ``@`` inside the password) is fully stripped.

    The strip takes the host side of the LAST ``@`` (``rsplit("@", 1)``), so a
    password containing ``@`` cannot leave a residual credential fragment in the
    pre-image. All credentialed variants collapse to the credential-free form.
    """
    plain = "postgres://cache-host:5432/app_a"
    fp = express_db_instance_fingerprint(plain)
    for creds in (
        "postgres://user:pw@cache-host:5432/app_a",
        "postgres://user:p@ss@cache-host:5432/app_a",  # '@' inside the password
        "postgres://user@cache-host:5432/app_a",  # user only, no password
    ):
        got = express_db_instance_fingerprint(creds)
        assert got == fp, f"userinfo not fully stripped for {creds!r}: {got!r}"


def test_scheme_only_credential_dsn_fails_closed():
    """py-local: a `//`-less credential-bearing DSN fails closed (returns None).

    ``urlparse("postgres:user:pass@host/db")`` yields an empty netloc with the
    userinfo in ``path``, so the netloc `@`-strip cannot fire; hashing that
    pre-image would leak credential bytes into it. The fingerprint refuses
    (None → caller WARNs, isolation INACTIVE) rather than hash a credential.
    A valid sqlite file URL (empty netloc, no `@` in path) is UNAFFECTED.
    """
    # `//`-less DSN with embedded credentials -> fail closed.
    assert express_db_instance_fingerprint("postgres:user:s3cr3t@host/db") is None
    # A valid sqlite file URL (empty netloc, no '@') still fingerprints (V3).
    assert (
        express_db_instance_fingerprint("sqlite:///var/data/app_b.db")
        == "db5c74b84689218303"
    )
