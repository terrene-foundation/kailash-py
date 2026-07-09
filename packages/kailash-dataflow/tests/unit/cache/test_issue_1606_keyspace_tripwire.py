"""#1606 cross-SDK cache-keyspace TRIPWIRE.

This module pins the EXACT byte string of the current ``v2`` cache keyspace
emitted by ``CacheKeyGenerator`` (both the Express key and the query key) plus
the ``:{tenant}:{model}:`` substring adjacency that
``InMemoryCache.invalidate_model`` relies on.

WHY A TRIPWIRE (not the fix): issue #1606 asks for a DB-instance segment in the
key + a keyspace bump ``v2 -> v3``. That bump is a CROSS-SDK LOCKSTEP — the
``v2`` Express keyspace at ``src/dataflow/cache/key_generator.py`` is pinned to
kailash-rs (the Rust SDK, ``v3.19.0`` cross-SDK contract, BP-049) and MUST NOT
be changed unilaterally in one SDK. Changing ANY byte pinned in this file is
therefore a loud, deliberate event: update it ONLY together with the paired
Rust SDK keyspace change (the ``v2 -> v3`` lockstep). A silent drift here would
diverge the two SDKs' cache keys and break cross-SDK invalidation.

Tier: 1 (Unit — no external dependencies).
"""

from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.memory_cache import InMemoryCache

# --- Pinned v2 keyspace bytes (change ONLY with the Rust SDK v2->v3 lockstep) ---
EXPRESS_KEY_WITH_TENANT = "dataflow:v2:tenant-a:User:list:6a3d3c8c"
EXPRESS_KEY_NO_TENANT = "dataflow:v2:User:list"
QUERY_KEY = "dataflow:User:v2:2f5a5fc5af648187"


def test_express_key_v2_bytes_are_pinned():
    """generate_express_key emits the exact v2 byte string for fixed inputs."""
    gen = CacheKeyGenerator()

    # With tenant + params: dataflow:v2:<tenant>:<model>:<op>:<hash>
    key = gen.generate_express_key(
        "User", "list", {"active": True}, tenant_id="tenant-a"
    )
    assert key == EXPRESS_KEY_WITH_TENANT, (
        f"v2 Express keyspace drifted: got {key!r}. Changing these bytes is a "
        f"cross-SDK LOCKSTEP (#1606) — bump v2->v3 in BOTH SDKs, not one."
    )

    # Without tenant/params the trailing hash segment is absent.
    assert gen.generate_express_key("User", "list") == EXPRESS_KEY_NO_TENANT

    # Version segment is fixed at v2 (the pinned cross-SDK keyspace).
    assert key.startswith("dataflow:v2:")


def test_query_key_v2_bytes_are_pinned():
    """generate_key emits the exact v2 byte string for a fixed SQL+params."""
    gen = CacheKeyGenerator()
    key = gen.generate_key("User", "SELECT * FROM users WHERE active = $1", [True])
    assert key == QUERY_KEY, (
        f"v2 query keyspace drifted: got {key!r}. Changing these bytes is a "
        f"cross-SDK LOCKSTEP (#1606) — bump v2->v3 in BOTH SDKs, not one."
    )
    # Query-key shape places the model BEFORE the version: dataflow:<model>:v2:<hash>
    assert ":v2:" in key


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
