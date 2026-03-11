"""
Content Creator - Automated content generation with PEVAgent pattern.

This example demonstrates:
1. Plan → Execute → Verify → Refine iterative loop
2. Quality verification (grammar, style, facts)
3. Iterative refinement (max 5 iterations)
4. Final output export (Markdown, HTML, PDF)
5. Hooks integration for performance metrics

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+

Usage:
    python content_creator.py "blog post on AI ethics" length=1000 tone=professional

    The agent will:
    - Create initial content draft
    - Verify quality (grammar, style, coherence)
    - Refine based on verification feedback
    - Iterate until quality threshold met (max 5 iterations)
    - Export final content to multiple formats
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookManager, HookResult


class PerformanceMetricsHook:
    """Custom hook for tracking performance metrics."""

    def __init__(self):
        self.start_time = None
        self.iteration_times = []

    async def pre_agent_loop(self, context: HookContext) -> HookResult:
        """Track start time."""
        self.start_time = datetime.now()
        print("⏱️  Performance: Content creation started")
        return HookResult(success=True)

    async def post_agent_loop(self, context: HookContext) -> HookResult:
        """Calculate and display performance metrics."""
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            print("\n⏱️  Performance Metrics:")
            print(f"   Total Time: {duration:.2f} seconds")
            print(f"   Iterations: {len(self.iteration_times)}")
            if self.iteration_times:
                avg_time = sum(self.iteration_times) / len(self.iteration_times)
                print(f"   Avg Iteration Time: {avg_time:.2f} seconds")
        return HookResult(success=True)


class ContentCreator:
    """Content creator with iterative refinement pattern."""

    def __init__(
        self,
        config: PEVAgentConfig,
        control_protocol: ControlProtocol = None,
        enable_metrics: bool = True,
    ):
        """
        Initialize content creator.

        Args:
            config: PEV agent configuration
            control_protocol: Optional control protocol for progress reporting
            enable_metrics: Enable performance metrics tracking
        """
        self.config = config
        self.control_protocol = control_protocol

        # Setup hooks for performance metrics
        self.hook_manager = None
        self.metrics_hook = None
        if enable_metrics:
            self.hook_manager = HookManager()
            self.metrics_hook = PerformanceMetricsHook()
            self.hook_manager.register(
                HookEvent.PRE_AGENT_LOOP, self.metrics_hook.pre_agent_loop
            )
            self.hook_manager.register(
                HookEvent.POST_AGENT_LOOP, self.metrics_hook.post_agent_loop
            )

        # Create PEV agent
        self.agent = PEVAgent(
            llm_provider=config.llm_provider,
            model=config.model,
            temperature=config.temperature,
            max_iterations=config.max_iterations,
            verification_strictness=config.verification_strictness,
            enable_error_recovery=config.enable_error_recovery,
        )

        print("\n" + "=" * 60)
        print("🤖 CONTENT CREATOR INITIALIZED")
        print("=" * 60)
        print(f"🔧 LLM: {config.llm_provider}/{config.model}")
        print(f"🔄 Max Iterations: {config.max_iterations}")
        print(f"✅ Verification: {config.verification_strictness}")
        print(f"🛡️  Error Recovery: {config.enable_error_recovery}")
        print(f"📊 Performance Metrics: {enable_metrics}")
        print("=" * 60 + "\n")

    async def create_content(self, task: str, context: Dict = None) -> Dict:
        """
        Create content with iterative refinement.

        Args:
            task: Content creation task description
            context: Optional context (length, tone, audience)

        Returns:
            Dict with plan, execution, verification, refinements, and final result
        """
        print(f"\n✍️  Starting content creation: {task}\n")

        # Build content context
        content_context = context or {}
        content_context["task"] = task

        # Report progress
        if self.control_protocol:
            await self.control_protocol.report_progress(
                message="Creating initial draft", percentage=10
            )

        try:
            # Execute PEV agent (plan → execute → verify → refine loop)
            result = self.agent.run(task=task, context=content_context)

            # Display plan
            print("\n" + "=" * 60)
            print("📋 CONTENT PLAN")
            print("=" * 60)
            plan = result.get("plan", {})
            if isinstance(plan, dict):
                print(
                    f"Objective: {plan.get('objective', 'Create high-quality content')}"
                )
                print(
                    f"Target Length: {plan.get('length', content_context.get('length', 'default'))}"
                )
                print(
                    f"Tone: {plan.get('tone', content_context.get('tone', 'neutral'))}"
                )
            else:
                print(plan)
            print("=" * 60 + "\n")

            # Display initial execution
            print("=" * 60)
            print("📝 INITIAL DRAFT")
            print("=" * 60)
            execution_result = result.get("execution_result", {})
            if isinstance(execution_result, dict):
                draft = execution_result.get(
                    "draft", execution_result.get("content", "")
                )
                print(draft[:500] + "..." if len(draft) > 500 else draft)
            else:
                print(
                    str(execution_result)[:500] + "..."
                    if len(str(execution_result)) > 500
                    else execution_result
                )
            print("=" * 60 + "\n")

            # Display verification and refinements
            refinements = result.get("refinements", [])
            print("=" * 60)
            print(f"🔄 ITERATIVE REFINEMENT ({len(refinements)} iterations)")
            print("=" * 60)

            for i, refinement in enumerate(refinements, 1):
                if self.control_protocol:
                    progress = 10 + int((i / max(len(refinements), 1)) * 80)
                    await self.control_protocol.report_progress(
                        message=f"Refining content (iteration {i})", percentage=progress
                    )

                print(f"\nIteration {i}:")
                if isinstance(refinement, dict):
                    verification = refinement.get("verification", {})
                    print(f"  Verification Score: {verification.get('score', 'N/A')}")
                    print(f"  Status: {verification.get('status', 'unknown')}")

                    issues = verification.get("issues", [])
                    if issues:
                        print(f"  Issues Found: {len(issues)}")
                        for issue in issues[:3]:  # Show first 3 issues
                            print(f"    - {issue}")
                    else:
                        print("  ✅ No issues found")

                    improvements = refinement.get("improvements", [])
                    if improvements:
                        print(f"  Improvements Made: {len(improvements)}")
                else:
                    print(f"  {refinement}")

            print("=" * 60 + "\n")

            # Display final verification
            verification = result.get("verification", {})
            print("=" * 60)
            print("✅ FINAL VERIFICATION")
            print("=" * 60)
            print(f"Passed: {verification.get('passed', False)}")
            print(f"Final Score: {verification.get('score', 'N/A')}")
            if verification.get("issues"):
                print(f"Remaining Issues: {len(verification['issues'])}")
            else:
                print("✅ All quality checks passed")
            print("=" * 60 + "\n")

            # Display final content
            print("=" * 60)
            print("📄 FINAL CONTENT")
            print("=" * 60)
            final_result = result.get("final_result", "")
            print(final_result)
            print("=" * 60 + "\n")

            # Report completion
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message="Content creation complete", percentage=100
                )

            return result

        except Exception as e:
            print(f"\n❌ Error during content creation: {e}\n")
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message=f"Content creation failed: {e}", percentage=0
                )
            raise

    def export_content(self, content: str, output_dir: Path, formats: list = None):
        """
        Export content to multiple formats.

        Args:
            content: Content to export
            output_dir: Output directory
            formats: List of formats (markdown, html, txt)
        """
        formats = formats or ["markdown", "txt"]
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print("\n" + "=" * 60)
        print("💾 EXPORTING CONTENT")
        print("=" * 60)

        for fmt in formats:
            if fmt == "markdown":
                file_path = output_dir / f"content_{timestamp}.md"
                file_path.write_text(content, encoding="utf-8")
                print(f"✅ Markdown: {file_path}")

            elif fmt == "html":
                # Simple HTML wrapper
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Generated Content</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
        h1 {{ color: #333; }}
        p {{ line-height: 1.6; }}
    </style>
</head>
<body>
    {'<br>'.join(content.split('\n'))}
</body>
</html>"""
                file_path = output_dir / f"content_{timestamp}.html"
                file_path.write_text(html_content, encoding="utf-8")
                print(f"✅ HTML: {file_path}")

            elif fmt == "txt":
                file_path = output_dir / f"content_{timestamp}.txt"
                file_path.write_text(content, encoding="utf-8")
                print(f"✅ Text: {file_path}")

        print("=" * 60 + "\n")


