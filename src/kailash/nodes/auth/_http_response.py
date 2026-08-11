"""Unwrap the HTTP node result envelope.

``HTTPRequestNode`` and ``AsyncHTTPRequestNode`` both return

    {"response": <HTTPResponse.model_dump()>, "status_code": ..., "success": ...}

where the parsed body lives at ``response["content"]`` alongside ``headers``,
``content_type``, ``url`` and ``response_time_ms``. Callers in this package read
the identity out of the body, and several of them read ``result["response"]``
directly -- one level too shallow -- so they were looking for ``email`` on the
envelope and always found nothing.

That was invisible while the calls could not execute at all: they awaited
``async_run``/``execute_async`` on the sync ``HTTPRequestNode``, which defines
neither, so every call raised ``AttributeError`` first (issue #2060). Switching
to ``AsyncHTTPRequestNode`` made the calls run and exposed the shallow read
underneath. Both halves are fixed together; fixing only the method name would
have shipped a path that runs, fails to find an identity, and reports it as an
invalid token.
"""

from typing import Any, Dict, Optional

__all__ = ["http_body"]


def http_body(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the parsed body from an HTTP node result.

    Args:
        result: The dict returned by ``HTTPRequestNode`` / ``AsyncHTTPRequestNode``.

    Returns:
        The decoded body as a dict, or ``{}`` when the request produced no
        body, the body was not an object, or the envelope is absent. Returning
        an empty mapping rather than raising keeps the callers' fail-closed
        shape: no body means no identity, which every caller already treats as
        an authentication failure.
    """
    if not isinstance(result, dict):
        return {}

    envelope = result.get("response")
    if not isinstance(envelope, dict):
        return {}

    # An HTTP node envelope always carries "content" (HTTPResponse has
    # status_code/headers/content_type/content/response_time_ms/url). There is
    # deliberately NO fall-back to treating the envelope itself as the body: a
    # bare-body branch fails OPEN in shape, accepting whatever a caller happens
    # to pass, and the only thing it would have accommodated is a test double
    # that does not match the contract it is standing in for.
    body = envelope.get("content")
    return body if isinstance(body, dict) else {}
