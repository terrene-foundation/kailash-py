"""Resource management for Nexus MCP server.

This module implements Phase 3 of the MCP enhancement plan by providing
resource providers for workflow definitions, documentation, and data access.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from kailash.utils.url_credentials import (
    UNPARSEABLE_URL_SENTINEL,
    is_sensitive_query_key,
    mask_url,
)
from kailash.workflow import Workflow
from kailash_mcp import MCPServer

logger = logging.getLogger(__name__)

#: Marker written in place of a credential-bearing value. Deliberately
#: grep-able, and deliberately NOT length-preserving -- a mask that echoed the
#: original length would leak it.
REDACTED = "[REDACTED]"

#: SUPPLEMENT to :func:`kailash.utils.url_credentials.is_sensitive_query_key`,
#: which is the SINGLE SOURCE OF TRUTH for credential-bearing key names
#: (``rules/security.md`` § "No secrets in logs") and is consulted FIRST. It is
#: authoritative but was built for URL QUERY keys, so it does not recognise
#: several families that routinely appear in a NODE CONFIG -- measured:
#: ``connection_string``, ``credentials``, ``passphrase``, ``dsn``, ``bearer``,
#: ``aws_secret_access_key`` and ``session_key`` all return False.
#:
#: These are matched as SUBSTRINGS of the normalized key, not exact members, so
#: ``db_connection_string`` and ``aws_secret_access_key`` are both caught. Add
#: here only what the canonical set genuinely does not cover; never copy an
#: entry that it already handles, or the two lists drift.
_SENSITIVE_CONFIG_SUBSTRINGS = (
    "connstr",
    "connectionstring",
    "credential",
    "passphrase",
    "privatekey",
    "secret",
    "password",
    "token",
    "apikey",
    "bearer",
    "sessionkey",
    "dsn",
    "dburl",
    "databaseurl",
)


def _is_sensitive_config_key(key: str) -> bool:
    """True when a node-config key name is credential-bearing.

    Canonical set first, documented supplement second.
    """
    if is_sensitive_query_key(key):
        return True
    normalized = key.lower().replace("_", "").replace("-", "")
    return any(marker in normalized for marker in _SENSITIVE_CONFIG_SUBSTRINGS)


def redact_config(value: Any) -> Any:
    """Recursively replace credential-bearing values with :data:`REDACTED`.

    Node configuration routinely carries ``api_key``, ``connection_string`` and
    ``password`` entries. ``workflow://{name}`` serves that configuration to any
    MCP client that can reach the resource surface, so it MUST NOT be emitted
    verbatim -- ``rules/security.md`` § "No secrets in logs" applies with more
    force here, because this is a response body rather than a log file.

    Redaction is by KEY NAME, which bounds what it can catch: a secret stored
    under a name neither the canonical set nor the supplement recognises is
    still emitted. Node authors who need a guarantee should keep credentials in
    the environment and reference them by name, which is what
    ``rules/env-models.md`` already requires.
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_sensitive_config_key(str(k)) else redact_config(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_config(item) for item in value]
    if isinstance(value, str) and "://" in value:
        # A URL carries its credential in the VALUE, not the key name, so
        # key-name matching cannot see it: `redis_url` is not in the canonical
        # set and adding a `url` substring would redact every harmless
        # endpoint. Delegate to the canonical masker, which strips userinfo and
        # sensitive query parameters while leaving the host and path readable
        # -- an operator still needs to see WHICH cache the limiter points at.
        # UNPARSEABLE_URL_SENTINEL means it was not a URL after all, so the
        # original is returned rather than a misleading sentinel.
        masked = mask_url(value)
        return value if masked == UNPARSEABLE_URL_SENTINEL else masked
    return value


