"""Edge cleanup must preserve pool identity across event-loop owners."""

import asyncio
import tempfile

import pytest

from kailash.utils.resource_manager import AsyncResourcePool
from kailash.workflow.edge_infrastructure import EdgeInfrastructure


@pytest.fixture
def infrastructure():
    previous = EdgeInfrastructure._instance
    EdgeInfrastructure._instance = None
    instance = EdgeInfrastructure()
    try:
        yield instance
    finally:
        EdgeInfrastructure._instance = previous


def test_cleanup_retains_foreign_owner_pool_and_aggregate_cap(infrastructure):
    owner = asyncio.new_event_loop()
    other = asyncio.new_event_loop()
    closed_on = []

    async def close(resource):
        closed_on.append(asyncio.get_running_loop())
        resource.close()

    pool = AsyncResourcePool(
        tempfile.TemporaryFile, max_size=1, timeout=0.01, cleanup=close
    )
    infrastructure._connection_pools["shared"] = pool

    async def borrow_and_return():
        async with infrastructure.get_connection_pool("shared").acquire() as resource:
            return resource

    async def verify_foreign_cap():
        with pytest.raises(TimeoutError):
            async with infrastructure.get_connection_pool("shared").acquire():
                pytest.fail("another loop must not bypass the aggregate cap")

    try:
        original = owner.run_until_complete(borrow_and_return())
        other.run_until_complete(infrastructure.cleanup())
        assert infrastructure.get_connection_pool("shared") is pool
        assert not original.closed
        other.run_until_complete(verify_foreign_cap())
        assert owner.run_until_complete(borrow_and_return()) is original
        owner.run_until_complete(infrastructure.cleanup())
        assert original.closed
        assert closed_on == [owner]
        assert infrastructure.get_metrics()["connection_pools"] == 1
        replacement = other.run_until_complete(borrow_and_return())
        assert replacement is not original and not replacement.closed
        other.run_until_complete(infrastructure.cleanup())
        assert replacement.closed
        assert closed_on == [owner, other]
    finally:
        owner.run_until_complete(pool.cleanup_all())
        other.run_until_complete(pool.cleanup_all())
        owner.close()
        other.close()


@pytest.mark.asyncio
async def test_cleanup_retires_borrowed_resource_without_replacing_pool(infrastructure):
    pool = AsyncResourcePool(
        tempfile.TemporaryFile, cleanup=lambda resource: resource.close()
    )
    infrastructure._connection_pools["borrowed"] = pool
    async with pool.acquire() as resource:
        await infrastructure.cleanup()
        assert infrastructure.get_connection_pool("borrowed") is pool
        assert not resource.closed
    assert resource.closed
    assert pool._created_count == 0
    async with pool.acquire() as replacement:
        assert replacement is not resource
    await infrastructure.cleanup()
    assert replacement.closed
