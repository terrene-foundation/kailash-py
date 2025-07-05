"""AI Registry MCP Server using FastMCP.

This server provides access to AI use case registry data via MCP,
exposing tools for searching, analyzing, and exploring AI implementations.
"""

import json
import os
from pathlib import Path
from typing import Any

from kailash.mcp_server.server import MCPServerBase


class AIRegistryServer(MCPServerBase):
    """MCP server for AI use case registry.

    Provides tools and resources for exploring AI use cases from
    ISO/IEC standards and industry implementations.

    Examples:
        >>> server = AIRegistryServer(
        ...     registry_file="data/ai_registry.json",
        ...     port=8080
        ... )
        >>> server.start()  # Runs until stopped
    """

    def __init__(
        self,
        registry_file: str = "research/combined_ai_registry.json",
        name: str = "ai-registry",
        port: int = 8080,
        host: str = "localhost",
    ):
        """Initialize the AI Registry server.

        Args:
            registry_file: Path to JSON file containing AI use cases
            name: Server name
            port: Port to listen on
            host: Host to bind to
        """
        super().__init__(name, port, host)
        self.registry_file = registry_file
        self._registry_data = None
        self._load_registry()

    def _load_registry(self):
        """Load the AI registry data from file."""
        try:
            registry_path = Path(self.registry_file)
            if registry_path.exists():
                with open(registry_path, encoding="utf-8") as f:
                    self._registry_data = json.load(f)
            else:
                # Provide sample data if file not found
                self._registry_data = {
                    "use_cases": [
                        {
                            "use_case_id": 1,
                            "name": "Medical Diagnosis Assistant",
                            "application_domain": "Healthcare",
                            "description": "AI system to assist doctors in diagnosing diseases",
                            "ai_methods": ["Machine Learning", "Deep Learning"],
                            "status": "Production",
                        },
                        {
                            "use_case_id": 2,
                            "name": "Fraud Detection System",
                            "application_domain": "Finance",
                            "description": "Real-time fraud detection in financial transactions",
                            "ai_methods": ["Anomaly Detection", "Pattern Recognition"],
                            "status": "Production",
                        },
                    ]
                }
        except Exception as e:
            self.logger.error(f"Failed to load registry: {e}")
            self._registry_data = {"use_cases": []}

    def setup(self):
        """Setup server tools and resources."""

        @self.add_tool()
        def search_use_cases(query: str, limit: int = 10) -> dict[str, Any]:
            """Search for AI use cases matching the query.

            Args:
                query: Search query string
                limit: Maximum number of results to return

            Returns:
                Search results with matching use cases
            """
            if not self._registry_data:
                return {"results": [], "count": 0, "query": query}

            use_cases = self._registry_data.get("use_cases", [])
            results = []

            query_lower = query.lower()
            for use_case in use_cases:
                # Search in multiple fields
                searchable_text = " ".join(
                    [
                        str(use_case.get("name", "")),
                        str(use_case.get("description", "")),
                        str(use_case.get("application_domain", "")),
                        " ".join(use_case.get("ai_methods", [])),
                    ]
                )

                if query_lower in searchable_text.lower():
                    results.append(use_case)
                    if len(results) >= limit:
                        break

            return {"results": results, "count": len(results), "query": query}

        @self.add_tool()
        def filter_by_domain(domain: str) -> dict[str, Any]:
            """Filter use cases by application domain.

            Args:
                domain: Application domain to filter by

            Returns:
                Use cases in the specified domain
            """
            if not self._registry_data:
                return {"domain": domain, "use_cases": [], "count": 0}

            use_cases = self._registry_data.get("use_cases", [])
            filtered = [
                uc
                for uc in use_cases
                if uc.get("application_domain", "").lower() == domain.lower()
            ]

            return {"domain": domain, "use_cases": filtered, "count": len(filtered)}

        @self.add_tool()
        def get_use_case_details(use_case_id: int) -> dict[str, Any]:
            """Get detailed information about a specific use case.

            Args:
                use_case_id: ID of the use case

            Returns:
                Detailed use case information
            """
            if not self._registry_data:
                return {"error": "No registry data available"}

            use_cases = self._registry_data.get("use_cases", [])
            for use_case in use_cases:
                if use_case.get("use_case_id") == use_case_id:
                    return {"use_case": use_case}

            return {"error": f"Use case {use_case_id} not found"}

        @self.add_tool()
        def list_domains() -> dict[str, Any]:
            """List all available application domains.

            Returns:
                List of domains with use case counts
            """
            if not self._registry_data:
                return {"domains": []}

            use_cases = self._registry_data.get("use_cases", [])
            domain_counts = {}

            for use_case in use_cases:
                domain = use_case.get("application_domain", "Unknown")
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            domains = [
                {"name": domain, "count": count}
                for domain, count in domain_counts.items()
            ]

            return {
                "domains": sorted(domains, key=lambda x: x["count"], reverse=True),
                "total_domains": len(domains),
            }

        @self.add_resource("registry://stats")
        def get_registry_stats():
            """Get statistics about the AI registry."""
            if not self._registry_data:
                return {"error": "No registry data available"}

            use_cases = self._registry_data.get("use_cases", [])

            # Calculate statistics
            total_count = len(use_cases)
            domain_counts = {}
            method_counts = {}
            status_counts = {}

            for use_case in use_cases:
                # Count by domain
                domain = use_case.get("application_domain", "Unknown")
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

                # Count by AI method
                for method in use_case.get("ai_methods", []):
                    method_counts[method] = method_counts.get(method, 0) + 1

                # Count by status
                status = use_case.get("status", "Unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "total_use_cases": total_count,
                "domains": domain_counts,
                "ai_methods": method_counts,
                "status_distribution": status_counts,
            }

        @self.add_resource("registry://domains/{domain}")
        def get_domain_resource(domain: str):
            """Get all use cases for a specific domain."""
            result = filter_by_domain(domain)
            return result

        @self.add_prompt("analyze_use_case")
        def analyze_use_case_prompt(
            use_case_name: str, focus_area: str = "implementation"
        ) -> str:
            """Generate a prompt for analyzing a use case.

            Args:
                use_case_name: Name of the use case
                focus_area: Area to focus on (implementation, challenges, benefits)

            Returns:
                Analysis prompt
            """
            return f"""Please analyze the AI use case '{use_case_name}' with a focus on {focus_area}.

Consider the following aspects:
1. Technical implementation requirements
2. Key challenges and how to address them
3. Expected benefits and ROI
4. Best practices and recommendations
5. Similar use cases and lessons learned

Provide a comprehensive analysis with actionable insights."""


# Convenience function to start the server
def start_server(
    registry_file: str = "research/combined_ai_registry.json",
    port: int = 8080,
    host: str = "localhost",
):
    """Start the AI Registry MCP server.

    Args:
        registry_file: Path to registry JSON file
        port: Port to listen on
        host: Host to bind to
    """
    server = AIRegistryServer(registry_file, port=port, host=host)
    server.start()


if __name__ == "__main__":
    # Allow running as a module
    import sys

    registry_file = os.environ.get(
        "REGISTRY_FILE", "research/combined_ai_registry.json"
    )
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "localhost")

    if "--help" in sys.argv:
        print("AI Registry MCP Server")
        print("Environment variables:")
        print("  REGISTRY_FILE - Path to AI registry JSON file")
        print("  PORT - Port to listen on (default: 8080)")
        print("  HOST - Host to bind to (default: localhost)")
    else:
        start_server(registry_file, port, host)
