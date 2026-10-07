"""Resource management utilities for the Kailash SDK.

This module provides context managers and utilities for efficient resource
management across the SDK, ensuring proper cleanup and preventing memory leaks.
"""

import asyncio
import contextvars
import inspect
import logging
import threading
import weakref
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from itertools import count
from types import CoroutineType
from typing import Any, Callable, Dict, Generic, Optional, Set, TypeVar

from kailash.utils.async_types import _is_native_awaitable
from kailash.utils.secure_logging import (
    safe_exception_frames,
    safe_log_field,
    safe_type_name,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _cleanup_observe(handle, operation, *args, **kwargs):
    """Use native completion state, or a checked truthful opaque protocol."""
    native_mro = type.__dict__["__mro__"].__get__(type(handle))
    if any(base is asyncio.Future for base in native_mro):
        return operation(handle, *args, **kwargs)

    from kailash.nodes.base import _get_execution_attribute

    method = _get_execution_attribute(handle, operation.__name__, strict=True)
    if not callable(method):
        raise TypeError(f"Cleanup owner must expose {operation.__name__}")
    result = method(*args, **kwargs)
    if operation is asyncio.Future.done and result is not True and result is not False:
        raise TypeError("Cleanup owner done must return bool")
    return result


def _cleanup_admit(handle, loop):
    """Refuse dependent native waits before observing or registering completion."""
    if handle is asyncio.current_task():
        raise RuntimeError("Cleanup cannot await its owner task")
    native_mro = type.__dict__["__mro__"].__get__(type(handle))
    if (
        any(base is asyncio.Future for base in native_mro)
        and not asyncio.Future.done(handle)
        and asyncio.Future.get_loop(handle) is not loop
    ):
        raise RuntimeError("Cleanup cannot await pending work from another loop")


def _cleanup_owner_pending(owner: Any) -> bool:
    """Observe ancestry in a running loop; opaque owners retain their protocol."""
    if owner is asyncio.current_task() and owner is not None:
        return True
    return not _cleanup_observe(owner, asyncio.Future.done)


async def _await_cleanup(awaitable, *, on_cancel=None):
    """Drain cleanup, optionally observing the first caller cancellation once.

    ``on_cancel`` is a synchronous recorder for owners that order callback
    controls with caller cancellation. It cannot replace the saved cancellation
    or interrupt resource drain. Omission preserves caller-priority behavior.
    """
    if awaitable is asyncio.current_task():
        raise RuntimeError("Cleanup cannot await its owner task")
    # Keep existing native Future/Task custody. For other returned awaitables,
    # hand task machinery a native coroutine: ensure_future's duck typing reads
    # instance __class__ before it ever starts the owned cleanup.
    owner = None
    entered = False
    loop = asyncio.get_running_loop()

    async def close_unstarted():
        first_error = None
        if owner is not None and not entered:
            for coroutine in (owner, awaitable):
                coroutine_type = type(coroutine)
                if coroutine_type is CoroutineType:
                    try:
                        coroutine.close()
                    except BaseException as error:
                        if first_error is None:
                            first_error = error
            awaitable_type = type(awaitable)
            if awaitable_type is CoroutineType:
                try:
                    # A primed native input can cancel this caller while being
                    # closed. Finish that close before returning its first error
                    # or the earlier admission/task failure.
                    await asyncio.sleep(0)
                except BaseException as error:
                    if first_error is None:
                        first_error = error
        return first_error

    native_mro = type.__dict__["__mro__"].__get__(type(awaitable))
    if any(base is asyncio.Future for base in native_mro):
        task = awaitable
    else:

        async def finish_owned():
            nonlocal entered
            entered = True
            return await awaitable

        owner = finish_owned()
        try:
            task = asyncio.create_task(owner)
        except BaseException:
            await close_unstarted()
            raise
    try:
        _cleanup_admit(task, loop)
    except BaseException:
        await close_unstarted()
        raise

    def observe(operation, *args):
        return _cleanup_observe(task, operation, *args)

    cancellation = None
    while not observe(asyncio.Future.done):
        completed = asyncio.Future(loop=loop)

        def finished(_task, completed=completed):
            if not asyncio.Future.done(completed):
                asyncio.Future.set_result(completed, None)

        observe(asyncio.Future.add_done_callback, finished)
        try:
            # Cancellation affects only this completion notification, never the
            # resource cleanup task. Its exception is retrieved exactly once.
            await completed
        except asyncio.CancelledError as error:
            if cancellation is None:
                cancellation = error
                if on_cancel is not None:
                    try:
                        on_cancel(error)
                    except BaseException:
                        # The observer is secondary to the saved cancellation.
                        pass
                    try:
                        # Consume observer cancel-and-return while still owning
                        # the wait; later caller cancellations remain secondary.
                        await asyncio.sleep(0)
                    except BaseException:
                        pass
        finally:
            observe(asyncio.Future.remove_done_callback, finished)
    # Task acceptance alone does not consume the nested native coroutine: a
    # factory may cancel the wrapper before its first step. Release that custody
    # after settlement, without invoking custom close methods or replaying work.
    unstarted_error = await close_unstarted()
    try:
        result = observe(asyncio.Future.result)
    except BaseException as exc:
        if cancellation is not None:
            try:
                logger.error(
                    "Error cleaning up cancelled resource: %s", safe_type_name(exc)
                )
            except BaseException:
                # A diagnostic sink cannot replace the already-owned cancellation.
                pass
            try:
                # Consume a sink's synchronous self-cancel before the caller can
                # catch the primary and continue using this task.
                await asyncio.sleep(0)
            except BaseException:
                pass
            if cancellation is exc:
                raise cancellation
            raise cancellation from exc
        raise
    if cancellation is not None:
        raise cancellation
    if unstarted_error is not None:
        raise unstarted_error
    return result


_CLEANUP_CONTROL_ORDER = count()


_CLEANUP_GRAPH_LOCK = threading.RLock()


_CLEANUP_OBSERVATION = contextvars.ContextVar("cleanup_observation", default=())


_CLEANUP_CANCELLATION = contextvars.ContextVar("cleanup_cancellation", default=())


class _CleanupOutcome:
    """Retain ordered errors and task-classified controls across owned edges."""

    def __init__(self):
        self.control = None
        self._terminal = None
        self.children = []
        self._links = []

    def record(self, error):
        terminal = _cleanup_control(error) is not None
        with _CLEANUP_GRAPH_LOCK:
            self._record_preclassified(error, terminal)

    def _record_preclassified(self, error, terminal):
        event = (next(_CLEANUP_CONTROL_ORDER), error)
        self._retain(event, event if terminal else None)

    @staticmethod
    def _check(outcome):
        outcome_type = type(outcome)
        if outcome_type is not _CleanupOutcome:
            raise TypeError("Cleanup links require a native cleanup outcome")

    def _walk(self, controls_only=False):
        active, visited = set(), set()
        stack = [(self, controls_only, False)]
        while stack:
            node, projected, leaving = stack.pop()
            self._check(node)
            key = (id(node), projected)
            if leaving:
                active.remove(id(node))
                continue
            if id(node) in active:
                raise RuntimeError("Cleanup outcome dependency cycle")
            if key in visited:
                continue
            visited.add(key)
            active.add(id(node))
            yield node, projected
            stack.append((node, projected, True))
            stack.extend((child, projected, False) for child in node.children)
            stack.extend(
                (child, projected or filtered, False)
                for _, child, filtered in node._links
            )

    def _snapshot(self, controls_only=False):
        first = terminal = None
        for node, projected in self._walk(controls_only):
            event = node._terminal if projected else node.control
            if event is not None and (first is None or event[0] < first[0]):
                first = event
            control = node._terminal
            if control is not None and (terminal is None or control[0] < terminal[0]):
                terminal = control
        return first, terminal

    def first(self, controls_only=False):
        with _CLEANUP_GRAPH_LOCK:
            return self._snapshot(controls_only)[0]

    def error(self):
        event = self.first()
        return event[1] if event is not None else None

    def _retain(self, event, terminal):
        if event is not None and (self.control is None or event[0] < self.control[0]):
            self.control = event
        if terminal is not None and (
            self._terminal is None or terminal[0] < self._terminal[0]
        ):
            self._terminal = terminal

    def link(self, child, *, controls_only=False):
        """Return a detacher for this exact edge, retaining original ordering."""
        self._check(child)
        token = object()
        with _CLEANUP_GRAPH_LOCK:
            if any(node is self for node, _ in child._walk()):
                raise RuntimeError("Cleanup outcome dependency cycle")
            self._links.append((token, child, controls_only))

        def detach():
            with _CLEANUP_GRAPH_LOCK:
                for index, (owned, _, _) in enumerate(self._links):
                    if owned is token:
                        self._retain(child.first(controls_only), child.first(True))
                        del self._links[index]
                        break

        return detach

    def compact(self):
        """Drop completed graphs without recreating their first event."""
        with _CLEANUP_GRAPH_LOCK:
            first, terminal = self.first(), self.first(True)
            self._retain(first, terminal)
            self.children.clear()
            self._links.clear()


class _CleanupScope:
    def __init__(self, outcome):
        self.outcome = outcome
        self.task = asyncio.current_task()
        self.active = True


def _current_cleanup_scope():
    try:
        task = asyncio.current_task()
    except RuntimeError:
        return None
    for scope in reversed(_CLEANUP_OBSERVATION.get()):
        if scope.active and scope.task is task:
            return scope
    return None


def _current_cleanup_outcome():
    scope = _current_cleanup_scope()
    return scope.outcome if scope is not None else None


def _record_cleanup_primary(error):
    """Declare a body failure before isolating its secondary cleanup work."""
    outcome = _current_cleanup_outcome()
    if error is not None and outcome is not None:
        outcome.record(error)


class _CleanupCancellationScope:
    def __init__(self, token):
        self.token = token
        self.task = asyncio.current_task()
        self.active = True


class _cleanup_cancel_scope:
    """Exclude one task-local deadline without touching escaping error metadata."""

    def __init__(self, token):
        self.token = token

    def __enter__(self):
        self.policy = _CleanupCancellationScope(self.token)
        self.reset = _CLEANUP_CANCELLATION.set(
            (*_CLEANUP_CANCELLATION.get(), self.policy)
        )

    def __exit__(self, exc_type, error, traceback):
        self.policy.active = False
        _CLEANUP_CANCELLATION.reset(self.reset)
        return False


class _CleanupObservation:
    """Prepared cancellation metadata; operations below run under graph custody."""

    def __init__(self, error):
        from kailash.runtime.resource_manager import _exception_is

        self.error = error
        self.terminal = _cleanup_control(error) is not None
        self.event = self.control = None
        self.excluded = False
        if _exception_is(error, asyncio.CancelledError):
            values = BaseException.args.__get__(error)
            task = asyncio.current_task()
            self.excluded = len(values) == 1 and any(
                policy.active and policy.task is task and values[0] is policy.token
                for policy in _CLEANUP_CANCELLATION.get()
            )

    def snapshot(self, outcome, *, controls_only=False):
        if outcome is not None:
            self.event, self.control = outcome._snapshot(controls_only)
        return self.event[1] if self.event is not None else None

    def publish(self, expected_parent=None):
        parent = _current_cleanup_outcome()
        if parent is None or (
            expected_parent is not None and parent is not expected_parent
        ):
            return
        if self.event is not None:
            parent._retain(self.event, self.control)
        elif not self.excluded:
            self.record(parent)

    def record(self, outcome):
        outcome._record_preclassified(self.error, self.terminal)


@contextmanager
def _cleanup_observation(error):
    # Classification can acquire the retry-scope lock and lazily import types.
    # Resolve it before taking the graph lock; the transaction is native data only.
    observation = _CleanupObservation(error)
    with _CLEANUP_GRAPH_LOCK:
        yield observation


def _publish_cleanup_cancel(error, *, observed=None):
    """Publish actual callback cancellation, excluding private deadline tokens."""
    from kailash.runtime.resource_manager import _exception_is

    outcome = _current_cleanup_outcome()
    if outcome is None:
        return
    if observed is not None:
        outcome.record(observed)
        return
    if _exception_is(error, asyncio.CancelledError):
        values = BaseException.args.__get__(error)
        if len(values) == 1 and any(
            policy.active
            and policy.task is asyncio.current_task()
            and values[0] is policy.token
            for policy in _CLEANUP_CANCELLATION.get()
        ):
            return
    outcome.record(error)


class _cleanup_owner:
    """Bind actual-task publication without touching escaping error metadata.

    Inherited scopes reject recursive waits but grant no publication authority.
    Quiet boundaries project controls classified at their original record site.
    """

    def __init__(self, outcome, *, controls_only=False):
        self.outcome = outcome
        self.controls_only = controls_only
        self.detach = None
        self.joined = False

    def __enter__(self):
        parent = _current_cleanup_scope()
        if parent is not None and parent.outcome is self.outcome:
            self.joined = True
            return parent
        if (
            self.outcome is not None
            and parent is not None
            and parent.outcome is not None
        ):
            self.detach = parent.outcome.link(
                self.outcome, controls_only=self.controls_only
            )
        self.scope = _CleanupScope(self.outcome)
        self.token = _CLEANUP_OBSERVATION.set((*_CLEANUP_OBSERVATION.get(), self.scope))
        return self.scope

    def __exit__(self, exc_type, error, traceback):
        if not self.joined:
            self.scope.active = False
            _CLEANUP_OBSERVATION.reset(self.token)
            try:
                if self.outcome is not None:
                    self.outcome.compact()
            finally:
                if self.detach is not None:
                    self.detach()
        return False


async def _await_cleanup_outcome(awaitable, outcome):
    """Drain a shared owner while keeping external cancellation private."""
    native_mro = type.__dict__["__mro__"].__get__(type(awaitable))
    completed = any(
        base is asyncio.Future for base in native_mro
    ) and asyncio.Future.done(awaitable)
    try:
        for scope in _CLEANUP_OBSERVATION.get():
            if scope.active and scope.outcome is outcome and not completed:
                raise RuntimeError("Cleanup cannot await its own active outcome")
        parent = _current_cleanup_outcome()
        detach = (
            parent.link(outcome)
            if parent is not None and parent is not outcome
            else None
        )
    except BaseException:
        awaitable_type = type(awaitable)
        if awaitable_type is CoroutineType:
            try:
                awaitable.close()
            except BaseException:
                # Admission failed first; native close cannot replace that error.
                pass
            try:
                await asyncio.sleep(0)
            except BaseException:
                # Native close may cancel-and-return/raise on this same task.
                # Consume its pending request before exposing the first rejection.
                pass
        raise
    first_terminal = None

    def cancelled(error):
        nonlocal first_terminal
        if first_terminal is None:
            with _cleanup_observation(error) as observation:
                observed = observation.snapshot(outcome)
                first_terminal = error if observed is None else observed
                if parent is not None:
                    observation.publish(parent)

    try:
        try:
            result = await _await_cleanup(awaitable, on_cancel=cancelled)
        except BaseException as error:
            if first_terminal is None:
                observed = outcome.error()
                first_terminal = error if observed is None else observed
            raise first_terminal
        if first_terminal is not None:
            raise first_terminal
        return result
    finally:
        if detach is not None:
            detach()


def _cleanup_control(error):
    """Return a terminal failure without consulting exception instance metadata."""
    from kailash.runtime.resource_manager import (
        _exception_is,
        _raise_if_execution_control,
    )

    if not _exception_is(error, Exception):
        return error
    try:
        _raise_if_execution_control(error)
    except BaseException as control:
        return control
    return None


def _report_cleanup_failure(
    error, primary=None, resource_type="resource", *, reporter=None
):
    """Keep body/control ownership even when the diagnostic sink fails."""
    terminal = _cleanup_control(error) if primary is None else None
    report = logger if reporter is None else reporter
    try:
        report.error(
            "Error cleaning up %s: %s",
            safe_log_field(resource_type),
            safe_exception_frames(error),
        )
    except BaseException as diagnostic:
        if primary is None and terminal is None:
            terminal = _cleanup_control(diagnostic)
    if terminal is not None:
        raise terminal


async def _report_cleanup_failure_async(
    error, primary=None, resource_type="resource", *, reporter=None, on_control=None
):
    """Own diagnostic self-cancellation before the asynchronous caller resumes."""
    terminal = None
    try:
        _report_cleanup_failure(error, primary, resource_type, reporter=reporter)
    except BaseException as caught:
        terminal = caught
        if on_control is not None:
            on_control(terminal)
    try:
        await asyncio.sleep(0)
    except BaseException as caught:
        if primary is None and terminal is None:
            terminal = caught
            if on_control is not None:
                on_control(terminal)
    if terminal is not None:
        raise terminal


async def _run_resource_cleanup(
    callback,
    resource,
    primary=None,
    resource_type="resource",
    *,
    outcome=None,
    already_owned=False,
    on_admitted=None,
    reporter=None,
):
    """Own callback, diagnostics and pending cancellation in the same task."""
    _record_cleanup_primary(primary)
    first_terminal = primary
    stage = _CleanupOutcome() if primary is None else None
    detach = (
        outcome.link(stage, controls_only=True)
        if outcome is not None and stage is not None
        else None
    )

    parent = _current_cleanup_outcome()
    parent_link = (
        parent.link(stage, controls_only=True)
        if parent is not None and stage is not None
        else None
    )

    def record(error):
        nonlocal first_terminal
        with _cleanup_observation(error) as observation:
            observed = observation.snapshot(stage, controls_only=True)
            if stage is not None:
                observation.record(stage)
            if first_terminal is None:
                first_terminal = error if observed is None else observed

    def cancelled(error):
        nonlocal first_terminal
        with _cleanup_observation(error) as observation:
            observed = observation.snapshot(stage, controls_only=True)
            if first_terminal is None:
                first_terminal = error if observed is None else observed
            if primary is None and parent is not None:
                observation.publish(parent)

    async def drain():
        with _cleanup_owner(stage, controls_only=True):
            if on_admitted is not None:
                on_admitted()
            error = None
            try:
                result = callback(resource)
                try:
                    # Retain a returned finalizer before consuming a callback's
                    # pending self-cancel; it must still enter and settle.
                    await asyncio.sleep(0)
                except BaseException as caught:
                    record(caught)
                    error = caught
                if _is_native_awaitable(result):
                    native_mro = type.__dict__["__mro__"].__get__(type(result))
                    if any(base is asyncio.Future for base in native_mro):
                        # Accepted native work keeps its completion custody even
                        # if the callback owner is cancelled during the wait.
                        await _await_cleanup(result, on_cancel=record)
                    else:
                        # Raw coroutines retain the callback's Task/Context.
                        await result
            except BaseException as caught:
                error = caught
                terminal = _cleanup_control(error)
                if terminal is not None:
                    record(terminal)
            try:
                await asyncio.sleep(0)
            except BaseException as caught:
                record(caught)
                if error is None:
                    error = caught
            if error is not None:
                try:
                    await _report_cleanup_failure_async(
                        error,
                        first_terminal,
                        resource_type,
                        reporter=reporter,
                        on_control=record,
                    )
                except BaseException as caught:
                    record(caught)

    try:
        try:
            if already_owned:
                await drain()
            else:
                await _await_cleanup(drain(), on_cancel=cancelled)
        except BaseException as caught:
            cancelled(caught)
        if primary is None and first_terminal is not None:
            raise first_terminal
    finally:
        if parent_link is not None:
            parent_link()
        if detach is not None:
            detach()


class ResourcePool(Generic[T]):
    """Generic resource pool for connection pooling and resource reuse.

    This class provides a thread-safe pool for managing expensive resources
    like database connections, HTTP clients, etc.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 10,
        timeout: float = 30.0,
        cleanup: Optional[Callable[[T], None]] = None,
    ):
        """Initialize the resource pool.

        Args:
            factory: Function to create new resources
            max_size: Maximum pool size
            timeout: Timeout for acquiring resources
            cleanup: Optional cleanup function for resources
        """
        self._factory = factory
        self._max_size = max_size
        self._timeout = timeout
        self._cleanup = cleanup

        self._pool: list[T] = []
        self._in_use: Dict[int, T] = {}
        self._retired: Set[int] = set()
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_size)
        self._created_count = 0

    @contextmanager
    def acquire(self):
        """Acquire a resource from the pool.

        Yields:
            Resource instance

        Raises:
            TimeoutError: If resource cannot be acquired within timeout
        """
        if not self._semaphore.acquire(timeout=self._timeout):
            raise TimeoutError(f"Failed to acquire resource within {self._timeout}s")

        resource = None
        try:
            with self._lock:
                # Try to get from pool
                if self._pool:
                    resource = self._pool.pop()
                else:
                    # Create new resource if under limit
                    if self._created_count < self._max_size:
                        resource = self._factory()
                        self._created_count += 1
                    else:
                        raise RuntimeError("Pool exhausted")

                self._in_use[id(resource)] = resource

            yield resource

        finally:
            if resource is not None:
                with self._lock:
                    self._in_use.pop(id(resource), None)
                    if id(resource) in self._retired:
                        self._retired.discard(id(resource))
                        self._dispose(resource)
                    else:
                        self._pool.append(resource)
            self._semaphore.release()

    def _dispose(self, resource):
        try:
            if self._cleanup:
                self._cleanup(resource)
        except Exception as exc:
            logger.error("Error cleaning up resource: %s", exc)
        finally:
            self._created_count -= 1

    def cleanup_all(self):
        """Close idle resources and retire active leases when returned."""
        with self._lock:
            self._retired.update(self._in_use)
            for resource in self._pool:
                self._dispose(resource)
            self._pool.clear()


class _AsyncPoolState:
    """Resources belonging to one event loop; guarded by the pool mutex."""

    def __init__(self):
        self.idle = []
        self.borrowed = {}
        self.retired = set()
        self.generation = 0
        self.creating = 0


class AsyncResourcePool(Generic[T]):
    """Reuse async resources only on their owning loop, with one aggregate cap.

    Owners must await ``cleanup_all()`` before closing their event loop. Cleanup
    affects that loop only; borrowed resources remain usable until lease return.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 10,
        timeout: float = 30.0,
        cleanup: Optional[Callable[[T], Any]] = None,
    ):
        """Initialize a pool with a maximum resource count across all loops."""
        if max_size < 1:
            raise ValueError("max_size must be positive")
        self._factory = factory
        self._max_size = max_size
        self._timeout = timeout
        self._cleanup = cleanup
        self._states = {}
        self._mutex = threading.Lock()
        self._waiters = set()
        self._created_count = 0

    def _state(self, loop):
        return self._states.setdefault(loop, _AsyncPoolState())

    def _prune(self, loop, state):
        if not state.idle and not state.borrowed and not state.creating:
            if self._states.get(loop) is state:
                del self._states[loop]

    @property
    def _pool(self):
        with self._mutex:
            return self._state(asyncio.get_running_loop()).idle

    @property
    def _in_use(self):
        with self._mutex:
            return self._state(asyncio.get_running_loop()).borrowed

    @staticmethod
    def _wake(waiter):
        if not waiter.done():
            waiter.set_result(None)

    def _notify(self):
        # Called under the mutex. Futures belong to their respective loops.
        for waiter in self._waiters:
            loop = waiter.get_loop()
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self._wake, waiter)
                except RuntimeError:
                    logger.debug("Resource waiter loop closed during notification")

    async def _dispose(self, resource):
        try:
            if self._cleanup:
                result = self._cleanup(resource)
                if inspect.isawaitable(result):
                    await _await_cleanup(result)
        except Exception as exc:
            logger.error("Error cleaning up resource: %s", exc)
        finally:
            with self._mutex:
                self._created_count -= 1
                self._notify()

    @asynccontextmanager
    async def acquire(self):
        """Acquire on the current loop, timing out if aggregate capacity is full."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        while True:
            with self._mutex:
                state = self._state(loop)
                generation = state.generation
                if state.idle:
                    resource = state.idle.pop()
                    state.borrowed[id(resource)] = resource
                    create = False
                    break
                if self._created_count < self._max_size:
                    self._created_count += 1
                    state.creating += 1
                    create = True
                    break
                waiter = loop.create_future()
                self._waiters.add(waiter)
            try:
                await asyncio.wait_for(waiter, max(0, deadline - loop.time()))
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Failed to acquire resource within {self._timeout}s"
                ) from None
            finally:
                with self._mutex:
                    self._waiters.discard(waiter)
                    self._prune(loop, state)
        if create:
            try:
                resource = self._factory()
                if inspect.isawaitable(resource):
                    resource = await resource
            except BaseException:
                with self._mutex:
                    self._created_count -= 1
                    state.creating -= 1
                    self._prune(loop, state)
                    self._notify()
                raise
            with self._mutex:
                state.creating -= 1
                state.borrowed[id(resource)] = resource
                if state.generation != generation:
                    state.retired.add(id(resource))
        try:
            yield resource
        finally:
            with self._mutex:
                state.borrowed.pop(id(resource), None)
                retire = id(resource) in state.retired
                state.retired.discard(id(resource))
                if not retire:
                    state.idle.append(resource)
                self._notify()
            if retire:
                try:
                    await self._dispose(resource)
                finally:
                    with self._mutex:
                        self._prune(loop, state)

    async def cleanup_all(self):
        """Close current-loop idle resources; retire its outstanding leases.

        Resources borrowed by another caller are closed when returned, never
        while that caller is using them. Other event loops are untouched.
        """
        loop = asyncio.get_running_loop()
        with self._mutex:
            state = self._states.get(loop)
            if state is None:
                return
            state.generation += 1
            state.retired.update(state.borrowed)
            idle, state.idle = state.idle, []
        try:
            if idle:
                closing = asyncio.gather(
                    *(self._dispose(resource) for resource in idle)
                )
                await _await_cleanup(closing)
        finally:
            with self._mutex:
                self._prune(loop, state)


class ResourceTracker:
    """Track and manage resources across the SDK to prevent leaks."""

    def __init__(self):
        self._resources: Dict[str, weakref.WeakSet] = defaultdict(weakref.WeakSet)
        self._metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = threading.Lock()

    def register(self, resource_type: str, resource: Any):
        """Register a resource for tracking.

        Args:
            resource_type: Type/category of resource
            resource: Resource instance to track
        """
        with self._lock:
            self._resources[resource_type].add(resource)

            # Update metrics
            if resource_type not in self._metrics:
                self._metrics[resource_type] = {
                    "created": 0,
                    "active": 0,
                    "peak": 0,
                    "last_created": None,
                }

            self._metrics[resource_type]["created"] += 1
            self._metrics[resource_type]["active"] = len(self._resources[resource_type])
            self._metrics[resource_type]["peak"] = max(
                self._metrics[resource_type]["peak"],
                self._metrics[resource_type]["active"],
            )
            self._metrics[resource_type]["last_created"] = datetime.now(UTC)

    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get current resource metrics.

        Returns:
            Dictionary of metrics by resource type
        """
        with self._lock:
            # Update active counts
            for resource_type in self._metrics:
                self._metrics[resource_type]["active"] = len(
                    self._resources[resource_type]
                )

            return dict(self._metrics)

    def get_active_resources(
        self, resource_type: Optional[str] = None
    ) -> Dict[str, int]:
        """Get count of active resources.

        Args:
            resource_type: Optional filter by type

        Returns:
            Dictionary of resource type to active count
        """
        with self._lock:
            if resource_type:
                return {resource_type: len(self._resources.get(resource_type, set()))}
            else:
                return {
                    rtype: len(resources)
                    for rtype, resources in self._resources.items()
                }


