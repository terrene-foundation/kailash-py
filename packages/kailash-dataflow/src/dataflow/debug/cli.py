"""CLI command entry point for Debug Agent.

This module provides the command-line interface for the DataFlow Debug Agent.

Usage:
    python -m dataflow.debug.cli "NOT NULL constraint failed: users.id"
    python -m dataflow.debug.cli --error-file error.log
    python -m dataflow.debug.cli --help
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from dataflow.debug.cli_formatter import CLIFormatter
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase


def _get_error_message(args: argparse.Namespace) -> str:
    """Get error message from command-line arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        Error message string

    Raises:
        ValueError: If no error message provided

    Example:
        >>> args = parser.parse_args(["Error message"])
        >>> error_message = _get_error_message(args)
        >>> error_message
        'Error message'
    """
    if args.error_file:
        # Read error from file
        error_file = Path(args.error_file)
        if not error_file.exists():
            raise ValueError(f"Error file not found: {args.error_file}")
        return error_file.read_text().strip()
    elif args.error_message:
        # Use command-line argument
        return args.error_message
    else:
        raise ValueError(
            "No error message provided. Use <error_message> or --error-file"
        )


def _initialize_knowledge_base(args: argparse.Namespace) -> KnowledgeBase:
    """Initialize KnowledgeBase from command-line arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        KnowledgeBase instance

    Example:
        >>> args = parser.parse_args([])
        >>> kb = _initialize_knowledge_base(args)
        >>> kb is not None
        True
    """
    # Default paths (auto-detect from package)
    patterns_path = (
        args.patterns if args.patterns else "src/dataflow/debug/patterns.yaml"
    )
    solutions_path = (
        args.solutions if args.solutions else "src/dataflow/debug/solutions.yaml"
    )

    return KnowledgeBase(patterns_path, solutions_path)


def main():
    """Main CLI entry point for debug-agent command.

    Command-line interface for DataFlow Debug Agent with support for:
    - Direct error message strings
    - Error messages from files
    - JSON output format
    - Configurable solution filtering

    Example:
        $ python -m dataflow.debug.cli "NOT NULL constraint failed: users.id"
        [Formatted output with solutions]

        $ python -m dataflow.debug.cli --error-file error.log --format json
        {"captured_error": {...}, "suggested_solutions": [...]}
    """
    parser = argparse.ArgumentParser(
        prog="debug-agent",
        description="DataFlow Debug Agent - Intelligent error analysis and suggestions",
        epilog="For more information, see https://docs.dataflow.dev/debug-agent",
    )

    # Positional argument
    parser.add_argument(
        "error_message", nargs="?", help="Error message to debug (or use --error-file)"
    )

    # Input options
    parser.add_argument("--error-file", type=str, help="Read error message from file")
    parser.add_argument(
        "--error-type",
        type=str,
        default="RuntimeError",
        help="Error type name (default: RuntimeError)",
    )

    # Solution filtering options
    parser.add_argument(
        "--max-solutions",
        type=int,
        default=5,
        help="Maximum solutions to show (default: 5)",
    )
    parser.add_argument(
        "--min-relevance",
        type=float,
        default=0.3,
        help="Minimum relevance score 0.0-1.0 (default: 0.3)",
    )

    # Output options
    parser.add_argument(
        "--format",
        choices=["cli", "json"],
        default="cli",
        help="Output format (default: cli)",
    )

    # KnowledgeBase options
    parser.add_argument(
        "--patterns", type=str, help="Path to patterns.yaml (default: auto-detect)"
    )
    parser.add_argument(
        "--solutions", type=str, help="Path to solutions.yaml (default: auto-detect)"
    )

    # Parse arguments
    args = parser.parse_args()

    try:
        # Get error message
        error_message = _get_error_message(args)

        # Initialize KnowledgeBase
        kb = _initialize_knowledge_base(args)

        # Initialize DebugAgent (without Inspector for CLI usage)
        agent = DebugAgent(kb, inspector=None)

        # Run debug pipeline
        report = agent.debug_from_string(
            error_message,
            error_type=args.error_type,
            max_solutions=args.max_solutions,
            min_relevance=args.min_relevance,
        )

        # Format output
        if args.format == "json":
            print(report.to_json())
        else:
            formatter = CLIFormatter()
            print(formatter.format_report(report))

        # Exit with appropriate code
        # 0 = solutions found
        # 1 = no solutions found
        sys.exit(0 if report.suggested_solutions else 1)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        parser.print_help()
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
