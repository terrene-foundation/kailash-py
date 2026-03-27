# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""The ``search_tools`` meta-tool for tool discovery.

This tool enables the LLM to search over available tools by name and
description when the tool set is too large to send in full. The LLM
decides when to search -- this is a dumb data endpoint that returns
matching tool schemas.

The tool is registered as a built-in when hydration is active. It uses
BM25-style scoring from :mod:`kaizen_agents.delegate.tools.hydrator`
with no external dependencies.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from kaizen_agents.delegate.tools.hydrator import ToolHydrator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schema (OpenAI function-calling format)
# ---------------------------------------------------------------------------

SEARCH_TOOLS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_tools",
        "description": (
            "Search for available tools by keyword. Use this when you need a "
            "tool that is not in your current active set. Returns matching "
            "tool names, descriptions, and relevance scores. After finding "
            "the tools you need, they will be automatically added to your "
            "active tool set for the rest of this conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query describing what tool you need. "
                        "Use descriptive terms like 'database query', "
                        "'send email', 'kubernetes deploy', etc."
                    ),
                },
                "top_n": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 10.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# Executor factory
# ---------------------------------------------------------------------------


def create_search_tools_executor(
    hydrator: ToolHydrator,
) -> Any:
    """Create the async executor for the ``search_tools`` meta-tool.

    The executor searches the hydrator's index and automatically hydrates
    the matching tools into the active set so they are available on the
    next LLM call.

    Parameters
    ----------
    hydrator:
        The :class:`ToolHydrator` instance to search and hydrate from.

    Returns
    -------
    An async callable that accepts ``query`` and optional ``top_n``,
    returning a JSON string with search results.
    """

    async def _execute_search_tools(query: str, top_n: int = 10) -> str:
        """Search for tools and hydrate matches into the active set."""
        if not query or not query.strip():
            return json.dumps({"error": "Empty search query", "results": []})

        results = hydrator.search(query, top_n=top_n)

        if not results:
            return json.dumps(
                {
                    "query": query,
                    "results": [],
                    "message": "No matching tools found. Try different keywords.",
                }
            )

        # Auto-hydrate the found tools so they are available on the next turn
        found_names = [r["name"] for r in results]
        hydrated = hydrator.hydrate(found_names)

        logger.info(
            "search_tools query=%r found=%d hydrated=%d",
            query,
            len(results),
            len(hydrated),
        )

        return json.dumps(
            {
                "query": query,
                "results": results,
                "hydrated": hydrated,
                "message": (
                    f"Found {len(results)} tools. "
                    f"{len(hydrated)} tools have been added to your active set "
                    f"and are now available for use."
                ),
            },
            indent=2,
        )

    return _execute_search_tools
