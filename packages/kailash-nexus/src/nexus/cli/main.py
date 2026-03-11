"""Main CLI interface for Nexus workflow orchestration.

This module provides command-line access to Nexus workflows running on a server.
It connects to a running Nexus instance and allows listing and executing workflows.
"""

import argparse
import json
import sys
from typing import Any, Dict, Optional

import requests


class NexusCLI:
    """Command-line interface for Nexus workflows."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize CLI with Nexus server URL.

        Args:
            base_url: Base URL of the Nexus server
        """
        self.base_url = base_url.rstrip("/")

    def list_workflows(self) -> None:
        """List all available workflows."""
        try:
            response = requests.get(f"{self.base_url}/workflows", timeout=5)
            response.raise_for_status()

            workflows = response.json()

            if not workflows:
                print("No workflows available.")
                return

            print("Available workflows:")
            for workflow_name in sorted(workflows.keys()):
                print(f"  - {workflow_name}")

        except requests.RequestException as e:
            print(f"Error connecting to Nexus server: {e}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error parsing server response: {e}", file=sys.stderr)
            sys.exit(1)

    def run_workflow(
        self, workflow_name: str, parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute a workflow with optional parameters.

        Args:
            workflow_name: Name of the workflow to execute
            parameters: Optional parameters for the workflow
        """
        try:
            payload = {"parameters": parameters or {}}

            response = requests.post(
                f"{self.base_url}/workflows/{workflow_name}", json=payload, timeout=30
            )
            response.raise_for_status()

            result = response.json()

            # Handle enterprise workflow execution format
            if "outputs" in result:
                # Extract results from each node
                for node_name, node_result in result["outputs"].items():
                    if "result" in node_result:
                        node_output = node_result["result"]
                        # Print meaningful output
                        for key, value in node_output.items():
                            print(f"{key}: {value}")
            else:
                # Handle direct result format
                print(json.dumps(result, indent=2))

        except requests.RequestException as e:
            print(f"Error executing workflow: {e}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error parsing execution result: {e}", file=sys.stderr)
            sys.exit(1)

    def parse_parameters(self, param_strings: list) -> Dict[str, Any]:
        """Parse parameter strings in key=value format.

        Args:
            param_strings: List of parameter strings in "key=value" format

        Returns:
            Dictionary of parsed parameters
        """
        parameters = {}

        for param_str in param_strings:
            if "=" not in param_str:
                print(
                    f"Invalid parameter format: {param_str}. Use key=value format.",
                    file=sys.stderr,
                )
                sys.exit(1)

            key, value = param_str.split("=", 1)

            # Try to parse as JSON for complex values, otherwise use as string
            try:
                parameters[key] = json.loads(value)
            except json.JSONDecodeError:
                parameters[key] = value

        return parameters


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Nexus CLI - Command-line interface for workflow orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m nexus.cli list
  python -m nexus.cli run my-workflow
  python -m nexus.cli run my-workflow --param name=value --param count=5

  # Connect to different server:
  python -m nexus.cli --url http://localhost:8001 list
        """,
    )

    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the Nexus server (default: http://localhost:8000)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List available workflows")

    # Run command
    run_parser = subparsers.add_parser("run", help="Execute a workflow")
    run_parser.add_argument("workflow", help="Name of the workflow to execute")
    run_parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Workflow parameters in key=value format (can be used multiple times)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize CLI client
    cli = NexusCLI(base_url=args.url)

    # Execute command
    if args.command == "list":
        cli.list_workflows()
    elif args.command == "run":
        parameters = cli.parse_parameters(args.param)
        cli.run_workflow(args.workflow, parameters)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