class NexusResourceManager:
    """Manage resources for Nexus MCP server.

    Provides access to:
    - Workflow definitions and schemas
    - Documentation and help content
    - Data resources (files, databases, etc.)
    - System information and configuration
    """

    def __init__(self, mcp_server: MCPServer, nexus_instance: Any):
        """Initialize resource manager.

        Args:
            mcp_server: The MCP server instance
            nexus_instance: The parent Nexus instance
        """
        self.server = mcp_server
        self.nexus = nexus_instance
        self._setup_default_resources()

    def _setup_default_resources(self):
        """Set up default resource providers.

        URI templates, NOT wildcards (issue #2056)
        ------------------------------------------

        Every provider registers an RFC 6570-style ``{param}`` template whose
        parameter names match its handler's signature exactly. Until #2056
        these registered ``scheme://*`` while the handlers took a single
        ``uri`` argument, and official FastMCP rejects that outright::

            ValueError: Mismatch between URI parameters set() and
                        function parameters {'uri'}

        raised from ``mcp/server/fastmcp/server.py`` at the point where it
        compares ``re.findall(r"{(\\w+)}", uri)`` against the handler's
        parameters. ``*`` declares NO parameters while the handler declared
        one, so ``NexusResourceManager.__init__`` raised for every deployment
        with the official ``mcp`` package installed. ``kailash_mcp``'s own
        non-FastMCP fallback stores handlers under the URI string verbatim and
        imposes no such constraint, so it accepted both forms -- which is why
        the failure looked import-order dependent rather than constant.

        Handlers therefore take the template parameters and RECONSTRUCT the
        full URI for the response's ``uri`` field, which keeps the response
        shape byte-identical to what MCP clients already consume.

        Why ``data://`` is registered at four depths
        --------------------------------------------

        FastMCP compiles a template parameter to ``(?P<name>[^/]+)``
        (``resources/templates.py::ResourceTemplate.matches``), so ONE
        parameter cannot span a ``/``. Measured: with ``data://{path}``
        registered, ``data://examples/sample.json`` -- this module's own
        documented example, pinned by ``test_data_resource_content`` -- does
        not match and would 404. The RFC 6570 explode form ``{path*}`` is not
        supported either; it crashes ``re.compile`` with
        ``bad character in group name 'path*'``.

        Registering one template per depth is the construction FastMCP's
        matcher actually supports. Four is the documented ceiling, and it is a
        real limit rather than a guess: deeper paths simply do not match any
        template and are reported as not found, exactly as an absent file is.
        """

        # Workflow definitions as resources
        @self.server.resource("workflow://{name}")
        async def get_workflow_definition(name: str) -> Dict[str, Any]:
            """Provide workflow definition and schema."""
            return self._workflow_response(name)

        # Documentation resources
        @self.server.resource("docs://{topic}")
        async def get_documentation(topic: str) -> Dict[str, Any]:
            """Provide documentation content."""
            return self._documentation_response(topic)

        # Data resources (files, configurations, etc.). One template per path
        # depth -- see the class docstring for why a single {path} cannot work.
        @self.server.resource("data://{seg1}")
        async def get_data_resource(seg1: str) -> Dict[str, Any]:
            """Provide data resources."""
            return self._data_response(seg1)

        @self.server.resource("data://{seg1}/{seg2}")
        async def get_data_resource_d2(seg1: str, seg2: str) -> Dict[str, Any]:
            """Provide data resources nested one directory deep."""
            return self._data_response(f"{seg1}/{seg2}")

        @self.server.resource("data://{seg1}/{seg2}/{seg3}")
        async def get_data_resource_d3(
            seg1: str, seg2: str, seg3: str
        ) -> Dict[str, Any]:
            """Provide data resources nested two directories deep."""
            return self._data_response(f"{seg1}/{seg2}/{seg3}")

        @self.server.resource("data://{seg1}/{seg2}/{seg3}/{seg4}")
        async def get_data_resource_d4(
            seg1: str, seg2: str, seg3: str, seg4: str
        ) -> Dict[str, Any]:
            """Provide data resources nested three directories deep."""
            return self._data_response(f"{seg1}/{seg2}/{seg3}/{seg4}")

        # Configuration resources
        @self.server.resource("config://{key}")
        async def get_configuration(key: str) -> Dict[str, Any]:
            """Provide configuration information."""
            return self._configuration_response(key)

        # Help resources
        @self.server.resource("help://{topic}")
        async def get_help(topic: str) -> Dict[str, Any]:
            """Provide context-sensitive help."""
            return self._help_response(topic)

        logger.info("Default resource providers configured")

    #: Deepest ``data://`` path the registered templates can match. See
    #: :meth:`_setup_default_resources` for why this is bounded at all.
    DATA_MAX_PATH_SEGMENTS = 4

    def _workflow_response(self, name: str) -> Dict[str, Any]:
        """Build the ``workflow://<name>`` resource payload."""
        uri = f"workflow://{name}"

        if name not in self.nexus._workflows:
            return {
                "uri": uri,
                "mimeType": "application/json",
                "error": f"Workflow '{name}' not found",
            }

        workflow = self.nexus._workflows[name]
        workflow_info = self._extract_workflow_info(name, workflow)

        return {
            "uri": uri,
            "mimeType": "application/json",
            "content": json.dumps(workflow_info, indent=2),
        }

    def _documentation_response(self, topic: str) -> Dict[str, Any]:
        """Build the ``docs://<topic>`` resource payload."""
        uri = f"docs://{topic}"
        doc_content = self._get_documentation(topic)

        if doc_content:
            return {"uri": uri, "mimeType": "text/markdown", "content": doc_content}
        return {
            "uri": uri,
            "mimeType": "text/plain",
            "error": f"Documentation '{topic}' not found",
        }

    def _data_response(self, resource_path: str) -> Dict[str, Any]:
        """Build the ``data://<path>`` resource payload."""
        uri = f"data://{resource_path}"

        # Security check - only allow specific data access
        if not self._is_allowed_resource(resource_path):
            return {
                "uri": uri,
                "mimeType": "application/json",
                "error": "Access denied to this resource",
            }

        content = self._get_data_content(resource_path)
        mime_type = self._get_mime_type(resource_path)

        if content is not None:
            return {"uri": uri, "mimeType": mime_type, "content": content}
        return {
            "uri": uri,
            "mimeType": "application/json",
            "error": f"Resource '{resource_path}' not found",
        }

    def _configuration_response(self, key: str) -> Dict[str, Any]:
        """Build the ``config://<key>`` resource payload."""
        return {
            "uri": f"config://{key}",
            "mimeType": "application/json",
            "content": json.dumps(self._get_configuration(key), indent=2),
        }

    def _help_response(self, topic: str) -> Dict[str, Any]:
        """Build the ``help://<topic>`` resource payload."""
        return {
            "uri": f"help://{topic}",
            "mimeType": "text/markdown",
            "content": self._get_help_content(topic),
        }

    def _extract_workflow_info(self, name: str, workflow: Workflow) -> Dict[str, Any]:
        """Extract comprehensive workflow information.

        Args:
            name: Workflow name
            workflow: Workflow instance

        Returns:
            Dictionary with workflow information
        """
        info = {
            "name": name,
            "type": "workflow",
            "nodes": [],
            "connections": [],
            "metadata": {},
        }

        # Extract metadata if available. Redacted on the same grounds as node
        # config -- metadata is author-supplied and free-form, so it is exactly
        # where a stray credential ends up.
        if hasattr(workflow, "metadata"):
            info["metadata"] = redact_config(workflow.metadata)

        # Extract nodes.
        #
        # `Workflow` exposes `nodes` / `connections`, NOT `_nodes` /
        # `_connections`, and a node is a `NodeInstance` carrying `node_type` +
        # `config` rather than `_config`. The previous probes named the private
        # spellings, so every `hasattr` resolved False and this method returned
        # empty node and connection lists for every workflow -- the same
        # dead-guard silent fallback as #2013, here on the MCP resource surface
        # that AI agents read to discover what a workflow does.
        for node_id, node in (getattr(workflow, "nodes", None) or {}).items():
            info["nodes"].append(
                {
                    "id": node_id,
                    "type": getattr(node, "node_type", type(node).__name__),
                    # REDACTED, not raw. Node config routinely holds api_key /
                    # connection_string / password, and this dict is served to
                    # any MCP client that can read the resource surface. Two
                    # changes in this file made that reachable at once: the
                    # dead-guard fix above (which previously left `nodes` empty
                    # for every real workflow) and #2056's template repair
                    # (`workflow://*` matched nothing, so the handler was never
                    # invoked). Emitting it verbatim would have turned a pair of
                    # correctness fixes into a credential-disclosure surface.
                    "parameters": redact_config(getattr(node, "config", None) or {}),
                }
            )

        # Extract connections. `Connection` is a pydantic model with
        # source_node/source_output/target_node/target_input -- the old
        # `conn.get("source")` would have raised AttributeError had the guard
        # above ever admitted it.
        for conn in getattr(workflow, "connections", None) or []:
            info["connections"].append(
                {
                    "source": getattr(conn, "source_node", None),
                    "output": getattr(conn, "source_output", None),
                    "target": getattr(conn, "target_node", None),
                    "input": getattr(conn, "target_input", None),
                }
            )

        # Add schema information
        info["schema"] = {
            "inputs": redact_config(self._extract_workflow_inputs(workflow)),
            "outputs": redact_config(self._extract_workflow_outputs(workflow)),
        }

        return info

    def _extract_workflow_inputs(self, workflow: Workflow) -> Dict[str, Any]:
        """Extract workflow input schema.

        Attempts to extract schema from workflow metadata. If not available,
        returns empty dict as automatic schema inference is deferred to v1.1.

        TODO v1.1: Implement automatic schema inference by analyzing:
        - Node configurations for parameter references
        - First node in workflow as entry point
        - Parameter usage patterns across workflow
        """
        inputs = {}

        # Extract from explicit metadata if available
        if hasattr(workflow, "metadata") and workflow.metadata:
            # Check for explicit parameters in metadata
            if "parameters" in workflow.metadata:
                return workflow.metadata["parameters"]

            # Check for input_schema in metadata
            if "input_schema" in workflow.metadata:
                return workflow.metadata["input_schema"]

        # Automatic inference not yet implemented - return empty dict
        # Workflows should document their inputs in metadata for now
        return inputs

    def _extract_workflow_outputs(self, workflow: Workflow) -> Dict[str, Any]:
        """Extract workflow output schema.

        Attempts to extract schema from workflow metadata. If not available,
        returns empty dict as automatic schema inference is deferred to v1.1.

        TODO v1.1: Implement automatic schema inference by analyzing:
        - Final nodes in workflow (nodes with no outgoing connections)
        - Node output configurations
        - Common output patterns
        """
        outputs = {}

        # Extract from explicit metadata if available
        if hasattr(workflow, "metadata") and workflow.metadata:
            if "output_schema" in workflow.metadata:
                return workflow.metadata["output_schema"]

        # Automatic inference not yet implemented - return empty dict
        # Workflows should document their outputs in metadata for now
        return outputs

    def _get_documentation(self, doc_path: str) -> Optional[str]:
        """Get documentation content for a given path."""
        # Predefined documentation
        docs = {
            "quickstart": """# Nexus Quick Start Guide

## Getting Started

1. **Install Nexus:**
   ```bash
   pip install kailash-nexus
   ```

2. **Create a simple workflow:**
   ```python
   from nexus import Nexus
   from kailash.workflow.builder import WorkflowBuilder

   app = Nexus()

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'message': 'Hello from Nexus!'}"
   })

   app.register("hello", workflow.build())
   app.start()
   ```

3. **Access your workflow:**
   - API: POST http://localhost:8000/workflows/hello
   - CLI: nexus run hello
   - MCP: Connect AI agent to ws://localhost:3001

## Key Features

- **Zero Configuration**: Works out of the box
- **Multi-Channel**: API, CLI, and MCP from one registration
- **Enterprise Ready**: Built-in auth, monitoring, and scaling
- **AI Native**: Full MCP protocol support for AI agents
""",
            "api": """# Nexus API Reference

## Endpoints

### Execute Workflow
- **POST** `/workflows/{name}`
- **Body**: JSON with workflow parameters
- **Response**: Workflow execution results

### List Workflows
- **GET** `/workflows`
- **Response**: List of registered workflows

### Health Check
- **GET** `/health`
- **Response**: Platform health status

## Authentication

When auth is enabled:
- Include `Authorization: Bearer <token>` header
- Or use API key: `X-API-Key: <key>`

## WebSocket

Real-time updates available at `ws://host:port/ws`
""",
            "mcp": """# MCP Integration Guide

## Connecting AI Agents

Nexus provides full Model Context Protocol support:

### Available Features
- **Tools**: All workflows exposed as executable tools
- **Resources**: Access workflow definitions and docs
- **Prompts**: Pre-configured templates (coming soon)

### Connection
```
ws://localhost:3001
```

### Authentication
Include API key in connection headers when auth is enabled.

### Tool Discovery
Send `tools/list` to discover available workflows.

### Resource Access
- `workflow://<name>` - Workflow definitions
- `docs://<topic>` - Documentation
- `config://<key>` - Configuration
""",
        }

        return docs.get(doc_path)

    def _get_data_content(self, resource_path: str) -> Optional[str]:
        """Get data content for a resource path."""
        # Example: Handle specific data resources
        if resource_path == "examples/sample.json":
            return json.dumps(
                {"example": "data", "timestamp": "2024-01-01T00:00:00Z"}, indent=2
            )

        # Try to read from file system (with security checks).
        #
        # Containment is tested on the REAL canonical form of BOTH sides, per
        # rules/security.md Path Containment. The previous check was
        #     requested_path.startswith(safe_base)
        # over `abspath`-only paths, which is unsound twice over:
        #
        # 1. `startswith` is a PREFIX test, not a boundary test, so a sibling
        #    directory whose name extends the base -- `/srv/database` against a
        #    base of `/srv/data` -- satisfies it.
        # 2. `abspath` normalizes `..` lexically but never resolves SYMLINKS, so
        #    a link inside ./data pointing anywhere on the filesystem passed the
        #    string check and was then read.
        #
        # Resolution failure is treated as denial (fail closed) rather than
        # falling through to the read.
        try:
            safe_base = os.path.realpath("./data")
            requested_path = os.path.realpath(os.path.join(safe_base, resource_path))
        except OSError as exc:
            logger.warning(
                "Refusing data resource %r: path could not be resolved (%s)",
                resource_path,
                type(exc).__name__,
            )
            return None

        # Boundary-aware containment: equal to the base, or beneath it with a
        # separator. `commonpath` raises when the paths share no root (different
        # drives on Windows), which is itself a denial.
        try:
            contained = os.path.commonpath([safe_base, requested_path]) == safe_base
        except ValueError:
            contained = False

        if not contained:
            logger.warning(
                "Refusing data resource %r: resolves outside the data directory",
                resource_path,
            )
            return None

        if not os.path.isfile(requested_path):
            return None

        try:
            # O_NOFOLLOW refuses a symlink at the FINAL component, narrowing the
            # check-to-use window between the realpath above and this open. It
            # does not close it for intermediate directories; a deployment that
            # lets an attacker create links inside ./data needs the directory
            # locked down as well.
            fd = os.open(requested_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                handle = os.fdopen(fd, "r")
            except BaseException:
                # fdopen did not take ownership of the descriptor; close it
                # here. On success the `with` below owns and closes it, so this
                # arm must not also close (that would be a double close).
                os.close(fd)
                raise
            with handle:
                return handle.read()
        except OSError as exc:
            # Logged WITHOUT the resolved absolute path, which would disclose
            # filesystem layout to an MCP client.
            logger.error(
                "Error reading data resource %r: %s", resource_path, type(exc).__name__
            )

        return None

    def _get_mime_type(self, resource_path: str) -> str:
        """Determine MIME type for a resource."""
        ext = os.path.splitext(resource_path)[1].lower()

        mime_types = {
            ".json": "application/json",
            ".xml": "application/xml",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".py": "text/x-python",
            ".yaml": "application/x-yaml",
            ".yml": "application/x-yaml",
        }

        return mime_types.get(ext, "application/octet-stream")

    def _is_allowed_resource(self, resource_path: str) -> bool:
        """Check if a resource path is allowed for access."""
        # Disallow access to sensitive paths
        forbidden_patterns = [
            "..",  # Directory traversal
            "/etc/",  # System configs
            "/proc/",  # Process info
            ".env",  # Environment files
            "secret",  # Anything with 'secret'
            "password",  # Anything with 'password'
            "key",  # Anything with 'key'
        ]

        path_lower = resource_path.lower()
        for pattern in forbidden_patterns:
            if pattern in path_lower:
                return False

        return True

    def _get_configuration(self, config_key: str) -> Dict[str, Any]:
        """Get configuration for a given key."""
        configs = {
            "platform": {
                "name": "Kailash Nexus",
                "version": "1.0.0",
                "api_port": self.nexus._api_port,
                "mcp_port": self.nexus._mcp_port,
                "features": {
                    "auth": self.nexus._enable_auth,
                    "monitoring": self.nexus._enable_monitoring,
                    "discovery": self.nexus._enable_discovery,
                    "transports": self.nexus._get_enabled_transports(),
                },
            },
            "workflows": {
                "registered": list(self.nexus._workflows.keys()),
                "count": len(self.nexus._workflows),
            },
            "limits": {
                # Redacted for the same reason as node config: a rate-limit
                # config carries `redis_url`, which embeds a password.
                "rate_limit": redact_config(self.nexus.rate_limit_config),
                "max_workflows": 1000,
                "max_connections": 10000,
            },
        }

        return configs.get(
            config_key, {"error": f"Unknown configuration key: {config_key}"}
        )

    def _get_help_content(self, help_topic: str) -> str:
        """Get help content for a topic."""
        help_topics = {
            "getting-started": """# Getting Started with Nexus

1. Create a Nexus instance
2. Register your workflows
3. Start the platform
4. Access via API, CLI, or MCP

Need more help? Check:
- docs://quickstart - Quick start guide
- docs://api - API reference
- docs://mcp - MCP integration
""",
            "workflows": """# Working with Workflows

Workflows are the core of Nexus. Each workflow:
- Can contain multiple nodes
- Processes data through connections
- Is accessible via all channels

To see available workflows:
- API: GET /workflows
- MCP: Send tools/list
- Resources: workflow://<name>
""",
            "troubleshooting": """# Troubleshooting

Common issues:

**Port already in use:**
- Change ports: `Nexus(api_port=8080, mcp_port=3002)`

**Workflow not found:**
- Check registration: `app.register("name", workflow)`
- Ensure workflow is built: `workflow.build()`

**Connection refused:**
- Check if Nexus is running: `app.start()`
- Verify firewall settings
""",
        }

        content = help_topics.get(help_topic)
        if content:
            return content

        # Default help
        return f"""# Help: {help_topic}

No specific help available for '{help_topic}'.

Available help topics:
- help://getting-started
- help://workflows
- help://troubleshooting

Or check documentation:
- docs://quickstart
- docs://api
- docs://mcp
"""

    def register_custom_resource(self, pattern: str, handler: Any):
        """Register a custom resource handler.

        Args:
            pattern: URI template whose ``{param}`` placeholders match
                ``handler``'s parameter names EXACTLY -- e.g.
                ``"custom://{name}"`` for ``async def handler(name: str)``, or
                a parameterless concrete URI like ``"custom://status"`` for
                ``async def handler()``.

                The example here used to read ``"custom://*"``. That form is
                rejected by official FastMCP, which raises ``ValueError:
                Mismatch between URI parameters ... and function parameters
                ...`` because ``*`` declares no parameters (issue #2056). A
                template parameter matches ``[^/]+`` and so cannot span ``/``;
                register one template per path depth if the handler needs
                nested paths, as the built-in ``data://`` provider does.
            handler: Async function to handle resource requests.
        """
        self.server.resource(pattern)(handler)
        logger.info(f"Registered custom resource handler for {pattern}")
