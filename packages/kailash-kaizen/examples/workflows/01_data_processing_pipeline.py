"""
Production-Ready Data Processing Pipeline

Real-world use case: Process CSV files, transform data, generate reports
This agent autonomously reads files, validates data, and produces analytics.
"""

import asyncio
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class DataProcessingSignature(Signature):
    input_directory: str = InputField(description="Directory containing data files")
    output_directory: str = InputField(description="Directory for processed results")
    file_pattern: str = InputField(description="File pattern to match (e.g., *.csv)")
    result_summary: str = OutputField(description="Processing summary")
    files_processed: int = OutputField(description="Number of files processed")


@dataclass
class ProcessorConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1  # Low temperature for consistent processing


class DataProcessor(BaseAgent):
    """Production data processing agent with error handling and logging."""

    def __init__(self, config: ProcessorConfig):
        super().__init__(
            config=config,
            signature=DataProcessingSignature(),
        )

    async def process_directory(
        self, input_dir: str, output_dir: str, file_pattern: str = "*.txt"
    ) -> dict:
        """Process all matching files in directory."""

        results = {"processed": [], "failed": [], "summary": {}}

        # List directory contents
        list_result = await self.execute_tool("list_directory", {"path": input_dir})

        if not list_result.success:
            return {"error": f"Failed to list directory: {list_result.error}"}

        files = list_result.result.get("files", [])
        target_files = [
            f
            for f in files
            if f.get("is_file")
            and f.get("name", "").endswith(file_pattern.replace("*", ""))
        ]

        # Process each file
        for file_info in target_files:
            file_path = file_info.get("path")
            file_name = file_info.get("name")

            try:
                # Read file
                read_result = await self.execute_tool("read_file", {"path": file_path})

                if not read_result.success:
                    results["failed"].append(
                        {"file": file_name, "error": read_result.error}
                    )
                    continue

                content = read_result.result.get("content", "")

                # Analyze content
                analysis = self._analyze_content(content)

                # Generate report
                report = self._generate_report(file_name, analysis)

                # Write output
                output_path = os.path.join(output_dir, f"{file_name}.report.txt")
                write_result = await self.execute_tool(
                    "write_file", {"path": output_path, "content": report}
                )

                if write_result.success:
                    results["processed"].append(
                        {"file": file_name, "output": output_path, "analysis": analysis}
                    )
                else:
                    results["failed"].append(
                        {"file": file_name, "error": write_result.error}
                    )

            except Exception as e:
                results["failed"].append({"file": file_name, "error": str(e)})

        # Generate summary
        results["summary"] = {
            "total_files": len(target_files),
            "processed": len(results["processed"]),
            "failed": len(results["failed"]),
            "success_rate": (
                len(results["processed"]) / len(target_files) * 100
                if target_files
                else 0
            ),
        }

        return results

    def _analyze_content(self, content: str) -> dict:
        """Analyze file content and extract metrics."""
        lines = content.split("\n")
        words = content.split()

        return {
            "line_count": len(lines),
            "word_count": len(words),
            "char_count": len(content),
            "avg_line_length": len(content) / len(lines) if lines else 0,
            "non_empty_lines": len([l for l in lines if l.strip()]),
        }

    def _generate_report(self, filename: str, analysis: dict) -> str:
        """Generate formatted analysis report."""
        return f"""Data Analysis Report
{'=' * 50}

File: {filename}
Processed: {analysis.get('line_count')} lines, {analysis.get('word_count')} words

Metrics:
- Total Characters: {analysis.get('char_count')}
- Average Line Length: {analysis.get('avg_line_length', 0):.2f}
- Non-Empty Lines: {analysis.get('non_empty_lines')}

{'=' * 50}
"""


async def main():
    """Production pipeline execution."""

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required")
        return

    # Setup
    config = ProcessorConfig()
    processor = DataProcessor(config)

    # Configuration from environment or arguments
    input_dir = os.getenv("INPUT_DIR", "/tmp/data_input")
    output_dir = os.getenv("OUTPUT_DIR", "/tmp/data_output")

    # Ensure directories exist
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # Create sample data for demo
    sample_files = {
        "sales_data.txt": "Product A: 100 units\nProduct B: 200 units\nProduct C: 150 units",
        "inventory.txt": "Warehouse 1: 500 items\nWarehouse 2: 300 items",
    }

    for filename, content in sample_files.items():
        with open(os.path.join(input_dir, filename), "w") as f:
            f.write(content)

    # Execute pipeline
    print(f"Processing files from {input_dir}...")
    results = await processor.process_directory(input_dir, output_dir, "*.txt")

    # Output results
    if "error" in results:
        print(f"Pipeline failed: {results['error']}")
        return

    summary = results["summary"]
    print("\nProcessing Complete:")
    print(f"  Processed: {summary['processed']}/{summary['total_files']} files")
    print(f"  Success Rate: {summary['success_rate']:.1f}%")

    if results["failed"]:
        print("\nFailed files:")
        for failure in results["failed"]:
            print(f"  - {failure['file']}: {failure['error']}")

    print(f"\nReports saved to: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
