"""#1606 cache-keyspace TRIPWIRE (Tier 1).

This module pins the EXACT byte string of TWO cache keyspaces, which have
DIFFERENT cross-SDK contracts and MUST NOT be conflated:

1. EXPRESS ``v2`` keyspace (``generate_express_key``) — RUST-PINNED / cross-SDK
   LOCKSTEP. It is a byte-for-byte contract with kailash-rs (the Rust SDK,
   ``v3.19.0``, BP-049); see ``src/dataflow/cache/key_generator.py`` docstring.
   Changing ANY express byte pinned here diverges the two SDKs' cache keys and
   breaks cross-SDK invalidation — it is a deliberate ``v2 -> v3`` lockstep to
   be done in BOTH SDKs, never one. These assertions stay loud.

2. QUERY keyspace (``generate_key``) — NOT Rust-pinned. It hashes a normalized
   SQL string + params, which diverges cross-SDK by construction (the py and rs
   query builders emit different SQL for the same model+filter). There is no
   cross-SDK/BP-049 contract on these bytes. Issue #1606 ADDS a DB-instance
   identity segment to this keyspace (directly after the model name) so two
   DataFlow instances at DIFFERENT databases never collide on the same query
   cache key (cross-DB cache bleed). This tripwire RE-PINS the new query bytes
   (with the DB-identity segment) as a py-local tripwire — a query-key drift is
   a loud, deliberate py-side event, NOT a cross-SDK lockstep.

Tier: 1 (Unit — no external dependencies).
"""

import hashlib

from dataflow.cache.key_generator import (
    CacheKeyGenerator,
    hash_database_identity,
)
from dataflow.cache.memory_cache import InMemoryCache

# --- Pinned EXPRESS v2 keyspace bytes (Rust-pinned — change ONLY with the ---
# --- kailash-rs v2->v3 cross-SDK LOCKSTEP) ---------------------------------
EXPRESS_KEY_WITH_TENANT = "dataflow:v2:tenant-a:User:list:6a3d3c8c"
EXPRESS_KEY_NO_TENANT = "dataflow:v2:User:list"

# --- Pinned QUERY keyspace bytes (py-local tripwire; NOT Rust-pinned) ------
# A fixed DB-identity segment for byte-pinning. In production this is the
# short sha256 of the credential-stripped DSN (hash_database_identity).
_FIXED_DBID = "dbidfixd"
# New-shape (post-#1606) query keys: the DB-identity segment sits directly
# after the model name, BEFORE the version segment.
QUERY_KEY_DEFAULT_PREFIX = "dataflow:User:dbidfixd:v2:2f5a5fc5af648187"
QUERY_KEY_PROD_PREFIX = "dataflow:query:User:dbidfixd:v2:2f5a5fc5af648187"
# Old-shape (pre-#1606, no DB-identity) — still produced when db_identity is
# unset; kept pinned for backward-compat + invalidation coverage.
QUERY_KEY_NO_DBID = "dataflow:User:v2:2f5a5fc5af648187"

_QUERY_SQL = "SELECT * FROM users WHERE active = $1"
_QUERY_PARAMS = [True]


# =========================================================================
# EXPRESS keyspace — RUST-PINNED. These assertions guard the cross-SDK
# byte-for-byte contract and MUST stay loud + unchanged by #1606.
# =========================================================================
def test_express_key_v2_bytes_are_pinned():
    """generate_express_key emits the exact v2 byte string for fixed inputs."""
    gen = CacheKeyGenerator()

    # With tenant + params: dataflow:v2:<tenant>:<model>:<op>:<hash>
    key = gen.generate_express_key(
        "User", "list", {"active": True}, tenant_id="tenant-a"
    )
    assert key == EXPRESS_KEY_WITH_TENANT, (
        f"v2 Express keyspace drifted: got {key!r}. Changing these bytes is a "
        f"cross-SDK LOCKSTEP (#1606/rs#1713) — bump v2->v3 in BOTH SDKs, not one."
    )

    # Without tenant/params the trailing hash segment is absent.
    assert gen.generate_express_key("User", "list") == EXPRESS_KEY_NO_TENANT

    # Version segment is fixed at v2 (the pinned cross-SDK keyspace).
    assert key.startswith("dataflow:v2:")


