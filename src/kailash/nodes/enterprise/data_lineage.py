"""Data lineage tracking node for audit trails and compliance reporting.

This module provides comprehensive data lineage tracking capabilities that record
data transformations, track data flow through workflows, and generate compliance
reports for regulatory requirements.

Key Features:
- Automatic data transformation tracking
- Data source and destination recording
- Compliance report generation
- Data flow visualization
- Audit trail maintenance
- Data quality metrics tracking
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


@register_node()
class DataLineageNode(Node):
    """Node for tracking data lineage and generating audit trails.

    This node automatically tracks data transformations, maintains audit trails,
    and generates compliance reports for regulatory requirements. It provides
    comprehensive data lineage tracking for enterprise workflows.

    Key capabilities:
    1. Data transformation tracking
    2. Source and destination recording
    3. Compliance report generation
    4. Data quality metrics
    5. Audit trail maintenance
    6. Data flow visualization

    Example:
        >>> lineage = DataLineageNode()
        >>> result = lineage.execute(
        ...     operation="track_transformation",
        ...     data_source="customer_db",
        ...     transformation_type="anonymization",
        ...     output_destination="analytics_db",
        ...     compliance_tags=["GDPR", "CCPA"],
        ...     data_classifications=["PII", "financial"]
        ... )
    """

    def get_metadata(self) -> NodeMetadata:
        """Get node metadata for discovery and orchestration."""
        return NodeMetadata(
            name="Data Lineage Node",
            description="Track data lineage and generate audit trails for compliance",
            tags={"enterprise", "compliance", "audit", "lineage", "governance"},
            version="1.0.0",
            author="Kailash SDK",
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for data lineage operations."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="track_transformation",
                description="Operation: track_transformation, generate_report, query_lineage, compliance_check",
            ),
            "data_source": NodeParameter(
                name="data_source",
                type=str,
                required=False,
                description="Source of the data being processed",
            ),
            "output_destination": NodeParameter(
                name="output_destination",
                type=str,
                required=False,
                description="Destination where processed data is stored",
            ),
            "transformation_type": NodeParameter(
                name="transformation_type",
                type=str,
                required=False,
                description="Type of transformation applied (anonymization, aggregation, filtering, etc.)",
            ),
            "transformation_details": NodeParameter(
                name="transformation_details",
                type=dict,
                required=False,
                description="Detailed transformation metadata",
            ),
            "compliance_tags": NodeParameter(
                name="compliance_tags",
                type=list,
                required=False,
                default=[],
                description="Compliance framework tags (GDPR, CCPA, SOX, etc.)",
            ),
            "data_classifications": NodeParameter(
                name="data_classifications",
                type=list,
                required=False,
                default=[],
                description="Data classification tags (PII, PHI, financial, etc.)",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User ID performing the operation",
            ),
            "workflow_id": NodeParameter(
                name="workflow_id",
                type=str,
                required=False,
                description="Workflow ID for this operation",
            ),
            "start_date": NodeParameter(
                name="start_date",
                type=str,
                required=False,
                description="Start date for lineage queries (ISO format)",
            ),
            "end_date": NodeParameter(
                name="end_date",
                type=str,
                required=False,
                description="End date for lineage queries (ISO format)",
            ),
            "report_format": NodeParameter(
                name="report_format",
                type=str,
                required=False,
                default="json",
                description="Report format: json, csv, html",
            ),
            "storage_backend": NodeParameter(
                name="storage_backend",
                type=str,
                required=False,
                default="memory",
                description="Storage backend: memory, file, database",
            ),
            "storage_config": NodeParameter(
                name="storage_config",
                type=dict,
                required=False,
                default={},
                description="Storage backend configuration",
            ),
        }

    def __init__(self, **kwargs):
        """Initialize the DataLineageNode."""
        super().__init__(**kwargs)
        self._lineage_storage = {}
        self._compliance_rules = {
            "GDPR": {
                "required_classifications": ["PII"],
                "retention_days": 2555,  # 7 years
                "anonymization_required": True,
            },
            "CCPA": {
                "required_classifications": ["PII"],
                "retention_days": 1095,  # 3 years
                "deletion_rights": True,
            },
            "SOX": {
                "required_classifications": ["financial"],
                "retention_days": 2555,  # 7 years
                "audit_trail_required": True,
            },
            "HIPAA": {
                "required_classifications": ["PHI"],
                "retention_days": 2190,  # 6 years
                "encryption_required": True,
            },
        }

    def _generate_lineage_id(self) -> str:
        """Generate unique lineage tracking ID."""
        return f"lineage_{uuid.uuid4().hex[:12]}"

    def _track_transformation(
        self,
        data_source: str,
        output_destination: str,
        transformation_type: str,
        transformation_details: Optional[Dict] = None,
        compliance_tags: Optional[List[str]] = None,
        data_classifications: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Track a data transformation operation."""
        lineage_id = self._generate_lineage_id()
        timestamp = datetime.now().isoformat()

        # Create lineage record
        lineage_record = {
            "lineage_id": lineage_id,
            "timestamp": timestamp,
            "data_source": data_source,
            "output_destination": output_destination,
            "transformation_type": transformation_type,
            "transformation_details": transformation_details or {},
            "compliance_tags": compliance_tags or [],
            "data_classifications": data_classifications or [],
            "user_id": user_id,
            "workflow_id": workflow_id,
            "data_flow": {
                "input": {
                    "source": data_source,
                    "timestamp": timestamp,
                    "classifications": data_classifications or [],
                },
                "processing": {
                    "transformation": transformation_type,
                    "details": transformation_details or {},
                    "user": user_id,
                    "workflow": workflow_id,
                },
                "output": {
                    "destination": output_destination,
                    "timestamp": timestamp,
                    "compliance_tags": compliance_tags or [],
                },
            },
        }

        # Perform compliance checks
        compliance_results = self._check_compliance(lineage_record)
        lineage_record["compliance_check"] = compliance_results

        # Store lineage record
        self._lineage_storage[lineage_id] = lineage_record

        return {
            "lineage_id": lineage_id,
            "status": "tracked",
            "compliance_status": compliance_results["overall_status"],
            "compliance_warnings": compliance_results["warnings"],
            "audit_trail_created": True,
            "record": lineage_record,
        }

    def _check_compliance(self, lineage_record: Dict[str, Any]) -> Dict[str, Any]:
        """Check compliance requirements for a lineage record."""
        compliance_tags = lineage_record.get("compliance_tags", [])
        data_classifications = lineage_record.get("data_classifications", [])

        compliance_results = {
            "overall_status": "compliant",
            "warnings": [],
            "requirements_met": [],
            "requirements_failed": [],
        }

        for tag in compliance_tags:
            if tag in self._compliance_rules:
                rule = self._compliance_rules[tag]

                # Check required classifications
                required_classifications = rule.get("required_classifications", [])
                if required_classifications:
                    missing_classifications = set(required_classifications) - set(
                        data_classifications
                    )
                    if missing_classifications:
                        compliance_results["requirements_failed"].append(
                            f"{tag}: Missing required classifications: {list(missing_classifications)}"
                        )
                        compliance_results["overall_status"] = "non_compliant"
                    else:
                        compliance_results["requirements_met"].append(
                            f"{tag}: Required classifications present"
                        )

                # Check transformation requirements
                transformation_type = lineage_record.get("transformation_type", "")
                if (
                    rule.get("anonymization_required")
                    and "anonymization" not in transformation_type.lower()
                ):
                    compliance_results["warnings"].append(
                        f"{tag}: Anonymization may be required for this data"
                    )

                if rule.get("encryption_required"):
                    compliance_results["warnings"].append(
                        f"{tag}: Ensure data encryption is applied"
                    )

                if rule.get("audit_trail_required"):
                    compliance_results["requirements_met"].append(
                        f"{tag}: Audit trail automatically maintained"
                    )

        return compliance_results

    def _generate_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        report_format: str = "json",
        compliance_tags: Optional[List[str]] = None,
        data_classifications: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate a compliance and lineage report."""
        # Parse date filters
        start_dt = (
            datetime.fromisoformat(start_date)
            if start_date
            else datetime.now() - timedelta(days=30)
        )
        end_dt = datetime.fromisoformat(end_date) if end_date else datetime.now()

        # Filter lineage records
        filtered_records = []
        for record in self._lineage_storage.values():
            record_time = datetime.fromisoformat(record["timestamp"])
            if start_dt <= record_time <= end_dt:
                # Apply tag and classification filters
                if compliance_tags:
                    if not any(
                        tag in record.get("compliance_tags", [])
                        for tag in compliance_tags
                    ):
                        continue

                if data_classifications:
                    if not any(
                        cls in record.get("data_classifications", [])
                        for cls in data_classifications
                    ):
                        continue

                filtered_records.append(record)

        # Generate summary statistics
        summary = {
            "total_operations": len(filtered_records),
            "date_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "compliance_summary": {},
            "transformation_types": {},
            "data_sources": {},
            "destinations": {},
            "compliance_violations": 0,
        }

        # Analyze records
        for record in filtered_records:
            # Count transformation types
            transform_type = record.get("transformation_type", "unknown")
            summary["transformation_types"][transform_type] = (
                summary["transformation_types"].get(transform_type, 0) + 1
            )

            # Count data sources
            source = record.get("data_source", "unknown")
            summary["data_sources"][source] = summary["data_sources"].get(source, 0) + 1

            # Count destinations
            dest = record.get("output_destination", "unknown")
            summary["destinations"][dest] = summary["destinations"].get(dest, 0) + 1

            # Analyze compliance
            compliance_check = record.get("compliance_check", {})
            if compliance_check.get("overall_status") == "non_compliant":
                summary["compliance_violations"] += 1

            for tag in record.get("compliance_tags", []):
                if tag not in summary["compliance_summary"]:
                    summary["compliance_summary"][tag] = {
                        "total_operations": 0,
                        "compliant": 0,
                        "non_compliant": 0,
                    }
                summary["compliance_summary"][tag]["total_operations"] += 1
                if compliance_check.get("overall_status") == "compliant":
                    summary["compliance_summary"][tag]["compliant"] += 1
                else:
                    summary["compliance_summary"][tag]["non_compliant"] += 1

        report = {
            "report_id": f"report_{uuid.uuid4().hex[:12]}",
            "generated_at": datetime.now().isoformat(),
            "report_format": report_format,
            "summary": summary,
            "detailed_records": (
                filtered_records if report_format == "json" else len(filtered_records)
            ),
        }

        return report

    def _query_lineage(
        self,
        data_source: Optional[str] = None,
        output_destination: Optional[str] = None,
        workflow_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query lineage records based on criteria."""
        matching_records = []

        for record in self._lineage_storage.values():
            matches = True

            if data_source and record.get("data_source") != data_source:
                matches = False
            if (
                output_destination
                and record.get("output_destination") != output_destination
            ):
                matches = False
            if workflow_id and record.get("workflow_id") != workflow_id:
                matches = False
            if user_id and record.get("user_id") != user_id:
                matches = False

            if matches:
                matching_records.append(record)

        return {
            "query_results": matching_records,
            "total_matches": len(matching_records),
            "query_timestamp": datetime.now().isoformat(),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute data lineage operation."""
        operation = kwargs.get("operation", "track_transformation")

        if operation == "track_transformation":
            data_source = kwargs.get("data_source")
            output_destination = kwargs.get("output_destination")

            if not data_source or not output_destination:
                raise NodeConfigurationError(
                    "data_source and output_destination are required for track_transformation"
                )

            return self._track_transformation(
                data_source=data_source,
                output_destination=output_destination,
                transformation_type=kwargs.get("transformation_type", "unknown"),
                transformation_details=kwargs.get("transformation_details"),
                compliance_tags=kwargs.get("compliance_tags"),
                data_classifications=kwargs.get("data_classifications"),
                user_id=kwargs.get("user_id"),
                workflow_id=kwargs.get("workflow_id"),
            )

        elif operation == "generate_report":
            return self._generate_report(
                start_date=kwargs.get("start_date"),
                end_date=kwargs.get("end_date"),
                report_format=kwargs.get("report_format", "json"),
                compliance_tags=kwargs.get("compliance_tags"),
                data_classifications=kwargs.get("data_classifications"),
            )

        elif operation == "query_lineage":
            return self._query_lineage(
                data_source=kwargs.get("data_source"),
                output_destination=kwargs.get("output_destination"),
                workflow_id=kwargs.get("workflow_id"),
                user_id=kwargs.get("user_id"),
            )

        elif operation == "compliance_check":
            # Perform standalone compliance check
            mock_record = {
                "compliance_tags": kwargs.get("compliance_tags", []),
                "data_classifications": kwargs.get("data_classifications", []),
                "transformation_type": kwargs.get("transformation_type", ""),
            }
            return {
                "compliance_check": self._check_compliance(mock_record),
                "timestamp": datetime.now().isoformat(),
            }

        else:
            raise NodeConfigurationError(f"Invalid operation: {operation}")

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
