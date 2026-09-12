"""
Unit tests for ParallelBatchStrategy.

Tests cover:
- execute_batch processes all inputs
- Results in same order as inputs
- max_concurrent limits concurrency
- Batch of 10, 100, 1000 items
- Error in one item doesn't stop others
- Semaphore correctly limits concurrent execution
- Empty batch returns empty list
- Single item batch
- Verify concurrent execution (observed overlap, plus relative timing)
- Different max_concurrent values (1, 5, 50)

A note on the concurrency tests. ``execute_batch`` owns its per-item work: it
issues its own ``asyncio.sleep``, and never calls the agent it is handed. So a
test cannot observe overlap by instrumenting the agent -- it has to intercept
that sleep, which is what ``_ConcurrencyProbe`` below does. Concurrency is then
asserted as *observed overlap*, a property of the scheduling, instead of as a
wall-clock deadline, which on a loaded machine measures the machine.
"""

import asyncio
import time

import pytest

from kaizen.strategies import parallel_batch
from kaizen.strategies.parallel_batch import ParallelBatchStrategy


class MockAgent:
    """Mock agent for testing."""

    async def execute(self, inputs):
        """Mock execution."""
        return {"response": f"Processed: {inputs.get('prompt', 'input')}"}


#: Per-item delay injected by the probe. Large enough that a serialised batch is
#: unambiguously slower than a concurrent one, small enough to keep the file fast.
PROBE_DELAY = 0.02

#: Wall-clock is sampled more than once and the *fastest* sample is used. Load can
#: only push a measurement up, never down, so a minimum is the closest thing to an
#: unloaded reading that a busy machine can give.
TIMING_SAMPLES = 3