# Global resource tracker instance
_resource_tracker = ResourceTracker()


def get_resource_tracker() -> ResourceTracker:
    """Get the global resource tracker instance."""
    return _resource_tracker


@contextmanager
def managed_resource(
    resource_type: str, resource: Any, cleanup: Optional[Callable] = None
):
    """Context manager for tracking and cleaning up resources.

    Args:
        resource_type: Type/category of resource
        resource: Resource instance
        cleanup: Optional cleanup function

    Yields:
        The resource instance
    """
    _resource_tracker.register(resource_type, resource)

    try:
        yield resource
    finally:
        if cleanup:
            try:
                cleanup(resource)
            except Exception as e:
                logger.error(f"Error cleaning up {resource_type}: {e}")


@asynccontextmanager
async def async_managed_resource(
    resource_type: str, resource: Any, cleanup: Optional[Callable] = None
):
    """Async context manager for tracking and cleaning up resources.

    Args:
        resource_type: Type/category of resource
        resource: Resource instance
        cleanup: Optional async cleanup function

    Yields:
        The resource instance
    """
    _resource_tracker.register(resource_type, resource)

    primary = None
    try:
        yield resource
    except BaseException as error:
        primary = error
        raise
    finally:
        if cleanup is not None:
            await _run_resource_cleanup(cleanup, resource, primary, resource_type)


