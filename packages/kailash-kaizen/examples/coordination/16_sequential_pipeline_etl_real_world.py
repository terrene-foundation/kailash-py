"""
Example 16: Sequential Pipeline Pattern - Real-World ETL Pipeline

This example demonstrates a real-world use case: ETL (Extract, Transform, Load) pipeline
for customer data processing using the SequentialPipelinePattern.

Use Case:
A data engineering team needs to process customer transaction data through multiple
stages of extraction, transformation, validation, enrichment, and loading.

Learning Objectives:
- Real-world ETL pipeline implementation
- Multi-stage data processing
- Data quality validation
- Error handling and logging
- Result tracking and reporting

Estimated time: 15 minutes
"""

import json
from datetime import datetime
from typing import Any, Dict, List

from kaizen.agents.coordination import create_sequential_pipeline
from kaizen.agents.coordination.sequential_pipeline import PipelineStageAgent
from kaizen.core.base_agent import BaseAgentConfig

# Sample customer transaction data
CUSTOMER_TRANSACTIONS = [
    {
        "id": 1,
        "raw_data": "John Doe, john@example.com, 2024-01-15, purchased laptop for $1200, shipping to 123 Main St",
    },
    {
        "id": 2,
        "raw_data": "Jane Smith, jane.smith@company.com, 2024-01-16, bought 3 books totaling $85.50, express delivery",
    },
    {
        "id": 3,
        "raw_data": "Bob Johnson, bob.j@email.com, 2024-01-17, ordered headphones $250 and mouse $45, standard shipping",
    },
    {
        "id": 4,
        "raw_data": "Alice Williams, alice@domain.com, 2024-01-18, purchased tablet $650, gift wrapping requested",
    },
    {
        "id": 5,
        "raw_data": "Charlie Brown, charlie.b@mail.com, 2024-01-19, bought keyboard $120 and monitor $400, rush delivery",
    },
]