def test_express_key_excludes_db_identity_segment():
    """The #1606 DB-identity segment MUST NOT enter the Rust-pinned express key.

    Even when the generator is constructed WITH a db_identity (as it always is
    in production, from engine.py), generate_express_key emits byte-identical
    output to a generator without one. This is the structural guard that the
    #1606 change stayed in the query keyspace and never touched the express
    (Rust-pinned) keyspace.
    """
    gen_with_dbid = CacheKeyGenerator(db_identity=_FIXED_DBID)
    gen_without_dbid = CacheKeyGenerator()

    key_with = gen_with_dbid.generate_express_key(
        "User", "list", {"active": True}, tenant_id="tenant-a"
    )
    key_without = gen_without_dbid.generate_express_key(
        "User", "list", {"active": True}, tenant_id="tenant-a"
    )
    assert key_with == key_without == EXPRESS_KEY_WITH_TENANT, (
        "db_identity leaked into the Rust-pinned express keyspace: "
        f"with={key_with!r} without={key_without!r}. The #1606 segment is "
        "query-keyspace-ONLY; express is a cross-SDK byte contract."
    )


# =========================================================================
# QUERY keyspace — py-local tripwire. RE-PINS the new #1606 bytes (with the
# DB-identity segment) + a production-prefix assertion. De-bundled from the
# cross-SDK lockstep claim (this keyspace diverges cross-SDK by construction).
# =========================================================================
def test_query_key_new_bytes_with_db_identity_are_pinned():
    """generate_key emits the exact new-shape (DB-identity) byte string.

    The DB-identity segment sits directly after the model name:
    ``dataflow:<model>:<db_identity>:v2:<sql+params hash>``. The trailing
    SQL+params hash is unchanged from the pre-#1606 shape (only the segment
    is inserted).
    """
    gen = CacheKeyGenerator(db_identity=_FIXED_DBID)
    key = gen.generate_key("User", _QUERY_SQL, _QUERY_PARAMS)
    assert key == QUERY_KEY_DEFAULT_PREFIX, (
        f"#1606 query keyspace drifted: got {key!r}. This keyspace is py-local "
        f"(NOT Rust-pinned) — a drift is a deliberate py-side event, but pin it "
        f"here so the change is loud."
    )
    # DB-identity segment is present between model and version.
    assert ":dbidfixd:v2:" in key


def test_query_key_production_prefix_shape_is_pinned():
    """Production uses the ``dataflow:query`` prefix (config.py) — pin that shape.

    The prior tripwire only pinned the default (``dataflow``) prefix; production
    keys carry the ``dataflow:query`` prefix (confirmed list_node_integration.py
    ``_setup_invalidation_patterns`` docstring). Both the prefix AND the new
    DB-identity segment are asserted here.
    """
    gen = CacheKeyGenerator(prefix="dataflow:query", db_identity=_FIXED_DBID)
    key = gen.generate_key("User", _QUERY_SQL, _QUERY_PARAMS)
    assert (
        key == QUERY_KEY_PROD_PREFIX
    ), f"#1606 production-prefix query keyspace drifted: got {key!r}."
    # Production key is anchored at the ``dataflow:query:User:`` prefix so the
    # model-anchored invalidation sweep (`{prefix}:{model}:*`) matches it.
    assert key.startswith("dataflow:query:User:")


def test_query_key_without_db_identity_keeps_old_shape():
    """A generator with no db_identity keeps the pre-#1606 shape (backward-compat).

    The DB-identity segment is opt-in — absent for a generator constructed
    without one (e.g. a no-database DataFlow). This guards that #1606 did not
    change bytes for the unset path.
    """
    gen = CacheKeyGenerator()
    assert gen.generate_key("User", _QUERY_SQL, _QUERY_PARAMS) == QUERY_KEY_NO_DBID


# =========================================================================
# Invariant coverage (deterministic, no infra).
# =========================================================================
def test_db_identity_is_credential_free_and_differs_per_database():
    """hash_database_identity strips credentials and separates databases (#1606).

    Invariant 2 (no credentials in any key segment) + invariant 3 (two DBs ->
    different identity).
    """
    url_a = "postgresql://alice:s3cret@db-a.example.com:5432/prod"
    url_b = "postgresql://alice:s3cret@db-b.example.com:5432/prod"

    dbid_a = hash_database_identity(url_a)
    dbid_b = hash_database_identity(url_b)

    # Invariant 3: different databases -> different identity segments.
    assert dbid_a != dbid_b
    # Short, opaque fingerprint (8 hex chars).
    assert len(dbid_a) == 8 and all(c in "0123456789abcdef" for c in dbid_a)

    # Invariant 2: NO credential byte enters the identity input. The digest is
    # over the credential-stripped mask (host+port+dbname only), so the raw
    # user/password can never be a pre-image of the segment.
    from kailash.utils.url_credentials import mask_url

    masked = mask_url(url_a)
    assert "alice" not in masked and "s3cret" not in masked
    assert dbid_a == hashlib.sha256(masked.encode("utf-8")).hexdigest()[:8]

    # Falsy URL -> no segment (old-shape fallback).
    assert hash_database_identity(None) is None
    assert hash_database_identity("") is None


