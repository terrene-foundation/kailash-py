"""Credential and endpoint boundaries cannot alias provider client ownership."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from kaizen.nodes.ai.client_cache import BYOKClientCache

PAIRS = [
    (
        ("k", "https://one.invalid/|https://two.invalid/"),
        ("k|https://one.invalid/", "https://two.invalid/"),
    ),
    (("key|part", "endpoint"), ("key", "part|endpoint")),
    ((None, "endpoint"), ("", "endpoint")),
    (("key", None), ("key", "")),
    (("key\x00one", "two"), ("key", "one\x00two")),
    (("key雪", "endpoint"), ("key", "雪endpoint")),
]


class Client:
    def __init__(self, identity):
        self.identity = identity
        self.close_count = 0

    def close(self):
        self.close_count += 1


@pytest.mark.parametrize("first,second", PAIRS)
def test_distinct_credential_endpoint_pairs_have_distinct_live_clients(first, second):
    cache = BYOKClientCache()
    calls = []

    def create(identity):
        calls.append(identity)
        return Client(identity)

    one = cache.get_or_create(*first, lambda: create(first))
    two = cache.get_or_create(*second, lambda: create(second))
    assert one is not two
    assert one.identity == first and two.identity == second
    assert cache.get_or_create(*first, lambda: create(first)) is one
    assert cache.get_or_create(*second, lambda: create(second)) is two
    assert calls == [first, second]
    assert len(cache) == 2
    cache.clear()
    assert one.close_count == two.close_count == 1


@pytest.mark.parametrize("same_identity", [False, True])
def test_concurrent_factory_publication_preserves_identity_and_closes_loser(
    same_identity,
):
    cache = BYOKClientCache()
    first, second = PAIRS[0]
    if same_identity:
        second = first
    admitted = Barrier(2)
    created = []

    def request(identity):
        def factory():
            client = Client(identity)
            created.append(client)
            admitted.wait(timeout=5)
            return client

        return cache.get_or_create(*identity, factory)

    with ThreadPoolExecutor(max_workers=2) as workers:
        one_future = workers.submit(request, first)
        two_future = workers.submit(request, second)
        one, two = one_future.result(timeout=10), two_future.result(timeout=10)
    assert len(created) == 2
    assert (one is two) is same_identity
    assert one.identity == first and two.identity == second
    assert sum(c.close_count for c in created) == (1 if same_identity else 0)
    assert len(cache) == (1 if same_identity else 2)
    cache.clear()
    assert all(c.close_count == 1 for c in created)


def test_cache_indexes_and_repr_do_not_retain_plaintext_credentials():
    credential = "PRIVATE-CREDENTIAL-CANARY-not-a-real-secret"
    endpoint = "https://tenant.invalid/private"
    cache = BYOKClientCache()
    client = cache.get_or_create(
        credential, endpoint, lambda: Client((credential, endpoint))
    )
    keys = list(cache._cache)
    assert len(keys) == 1
    assert credential not in repr(keys) + repr(cache)
    assert endpoint not in repr(keys) + repr(cache)
    assert len(keys[0]) == 64 and all(c in "0123456789abcdef" for c in keys[0])
    assert cache.get_or_create(credential, endpoint, lambda: None) is client
    cache.clear()
    assert client.close_count == 1
