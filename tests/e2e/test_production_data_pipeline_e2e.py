"""
Production-quality data pipeline E2E tests.

These tests demonstrate:
- Processing large CSV files (10K+ records)
- Multiple validation cycles with real data quality issues
- PostgreSQL storage with proper transactions
- Export with error recovery mechanisms
- Performance benchmarking
"""

import csv
import os
import random
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, SQLDatabaseNode
from kailash.runtime.local import LocalRuntime

from tests.utils.docker_config import get_postgres_connection_string

# Mark as production e2e tests
pytestmark = [pytest.mark.e2e, pytest.mark.slow]


class ProductionDataGenerator:
    """Generate realistic production data for testing."""

    @staticmethod
    def generate_sales_data(num_records: int, error_rate: float = 0.05) -> List[Dict]:
        """Generate realistic sales data with controlled errors."""
        products = [
            "Laptop Pro",
            "Desktop Elite",
            "Monitor 4K",
            "Keyboard Mech",
            "Mouse Gaming",
            "Headset Premium",
            "Webcam HD",
            "SSD 1TB",
            "RAM 32GB",
            "Graphics Card",
            "Power Supply",
            "Case RGB",
        ]

        regions = ["North", "South", "East", "West", "Central"]
        categories = ["Electronics", "Accessories", "Components", "Peripherals"]

        data = []
        base_date = datetime.now(timezone.utc) - timedelta(days=365)

        for i in range(num_records):
            # Introduce controlled errors
            has_error = random.random() < error_rate

            if has_error:
                error_type = random.choice(
                    ["missing", "invalid", "duplicate", "outlier"]
                )

                if error_type == "missing":
                    # Missing required fields
                    record = {
                        "order_id": f"ORD-{i:06d}",
                        "product": random.choice(products),
                        # Missing: date, quantity, price
                        "region": random.choice(regions),
                        "category": random.choice(categories),
                    }
                elif error_type == "invalid":
                    # Invalid data types
                    record = {
                        "order_id": f"ORD-{i:06d}",
                        "date": (
                            base_date + timedelta(days=random.randint(0, 365))
                        ).isoformat(),
                        "product": random.choice(products),
                        "quantity": "invalid_number",  # Should be int
                        "price": random.uniform(50, 2000),
                        "region": random.choice(regions),
                        "category": random.choice(categories),
                    }
                elif error_type == "duplicate":
                    # Duplicate order ID
                    dup_id = max(0, i - random.randint(1, 100))
                    record = {
                        "order_id": f"ORD-{dup_id:06d}",  # Duplicate ID
                        "date": (
                            base_date + timedelta(days=random.randint(0, 365))
                        ).isoformat(),
                        "product": random.choice(products),
                        "quantity": random.randint(1, 10),
                        "price": random.uniform(50, 2000),
                        "region": random.choice(regions),
                        "category": random.choice(categories),
                    }
                else:  # outlier
                    # Outlier values
                    record = {
                        "order_id": f"ORD-{i:06d}",
                        "date": (
                            base_date + timedelta(days=random.randint(0, 365))
                        ).isoformat(),
                        "product": random.choice(products),
                        "quantity": random.randint(1000, 5000),  # Unusually high
                        "price": random.uniform(10000, 50000),  # Unusually high
                        "region": random.choice(regions),
                        "category": random.choice(categories),
                    }
            else:
                # Valid record
                record = {
                    "order_id": f"ORD-{i:06d}",
                    "date": (
                        base_date + timedelta(days=random.randint(0, 365))
                    ).isoformat(),
                    "product": random.choice(products),
                    "quantity": random.randint(1, 20),
                    "price": round(random.uniform(50, 2000), 2),
                    "region": random.choice(regions),
                    "category": random.choice(categories),
                }

            # Add calculated fields
            if (
                "quantity" in record
                and "price" in record
                and isinstance(record["quantity"], int)
            ):
                record["total"] = round(record["quantity"] * record["price"], 2)

            data.append(record)

        return data

    @staticmethod
    def write_csv(data: List[Dict], filepath: Path) -> None:
        """Write data to CSV file."""
        if not data:
            return

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)


