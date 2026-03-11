"""CLI formatter for Debug Agent reports.

This module provides the CLIFormatter that formats DebugReport objects
for terminal display with colors, box drawing, and clear structure.
"""

from typing import List

from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.debug_report import DebugReport
from dataflow.debug.error_capture import CapturedError
from dataflow.debug.suggested_solution import SuggestedSolution


class CLIFormatter:
    """Formats DebugReport for terminal display.

    The CLIFormatter provides rich terminal output with:
    - Color-coded sections (errors in red, info in blue, etc.)
    - Box drawing for visual structure
    - Clear hierarchy and readable formatting

    Usage:
        formatter = CLIFormatter()
        report = debug_agent.debug(exception)
        print(formatter.format_report(report))

    Example Output:
        ╔════════════════════════════════════════════════════════════════╗
        ║                   DataFlow Debug Agent                          ║
        ╚════════════════════════════════════════════════════════════════╝

        ┌─ ERROR DETAILS ────────────────────────────────────────────────┐
        │ Type: DatabaseError                                             │
        │ Category: PARAMETER (Confidence: 92%)                           │
        └─────────────────────────────────────────────────────────────────┘

        ERROR MESSAGE:
          NOT NULL constraint failed: users.id

        [... rest of formatted output ...]
    """

    # ANSI color codes
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def format_report(self, report: DebugReport) -> str:
        """Format complete debug report for CLI display.

        Args:
            report: DebugReport to format

        Returns:
            Formatted string with colors and structure

        Example:
            >>> formatter = CLIFormatter()
            >>> report = DebugReport(...)
            >>> output = formatter.format_report(report)
            >>> print(output)
            [Formatted output with colors and box drawing]
        """
        sections = []

        # Header
        sections.append(self._format_header())

        # Error details
        sections.append(
            self._format_error_section(report.captured_error, report.error_category)
        )

        # Analysis
        sections.append(self._format_analysis_section(report.analysis_result))

        # Solutions
        sections.append(self._format_solutions_section(report.suggested_solutions))

        # Footer
        sections.append(self._format_footer(report))

        return "\n\n".join(sections)

    def _format_header(self) -> str:
        """Format header banner.

        Returns:
            Formatted header string

        Example:
            ╔═══════════════════════════════════════════════════════════╗
            ║              DataFlow Debug Agent                         ║
            ║       Intelligent Error Analysis & Suggestions            ║
            ╚═══════════════════════════════════════════════════════════╝
        """
        lines = []
        lines.append(f"{self.BOLD}{self.CYAN}╔{'═' * 76}╗{self.RESET}")
        lines.append(
            f"{self.BOLD}{self.CYAN}║{' ' * 25}DataFlow Debug Agent{' ' * 28}║{self.RESET}"
        )
        lines.append(
            f"{self.BOLD}{self.CYAN}║{' ' * 16}Intelligent Error Analysis & Suggestions{' ' * 18}║{self.RESET}"
        )
        lines.append(f"{self.BOLD}{self.CYAN}╚{'═' * 76}╝{self.RESET}")
        return "\n".join(lines)

    def _format_error_section(self, captured: CapturedError, category) -> str:
        """Format captured error details.

        Args:
            captured: CapturedError object
            category: ErrorCategory object

        Returns:
            Formatted error section

        Example:
            ┌─ ERROR DETAILS ────────────────────────────────────────────┐
            │ Type: DatabaseError                                        │
            │ Category: PARAMETER (Confidence: 92%)                      │
            └────────────────────────────────────────────────────────────┘

            ERROR MESSAGE:
              NOT NULL constraint failed: users.id
        """
        lines = []

        # Box header
        lines.append(f"{self.BLUE}┌─ ERROR DETAILS {'─' * 56}┐{self.RESET}")
        lines.append(
            f"{self.BLUE}│{self.RESET} Type: {self.BOLD}{captured.error_type}{self.RESET}{' ' * (71 - len(captured.error_type) - 6)}{self.BLUE}│{self.RESET}"
        )

        confidence_pct = int(category.confidence * 100)
        category_line = f"Category: {category.category} (Confidence: {confidence_pct}%)"
        lines.append(
            f"{self.BLUE}│{self.RESET} {category_line}{' ' * (75 - len(category_line))}{self.BLUE}│{self.RESET}"
        )
        lines.append(f"{self.BLUE}└{'─' * 76}┘{self.RESET}")

        # Error message
        lines.append("")
        lines.append(f"{self.BOLD}ERROR MESSAGE:{self.RESET}")
        lines.append(f"  {self.RED}{captured.message}{self.RESET}")

        return "\n".join(lines)

    def _format_analysis_section(self, analysis: AnalysisResult) -> str:
        """Format root cause and affected components.

        Args:
            analysis: AnalysisResult object

        Returns:
            Formatted analysis section

        Example:
            ┌─ ROOT CAUSE ANALYSIS ──────────────────────────────────────┐
            │ Root Cause:                                                │
            │   Node 'create_user' is missing required parameter 'id'    │
            │                                                            │
            │ Affected Components:                                       │
            │   • Nodes: create_user                                     │
            │   • Models: User                                           │
            │   • Parameters: id (primary key)                           │
            └────────────────────────────────────────────────────────────┘
        """
        lines = []

        # Box header
        lines.append(f"{self.YELLOW}┌─ ROOT CAUSE ANALYSIS {'─' * 52}┐{self.RESET}")

        # Root cause
        lines.append(
            f"{self.YELLOW}│{self.RESET} {self.BOLD}Root Cause:{self.RESET}{' ' * 62}{self.YELLOW}│{self.RESET}"
        )
        # Wrap long root cause text
        root_cause_words = analysis.root_cause.split()
        current_line = "  "
        for word in root_cause_words:
            if len(current_line) + len(word) + 1 > 72:
                lines.append(
                    f"{self.YELLOW}│{self.RESET} {current_line}{' ' * (75 - len(current_line))}{self.YELLOW}│{self.RESET}"
                )
                current_line = "  " + word + " "
            else:
                current_line += word + " "
        if current_line.strip():
            lines.append(
                f"{self.YELLOW}│{self.RESET} {current_line.rstrip()}{' ' * (75 - len(current_line.rstrip()))}{self.YELLOW}│{self.RESET}"
            )

        # Affected components
        if (
            analysis.affected_nodes
            or analysis.affected_models
            or analysis.affected_connections
        ):
            lines.append(f"{self.YELLOW}│{' ' * 76}│{self.RESET}")
            lines.append(
                f"{self.YELLOW}│{self.RESET} {self.BOLD}Affected Components:{self.RESET}{' ' * 53}{self.YELLOW}│{self.RESET}"
            )

            if analysis.affected_nodes:
                nodes_text = f"  • Nodes: {', '.join(analysis.affected_nodes)}"
                lines.append(
                    f"{self.YELLOW}│{self.RESET} {nodes_text}{' ' * (75 - len(nodes_text))}{self.YELLOW}│{self.RESET}"
                )

            if analysis.affected_models:
                models_text = f"  • Models: {', '.join(analysis.affected_models)}"
                lines.append(
                    f"{self.YELLOW}│{self.RESET} {models_text}{' ' * (75 - len(models_text))}{self.YELLOW}│{self.RESET}"
                )

            if analysis.affected_connections:
                conns_text = (
                    f"  • Connections: {', '.join(analysis.affected_connections[:2])}"
                )
                if len(analysis.affected_connections) > 2:
                    conns_text += f" (+{len(analysis.affected_connections) - 2} more)"
                lines.append(
                    f"{self.YELLOW}│{self.RESET} {conns_text}{' ' * (75 - len(conns_text))}{self.YELLOW}│{self.RESET}"
                )

            # Show key context data
            if analysis.context_data:
                missing_param = analysis.context_data.get("missing_parameter")
                if missing_param:
                    is_pk = analysis.context_data.get("is_primary_key", False)
                    param_text = f"  • Parameters: {missing_param}"
                    if is_pk:
                        param_text += " (primary key)"
                    lines.append(
                        f"{self.YELLOW}│{self.RESET} {param_text}{' ' * (75 - len(param_text))}{self.YELLOW}│{self.RESET}"
                    )

        lines.append(f"{self.YELLOW}└{'─' * 76}┘{self.RESET}")

        return "\n".join(lines)

    def _format_solutions_section(self, solutions: List[SuggestedSolution]) -> str:
        """Format suggested solutions with code examples.

        Args:
            solutions: List of SuggestedSolution objects

        Returns:
            Formatted solutions section

        Example:
            ┌─ SUGGESTED SOLUTIONS ──────────────────────────────────────┐
            │                                                            │
            │ [1] Add Missing 'id' Parameter to CreateNode (QUICK_FIX)  │
            │     Relevance: 95% | Difficulty: easy | Time: 1 min       │
            │                                                            │
            │     Description:                                           │
            │     Add required 'id' field to UserCreateNode operation    │
            │                                                            │
            │     Code Example:                                          │
            │     workflow.add_node("UserCreateNode", "create_user", {   │
            │         "id": "user-123",  # Add missing parameter        │
            │         "name": "Alice"                                    │
            │     })                                                     │
            │                                                            │
            └────────────────────────────────────────────────────────────┘
        """
        lines = []

        # Box header
        lines.append(f"{self.GREEN}┌─ SUGGESTED SOLUTIONS {'─' * 52}┐{self.RESET}")

        if not solutions:
            lines.append(f"{self.GREEN}│{' ' * 76}│{self.RESET}")
            lines.append(
                f"{self.GREEN}│{self.RESET}  No solutions found{' ' * 54}{self.GREEN}│{self.RESET}"
            )
            lines.append(f"{self.GREEN}│{' ' * 76}│{self.RESET}")
        else:
            for i, solution in enumerate(solutions, 1):
                lines.append(f"{self.GREEN}│{' ' * 76}│{self.RESET}")

                # Title
                title_text = f" [{i}] {solution.title} ({solution.category})"
                lines.append(
                    f"{self.GREEN}│{self.RESET}{self.BOLD}{title_text}{self.RESET}{' ' * (76 - len(title_text))}{self.GREEN}│{self.RESET}"
                )

                # Metadata
                relevance_pct = int(solution.relevance_score * 100)
                meta_text = f"     Relevance: {relevance_pct}% | Difficulty: {solution.difficulty} | Time: {solution.estimated_time} min"
                lines.append(
                    f"{self.GREEN}│{self.RESET}{meta_text}{' ' * (76 - len(meta_text))}{self.GREEN}│{self.RESET}"
                )

                lines.append(f"{self.GREEN}│{' ' * 76}│{self.RESET}")

                # Description
                lines.append(
                    f"{self.GREEN}│{self.RESET}     {self.BOLD}Description:{self.RESET}{' ' * 58}{self.GREEN}│{self.RESET}"
                )
                desc_words = solution.description.split()
                desc_line = "     "
                for word in desc_words:
                    if len(desc_line) + len(word) + 1 > 72:
                        lines.append(
                            f"{self.GREEN}│{self.RESET} {desc_line}{' ' * (75 - len(desc_line))}{self.GREEN}│{self.RESET}"
                        )
                        desc_line = "     " + word + " "
                    else:
                        desc_line += word + " "
                if desc_line.strip():
                    lines.append(
                        f"{self.GREEN}│{self.RESET} {desc_line.rstrip()}{' ' * (75 - len(desc_line.rstrip()))}{self.GREEN}│{self.RESET}"
                    )

                lines.append(f"{self.GREEN}│{' ' * 76}│{self.RESET}")

                # Code example (first 5 lines only)
                if solution.code_example:
                    lines.append(
                        f"{self.GREEN}│{self.RESET}     {self.BOLD}Code Example:{self.RESET}{' ' * 57}{self.GREEN}│{self.RESET}"
                    )
                    code_lines = solution.code_example.split("\n")[:5]
                    for code_line in code_lines:
                        code_text = f"     {code_line}"
                        if len(code_text) > 72:
                            code_text = code_text[:72] + "..."
                        lines.append(
                            f"{self.GREEN}│{self.RESET} {self.CYAN}{code_text}{self.RESET}{' ' * (75 - len(code_text))}{self.GREEN}│{self.RESET}"
                        )
                    if len(solution.code_example.split("\n")) > 5:
                        lines.append(
                            f"{self.GREEN}│{self.RESET}     ...{' ' * 68}{self.GREEN}│{self.RESET}"
                        )

                lines.append(f"{self.GREEN}│{' ' * 76}│{self.RESET}")

                # Separator between solutions
                if i < len(solutions):
                    lines.append(f"{self.GREEN}├{'─' * 76}┤{self.RESET}")

        lines.append(f"{self.GREEN}└{'─' * 76}┘{self.RESET}")

        return "\n".join(lines)

    def _format_footer(self, report: DebugReport) -> str:
        """Format footer with execution time and links.

        Args:
            report: DebugReport object

        Returns:
            Formatted footer

        Example:
            ┌─ SUMMARY ──────────────────────────────────────────────────┐
            │ Execution Time: 23ms                                       │
            │ Documentation: https://docs.dataflow.dev/debug-agent       │
            └────────────────────────────────────────────────────────────┘
        """
        lines = []

        # Box header
        lines.append(f"{self.MAGENTA}┌─ SUMMARY {'─' * 64}┐{self.RESET}")

        # Execution time
        exec_text = f" Execution Time: {report.execution_time:.1f}ms"
        lines.append(
            f"{self.MAGENTA}│{self.RESET}{exec_text}{' ' * (76 - len(exec_text))}{self.MAGENTA}│{self.RESET}"
        )

        # Documentation link
        doc_text = " Documentation: https://docs.dataflow.dev/debug-agent"
        lines.append(
            f"{self.MAGENTA}│{self.RESET}{doc_text}{' ' * (76 - len(doc_text))}{self.MAGENTA}│{self.RESET}"
        )

        lines.append(f"{self.MAGENTA}└{'─' * 76}┘{self.RESET}")

        return "\n".join(lines)
