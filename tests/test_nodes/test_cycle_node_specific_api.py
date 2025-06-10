"""Node-specific cycle tests for API nodes.

Tests API nodes in cyclic workflows to ensure proper retry patterns,
polling behaviors, and error handling in cycle contexts.

Covers:
- RESTClientNode: API retry/polling patterns
- HTTPRequestNode: HTTP request cycles with backoff
"""

from typing import Any, Dict

from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.runtime.local import LocalRuntime


class MockRESTClientNode(CycleAwareNode):
    """Mock REST client for testing cycles without actual HTTP calls."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "url": NodeParameter(
                name="url", type=str, required=False, default="http://test.com"
            ),
            "method": NodeParameter(
                name="method", type=str, required=False, default="GET"
            ),
            "retry_count": NodeParameter(
                name="retry_count", type=int, required=False, default=0
            ),
            "success_threshold": NodeParameter(
                name="success_threshold", type=int, required=False, default=3
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        url = kwargs.get("url", "http://test.com")
        method = kwargs.get("method", "GET")
        retry_count = kwargs.get("retry_count", 0)
        success_threshold = kwargs.get("success_threshold", 3)
        iteration = self.get_iteration(context)

        # Simulate API response patterns
        if iteration < success_threshold:
            # Simulate API failures initially
            status_code = 500 if iteration < 2 else 429  # Server error then rate limit
            success = False
            response_data = {"error": f"API error on attempt {iteration + 1}"}
        else:
            # Success after retries
            status_code = 200
            success = True
            response_data = {
                "data": f"Success from {url}",
                "method": method,
                "attempt": iteration + 1,
            }

        # Calculate backoff delay
        backoff_delay = min(2**iteration, 30)  # Exponential backoff, max 30s

        converged = success or iteration >= 10  # Stop after success or max retries

        return {
            "status_code": status_code,
            "success": success,
            "response_data": response_data,
            "retry_count": retry_count + 1,
            "backoff_delay": backoff_delay,
            "iteration": iteration + 1,
            "converged": converged,
        }


class MockHTTPRequestNode(CycleAwareNode):
    """Mock HTTP request node for testing cycles."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "url": NodeParameter(
                name="url", type=str, required=False, default="http://api.example.com"
            ),
            "headers": NodeParameter(
                name="headers", type=dict, required=False, default={}
            ),
            "params": NodeParameter(
                name="params", type=dict, required=False, default={}
            ),
            "polling_interval": NodeParameter(
                name="polling_interval", type=int, required=False, default=5
            ),
            "polling_count": NodeParameter(
                name="polling_count", type=int, required=False, default=0
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        url = kwargs.get("url", "http://api.example.com")
        headers = kwargs.get("headers", {})
        params = kwargs.get("params", {})
        polling_interval = kwargs.get("polling_interval", 5)
        self.get_iteration(context)

        # Get polling count from previous cycle or initialize
        polling_count = kwargs.get("polling_count", 0) + 1

        # Simulate polling for job completion
        job_id = params.get("job_id", "job_123")

        # Simulate job progress - use polling_count instead of iteration
        if polling_count < 4:  # Need at least 4 polls to complete
            status = "running"
            progress = polling_count * 25  # 25%, 50%, 75%
            complete = False
        else:
            status = "completed"
            progress = 100
            complete = True

        converged = complete  # Converge when job is complete

        return {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "complete": complete,
            "polling_count": polling_count,
            "polling_interval": polling_interval,
            "url": url,  # Pass through for next iteration
            "params": params,  # Pass through for next iteration
            "headers": headers,  # Pass through for next iteration
            "converged": converged,
        }


class TestRESTClientNodeCycles:
    """Test RESTClientNode in cyclic workflows."""

    def test_rest_client_retry_cycle(self):
        """Test REST client retry pattern in cycles."""
        workflow = Workflow("rest-retry-cycle", "REST Retry Cycle")

        workflow.add_node("rest_client", MockRESTClientNode())

        # Create retry cycle
        workflow.create_cycle("api_retry").connect(
            "rest_client",
            "rest_client",
            mapping={"retry_count": "retry_count", "url": "url", "method": "method"},
        ).max_iterations(12).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "url": "https://api.example.com/data",
                "method": "POST",
                "success_threshold": 4,
            },
        )

        assert run_id is not None
        final_output = results["rest_client"]
        assert final_output["converged"] is True
        assert final_output["success"] is True
        assert final_output["status_code"] == 200
        assert final_output["retry_count"] >= 4

    def test_rest_client_exponential_backoff(self):
        """Test REST client with exponential backoff in cycles."""
        workflow = Workflow("rest-backoff-cycle", "REST Backoff Cycle")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "base_delay": NodeParameter(
                        name="base_delay", type=int, required=False, default=1
                    ),
                    "max_delay": NodeParameter(
                        name="max_delay", type=int, required=False, default=60
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return {
                    "base_delay": kwargs.get("base_delay", 1),
                    "max_delay": kwargs.get("max_delay", 60),
                }

        class BackoffRESTNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "base_delay": NodeParameter(
                        name="base_delay", type=int, required=False, default=1
                    ),
                    "max_delay": NodeParameter(
                        name="max_delay", type=int, required=False, default=60
                    ),
                    "delay_history": NodeParameter(
                        name="delay_history", type=list, required=False, default=[]
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                # Handle initial parameters vs cycle parameters
                try:
                    base_delay = kwargs.get("base_delay", 1)
                    max_delay = kwargs.get("max_delay", 60)
                except NameError:
                    base_delay = 1
                    max_delay = 60

                iteration = self.get_iteration(context)

                # Calculate exponential backoff starting from iteration 0
                delay = min(base_delay * (2**iteration), max_delay)

                # Track delay history - get from previous cycle
                delay_history = kwargs.get("delay_history", [])
                delay_history.append(delay)

                # Simulate API call success after several attempts
                success = iteration >= 3  # Success after 4 attempts (0,1,2,3)
                status_code = 200 if success else 429  # Rate limited

                converged = success

                return {
                    "current_delay": delay,
                    "delay_history": delay_history,
                    "status_code": status_code,
                    "success": success,
                    "iteration": iteration,
                    "converged": converged,
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("backoff_client", BackoffRESTNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "backoff_client",
            mapping={"base_delay": "base_delay", "max_delay": "max_delay"},
        )

        # Cycle with specific field mapping
        workflow.create_cycle("backoff_test").connect(
            "backoff_client",
            "backoff_client",
            mapping={
                "delay_history": "delay_history",
                "base_delay": "base_delay",
                "max_delay": "max_delay",
            },
        ).max_iterations(10).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"data_source": {"base_delay": 2, "max_delay": 30}}
        )

        assert run_id is not None
        final_output = results["backoff_client"]
        assert final_output["converged"] is True
        assert final_output["success"] is True

        # Verify exponential backoff pattern
        delay_history = final_output["delay_history"]
        assert len(delay_history) >= 1
        if len(delay_history) > 0:
            assert delay_history[0] == 2  # base_delay * 2^0 = 2 * 1 = 2
        if len(delay_history) > 1:
            assert delay_history[1] == 4  # base_delay * 2^1 = 2 * 2 = 4
        if len(delay_history) > 2:
            assert delay_history[2] == 8  # base_delay * 2^2 = 2 * 4 = 8
        assert all(delay <= 30 for delay in delay_history)  # max_delay respected

    def test_rest_client_conditional_retry(self):
        """Test REST client with conditional retry logic."""
        workflow = Workflow("rest-conditional-retry", "REST Conditional Retry")

        class ConditionalRetryRESTNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "retry_on_codes": NodeParameter(
                        name="retry_on_codes",
                        type=list,
                        required=False,
                        default=[429, 500, 502, 503],
                    )
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                retry_on_codes = kwargs.get("retry_on_codes", [429, 500, 502, 503])
                iteration = self.get_iteration(context)

                # Simulate different HTTP status codes
                status_codes = [500, 502, 429, 200]  # Pattern of responses
                current_status = status_codes[min(iteration, len(status_codes) - 1)]

                should_retry = current_status in retry_on_codes
                success = current_status == 200

                # Determine if we should continue cycling
                converged = success or (not should_retry) or iteration >= 6

                return {
                    "status_code": current_status,
                    "should_retry": should_retry,
                    "success": success,
                    "iteration": iteration + 1,
                    "converged": converged,
                }

        workflow.add_node("conditional_client", ConditionalRetryRESTNode())

        workflow.create_cycle("conditional_retry").connect(
            "conditional_client", "conditional_client"
        ).max_iterations(8).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"retry_on_codes": [429, 500, 502, 503, 504]}
        )

        assert run_id is not None
        final_output = results["conditional_client"]
        assert final_output["converged"] is True
        assert final_output["success"] is True
        assert final_output["status_code"] == 200


