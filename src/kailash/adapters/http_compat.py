"""HTTP transport-layer adapter for Kailash engine code.

Framework-first policy (see ``.claude/rules/framework-first.md``) requires
that engine-level code in ``src/kailash/`` (servers, middleware, durable
gateway, etc.) not import FastAPI directly. Raw HTTP library imports
belong in the adapter/transport layer — which is what this module is.

Engine modules import from here instead of importing from ``fastapi``
directly. When Waves 2-3 of the FastAPI -> Nexus migration land and
the base classes (``WorkflowServer``, ``WorkflowAPIGateway``) move to
pure Nexus primitives, this adapter is the single place to update.

The symbols exposed here intentionally mirror the FastAPI/Starlette
runtime objects that ``WorkflowServer.self.app`` (currently a FastAPI
instance) produces. Once the base classes no longer use FastAPI, this
file is the migration seam — either remapped to Nexus equivalents or
deleted entirely.
"""

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

__all__ = [
    "HTTPException",
    "Request",
    "Response",
    "JSONResponse",
    "HTTPAuthorizationCredentials",
    "HTTPBearer",
]