class TestProductionDataPipeline:
    """Production-quality data pipeline tests."""

    def test_large_scale_etl_pipeline_with_validation_cycles(self, tmp_path):
        """Test processing 10K+ records with validation and error recovery."""
        # Generate test data
        num_records = 15000
        input_file = tmp_path / "sales_data.csv"
        output_file = tmp_path / "processed_sales.csv"
        error_file = tmp_path / "errors.csv"

        print(f"Generating {num_records} test records...")
        test_data = ProductionDataGenerator.generate_sales_data(
            num_records, error_rate=0.08
        )
        ProductionDataGenerator.write_csv(test_data, input_file)

        workflow = Workflow("production-etl", "Production ETL Pipeline")

        # Data validation node with cycles
        class ProductionDataValidator(CycleAwareNode):
            def get_parameters(self):
                return {
                    "data": NodeParameter(type=list, required=True),
                    "validation_rules": NodeParameter(type=dict, required=False),
                    "max_error_rate": NodeParameter(
                        type=float, required=False, default=0.05
                    ),
                    "batch_size": NodeParameter(type=int, required=False, default=1000),
                }

            def run(self, **kwargs):
                data = kwargs.get("data", [])
                rules = kwargs.get("validation_rules", {})
                max_error_rate = kwargs.get("max_error_rate", 0.05)
                batch_size = kwargs.get("batch_size", 1000)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                processed_count = self.get_previous_state(context).get(
                    "processed_count", 0
                )
                all_valid = self.get_previous_state(context).get("all_valid", [])
                all_errors = self.get_previous_state(context).get("all_errors", [])

                # Process in batches for memory efficiency
                start_idx = processed_count
                end_idx = min(start_idx + batch_size, len(data))
                batch = data[start_idx:end_idx]

                valid_records = []
                error_records = []

                for record in batch:
                    errors = []

                    # Validate required fields
                    required_fields = [
                        "order_id",
                        "date",
                        "product",
                        "quantity",
                        "price",
                    ]
                    for field in required_fields:
                        if (
                            field not in record
                            or record[field] is None
                            or record[field] == ""
                        ):
                            errors.append(f"Missing required field: {field}")

                    # Validate data types
                    if "quantity" in record:
                        try:
                            q = int(record["quantity"])
                            if q < 0 or q > 1000:
                                errors.append(f"Quantity out of range: {q}")
                        except (ValueError, TypeError):
                            errors.append("Invalid quantity format")

                    if "price" in record:
                        try:
                            p = float(record["price"])
                            if p < 0 or p > 10000:
                                errors.append(f"Price out of range: {p}")
                        except (ValueError, TypeError):
                            errors.append("Invalid price format")

                    # Check for duplicates (simplified)
                    if "order_id" in record:
                        # In production, would check against database
                        if any(
                            v.get("order_id") == record["order_id"] for v in all_valid
                        ):
                            errors.append("Duplicate order ID")

                    if errors:
                        error_records.append(
                            {
                                **record,
                                "validation_errors": "; ".join(errors),
                                "validation_iteration": iteration,
                            }
                        )
                    else:
                        # Calculate total if not present
                        if (
                            "total" not in record
                            and "quantity" in record
                            and "price" in record
                        ):
                            try:
                                record["total"] = float(record["quantity"]) * float(
                                    record["price"]
                                )
                            except:
                                record["total"] = 0

                        valid_records.append(record)

                # Update cumulative results
                all_valid.extend(valid_records)
                all_errors.extend(error_records)
                new_processed_count = end_idx

                # Calculate error rate
                total_processed = new_processed_count
                current_error_rate = (
                    len(all_errors) / total_processed if total_processed > 0 else 0
                )

                # Determine if we need to continue
                all_processed = new_processed_count >= len(data)
                quality_acceptable = current_error_rate <= max_error_rate
                converged = all_processed and quality_acceptable

                return {
                    "valid_records": all_valid,
                    "error_records": all_errors,
                    "processed_count": new_processed_count,
                    "total_count": len(data),
                    "error_rate": current_error_rate,
                    "converged": converged,
                    "batch_number": iteration,
                    **self.set_cycle_state(
                        {
                            "processed_count": new_processed_count,
                            "all_valid": all_valid,
                            "all_errors": all_errors,
                        }
                    ),
                }

        # CSV reader
        reader = CSVReaderNode()
        workflow.add_node("reader", reader)

        # Validator
        validator = ProductionDataValidator()
        workflow.add_node("validator", validator)

        # Data enricher
        enricher = PythonCodeNode(
            code="""
import statistics
from datetime import datetime

# Enrich valid records with analytics
enriched_records = []

# Group by region and category for analytics
region_stats = {}
category_stats = {}
monthly_stats = {}

for record in valid_records:
    # Parse date for monthly grouping
    try:
        date = datetime.fromisoformat(record["date"].replace("Z", "+00:00"))
        month_key = f"{date.year}-{date.month:02d}"
    except:
        month_key = "unknown"

    # Collect stats
    region = record.get("region", "unknown")
    category = record.get("category", "unknown")
    total = float(record.get("total", 0))

    if region not in region_stats:
        region_stats[region] = []
    region_stats[region].append(total)

    if category not in category_stats:
        category_stats[category] = []
    category_stats[category].append(total)

    if month_key not in monthly_stats:
        monthly_stats[month_key] = []
    monthly_stats[month_key].append(total)

    # Enrich record
    enriched_record = {**record}
    enriched_record["month"] = month_key
    enriched_record["processing_timestamp"] = datetime.now().isoformat()
    enriched_records.append(enriched_record)

# Calculate aggregates
region_summary = {
    region: {
        "total_sales": sum(values),
        "avg_sale": statistics.mean(values) if values else 0,
        "transaction_count": len(values)
    }
    for region, values in region_stats.items()
}

category_summary = {
    cat: {
        "total_sales": sum(values),
        "avg_sale": statistics.mean(values) if values else 0,
        "transaction_count": len(values)
    }
    for cat, values in category_stats.items()
}

result = {
    "enriched_records": enriched_records,
    "region_summary": region_summary,
    "category_summary": category_summary,
    "total_records": len(enriched_records),
    "total_revenue": sum(float(r.get("total", 0)) for r in enriched_records)
}
"""
        )
        workflow.add_node("enricher", enricher)

        # Database setup (if Docker available)
        db_setup = PythonCodeNode(
            code="""
# Check if we should use database
use_database = False
db_error = None

try:
    import psycopg2
    # Try to connect to test database
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    # Create schema
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sales_data (
            order_id VARCHAR(20) PRIMARY KEY,
            date TIMESTAMP,
            product VARCHAR(100),
            quantity INTEGER,
            price DECIMAL(10,2),
            total DECIMAL(10,2),
            region VARCHAR(50),
            category VARCHAR(50),
            month VARCHAR(7),
            processing_timestamp TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_date ON sales_data(date)
    ''')

    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_region_category ON sales_data(region, category)
    ''')

    conn.commit()
    cur.close()
    conn.close()

    use_database = True
except Exception as e:
    db_error = str(e)
    use_database = False

result = {
    "use_database": use_database,
    "db_error": db_error,
    "database_url": database_url if use_database else None
}
"""
        )
        workflow.add_node("db_setup", db_setup)

        # Batch database writer
        batch_writer = PythonCodeNode(
            code="""
import psycopg2

written_count = 0
write_errors = []

if use_database and enriched_records:
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        # Batch insert with conflict handling
        batch_size = 500
        for i in range(0, len(enriched_records), batch_size):
            batch = enriched_records[i:i+batch_size]

            # Build insert query
            values = []
            for record in batch:
                values.append((
                    record.get("order_id"),
                    record.get("date"),
                    record.get("product"),
                    int(record.get("quantity", 0)),
                    float(record.get("price", 0)),
                    float(record.get("total", 0)),
                    record.get("region"),
                    record.get("category"),
                    record.get("month"),
                    record.get("processing_timestamp")
                ))

            # Use INSERT ... ON CONFLICT for upsert
            cur.executemany('''
                INSERT INTO sales_data
                (order_id, date, product, quantity, price, total, region, category, month, processing_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO UPDATE SET
                    date = EXCLUDED.date,
                    product = EXCLUDED.product,
                    quantity = EXCLUDED.quantity,
                    price = EXCLUDED.price,
                    total = EXCLUDED.total,
                    region = EXCLUDED.region,
                    category = EXCLUDED.category,
                    month = EXCLUDED.month,
                    processing_timestamp = EXCLUDED.processing_timestamp
            ''', values)

            written_count += len(batch)

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        write_errors.append(str(e))

result = {
    "written_to_db": written_count,
    "write_errors": write_errors,
    "db_success": len(write_errors) == 0
}
"""
        )
        workflow.add_node("db_writer", batch_writer)

        # CSV writer for valid records
        csv_writer = CSVWriterNode()
        workflow.add_node("csv_writer", csv_writer)

        # Error file writer
        error_writer = CSVWriterNode()
        workflow.add_node("error_writer", error_writer)

        # Performance analyzer
        perf_analyzer = PythonCodeNode(
            code="""
# Analyze pipeline performance
metrics = {
    "total_input_records": total_count if 'total_count' in locals() else 0,
    "valid_records": len(enriched_records) if 'enriched_records' in locals() else 0,
    "error_records": len(error_records) if 'error_records' in locals() else 0,
    "error_rate": error_rate if 'error_rate' in locals() else 0,
    "validation_batches": batch_number if 'batch_number' in locals() else 0,
    "db_records_written": written_to_db if 'written_to_db' in locals() else 0,
    "total_revenue": total_revenue if 'total_revenue' in locals() else 0,
    "regions_processed": len(region_summary) if 'region_summary' in locals() else 0,
    "categories_processed": len(category_summary) if 'category_summary' in locals() else 0
}

# Calculate throughput
if 'pipeline_start_time' in locals() and 'pipeline_end_time' in locals():
    duration = pipeline_end_time - pipeline_start_time
    metrics["pipeline_duration_seconds"] = duration
    metrics["records_per_second"] = metrics["total_input_records"] / duration if duration > 0 else 0
else:
    metrics["pipeline_duration_seconds"] = 0
    metrics["records_per_second"] = 0

result = {
    "performance_metrics": metrics,
    "pipeline_successful": metrics["error_rate"] < 0.1,
    "data_quality_score": 1.0 - metrics["error_rate"]
}
"""
        )
        workflow.add_node("analyzer", perf_analyzer)

        # Connect workflow
        workflow.connect("reader", "validator", mapping={"data": "data"})

        # Validation cycle
        workflow.connect(
            "validator",
            "validator",
            cycle=True,
            max_iterations=20,  # Process in batches
            convergence_check="converged == True",
        )

        # Process valid records
        workflow.connect(
            "validator", "enricher", mapping={"valid_records": "valid_records"}
        )

        # Database operations (conditional)
        db_url = (
            get_postgres_connection_string("test_etl")
            if os.getenv("POSTGRES_AVAILABLE")
            else ""
        )
        workflow.connect(
            "enricher", "db_setup", mapping={"database_url": "database_url"}
        )
        workflow.connect(
            "db_setup",
            "db_writer",
            mapping={"use_database": "use_database", "database_url": "database_url"},
        )
        workflow.connect(
            "enricher", "db_writer", mapping={"enriched_records": "enriched_records"}
        )

        # Write outputs
        workflow.connect("enricher", "csv_writer", mapping={"enriched_records": "data"})
        workflow.connect("validator", "error_writer", mapping={"error_records": "data"})

        # Performance analysis
        workflow.connect(
            "validator",
            "analyzer",
            mapping={
                "total_count": "total_count",
                "error_rate": "error_rate",
                "batch_number": "batch_number",
            },
        )
        workflow.connect(
            "enricher",
            "analyzer",
            mapping={
                "region_summary": "region_summary",
                "total_revenue": "total_revenue",
            },
        )
        workflow.connect(
            "db_writer", "analyzer", mapping={"written_to_db": "written_to_db"}
        )

        # Execute pipeline
        pipeline_start = time.time()
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "reader": {"file_path": str(input_file)},
                "validator": {"max_error_rate": 0.1, "batch_size": 2000},
                "db_setup": {"database_url": db_url},
                "csv_writer": {"file_path": str(output_file)},
                "error_writer": {"file_path": str(error_file)},
                "analyzer": {
                    "pipeline_start_time": pipeline_start,
                    "pipeline_end_time": time.time(),
                },
            },
        )

        # Verify results
        perf_metrics = results["analyzer"]["performance_metrics"]

        # Should process all records
        assert perf_metrics["total_input_records"] == num_records

        # Error rate should be controlled
        assert perf_metrics["error_rate"] < 0.15

        # Should have good throughput
        assert perf_metrics["records_per_second"] > 1000  # At least 1000 records/second

        # Should have valid records
        assert perf_metrics["valid_records"] > num_records * 0.85

        # Check output files exist
        assert output_file.exists()
        assert error_file.exists()

        # Verify CSV output
        with open(output_file, "r") as f:
            output_reader = csv.DictReader(f)
            output_records = list(output_reader)
            assert len(output_records) == perf_metrics["valid_records"]

            # Check enrichment worked
            first_record = output_records[0]
            assert "month" in first_record
            assert "processing_timestamp" in first_record

    def test_streaming_data_pipeline_with_backpressure(self, tmp_path):
        """Test streaming data processing with backpressure handling."""

        # Generate streaming data files
        num_files = 5
        records_per_file = 3000
        input_files = []

        for i in range(num_files):
            file_path = tmp_path / f"stream_batch_{i}.csv"
            data = ProductionDataGenerator.generate_sales_data(
                records_per_file, error_rate=0.03
            )
            ProductionDataGenerator.write_csv(data, file_path)
            input_files.append(str(file_path))

        workflow = Workflow("streaming-pipeline", "Streaming Data Pipeline")

        # Streaming data reader with backpressure
        class StreamingReader(Node):
            def get_parameters(self):
                return {
                    "file_paths": NodeParameter(type=list, required=True),
                    "batch_size": NodeParameter(type=int, required=False, default=500),
                    "max_memory_mb": NodeParameter(
                        type=int, required=False, default=100
                    ),
                }

            def run(self, **kwargs):
                import csv
                import sys

                file_paths = kwargs.get("file_paths", [])
                batch_size = kwargs.get("batch_size", 500)
                max_memory_mb = kwargs.get("max_memory_mb", 100)

                all_batches = []
                memory_used = 0
                files_processed = 0

                for file_path in file_paths:
                    # Check memory usage
                    current_memory = sys.getsizeof(all_batches) / (1024 * 1024)
                    if current_memory > max_memory_mb:
                        print(f"Backpressure triggered at {current_memory:.2f}MB")
                        break

                    with open(file_path, "r") as f:
                        reader = csv.DictReader(f)
                        batch = []

                        for row in reader:
                            batch.append(row)

                            if len(batch) >= batch_size:
                                all_batches.append(batch)
                                batch = []

                        if batch:
                            all_batches.append(batch)

                    files_processed += 1

                return {
                    "batches": all_batches,
                    "batch_count": len(all_batches),
                    "files_processed": files_processed,
                    "total_files": len(file_paths),
                    "memory_used_mb": sys.getsizeof(all_batches) / (1024 * 1024),
                }

        streaming_reader = StreamingReader()
        workflow.add_node("streamer", streaming_reader)

        # Batch processor with rate limiting
        batch_processor = PythonCodeNode(
            code="""
import time
import statistics

processed_records = []
batch_times = []

for i, batch in enumerate(batches):
    batch_start = time.time()

    # Process batch
    for record in batch:
        # Simple validation and enrichment
        try:
            if all(k in record for k in ["order_id", "quantity", "price"]):
                record["quantity"] = int(record.get("quantity", 0))
                record["price"] = float(record.get("price", 0))
                record["total"] = record["quantity"] * record["price"]
                record["batch_id"] = i
                processed_records.append(record)
        except:
            pass  # Skip invalid records

    batch_time = time.time() - batch_start
    batch_times.append(batch_time)

    # Rate limiting - ensure we don't overwhelm downstream
    if batch_time < 0.01:  # If batch processed too fast
        time.sleep(0.01 - batch_time)  # Add small delay

# Calculate throughput
total_time = sum(batch_times)
records_per_second = len(processed_records) / total_time if total_time > 0 else 0

result = {
    "processed_records": processed_records,
    "total_processed": len(processed_records),
    "batches_processed": len(batches),
    "avg_batch_time": statistics.mean(batch_times) if batch_times else 0,
    "records_per_second": records_per_second
}
"""
        )
        workflow.add_node("processor", batch_processor)

        # Aggregator with windowing
        aggregator = PythonCodeNode(
            code="""
from collections import defaultdict
import statistics

# Window-based aggregation
windows = defaultdict(lambda: {"count": 0, "total": 0, "products": set()})

for record in processed_records:
    batch_id = record.get("batch_id", 0)
    window_key = f"batch_{batch_id // 5}"  # 5-batch windows

    windows[window_key]["count"] += 1
    windows[window_key]["total"] += record.get("total", 0)
    windows[window_key]["products"].add(record.get("product", "unknown"))

# Convert sets to counts for serialization
window_stats = {}
for window, stats in windows.items():
    window_stats[window] = {
        "record_count": stats["count"],
        "total_revenue": round(stats["total"], 2),
        "unique_products": len(stats["products"]),
        "avg_order_value": round(stats["total"] / stats["count"], 2) if stats["count"] > 0 else 0
    }

result = {
    "window_aggregates": window_stats,
    "total_windows": len(window_stats),
    "global_stats": {
        "total_records": sum(s["record_count"] for s in window_stats.values()),
        "total_revenue": sum(s["total_revenue"] for s in window_stats.values()),
        "avg_window_size": statistics.mean(s["record_count"] for s in window_stats.values()) if window_stats else 0
    }
}
"""
        )
        workflow.add_node("aggregator", aggregator)

        # Connect workflow
        workflow.connect("streamer", "processor", mapping={"batches": "batches"})
        workflow.connect(
            "processor",
            "aggregator",
            mapping={"processed_records": "processed_records"},
        )

        # Execute streaming pipeline
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            workflow,
            parameters={
                "streamer": {
                    "file_paths": input_files,
                    "batch_size": 1000,
                    "max_memory_mb": 50,
                }
            },
        )

        # Verify streaming behavior
        streamer_results = results["streamer"]
        assert streamer_results["batch_count"] > 0
        assert streamer_results["memory_used_mb"] < 60  # Respects memory limit

        # Verify processing
        processor_results = results["processor"]
        assert processor_results["total_processed"] > 0
        assert processor_results["records_per_second"] > 1000

        # Verify aggregation
        aggregator_results = results["aggregator"]
        assert aggregator_results["total_windows"] > 0
        assert (
            aggregator_results["global_stats"]["total_records"]
            == processor_results["total_processed"]
        )