class TestHTTPRequestNodeCycles:
    """Test HTTPRequestNode in cyclic workflows."""

    def test_http_polling_cycle(self):
        """Test HTTP request node for polling patterns."""
        workflow = Workflow("http-polling-cycle", "HTTP Polling Cycle")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "url": NodeParameter(name="url", type=str, required=False),
                    "params": NodeParameter(name="params", type=dict, required=False),
                    "polling_interval": NodeParameter(
                        name="polling_interval", type=int, required=False
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return {
                    "url": kwargs.get("url", "https://api.example.com/jobs/status"),
                    "params": kwargs.get("params", {"job_id": "async_job_456"}),
                    "polling_interval": kwargs.get("polling_interval", 3),
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("http_poller", MockHTTPRequestNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "http_poller",
            mapping={
                "url": "url",
                "params": "params",
                "polling_interval": "polling_interval",
            },
        )

        # Create polling cycle - map specific fields that need to persist
        workflow.create_cycle("http_polling_cycle").connect(
            "http_poller",
            "http_poller",
            mapping={
                "polling_count": "polling_count",
                "url": "url",
                "params": "params",
                "headers": "headers",
                "polling_interval": "polling_interval",
            },
        ).max_iterations(10).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "url": "https://api.example.com/jobs/status",
                    "params": {"job_id": "async_job_456"},
                    "polling_interval": 3,
                }
            },
        )

        assert run_id is not None
        final_output = results["http_poller"]
        assert final_output["converged"] is True
        assert final_output["complete"] is True
        assert final_output["status"] == "completed"
        assert final_output["progress"] == 100
        assert final_output["polling_count"] >= 3

    def test_http_progressive_data_fetching(self):
        """Test HTTP request node for progressive data fetching."""
        workflow = Workflow("http-progressive-fetch", "HTTP Progressive Fetch")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "base_url": NodeParameter(
                        name="base_url", type=str, required=False
                    ),
                    "page": NodeParameter(name="page", type=int, required=False),
                    "per_page": NodeParameter(
                        name="per_page", type=int, required=False
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return {
                    "base_url": kwargs.get("base_url", "https://api.example.com/data"),
                    "page": kwargs.get("page", 1),
                    "per_page": kwargs.get("per_page", 10),
                }

        class ProgressiveHTTPNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "base_url": NodeParameter(
                        name="base_url",
                        type=str,
                        required=False,
                        default="http://api.com",
                    ),
                    "page": NodeParameter(
                        name="page", type=int, required=False, default=1
                    ),
                    "per_page": NodeParameter(
                        name="per_page", type=int, required=False, default=10
                    ),
                    "total_fetched": NodeParameter(
                        name="total_fetched", type=int, required=False, default=0
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                page = kwargs.get("page", 1)  # Current page number
                per_page = kwargs.get("per_page", 10)
                iteration = self.get_iteration(context)

                # Simulate paginated API responses
                total_records = 45  # Total available records
                current_page = page  # Use the passed page number directly
                start_idx = (current_page - 1) * per_page
                end_idx = min(start_idx + per_page, total_records)

                if start_idx >= total_records:
                    # No more data
                    page_data = []
                    has_more = False
                    current_total = kwargs.get("total_fetched", 0)
                else:
                    # Simulate fetching page data
                    page_data = [f"record_{i}" for i in range(start_idx, end_idx)]
                    has_more = end_idx < total_records
                    current_total = kwargs.get("total_fetched", 0) + len(page_data)

                converged = not has_more or iteration >= 10

                return {
                    "current_page": current_page,
                    "page_data": page_data,
                    "total_fetched": current_total,
                    "has_more": has_more,
                    "next_page": current_page + 1 if has_more else None,
                    "per_page": per_page,  # Pass through for next iteration
                    "converged": converged,
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("progressive_fetcher", ProgressiveHTTPNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "progressive_fetcher",
            mapping={"base_url": "base_url", "page": "page", "per_page": "per_page"},
        )

        # Cycle with specific field mapping
        workflow.create_cycle("progressive_fetch").connect(
            "progressive_fetcher",
            "progressive_fetcher",
            mapping={
                "total_fetched": "total_fetched",
                "per_page": "per_page",
                "next_page": "page",  # Use next_page as the new page number
            },
        ).max_iterations(15).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "base_url": "https://api.example.com/data",
                    "page": 1,
                    "per_page": 10,
                }
            },
        )

        assert run_id is not None
        final_output = results["progressive_fetcher"]
        assert final_output["converged"] is True
        assert final_output["has_more"] is False
        assert final_output["total_fetched"] == 45  # All records fetched

    def test_http_adaptive_rate_limiting(self):
        """Test HTTP request node with adaptive rate limiting."""
        workflow = Workflow("http-adaptive-rate-limit", "HTTP Adaptive Rate Limit")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "initial_rate": NodeParameter(
                        name="initial_rate", type=float, required=False
                    ),
                    "requests_to_make": NodeParameter(
                        name="requests_to_make", type=int, required=False
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                return {
                    "initial_rate": kwargs.get("initial_rate", 1.0),
                    "requests_to_make": kwargs.get("requests_to_make", 20),
                }

        class AdaptiveRateLimitNode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "initial_rate": NodeParameter(
                        name="initial_rate", type=float, required=False, default=1.0
                    ),
                    "requests_to_make": NodeParameter(
                        name="requests_to_make", type=int, required=False, default=20
                    ),
                    "current_rate": NodeParameter(
                        name="current_rate", type=float, required=False, default=None
                    ),
                    "successful_requests": NodeParameter(
                        name="successful_requests", type=int, required=False, default=0
                    ),
                    "failed_requests": NodeParameter(
                        name="failed_requests", type=int, required=False, default=0
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                initial_rate = kwargs.get("initial_rate", 1.0)
                requests_to_make = kwargs.get("requests_to_make", 20)
                self.get_iteration(context)

                # Use passed values or initialize from first iteration
                current_rate = kwargs.get("current_rate", initial_rate)
                successful_requests = kwargs.get("successful_requests", 0)
                failed_requests = kwargs.get("failed_requests", 0)

                # Simulate API response based on current rate
                if current_rate > 2.0:
                    # Too fast - rate limited
                    status_code = 429
                    success = False
                    new_rate = current_rate * 0.5  # Slow down
                elif current_rate < 0.1:
                    # Too slow - can speed up
                    status_code = 200
                    success = True
                    new_rate = min(current_rate * 1.5, 2.0)  # Speed up
                else:
                    # Good rate
                    status_code = 200
                    success = True
                    new_rate = current_rate

                # Update counters
                if success:
                    new_successful = successful_requests + 1
                    new_failed = failed_requests
                else:
                    new_successful = successful_requests
                    new_failed = failed_requests + 1

                total_requests = new_successful + new_failed
                converged = new_successful >= requests_to_make or total_requests >= 30

                return {
                    "status_code": status_code,
                    "success": success,
                    "current_rate": new_rate,
                    "successful_requests": new_successful,
                    "failed_requests": new_failed,
                    "total_requests": total_requests,
                    "requests_to_make": requests_to_make,  # Pass through
                    "converged": converged,
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("adaptive_limiter", AdaptiveRateLimitNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "adaptive_limiter",
            mapping={
                "initial_rate": "initial_rate",
                "requests_to_make": "requests_to_make",
            },
        )

        # Cycle with specific field mapping
        workflow.create_cycle("adaptive_rate_limiting").connect(
            "adaptive_limiter",
            "adaptive_limiter",
            mapping={
                "current_rate": "current_rate",
                "successful_requests": "successful_requests",
                "failed_requests": "failed_requests",
                "requests_to_make": "requests_to_make",
            },
        ).max_iterations(35).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "initial_rate": 3.0,  # Start too fast
                    "requests_to_make": 15,
                }
            },
        )

        assert run_id is not None
        final_output = results["adaptive_limiter"]
        assert final_output["converged"] is True
        assert final_output["successful_requests"] >= 15
        # Rate should have adapted to a reasonable level
        assert 0.1 <= final_output["current_rate"] <= 2.0


