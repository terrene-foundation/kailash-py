"""
Template: Comprehensive Data Validation
Purpose: Validate data quality with detailed reporting
Use Case: Data quality assurance, ETL pipelines, data governance

Customization Points:
- VALIDATION_RULES: Define your validation criteria
- Custom validation functions
- Error handling strategies
- Validation report format
"""

from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode, CSVWriterNode
from typing import Dict, Any, List, Set, Optional
import re
from datetime import datetime

# Configuration (customize these)
INPUT_FILE = "data/raw_data.csv"
VALID_OUTPUT = "outputs/validated_data.csv"
INVALID_OUTPUT = "outputs/validation_errors.json"
REPORT_OUTPUT = "outputs/validation_report.json"

# Validation rules
VALIDATION_RULES = {
    "required_fields": ["id", "email", "name", "date_created"],
    "field_types": {
        "id": int,
        "email": str,
        "name": str,
        "age": int,
        "salary": float,
        "date_created": str,  # Will validate date format
        "status": str,
    },
    "field_constraints": {
        "age": {"min": 18, "max": 100},
        "salary": {"min": 0, "max": 1000000},
        "status": {"allowed_values": ["active", "inactive", "pending"]},
    },
    "regex_patterns": {
        "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        "phone": r"^\+?1?\d{9,15}$",
        "postal_code": r"^\d{5}(-\d{4})?$",
    },
    "date_formats": {"date_created": "%Y-%m-%d", "last_login": "%Y-%m-%d %H:%M:%S"},
    "unique_fields": ["id", "email"],
    "custom_validations": {
        "email_domain": ["company.com", "example.com"],  # Allowed domains
        "name_length": {"min": 2, "max": 100},
    },
}


