# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
JSON-RPC 2.0 Handler for A2A Protocol.

Implements the JSON-RPC 2.0 specification for A2A method calls
including agent invocation, trust verification, and delegation.
"""

import json
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from eatp.a2a.exceptions import (
    A2AError,
    JsonRpcInternalError,
    JsonRpcInvalidParamsError,
    JsonRpcInvalidRequestError,
    JsonRpcMethodNotFoundError,
    JsonRpcParseError,
)
from eatp.a2a.models import (
    AuditQueryRequest,
    AuditQueryResponse,
    DelegationRequest,
    DelegationResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    VerificationRequest,
    VerificationResponse,
)

logger = logging.getLogger(__name__)

# Type alias for JSON-RPC method handlers
MethodHandler = Callable[[Dict[str, Any], Optional[str]], Coroutine[Any, Any, Any]]


class JsonRpcHandler:
    """
    JSON-RPC 2.0 compliant request handler.

    Handles A2A method dispatch including:
    - agent.invoke: Invoke agent with task
    - agent.capabilities: Get agent capabilities
    - trust.verify: Verify agent trust chain
    - trust.delegate: Delegate capabilities
    - audit.query: Query audit trail

    Example:
        >>> handler = JsonRpcHandler()
        >>> handler.register_method("agent.capabilities", get_capabilities)
        >>> response = await handler.handle(request_data, auth_token)
    """

    # Methods that don't require authentication
    PUBLIC_METHODS = {"agent.capabilities", "trust.verify"}

    def __init__(self):
        """Initialize the JSON-RPC handler."""
        self._methods: Dict[str, MethodHandler] = {}

    def register_method(self, name: str, handler: MethodHandler) -> None:
        """
        Register a method handler.

        Args:
            name: Method name (e.g., "agent.invoke").
            handler: Async function to handle the method.
        """
        self._methods[name] = handler
        logger.debug(f"Registered JSON-RPC method: {name}")

    def unregister_method(self, name: str) -> None:
        """
        Unregister a method handler.

        Args:
            name: Method name to unregister.
        """
        if name in self._methods:
            del self._methods[name]

    def get_registered_methods(self) -> List[str]:
        """Get list of registered method names."""
        return list(self._methods.keys())

    async def handle(
        self,
        data: bytes | str | Dict[str, Any],
        auth_token: Optional[str] = None,
    ) -> JsonRpcResponse:
        """
        Handle a JSON-RPC request.

        Args:
            data: Raw request data (bytes, str, or parsed dict).
            auth_token: Optional authentication token.

        Returns:
            JsonRpcResponse with result or error.
        """
        request_id: Optional[int | str] = None
        start_time = time.time()

        try:
            # Parse request
            request = self._parse_request(data)
            request_id = request.id

            # Validate request
            self._validate_request(request)

            # Check authentication for protected methods
            if request.method not in self.PUBLIC_METHODS:
                if not auth_token:
                    from eatp.a2a.exceptions import AuthenticationError

                    raise AuthenticationError(f"Authentication required for method: {request.method}")

            # Dispatch to handler
            if request.method not in self._methods:
                raise JsonRpcMethodNotFoundError(request.method)

            handler = self._methods[request.method]
            result = await handler(request.params or {}, auth_token)

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"JSON-RPC {request.method} completed in {elapsed_ms:.1f}ms")

            return JsonRpcResponse.success(request_id, result)

        except JsonRpcParseError:
            # Re-raise parse errors to be handled at HTTP layer (400 status)
            raise
        except A2AError as e:
            logger.warning(f"A2A error: {e.message} (code={e.code})")
            return JsonRpcResponse.create_error(request_id, e.code, e.message, e.data)
        except Exception as e:
            logger.exception(f"Internal error handling JSON-RPC request: {e}")
            return JsonRpcResponse.create_error(
                request_id,
                -32603,
                "Internal error",
                {"detail": str(e)},
            )

    async def handle_batch(
        self,
        data: bytes | str | List[Dict[str, Any]],
        auth_token: Optional[str] = None,
    ) -> List[JsonRpcResponse]:
        """
        Handle a batch of JSON-RPC requests.

        Args:
            data: Raw batch request data.
            auth_token: Optional authentication token.

        Returns:
            List of JsonRpcResponse objects.
        """
        try:
            if isinstance(data, (bytes, str)):
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                requests = json.loads(data)
            else:
                requests = data

            if not isinstance(requests, list):
                raise JsonRpcInvalidRequestError("Batch request must be an array")

            if len(requests) == 0:
                raise JsonRpcInvalidRequestError("Empty batch request")

            responses = []
            for req_data in requests:
                response = await self.handle(req_data, auth_token)
                # Only include responses for requests with id (not notifications)
                if "id" in req_data and req_data["id"] is not None:
                    responses.append(response)

            return responses

        except json.JSONDecodeError as e:
            raise JsonRpcParseError(f"Invalid JSON: {e}")

    def _parse_request(self, data: bytes | str | Dict[str, Any]) -> JsonRpcRequest:
        """Parse raw data into JsonRpcRequest."""
        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if isinstance(data, str):
                data = json.loads(data)
            return JsonRpcRequest.from_dict(data)
        except json.JSONDecodeError as e:
            raise JsonRpcParseError(f"Invalid JSON: {e}")
        except Exception as e:
            raise JsonRpcInvalidRequestError(f"Cannot parse request: {e}")

    def _validate_request(self, request: JsonRpcRequest) -> None:
        """Validate JSON-RPC request structure."""
        if request.jsonrpc != "2.0":
            raise JsonRpcInvalidRequestError(f"Invalid jsonrpc version: {request.jsonrpc}")
        if not request.method:
            raise JsonRpcInvalidRequestError("Missing method")
        if not isinstance(request.method, str):
            raise JsonRpcInvalidRequestError("Method must be a string")
        if request.params is not None and not isinstance(request.params, dict):
            # We only support named params, not positional
            raise JsonRpcInvalidParamsError("Parameters must be an object (named parameters)")


class A2AMethodHandlers:
    """
    Default method handlers for A2A protocol.

    Provides implementation for standard A2A methods:
    - agent.invoke
    - agent.capabilities
    - trust.verify
    - trust.delegate
    - audit.query
    """

    def __init__(
        self,
        trust_operations: "TrustOperations",
        agent_id: str,
        capabilities: List[str],
        invoke_handler: Optional[MethodHandler] = None,
    ):
        """
        Initialize A2A method handlers.

        Args:
            trust_operations: TrustOperations for trust methods.
            agent_id: This agent's identifier.
            capabilities: List of capabilities this agent supports.
            invoke_handler: Optional custom handler for agent.invoke.
        """
        from eatp.operations import TrustOperations

        self._trust_ops = trust_operations
        self._agent_id = agent_id
        self._capabilities = capabilities
        self._invoke_handler = invoke_handler

    async def handle_capabilities(
        self,
        params: Dict[str, Any],
        auth_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Handle agent.capabilities method.

        Returns the agent's capabilities without requiring authentication.
        """
        return {
            "agent_id": self._agent_id,
            "capabilities": self._capabilities,
        }

    async def handle_verify(
        self,
        params: Dict[str, Any],
        auth_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Handle trust.verify method.

        Verifies an agent's trust chain at the requested level.
        """
        agent_id = params.get("agent_id")
        if not agent_id:
            raise JsonRpcInvalidParamsError("Missing required parameter: agent_id")

        level_str = params.get("verification_level", "STANDARD").upper()
        from eatp.chain import VerificationLevel

        try:
            level = VerificationLevel[level_str]
        except KeyError:
            raise JsonRpcInvalidParamsError(
                f"Invalid verification_level: {level_str}. Must be one of: QUICK, STANDARD, FULL"
            )

        start_time = time.time()
        result = await self._trust_ops.verify(agent_id, level=level)
        latency_ms = (time.time() - start_time) * 1000

        # Build trust chain summary if valid
        chain_summary = None
        if result.valid:
            try:
                chain = await self._trust_ops.get_chain(agent_id)
                if chain:
                    chain_summary = {
                        "genesis_authority": chain.genesis.authority_id,
                        "capabilities_count": len(chain.capabilities),
                        "delegations_count": len(chain.delegations),
                    }
            except Exception:
                pass

        # VerificationResult uses 'violations' and 'reason', not 'errors'
        errors = []
        if result.reason:
            errors.append(result.reason)
        errors.extend([str(v) for v in result.violations])

        return VerificationResponse(
            valid=result.valid,
            agent_id=agent_id,
            verification_level=level_str,
            errors=errors,
            trust_chain_summary=chain_summary,
            latency_ms=latency_ms,
        ).to_dict()

    async def handle_delegate(
        self,
        params: Dict[str, Any],
        auth_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Handle trust.delegate method.

        Creates a delegation from the authenticated agent to the delegatee.
        """
        from eatp.a2a.exceptions import AuthenticationError

        if not auth_token:
            raise AuthenticationError("Authentication required for delegation")

        # Extract parameters
        delegatee_id = params.get("delegatee_agent_id")
        task_id = params.get("task_id")
        capabilities = params.get("capabilities", [])
        constraints = params.get("constraints", {})

        if not delegatee_id:
            raise JsonRpcInvalidParamsError("Missing required parameter: delegatee_agent_id")
        if not task_id:
            raise JsonRpcInvalidParamsError("Missing required parameter: task_id")
        if not capabilities:
            raise JsonRpcInvalidParamsError("Missing required parameter: capabilities")

        # Create delegation
        try:
            delegation = await self._trust_ops.delegate(
                delegator_agent_id=self._agent_id,
                delegatee_agent_id=delegatee_id,
                task_id=task_id,
                capabilities=capabilities,
                constraints=constraints,
            )

            return DelegationResponse(
                delegation_id=delegation.id,
                delegator_agent_id=delegation.delegator_agent_id,
                delegatee_agent_id=delegation.delegatee_agent_id,
                task_id=delegation.task_id,
                capabilities_delegated=delegation.capabilities_delegated,
                constraints=delegation.constraints,
                delegated_at=delegation.delegated_at,
                expires_at=delegation.expires_at,
                signature=delegation.signature,
            ).to_dict()

        except Exception as e:
            from eatp.a2a.exceptions import DelegationError

            raise DelegationError(str(e))

    async def handle_audit_query(
        self,
        params: Dict[str, Any],
        auth_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Handle audit.query method.

        Queries the audit trail for the specified agent.
        """
        from eatp.a2a.exceptions import AuthenticationError

        if not auth_token:
            raise AuthenticationError("Authentication required for audit query")

        agent_id = params.get("agent_id")
        if not agent_id:
            raise JsonRpcInvalidParamsError("Missing required parameter: agent_id")

        # Build query
        from datetime import datetime

        start_time = params.get("start_time")
        end_time = params.get("end_time")
        action_type = params.get("action_type")
        resource_uri = params.get("resource_uri")
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)

        # Parse datetime strings
        start_dt = None
        end_dt = None
        if start_time:
            start_dt = datetime.fromisoformat(start_time)
        if end_time:
            end_dt = datetime.fromisoformat(end_time)

        # Query audit service
        try:
            from eatp.audit_service import AuditQueryService

            audit_service = AuditQueryService(self._trust_ops._audit_store)

            actions = await audit_service.query_actions(
                agent_id=agent_id,
                start_time=start_dt,
                end_time=end_dt,
                action_type=action_type,
                resource_uri=resource_uri,
                limit=limit,
                offset=offset,
            )

            # Get delegation chain if available
            delegation_chain = None
            try:
                chain = await self._trust_ops.get_chain(agent_id)
                if chain and chain.delegations:
                    delegation_chain = [
                        {
                            "delegator": d.delegator_agent_id,
                            "delegatee": d.delegatee_agent_id,
                            "task_id": d.task_id,
                            "capabilities": d.capabilities_delegated,
                            "delegated_at": d.delegated_at.isoformat(),
                        }
                        for d in chain.delegations
                    ]
            except Exception:
                pass

            return AuditQueryResponse(
                agent_id=agent_id,
                total_count=len(actions),
                actions=[a.to_dict() for a in actions],
                delegation_chain=delegation_chain,
            ).to_dict()

        except Exception as e:
            raise JsonRpcInternalError(f"Audit query failed: {e}")

    async def handle_invoke(
        self,
        params: Dict[str, Any],
        auth_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Handle agent.invoke method.

        Invokes the agent with the given task. Requires custom implementation.
        """
        from eatp.a2a.exceptions import AuthenticationError

        if not auth_token:
            raise AuthenticationError("Authentication required for agent invocation")

        if self._invoke_handler:
            return await self._invoke_handler(params, auth_token)

        # Default: return method not implemented
        raise JsonRpcMethodNotFoundError("agent.invoke not implemented for this agent")

    def register_all(self, handler: JsonRpcHandler) -> None:
        """Register all A2A methods with the handler."""
        handler.register_method("agent.capabilities", self.handle_capabilities)
        handler.register_method("agent.invoke", self.handle_invoke)
        handler.register_method("trust.verify", self.handle_verify)
        handler.register_method("trust.delegate", self.handle_delegate)
        handler.register_method("audit.query", self.handle_audit_query)
