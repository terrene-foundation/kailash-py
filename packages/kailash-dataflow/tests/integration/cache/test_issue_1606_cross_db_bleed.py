"""#1606 cross-DB query-cache bleed — Tier 2 (real Redis + two real SQLite DBs).

Reproduces (RED) and proves closed (GREEN) the cross-database cache bleed:
two DataFlow instances pointed at DIFFERENT databases, sharing ONE Redis cache
backend, running the SAME model+filter, must NOT read each other's cached query
rows.

Root cause: the QUERY cache key hashes a normalized SQL string + params, which
is identical for the same model+filter regardless of which database the
instance targets. Without a DB-instance identity segment, both instances
compute the SAME key on a shared Redis, so instance B reads instance A's cached
rows. Fix (#1606): a credential-free DB-identity segment in the query keyspace
(``dataflow:<model>:<db_identity>:v2:<hash>``).

NO MOCKING (testing.md Tier 2): real Redis + two real file-backed SQLite
databases; every assertion is a read-back through the real cache path.
"""

import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter
from dataflow.cache.invalidation import CacheInvalidator
from dataflow.cache.key_generator import (
    CacheKeyGenerator,
    express_db_instance_fingerprint,
    hash_database_identity,
)
from dataflow.cache.list_node_integration import ListNodeCacheIntegration
from dataflow.cache.redis_manager import CacheConfig, RedisCacheManager

# Same fixed model+SQL+params for BOTH instances — this is what makes the
# query hash collide across databases (the bug's precondition).
_MODEL = "User"
_SQL = "SELECT id, name FROM users WHERE active = ?"
_PARAMS = [1]


def _redis_config_or_skip() -> CacheConfig:
    """Return a CacheConfig for a reachable real Redis, or skip the test."""
    import redis as _redis_sync

    for host, port, db in (("localhost", 6380, 1), ("localhost", 6379, 1)):
        try:
            client = _redis_sync.Redis(host=host, port=port, db=db, socket_timeout=0.5)
            client.ping()
            client.close()
            return CacheConfig(host=host, port=port, db=db)
        except Exception:
            continue
    pytest.skip("No reachable Redis instance on localhost:6380 or :6379")


def _make_sqlite_db(tmp: Path, name: str, row_name: str) -> str:
    """Create a real file-backed SQLite DB with one users row; return its URL."""
    db_path = tmp / f"{name}.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, active INTEGER)"
        )
        conn.execute("INSERT INTO users (name, active) VALUES (?, 1)", (row_name,))
        conn.commit()
    finally:
        conn.close()
    return f"sqlite:///{db_path}"


def _executor_for(db_url: str, source_tag: str):
    """Return a sync executor_func that runs the real SELECT against `db_url`."""

    db_path = db_url[len("sqlite:///") :]

    def _run():
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute("SELECT id, name FROM users WHERE active = 1")
            rows = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
        finally:
            conn.close()
        # source_db lets the test detect a bleed: a cached row from the WRONG
        # instance carries the other instance's source tag.
        return {"rows": rows, "source_db": source_tag}

    return _run


