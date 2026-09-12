"""REST API client nodes for the Kailash SDK.

This module provides specialized nodes for interacting with REST APIs in both
synchronous and asynchronous modes. These nodes build on the base HTTP nodes
to provide a more convenient interface for working with REST APIs.

Key Components:
    * RESTClientNode: Synchronous REST API client
    * AsyncRESTClientNode: Asynchronous REST API client
    * Resource path builders and response handlers
"""

import asyncio
import copy
import ipaddress
import types
from typing import Any
from urllib.parse import urljoin, urlparse

from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from kailash.utils.url_credentials import mask_error_text, mask_url

#: Redirect hops allowed per pagination page. Each hop is re-authorized by the
#: origin guard, so this only bounds a redirect LOOP; it is not a trust control.
_MAX_REDIRECT_HOPS = 5


def _sanitize_for_log(value: Any) -> str:
    """Render an untrusted value safe to put in a single log line.

    ``mask_error_text`` removes embedded credentials but leaves control
    characters intact, so a server-supplied link containing CR/LF could inject
    additional, attacker-authored lines into the log -- including lines that
    look like a different component's output. Masking runs FIRST so the
    credential rule still applies, then every non-printable character is
    replaced by a visible escape of the form backslash-x-hex.
    """
    text = mask_error_text(value)
    return "".join(
        ch if (ch.isprintable() or ch == " ") else f"\\x{ord(ch):02x}" for ch in text
    )