def test_same_database_same_query_key_no_over_invalidation():
    """Invariant 5: same DB + same query -> SAME key (cache still hits)."""
    url = "postgresql://u:p@db.example.com:5432/prod"
    dbid = hash_database_identity(url)

    gen1 = CacheKeyGenerator(prefix="dataflow:query", db_identity=dbid)
    gen2 = CacheKeyGenerator(prefix="dataflow:query", db_identity=dbid)

    key1 = gen1.generate_key("User", _QUERY_SQL, _QUERY_PARAMS)
    key2 = gen2.generate_key("User", _QUERY_SQL, _QUERY_PARAMS)
    assert key1 == key2, "same DB + same query must yield the same cache key"

    # A DIFFERENT database yields a DIFFERENT key for the identical query.
    other = CacheKeyGenerator(
        prefix="dataflow:query",
        db_identity=hash_database_identity(
            "postgresql://u:p@other-db.example.com:5432/prod"
        ),
    )
    assert other.generate_key("User", _QUERY_SQL, _QUERY_PARAMS) != key1


async def test_invalidate_model_matches_v2_express_key():
    """invalidate_model's ``:{tenant}:{model}:`` adjacency still deletes the key.

    Pins the substring contract at memory_cache.py::invalidate_model — a
    tenant-scoped invalidation matches the current v2 Express key layout
    (``dataflow:v2:tenant-a:User:list:...`` contains ``:tenant-a:User:``).
    """
    cache = InMemoryCache()
    await cache.set(EXPRESS_KEY_WITH_TENANT, {"rows": []})

    # Tenant-scoped invalidation for a DIFFERENT tenant MUST NOT match.
    assert await cache.invalidate_model("User", tenant_id="tenant-b") == 0
    assert await cache.get(EXPRESS_KEY_WITH_TENANT) is not None

    # The owning tenant's invalidation MUST delete exactly this key.
    removed = await cache.invalidate_model("User", tenant_id="tenant-a")
    assert removed == 1
    assert await cache.get(EXPRESS_KEY_WITH_TENANT) is None


async def test_invalidation_sweeps_both_old_and_new_query_shapes():
    """Invariant 4: model-scoped invalidation sweeps old- AND new-shape query keys.

    The ``:{model}:`` segment matcher (invalidate_model) and the
    ``{prefix}:{model}:*`` clear_pattern both anchor at the model and use a
    trailing match, so they cover the version segment AND the #1606 DB-identity
    segment — no stale query-cache entry survives under the old shape.
    """
    cache = InMemoryCache()
    await cache.set(QUERY_KEY_NO_DBID, {"rows": ["old-shape"]})  # pre-#1606
    await cache.set(QUERY_KEY_DEFAULT_PREFIX, {"rows": ["new-shape"]})  # post-#1606

    # Model-scoped invalidate_model (no tenant) sweeps BOTH via ``:User:``.
    removed = await cache.invalidate_model("User")
    assert removed == 2
    assert await cache.get(QUERY_KEY_NO_DBID) is None
    assert await cache.get(QUERY_KEY_DEFAULT_PREFIX) is None

    # The producer-side clear_pattern sweep (`{prefix}:{model}:*`) also covers
    # both shapes — re-seed and clear via the pattern the CacheInvalidator uses.
    await cache.set(QUERY_KEY_NO_DBID, {"rows": ["old-shape"]})
    await cache.set(QUERY_KEY_DEFAULT_PREFIX, {"rows": ["new-shape"]})
    cleared = await cache.clear_pattern("dataflow:User:*")
    assert cleared == 2
    assert await cache.get(QUERY_KEY_NO_DBID) is None
    assert await cache.get(QUERY_KEY_DEFAULT_PREFIX) is None