def _integration(cache_manager, db_url, *, with_db_identity: bool, prefix: str):
    """Build a query-cache integration sharing `cache_manager`.

    with_db_identity=False reproduces the PRE-#1606 keyspace (the bug);
    with_db_identity=True is the POST-#1606 fixed keyspace.
    """
    db_identity = hash_database_identity(db_url) if with_db_identity else None
    key_gen = CacheKeyGenerator(prefix=prefix, db_identity=db_identity)
    invalidator = CacheInvalidator(cache_manager)
    return ListNodeCacheIntegration(cache_manager, key_gen, invalidator)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pre_fix_shape_reproduces_cross_db_bleed():
    """RED: without the DB-identity segment, instance B reads instance A's rows."""
    config = _redis_config_or_skip()
    # Unique prefix so this test's keys are isolated + cleanable on shared Redis.
    prefix = f"df1606test:{uuid4().hex}"

    cache_manager = AsyncRedisCacheAdapter(RedisCacheManager(config))
    try:
        with tempfile.TemporaryDirectory() as d_a, tempfile.TemporaryDirectory() as d_b:
            url_a = _make_sqlite_db(Path(d_a), "dba", "alice-from-db-A")
            url_b = _make_sqlite_db(Path(d_b), "dbb", "bob-from-db-B")

            integ_a = _integration(
                cache_manager, url_a, with_db_identity=False, prefix=prefix
            )
            integ_b = _integration(
                cache_manager, url_b, with_db_identity=False, prefix=prefix
            )

            # Sanity: pre-fix, the two instances compute the IDENTICAL key.
            key_a = integ_a.key_generator.generate_key(_MODEL, _SQL, _PARAMS)
            key_b = integ_b.key_generator.generate_key(_MODEL, _SQL, _PARAMS)
            assert key_a == key_b, "pre-fix precondition: keys must collide"

            # A caches its own rows.
            res_a = await integ_a.execute_with_cache(
                _MODEL, _SQL, _PARAMS, _executor_for(url_a, "A")
            )
            assert res_a["_cache"]["hit"] is False
            assert res_a["source_db"] == "A"

            # B runs the SAME query -> HIT on A's cached entry -> BLEED.
            res_b = await integ_b.execute_with_cache(
                _MODEL, _SQL, _PARAMS, _executor_for(url_b, "B")
            )
            assert res_b["_cache"]["hit"] is True, "pre-fix: expected a cache HIT"
            assert res_b["source_db"] == "A", (
                "BLEED reproduced: instance B read instance A's cached rows "
                f"({res_b['rows']!r})"
            )
            assert res_b["rows"] == [{"id": 1, "name": "alice-from-db-A"}]
    finally:
        _cleanup_redis(config, prefix)
        await cache_manager.close_async()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_fix_db_identity_closes_cross_db_bleed():
    """GREEN: with the DB-identity segment, B reads ITS OWN rows (no bleed)."""
    config = _redis_config_or_skip()
    prefix = f"df1606test:{uuid4().hex}"

    cache_manager = AsyncRedisCacheAdapter(RedisCacheManager(config))
    try:
        with tempfile.TemporaryDirectory() as d_a, tempfile.TemporaryDirectory() as d_b:
            url_a = _make_sqlite_db(Path(d_a), "dba", "alice-from-db-A")
            url_b = _make_sqlite_db(Path(d_b), "dbb", "bob-from-db-B")

            integ_a = _integration(
                cache_manager, url_a, with_db_identity=True, prefix=prefix
            )
            integ_b = _integration(
                cache_manager, url_b, with_db_identity=True, prefix=prefix
            )

            # Post-fix: the two instances compute DIFFERENT keys (the fix).
            key_a = integ_a.key_generator.generate_key(_MODEL, _SQL, _PARAMS)
            key_b = integ_b.key_generator.generate_key(_MODEL, _SQL, _PARAMS)
            assert key_a != key_b, "post-fix: keys MUST differ per database"

            # A caches its own rows.
            res_a = await integ_a.execute_with_cache(
                _MODEL, _SQL, _PARAMS, _executor_for(url_a, "A")
            )
            assert res_a["_cache"]["hit"] is False
            assert res_a["source_db"] == "A"

            # B runs the SAME query -> MISS (own key) -> reads ITS OWN DB.
            res_b = await integ_b.execute_with_cache(
                _MODEL, _SQL, _PARAMS, _executor_for(url_b, "B")
            )
            assert res_b["_cache"]["hit"] is False, "post-fix: B must MISS, not bleed"
            assert res_b["source_db"] == "B"
            assert res_b["rows"] == [
                {"id": 1, "name": "bob-from-db-B"}
            ], "no bleed: B reads its own database's rows"

            # Read-back through the shared Redis: each key holds ITS OWN data,
            # and A's cached entry is untouched by B.
            back_a = await cache_manager.get(key_a)
            back_b = await cache_manager.get(key_b)
            assert back_a["rows"] == [{"id": 1, "name": "alice-from-db-A"}]
            assert back_b["rows"] == [{"id": 1, "name": "bob-from-db-B"}]

            # Invariant 5 restated on the real backend: a SECOND B read HITS its
            # own key (cache still works — no over-invalidation from the fix).
            res_b2 = await integ_b.execute_with_cache(
                _MODEL, _SQL, _PARAMS, _executor_for(url_b, "B")
            )
            assert res_b2["_cache"]["hit"] is True
            assert res_b2["source_db"] == "B"
    finally:
        _cleanup_redis(config, prefix)
        await cache_manager.close_async()


# ---------------------------------------------------------------------------
# EXPRESS keyspace (#1606 v2->v3) cross-DB bleed — the HOT path.
#
# The Express path (read/list/find_one/count) has no SQL: keys come from
# ``generate_express_key`` (``dataflow:v3:<db_instance>:<tenant>:<model>:<op>:
# <hash>``). Without the ``db_instance`` segment (pre-v3), two DataFlow
# instances at DIFFERENT databases compute the IDENTICAL express key for the
# same tenant+model+op+params and bleed across each other on a shared Redis.
# The v3 db-instance segment closes it. Real Redis, real key generation,
# real set/get read-back — NO MOCKING.
# ---------------------------------------------------------------------------
_EXPRESS_OP = "list"
_EXPRESS_TENANT = "tenant-a"
_EXPRESS_PARAMS = {"active": True}