async def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print(
            "Usage: python content_creator.py 'content task' [length=1000] [tone=professional]"
        )
        print("\nExamples:")
        print("  python content_creator.py 'blog post on AI ethics'")
        print(
            "  python content_creator.py 'technical documentation' length=2000 tone=technical"
        )
        sys.exit(1)

    task = sys.argv[1]

    # Parse context parameters
    context = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            key, value = arg.split("=", 1)
            # Try to parse as int, otherwise string
            try:
                context[key] = int(value)
            except ValueError:
                context[key] = value.strip('"')

    # Create control protocol for progress reporting
    transport = MemoryTransport()
    await transport.connect()
    control_protocol = ControlProtocol(transport)

    # Create content creator with Ollama (FREE)
    config = PEVAgentConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.7,  # Balanced creativity and coherence
        max_iterations=5,
        verification_strictness="medium",  # medium: balanced quality/speed
        enable_error_recovery=True,
    )

    creator = ContentCreator(
        config=config,
        control_protocol=control_protocol,
        enable_metrics=True,
    )

    try:
        # Create content
        result = await creator.create_content(task, context=context)

        # Export content
        output_dir = Path("./content_output")
        creator.export_content(
            content=result.get("final_result", ""),
            output_dir=output_dir,
            formats=["markdown", "html", "txt"],
        )

        # Show statistics
        print("\n" + "=" * 60)
        print("📈 CONTENT CREATION STATISTICS")
        print("=" * 60)
        print(f"Iterations: {len(result.get('refinements', []))}")
        print(
            f"Final Verification: {result.get('verification', {}).get('passed', False)}"
        )
        print(f"Word Count: {len(result.get('final_result', '').split())}")
        print("💰 Cost: $0.00 (using Ollama local inference)")
        print("=" * 60 + "\n")

    except KeyboardInterrupt:
        print("\n⚠️  Content creation interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during content creation: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
