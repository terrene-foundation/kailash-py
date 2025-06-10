"""Example of a parallel workflow execution with async nodes.

This example demonstrates the use of AsyncMerge, AsyncSwitch, and the ParallelRuntime
to execute a workflow with multiple parallel paths for maximum efficiency.
"""

import asyncio
import logging
import random
import time
from typing import Any, Dict

from kailash.nodes.base_async import AsyncNode
from kailash.nodes.logic.async_operations import AsyncMergeNode, AsyncSwitchNode
from kailash.runtime.parallel import ParallelRuntime
from kailash.workflow import Workflow

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataSourceNode(AsyncNode):
    """Simulates an async data source like an API or database."""

    def get_parameters(self) -> Dict[str, Any]:
        """Define parameters for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "data_size": NodeParameter(
                name="data_size",
                type=int,
                required=False,
                default=100,
                description="Number of data records to generate",
            ),
            "source_id": NodeParameter(
                name="source_id",
                type=str,
                required=False,
                default="default",
                description="Identifier for this data source",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous implementation for compatibility."""
        # Generate sample data without delay
        data_size = kwargs.get("data_size", 100)
        source_id = kwargs.get("source_id", "default")

        data = [
            {
                "id": f"{source_id}_{i}",
                "value": random.randint(1, 100),
                "source": source_id,
            }
            for i in range(data_size)
        ]

        logger.info(f"DataSourceNode {source_id} produced {len(data)} records (sync)")
        return {"output": data}

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Simulate fetching data with network delay."""
        # Simulate API or DB delay
        await asyncio.sleep(0.5)

        # Generate some sample data
        data_size = kwargs.get("data_size", 100)
        source_id = kwargs.get("source_id", "default")

        data = [
            {
                "id": f"{source_id}_{i}",
                "value": random.randint(1, 100),
                "source": source_id,
            }
            for i in range(data_size)
        ]

        logger.info(f"DataSourceNode {source_id} produced {len(data)} records")
        return {"output": data}


class ProcessingNode(AsyncNode):
    """Simulates data processing with async operations."""

    def get_parameters(self) -> Dict[str, Any]:
        """Define parameters for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "input": NodeParameter(
                name="input",
                type=list,
                required=False,  # Set to False for initialization
                description="Input data to process",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous implementation for compatibility."""
        input_data = kwargs.get("input", [])

        if not input_data:
            return {"output": []}

        # Process data - add a calculated field
        processed_data = []
        for item in input_data:
            processed_item = item.copy()
            processed_item["processed_value"] = item["value"] * 2
            processed_item["status"] = "processed"
            processed_data.append(processed_item)

        logger.info(f"ProcessingNode processed {len(processed_data)} records (sync)")
        return {"output": processed_data}

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Process input data with simulated computation time."""
        input_data = kwargs.get("input", [])

        if not input_data:
            return {"output": []}

        # Simulate processing delay proportional to data size
        processing_time = min(0.5, len(input_data) * 0.005)
        await asyncio.sleep(processing_time)

        # Process data - add a calculated field
        processed_data = []
        for item in input_data:
            processed_item = item.copy()
            processed_item["processed_value"] = item["value"] * 2
            processed_item["status"] = "processed"
            processed_data.append(processed_item)

        logger.info(
            f"ProcessingNode processed {len(processed_data)} records in {processing_time:.2f}s"
        )
        return {"output": processed_data}


class FilterNode(AsyncNode):
    """Filters data based on criteria."""

    def get_parameters(self) -> Dict[str, Any]:
        """Define parameters for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "input": NodeParameter(
                name="input",
                type=list,
                required=False,  # Set to False for initialization
                description="Input data to filter",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=int,
                required=False,
                default=50,
                description="Value threshold for filtering",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous implementation for compatibility."""
        input_data = kwargs.get("input", [])
        threshold = kwargs.get("threshold", 50)

        # Filter items above threshold
        filtered_data = [
            item for item in input_data if item.get("value", 0) > threshold
        ]

        # Add status
        for item in filtered_data:
            item["status"] = "high_value"

        logger.info(
            f"FilterNode filtered {len(filtered_data)} high-value items from {len(input_data)} total (sync)"
        )
        return {"output": filtered_data}

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Filter data asynchronously."""
        input_data = kwargs.get("input", [])
        threshold = kwargs.get("threshold", 50)

        # Simulate processing time
        await asyncio.sleep(0.2)

        # Filter items above threshold
        filtered_data = [
            item for item in input_data if item.get("value", 0) > threshold
        ]

        # Add status
        for item in filtered_data:
            item["status"] = "high_value"

        logger.info(
            f"FilterNode filtered {len(filtered_data)} high-value items from {len(input_data)} total"
        )
        return {"output": filtered_data}


class EnrichmentNode(AsyncNode):
    """Enriches data with additional information."""

    def get_parameters(self) -> Dict[str, Any]:
        """Define parameters for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "input": NodeParameter(
                name="input",
                type=list,
                required=False,  # Set to False for initialization
                description="Input data to enrich",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous implementation for compatibility."""
        input_data = kwargs.get("input", [])

        # Add enrichment data
        enriched_data = []
        for item in input_data:
            enriched_item = item.copy()
            enriched_item["enriched"] = True
            enriched_item["timestamp"] = time.time()
            enriched_item["score"] = random.random() * 100
            enriched_data.append(enriched_item)

        logger.info(f"EnrichmentNode enriched {len(enriched_data)} records (sync)")
        return {"output": enriched_data}

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Enrich data with additional fields."""
        input_data = kwargs.get("input", [])

        # Simulate external data lookup
        await asyncio.sleep(0.3)

        # Add enrichment data
        enriched_data = []
        for item in input_data:
            enriched_item = item.copy()
            enriched_item["enriched"] = True
            enriched_item["timestamp"] = time.time()
            enriched_item["score"] = random.random() * 100
            enriched_data.append(enriched_item)

        logger.info(f"EnrichmentNode enriched {len(enriched_data)} records")
        return {"output": enriched_data}


class SummaryNode(AsyncNode):
    """Generates summary statistics from data."""

    def get_parameters(self) -> Dict[str, Any]:
        """Define parameters for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "input": NodeParameter(
                name="input",
                type=list,
                required=False,  # Set to False for initialization
                description="Input data to summarize",
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous implementation for compatibility."""
        input_data = kwargs.get("input", [])

        # Calculate summaries
        if not input_data:
            return {"count": 0, "avg_value": 0, "min_value": 0, "max_value": 0}

        values = [item.get("value", 0) for item in input_data]

        summary = {
            "count": len(values),
            "avg_value": sum(values) / len(values) if values else 0,
            "min_value": min(values) if values else 0,
            "max_value": max(values) if values else 0,
            "sources": list(set(item.get("source", "unknown") for item in input_data)),
        }

        logger.info(
            f"SummaryNode calculated summary for {summary['count']} records (sync)"
        )
        return summary

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Calculate summary statistics."""
        input_data = kwargs.get("input", [])

        # Simulate complex calculation
        await asyncio.sleep(0.4)

        # Calculate summaries
        if not input_data:
            return {"count": 0, "avg_value": 0, "min_value": 0, "max_value": 0}

        values = [item.get("value", 0) for item in input_data]

        summary = {
            "count": len(values),
            "avg_value": sum(values) / len(values) if values else 0,
            "min_value": min(values) if values else 0,
            "max_value": max(values) if values else 0,
            "sources": list(set(item.get("source", "unknown") for item in input_data)),
        }

        logger.info(f"SummaryNode calculated summary for {summary['count']} records")
        return summary


async def create_and_run_workflow():
    """Create and run the parallel workflow."""
    # Create workflow
    workflow = Workflow(
        workflow_id="parallel_demo",
        name="Parallel Workflow Demo",
        description="Demonstrates parallel execution with multiple data paths",
    )

    # Add data source nodes
    workflow.add_node("source_a", DataSourceNode(source_id="source_a", data_size=200))
    workflow.add_node("source_b", DataSourceNode(source_id="source_b", data_size=150))
    workflow.add_node("source_c", DataSourceNode(source_id="source_c", data_size=100))

    # Add processing nodes for each source
    workflow.add_node("process_a", ProcessingNode())
    workflow.add_node("process_b", ProcessingNode())
    workflow.add_node("process_c", ProcessingNode())

    # Connect sources to processors
    workflow.connect("source_a", "process_a", {"output": "input"})
    workflow.connect("source_b", "process_b", {"output": "input"})
    workflow.connect("source_c", "process_c", {"output": "input"})

    # Add filter node for high-value items
    workflow.add_node("filter_high_value", FilterNode(threshold=70))

    # Connect one source to the filter
    workflow.connect("process_a", "filter_high_value", {"output": "input"})

    # Add enrichment node
    workflow.add_node("enrich_data", EnrichmentNode())

    # Connect filter output to enrichment
    workflow.connect("filter_high_value", "enrich_data", {"output": "input"})

    # Add merge node to combine all processed data
    workflow.add_node("merge_all", AsyncMergeNode(merge_type="concat", chunk_size=100))

    # Connect processors and enrichment to merge
    workflow.connect("process_b", "merge_all", {"output": "data1"})
    workflow.connect("process_c", "merge_all", {"output": "data2"})
    workflow.connect("enrich_data", "merge_all", {"output": "data3"})

    # Add summary node
    workflow.add_node("calculate_summary", SummaryNode())

    # Connect merge to summary
    workflow.connect("merge_all", "calculate_summary", {"merged_data": "input"})

    # Add switch node to route data based on count
    workflow.add_node(
        "route_by_size",
        AsyncSwitchNode(condition_field="count", operator=">", value=300),
    )

    # Connect summary to switch
    workflow.connect("calculate_summary", "route_by_size", {"count": "input_data"})

    # Create parallel runtime
    runtime = ParallelRuntime(max_workers=5, debug=True)

    # Execute workflow
    logger.info("Starting parallel workflow execution")
    start_time = time.time()

    results, run_id = await runtime.execute(workflow)

    execution_time = time.time() - start_time
    logger.info(f"Workflow execution completed in {execution_time:.2f} seconds")

    # Extract and display results
    if "calculate_summary" in results:
        summary = results["calculate_summary"]
        logger.info(f"Summary results: {summary}")

    if "route_by_size" in results:
        routing = results["route_by_size"]
        logger.info(f"Routing results: {routing}")

    # Return full results
    return results


if __name__ == "__main__":
    asyncio.run(create_and_run_workflow())