@register_node()
class RESTClientNode(Node):
    """
    Node for interacting with REST APIs using resource-oriented patterns.

    This node provides a higher-level abstraction over HTTP operations, specifically
    designed for REST APIs. It understands REST conventions and provides convenient
    methods for resource-based operations, making it easier to integrate RESTful
    services into Kailash workflows.

    Design Philosophy:
        The RESTClientNode embraces REST principles and conventions, providing an
        intuitive interface for resource manipulation. It abstracts common patterns
        like path parameter substitution, pagination, and error handling while
        maintaining flexibility for API-specific requirements. The design promotes
        clean, maintainable API integration code.

    Upstream Dependencies:
        - Workflow orchestrators defining API endpoints
        - Configuration nodes providing API credentials
        - Data transformation nodes preparing resources
        - Authentication nodes managing tokens
        - Schema validation nodes defining expected formats

    Downstream Consumers:
        - Data processing nodes working with API responses
        - Pagination handlers managing result sets
        - Error recovery nodes handling failures
        - Caching nodes storing resource data
        - Analytics nodes tracking API usage patterns

    Configuration:
        The node supports REST-specific configuration:
        - Base URL for API endpoints
        - Resource paths with parameter placeholders
        - Default headers and authentication
        - API versioning strategies
        - Pagination parameters
        - Response format expectations

    Implementation Details:
        - Built on HTTPRequestNode for core functionality
        - Automatic URL construction from base + resource
        - Path parameter substitution (e.g., /users/{id})
        - Query parameter handling with encoding
        - Standard REST method mapping
        - Response format negotiation
        - Error response parsing for API-specific errors
        - Link header parsing for pagination

    Error Handling:
        - 404 errors for missing resources
        - 422 validation errors with field details
        - 401/403 authentication/authorization errors
        - Rate limiting (429) with retry headers
        - 5xx server errors with backoff
        - Network failures with retry logic
        - Malformed response handling

    Side Effects:
        - Performs HTTP requests to external APIs
        - May modify remote resources (POST/PUT/DELETE)
        - Consumes API rate limits
        - May trigger webhooks or notifications
        - Updates internal request metrics

    Examples:
        >>> # Initialize REST client
        >>> client = RESTClientNode()
        >>>
        >>> # Get a single resource
        >>> result = client.execute(
        ...     base_url="https://api.example.com/v1",
        ...     resource="users/{id}",
        ...     method="GET",
        ...     path_params={"id": 123},
        ...     headers={"Authorization": "Bearer token"}
        ... )
        >>> assert result["status_code"] == 200
        >>> user = result["content"]
        >>> assert user["id"] == 123
        >>>
        >>> # List resources with pagination
        >>> result = client.execute(
        ...     base_url="https://api.example.com/v1",
        ...     resource="products",
        ...     method="GET",
        ...     query_params={"page": 1, "per_page": 20, "category": "electronics"}
        ... )
        >>> assert len(result["content"]) <= 20
        >>>
        >>> # Create a new resource
        >>> result = client.execute(
        ...     base_url="https://api.example.com/v1",
        ...     resource="posts",
        ...     method="POST",
        ...     data={"title": "New Post", "content": "Post content"},
        ...     headers={"Content-Type": "application/json"}
        ... )
        >>> assert result["status_code"] == 201
        >>> assert "id" in result["content"]
        >>>
        >>> # Update a resource
        >>> result = client.execute(
        ...     base_url="https://api.example.com/v1",
        ...     resource="users/{id}",
        ...     method="PATCH",
        ...     path_params={"id": 123},
        ...     data={"email": "newemail@example.com"}
        ... )
        >>> assert result["status_code"] == 200
        >>>
        >>> # Delete a resource
        >>> result = client.execute(
        ...     base_url="https://api.example.com/v1",
        ...     resource="comments/{id}",
        ...     method="DELETE",
        ...     path_params={"id": 456}
        ... )
        >>> assert result["status_code"] in [200, 204]
    """

    def __init__(self, **kwargs):
        """Initialize the REST client node.

        Args:
            base_url (str): Base URL for the REST API
            headers (dict, optional): Default headers for all requests
            auth (dict, optional): Authentication configuration
            version (str, optional): API version to use
            timeout (int, optional): Default request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries
            **kwargs: Additional parameters passed to base Node
        """
        super().__init__(**kwargs)
        self.http_node = HTTPRequestNode(url="")

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "base_url": NodeParameter(
                name="base_url",
                type=str,
                required=False,
                description="Base URL for the REST API (e.g., https://api.example.com)",
            ),
            "resource": NodeParameter(
                name="resource",
                type=str,
                required=False,
                description="API resource path (e.g., 'users' or 'products/{id}')",
            ),
            "method": NodeParameter(
                name="method",
                type=str,
                required=False,
                default="GET",
                description="HTTP method (GET, POST, PUT, PATCH, DELETE)",
            ),
            "path_params": NodeParameter(
                name="path_params",
                type=dict,
                required=False,
                default={},
                description="Parameters to substitute in resource path (e.g., {'id': 123})",
            ),
            "query_params": NodeParameter(
                name="query_params",
                type=dict,
                required=False,
                default={},
                description="Query parameters to include in the URL",
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=False,
                default={},
                description="HTTP headers to include in the request",
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                default=None,
                description="Request body data (for POST, PUT, etc.)",
            ),
            "version": NodeParameter(
                name="version",
                type=str,
                required=False,
                default=None,
                description="API version to use (e.g., 'v1')",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Request timeout in seconds",
            ),
            "verify_ssl": NodeParameter(
                name="verify_ssl",
                type=bool,
                required=False,
                default=True,
                description="Whether to verify SSL certificates",
            ),
            "allow_redirects": NodeParameter(
                name="allow_redirects",
                type=bool,
                required=False,
                default=True,
                # Mirrors `HTTPRequestNode`'s own declaration (`http.py:337`),
                # and it must EXIST here for the same reason: an undeclared
                # parameter is filtered out by `validate_inputs`, so
                # `add_node("RESTClientNode", "n", {"allow_redirects": False})`
                # was SILENTLY DROPPED and the control was unreachable from a
                # workflow. Note the semantics differ from the HTTP node's: the
                # REST node NEVER lets the transport follow a redirect by
                # itself (see `_execute_following_redirects`), so this flag
                # selects whether the NODE follows one under the origin guard.
                # Default True so existing callers are unaffected.
                description=(
                    "Whether 3xx redirects are followed. Following is done by "
                    "this node, re-authorizing every hop against the origin "
                    "guard and bounded by _MAX_REDIRECT_HOPS; the underlying "
                    "client's automatic follow is always OFF. Set False to "
                    "receive the 3xx response itself."
                ),
            ),
            "paginate": NodeParameter(
                name="paginate",
                type=bool,
                required=False,
                default=False,
                description="Whether to handle pagination automatically (for GET requests)",
            ),
            "pagination_params": NodeParameter(
                name="pagination_params",
                type=dict,
                required=False,
                default=None,
                description="Pagination configuration parameters",
            ),
            "allowed_pagination_origins": NodeParameter(
                name="allowed_pagination_origins",
                type=list,
                required=False,
                default=None,
                description=(
                    "Origins (scheme://host[:port]) a server-supplied pagination "
                    "link may point to besides the original request's own origin. "
                    "A follow-up page on an allow-listed cross-origin target is "
                    "fetched WITHOUT credential-bearing headers; anything not "
                    "same-origin and not allow-listed stops pagination."
                ),
            ),
            "retry_count": NodeParameter(
                name="retry_count",
                type=int,
                required=False,
                default=0,
                description="Number of times to retry failed requests",
            ),
            "retry_backoff": NodeParameter(
                name="retry_backoff",
                type=float,
                required=False,
                default=0.5,
                description="Backoff factor for retries",
            ),
            "auth_type": NodeParameter(
                name="auth_type",
                type=str,
                required=False,
                default=None,
                description="Authentication type: bearer, basic, api_key, oauth2",
            ),
            "auth_token": NodeParameter(
                name="auth_token",
                type=str,
                required=False,
                default=None,
                description="Authentication token/key for bearer, api_key, or oauth2",
            ),
            "auth_username": NodeParameter(
                name="auth_username",
                type=str,
                required=False,
                default=None,
                description="Username for basic authentication",
            ),
            "auth_password": NodeParameter(
                name="auth_password",
                type=str,
                required=False,
                default=None,
                description="Password for basic authentication",
            ),
            "api_key_header": NodeParameter(
                name="api_key_header",
                type=str,
                required=False,
                default="X-API-Key",
                description="Header name for API key authentication",
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "data": NodeParameter(
                name="data",
                type=Any,
                required=True,
                description="Parsed response data from the API",
            ),
            "status_code": NodeParameter(
                name="status_code",
                type=int,
                required=True,
                description="HTTP status code",
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=True,
                description="Whether the request was successful (status code 200-299)",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Additional metadata about the request and response",
            ),
        }

    def _build_url(
        self,
        base_url: str,
        resource: str,
        path_params: dict[str, Any],
        version: str | None = None,
    ) -> str:
        """Build the full URL for a REST API request.

        Args:
            base_url: Base API URL
            resource: Resource path pattern
            path_params: Parameters to substitute in the path
            version: API version to include in the URL

        Returns:
            Complete URL with path parameters substituted

        Raises:
            NodeValidationError: If a required path parameter is missing
        """
        # Remove trailing slash from base URL if present
        base_url = base_url.rstrip("/")

        # Add version to URL if specified
        if version:
            base_url = f"{base_url}/{version}"

        # Substitute path parameters
        try:
            # Extract required path parameters from the resource pattern
            required_params = [
                param.strip("{}")
                for param in resource.split("/")
                if param.startswith("{") and param.endswith("}")
            ]

            # Check if all required parameters are provided
            for param in required_params:
                if param not in path_params:
                    raise NodeValidationError(
                        f"Missing required path parameter '{param}' for resource '{resource}'"
                    )

            # Substitute parameters in the resource path
            resource_path = resource
            for param, value in path_params.items():
                placeholder = f"{{{param}}}"
                if placeholder in resource_path:
                    resource_path = resource_path.replace(placeholder, str(value))

            # Ensure path starts without a slash
            resource_path = resource_path.lstrip("/")

            # Build complete URL
            return f"{base_url}/{resource_path}"

        except Exception as e:
            if not isinstance(e, NodeValidationError):
                raise NodeValidationError(f"Failed to build URL: {str(e)}") from e
            raise

    def _handle_pagination(
        self,
        initial_response: dict[str, Any],
        query_params: dict[str, Any],
        pagination_params: dict[str, Any] | None,
        *,
        request_url: str,
        request_headers: dict[str, Any],
        request_timeout: int,
        request_kwargs: dict[str, Any] | None = None,
        allowed_origins: Any = None,
    ) -> list[Any]:
        """Handle pagination for REST API responses.

        This method supports common pagination patterns:
            * Page-based: ?page=1&per_page=100
            * Offset-based: ?offset=0&limit=100
            * Cursor-based: ?cursor=abc123

        Args:
            initial_response: Response from the first API call
            query_params: Original query parameters
            pagination_params: Configuration for pagination handling
            request_url: Fully-built URL of the originating request. Follow-up
                page requests are issued against this exact URL; it is
                keyword-only and required so a caller cannot silently fall back
                to an unusable default.
            request_headers: Headers of the originating request (auth headers
                included) — follow-up pages need the same credentials.
            request_timeout: Timeout of the originating request, in seconds.
            request_kwargs: The COMPLETE transport keyword set the originating
                request was issued with (the caller's ``http_params`` dict,
                threaded whole and never re-enumerated). Follow-up pages are
                issued from a copy of it, so node-level transport settings that
                never reach ``request_headers`` -- ``auth_type``/``auth_token``/
                ``auth_username``/``auth_password``/``api_key_header`` (the
                ``Authorization`` header is injected by ``HTTPRequestNode``
                itself, not by the caller's headers dict), plus ``verify_ssl``,
                ``retry_count`` and ``retry_backoff`` -- apply to page 2+ as
                well as page 1. Threading the whole dict rather than listing
                keywords is deliberate: a transport parameter added to
                ``http_params`` later propagates to follow-up pages with no
                edit here, so it cannot be silently dropped. Omitting it
                (``None``) issues follow-ups with url/headers/params/timeout
                only -- the historical behaviour, retained for direct callers
                that have no originating kwarg set.
            allowed_origins: The caller's ``allowed_pagination_origins``,
                threaded on into the redirect guard for the follow-up request.
                Defaults to ``None``, which is the FAIL-CLOSED reading -- an
                omitted allowlist is never invented. Without this parameter the
                follow-up hop ran with ``allowed_origins=None`` unconditionally
                while the initial request honoured the caller's list, so the
                two halves of one run were guarded to different widths.

        Returns:
            Combined list of items from all pages

        Raises:
            NodeExecutionError: If the response shape does not match the
                configured pagination paths.
            NodeValidationError: If a follow-up page request is mis-configured
                (e.g. an unusable URL). This is deliberately NOT swallowed:
                doing so silently returned page 1 as if it were the whole
                result set.
        """
        if not pagination_params:
            # Default pagination configuration
            pagination_params = {
                "type": "page",  # page, offset, or cursor
                "page_param": "page",  # query parameter for page number
                "limit_param": "per_page",  # query parameter for items per page
                "items_path": "data",  # path to items in response
                "total_path": "meta.total",  # path to total count in response
                "next_page_path": "meta.next_page",  # path to next page in response
                "max_pages": 10,  # maximum number of pages to fetch
            }

        pagination_type = pagination_params.get("type", "page")
        items_path = pagination_params.get("items_path", "data")
        # The max_pages cap is read and enforced in the remaining-pages fetch
        # loop below (see `while pages_fetched < max_pages`).

        # Extract items from initial response
        all_items = self._get_nested_value(initial_response, items_path, [])
        if not isinstance(all_items, list):
            raise NodeExecutionError(
                f"Pagination items path '{items_path}' did not return a list in response"
            )
        # `_get_nested_value` hands back the SAME list object that is nested
        # inside the caller's response, and the loop below `extend`s the
        # accumulator in place -- so merely reading the pages mutated the
        # caller's own `response["content"][items_path]` from 2 entries to
        # 2*N. Accumulate into our own list; the caller's response is left
        # exactly as the transport returned it.
        all_items = list(all_items)

        # Return immediately if no additional pages
        current_page = 1
        if pagination_type == "page":
            # These coercions raise BUILTIN ValueError/TypeError on a
            # non-numeric value. Both callers now catch NodeExecutionError only
            # (the deliberate narrowing that stops a mis-configured request
            # being swallowed), and NodeValidationError is a SIBLING of it, not
            # a subclass — so an unwrapped builtin escapes the node entirely,
            # outside the documented Raises taxonomy, taking page 1's data with
            # it. Wrap into the taxonomy and name the offending value.
            page_param = pagination_params.get("page_param", "page")
            limit_param = pagination_params.get("limit_param", "per_page")
            try:
                current_page = int(query_params.get(page_param, 1))
            except (ValueError, TypeError, OverflowError) as exc:
                raise NodeValidationError(
                    f"pagination page parameter '{page_param}' must be an "
                    f"integer; got {query_params.get(page_param)!r}"
                ) from exc
            total_path = pagination_params.get("total_path")
            try:
                per_page = int(query_params.get(limit_param, 20))
            except (ValueError, TypeError, OverflowError) as exc:
                raise NodeValidationError(
                    f"pagination limit parameter '{limit_param}' must be an "
                    f"integer; got {query_params.get(limit_param)!r}"
                ) from exc

            # If we have total info, check if more pages exist
            if total_path:
                total_items = self._get_nested_value(initial_response, total_path, 0)
                # A server-supplied total is untrusted: "1,234" or "many" makes
                # the comparison below raise TypeError against an int.
                if total_items is not None and not isinstance(
                    total_items, (int, float)
                ):
                    raise NodeValidationError(
                        f"pagination total_path '{total_path}' must resolve to a "
                        f"number; got {type(total_items).__name__} {total_items!r}"
                    )
                if not total_items or current_page * per_page >= total_items:
                    return all_items

        elif pagination_type == "cursor":
            next_cursor_path = pagination_params.get("next_page_path", "meta.next")
            next_cursor = self._get_nested_value(initial_response, next_cursor_path)
            if not next_cursor:
                return all_items

        # Fetch remaining pages
        max_pages = int(pagination_params.get("max_pages", 10))
        pages_fetched = 1
        # EVERY cursor we have already requested, not just the most recent one.
        # A single-slot `prev_cursor` only catches an IMMEDIATE repeat: a server
        # alternating A -> B -> A -> B never compares equal to its predecessor,
        # so the loop ran to `max_pages` appending the same two pages over and
        # over. Bounded by construction -- exactly one cursor is added per
        # iteration of the `while pages_fetched < max_pages` loop below, so
        # `len(seen_cursors) < max_pages` always; the loop bound IS the set
        # bound, and there is no path that adds without iterating.
        seen_cursors: set[str] = set()

        while pages_fetched < max_pages:
            next_query = dict(query_params)

            if pagination_type == "page":
                current_page += 1
                page_param = pagination_params.get("page_param", "page")
                next_query[page_param] = str(current_page)
            elif pagination_type == "cursor":
                cursor_param = pagination_params.get("cursor_param", "cursor")
                next_cursor_path = pagination_params.get("next_page_path", "meta.next")
                next_cursor = self._get_nested_value(initial_response, next_cursor_path)
                if not next_cursor:
                    break
                cursor_key = str(next_cursor)
                if cursor_key in seen_cursors:
                    self.logger.warning(
                        "Pagination stopped: server re-issued cursor %r, which "
                        "was already requested; fetching it again would "
                        "duplicate an earlier page.",
                        next_cursor,
                    )
                    break
                seen_cursors.add(cursor_key)
                next_query[cursor_param] = cursor_key
            else:
                break

            # Make the next request with the SAME transport configuration the
            # first page used — threaded in from the caller rather than
            # reconstructed here. Everything the originating request carried is
            # inherited (auth_*, verify_ssl, retry_*, ...); only the fields that
            # MUST differ for a follow-up GET are overridden.
            next_call = dict(request_kwargs or {})
            next_call.update(
                {
                    "url": request_url,
                    "method": "GET",
                    "headers": request_headers,
                    "params": next_query,
                    "response_format": "json",
                    "timeout": request_timeout,
                    # A follow-up page is a GET: never replay the originating
                    # request's body.
                    "json_data": None,
                    "data": None,
                }
            )
            try:
                # Through the redirect guard, never straight at the transport.
                # This request carries the caller's credentials, and with the
                # client's automatic follow left ON the server's `Location`
                # header chose where they went -- past the origin guard, past
                # `_MAX_REDIRECT_HOPS`, and past the internal-address refusal.
                #
                # `caller_chosen=True`: the destination is `request_url`, the
                # caller's own URL with different query parameters. No
                # server-supplied value reaches it, which is what separates
                # this from the async HATEOAS loop's fail-closed link.
                next_result = self._execute_following_redirects(
                    next_call,
                    allowed_origins=allowed_origins,
                    caller_chosen=True,
                )
            except NodeValidationError:
                # A mis-configured request is a programming/configuration
                # error, not a transient transport failure. Swallowing it is
                # exactly what made `paginate=True` a silent no-op: every
                # follow-up request failed validation, was logged at WARNING,
                # and the caller got page 1 presented as the complete result.
                raise
            except Exception as e:
                # Transport-level failures (connection reset, timeout, ...)
                # still degrade gracefully to the pages fetched so far.
                # Masked for parity with every rendered-exception sink in
                # `http.py` (`:639, 651, 686, 1041, 1073, 1085`): a driver
                # renders the full request URL, credentials and all, into its
                # exception text. Defence-in-depth / enforcement-surface
                # parity — no concrete credential has been traced to THIS sink
                # (http.py catches and masks `RequestException` itself, so what
                # arrives here is the non-`RequestException` residue).
                self.logger.warning("Pagination request failed: %s", mask_error_text(e))
                break

            next_response = next_result.get("response", {})
            if not next_result.get("success"):
                break

            next_content = next_response.get("content", {}) if next_response else {}
            next_items = self._get_nested_value(next_content, items_path, [])
            if not next_items:
                break

            all_items.extend(next_items)
            pages_fetched += 1
            initial_response = next_content  # For cursor extraction on next iteration

        return all_items

    def _paginate_with_page_count(
        self,
        initial_response: dict[str, Any],
        query_params: dict[str, Any],
        pagination_params: dict[str, Any] | None,
        *,
        request_url: str,
        request_headers: dict[str, Any],
        request_timeout: int,
        request_kwargs: dict[str, Any] | None = None,
        allowed_origins: Any = None,
    ) -> tuple[Any, int]:
        """Run ``_handle_pagination`` and report how many pages it merged.

        ``_handle_pagination`` returns items only, so the number of pages it
        merged is not otherwise observable -- and every caller needs it to
        decide whether page 1's navigation pointers still describe the merged
        ``data`` (see ``_drop_stale_pagination_metadata``). Count through a
        per-call proxy over the transport, installed on a SHALLOW COPY of this
        node so no state shared with a concurrent call is mutated.

        This is the SINGLE definition of the page-counting semantics: both
        ``RESTClientNode.run`` and ``AsyncRESTClientNode.async_run`` (which
        reaches it through ``asyncio.to_thread``, since ``_handle_pagination``
        blocks the calling thread) call it rather than each carrying a copy of
        the proxy. Two copies of this would satisfy their tests on the day
        they were written and then drift; this module has already paid that
        exact price once, in the divergent async result shaping that returned
        ``data=None`` on every call.

        Args:
            initial_response: Parsed content of the first page.
            query_params: Original query parameters.
            pagination_params: Pagination configuration (may be empty).
            request_url: Fully-built URL of the originating request.
            request_headers: Headers of the originating request.
            request_timeout: Timeout of the originating request, in seconds.
            request_kwargs: The COMPLETE transport keyword set the originating
                request was issued with, threaded whole -- see
                ``_handle_pagination`` for why dropping it 401s page 2+.
            allowed_origins: The caller's ``allowed_pagination_origins``,
                forwarded verbatim to ``_handle_pagination``. Default ``None``
                keeps an omitted allowlist fail-closed.

        Returns:
            ``(merged_items, pages_merged)``. ``pages_merged`` counts page 1
            plus every follow-up page whose items were actually merged, so a
            trailing empty page -- which ends the loop WITHOUT merging -- is
            not counted.

        Raises:
            NodeExecutionError: Propagated from ``_handle_pagination`` on a
                response-shape mismatch. Deliberately NOT caught here: the two
                callers degrade to page 1 differently (one has a ``None``
                first-page content case the other cannot produce), and
                flattening that difference into this helper would silently
                change what each returns on the failure path.
            NodeValidationError: Propagated -- a mis-configured follow-up
                request must never be swallowed.
        """
        paging_node = copy.copy(self)
        transport = self.http_node
        # Mirrors `_handle_pagination`'s own default for this key.
        items_path = (pagination_params or {}).get("items_path", "data")
        page_tally = {"merged": 1}

        def _counting_execute(**call_kwargs):
            """Count follow-up pages whose items were merged into the result.

            Mirrors the two conditions `_handle_pagination` increments
            `pages_fetched` on -- a successful response whose `items_path`
            yields a non-empty list. On anything else its loop breaks without
            counting the page, and so does this.
            """
            page_result = transport.execute(**call_kwargs)
            if page_result.get("success"):
                page_response = page_result.get("response") or {}
                page_content = page_response.get("content") or {}
                if self._get_nested_value(page_content, items_path, []):
                    page_tally["merged"] += 1
            return page_result

        paging_node.http_node = types.SimpleNamespace(execute=_counting_execute)

        merged = paging_node._handle_pagination(
            initial_response,
            query_params,
            pagination_params,
            request_url=request_url,
            request_headers=request_headers,
            request_timeout=request_timeout,
            request_kwargs=request_kwargs,
            allowed_origins=allowed_origins,
        )
        return merged, page_tally["merged"]

    #: Keys inside the ``pagination`` block that POINT AT A PAGE. A multi-page
    #: merge makes every one of them false: the page they name is already
    #: inside ``data``. Matched case-insensitively; ``has_prev`` is listed
    #: alongside ``has_previous`` because that is the spelling
    #: ``_extract_pagination_metadata`` actually emits, and dropping
    #: ``has_next`` while keeping its own counterpart would be incoherent.
    _STALE_PAGINATION_NAV_KEYS = frozenset(
        {
            "next",
            "next_url",
            "prev",
            "previous",
            "prev_url",
            "has_next",
            "has_prev",
            "has_previous",
        }
    )

    #: Link relations that point at a page rather than describing the
    #: collection. ``self``/``first``/``last`` are deliberately absent: they
    #: still describe the collection after the merge, not the merged window.
    _STALE_LINK_RELS = frozenset({"next", "prev", "previous"})

    @staticmethod
    def _drop_stale_pagination_metadata(
        metadata: dict[str, Any], pages_merged: int
    ) -> dict[str, Any]:
        """Strip the pagination metadata a multi-page merge made false.

        ``metadata`` is assembled from the FIRST page's response, but by the
        time a caller sees it ``data`` may already span N pages. That makes
        SOME of page 1's metadata wrong -- and leaves the rest true. The two
        are separated here rather than discarded together:

        * NAVIGATION pointers -- the ``Link: ...; rel="next"`` header, the
          ``next``/``prev`` relations in the HATEOAS ``links`` block, and the
          ``next``/``prev``/``has_next``/``has_prev`` keys in the
          ``pagination`` block -- name a PAGE. After the merge that page is
          ALREADY inside ``data``, so a consumer following ``links["next"]``
          re-fetches what it was just handed. These are DROPPED.
        * DESCRIPTIVE facts -- ``total``, ``total_pages``, ``page``,
          ``per_page``, ``count``, and the ``self``/``first``/``last``
          relations -- describe the server-side COLLECTION, not the window
          that was merged. The merge does not falsify any of them, so they are
          KEPT. Dropping them was a silent data loss: it took the record count
          with it.

        Keeping the descriptive side is what RESTORES the truncation signal.
        A caller that capped the run with ``max_pages`` can compare
        ``pagination["total_pages"]`` (how many pages exist) against
        ``total_pages_fetched`` (how many it got); when the former exceeds the
        latter the result is truncated. Under the previous
        drop-the-whole-block behaviour a truncated result carried NO signal of
        truncation at all -- which is precisely why the split is drawn here.

        A block left empty by the drop is removed rather than presented as
        ``{}``: an empty block reads as "the server sent no pagination data",
        which is a different and false claim.

        Call this only when pagination RAN -- ``total_pages_fetched`` is a
        pagination fact and is absent from a non-paginated result. Nothing is
        stripped when only one page was fetched: page 1's pointers still
        describe ``data`` exactly, and blanking them would discard true
        information.

        Args:
            metadata: The metadata dict to finalise; mutated in place.
            pages_merged: Page count from ``_paginate_with_page_count``.

        Returns:
            The same ``metadata`` dict, for call-site convenience.
        """
        metadata["total_pages_fetched"] = pages_merged
        if pages_merged > 1:
            cls = RESTClientNode
            for block_key, stale_keys in (
                ("pagination", cls._STALE_PAGINATION_NAV_KEYS),
                ("links", cls._STALE_LINK_RELS),
            ):
                block = metadata.get(block_key)
                if not isinstance(block, dict):
                    continue
                kept = {
                    name: value
                    for name, value in block.items()
                    if not (isinstance(name, str) and name.lower() in stale_keys)
                }
                if kept:
                    metadata[block_key] = kept
                else:
                    # Nothing true survived; an empty block would read as
                    # "the server sent no pagination data".
                    metadata.pop(block_key, None)
            headers = metadata.get("headers")
            if isinstance(headers, dict):
                # Header names are case-insensitive on the wire.
                metadata["headers"] = {
                    name: value
                    for name, value in headers.items()
                    if name.lower() != "link"
                }
        return metadata

    def _get_nested_value(
        self, obj: dict[str, Any], path: str, default: Any | None = None
    ) -> Any:
        """Get a nested value from a dictionary using a dot-separated path.

        Args:
            obj: Dictionary to extract value from
            path: Dot-separated path to the value (e.g., "meta.pagination.next")
            default: Value to return if path doesn't exist

        Returns:
            Value at the specified path or default if not found
        """
        if not path:
            return obj

        parts = path.split(".")
        current = obj

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default

        return current

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute a REST API request.

        Args:
            base_url (str): Base URL for the REST API
            resource (str): API resource path template
            method (str, optional): HTTP method to use
            path_params (dict, optional): Path parameters to substitute
            query_params (dict, optional): Query parameters
            headers (dict, optional): HTTP headers
            data (dict/str, optional): Request body data
            version (str, optional): API version
            timeout (int, optional): Request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            allow_redirects (bool, optional): Whether THIS NODE follows a 3xx,
                re-authorizing every hop against the origin guard and bounded
                by ``_MAX_REDIRECT_HOPS``. The underlying client's automatic
                follow is always off. Defaults to True.
            paginate (bool, optional): Whether to handle pagination
            pagination_params (dict, optional): Pagination configuration
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries
            auth_type (str, optional): Authentication type (bearer, basic, api_key, oauth2)
            auth_token (str, optional): Authentication token/key
            auth_username (str, optional): Username for basic auth
            auth_password (str, optional): Password for basic auth
            api_key_header (str, optional): Header name for API key auth

        Returns:
            Dictionary containing:
                data: Parsed response data
                status_code: HTTP status code
                success: Boolean indicating request success
                metadata: Additional request/response metadata

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails or returns an error status
        """
        base_url = kwargs.get("base_url") or ""
        resource = kwargs.get("resource") or ""
        method = kwargs.get("method", "GET").upper()
        path_params = kwargs.get("path_params", {})
        query_params = kwargs.get("query_params", {})
        headers = kwargs.get("headers", {})
        data = kwargs.get("data")
        version = kwargs.get("version")
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        # Whether the NODE follows a 3xx under the origin guard. The transport
        # is told False either way -- see `_execute_following_redirects`.
        allow_redirects = kwargs.get("allow_redirects", True)
        allowed_pagination_origins = kwargs.get("allowed_pagination_origins")
        paginate = kwargs.get("paginate", False)
        pagination_params = kwargs.get("pagination_params") or {}
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)
        # Authentication parameters
        auth_type = kwargs.get("auth_type")
        auth_token = kwargs.get("auth_token")
        auth_username = kwargs.get("auth_username")
        auth_password = kwargs.get("auth_password")
        api_key_header = kwargs.get("api_key_header", "X-API-Key")

        # Build full URL with path parameters
        url = self._build_url(base_url, resource, path_params, version)

        # Set default Content-Type header for requests with body
        if (
            method in ("POST", "PUT", "PATCH")
            and data
            and "Content-Type" not in headers
        ):
            headers["Content-Type"] = "application/json"

        # Accept JSON responses by default
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        # Build HTTP request parameters
        http_params = {
            "url": url,
            "method": method,
            "headers": headers,
            "params": query_params,
            "json_data": data if isinstance(data, dict) else None,
            "data": data if not isinstance(data, dict) else None,
            "response_format": "json",
            "timeout": timeout,
            "verify_ssl": verify_ssl,
            # The caller's value, threaded so a follow-up page inherits the
            # same policy (`request_kwargs` carries this dict whole). The
            # transport is told False regardless: `_execute_following_redirects`
            # reads this key and then overwrites it.
            "allow_redirects": allow_redirects,
            "retry_count": retry_count,
            "retry_backoff": retry_backoff,
            "auth_type": auth_type,
            "auth_token": auth_token,
            "auth_username": auth_username,
            "auth_password": auth_password,
            "api_key_header": api_key_header,
        }

        # Execute the HTTP request.
        #
        # Masked, and lazily formatted, for parity with `http.py:625`, which
        # does the identical thing correctly. `url` is `base_url` + resource,
        # so it can carry userinfo (`https://svc:pw@host`), a presigned
        # signature, or an `?api_key=` parameter -- an f-string wrote all three
        # verbatim into the log on EVERY request.
        self.logger.info("Making REST %s request to %s", method, mask_url(url))
        result = self._execute_following_redirects(
            http_params,
            allowed_origins=allowed_pagination_origins,
            # The destination is the URL the CALLER built from `base_url` +
            # `resource`; no server-supplied value reaches it. A cross-origin
            # 3xx is therefore followed with credentials stripped rather than
            # refused -- CDN and vanity-domain redirects are routine.
            caller_chosen=True,
        )

        # Extract response data
        response = result.get("response")
        status_code = result.get("status_code")
        success = result.get("success", False)

        # Handle potential error responses
        if not success:
            error_message = result.get("error", "Unknown error")

            # If we have a response object, try to extract error details
            if response and isinstance(response.get("content"), dict):
                # Try to extract error message from common formats
                content = response["content"]
                # Handle case where error is a string or dict
                error_value = content.get("error")
                if isinstance(error_value, dict):
                    error_message = error_value.get("message") or error_message
                elif isinstance(error_value, str):
                    error_message = error_value
                # Check for message at root level
                if not error_message or error_message == result.get(
                    "error", "Unknown error"
                ):
                    error_message = content.get("message") or error_message

            # If we have a status code, include it
            if status_code:
                error_message = f"{error_message} (status: {status_code})"

            # `error_message` is lifted out of the RESPONSE BODY above
            # (`content["error"]` / `content["message"]`), so it is fully
            # server-controlled -- the exact input class `_sanitize_for_log`
            # was added for. Raw CR/LF in it let an upstream forge whole log
            # lines, including lines attributed to another component.
            #
            # Sanitized ONCE, before BOTH surfaces, and the RETURNED value is
            # sanitized too -- not only the logged one. They are different
            # surfaces, and including the returned one is a deliberate call:
            # this field is a human-readable message whose consumers are all
            # line-oriented sinks (a caller's own logger, an exception message,
            # a UI row), so leaving it raw merely moves the forge one hop
            # downstream, to a caller with no reason to suspect it. Nothing the
            # caller needs is lost -- a control character carries no
            # information, and the masking half strips credentials the upstream
            # echoed back into its own error text. Enforcement-surface parity.
            error_message = _sanitize_for_log(error_message)

            self.logger.error("REST API error: %s", error_message)

            # Return error response with recovery suggestions if available
            error_result = {
                "data": None,
                "status_code": status_code,
                "success": False,
                "error": error_message,
                "error_type": result.get("error_type", "APIError"),
                "metadata": {},
            }

            # Include recovery suggestions if available
            if "recovery_suggestions" in result:
                error_result["recovery_suggestions"] = result["recovery_suggestions"]

            return error_result

            # Note: We don't raise an exception here, as the caller might want
            # to handle error responses normally. Instead, we set success=False
            # and include error details in the response.

        # Handle pagination if requested
        data = response["content"] if response else None
        paginated = bool(paginate and method == "GET" and success)
        pages_merged = 1
        if paginated:
            try:
                # Shared with `AsyncRESTClientNode.async_run`: the
                # page-counting proxy lives in ONE place so the two clients
                # cannot drift apart on what a "page" counts as. The whole
                # originating kwarg set is threaded intact -- auth_type /
                # auth_token / auth_username / auth_password / api_key_header /
                # verify_ssl / retry_count / retry_backoff would otherwise be
                # dropped on page 2+, which 401s and silently returns page 1 as
                # the complete result set.
                data, pages_merged = self._paginate_with_page_count(
                    data or {},
                    query_params,
                    pagination_params,
                    request_url=url,
                    request_headers=headers,
                    request_timeout=timeout,
                    request_kwargs=http_params,
                    allowed_origins=allowed_pagination_origins,
                )
            except NodeExecutionError as e:
                # Response-shape mismatches (e.g. items_path is not a list)
                # degrade to the first page. A NodeValidationError — a
                # mis-configured follow-up request — deliberately propagates:
                # returning page 1 as the whole result set is the bug this
                # narrowing exists to prevent.
                self.logger.warning(
                    "Pagination handling failed: %s", mask_error_text(e)
                )

        # Return processed results
        metadata = {
            "url": url,
            "method": method,
        }

        # Add response metadata if available
        if response:
            metadata["response_time_ms"] = response.get("response_time_ms", 0)
            metadata["headers"] = response.get("headers", {})
            # Extract additional metadata
            metadata.update(self._extract_metadata(response))

        if paginated:
            # `response` is still the FIRST page, so the `links` / `pagination`
            # blocks just extracted from it -- and its `Link` header -- describe
            # page 1 alone, while `data` may already span N pages.
            self._drop_stale_pagination_metadata(metadata, pages_merged)

        return {
            "data": data,
            "status_code": status_code,
            "success": success,
            "metadata": metadata,
        }

    # Convenience methods for CRUD operations
    def get(
        self, base_url: str, resource: str, resource_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """GET a resource or list of resources.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            resource_id: Optional resource ID for single resource retrieval
            **kwargs: Additional parameters (query_params, headers, etc.)

        Returns:
            API response dictionary
        """
        if resource_id:
            # Single resource retrieval
            path_params = kwargs.pop("path_params", {})
            path_params["id"] = resource_id
            resource_path = f"{resource}/{{id}}"
        else:
            # List resources
            resource_path = resource
            path_params = kwargs.pop("path_params", {})

        return self.execute(
            base_url=base_url,
            resource=resource_path,
            method="GET",
            path_params=path_params,
            **kwargs,
        )

    def create(
        self, base_url: str, resource: str, data: dict[str, Any], **kwargs
    ) -> dict[str, Any]:
        """CREATE (POST) a new resource.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            data: Resource data to create
            **kwargs: Additional parameters (headers, etc.)

        Returns:
            API response dictionary
        """
        return self.execute(
            base_url=base_url, resource=resource, method="POST", data=data, **kwargs
        )

    def update(
        self,
        base_url: str,
        resource: str,
        resource_id: str,
        data: dict[str, Any],
        partial: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """UPDATE (PUT/PATCH) an existing resource.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            resource_id: Resource ID to update
            data: Updated resource data
            partial: If True, use PATCH for partial update; if False, use PUT
            **kwargs: Additional parameters (headers, etc.)

        Returns:
            API response dictionary
        """
        path_params = kwargs.pop("path_params", {})
        path_params["id"] = resource_id

        return self.execute(
            base_url=base_url,
            resource=f"{resource}/{{id}}",
            method="PATCH" if partial else "PUT",
            path_params=path_params,
            data=data,
            **kwargs,
        )

    def delete(
        self, base_url: str, resource: str, resource_id: str, **kwargs
    ) -> dict[str, Any]:
        """DELETE a resource.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            resource_id: Resource ID to delete
            **kwargs: Additional parameters (headers, etc.)

        Returns:
            API response dictionary
        """
        path_params = kwargs.pop("path_params", {})
        path_params["id"] = resource_id

        return self.execute(
            base_url=base_url,
            resource=f"{resource}/{{id}}",
            method="DELETE",
            path_params=path_params,
            **kwargs,
        )

    def _extract_metadata(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract additional metadata from response.

        Args:
            response: HTTP response dictionary

        Returns:
            Dictionary with extracted metadata
        """
        metadata = {}
        headers = response.get("headers", {})

        # Extract rate limit information
        rate_limit = self._extract_rate_limit_metadata(headers)
        if rate_limit:
            metadata["rate_limit"] = rate_limit

        # Extract pagination metadata
        pagination = self._extract_pagination_metadata(
            headers, response.get("content", {})
        )
        if pagination:
            metadata["pagination"] = pagination

        # Extract HATEOAS links
        links = self._extract_links(response.get("content", {}))
        if links:
            metadata["links"] = links

        return metadata

    def _extract_rate_limit_metadata(
        self, headers: dict[str, str]
    ) -> dict[str, Any] | None:
        """Extract rate limiting information from response headers.

        Args:
            headers: Response headers dictionary

        Returns:
            Rate limit metadata or None if not found
        """
        rate_limit = {}

        # Common rate limit headers
        rate_limit_headers = {
            "X-RateLimit-Limit": "limit",
            "X-RateLimit-Remaining": "remaining",
            "X-RateLimit-Reset": "reset",
            "X-Rate-Limit-Limit": "limit",
            "X-Rate-Limit-Remaining": "remaining",
            "X-Rate-Limit-Reset": "reset",
            "RateLimit-Limit": "limit",
            "RateLimit-Remaining": "remaining",
            "RateLimit-Reset": "reset",
        }

        for header, key in rate_limit_headers.items():
            value = headers.get(header) or headers.get(header.lower())
            if value:
                try:
                    rate_limit[key] = int(value)
                except ValueError:
                    rate_limit[key] = value

        return rate_limit if rate_limit else None

    def _extract_pagination_metadata(
        self, headers: dict[str, str], content: Any
    ) -> dict[str, Any] | None:
        """Extract pagination information from headers and response body.

        Args:
            headers: Response headers dictionary
            content: Response body content

        Returns:
            Pagination metadata or None if not found
        """
        pagination = {}

        # Extract from headers (Link header parsing)
        link_header = headers.get("Link") or headers.get("link")
        if link_header:
            links = self._parse_link_header(link_header)
            pagination.update(links)

        # Extract from response body (common patterns)
        if isinstance(content, dict):
            # Look for common pagination fields
            pagination_fields = {
                "page": ["page", "current_page", "pageNumber"],
                "per_page": ["per_page", "page_size", "pageSize", "limit"],
                "total": ["total", "totalCount", "total_count", "totalRecords"],
                "total_pages": ["total_pages", "totalPages", "pageCount"],
                "has_next": ["has_next", "hasNext", "has_more", "hasMore"],
                "has_prev": ["has_prev", "hasPrev", "has_previous", "hasPrevious"],
            }

            for key, fields in pagination_fields.items():
                for field in fields:
                    # Check in root
                    if field in content:
                        pagination[key] = content[field]
                        break
                    # Check in meta/metadata
                    meta = content.get("meta") or content.get("metadata", {})
                    if isinstance(meta, dict) and field in meta:
                        pagination[key] = meta[field]
                        break

        return pagination if pagination else None

    def _parse_link_header(self, link_header: str) -> dict[str, str]:
        """Parse Link header for pagination URLs.

        Args:
            link_header: Link header value

        Returns:
            Dictionary of rel -> URL mappings
        """
        links = {}

        # Parse Link header format: <url>; rel="next", <url>; rel="prev"
        for link in link_header.split(","):
            link = link.strip()
            if ";" in link:
                url_part, rel_part = link.split(";", 1)
                url = url_part.strip("<>")
                rel_match = rel_part.split("=", 1)
                if len(rel_match) == 2:
                    rel = rel_match[1].strip("\"'")
                    links[rel] = url

        return links

    # ------------------------------------------------------------------
    # Pagination link-following guard
    #
    # ``metadata["links"]["next"]`` is a SERVER-SUPPLIED value. The async
    # pagination loop below issues a follow-up request against it carrying the
    # caller's request headers -- ``Authorization`` included -- so an upstream
    # API that is hostile (or merely compromised) could redirect those
    # credentials to any host it likes, or point the node at ``file:///`` or at
    # the cloud metadata endpoint. The sync ``_handle_pagination`` is immune
    # because no server-supplied value ever reaches its destination URL; this
    # guard gives the async path the same property.
    # ------------------------------------------------------------------

    #: Header names that MAY cross an origin boundary. Everything else is
    #: dropped on an allow-listed CROSS-ORIGIN follow-up page request, and on
    #: every later hop once credentials have been withheld.
    #:
    #: This is an ALLOWLIST, and the inversion is the point. The predecessor
    #: was a six-name denylist (``authorization``/``cookie``/
    #: ``proxy-authorization``/``x-api-key``/``x-auth-token``/``api-key``),
    #: which is the wrong shape at an egress boundary: the set of header names
    #: that carry a credential is unbounded and grows with every vendor, so
    #: ``PRIVATE-TOKEN``, ``X-Vault-Token``, ``Ocp-Apim-Subscription-Key``,
    #: ``X-Amz-Security-Token``, ``X-Shopify-Access-Token``, ``X-Goog-Api-Key``,
    #: ``Circle-Token``, bare ``Token`` and the rest were each a silent leak
    #: until somebody remembered to extend the list. Under an allowlist a new
    #: vendor header is dropped by default and the failure mode is a missing
    #: header, not an exfiltrated secret.
    #:
    #: The node's configured ``api_key_header`` needs no special case here: an
    #: operator-chosen name is by definition not one of the ten below, so it is
    #: dropped like anything else. The former explicit add was deleted rather
    #: than kept -- a second matcher alongside this set is exactly the drift
    #: the inversion exists to end.
    #:
    #: ``X-Tenant``-style caller identity/routing metadata is NOT forward-safe
    #: and is deliberately absent: disclosing a tenant identifier to a
    #: third-party origin is precisely what this boundary exists to prevent.
    _FORWARD_SAFE_HEADERS = frozenset(
        {
            "accept",
            "accept-encoding",
            "accept-language",
            "accept-charset",
            "content-type",
            "user-agent",
            "x-request-id",
            "x-correlation-id",
            "traceparent",
            "tracestate",
        }
    )

    #: Non-literal hostnames that resolve to an internal/metadata endpoint.
    #: Deliberately small -- literal addresses are covered by ``ipaddress``,
    #: and a general DNS-rebinding defense belongs at the transport layer.
    _INTERNAL_HOSTNAMES = frozenset(
        {
            "localhost",
            "metadata",
            "metadata.google.internal",
        }
    )

    @staticmethod
    def _pagination_origin(parsed) -> str | None:
        """Normalize a parsed URL to ``scheme://host:port``.

        Default ports are made explicit so ``http://h:80`` and ``http://h``
        compare equal. Returns None when the URL carries no usable origin.
        """
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if not scheme or not host:
            return None
        try:
            port = parsed.port
        except ValueError:
            # Malformed port ("http://h:notaport") -- no usable origin.
            return None
        if port is None:
            port = {"http": 80, "https": 443}.get(scheme)
        if port is None:
            return None
        return f"{scheme}://{host}:{port}"

    @classmethod
    def _is_internal_host(cls, host: str | None) -> bool:
        """True for loopback / link-local / private / reserved address literals.

        A missing host counts as internal (fail closed). Bracketed IPv6 hosts
        are unwrapped before parsing.
        """
        if not host:
            return True
        candidate = host.strip("[]")
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return candidate.lower() in cls._INTERNAL_HOSTNAMES
        return (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_private
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        )

    @classmethod
    def _normalize_origin_allowlist(cls, allowed_origins: Any) -> set[str]:
        """Normalize caller-supplied origins to the ``_pagination_origin`` form."""
        if not allowed_origins:
            return set()
        if isinstance(allowed_origins, str):
            allowed_origins = [allowed_origins]
        normalized: set[str] = set()
        for entry in allowed_origins:
            if not isinstance(entry, str) or not entry.strip():
                continue
            try:
                origin = cls._pagination_origin(urlparse(entry.strip()))
            except ValueError:
                continue
            if origin:
                normalized.add(origin)
        return normalized

    @classmethod
    def _forward_safe_headers(cls, headers: dict[str, Any]) -> dict[str, Any]:
        """Keep only ``_FORWARD_SAFE_HEADERS``, matching case-insensitively.

        Allowlist, not denylist: a name this set does not recognize is DROPPED.
        A non-string key cannot be matched at all, so it is dropped too (fail
        closed) rather than passed through unexamined.
        """
        return {
            key: value
            for key, value in headers.items()
            if isinstance(key, str) and key.lower() in cls._FORWARD_SAFE_HEADERS
        }

    def _evaluate_pagination_next_link(
        self,
        next_url: Any,
        *,
        request_url: str,
        request_headers: dict[str, Any] | None = None,
        allowed_origins: Any = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        """Decide whether a server-supplied pagination link may be followed.

        Policy, applied in order:

        1. A relative link is resolved against ``base_url`` (the page it was
           found on, which for the first hop is the original request URL).
        2. Any scheme other than ``http``/``https`` is REJECTED -- this covers
           ``file:``, ``javascript:``, ``data:`` and ``gopher:``.
        3. A loopback / link-local / private / reserved / unspecified address
           literal, or a cloud-metadata hostname, is REJECTED unless its origin
           is identical to the original request's origin (so a node pointed at
           ``http://localhost:8000`` still paginates).
        4. Same origin as the original request (scheme + host + port, default
           ports normalized) -> ALLOW, caller's headers forwarded unchanged.
        5. Origin present in ``allowed_pagination_origins`` -> ALLOW, but only
           the ``_FORWARD_SAFE_HEADERS`` allowlist survives; every other
           header -- caller credentials and caller identity metadata alike --
           is DROPPED.
        6. Anything else -> REJECT.

        ``request_url`` stays pinned to the ORIGINAL request for the whole
        pagination run, so an allow-listed third-party origin can never become
        "same origin" on a later hop and win the credentials back.

        Args:
            next_url: The server-supplied link, absolute or relative.
            request_url: The ORIGINAL request URL; sole source of "same origin".
            request_headers: Headers of the originating request.
            allowed_origins: Caller-supplied origin allowlist (may be None).
            base_url: URL of the page the link was found on, for relative
                resolution. Defaults to ``request_url``.

        Returns:
            ``{"allow": bool, "url": str | None, "headers": dict,
            "reason": str | None}``. The caller stops paginating when
            ``allow`` is False; the rejection is already logged here.
        """
        headers = dict(request_headers or {})

        def reject(reason: str, rendered: Any) -> dict[str, Any]:
            # The rejected value is never echoed raw: an embedded credential
            # would otherwise land in the log the rejection exists to protect,
            # and a CR/LF inside a server-supplied link would let that server
            # forge whole log lines. Mask first, then neutralize the control
            # characters the mask does not cover.
            self.logger.warning(
                "Pagination stopped: %s (link=%s)",
                reason,
                _sanitize_for_log(rendered),
            )
            return {
                "allow": False,
                "url": None,
                "headers": {},
                "reason": reason,
                "cross_origin": False,
            }

        if not isinstance(next_url, str) or not next_url.strip():
            return reject("next link is missing or not a string", next_url)

        resolution_base = base_url or request_url or ""
        try:
            resolved = urljoin(resolution_base, next_url.strip())
            parsed = urlparse(resolved)
            origin_parsed = urlparse(request_url or "")
        except ValueError as exc:
            return reject(f"next link is unparseable ({type(exc).__name__})", next_url)

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return reject(f"scheme {scheme!r} is not http(s)", resolved)

        target_origin = self._pagination_origin(parsed)
        if target_origin is None:
            return reject("next link has no usable origin", resolved)
        source_origin = self._pagination_origin(origin_parsed)
        same_origin = source_origin is not None and target_origin == source_origin

        if not same_origin and self._is_internal_host(parsed.hostname):
            return reject("next link targets an internal/reserved address", resolved)

        if same_origin:
            return {
                "allow": True,
                "url": resolved,
                "headers": headers,
                "reason": None,
                "cross_origin": False,
            }

        if target_origin in self._normalize_origin_allowlist(allowed_origins):
            return {
                "allow": True,
                "url": resolved,
                "headers": self._forward_safe_headers(headers),
                "reason": None,
                # The caller's credentials do not go to this origin -- and per
                # the STICKY rule they must not return to the original origin
                # later in the run either.
                "cross_origin": True,
            }

        return reject("next link is cross-origin and not allow-listed", resolved)

    # ------------------------------------------------------------------
    # Redirect-hop policy — SHARED by both transports
    #
    # `_evaluate_pagination_next_link` decides whether a DESTINATION may be
    # requested. This decides whether a `Location` handed back by a hop may
    # become the next destination, and re-enters that same evaluator so the
    # origin policy is defined exactly once. It performs no I/O, so the sync
    # executor below and `AsyncRESTClientNode`'s pagination loop both call it.
    #
    # TWO CALLERS, TWO POLICIES, ONE DIFFERENCE THAT MATTERS -- `caller_chosen`:
    #
    #   * A PAGINATION LINK is a value read out of the response BODY. The
    #     server picked it, so it stays FAIL-CLOSED: a cross-origin destination
    #     that is not in `allowed_pagination_origins` is REFUSED outright.
    #     (`caller_chosen=False` -- the async HATEOAS loop.)
    #
    #   * An INITIAL-REQUEST redirect targets a URL the CALLER chose. Refusing
    #     every cross-origin 3xx would break ordinary APIs: CDN fronting and
    #     vanity-domain redirects are routine, and `requests` followed them
    #     before this guard existed. So a cross-origin hop is FOLLOWED -- but
    #     with the caller's credentials STRIPPED, exactly the treatment an
    #     allow-listed cross-origin pagination hop gets. (`caller_chosen=True`.)
    #
    # WHO CHOSE THE URL is the whole of the distinction, which is why the sync
    # pagination follow-up also passes `caller_chosen=True`: its destination is
    # `request_url`, the caller's own URL with different query parameters -- no
    # server-supplied value reaches it. The async loop's destination IS a
    # server-supplied value, and that is the one that stays fail-closed.
    #
    # Neither policy softens the internal/metadata/loopback/non-HTTP class:
    # `_evaluate_pagination_next_link` rules 2 and 3 refuse those BEFORE the
    # allowlist is consulted, so they are refused on both paths with no
    # exception. The softening is implemented by adding the resolved target to
    # the allowlist passed in, never by overriding a rejection -- a rule that
    # rejects earlier therefore still rejects.
    # ------------------------------------------------------------------

    def _evaluate_redirect_hop(
        self,
        hop_result: Any,
        *,
        request_url: str,
        hop_url: str,
        hop_index: int,
        request_headers: dict[str, Any] | None = None,
        allowed_origins: Any = None,
        credentials_withheld: bool = False,
        caller_chosen: bool = False,
    ) -> dict[str, Any]:
        """Decide whether a 3xx's ``Location`` may become the next request.

        Args:
            hop_result: The transport result of the hop that answered 3xx --
                ``{"response": HTTPResponse.model_dump(), ...}``, the shape
                BOTH ``HTTPRequestNode.execute`` and
                ``AsyncHTTPRequestNode.async_run`` return.
            request_url: The ORIGINAL caller-chosen URL, pinned for the whole
                run. Sole definition of "same origin", so a third-party origin
                can never become same-origin on a later hop and win the
                credentials back.
            hop_url: URL of the hop that issued this ``Location``; the base a
                RELATIVE ``Location`` is resolved against.
            hop_index: 1-based index of this hop. Above ``_MAX_REDIRECT_HOPS``
                the chain stops, the same bound the async pagination loop uses,
                instead of the client default (``requests`` 30, aiohttp 10).
            request_headers: Headers the previous hop was issued with.
            allowed_origins: Caller-supplied origin allowlist (may be None).
            credentials_withheld: True once any earlier hop left the original
                origin. STICKY: credentials are not re-attached for the
                remainder of the run even if a later hop returns home.
            caller_chosen: See the block comment above. True softens a
                cross-origin refusal into a credential-stripped follow.

        Returns:
            ``{"allow", "url", "headers", "reason", "cross_origin",
            "credentials_withheld"}``. The caller stops following when
            ``allow`` is False; the refusal is already logged.
        """

        def refuse(reason: str, rendered: Any = None) -> dict[str, Any]:
            # Never echo the server's value raw: an embedded credential would
            # land in the log this refusal exists to protect, and a CR/LF would
            # let the server forge whole log lines.
            self.logger.warning(
                "Redirect not followed: %s (from=%s)",
                reason,
                _sanitize_for_log(hop_url if rendered is None else rendered),
            )
            return {
                "allow": False,
                "url": None,
                "headers": {},
                "reason": reason,
                "cross_origin": False,
                "credentials_withheld": credentials_withheld,
            }

        if hop_index > _MAX_REDIRECT_HOPS:
            return refuse(f"more than {_MAX_REDIRECT_HOPS} redirect hops")

        response = hop_result.get("response") if isinstance(hop_result, dict) else None
        hop_headers_in = (
            (response.get("headers") or {}) if isinstance(response, dict) else {}
        )
        location = next(
            (
                value
                for name, value in hop_headers_in.items()
                if isinstance(name, str) and name.lower() == "location"
            ),
            None,
        )
        if not isinstance(location, str) or not location.strip():
            # Fail closed: a redirect we cannot follow is not a destination.
            return refuse("redirect carried no Location header")

        try:
            resolved = urljoin(hop_url, location.strip())
        except ValueError as exc:
            return refuse(f"Location is unparseable ({type(exc).__name__})", location)

        effective_allowed = list(self._normalize_origin_allowlist(allowed_origins))
        if caller_chosen:
            # The softening, expressed as an allowlist entry rather than as an
            # override, so every EARLIER rule (non-http scheme, no usable
            # origin, internal/reserved address) still refuses this hop.
            effective_allowed.append(resolved)

        decision = self._evaluate_pagination_next_link(
            resolved,
            request_url=request_url,
            request_headers=request_headers,
            allowed_origins=effective_allowed,
            base_url=hop_url,
        )
        if not decision["allow"]:
            return {**decision, "credentials_withheld": credentials_withheld}

        headers = decision["headers"]
        cross_origin = bool(decision.get("cross_origin"))
        if credentials_withheld:
            headers = self._forward_safe_headers(headers)
        return {
            "allow": True,
            "url": decision["url"],
            "headers": headers,
            "reason": None,
            "cross_origin": cross_origin,
            "credentials_withheld": credentials_withheld or cross_origin,
        }

    def _execute_following_redirects(
        self,
        http_params: dict[str, Any],
        *,
        follow_redirects: bool | None = None,
        allowed_origins: Any = None,
        caller_chosen: bool = False,
    ) -> dict[str, Any]:
        """Issue a SYNC request, following any redirect through the guard.

        ``allow_redirects`` is forced OFF on every transport call: the guard,
        not the HTTP client, decides where a credentialed run may go.
        ``requests`` follows by default, allows 30 hops, and drops only
        ``Authorization`` on a cross-host redirect -- ``Cookie``, ``X-API-Key``
        and any custom API-key header ride along to whatever host the server
        names, including the link-local addresses the guard exists to refuse.

        Both sync request sites go through here so the follow loop exists once.
        The async sibling cannot reuse this (it awaits a different transport)
        but shares the POLICY via ``_evaluate_redirect_hop``.

        Args:
            http_params: The complete transport keyword set for the request.
            follow_redirects: Whether the NODE follows a 3xx. ``None`` (the
                default) reads the caller's ``allow_redirects`` out of
                ``http_params``, which is how a follow-up page inherits it --
                the originating kwarg set is threaded whole, so the policy is
                carried rather than re-derived. False returns the 3xx response
                itself.
            allowed_origins: Caller-supplied origin allowlist (may be None).
            caller_chosen: Whether the destination was chosen by the caller
                rather than read out of a response body -- see the block
                comment above ``_evaluate_redirect_hop``.

        Returns:
            The transport result of the final hop. A refused or unfollowable
            redirect returns the 3xx result itself (the refusal is logged),
            which the caller surfaces as an unsuccessful response rather than
            silently presenting as data.
        """
        call = dict(http_params)
        if follow_redirects is None:
            follow_redirects = bool(call.get("allow_redirects", True))
        # Not `setdefault`: a caller's True must NOT reach the client. The
        # caller's value has already been read out, one line above.
        call["allow_redirects"] = False
        request_url = call.get("url") or ""
        result = self.http_node.execute(**call)
        if not follow_redirects:
            return result

        hop_url = request_url
        credentials_withheld = False
        hop_index = 0
        while True:
            status = result.get("status_code")
            if not (isinstance(status, int) and 300 <= status < 400):
                return result

            hop_index += 1
            decision = self._evaluate_redirect_hop(
                result,
                request_url=request_url,
                hop_url=hop_url,
                hop_index=hop_index,
                request_headers=call.get("headers") or {},
                allowed_origins=allowed_origins,
                credentials_withheld=credentials_withheld,
                caller_chosen=caller_chosen,
            )
            if not decision["allow"]:
                return result

            credentials_withheld = decision["credentials_withheld"]
            call = dict(call)
            call["url"] = decision["url"]
            call["headers"] = decision["headers"]
            # The `Location` carries its own query string; re-appending the
            # originating request's `params` would corrupt the destination.
            # This is also what `requests` does -- it prepares the redirect
            # from the Location alone.
            call["params"] = {}
            if credentials_withheld:
                # Node-level auth is injected as a header by `HTTPRequestNode`
                # ITSELF, from these kwargs rather than from `headers`, so
                # stripping the headers dict alone would still hand the
                # credential to a third-party origin.
                call["auth_type"] = None
                call["auth_token"] = None
                call["auth_username"] = None
                call["auth_password"] = None
            if status in (301, 302, 303) and call.get("method", "GET").upper() not in (
                "GET",
                "HEAD",
            ):
                # Same rewrite `requests` performs: a 303, and by long-standing
                # convention a 301/302 on a POST, continue as a bodiless GET.
                # A 307/308 preserves method and body, so it is left alone.
                call["method"] = "GET"
                call["json_data"] = None
                call["data"] = None
            hop_url = decision["url"]
            result = self.http_node.execute(**call)

    def _build_async_result(
        self, http_result: dict[str, Any], url: str, method: str
    ) -> dict[str, Any]:
        """Shape an ``AsyncHTTPRequestNode.async_run`` return into node output.

        The transport returns ``{"response": HTTPResponse.model_dump(),
        "status_code", "success"}`` -- ``content``, ``headers`` and
        ``response_time_ms`` live INSIDE ``response``, and ``response`` is
        ``None`` on the failure path. Reading ``content``/``headers`` off the
        TOP level (what this node used to do) always yielded ``None``/``{}``,
        which is why every async call reported success with no data and why
        pagination never found a link.
        """
        response = http_result.get("response") or {}
        if not isinstance(response, dict):
            response = {}

        metadata: dict[str, Any] = {"url": url, "method": method}
        if response:
            metadata["response_time_ms"] = response.get("response_time_ms", 0)
            metadata["headers"] = response.get("headers", {}) or {}
            # Rate-limit / pagination / HATEOAS links, same as the sync path.
            metadata.update(self._extract_metadata(response))
        else:
            metadata["headers"] = {}

        return {
            "data": response.get("content"),
            "status_code": http_result.get("status_code"),
            "success": http_result.get("success", False),
            "metadata": metadata,
        }

    def _extract_links(self, content: Any) -> dict[str, Any] | None:
        """Extract HATEOAS links from response content.

        Args:
            content: Response body content

        Returns:
            Links dictionary or None if not found
        """
        if not isinstance(content, dict):
            return None

        links = {}

        # Check common link locations
        link_fields = ["links", "_links", "link", "href"]

        for field in link_fields:
            if field in content:
                link_data = content[field]
                if isinstance(link_data, dict):
                    # HAL format: {"self": {"href": "..."}, "next": {"href": "..."}}
                    for rel, link_obj in link_data.items():
                        if isinstance(link_obj, dict) and "href" in link_obj:
                            links[rel] = link_obj["href"]
                        elif isinstance(link_obj, str):
                            links[rel] = link_obj
                elif isinstance(link_data, list):
                    # Array of link objects
                    for link_obj in link_data:
                        if isinstance(link_obj, dict):
                            rel = link_obj.get("rel", "related")
                            href = link_obj.get("href") or link_obj.get("url")
                            if href:
                                links[rel] = href

        return links if links else None

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute a REST API request asynchronously.

        This method provides true async implementation for REST API calls,
        offering 3-5x performance improvement for I/O-heavy workflows.

        Args:
            Same as run() method

        Returns:
            Same as run() method

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails or returns an error status
        """
        # Use AsyncHTTPRequestNode for true async performance
        if not hasattr(self, "_async_http_node"):
            # Create async HTTP node instance lazily
            from kailash.nodes.api.http import AsyncHTTPRequestNode

            self._async_http_node = AsyncHTTPRequestNode()

        # Extract REST-specific parameters
        base_url = kwargs.get("base_url") or ""
        resource = kwargs.get("resource", "")
        method = kwargs.get("method", "GET").upper()
        path_params = kwargs.get("path_params", {})
        query_params = kwargs.get("query_params", {})
        headers = kwargs.get("headers", {})

        # Build full URL using same logic as sync version
        full_url = self._build_url(
            base_url, resource, path_params, kwargs.get("version")
        )

        # Set default headers (same as sync version)
        if (
            method in ("POST", "PUT", "PATCH")
            and kwargs.get("data")
            and "Content-Type" not in headers
        ):
            headers["Content-Type"] = "application/json"
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        # Execute async HTTP request
        http_result = await self._async_http_node.async_run(  # type: ignore[attr-defined]
            url=full_url,
            method=method,
            headers=headers,
            params=query_params,
            json_data=(
                kwargs.get("data") if isinstance(kwargs.get("data"), dict) else None
            ),
            data=(
                kwargs.get("data") if not isinstance(kwargs.get("data"), dict) else None
            ),
            response_format="json",
            timeout=kwargs.get("timeout", 30),
            verify_ssl=kwargs.get("verify_ssl", True),
        )

        # Process response. content/headers are nested under "response" -- see
        # _build_async_result for why reading them off the top level returned
        # data=None on every async call.
        result = self._build_async_result(http_result, full_url, method)

        # Handle pagination if requested (async version)
        if kwargs.get("paginate", False) and result.get("success", False):
            result = await self._handle_async_pagination(result, kwargs)

        return result

    async def _handle_async_pagination(
        self, initial_result: dict, kwargs: dict
    ) -> dict:
        """Handle pagination asynchronously for better performance.

        Args:
            initial_result: The first page response
            kwargs: Original request parameters

        Returns:
            Combined results from all pages
        """
        pagination_config = kwargs.get("pagination_params") or {}
        max_pages = pagination_config.get("max_pages", 10)
        items_path = pagination_config.get("items_path", "data")
        page_count = 1

        def page_items(payload: Any) -> list[Any] | None:
            """The mergeable item list inside one page, or None.

            A page is ordinarily an envelope (``{"data": [...], "links": …}``)
            -- and it MUST be, because that is the only shape
            ``_extract_links`` can read a ``next`` out of. Merging previously
            required the page itself to BE a list, so on every real HATEOAS
            response the branch never fired: the loop walked and counted each
            page, then discarded all of them and returned page 1. Resolve the
            same ``items_path`` the sync strategies use.
            """
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                found = self._get_nested_value(payload, items_path, None)
                if isinstance(found, list):
                    return found
            return None

        initial_items = page_items(initial_result.get("data"))
        if initial_items is None:
            # Page 1's shape did not RESOLVE -- the body is a dict whose
            # `items_path` is absent. Nothing that follows could ever be merged
            # into it, so do not enter the walk. Previously `all_data` became
            # the page-1 ENVELOPE (a dict), the merge was guarded by
            # `isinstance(all_data, list)` -- False forever -- and every later
            # page was fetched, COUNTED and DISCARDED; the resulting count of
            # >1 then made `_drop_stale_pagination_metadata` strip the `links`
            # the caller needed to walk the pages by hand. Strictly worse than
            # not paginating. Note this is the `None` case ONLY: a page whose
            # `items_path` resolves to an EMPTY list is a well-formed page and
            # still paginates (the loop below handles the empty-page case).
            self.logger.warning(
                "Pagination skipped: items_path %r did not resolve to a list in "
                "the first page's body, so no later page could be merged into "
                "it; returning page 1 with its navigation metadata intact.",
                items_path,
            )
            result = initial_result.copy()
            if isinstance(result.get("metadata"), dict):
                # ONE page merged -- which is the truth, and which keeps the
                # shared stripper's `pages_merged > 1` branch shut so `links` /
                # `pagination` / `Link` survive for a manual walk. Copied first:
                # `.copy()` is shallow.
                result["metadata"] = self._drop_stale_pagination_metadata(
                    dict(result["metadata"]), 1
                )
            return result

        # Copied, never aliased: `extend` on the caller's own list would mutate
        # the response they still hold. Always a list now -- the unresolvable
        # case returned above.
        all_data = list(initial_items)

        # The ORIGINAL request URL. Pinned for the whole run: it is the sole
        # definition of "same origin", so an allow-listed third-party origin
        # cannot become same-origin on a later hop and win the credentials back.
        origin_url = (initial_result.get("metadata") or {}).get("url") or ""
        # URL of the page the next link was read from -- the base for resolving
        # a RELATIVE link. Advances with each hop.
        page_url = origin_url
        request_headers = kwargs.get("headers") or {}
        allowed_origins = kwargs.get("allowed_pagination_origins")
        # No `api_key_header` local here: under the _FORWARD_SAFE_HEADERS
        # allowlist an operator-chosen auth header name is dropped like any
        # other unrecognized name, so the former special case is gone.

        current_result = initial_result
        # STICKY: once a hop has gone to an origin that is not the original,
        # the caller's credentials must not be re-attached for the REMAINDER of
        # the run. Without this, an allow-listed partner can hand back a link
        # to the ORIGINAL origin, which matches the same-origin rule and is
        # fetched with full credentials -- laundering the third party back into
        # the trusted position it was deliberately stripped out of.
        credentials_withheld = False
        # EVERY page URL already requested, not just the most recent one. The
        # sync sibling grew `seen_cursors` (#2231) for exactly this: a server
        # alternating A -> B -> A -> B never compares equal to its immediate
        # predecessor, so a single-slot check runs to `max_pages` re-merging
        # the same pages. This loop needs it MORE, not less -- its next URL is
        # read out of the response BODY, so the cycle is attacker-influenceable.
        # Keyed on the RESOLVED `decision["url"]` (post-guard, post-redirect),
        # never the raw link: the same destination can be spelled several ways.
        # Bounded by construction -- exactly one URL is added per iteration of
        # the `while page_count < max_pages` loop below, so
        # `len(seen_urls) < max_pages` always; the loop bound IS the set bound,
        # and there is no path that adds without iterating.
        seen_urls: set[str] = set()

        while page_count < max_pages:
            # Check for next page link in metadata
            metadata = current_result.get("metadata", {})
            pagination = metadata.get("pagination") or {}
            links = metadata.get("links") or {}

            next_url = links.get("next") or pagination.get("next_url")
            if not next_url:
                break

            # The link came from the response BODY. Validate its origin before
            # it can receive the caller's credentials (the rejection is logged
            # inside the guard). A 3xx answer re-enters this same guard with
            # its `Location`, so the transport never chooses a destination the
            # guard has not authorized.
            candidate = next_url
            candidate_base = page_url
            redirect_hops = 0
            decision = None
            http_result = None
            transport_failed = False

            while True:
                decision = self._evaluate_pagination_next_link(
                    candidate,
                    request_url=origin_url,
                    request_headers=request_headers,
                    allowed_origins=allowed_origins,
                    base_url=candidate_base,
                )
                if not decision["allow"]:
                    break

                if decision["url"] in seen_urls:
                    self.logger.warning(
                        "Pagination stopped: server re-issued page URL %s, which "
                        "was already requested; fetching it again would "
                        "duplicate an earlier page.",
                        _sanitize_for_log(decision["url"]),
                    )
                    # Same signal the redirect-hop ceiling uses: `None` ends the
                    # OUTER loop, so the repeat is refused BEFORE the request.
                    decision = None
                    break

                hop_headers = decision["headers"]
                if credentials_withheld:
                    hop_headers = self._forward_safe_headers(hop_headers)
                if decision.get("cross_origin"):
                    credentials_withheld = True

                try:
                    http_result = await self._async_http_node.async_run(  # type: ignore[attr-defined]
                        url=decision["url"],
                        method="GET",
                        headers=hop_headers,
                        timeout=kwargs.get("timeout", 30),
                        verify_ssl=kwargs.get("verify_ssl", True),
                        # The guard, not the HTTP client, decides where this
                        # run may go. Both clients follow redirects by default
                        # and drop only `Authorization` on a cross-host hop, so
                        # leaving this on would hand `Cookie` / `X-API-Key` to
                        # any host a 3xx names -- including the link-local
                        # addresses rule 3 exists to refuse.
                        allow_redirects=False,
                    )
                except NodeValidationError:
                    # A mis-configured request is a programming/configuration
                    # error, not a transient transport failure -- swallowing it
                    # is what turned a broken follow-up into "page 1 is the
                    # whole result set". Same narrowing as the sync sibling.
                    raise
                except Exception as e:
                    # Transport-level failures degrade to the pages fetched so
                    # far, but they are no longer SILENT.
                    self.logger.warning(
                        "Async pagination request failed: %s", mask_error_text(e)
                    )
                    transport_failed = True
                    break

                status = http_result.get("status_code")
                if not (isinstance(status, int) and 300 <= status < 400):
                    break

                redirect_hops += 1
                if redirect_hops > _MAX_REDIRECT_HOPS:
                    self.logger.warning(
                        "Pagination stopped: more than %d redirect hops from %s",
                        _MAX_REDIRECT_HOPS,
                        _sanitize_for_log(decision["url"]),
                    )
                    decision = None
                    break

                hop_response = http_result.get("response") or {}
                hop_headers_in = (
                    hop_response.get("headers") or {} if hop_response else {}
                )
                location = next(
                    (
                        value
                        for name, value in hop_headers_in.items()
                        if name.lower() == "location"
                    ),
                    None,
                )
                if not location:
                    # Fail closed: a redirect we cannot follow is not a page.
                    self.logger.warning(
                        "Pagination stopped: redirect from %s carried no Location",
                        _sanitize_for_log(decision["url"]),
                    )
                    decision = None
                    break

                candidate = location
                candidate_base = decision["url"]

            if transport_failed or decision is None or not decision["allow"]:
                break

            # The one add per outer iteration the bound above is argued from:
            # only a URL actually fetched is recorded, and an iteration that
            # broke out above recorded nothing.
            seen_urls.add(decision["url"])

            current_result = self._build_async_result(
                http_result or {}, decision["url"], "GET"
            )

            if not current_result.get("success", False):
                break

            fetched = page_items(current_result.get("data"))
            if fetched is None:
                # The shape did not RESOLVE on this page (see the page-1 case
                # above). Distinct from `[]` below: that page was well-formed
                # and simply empty, this one we could not read at all, so say
                # so rather than reporting it as a quiet end-of-data.
                self.logger.warning(
                    "Pagination stopped: items_path %r did not resolve to a "
                    "list in the page fetched from %s.",
                    items_path,
                    _sanitize_for_log(decision["url"]),
                )
                break
            if not fetched:
                # RESOLVED but EMPTY -- end of data. Break WITHOUT counting, so
                # `total_pages_fetched` means "pages MERGED" here exactly as it
                # does on the sync path, whose `_paginate_with_page_count`
                # docstring pins that "a trailing empty page -- which ends the
                # loop WITHOUT merging -- is not counted". Counting the fetch
                # instead let a server of endless empty pages burn the whole
                # `max_pages` budget and report every wasted round-trip as a
                # merged page: one output key, two meanings.
                break

            all_data.extend(fetched)
            page_url = decision["url"]
            page_count += 1

        # Update result with combined data
        result = initial_result.copy()
        result["data"] = all_data
        if isinstance(result.get("metadata"), dict):
            # `metadata` still describes page 1, but `data` now spans
            # `page_count` pages: page 1's `links`/`pagination`/`Link` point at
            # records the caller was just handed. Same shared stripper the
            # page/offset/cursor paths use, so the three pagination strategies
            # cannot drift on what a merged result advertises. Copied first --
            # `initial_result.copy()` is shallow, so mutating the metadata in
            # place would reach back into the caller's own dict.
            result["metadata"] = self._drop_stale_pagination_metadata(
                dict(result["metadata"]), page_count
            )

        return result


@register_node()
class AsyncRESTClientNode(AsyncNode):
    """Asynchronous node for interacting with REST APIs.

    This node provides the same functionality as RESTClientNode but uses
    asynchronous I/O for better performance, especially for concurrent requests.

    Design Purpose:
        * Enable efficient, non-blocking REST API operations in workflows
        * Provide the same interface as RESTClientNode but with async execution
        * Support high-throughput API integrations with minimal overhead

    Upstream Usage:
        * AsyncLocalRuntime: Executes workflow with async support
        * Specialized async API nodes: May extend this node

    Downstream Consumers:
        * Data processing nodes: Consume API response data
        * Decision nodes: Route workflow based on API responses
    """

    def __init__(self, **kwargs):
        """Initialize the async REST client node.

        Args:
            Same as RESTClientNode
        """
        super().__init__(**kwargs)
        self.http_node = AsyncHTTPRequestNode(**kwargs)
        self.rest_node = RESTClientNode(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Delegates to the synchronous node's *class-level* definition rather
        than to ``self.rest_node``. ``Node.__init__`` validates configuration,
        and therefore calls this method, before any subclass ``__init__`` body
        has run — so reading instance state here is unsound regardless of the
        order in which ``__init__`` makes its assignments (issue #2230).

        Returns:
            Dictionary of parameter definitions
        """
        # Same parameters as the synchronous version. RESTClientNode's
        # implementation reads no instance state, so the unbound call is exact.
        # Deliberate: `RESTClientNode.get_parameters` references no
        # instance state, so it is callable before `__init__` assigns the
        # delegates -- which is what stops config validation from failing on
        # every construction of this node.
        return RESTClientNode.get_parameters(self)  # type: ignore[arg-type]

    def get_output_schema(self) -> dict[str, NodeParameter]:
        """Define the output schema for this node.

        Class-level delegation, for the same reason as ``get_parameters``:
        this must not depend on instance state that ``__init__`` establishes.

        Returns:
            Dictionary of output parameter definitions
        """
        # Same output schema as the synchronous version. RESTClientNode's
        # implementation reads no instance state, so the unbound call is exact.
        # Deliberate: `RESTClientNode.get_output_schema` references no
        # instance state, so it is callable before `__init__` assigns the
        # delegates -- which is what stops config validation from failing on
        # every construction of this node.
        return RESTClientNode.get_output_schema(self)  # type: ignore[arg-type]

    def run(self, **kwargs) -> dict[str, Any]:
        """Synchronous version of the REST request, for compatibility.

        This is implemented for compatibility but users should use the
        async_run method for better performance.

        Args:
            Same as RESTClientNode.execute()

        Returns:
            Same as RESTClientNode.execute()

        Raises:
            NodeExecutionError: If the request fails or returns an error status
        """
        # Forward to the synchronous REST node
        return self.rest_node.execute(**kwargs)

    async def _execute_following_redirects_async(
        self,
        http_params: dict[str, Any],
        *,
        follow_redirects: bool | None = None,
        allowed_origins: Any = None,
        caller_chosen: bool = False,
    ) -> dict[str, Any]:
        """Issue an ASYNC request, following any redirect through the guard.

        The async twin of ``RESTClientNode._execute_following_redirects``. The
        POLICY is not duplicated: both loops call the single
        ``_evaluate_redirect_hop``, which performs no I/O precisely so this
        coroutine can reuse it. What cannot be shared is the driving loop --
        the sync executor calls a blocking ``requests``-backed transport, so
        awaiting it here would block the event loop.

        ``allow_redirects`` is forced OFF on every transport call: the guard,
        not the HTTP client, decides where a credentialed run may go. aiohttp
        follows by default (``http.py:923``) and carries EVERY header across a
        cross-host redirect -- it does not even drop ``Authorization``, which
        is the one header ``requests`` drops -- so the server's ``Location``
        chose where the caller's credentials went, past the origin guard, past
        ``_MAX_REDIRECT_HOPS``, and past the internal-address refusal.

        Args:
            http_params: The complete transport keyword set for the request.
            follow_redirects: Whether the NODE follows a 3xx. ``None`` (the
                default) reads the caller's ``allow_redirects`` out of
                ``http_params``. False returns the 3xx response itself.
            allowed_origins: Caller-supplied origin allowlist (may be None).
            caller_chosen: Whether the destination was chosen by the caller
                rather than read out of a response body -- see the block
                comment above ``_evaluate_redirect_hop``.

        Returns:
            The transport result of the final hop. A refused or unfollowable
            redirect returns the 3xx result itself (the refusal is logged),
            which the caller surfaces as an unsuccessful response rather than
            silently presenting as data.
        """
        call = dict(http_params)
        if follow_redirects is None:
            follow_redirects = bool(call.get("allow_redirects", True))
        # Not `setdefault`: a caller's True must NOT reach the client. The
        # caller's value has already been read out, one line above.
        call["allow_redirects"] = False
        request_url = call.get("url") or ""
        result = await self.http_node.async_run(**call)  # type: ignore[attr-defined]
        if not follow_redirects:
            return result

        hop_url = request_url
        credentials_withheld = False
        hop_index = 0
        while True:
            status = result.get("status_code")
            if not (isinstance(status, int) and 300 <= status < 400):
                return result

            hop_index += 1
            decision = self.rest_node._evaluate_redirect_hop(  # type: ignore[attr-defined]
                result,
                request_url=request_url,
                hop_url=hop_url,
                hop_index=hop_index,
                request_headers=call.get("headers") or {},
                allowed_origins=allowed_origins,
                credentials_withheld=credentials_withheld,
                caller_chosen=caller_chosen,
            )
            if not decision["allow"]:
                return result

            credentials_withheld = decision["credentials_withheld"]
            call = dict(call)
            call["url"] = decision["url"]
            call["headers"] = decision["headers"]
            # The `Location` carries its own query string; re-appending the
            # originating request's `params` would corrupt the destination.
            call["params"] = {}
            if credentials_withheld:
                # Node-level auth is injected as a header by
                # `AsyncHTTPRequestNode` ITSELF, from these kwargs rather than
                # from `headers` (`http.py::_apply_authentication`), so
                # stripping the headers dict alone would still hand the
                # credential to a third-party origin.
                call["auth_type"] = None
                call["auth_token"] = None
                call["auth_username"] = None
                call["auth_password"] = None
            if status in (301, 302, 303) and call.get("method", "GET").upper() not in (
                "GET",
                "HEAD",
            ):
                # Same rewrite the sync executor performs, and the same one
                # `requests` performs: a 303, and by long-standing convention a
                # 301/302 on a POST, continue as a bodiless GET. A 307/308
                # preserves method and body, so it is left alone.
                call["method"] = "GET"
                call["json_data"] = None
                call["data"] = None
            hop_url = decision["url"]
            result = await self.http_node.async_run(**call)  # type: ignore[attr-defined]

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute a REST API request asynchronously.

        Args:
            Same as RESTClientNode.execute()

        Returns:
            Same as RESTClientNode.execute()

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails or returns an error status
        """
        base_url = kwargs.get("base_url")
        resource = kwargs.get("resource")
        method = kwargs.get("method", "GET").upper()
        path_params = kwargs.get("path_params", {})
        query_params = kwargs.get("query_params", {})
        headers = kwargs.get("headers", {})
        data = kwargs.get("data")
        version = kwargs.get("version")
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        # Whether the NODE follows a 3xx under the origin guard. The transport
        # is told False either way -- see `_execute_following_redirects_async`.
        allow_redirects = kwargs.get("allow_redirects", True)
        allowed_origins = kwargs.get("allowed_pagination_origins")
        paginate = kwargs.get("paginate", False)
        pagination_params = kwargs.get("pagination_params")
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)
        # Authentication parameters
        auth_type = kwargs.get("auth_type")
        auth_token = kwargs.get("auth_token")
        auth_username = kwargs.get("auth_username")
        auth_password = kwargs.get("auth_password")
        api_key_header = kwargs.get("api_key_header", "X-API-Key")

        # Build full URL with path parameters (reuse from synchronous version)
        url = self.rest_node._build_url(base_url, resource, path_params, version)  # type: ignore[attr-defined]

        # Set default Content-Type header for requests with body
        if (
            method in ("POST", "PUT", "PATCH")
            and data
            and "Content-Type" not in headers
        ):
            headers["Content-Type"] = "application/json"

        # Accept JSON responses by default
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        # Build HTTP request parameters
        http_params = {
            "url": url,
            "method": method,
            "headers": headers,
            "params": query_params,
            "json_data": data if isinstance(data, dict) else None,
            "data": data if not isinstance(data, dict) else None,
            "response_format": "json",
            "timeout": timeout,
            "verify_ssl": verify_ssl,
            # The caller's value, threaded so a follow-up page inherits the
            # same policy (`request_kwargs` carries this dict whole). The
            # transport is told False regardless:
            # `_execute_following_redirects_async` reads this key and then
            # overwrites it.
            "allow_redirects": allow_redirects,
            "retry_count": retry_count,
            "retry_backoff": retry_backoff,
            "auth_type": auth_type,
            "auth_token": auth_token,
            "auth_username": auth_username,
            "auth_password": auth_password,
            "api_key_header": api_key_header,
        }

        # Execute the HTTP request asynchronously.
        #
        # Masked, and lazily formatted, for parity with `http.py:625` and with
        # the synchronous sibling. `url` is `base_url` + resource, so it can
        # carry userinfo (`https://svc:pw@host`), a presigned signature, or an
        # `?api_key=` parameter -- an f-string wrote all three verbatim into
        # the log on EVERY async request.
        self.logger.info("Making async REST %s request to %s", method, mask_url(url))
        result = await self._execute_following_redirects_async(
            http_params,
            allowed_origins=allowed_origins,
            # The destination is the URL the CALLER built from `base_url` +
            # `resource`; no server-supplied value reaches it. A cross-origin
            # 3xx is therefore followed with credentials stripped rather than
            # refused -- CDN and vanity-domain redirects are routine.
            caller_chosen=True,
        )

        # Extract response data
        response = result.get("response")
        status_code = result.get("status_code")
        success = result.get("success", False)

        # Handle potential error responses
        if not success:
            error_message = result.get("error", "Unknown error")

            # If we have a response object, try to extract error details
            if response and isinstance(response.get("content"), dict):
                # Try to extract error message from common formats
                content = response["content"]
                # Handle case where error is a string or dict
                error_value = content.get("error")
                if isinstance(error_value, dict):
                    error_message = error_value.get("message") or error_message
                elif isinstance(error_value, str):
                    error_message = error_value
                # Check for message at root level
                if not error_message or error_message == result.get(
                    "error", "Unknown error"
                ):
                    error_message = content.get("message") or error_message

            # If we have a status code, include it
            if status_code:
                error_message = f"{error_message} (status: {status_code})"

            # `error_message` is lifted out of the RESPONSE BODY above
            # (`content["error"]` / `content["message"]`), so it is fully
            # server-controlled -- the exact input class `_sanitize_for_log`
            # was added for. Raw CR/LF in it let an upstream forge whole log
            # lines, including lines attributed to another component.
            #
            # Sanitized ONCE, before BOTH surfaces, and the RETURNED value is
            # sanitized too -- matching the synchronous site verbatim, so the
            # two paths cannot present the same upstream string differently.
            error_message = _sanitize_for_log(error_message)

            self.logger.error("REST API error: %s", error_message)

            # Return error response with recovery suggestions if available
            error_result = {
                "data": None,
                "status_code": status_code,
                "success": False,
                "error": error_message,
                "error_type": result.get("error_type", "APIError"),
                "metadata": {},
            }

            # Include recovery suggestions if available
            if "recovery_suggestions" in result:
                error_result["recovery_suggestions"] = result["recovery_suggestions"]

            return error_result

        # `success` is True here, so the transport returned a payload -- but
        # nothing in the type says so, and a transport that ever reported
        # success with `response=None` would raise an opaque TypeError from
        # the subscript below rather than a usable result.
        response = response or {}

        # Handle pagination if requested.
        data = response.get("content")
        paginated = bool(paginate and method == "GET" and success)
        pages_fetched = 1
        if paginated:
            # `_handle_pagination` is SYNCHRONOUS: every follow-up page goes
            # through a `requests`-backed node, which blocks the calling
            # thread. Called inline from this coroutine it blocked the EVENT
            # LOOP for up to `(max_pages - 1) * timeout` seconds, starving
            # every other task on it (#2230). Offload it to a worker thread --
            # the same `asyncio.to_thread` offload `base_async.py` uses for its
            # own blocking calls.
            #
            # An async twin of `_handle_pagination` was considered and
            # rejected: it is ~190 lines of page/offset/cursor logic, a
            # seen-cursor set, auth-kwarg threading and masked error sinks,
            # and a second copy would drift from it. This module has already
            # paid that exact price once -- the divergent async result shaping
            # fixed earlier in this same issue. `_handle_async_pagination`
            # remains the async HATEOAS link-following strategy; it is not a
            # substitute for the page/offset/cursor strategy run here.
            try:
                # `_paginate_with_page_count` owns the per-call counting proxy
                # AND the `_handle_pagination` invocation; the synchronous
                # client calls the SAME method. The page-counting semantics
                # therefore exist in exactly one place, so the two clients
                # cannot drift apart on what a "page" counts as. The whole
                # `http_params` dict is threaded through, same as the
                # synchronous caller, so follow-up pages keep the originating
                # request's auth and transport settings.
                data, pages_fetched = await asyncio.to_thread(
                    self.rest_node._paginate_with_page_count,  # type: ignore[attr-defined]
                    # `or {}` matches the synchronous caller: a JSON `null`
                    # body would otherwise reach the pagination walker as None.
                    data or {},
                    query_params,
                    pagination_params,
                    request_url=url,
                    request_headers=headers,
                    request_timeout=timeout,
                    request_kwargs=http_params,
                    allowed_origins=allowed_origins,
                )
            except NodeExecutionError as e:
                # Same split as the synchronous caller: shape mismatches
                # degrade to page 1, configuration errors surface.
                self.logger.warning(
                    "Pagination handling failed: %s", mask_error_text(e)
                )

        # Return processed results. `response` is still the FIRST page, so its
        # navigation headers describe page 1 alone -- see
        # `_drop_stale_pagination_metadata` for why they are not presented
        # verbatim once `data` spans several pages.
        metadata = {
            "url": url,
            "method": method,
            "response_time_ms": response.get("response_time_ms", 0),
            "headers": response.get("headers") or {},
        }
        if paginated:
            # Same helper, and so the same `total_pages_fetched` key, as the
            # synchronous client. This metadata carries no `links`/`pagination`
            # block (it is not built via `_extract_metadata`), so here the
            # helper's strip reduces to the stale `Link` header.
            self.rest_node._drop_stale_pagination_metadata(  # type: ignore[attr-defined]
                metadata, pages_fetched
            )

        return {
            "data": data,
            "status_code": status_code,
            "success": success,
            "metadata": metadata,
        }