class TestAPINodeCycleIntegration:
    """Test integration scenarios with API nodes in cycles."""

    def test_api_retry_with_circuit_breaker(self):
        """Test API retry cycles with circuit breaker pattern."""
        workflow = Workflow("api-circuit-breaker", "API Circuit Breaker")

        class CircuitBreakerAPINode(CycleAwareNode):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "failure_threshold": NodeParameter(
                        name="failure_threshold", type=int, required=False, default=5
                    ),
                    "recovery_timeout": NodeParameter(
                        name="recovery_timeout", type=int, required=False, default=10
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
                failure_threshold = kwargs.get("failure_threshold", 5)
                recovery_timeout = kwargs.get("recovery_timeout", 10)
                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                circuit_state = prev_state.get(
                    "circuit_state", "closed"
                )  # closed, open, half-open
                failure_count = prev_state.get("failure_count", 0)
                last_failure_time = prev_state.get("last_failure_time", 0)

                current_time = iteration  # Simplified time for testing

                # Circuit breaker logic
                if circuit_state == "open":
                    if current_time - last_failure_time >= recovery_timeout:
                        circuit_state = "half-open"
                    else:
                        # Circuit open - fail fast
                        self.set_cycle_state(
                            {
                                "circuit_state": circuit_state,
                                "failure_count": failure_count,
                                "last_failure_time": last_failure_time,
                            }
                        )
                        return {
                            "success": False,
                            "circuit_state": circuit_state,
                            "error": "Circuit breaker open",
                            "converged": True,  # Stop trying while circuit is open
                        }

                # Simulate API call
                if iteration < 3 or (circuit_state == "half-open" and iteration < 8):
                    # Failures
                    success = False
                    new_failure_count = failure_count + 1
                    new_last_failure_time = current_time

                    if new_failure_count >= failure_threshold:
                        new_circuit_state = "open"
                    else:
                        new_circuit_state = circuit_state
                else:
                    # Success
                    success = True
                    new_failure_count = 0  # Reset on success
                    new_last_failure_time = last_failure_time
                    new_circuit_state = "closed"

                self.set_cycle_state(
                    {
                        "circuit_state": new_circuit_state,
                        "failure_count": new_failure_count,
                        "last_failure_time": new_last_failure_time,
                    }
                )

                converged = success or (
                    new_circuit_state == "open" and iteration > recovery_timeout
                )

                return {
                    "success": success,
                    "circuit_state": new_circuit_state,
                    "failure_count": new_failure_count,
                    "iteration": iteration + 1,
                    "converged": converged,
                }

        workflow.add_node("circuit_breaker_api", CircuitBreakerAPINode())

        workflow.create_cycle("circuit_breaker_cycle").connect(
            "circuit_breaker_api", "circuit_breaker_api"
        ).max_iterations(20).converge_when("converged == True").build()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"failure_threshold": 3, "recovery_timeout": 5}
        )

        assert run_id is not None
        final_output = results["circuit_breaker_api"]
        assert final_output["converged"] is True
        # Should eventually succeed or properly handle circuit opening
        assert final_output["circuit_state"] in ["closed", "open"]
