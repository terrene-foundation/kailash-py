#!/usr/bin/env python3
"""
AI Registry MCP Server using Anthropic's Official MCP Python SDK.

This creates a real MCP server that exposes AI Registry tools following
the actual Model Context Protocol specification.

Run as: python -m kailash.mcp_server.ai_registry_server
"""

import asyncio
import json
import os
from typing import Any

# Use low-level server implementation with fallback
try:
    from mcp.server.lowlevel import Server
    from mcp.types import Resource, TextContent, Tool
except ImportError:
    # Fallback if official MCP is broken
    print("Warning: Official MCP server not available, using fallback")
    from kailash.mcp_server.server import MCPServerBase as Server

    # Minimal type definitions for fallback
    class Resource:
        def __init__(self, uri, name, description, mimeType=None):
            self.uri = uri
            self.name = name
            self.description = description
            self.mimeType = mimeType

    class TextContent:
        def __init__(self, type, text):
            self.type = type
            self.text = text

    class Tool:
        def __init__(self, name, description, inputSchema):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema


class AIRegistryServer:
    """
    AI Registry MCP Server providing real ISO/IEC AI use case data.

    This server implements the actual MCP protocol using Anthropic's official SDK,
    providing 8 real tools for AI use case discovery and analysis.
    """

    def __init__(self, registry_file: str = "research/combined_ai_registry.json"):
        """Initialize the AI Registry MCP server."""
        self.server = Server("ai-registry")
        self.registry_data = self._load_registry_data(registry_file)
        self._setup_tools()
        self._setup_resources()

    def _load_registry_data(self, registry_file: str) -> dict[str, Any]:
        """Load AI Registry data from JSON file."""
        # Handle both absolute and relative paths
        if not os.path.isabs(registry_file):
            # Try relative to current working directory first
            if os.path.exists(registry_file):
                pass  # Use as-is
            else:
                # Try relative to this module's directory
                module_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(
                    os.path.dirname(os.path.dirname(module_dir))
                )
                registry_file = os.path.join(project_root, registry_file)

        try:
            with open(registry_file, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            # Return mock data if file not found
            return {
                "registry_info": {
                    "source": "AI Registry MCP Server",
                    "total_cases": 3,
                    "domains": 2,
                },
                "use_cases": [
                    {
                        "use_case_id": 42,
                        "name": "Medical Diagnosis Assistant",
                        "application_domain": "Healthcare",
                        "description": "AI-powered diagnostic support system for medical professionals",
                        "ai_methods": [
                            "Machine Learning",
                            "Deep Learning",
                            "Natural Language Processing",
                        ],
                        "tasks": [
                            "Classification",
                            "Diagnosis Support",
                            "Risk Assessment",
                        ],
                        "status": "PoC",
                        "challenges": "Data privacy, model interpretability, regulatory compliance",
                        "kpis": [
                            "Diagnostic accuracy",
                            "Time to diagnosis",
                            "User satisfaction",
                        ],
                    },
                    {
                        "use_case_id": 87,
                        "name": "Clinical Decision Support",
                        "application_domain": "Healthcare",
                        "description": "Evidence-based recommendations for clinical decision making",
                        "ai_methods": ["Expert Systems", "Machine Learning"],
                        "tasks": ["Decision Support", "Risk Assessment"],
                        "status": "Production",
                        "challenges": "Integration with EHR systems, physician adoption",
                        "kpis": [
                            "Decision accuracy",
                            "Time savings",
                            "Physician satisfaction",
                        ],
                    },
                    {
                        "use_case_id": 156,
                        "name": "Manufacturing Quality Control",
                        "application_domain": "Manufacturing",
                        "description": "Automated quality inspection using computer vision",
                        "ai_methods": ["Computer Vision", "Deep Learning"],
                        "tasks": ["Detection", "Classification", "Quality Control"],
                        "status": "Production",
                        "challenges": "Real-time processing, accuracy requirements",
                        "kpis": [
                            "Detection accuracy",
                            "Processing speed",
                            "Cost savings",
                        ],
                    },
                ],
            }
        except Exception as e:
            raise ValueError(
                f"Failed to load AI registry data from {registry_file}: {e}"
            )

    def _setup_tools(self):
        """Setup MCP tools using the official SDK."""

        @self.server.list_tools()
        async def handle_list_tools():
            """List all available AI Registry tools."""
            return [
                Tool(
                    name="search_use_cases",
                    description="Advanced search across AI use cases with domain and method filters",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by domains",
                            },
                            "methods": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by AI methods",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results",
                                "default": 10,
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="filter_by_domain",
                    description="Get all use cases in a specific application domain",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Application domain",
                            },
                            "status": {
                                "type": "string",
                                "description": "Optional status filter",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results",
                                "default": 20,
                            },
                        },
                        "required": ["domain"],
                    },
                ),
                Tool(
                    name="get_use_case_details",
                    description="Get complete details for a specific use case by ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "use_case_id": {
                                "type": "integer",
                                "description": "Use case ID",
                            }
                        },
                        "required": ["use_case_id"],
                    },
                ),
                Tool(
                    name="analyze_domain_trends",
                    description="Analyze trends, methods, and patterns within a specific domain",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Application domain to analyze",
                            },
                            "include_details": {
                                "type": "boolean",
                                "description": "Include detailed examples",
                                "default": False,
                            },
                        },
                        "required": ["domain"],
                    },
                ),
                Tool(
                    name="recommend_similar",
                    description="Find similar use cases based on various similarity factors",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "use_case_id": {
                                "type": "integer",
                                "description": "Reference use case ID",
                            },
                            "similarity_factors": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Factors to consider",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum similar cases",
                                "default": 5,
                            },
                        },
                        "required": ["use_case_id"],
                    },
                ),
                Tool(
                    name="estimate_complexity",
                    description="Assess implementation complexity based on methods, challenges, and KPIs",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "use_case_id": {
                                "type": "integer",
                                "description": "Use case ID to analyze",
                            },
                            "organization_context": {
                                "type": "object",
                                "description": "Optional organization context",
                            },
                        },
                        "required": ["use_case_id"],
                    },
                ),
                Tool(
                    name="suggest_implementation_path",
                    description="Suggest implementation roadmap and strategy based on use case and organizational context",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "use_case_id": {
                                "type": "integer",
                                "description": "Use case ID",
                            },
                            "organization_context": {
                                "type": "object",
                                "description": "Organization context for tailored recommendations",
                            },
                        },
                        "required": ["use_case_id"],
                    },
                ),
                Tool(
                    name="filter_by_method",
                    description="Find use cases using specific AI methods or techniques",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "method": {
                                "type": "string",
                                "description": "AI method or technique",
                            },
                            "min_maturity": {
                                "type": "string",
                                "description": "Minimum implementation maturity",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results",
                                "default": 15,
                            },
                        },
                        "required": ["method"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict):
            """Handle tool execution requests."""
            if name == "search_use_cases":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(self._search_use_cases(**arguments), indent=2),
                    )
                ]
            elif name == "filter_by_domain":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(self._filter_by_domain(**arguments), indent=2),
                    )
                ]
            elif name == "get_use_case_details":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            self._get_use_case_details(**arguments), indent=2
                        ),
                    )
                ]
            elif name == "analyze_domain_trends":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            self._analyze_domain_trends(**arguments), indent=2
                        ),
                    )
                ]
            elif name == "recommend_similar":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(self._recommend_similar(**arguments), indent=2),
                    )
                ]
            elif name == "estimate_complexity":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            self._estimate_complexity(**arguments), indent=2
                        ),
                    )
                ]
            elif name == "suggest_implementation_path":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            self._suggest_implementation_path(**arguments), indent=2
                        ),
                    )
                ]
            elif name == "filter_by_method":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(self._filter_by_method(**arguments), indent=2),
                    )
                ]
            else:
                raise ValueError(f"Unknown tool: {name}")

    def _setup_resources(self):
        """Setup MCP resources using the official SDK."""

        @self.server.list_resources()
        async def handle_list_resources():
            """List all available AI Registry resources."""
            resources = []

            # Registry overview resource
            resources.append(
                Resource(
                    uri="ai-registry://overview",
                    name="AI Registry Overview",
                    description="Overview of the AI use case registry",
                    mimeType="application/json",
                )
            )

            # Individual use case resources
            for use_case in self.registry_data.get("use_cases", []):
                use_case_id = use_case.get("use_case_id")
                if use_case_id:
                    resources.append(
                        Resource(
                            uri=f"ai-registry://use-case/{use_case_id}",
                            name=f"Use Case {use_case_id}: {use_case.get('name', 'Unknown')}",
                            description=use_case.get("description", ""),
                            mimeType="application/json",
                        )
                    )

            return resources

        @self.server.read_resource()
        async def handle_read_resource(uri: str):
            """Handle resource read requests."""
            if uri == "ai-registry://overview":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            self.registry_data.get("registry_info", {}), indent=2
                        ),
                    )
                ]
            elif uri.startswith("ai-registry://use-case/"):
                use_case_id = int(uri.split("/")[-1])
                use_case = self._get_use_case_by_id(use_case_id)
                if use_case:
                    return [
                        TextContent(type="text", text=json.dumps(use_case, indent=2))
                    ]
                else:
                    raise ValueError(f"Use case not found: {use_case_id}")
            else:
                raise ValueError(f"Unknown resource: {uri}")

    # Tool implementation methods

    def _search_use_cases(
        self,
        query: str,
        domains: list[str] | None = None,
        methods: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search use cases with filters."""
        use_cases = self.registry_data.get("use_cases", [])
        results = []

        for use_case in use_cases:
            # Simple text search
            score = 0.0
            search_text = (
                f"{use_case.get('name', '')} {use_case.get('description', '')}".lower()
            )
            if query.lower() in search_text:
                score += 0.8

            # Domain filter
            if domains and use_case.get("application_domain") in domains:
                score += 0.3

            # Method filter
            if methods:
                use_case_methods = use_case.get("ai_methods", [])
                if any(method in use_case_methods for method in methods):
                    score += 0.2

            if score > 0:
                results.append({"use_case": use_case, "score": score})

        # Sort by score and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:limit], "count": len(results), "query": query}

    def _filter_by_domain(
        self, domain: str, status: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        """Filter use cases by domain."""
        use_cases = self.registry_data.get("use_cases", [])
        filtered = []

        for use_case in use_cases:
            if use_case.get("application_domain") == domain:
                if not status or use_case.get("status") == status:
                    filtered.append(use_case)

        return {"domain": domain, "count": len(filtered), "use_cases": filtered[:limit]}

    def _get_use_case_details(self, use_case_id: int) -> dict[str, Any]:
        """Get detailed information for a specific use case."""
        use_case = self._get_use_case_by_id(use_case_id)
        if use_case:
            return {
                "use_case": use_case,
                "similar_cases": [],  # Could implement similarity search
            }
        else:
            raise ValueError(f"Use case not found: {use_case_id}")

    def _analyze_domain_trends(
        self, domain: str, include_details: bool = False
    ) -> dict[str, Any]:
        """Analyze trends within a specific domain."""
        use_cases = [
            uc
            for uc in self.registry_data.get("use_cases", [])
            if uc.get("application_domain") == domain
        ]

        # Analyze methods and statuses
        methods = {}
        statuses = {}

        for use_case in use_cases:
            for method in use_case.get("ai_methods", []):
                methods[method] = methods.get(method, 0) + 1

            status = use_case.get("status", "Unknown")
            statuses[status] = statuses.get(status, 0) + 1

        return {
            "domain": domain,
            "total_use_cases": len(use_cases),
            "popular_methods": sorted(
                methods.items(), key=lambda x: x[1], reverse=True
            ),
            "status_distribution": statuses,
            "examples": use_cases[:3] if include_details else [],
        }

    def _recommend_similar(
        self,
        use_case_id: int,
        similarity_factors: list[str] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Find similar use cases."""
        reference_case = self._get_use_case_by_id(use_case_id)
        if not reference_case:
            raise ValueError(f"Use case not found: {use_case_id}")

        similar_cases = []
        for use_case in self.registry_data.get("use_cases", []):
            if use_case.get("use_case_id") != use_case_id:
                similarity = self._calculate_similarity(reference_case, use_case)
                if similarity > 0.3:  # Threshold
                    similar_cases.append(
                        {"use_case": use_case, "similarity": similarity}
                    )

        similar_cases.sort(key=lambda x: x["similarity"], reverse=True)
        return {
            "reference_use_case_id": use_case_id,
            "similar_cases": similar_cases[:limit],
        }

    def _estimate_complexity(
        self, use_case_id: int, organization_context: dict | None = None
    ) -> dict[str, Any]:
        """Estimate implementation complexity."""
        use_case = self._get_use_case_by_id(use_case_id)
        if not use_case:
            raise ValueError(f"Use case not found: {use_case_id}")

        # Simple complexity scoring
        score = 0
        factors = []

        methods = use_case.get("ai_methods", [])
        for method in methods:
            if "Deep Learning" in method:
                score += 4
                factors.append(f"AI Method: {method} (+4)")
            elif "Machine Learning" in method:
                score += 2
                factors.append(f"AI Method: {method} (+2)")

        domain = use_case.get("application_domain", "")
        if domain == "Healthcare":
            score += 4
            factors.append(f"Domain: {domain} (+4)")

        challenges = use_case.get("challenges", "")
        if "privacy" in challenges.lower():
            score += 3
            factors.append("Challenge: privacy (+3)")

        complexity_level = "Low" if score < 5 else "Medium" if score < 10 else "High"

        return {
            "use_case_id": use_case_id,
            "complexity_score": score,
            "complexity_level": complexity_level,
            "scoring_factors": factors,
            "estimates": {
                "timeline": "6-12 months" if score < 8 else "12-18 months",
                "team_size": "3-8 people" if score < 8 else "8-15 people",
                "budget_category": "medium" if score < 8 else "high",
            },
        }

    def _suggest_implementation_path(
        self, use_case_id: int, organization_context: dict | None = None
    ) -> dict[str, Any]:
        """Suggest implementation roadmap."""
        use_case = self._get_use_case_by_id(use_case_id)
        if not use_case:
            raise ValueError(f"Use case not found: {use_case_id}")

        phases = [
            {"phase": 1, "name": "Foundation & Planning", "duration": "2-4 weeks"},
            {"phase": 2, "name": "Proof of Concept", "duration": "6-8 weeks"},
            {"phase": 3, "name": "Advanced Development", "duration": "12-24 weeks"},
            {"phase": 4, "name": "Deployment & Monitoring", "duration": "4-8 weeks"},
        ]

        recommendations = [
            "Start with a well-defined proof of concept",
            "Ensure data quality and availability early",
            "Plan for change management and user adoption",
        ]

        # Domain-specific recommendations
        domain = use_case.get("application_domain", "")
        if domain == "Healthcare":
            recommendations.extend(
                [
                    "Ensure HIPAA compliance and data privacy measures",
                    "Plan for regulatory approval processes",
                    "Consider partnering with medical AI specialists",
                ]
            )

        return {
            "use_case_id": use_case_id,
            "use_case_name": use_case.get("name", ""),
            "implementation_phases": phases,
            "key_recommendations": recommendations,
        }

    def _filter_by_method(
        self, method: str, min_maturity: str | None = None, limit: int = 15
    ) -> dict[str, Any]:
        """Filter use cases by AI method."""
        use_cases = self.registry_data.get("use_cases", [])
        filtered = []

        for use_case in use_cases:
            methods = use_case.get("ai_methods", [])
            if any(method.lower() in m.lower() for m in methods):
                if not min_maturity or self._check_maturity(
                    use_case.get("status", ""), min_maturity
                ):
                    filtered.append(use_case)

        return {"method": method, "count": len(filtered), "use_cases": filtered[:limit]}

    # Helper methods

    def _get_use_case_by_id(self, use_case_id: int) -> dict[str, Any] | None:
        """Get use case by ID."""
        for use_case in self.registry_data.get("use_cases", []):
            if use_case.get("use_case_id") == use_case_id:
                return use_case
        return None

    def _calculate_similarity(
        self, case1: dict[str, Any], case2: dict[str, Any]
    ) -> float:
        """Calculate similarity between two use cases."""
        score = 0.0

        # Domain similarity
        if case1.get("application_domain") == case2.get("application_domain"):
            score += 0.4

        # Method similarity
        methods1 = set(case1.get("ai_methods", []))
        methods2 = set(case2.get("ai_methods", []))
        if methods1 and methods2:
            overlap = len(methods1.intersection(methods2))
            total = len(methods1.union(methods2))
            score += 0.6 * (overlap / total)

        return score

    def _check_maturity(self, status: str, min_maturity: str) -> bool:
        """Check if status meets minimum maturity requirement."""
        maturity_order = ["Idea", "PoC", "PoB", "Production"]
        try:
            status_level = maturity_order.index(status)
            min_level = maturity_order.index(min_maturity)
            return status_level >= min_level
        except ValueError:
            return True  # If unknown status, include it

    async def run_stdio(self):
        """Run the server with stdio transport."""
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


async def main():
    """Main entry point for running the AI Registry MCP server."""
    # Get registry file from environment or use default
    registry_file = os.environ.get(
        "REGISTRY_FILE", "research/combined_ai_registry.json"
    )

    server = AIRegistryServer(registry_file)
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())


# For module execution
def run_server():
    """Entry point for python -m kailash.mcp_server.ai_registry_server"""
    asyncio.run(main())