class ConcurrencyLimiter:
    """Limit concurrent operations to prevent resource exhaustion."""

    def __init__(self, max_concurrent: int = 10):
        """Initialize the concurrency limiter.

        Args:
            max_concurrent: Maximum concurrent operations
        """
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active = 0
        self._peak = 0
        self._lock = threading.Lock()

    @contextmanager
    def limit(self):
        """Context manager to limit concurrency."""
        self._semaphore.acquire()
        with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)

        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
            self._semaphore.release()

    def get_stats(self) -> Dict[str, int]:
        """Get concurrency statistics."""
        with self._lock:
            return {"active": self._active, "peak": self._peak}


class AsyncConcurrencyLimiter:
    """Async version of ConcurrencyLimiter."""

    def __init__(self, max_concurrent: int = 10):
        """Initialize the async concurrency limiter.

        Args:
            max_concurrent: Maximum concurrent operations
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._peak = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def limit(self):
        """Async context manager to limit concurrency."""
        await self._semaphore.acquire()
        async with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)

        try:
            yield
        finally:
            async with self._lock:
                self._active -= 1
            self._semaphore.release()

    async def get_stats(self) -> Dict[str, int]:
        """Get concurrency statistics."""
        async with self._lock:
            return {"active": self._active, "peak": self._peak}


class _CleanupInvocation:
    """Retain one native worker and its original returned-work coordinator.

    The consumer must retain this request before calling ``start``. ``wait`` can
    report uncertain submission or unclassified worker settlement while the
    coordinator remains owned here; only ``drained`` permits releasing custody.
    Callback completion alone does not settle a returned awaitable. Rejected,
    unentered requests may be replaced; all others must be observed, not replayed.
    """

    def __init__(self, callback, args=()):
        from concurrent.futures import Future

        if not callable(callback):
            raise TypeError("Cleanup invocation callback must be callable")
        if type(args) is not tuple:
            raise TypeError("Cleanup invocation arguments must be a tuple")
        self.callback = callback
        self.args = args
        self.outcome = _CleanupOutcome()
        self.coordinator = None
        self.worker = None
        self.worker_thread = None
        self.submission = "not_submitted"
        self.unclassified = False
        self.callback_entered = False
        self.callback_completed = Future()
        self.completion = Future()
        self.observation = Future()
        self.returned_started = False
        self.returned_succeeded = False
        self.deadline_requested = False
        self._deadline_sent = False
        self.deadline_token = object()
        self._lock = threading.RLock()
        self._ready = Future()
        self._started = False
        self._entered = False
        self._gate = None
        self._runner = None
        self._returned = None
        self._returned_future = False
        self._value = None

    @property
    def drained(self):
        return self.completion.done()

    @property
    def retry_safe(self):
        return self.drained and self.submission == "not_submitted"

    @property
    def unresolved(self):
        return (
            self.submission == "uncertain" or self.unclassified
        ) and not self.drained

    def _notify_observers(self):
        # This notification conveys no completion or retry authority. Existing
        # observers must wake even if they joined before the worker failed.
        with self._lock:
            if not self.observation.done():
                self.observation.set_result(None)

    def _record(self, error):
        from kailash.runtime.resource_manager import _exception_is

        # A copied worker context has no deadline authority. This exclusion
        # requires the actual coordinator and a deadline requested on this owner.
        if self.deadline_requested and _exception_is(error, asyncio.CancelledError):
            try:
                actual_owner = asyncio.current_task() is self.coordinator
            except RuntimeError:
                actual_owner = False
            values = BaseException.args.__get__(error)
            if actual_owner and len(values) == 1 and values[0] is self.deadline_token:
                return
        self.outcome.record(error)

    def _invoke(self):
        with self._lock:
            self.worker_thread = threading.current_thread()
            self.callback_entered = True
        try:
            result = (True, self.callback(*self.args))
        except BaseException as error:
            # Explicit worker ownership permits private publication before either
            # the native acknowledgement or executor Future notifies its observer.
            self._record(error)
            result = (False, error)
        self.callback_completed.set_result(result)

    def start(self):
        """Publish a gated coordinator once; never retry an existing request."""
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._started:
                return
            try:
                self._started = True
                self._gate = asyncio.Future(loop=loop)
                self._runner = self._run()
                self.coordinator = loop.create_task(self._runner)
                _cleanup_admit(self.coordinator, loop)
                if _cleanup_observe(self.coordinator, asyncio.Future.done):
                    loop.call_soon(self._finished, self.coordinator)
                else:
                    _cleanup_observe(
                        self.coordinator,
                        asyncio.Future.add_done_callback,
                        self._finished,
                    )
            except BaseException as error:
                self._record(error)
                if self._runner is not None:
                    self._runner.close()
                self._ready.set_result(None)
                self.completion.set_result((None, self.outcome.error()))
                self._notify_observers()
                raise
            asyncio.Future.set_result(self._gate, None)

    def _finished(self, task):
        try:
            _cleanup_observe(task, asyncio.Future.result)
        except BaseException as error:
            self._record(error)
        if not self._entered:
            # Accepted then cancelled before its first step: no submission began.
            self._runner.close()
        if not self._ready.done():
            self._ready.set_result(None)
        if not self.completion.done():
            self.completion.set_result((self._value, self.outcome.error()))
        self._notify_observers()

    async def _checkpoint(self):
        try:
            await asyncio.sleep(0)
        except BaseException as error:
            self._record(error)

    async def _run(self):
        await self._gate
        self._entered = True
        with _cleanup_owner(self.outcome), _cleanup_cancel_scope(self.deadline_token):
            try:
                # Set uncertainty BEFORE the call. An exception after this point
                # does not prove whether a native worker was accepted or started.
                self.submission = "uncertain"
                try:
                    self.worker = asyncio.get_running_loop().run_in_executor(
                        None, contextvars.copy_context().run, self._invoke
                    )
                except BaseException as error:
                    self._record(error)
                else:
                    self.submission = "accepted"
                self._ready.set_result(None)
                if self.submission == "uncertain":
                    self._notify_observers()
                if self.worker is not None:
                    try:
                        await _await_cleanup(self.worker, on_cancel=self._record)
                    except BaseException as error:
                        self._record(error)
                        if not self.callback_completed.done():
                            # A settled/cancelled loop handle cannot establish
                            # native rejection or callback non-entry. Report its
                            # original failure, retaining any late callback here.
                            self.unclassified = True
                            self._notify_observers()
                # The independent acknowledgement keeps custody even if native
                # submission raised without returning the executor Future.
                acknowledgement = asyncio.wrap_future(self.callback_completed)
                try:
                    result = await _await_cleanup(
                        acknowledgement, on_cancel=self._record
                    )
                except BaseException as error:
                    self._record(error)
                    if not self.callback_completed.done():
                        raise
                    result = self.callback_completed.result()
                succeeded, value = result
                if succeeded:
                    self._returned = value
                    await self._checkpoint()
                    if _is_native_awaitable(value):
                        native_mro = type.__dict__["__mro__"].__get__(type(value))
                        self._returned_future = any(
                            base is asyncio.Future for base in native_mro
                        )
                        if self._returned_future:
                            _cleanup_admit(value, asyncio.get_running_loop())
                        self.returned_started = True
                        if self.deadline_requested:
                            asyncio.get_running_loop().call_soon(self.cancel_returned)
                        if self._returned_future:
                            value = await _await_cleanup(value, on_cancel=self._record)
                        else:
                            # Raw returned work stays in this admitted Task/Context.
                            value = await value
                    self._value = value
                    self.returned_succeeded = True
            except BaseException as error:
                self._record(error)
            await self._checkpoint()

    def cancel_returned(self):
        """Request a private cooperative deadline, never cancelling the worker."""
        with self._lock:
            self.deadline_requested = True
            if not self.returned_started or self.drained or self._deadline_sent:
                return False
            self._deadline_sent = True
        if self._returned_future:
            return asyncio.Future.cancel(self._returned, self.deadline_token)
        return _cleanup_observe(
            self.coordinator, asyncio.Task.cancel, self.deadline_token
        )

    async def wait(self):
        """Report unresolved work without abandoning its original coordinator."""
        if not self._started:
            raise RuntimeError("Cleanup invocation must start before observation")
        loop = asyncio.get_running_loop()
        ready = asyncio.wrap_future(self._ready, loop=loop)
        first = None
        try:
            await _await_cleanup_outcome(ready, self.outcome)
        except BaseException as error:
            first = error
        if not self.unresolved:
            # Observe either full settlement or a later unclassified worker
            # failure. Waiting only on completion would strand joined observers.
            observed = asyncio.wrap_future(self.observation, loop=loop)
            try:
                await _await_cleanup_outcome(observed, self.outcome)
            except BaseException as error:
                if first is None:
                    first = error
        if self.unresolved:
            # Returning this failure does not cancel the original coordinator or
            # make a new invocation safe. The consumer must retain this request.
            error = first if first is not None else self.outcome.error()
            if error is None:
                raise RuntimeError("Native cleanup submission remains unresolved")
            raise error
        pending = asyncio.wrap_future(self.completion, loop=loop)
        try:
            value, error = await _await_cleanup_outcome(pending, self.outcome)
        except BaseException:
            if first is not None:
                raise first
            raise
        if first is not None:
            raise first
        if error is not None:
            raise error
        return value
