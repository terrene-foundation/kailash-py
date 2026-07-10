"""#1606 DB-identity resolver — Tier 1 (no external dependencies).

Covers the silent-fallback fix (redteam FINDING 1): a falsy/absent URL or a
non-URL keyword/value DSN MUST NOT silently collapse cross-DB isolation. The
resolver derives identity from the URL, falls back to credential-free
component config (host/port/dbname), and reports ``identity=None`` (so the
engine warns) only when neither yields a usable identity.

Also pins the documented scope caveat (FINDING 2): identity keys on database
LOCATION, not the connecting principal.

Tier: 1 (Unit).
"""

import hashlib

from dataflow.cache.key_generator import (
    CacheKeyGenerator,
    _hash8,
    _sanitize_component_host,
    hash_database_identity,
    resolve_db_identity,
)

_QUERY_SQL = "SELECT * FROM users WHERE active = $1"
_QUERY_PARAMS = [True]


def test_component_identity_sanitizes_dsn_shaped_host():
    """Defense-in-depth (#1606): a DSN-with-creds mis-set as `host` enters the
    component-identity pre-image credential-FREE; a bare hostname is unchanged.

    Parity with the URL path (which routes through mask_url before hashing):
    if an operator sets ``config.database.host`` to a full DSN with credentials
    AND leaves ``url`` absent, no credential byte may reach the hash pre-image.
    """
    dsn_host = "postgres://myuser:mypassword@realhost:5432/appdb"

    # The sanitized host (which feeds the hash pre-image) carries NO credential.
    sanitized = _sanitize_component_host(dsn_host)
    assert "mypassword" not in sanitized
    assert "myuser" not in sanitized

    # No credential byte enters the identity pre-image: the identity equals the
    # hash of the credential-free normalized string, and DIFFERS from the naive
    # with-credentials pre-image (proving the strip happened, not a coincidence).
    res = resolve_db_identity(host=dsn_host, port=5432, dbname="appdb")
    assert res.identity == _hash8(f"{sanitized}:5432/appdb")
    assert res.identity != _hash8(f"{dsn_host}:5432/appdb")

    # A userinfo-only host (no scheme) is also stripped.
    assert "mypassword" not in _sanitize_component_host("myuser:mypassword@realhost")

    # NO REGRESSION: a normal bare hostname is byte-identical (guard triggers
    # only on DSN-shaped hosts), so a correctly-configured host's identity is
    # unchanged from the pre-sanitize behavior.
    assert _sanitize_component_host("realhost") == "realhost"
    assert (
        resolve_db_identity(host="h1", port=5432, dbname="db1").identity == "8f1d9ced"
    )


def test_url_path_derives_identity_credential_free():
    res = resolve_db_identity(
        url="postgresql://alice:s3cret@db-a.example.com:5432/prod"
    )
    assert res.identity is not None
    assert res.source == "url"
    assert res.url_unparseable is False
    # Invariant 2 (no credentials): identity is the hash of the masked DSN.
    from kailash.utils.url_credentials import mask_url

    masked = mask_url("postgresql://alice:s3cret@db-a.example.com:5432/prod")
    assert "alice" not in masked and "s3cret" not in masked
    assert res.identity == hashlib.sha256(masked.encode()).hexdigest()[:8]


def test_falsy_url_no_components_yields_none_for_engine_to_warn():
    """No URL and no components -> identity None (engine emits the WARN)."""
    res = resolve_db_identity(url=None)
    assert res.identity is None
    assert res.source == "none"
    assert res.url_unparseable is False


def test_falsy_url_with_components_falls_back_isolation_holds():
    """FINDING 1(a): URL-less config still gets an identity from host/dbname."""
    res = resolve_db_identity(url=None, host="h1", port=5432, dbname="db1")
    assert res.identity is not None
    assert res.source == "components"
    assert res.url_unparseable is False


def test_unparseable_dsn_never_hashes_the_constant_sentinel():
    """FINDING 1(b): a non-URL DSN must NOT produce a constant identity.

    ``mask_url`` returns UNPARSEABLE_URL_SENTINEL for a libpq keyword DSN;
    hashing that constant would give every such instance the SAME identity.
    The resolver refuses: url_unparseable=True and (absent components) None.
    """
    res = resolve_db_identity(url="host=a dbname=x")
    assert res.identity is None
    assert res.url_unparseable is True
    # hash_database_identity likewise refuses the sentinel (no constant leak).
    assert hash_database_identity("host=a dbname=x") is None


def test_unparseable_dsn_with_components_rescues_but_flags_unparseable():
    """Unparseable URL + usable components -> component identity, still flagged.

    The engine warns on url_unparseable even though isolation now holds via
    components, so the operator learns the supplied URL could not be used.
    """
    res = resolve_db_identity(url="host=a dbname=x", host="h1", port=5432, dbname="db1")
    assert res.identity is not None
    assert res.source == "components"
    assert res.url_unparseable is True


def test_component_identity_isolates_two_urlless_instances():
    """FINDING 1(a): two URL-less configs at different DBs -> different keys."""
    i1 = resolve_db_identity(host="h1", port=5432, dbname="db1").identity
    i2 = resolve_db_identity(host="h2", port=5432, dbname="db2").identity
    assert i1 is not None and i2 is not None and i1 != i2

    g1 = CacheKeyGenerator(prefix="dataflow:query", db_identity=i1)
    g2 = CacheKeyGenerator(prefix="dataflow:query", db_identity=i2)
    k1 = g1.generate_key("User", _QUERY_SQL, _QUERY_PARAMS)
    k2 = g2.generate_key("User", _QUERY_SQL, _QUERY_PARAMS)
    assert k1 != k2, "different component-config DBs must yield different query keys"


def test_same_host_different_dbname_differ_same_dbname_same():
    """Component identity is keyed on host:port/dbname."""
    a = resolve_db_identity(host="h", port=5432, dbname="db1").identity
    b = resolve_db_identity(host="h", port=5432, dbname="db2").identity
    c = resolve_db_identity(host="h", port=5432, dbname="db1").identity
    assert a != b  # different dbname -> different identity
    assert a == c  # same host+port+dbname -> same identity (cache still works)


def test_documented_scope_same_location_different_principal_shares_identity():
    """FINDING 2 (documented caveat): identity keys on LOCATION, not principal.

    Two instances at the same host/port/dbname with DIFFERENT credentials
    share a cache namespace BY DESIGN (mask_url strips userinfo to ``***``).
    """
    alice = hash_database_identity("postgres://alice:pw1@h:5432/db")
    bob = hash_database_identity("postgres://bob:pw2@h:5432/db")
    assert (
        alice == bob
    ), "same DB location, different principal -> same identity (by design)"