def format_etl_report(
    transaction: Dict[str, Any],
    result: Dict[str, Any],
    stage_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Format ETL pipeline report."""

    return {
        "timestamp": datetime.now().isoformat(),
        "transaction_id": transaction["id"],
        "pipeline_id": result["pipeline_id"],
        "status": result["status"],
        "stages_executed": result["stage_count"],
        "pipeline_stages": {
            "extract": next(
                (s for s in stage_results if s["stage_name"] == "extract"), None
            ),
            "validate": next(
                (s for s in stage_results if s["stage_name"] == "validate"), None
            ),
            "transform": next(
                (s for s in stage_results if s["stage_name"] == "transform"), None
            ),
            "enrich": next(
                (s for s in stage_results if s["stage_name"] == "enrich"), None
            ),
            "load": next((s for s in stage_results if s["stage_name"] == "load"), None),
        },
        "final_output": (
            result["final_output"][:500] + "..."
            if len(result["final_output"]) > 500
            else result["final_output"]
        ),
        "processing_status": (
            "completed" if result["status"] == "completed" else "partial"
        ),
    }


def main():
    print("=" * 70)
    print("Real-World ETL Pipeline - Customer Transaction Processing")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Configure ETL Pipeline
    # ==================================================================
    print("Step 1: Configuring ETL pipeline...")
    print("-" * 70)

    print("Pipeline Configuration:")
    print("  - Extract: Parse raw transaction data")
    print("  - Validate: Ensure data quality and completeness")
    print("  - Transform: Standardize formats and structure")
    print("  - Enrich: Add calculated fields and metadata")
    print("  - Load: Prepare for database insertion")
    print()

    # ==================================================================
    # STEP 2: Create ETL Pipeline Pattern
    # ==================================================================
    print("Step 2: Creating ETL pipeline pattern...")
    print("-" * 70)

    # Optimize stage configs for ETL workload
    etl_configs = [
        # Extract: Fast model, low temp (deterministic extraction)
        {"model": "gpt-3.5-turbo", "temperature": 0.3, "max_tokens": 1000},
        # Validate: Fast model, very low temp (strict validation)
        {"model": "gpt-3.5-turbo", "temperature": 0.1, "max_tokens": 800},
        # Transform: Powerful model, moderate temp (complex transformation)
        {"model": "gpt-4", "temperature": 0.5, "max_tokens": 1500},
        # Enrich: Fast model, low temp (deterministic enrichment)
        {"model": "gpt-3.5-turbo", "temperature": 0.3, "max_tokens": 1000},
        # Load: Fast model, very low temp (format for DB)
        {"model": "gpt-3.5-turbo", "temperature": 0.1, "max_tokens": 800},
    ]

    etl_pipeline = create_sequential_pipeline(stage_configs=etl_configs)

    # Add ETL stages
    etl_pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "extract"))
    etl_pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "validate"))
    etl_pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "transform"))
    etl_pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "enrich"))
    etl_pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "load"))

    print("✓ ETL pipeline created successfully!")
    print(f"  - Total stages: {len(etl_pipeline.stages)}")
    print(f"  - Stage IDs: {etl_pipeline.get_agent_ids()}")
    print()

    # ==================================================================
    # STEP 3: Process Customer Transactions
    # ==================================================================
    print("Step 3: Processing customer transactions...")
    print("-" * 70)
    print()

    etl_reports = []

    for idx, transaction in enumerate(CUSTOMER_TRANSACTIONS, 1):
        print(f"{'='*70}")
        print(f"TRANSACTION {idx}/{len(CUSTOMER_TRANSACTIONS)}: ID {transaction['id']}")
        print(f"{'='*70}")
        print()

        print("Raw Data:")
        print(f"  {transaction['raw_data']}")
        print()

        # Run ETL pipeline
        print("ETL Pipeline Processing...")
        print("-" * 70)

        result = etl_pipeline.execute_pipeline(
            initial_input=transaction["raw_data"],
            context="""
            ETL Context:
            - Extract: Parse customer name, email, date, items, price, shipping
            - Validate: Ensure all fields present, email valid, price numeric
            - Transform: Standardize date format (YYYY-MM-DD), normalize price ($X.XX)
            - Enrich: Calculate tax (8%), total with tax, categorize shipping
            - Load: Format as JSON for database insertion
            """,
        )

        print(f"✓ Pipeline completed for transaction {transaction['id']}")
        print()

        # Get stage results
        stage_results = etl_pipeline.get_stage_results(result["pipeline_id"])

        # Display stage-by-stage progress
        print("ETL Stages:")
        for stage in stage_results:
            status_icon = "✓" if stage["stage_status"] == "success" else "⚠️"
            print(
                f"  {status_icon} {stage['stage_name'].capitalize()}: {stage['stage_status']}"
            )

        print()

        # Display final output preview
        print("Final Output (Database-Ready):")
        print(f"  {result['final_output'][:150]}...")
        print()

        # Generate report
        report = format_etl_report(transaction, result, stage_results)
        etl_reports.append(report)

        # Clear memory for next transaction
        etl_pipeline.clear_shared_memory()

        print()

    # ==================================================================
    # STEP 4: ETL Session Summary
    # ==================================================================
    print("=" * 70)
    print("ETL SESSION SUMMARY")
    print("=" * 70)
    print()

    print(f"Session Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Transactions Processed: {len(etl_reports)}")
    print()

    # Summary table
    print("Processing Results:")
    print("-" * 70)
    print(f"{'Transaction ID':<18} {'Pipeline ID':<15} {'Stages':<10} {'Status':<12}")
    print("-" * 70)

    for report in etl_reports:
        print(
            f"{report['transaction_id']:<18} {report['pipeline_id']:<15} {report['stages_executed']:<10} {report['status']:<12}"
        )

    print()

    # Success metrics
    successful = sum(1 for r in etl_reports if r["status"] == "completed")
    partial = sum(1 for r in etl_reports if r["status"] == "partial")

    print("ETL Success Metrics:")
    print(
        f"  - Successful: {successful}/{len(etl_reports)} ({successful/len(etl_reports)*100:.1f}%)"
    )
    print(f"  - Partial: {partial}/{len(etl_reports)}")
    print(
        f"  - Average stages per transaction: {sum(r['stages_executed'] for r in etl_reports) / len(etl_reports):.1f}"
    )
    print()

    # Stage performance
    print("Stage Performance:")
    all_stages = ["extract", "validate", "transform", "enrich", "load"]
    for stage_name in all_stages:
        stage_count = sum(
            1 for r in etl_reports if r["pipeline_stages"].get(stage_name)
        )
        success_count = sum(
            1
            for r in etl_reports
            if r["pipeline_stages"].get(stage_name)
            and r["pipeline_stages"][stage_name]["stage_status"] == "success"
        )
        print(
            f"  - {stage_name.capitalize()}: {success_count}/{stage_count} successful"
        )

    print()

    # ==================================================================
    # STEP 5: Export ETL Reports
    # ==================================================================
    print("Step 5: Exporting ETL reports...")
    print("-" * 70)

    # In real scenario, would save to database or file system
    print(f"✓ {len(etl_reports)} ETL reports generated")
    print()

    # Show sample report (first transaction)
    print("Sample ETL Report (JSON format):")
    print("-" * 70)
    sample_report = etl_reports[0]
    print(json.dumps(sample_report, indent=2)[:800] + "...")
    print()

    # ==================================================================
    # STEP 6: Data Quality Insights
    # ==================================================================
    print("Step 6: Data quality insights...")
    print("-" * 70)

    print("Data Quality Analysis:")

    # Check validation stage
    validation_issues = []
    for report in etl_reports:
        validate_stage = report["pipeline_stages"].get("validate")
        if validate_stage and validate_stage["stage_status"] != "success":
            validation_issues.append(
                {
                    "transaction_id": report["transaction_id"],
                    "issue": validate_stage["stage_output"][:100],
                }
            )

    if validation_issues:
        print(f"  ⚠️  Validation issues found: {len(validation_issues)}")
        for issue in validation_issues:
            print(f"     - Transaction {issue['transaction_id']}: {issue['issue']}")
    else:
        print("  ✓ No validation issues detected")

    print()

    # Check transformation completeness
    transform_successful = sum(
        1
        for r in etl_reports
        if r["pipeline_stages"].get("transform")
        and r["pipeline_stages"]["transform"]["stage_status"] == "success"
    )

    print(
        f"Transformation Success Rate: {transform_successful}/{len(etl_reports)} ({transform_successful/len(etl_reports)*100:.1f}%)"
    )
    print()

    # ==================================================================
    # STEP 7: Recommendations
    # ==================================================================
    print("Step 7: ETL pipeline recommendations...")
    print("-" * 70)

    print("Performance Recommendations:")
    if successful == len(etl_reports):
        print("  ✓ Pipeline running optimally - all transactions successful")
    else:
        print(f"  → {partial} partial failures - review validation rules")

    print()

    print("Optimization Opportunities:")
    print("  → Extract stage: Consider caching common patterns")
    print("  → Transform stage: Batch similar transformations")
    print("  → Load stage: Implement bulk insert capability")
    print()

    # ==================================================================
    # Summary and Next Steps
    # ==================================================================
    print("=" * 70)
    print("ETL Pipeline Session Complete!")
    print("=" * 70)
    print()

    print("What you learned:")
    print("  ✓ How to build production ETL pipelines")
    print("  ✓ How to configure stages for optimal performance")
    print("  ✓ How to process multiple transactions sequentially")
    print("  ✓ How to track and report on ETL operations")
    print("  ✓ How to analyze data quality across stages")
    print("  ✓ How to generate insights from pipeline execution")
    print()

    print("Production Considerations:")
    print("  → Store stage results in database for audit trail")
    print("  → Implement retry logic for failed stages")
    print("  → Add monitoring and alerting for failures")
    print("  → Batch process transactions for efficiency")
    print("  → Implement data lineage tracking")
    print("  → Add performance metrics collection")
    print("  → Create data quality dashboards")
    print()

    print("ETL Best Practices:")
    print("  → Use deterministic models for extraction (low temp)")
    print("  → Strict validation before transformation")
    print("  → Log all stage outputs for debugging")
    print("  → Handle partial failures gracefully")
    print("  → Enrich data with business context")
    print("  → Format output for target system")
    print()

    print("Use Cases for Sequential Pipeline:")
    print("  → ETL data processing (extract, transform, load)")
    print("  → Content generation pipelines (research, draft, edit, publish)")
    print("  → Multi-stage analysis workflows")
    print("  → Document processing pipelines")
    print("  → Data quality workflows")
    print("  → Customer onboarding flows")
    print()


if __name__ == "__main__":
    main()