def _express_gen(db_url: str, *, with_db_instance: bool, prefix: str):
    """Build an express key generator; with_db_instance=False = pre-v3 shape."""
    inst = express_db_instance_fingerprint(db_url) if with_db_instance else None
    return CacheKeyGenerator(prefix=prefix, express_db_instance=inst)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_express_pre_v3_shape_reproduces_cross_db_bleed():
    """RED: without the db-instance segment, two DBs share ONE express key -> bleed."""
    config = _redis_config_or_skip()
    prefix = f"df1606expr:{uuid4().hex}"

    cache_manager = AsyncRedisCacheAdapter(RedisCacheManager(config))
    try:
        gen_a = _express_gen(
            "sqlite:///tmp/db_a.db", with_db_instance=False, prefix=prefix
        )
        gen_b = _express_gen(
            "sqlite:///tmp/db_b.db", with_db_instance=False, prefix=prefix
        )

        key_a = gen_a.generate_express_key(
            _MODEL, _EXPRESS_OP, _EXPRESS_PARAMS, tenant_id=_EXPRESS_TENANT
        )
        key_b = gen_b.generate_express_key(
            _MODEL, _EXPRESS_OP, _EXPRESS_PARAMS, tenant_id=_EXPRESS_TENANT
        )
        # Pre-v3 precondition: no db-instance -> identical key across databases.
        assert key_a == key_b, "pre-v3 precondition: express keys must collide"

        # A caches its rows; B reads the SAME key -> HIT on A's data -> BLEED.
        await cache_manager.set(key_a, {"rows": [{"id": 1, "src": "A"}]}, ttl=60)
        bled = await cache_manager.get(key_b)
        assert (
            bled is not None and bled["rows"][0]["src"] == "A"
        ), "BLEED reproduced: B read A's cached express rows via the shared key"
    finally:
        _cleanup_redis(config, prefix)
        await cache_manager.close_async()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_express_v3_db_instance_closes_cross_db_bleed():
    """GREEN: the v3 db-instance segment gives each database a DISTINCT express key."""
    config = _redis_config_or_skip()
    prefix = f"df1606expr:{uuid4().hex}"

    cache_manager = AsyncRedisCacheAdapter(RedisCacheManager(config))
    try:
        with tempfile.TemporaryDirectory() as d_a, tempfile.TemporaryDirectory() as d_b:
            url_a = _make_sqlite_db(Path(d_a), "dba", "alice-from-db-A")
            url_b = _make_sqlite_db(Path(d_b), "dbb", "bob-from-db-B")

            gen_a = _express_gen(url_a, with_db_instance=True, prefix=prefix)
            gen_b = _express_gen(url_b, with_db_instance=True, prefix=prefix)

            key_a = gen_a.generate_express_key(
                _MODEL, _EXPRESS_OP, _EXPRESS_PARAMS, tenant_id=_EXPRESS_TENANT
            )
            key_b = gen_b.generate_express_key(
                _MODEL, _EXPRESS_OP, _EXPRESS_PARAMS, tenant_id=_EXPRESS_TENANT
            )
            # Post-v3: distinct db-instance -> distinct express keys (the fix).
            assert key_a != key_b, "post-v3: express keys MUST differ per database"
            assert gen_a.express_db_instance != gen_b.express_db_instance

            # A caches ITS rows under ITS key; B's key is a MISS (no bleed).
            await cache_manager.set(
                key_a, {"rows": [{"id": 1, "name": "alice-from-db-A"}]}, ttl=60
            )
            miss_b = await cache_manager.get(key_b)
            assert (
                miss_b is None
            ), "post-v3: B's express key MUST miss, not bleed A's data"

            # B caches its OWN rows; both keys coexist on the shared Redis.
            await cache_manager.set(
                key_b, {"rows": [{"id": 1, "name": "bob-from-db-B"}]}, ttl=60
            )
            back_a = await cache_manager.get(key_a)
            back_b = await cache_manager.get(key_b)
            assert back_a is not None and back_a["rows"][0]["name"] == "alice-from-db-A"
            assert back_b is not None and back_b["rows"][0]["name"] == "bob-from-db-B"
    finally:
        _cleanup_redis(config, prefix)
        await cache_manager.close_async()


def _cleanup_redis(config: CacheConfig, prefix: str) -> None:
    """Delete this test's keys from the shared Redis (no flushdb — shared infra)."""
    import redis as _redis_sync

    client = _redis_sync.Redis(
        host=config.host, port=config.port, db=config.db, decode_responses=True
    )
    try:
        keys = list(client.scan_iter(match=f"{prefix}*"))
        if keys:
            client.delete(*keys)
    finally:
        client.close()