def validate_record(
    record: Dict, rules: Dict, seen_values: Dict[str, Set]
) -> Dict[str, Any]:
    """Validate a single record against rules"""
    errors = []
    warnings = []

    # Check required fields
    for field in rules["required_fields"]:
        if field not in record or record[field] is None or record[field] == "":
            errors.append(
                {
                    "field": field,
                    "error": "missing_required",
                    "message": f"Required field '{field}' is missing or empty",
                }
            )

    # Validate field types
    for field, expected_type in rules["field_types"].items():
        if field in record and record[field] is not None:
            try:
                if expected_type == int:
                    int(record[field])
                elif expected_type == float:
                    float(record[field])
                elif expected_type == str:
                    str(record[field])
            except (ValueError, TypeError):
                errors.append(
                    {
                        "field": field,
                        "error": "invalid_type",
                        "message": f"Field '{field}' should be {expected_type.__name__}",
                        "value": record[field],
                    }
                )

    # Check field constraints
    for field, constraints in rules["field_constraints"].items():
        if field in record and record[field] is not None:
            try:
                value = float(record[field]) if "min" in constraints else record[field]

                # Min/max checks
                if "min" in constraints and value < constraints["min"]:
                    errors.append(
                        {
                            "field": field,
                            "error": "below_minimum",
                            "message": f"Value {value} is below minimum {constraints['min']}",
                            "value": value,
                        }
                    )

                if "max" in constraints and value > constraints["max"]:
                    errors.append(
                        {
                            "field": field,
                            "error": "above_maximum",
                            "message": f"Value {value} is above maximum {constraints['max']}",
                            "value": value,
                        }
                    )

                # Allowed values check
                if "allowed_values" in constraints:
                    if record[field] not in constraints["allowed_values"]:
                        errors.append(
                            {
                                "field": field,
                                "error": "invalid_value",
                                "message": f"Value '{record[field]}' not in allowed values: {constraints['allowed_values']}",
                                "value": record[field],
                            }
                        )

            except (ValueError, TypeError):
                pass  # Type error already caught above

    # Regex pattern validation
    for field, pattern in rules["regex_patterns"].items():
        if field in record and record[field]:
            if not re.match(pattern, str(record[field])):
                errors.append(
                    {
                        "field": field,
                        "error": "invalid_format",
                        "message": f"Field '{field}' has invalid format",
                        "value": record[field],
                        "pattern": pattern,
                    }
                )

    # Date format validation
    for field, date_format in rules["date_formats"].items():
        if field in record and record[field]:
            try:
                datetime.strptime(str(record[field]), date_format)
            except ValueError:
                errors.append(
                    {
                        "field": field,
                        "error": "invalid_date",
                        "message": f"Invalid date format for '{field}', expected {date_format}",
                        "value": record[field],
                    }
                )

    # Uniqueness validation
    for field in rules["unique_fields"]:
        if field in record and record[field]:
            value = str(record[field])
            if field not in seen_values:
                seen_values[field] = set()

            if value in seen_values[field]:
                errors.append(
                    {
                        "field": field,
                        "error": "duplicate_value",
                        "message": f"Duplicate value '{value}' for unique field '{field}'",
                        "value": value,
                    }
                )
            else:
                seen_values[field].add(value)

    # Custom validations
    if "custom_validations" in rules:
        # Email domain validation
        if "email_domain" in rules["custom_validations"] and "email" in record:
            email = str(record.get("email", ""))
            if "@" in email:
                domain = email.split("@")[1]
                allowed_domains = rules["custom_validations"]["email_domain"]
                if domain not in allowed_domains:
                    warnings.append(
                        {
                            "field": "email",
                            "warning": "unexpected_domain",
                            "message": f"Email domain '{domain}' not in expected domains: {allowed_domains}",
                            "value": email,
                        }
                    )

        # Name length validation
        if "name_length" in rules["custom_validations"] and "name" in record:
            name = str(record.get("name", ""))
            length_rules = rules["custom_validations"]["name_length"]
            if len(name) < length_rules["min"]:
                errors.append(
                    {
                        "field": "name",
                        "error": "too_short",
                        "message": f"Name '{name}' is shorter than {length_rules['min']} characters",
                    }
                )
            elif len(name) > length_rules["max"]:
                warnings.append(
                    {
                        "field": "name",
                        "warning": "too_long",
                        "message": f"Name '{name}' is longer than {length_rules['max']} characters",
                    }
                )

    return {
        "record": record,
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_dataset(data: List[Dict], rules: Dict) -> Dict[str, Any]:
    """Validate entire dataset"""
    valid_records = []
    invalid_records = []
    all_errors = []
    all_warnings = []
    seen_values = {}

    # Validate each record
    for i, record in enumerate(data):
        # Add record index for tracking
        record_with_index = record.copy()
        record_with_index["_row_index"] = i + 1

        validation_result = validate_record(record_with_index, rules, seen_values)

        if validation_result["is_valid"]:
            valid_records.append(record)
        else:
            invalid_records.append(
                {
                    "row_index": i + 1,
                    "record": record,
                    "errors": validation_result["errors"],
                }
            )
            all_errors.extend(validation_result["errors"])

        if validation_result["warnings"]:
            all_warnings.extend(
                [
                    {**warning, "row_index": i + 1}
                    for warning in validation_result["warnings"]
                ]
            )

    # Calculate statistics
    total_records = len(data)
    valid_count = len(valid_records)
    invalid_count = len(invalid_records)

    # Error summary by type
    error_summary = {}
    for error in all_errors:
        error_type = error["error"]
        if error_type not in error_summary:
            error_summary[error_type] = 0
        error_summary[error_type] += 1

    # Field error summary
    field_error_summary = {}
    for error in all_errors:
        field = error["field"]
        if field not in field_error_summary:
            field_error_summary[field] = 0
        field_error_summary[field] += 1

    return {
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "validation_report": {
            "summary": {
                "total_records": total_records,
                "valid_records": valid_count,
                "invalid_records": invalid_count,
                "validation_rate": (
                    valid_count / total_records if total_records > 0 else 0
                ),
                "total_errors": len(all_errors),
                "total_warnings": len(all_warnings),
            },
            "error_summary": error_summary,
            "field_error_summary": field_error_summary,
            "warnings": all_warnings[:10],  # First 10 warnings
            "sample_errors": all_errors[:10],  # First 10 errors
        },
    }


def generate_validation_report(validation_result: Dict) -> Dict[str, Any]:
    """Generate detailed validation report"""
    report = validation_result["validation_report"]

    # Add timestamp and metadata
    report["metadata"] = {
        "validation_date": datetime.now().isoformat(),
        "rules_applied": list(VALIDATION_RULES.keys()),
        "version": "1.0",
    }

    # Add recommendations
    recommendations = []

    # Check for high error rates
    if report["summary"]["validation_rate"] < 0.8:
        recommendations.append(
            {
                "severity": "high",
                "message": "High error rate detected. Review data source quality.",
                "action": "Investigate data collection process",
            }
        )

    # Check for specific error patterns
    for error_type, count in report["error_summary"].items():
        if error_type == "missing_required" and count > 10:
            recommendations.append(
                {
                    "severity": "medium",
                    "message": f"Many missing required fields ({count} occurrences)",
                    "action": "Ensure data source provides all required fields",
                }
            )
        elif error_type == "invalid_format" and count > 5:
            recommendations.append(
                {
                    "severity": "medium",
                    "message": f"Format validation failures ({count} occurrences)",
                    "action": "Review and standardize data formats",
                }
            )

    report["recommendations"] = recommendations

    return report


def create_validation_workflow():
    """Create the data validation workflow"""
    workflow = Workflow()

    # 1. Read input data
    reader = CSVReaderNode(config={"file_path": INPUT_FILE})
    workflow.add_node("reader", reader)

    # 2. Validate data
    validator = PythonCodeNode.from_function(
        func=validate_dataset,
        name="data_validator",
        description="Comprehensive data validation",
    )
    workflow.add_node("validator", validator)

    # 3. Generate report
    report_generator = PythonCodeNode.from_function(
        func=generate_validation_report,
        name="report_generator",
        description="Generate validation report",
    )
    workflow.add_node("report_gen", report_generator)

    # 4. Write valid records
    valid_writer = CSVWriterNode(
        config={"file_path": VALID_OUTPUT, "include_headers": True}
    )
    workflow.add_node("valid_writer", valid_writer)

    # 5. Write invalid records and errors
    error_writer = JSONWriterNode(config={"file_path": INVALID_OUTPUT, "indent": 2})
    workflow.add_node("error_writer", error_writer)

    # 6. Write validation report
    report_writer = JSONWriterNode(config={"file_path": REPORT_OUTPUT, "indent": 2})
    workflow.add_node("report_writer", report_writer)

    # Connect workflow
    workflow.connect("reader", "validator", mapping={"data": "data"})
    workflow.connect(
        "validator", "report_gen", mapping={"validation_report": "validation_result"}
    )
    workflow.connect("validator", "valid_writer", mapping={"valid_records": "data"})
    workflow.connect("validator", "error_writer", mapping={"invalid_records": "data"})
    workflow.connect(
        "report_gen", "report_writer", mapping={"validation_report": "data"}
    )

    return workflow


def main():
    """Execute the validation workflow"""
    import os

    # Create output directory
    os.makedirs("outputs", exist_ok=True)

    # Create sample data if needed
    if not os.path.exists(INPUT_FILE):
        sample_data = """id,email,name,age,salary,date_created,status
1,john@company.com,John Doe,25,50000,2024-01-15,active
2,jane@example.com,Jane Smith,30,60000,2024-02-20,active
3,invalid-email,Bob Wilson,17,45000,2024-03-10,pending
4,alice@unknown.com,Alice,35,120000,invalid-date,active
5,john@company.com,John Duplicate,40,55000,2024-04-05,inactive
,missing@example.com,Missing ID,28,52000,2024-05-01,active
7,charlie@company.com,,45,48000,2024-06-15,active"""

        os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
        with open(INPUT_FILE, "w") as f:
            f.write(sample_data)
        print(f"Created sample data in {INPUT_FILE}")

    # Create and execute workflow
    workflow = create_validation_workflow()
    workflow.validate()

    runtime = LocalRuntime()
    try:
        results = runtime.execute(
            workflow, parameters={"validator": {"rules": VALIDATION_RULES}}
        )

        print("Data validation completed!")
        print(f"Valid records: {VALID_OUTPUT}")
        print(f"Invalid records: {INVALID_OUTPUT}")
        print(f"Validation report: {REPORT_OUTPUT}")

        # Print summary
        if "report_gen" in results:
            report = results["report_gen"]["validation_report"]
            summary = report["summary"]

            print(f"\nValidation Summary:")
            print(f"- Total records: {summary['total_records']}")
            print(
                f"- Valid records: {summary['valid_records']} ({summary['validation_rate']:.1%})"
            )
            print(f"- Invalid records: {summary['invalid_records']}")
            print(f"- Total errors: {summary['total_errors']}")
            print(f"- Total warnings: {summary['total_warnings']}")

            if report.get("recommendations"):
                print("\nRecommendations:")
                for rec in report["recommendations"]:
                    print(f"- [{rec['severity'].upper()}] {rec['message']}")

        return 0

    except Exception as e:
        print(f"Error executing workflow: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