class _ConcurrencyProbe:
    """Stand-in for the ``asyncio`` module as seen from inside ``parallel_batch``.

    Only ``sleep`` is intercepted, to count how many items are in flight at the
    same time; everything else the module reaches for (``gather``) is forwarded
    to the real ``asyncio`` untouched.
    """

    def __init__(self, delay: float):
        self.delay = delay
        self.in_flight = 0
        self.max_overlap = 0
        self.sleep_calls = 0

    def __getattr__(self, name):
        # Reached only for attributes this class does not define.
        return getattr(asyncio, name)

    async def sleep(self, _duration):
        self.sleep_calls += 1
        self.in_flight += 1
        self.max_overlap = max(self.max_overlap, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.in_flight -= 1


async def _run_instrumented_batch(
    monkeypatch, max_concurrent, n_items, delay=PROBE_DELAY
):
    """Run the real ``execute_batch`` with its per-item sleep instrumented.

    Returns ``(probe, results, elapsed)``.
    """
    probe = _ConcurrencyProbe(delay)
    monkeypatch.setattr(parallel_batch, "asyncio", probe)
    try:
        strategy = ParallelBatchStrategy(max_concurrent=max_concurrent)
        batch = [{"prompt": f"Q{i}"} for i in range(n_items)]
        start = time.perf_counter()
        results = await strategy.execute_batch(MockAgent(), batch)
        elapsed = time.perf_counter() - start
    finally:
        monkeypatch.undo()

    # Establish that the instrument fired before reading anything off it: a green
    # from a probe that was never reached would report on nothing at all.
    assert probe.sleep_calls == n_items, (
        f"probe did not intercept the strategy's per-item work: saw "
        f"{probe.sleep_calls} sleeps for {n_items} items"
    )
    return probe, results, elapsed


@pytest.mark.asyncio
async def test_execute_batch_processes_all_inputs():
    """Test that execute_batch processes all inputs."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 10, f"Expected 10 results, got {len(results)}"
    assert all("response" in r for r in results), "All results should have response"


@pytest.mark.asyncio
async def test_results_in_same_order_as_inputs():
    """Test that results are in same order as inputs."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(20)]

    results = await strategy.execute_batch(agent, batch)

    # Verify order by checking the prompts in responses
    for i, result in enumerate(results):
        expected_response = f"Processed: Q{i}"
        assert (
            result["response"] == expected_response
        ), f"Result {i} out of order: expected '{expected_response}', got '{result['response']}'"


@pytest.mark.asyncio
async def test_max_concurrent_limits_concurrency(monkeypatch):
    """max_concurrent caps how many items are in flight at once.

    Asserted on observed overlap, not on a clock. An *upper* bound on concurrency
    cannot be established with a clock at all: a busy machine makes every run
    slower, which is indistinguishable from the semaphore doing its job, so the
    previous ``elapsed >= 0.015`` passed whether or not anything was limited.
    """
    probe, results, _ = await _run_instrumented_batch(
        monkeypatch, max_concurrent=5, n_items=10
    )

    assert len(results) == 10
    assert probe.max_overlap == 5, (
        f"max_concurrent=5 should hold exactly 5 items in flight at the peak, "
        f"observed {probe.max_overlap}"
    )


@pytest.mark.asyncio
async def test_batch_of_10_items():
    """Test batch of 10 items."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 10
    assert all(r["batch"] is True for r in results)


@pytest.mark.asyncio
async def test_batch_of_100_items():
    """Test batch of 100 items."""
    strategy = ParallelBatchStrategy(max_concurrent=20)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(100)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 100
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_batch_of_1000_items():
    """Test batch of 1000 items."""
    strategy = ParallelBatchStrategy(max_concurrent=50)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(1000)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 1000
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_empty_batch_returns_empty_list():
    """Test that empty batch returns empty list."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = []

    results = await strategy.execute_batch(agent, batch)

    assert results == [], "Empty batch should return empty list"


@pytest.mark.asyncio
async def test_single_item_batch():
    """Test single item batch."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": "Q0"}]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 1
    assert results[0]["response"] == "Processed: Q0"


@pytest.mark.asyncio
async def test_verify_concurrent_execution_timing(monkeypatch):
    """Batch items genuinely overlap, and that overlap buys wall-clock time.

    Two assertions, for two different reasons:

    * ``max_overlap`` is a property of the scheduling, so it reports on
      concurrency however loaded the machine is. This is the load-bearing one.
    * the wall-clock check stays, but only as an end-to-end guard that the
      overlap actually converts into throughput, and it is *relative*: the
      sequential cost of the same work is measured in the same test, on the same
      machine, rather than compared against a constant. The constant this test
      used to carry (``< 0.05s``) was measured at 0.109s against a correct,
      fully concurrent implementation purely because the box was busy -- and at
      0.115s against a deliberately serialised one, so its verdict did not
      distinguish the two.
    """
    n = 10
    seq_probes, seq_times = [], []
    conc_probes, conc_times = [], []

    for _ in range(TIMING_SAMPLES):
        probe, results, elapsed = await _run_instrumented_batch(monkeypatch, 1, n)
        assert len(results) == n
        seq_probes.append(probe)
        seq_times.append(elapsed)

        probe, results, elapsed = await _run_instrumented_batch(monkeypatch, n, n)
        assert len(results) == n
        conc_probes.append(probe)
        conc_times.append(elapsed)

    assert all(p.max_overlap == 1 for p in seq_probes), (
        f"max_concurrent=1 must serialise; observed peaks "
        f"{[p.max_overlap for p in seq_probes]}"
    )
    assert all(p.max_overlap == n for p in conc_probes), (
        f"max_concurrent={n} must hold all {n} items in flight; observed peaks "
        f"{[p.max_overlap for p in conc_probes]}"
    )

    fastest_seq = min(seq_times)
    fastest_conc = min(conc_times)
    assert fastest_conc < fastest_seq / 2, (
        f"concurrent execution should be materially faster than the sequential "
        f"cost of the same batch: fastest concurrent {fastest_conc:.3f}s vs "
        f"fastest sequential {fastest_seq:.3f}s over {TIMING_SAMPLES} samples"
    )


@pytest.mark.asyncio
async def test_max_concurrent_1(monkeypatch):
    """max_concurrent=1 serialises the batch.

    Overlap is the direct assertion. The wall-clock floor is kept because it is
    safe under load in a way a ceiling never is -- load can only push elapsed up
    -- and because it is derived from the delay this test itself injects, rather
    than from a hard-coded restatement of a constant that lives in the
    production module and can drift away from the test without either noticing.
    """
    n = 5
    probe, results, elapsed = await _run_instrumented_batch(monkeypatch, 1, n)

    assert len(results) == n
    assert probe.max_overlap == 1, (
        f"max_concurrent=1 should never hold more than one item in flight, "
        f"observed {probe.max_overlap}"
    )
    assert elapsed >= n * PROBE_DELAY * 0.9, (
        f"{n} serialised sleeps of {PROBE_DELAY}s cannot finish in "
        f"{elapsed:.3f}s -- the batch was not serialised"
    )


@pytest.mark.asyncio
async def test_max_concurrent_5():
    """Test max_concurrent=5."""
    strategy = ParallelBatchStrategy(max_concurrent=5)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(15)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 15
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_max_concurrent_50():
    """Test max_concurrent=50 with large batch."""
    strategy = ParallelBatchStrategy(max_concurrent=50)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(100)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 100
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_execute_single_input_compatibility():
    """Test execute method for single input (BaseAgent compatibility)."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    result = await strategy.execute(agent, inputs)

    assert "response" in result
    assert "batch" in result
    assert result["batch"] is False  # Single execution, not batch


@pytest.mark.asyncio
async def test_batch_flag_set_correctly():
    """Test that batch flag is set correctly in results."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()

    # Single execution
    single_result = await strategy.execute(agent, {"prompt": "test"})
    assert single_result["batch"] is False

    # Batch execution
    batch_results = await strategy.execute_batch(agent, [{"prompt": "test"}])
    assert all(r["batch"] is True for r in batch_results)


@pytest.mark.asyncio
async def test_semaphore_limits_actual_concurrency(monkeypatch):
    """The semaphore inside the real execute_batch caps in-flight work.

    This test used to subclass the strategy and reimplement ``execute_batch`` in
    its own body, so what it measured was the test's copy of the logic: the
    production semaphore could have been deleted outright and it would still
    have passed. It now drives the shipped code path.
    """
    probe, results, _ = await _run_instrumented_batch(
        monkeypatch, max_concurrent=3, n_items=10
    )

    assert len(results) == 10
    assert (
        probe.max_overlap == 3
    ), f"max concurrent should be exactly 3, was {probe.max_overlap}"


@pytest.mark.asyncio
async def test_different_batch_sizes_maintain_order():
    """Test that order is maintained across different batch sizes."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()

    for batch_size in [5, 20, 50, 100]:
        batch = [{"prompt": f"Q{i}"} for i in range(batch_size)]
        results = await strategy.execute_batch(agent, batch)

        assert len(results) == batch_size
        for i, result in enumerate(results):
            expected = f"Processed: Q{i}"
            assert (
                result["response"] == expected
            ), f"Batch size {batch_size}, index {i}: expected '{expected}', got '{result['response']}'"
