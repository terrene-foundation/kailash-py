"""
Production-Ready API Integration Workflow

Real-world use case: Aggregate data from multiple REST APIs, merge results, generate reports
This agent autonomously fetches data, handles retries, validates responses, and consolidates results.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class APIAggregationSignature(Signature):
    endpoints: List[str] = InputField(description="List of API endpoints to fetch")
    aggregated_data: dict = OutputField(description="Merged API responses")
    summary: dict = OutputField(description="Aggregation statistics")


@dataclass
class APIAgentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30


class APIAggregator(BaseAgent):
    """Production API integration agent with retry logic and error handling."""

    def __init__(self, config: APIAgentConfig):
        super().__init__(
            config=config,
            signature=APIAggregationSignature(),
        )
        self.max_retries = config.max_retries
        self.retry_delay = config.retry_delay
        self.timeout = config.timeout

    async def fetch_with_retry(self, endpoint: str, retry_count: int = 0) -> Dict:
        """Fetch API with exponential backoff retry."""

        result = await self.execute_tool(
            "http_get", {"url": endpoint, "timeout": self.timeout}
        )

        if result.success:
            try:
                response_data = result.result.get("response", {})
                if isinstance(response_data, str):
                    response_data = json.loads(response_data)

                return {
                    "endpoint": endpoint,
                    "status": "success",
                    "data": response_data,
                    "status_code": result.result.get("status_code", 200),
                }
            except json.JSONDecodeError as e:
                return {
                    "endpoint": endpoint,
                    "status": "error",
                    "error": f"JSON decode error: {str(e)}",
                    "raw_response": result.result.get("response", "")[:200],
                }
        else:
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (2**retry_count)
                await asyncio.sleep(wait_time)
                return await self.fetch_with_retry(endpoint, retry_count + 1)

            return {
                "endpoint": endpoint,
                "status": "error",
                "error": result.error,
                "retries": retry_count,
            }

    async def aggregate_endpoints(
        self, endpoints: List[str], output_path: Optional[str] = None
    ) -> Dict:
        """Fetch multiple APIs concurrently and aggregate results."""

        results = {
            "successful": [],
            "failed": [],
            "data": {},
            "stats": {"total": len(endpoints), "success": 0, "failed": 0},
        }

        fetch_tasks = [self.fetch_with_retry(endpoint) for endpoint in endpoints]
        responses = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for response in responses:
            if isinstance(response, Exception):
                results["failed"].append({"error": str(response), "type": "exception"})
                results["stats"]["failed"] += 1
                continue

            endpoint = response.get("endpoint")

            if response.get("status") == "success":
                results["successful"].append(endpoint)
                results["data"][endpoint] = response.get("data")
                results["stats"]["success"] += 1
            else:
                results["failed"].append(
                    {
                        "endpoint": endpoint,
                        "error": response.get("error"),
                        "retries": response.get("retries", 0),
                    }
                )
                results["stats"]["failed"] += 1

        if output_path:
            report = self._generate_report(results)
            write_result = await self.execute_tool(
                "write_file", {"path": output_path, "content": report}
            )

            if write_result.success:
                results["report_path"] = output_path

        return results

    def _generate_report(self, results: Dict) -> str:
        """Generate aggregation report."""

        report_lines = [
            "=" * 80,
            "API Aggregation Report",
            "=" * 80,
            "",
            f"Total Endpoints: {results['stats']['total']}",
            f"Successful: {results['stats']['success']}",
            f"Failed: {results['stats']['failed']}",
            f"Success Rate: {(results['stats']['success'] / results['stats']['total'] * 100):.1f}%",
            "",
            "=" * 80,
            "Successful Endpoints:",
            "=" * 80,
        ]

        for endpoint in results["successful"]:
            data_size = len(json.dumps(results["data"].get(endpoint, {})))
            report_lines.append(f"  ✓ {endpoint} ({data_size} bytes)")

        if results["failed"]:
            report_lines.extend(
                [
                    "",
                    "=" * 80,
                    "Failed Endpoints:",
                    "=" * 80,
                ]
            )

            for failure in results["failed"]:
                endpoint = failure.get("endpoint", "unknown")
                error = failure.get("error", "Unknown error")
                retries = failure.get("retries", 0)
                report_lines.append(f"  ✗ {endpoint}")
                report_lines.append(f"    Error: {error}")
                if retries > 0:
                    report_lines.append(f"    Retries: {retries}")

        report_lines.extend(["", "=" * 80])
        return "\n".join(report_lines)

    async def transform_and_save(
        self, data: Dict, output_path: str, format: str = "json"
    ) -> Dict:
        """Transform aggregated data and save to file."""

        if format == "json":
            content = json.dumps(data, indent=2)
        elif format == "csv":
            content = self._dict_to_csv(data)
        else:
            content = str(data)

        write_result = await self.execute_tool(
            "write_file", {"path": output_path, "content": content}
        )

        if write_result.success:
            return {
                "status": "success",
                "path": output_path,
                "format": format,
                "size": len(content),
            }
        else:
            return {"status": "error", "error": write_result.error}

    def _dict_to_csv(self, data: Dict) -> str:
        """Convert nested dict to CSV format."""
        lines = ["endpoint,status,data_keys"]

        for endpoint, value in data.items():
            if isinstance(value, dict):
                keys = ",".join(value.keys())
                lines.append(f'"{endpoint}",success,"{keys}"')
            else:
                lines.append(f'"{endpoint}",success,"{str(value)[:50]}"')

        return "\n".join(lines)


async def main():
    """Production API aggregation workflow."""

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required")
        return

    config = APIAgentConfig()
    agent = APIAggregator(config)

    endpoints = os.getenv("API_ENDPOINTS", "").split(",")
    if not endpoints or endpoints == [""]:
        endpoints = [
            "https://api.github.com/repos/python/cpython",
            "https://api.github.com/repos/microsoft/vscode",
            "https://api.github.com/repos/torvalds/linux",
        ]

    output_dir = os.getenv("OUTPUT_DIR", "/tmp/api_results")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Fetching {len(endpoints)} API endpoints...")
    results = await agent.aggregate_endpoints(
        endpoints, output_path=os.path.join(output_dir, "aggregation_report.txt")
    )

    print("\nAggregation Complete:")
    print(f"  Success: {results['stats']['success']}/{results['stats']['total']}")
    print(f"  Failed: {results['stats']['failed']}/{results['stats']['total']}")

    if results["successful"]:
        print("\nSaving aggregated data...")
        save_result = await agent.transform_and_save(
            results["data"],
            os.path.join(output_dir, "aggregated_data.json"),
            format="json",
        )

        if save_result["status"] == "success":
            print(f"  Saved: {save_result['path']} ({save_result['size']} bytes)")

    if results.get("report_path"):
        print(f"\nReport saved: {results['report_path']}")


if __name__ == "__main__":
    asyncio.run(main())
