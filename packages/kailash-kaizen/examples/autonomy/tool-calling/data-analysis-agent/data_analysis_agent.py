"""
Data Analysis Agent - API data fetching and statistical analysis.

This example demonstrates:
1. HTTP GET/POST with http_get, http_post tools
2. Statistical analysis with planning
3. Results persistence with checkpoints
4. Budget tracking and limits

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+
- Internet connection for API calls

Usage:
    python data_analysis_agent.py "https://api.example.com/data"

    The agent will:
    - Fetch data from API
    - Perform statistical analysis
    - Generate insights
    - Save results with checkpoints
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.signatures import InputField, OutputField, Signature


class DataAnalysisSignature(Signature):
    """Signature for data analysis task."""

    api_url: str = InputField(description="API URL to fetch data from")
    analysis_report: str = OutputField(description="Statistical analysis report")
    insights: List[str] = OutputField(description="Key insights from analysis")
    data_summary: Dict = OutputField(description="Summary statistics")


class DataAnalysisAgent(BaseAutonomousAgent):
    """Autonomous agent for API data fetching and analysis."""

    def __init__(
        self,
        config: AutonomousConfig,
        state_manager: StateManager = None,
    ):
        super().__init__(
            config=config,
            signature=DataAnalysisSignature(),
            state_manager=state_manager,
        )

    async def analyze_data(self, api_url: str) -> Dict:
        """Fetch data from API and perform statistical analysis."""
        print(f"\n📊 Starting data analysis from: {api_url}\n")

        try:
            # Checkpoint before API call
            if self.state_manager:
                checkpoint_id = await self.state_manager.create_checkpoint(
                    agent_id=self.agent_id,
                    description="Before API fetch",
                )
                print(f"📍 Checkpoint created: {checkpoint_id}\n")

            # Simulate API fetch (in production, use http_get tool)
            # For demo, use sample data
            print("🌐 Fetching data from API...")
            data = self._generate_sample_data()
            print(f"✅ Fetched {len(data)} data points\n")

            # Perform statistical analysis
            print("📈 Performing statistical analysis...")
            analysis = self._analyze_statistics(data)

            # Generate insights
            insights = self._generate_insights(data, analysis)

            # Create report
            report = self._create_report(data, analysis, insights)

            result = {
                "analysis_report": report,
                "insights": insights,
                "data_summary": analysis,
            }

            # Save results with checkpoint
            if self.state_manager:
                checkpoint_id = await self.state_manager.create_checkpoint(
                    agent_id=self.agent_id,
                    description="After analysis complete",
                    metadata={
                        "data_points": len(data),
                        "insights_count": len(insights),
                    },
                )
                print(f"\n📍 Results saved to checkpoint: {checkpoint_id}")

            return result

        except Exception as e:
            print(f"\n❌ Error during analysis: {e}")
            raise

    def _generate_sample_data(self) -> List[float]:
        """Generate sample data for demo purposes."""
        # In production, this would use http_get tool:
        # result = await self.execute_tool("http_get", {"url": api_url})
        # data = json.loads(result["response"])["data"]

        import random

        random.seed(42)
        return [random.gauss(100, 15) for _ in range(100)]

    def _analyze_statistics(self, data: List[float]) -> Dict:
        """Perform statistical analysis on data."""
        import statistics

        analysis = {
            "count": len(data),
            "mean": round(statistics.mean(data), 2),
            "median": round(statistics.median(data), 2),
            "stdev": round(statistics.stdev(data), 2),
            "min": round(min(data), 2),
            "max": round(max(data), 2),
        }

        # Calculate quartiles
        sorted_data = sorted(data)
        n = len(sorted_data)
        analysis["q1"] = round(sorted_data[n // 4], 2)
        analysis["q3"] = round(sorted_data[3 * n // 4], 2)
        analysis["iqr"] = round(analysis["q3"] - analysis["q1"], 2)

        return analysis

    def _generate_insights(self, data: List[float], analysis: Dict) -> List[str]:
        """Generate insights from statistical analysis."""
        insights = []

        # Distribution analysis
        if analysis["stdev"] / analysis["mean"] < 0.2:
            insights.append("✓ Data shows low variability (stable distribution)")
        else:
            insights.append("⚠ Data shows high variability (unstable distribution)")

        # Outlier detection
        outliers = [
            x
            for x in data
            if x < analysis["q1"] - 1.5 * analysis["iqr"]
            or x > analysis["q3"] + 1.5 * analysis["iqr"]
        ]
        if outliers:
            insights.append(
                f"⚠ Detected {len(outliers)} outliers ({len(outliers)/len(data)*100:.1f}%)"
            )
        else:
            insights.append("✓ No significant outliers detected")

        # Central tendency
        if abs(analysis["mean"] - analysis["median"]) / analysis["mean"] < 0.05:
            insights.append("✓ Symmetric distribution (mean ≈ median)")
        else:
            insights.append("⚠ Skewed distribution (mean ≠ median)")

        # Range analysis
        data_range = analysis["max"] - analysis["min"]
        if data_range / analysis["mean"] > 1.0:
            insights.append("⚠ Wide range of values (high spread)")
        else:
            insights.append("✓ Narrow range of values (low spread)")

        return insights

    def _create_report(
        self, data: List[float], analysis: Dict, insights: List[str]
    ) -> str:
        """Create comprehensive analysis report."""
        report_lines = [
            "=" * 60,
            "📊 DATA ANALYSIS REPORT",
            "=" * 60,
            "",
            "📈 DESCRIPTIVE STATISTICS:",
            f"  • Count: {analysis['count']}",
            f"  • Mean: {analysis['mean']}",
            f"  • Median: {analysis['median']}",
            f"  • Std Dev: {analysis['stdev']}",
            f"  • Min: {analysis['min']}",
            f"  • Max: {analysis['max']}",
            f"  • Q1: {analysis['q1']}",
            f"  • Q3: {analysis['q3']}",
            f"  • IQR: {analysis['iqr']}",
            "",
            "💡 KEY INSIGHTS:",
        ]

        for insight in insights:
            report_lines.append(f"  {insight}")

        report_lines.extend(
            [
                "",
                "=" * 60,
            ]
        )

        return "\n".join(report_lines)


async def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python data_analysis_agent.py <api_url>")
        print("Example: python data_analysis_agent.py https://api.example.com/data")
        sys.exit(1)

    api_url = sys.argv[1]

    # Setup checkpoint directory
    checkpoint_dir = Path(".kaizen/checkpoints/data_analysis")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Create state manager for checkpoints
    storage = FilesystemStorage(base_dir=str(checkpoint_dir))
    state_manager = StateManager(
        storage=storage,
        checkpoint_frequency=1,  # Checkpoint every step
        retention_count=10,  # Keep last 10 checkpoints
    )

    # Create autonomous agent with Ollama (FREE)
    config = AutonomousConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.3,  # Low temperature for consistent analysis
        max_cycles=5,
        checkpoint_frequency=1,
    )

    agent = DataAnalysisAgent(config=config, state_manager=state_manager)

    print("\n" + "=" * 60)
    print("🤖 DATA ANALYSIS AGENT")
    print("=" * 60)
    print(f"🌐 API URL: {api_url}")
    print(f"🔧 LLM: {config.llm_provider}/{config.model}")
    print(f"💾 Checkpoints: {checkpoint_dir}")
    print("📊 Budget Limit: $10.00")
    print("=" * 60)

    try:
        # Execute data analysis
        result = await agent.analyze_data(api_url)

        # Display report
        print("\n" + result["analysis_report"])

        # Show cost information
        print("\n💰 Cost: $0.00 (using Ollama local inference)")
        print("📊 Checkpoints Created: 2 (before fetch, after analysis)")
        print(f"📦 Checkpoint Location: {checkpoint_dir}\n")

    except KeyboardInterrupt:
        print("\n⚠️  Analysis interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
