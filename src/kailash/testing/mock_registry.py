"""Mock resource registry for testing."""

import asyncio
import functools
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, Mock, create_autospec

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    """Record of a method call."""

    method: str
    args: tuple
    kwargs: dict
    timestamp: datetime
    result: Any = None
    exception: Optional[Exception] = None
    duration: float = 0.0


class MockResource:
    """Base class for mock resources with call tracking."""

    def __init__(self, spec=None):
        self._call_records: List[CallRecord] = []
        self._spec = spec

    def _record_call(
        self,
        method_name: str,
        args: tuple,
        kwargs: dict,
        result: Any = None,
        exception: Exception = None,
        duration: float = 0.0,
    ):
        """Record a method call."""
        record = CallRecord(
            method=method_name,
            args=args,
            kwargs=kwargs,
            timestamp=datetime.now(timezone.utc),
            result=result,
            exception=exception,
            duration=duration,
        )
        self._call_records.append(record)

    def get_calls(self, method_name: str = None) -> List[CallRecord]:
        """Get call records, optionally filtered by method."""
        if method_name:
            return [r for r in self._call_records if r.method == method_name]
        return self._call_records.copy()


class MockResourceRegistry:
    """Registry for mock resources in tests."""

    def __init__(self):
        self._mocks: Dict[str, Any] = {}
        self._call_history: Dict[str, List[CallRecord]] = {}
        self._expectations: Dict[str, List["Expectation"]] = {}

    def register_mock(self, name: str, mock: Any):
        """Register a mock resource."""
        self._mocks[name] = mock
        self._call_history[name] = []

        # Wrap methods to track calls if not already a Mock
        if not isinstance(mock, (Mock, AsyncMock)):
            self._wrap_mock_methods(name, mock)

    async def create_mock(self, name: str, factory: Any, spec: Any = None) -> Any:
        """Create a mock resource from factory."""
        # Determine what to mock
        if spec is None and hasattr(factory, "create"):
            # Try to get the spec from factory
            try:
                if asyncio.iscoroutinefunction(factory.create):
                    # Create a temporary instance to get its type
                    instance = await factory.create()
                    spec = type(instance)
                    # Clean up if possible
                    if hasattr(instance, "close"):
                        if asyncio.iscoroutinefunction(instance.close):
                            await instance.close()
                        else:
                            instance.close()
                else:
                    instance = factory.create()
                    spec = type(instance)
                    if hasattr(instance, "close"):
                        instance.close()
            except Exception as e:
                logger.debug(f"Could not determine spec from factory: {e}")

        # Create appropriate mock
        if spec:
            # Check if it's an async class
            has_async = any(
                asyncio.iscoroutinefunction(getattr(spec, attr, None))
                for attr in dir(spec)
                if not attr.startswith("_") and callable(getattr(spec, attr, None))
            )

            if has_async:
                mock = create_autospec(spec, spec_set=True, instance=True)
                # Make async methods return AsyncMock but preserve them for configuration
                async_methods = []
                for attr in dir(spec):
                    if not attr.startswith("_"):
                        method = getattr(spec, attr, None)
                        if asyncio.iscoroutinefunction(method):
                            async_methods.append(attr)
                            # Special handling for acquire method
                            if attr == "acquire":
                                # Create async context manager
                                async_cm = AsyncMock()
                                async_cm.__aenter__ = AsyncMock(return_value=mock)
                                async_cm.__aexit__ = AsyncMock(return_value=None)
                                acquire_mock = AsyncMock(return_value=async_cm)
                                setattr(mock, attr, acquire_mock)
                            else:
                                setattr(mock, attr, AsyncMock())
            else:
                mock = create_autospec(spec, spec_set=True, instance=True)
        else:
            # Default to AsyncMock for resources
            mock = AsyncMock()

        # Configure common resource methods (only for non-autospec mocks)
        if not spec or not hasattr(mock, "_spec_class"):
            self._configure_resource_mock(mock)

        # Register it
        self.register_mock(name, mock)

        return mock

    def create_mock_method(self, return_value=None, side_effect=None):
        """Create a mock method with tracking."""
        if asyncio.iscoroutine(return_value) or (
            side_effect and asyncio.iscoroutinefunction(side_effect)
        ):
            mock = AsyncMock(return_value=return_value, side_effect=side_effect)
        else:
            mock = Mock(return_value=return_value, side_effect=side_effect)
        return mock

    def _configure_resource_mock(self, mock: Union[Mock, AsyncMock]):
        """Configure common resource patterns."""
        # Database-like resources
        if hasattr(mock, "acquire"):
            # Check if this is already an AsyncMock
            if isinstance(getattr(mock, "acquire", None), AsyncMock):
                # Configure the existing AsyncMock
                async_cm = AsyncMock()
                async_cm.__aenter__ = AsyncMock(return_value=mock)
                async_cm.__aexit__ = AsyncMock(return_value=None)
                mock.acquire.return_value = async_cm
            else:
                # For autospec mocks, we can't override, but acquire should already be mocked
                pass

        if hasattr(mock, "execute"):
            mock.execute = AsyncMock(return_value=None)

        if hasattr(mock, "fetch"):
            mock.fetch = AsyncMock(return_value=[])

        if hasattr(mock, "fetchone"):
            mock.fetchone = AsyncMock(return_value=None)

        if hasattr(mock, "fetchval"):
            mock.fetchval = AsyncMock(return_value=None)

        # HTTP client-like resources
        if hasattr(mock, "get"):
            response_mock = AsyncMock()
            response_mock.json = AsyncMock(return_value={})
            response_mock.text = AsyncMock(return_value="")
            response_mock.status = 200
            response_mock.raise_for_status = Mock()

            mock.get.return_value = response_mock
            if hasattr(mock, "post"):
                mock.post.return_value = response_mock
            if hasattr(mock, "put"):
                mock.put.return_value = response_mock
            if hasattr(mock, "delete"):
                mock.delete.return_value = response_mock

        # Cache-like resources
        if hasattr(mock, "get") and hasattr(mock, "set"):
            mock.get = AsyncMock(return_value=None)
            mock.set = AsyncMock()
            mock.setex = AsyncMock()
            mock.delete = AsyncMock()
            mock.expire = AsyncMock()

        # Add close/cleanup methods if not present (skip if spec_set)
        try:
            if not hasattr(mock, "close"):
                mock.close = AsyncMock()
        except AttributeError:
            # Spec_set mock - can't add new attributes
            pass

        try:
            if not hasattr(mock, "cleanup"):
                mock.cleanup = AsyncMock()
        except AttributeError:
            # Spec_set mock - can't add new attributes
            pass

    def _wrap_mock_methods(self, name: str, mock: Any):
        """Wrap mock methods to track calls."""
        # Only wrap MockResource instances
        if not isinstance(mock, MockResource):
            return

        for attr_name in dir(mock):
            if attr_name.startswith("_"):
                continue

            attr = getattr(mock, attr_name)
            if callable(attr) and not isinstance(attr, (Mock, AsyncMock)):
                wrapped = self._create_wrapper(name, attr_name, attr, mock)
                setattr(mock, attr_name, wrapped)

    def _create_wrapper(
        self,
        resource_name: str,
        method_name: str,
        method: Callable,
        mock_resource: MockResource,
    ) -> Callable:
        """Create method wrapper that tracks calls."""
        is_async = asyncio.iscoroutinefunction(method)

        if is_async:

            @functools.wraps(method)
            async def async_wrapper(*args, **kwargs):
                start_time = asyncio.get_event_loop().time()
                try:
                    result = await method(*args, **kwargs)
                    duration = asyncio.get_event_loop().time() - start_time

                    # Record in both places
                    record = CallRecord(
                        method=method_name,
                        args=args,
                        kwargs=kwargs,
                        timestamp=datetime.now(timezone.utc),
                        result=result,
                        duration=duration,
                    )
                    self._call_history[resource_name].append(record)
                    mock_resource._record_call(
                        method_name, args, kwargs, result, duration=duration
                    )

                    return result
                except Exception as e:
                    duration = asyncio.get_event_loop().time() - start_time
                    record = CallRecord(
                        method=method_name,
                        args=args,
                        kwargs=kwargs,
                        timestamp=datetime.now(timezone.utc),
                        exception=e,
                        duration=duration,
                    )
                    self._call_history[resource_name].append(record)
                    mock_resource._record_call(
                        method_name, args, kwargs, exception=e, duration=duration
                    )
                    raise

            return async_wrapper
        else:

            @functools.wraps(method)
            def sync_wrapper(*args, **kwargs):
                import time

                start_time = time.time()
                try:
                    result = method(*args, **kwargs)
                    duration = time.time() - start_time

                    record = CallRecord(
                        method=method_name,
                        args=args,
                        kwargs=kwargs,
                        timestamp=datetime.now(timezone.utc),
                        result=result,
                        duration=duration,
                    )
                    self._call_history[resource_name].append(record)
                    mock_resource._record_call(
                        method_name, args, kwargs, result, duration=duration
                    )

                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    record = CallRecord(
                        method=method_name,
                        args=args,
                        kwargs=kwargs,
                        timestamp=datetime.now(timezone.utc),
                        exception=e,
                        duration=duration,
                    )
                    self._call_history[resource_name].append(record)
                    mock_resource._record_call(
                        method_name, args, kwargs, exception=e, duration=duration
                    )
                    raise

            return sync_wrapper

    def get_calls(
        self, resource_name: str, method_name: str = None
    ) -> List[CallRecord]:
        """Get call history for a resource."""
        calls = self._call_history.get(resource_name, [])

        # Also check if it's a Mock object with call tracking
        mock = self._mocks.get(resource_name)
        if mock and isinstance(mock, (Mock, AsyncMock)):
            # For unittest.mock objects, create CallRecords from call history
            if method_name and hasattr(mock, method_name):
                method_mock = getattr(mock, method_name)
                if hasattr(method_mock, "call_args_list"):
                    for call in method_mock.call_args_list:
                        args, kwargs = call if call else ((), {})
                        record = CallRecord(
                            method=method_name,
                            args=args,
                            kwargs=kwargs,
                            timestamp=datetime.now(timezone.utc),
                        )
                        calls.append(record)

        if method_name:
            calls = [c for c in calls if c.method == method_name]
        return calls

    def assert_called(
        self,
        resource_name: str,
        method_name: str,
        times: Optional[int] = None,
        with_args: Optional[tuple] = None,
        with_kwargs: Optional[dict] = None,
    ):
        """Assert a method was called."""
        mock = self._mocks.get(resource_name)

        # Handle unittest.mock objects
        if mock and isinstance(mock, (Mock, AsyncMock)):
            method = getattr(mock, method_name, None)
            if method is None:
                raise AssertionError(f"{resource_name} has no method {method_name}")

            if times is not None:
                assert method.call_count == times, (
                    f"{resource_name}.{method_name} called {method.call_count} times, "
                    f"expected {times}"
                )
            else:
                method.assert_called()

            if with_args is not None or with_kwargs is not None:
                method.assert_called_with(*(with_args or ()), **(with_kwargs or {}))
        else:
            # Use recorded calls
            calls = self.get_calls(resource_name, method_name)

            # Filter by args/kwargs if specified
            if with_args is not None or with_kwargs is not None:
                matching_calls = []
                for call in calls:
                    args_match = with_args is None or call.args == with_args
                    kwargs_match = with_kwargs is None or all(
                        call.kwargs.get(k) == v for k, v in with_kwargs.items()
                    )
                    if args_match and kwargs_match:
                        matching_calls.append(call)
                calls = matching_calls

            # Check times
            if times is not None:
                assert len(calls) == times, (
                    f"{resource_name}.{method_name} called {len(calls)} times, "
                    f"expected {times}\n"
                    f"Calls: {[(c.args, c.kwargs) for c in calls]}"
                )
            else:
                assert len(calls) > 0, f"{resource_name}.{method_name} was not called"

    def assert_not_called(self, resource_name: str, method_name: str):
        """Assert a method was not called."""
        mock = self._mocks.get(resource_name)

        if mock and isinstance(mock, (Mock, AsyncMock)):
            method = getattr(mock, method_name, None)
            if method:
                method.assert_not_called()
        else:
            calls = self.get_calls(resource_name, method_name)
            assert (
                len(calls) == 0
            ), f"{resource_name}.{method_name} was called {len(calls)} times"

    def get_mock(self, name: str) -> Any:
        """Get a mock resource."""
        return self._mocks.get(name)

    def reset_history(self, resource_name: str = None):
        """Reset call history."""
        if resource_name:
            self._call_history[resource_name] = []
            mock = self._mocks.get(resource_name)
            if mock and isinstance(mock, (Mock, AsyncMock)):
                mock.reset_mock()
        else:
            for name in self._call_history:
                self._call_history[name] = []
            for mock in self._mocks.values():
                if isinstance(mock, (Mock, AsyncMock)):
                    mock.reset_mock()

    def expect_call(
        self,
        resource_name: str,
        method_name: str,
        returns: Any = None,
        raises: Exception = None,
    ) -> "Expectation":
        """Set up an expectation for a call."""
        expectation = Expectation(resource_name, method_name, returns, raises)

        if resource_name not in self._expectations:
            self._expectations[resource_name] = []
        self._expectations[resource_name].append(expectation)

        # Configure mock if it exists
        mock = self._mocks.get(resource_name)
        if mock and hasattr(mock, method_name):
            method = getattr(mock, method_name)
            if raises:
                method.side_effect = raises
            else:
                method.return_value = returns

        return expectation


@dataclass
class Expectation:
    """Expectation for a method call."""

    resource_name: str
    method_name: str
    returns: Any = None
    raises: Optional[Exception] = None
    times: Optional[int] = None
    with_args: Optional[tuple] = None
    with_kwargs: Optional[dict] = None

    def matches(self, method_name: str, args: tuple, kwargs: dict) -> bool:
        """Check if call matches expectation."""
        if method_name != self.method_name:
            return False

        if self.with_args is not None and args != self.with_args:
            return False

        if self.with_kwargs is not None:
            for k, v in self.with_kwargs.items():
                if kwargs.get(k) != v:
                    return False

        return True
