# Migration Guide

Comprehensive guide for migrating to Nexus's workflow-native platform from existing systems, frameworks, and legacy architectures.

## Overview

This guide covers migration strategies, automated tools, compatibility layers, and best practices for transitioning from various platforms to Nexus. Whether migrating from traditional APIs, microservices, or other workflow systems, this guide provides step-by-step approaches for seamless transitions.

## Migration from Traditional APIs

### REST API Migration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import json
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
import ast
import re

class APIToNexusMigrator:
    """Migrate REST APIs to Nexus workflows"""

    def __init__(self, source_framework: str = "flask"):
        self.source_framework = source_framework
        self.migration_config = {
            "preserve_endpoints": True,
            "auto_generate_workflows": True,
            "enable_backwards_compatibility": True,
            "migration_mode": "gradual",  # gradual, immediate, parallel
            "validation_level": "strict"
        }
        self.migration_log = []
        self.endpoint_mappings = {}

    def analyze_existing_api(self, api_definition_file: str) -> Dict[str, Any]:
        """Analyze existing API for migration planning"""

        analysis_result = {
            "endpoints": [],
            "data_models": [],
            "authentication": {},
            "middleware": [],
            "dependencies": [],
            "complexity_score": 0,
            "migration_recommendations": []
        }

        if api_definition_file.endswith('.json'):
            # OpenAPI/Swagger analysis
            analysis_result = self._analyze_openapi_spec(api_definition_file)
        elif api_definition_file.endswith('.py'):
            # Python code analysis
            analysis_result = self._analyze_python_api(api_definition_file)

        # Calculate complexity score
        analysis_result["complexity_score"] = self._calculate_complexity_score(analysis_result)

        # Generate recommendations
        analysis_result["migration_recommendations"] = self._generate_migration_recommendations(analysis_result)

        return analysis_result

    def _analyze_openapi_spec(self, spec_file: str) -> Dict[str, Any]:
        """Analyze OpenAPI specification"""

        with open(spec_file, 'r') as f:
            spec = json.load(f)

        analysis = {
            "endpoints": [],
            "data_models": [],
            "authentication": {},
            "middleware": [],
            "dependencies": []
        }

        # Extract endpoints
        for path, path_item in spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    endpoint = {
                        "path": path,
                        "method": method.upper(),
                        "operation_id": operation.get("operationId"),
                        "summary": operation.get("summary"),
                        "parameters": operation.get("parameters", []),
                        "request_body": operation.get("requestBody"),
                        "responses": operation.get("responses", {}),
                        "tags": operation.get("tags", [])
                    }
                    analysis["endpoints"].append(endpoint)

        # Extract data models
        components = spec.get("components", {})
        schemas = components.get("schemas", {})
        for model_name, model_schema in schemas.items():
            model = {
                "name": model_name,
                "type": model_schema.get("type", "object"),
                "properties": model_schema.get("properties", {}),
                "required": model_schema.get("required", [])
            }
            analysis["data_models"].append(model)

        # Extract authentication
        security_schemes = components.get("securitySchemes", {})
        for scheme_name, scheme_config in security_schemes.items():
            analysis["authentication"][scheme_name] = {
                "type": scheme_config.get("type"),
                "scheme": scheme_config.get("scheme"),
                "flows": scheme_config.get("flows", {})
            }

        return analysis

    def _analyze_python_api(self, source_file: str) -> Dict[str, Any]:
        """Analyze Python API source code"""

        with open(source_file, 'r') as f:
            source_code = f.read()

        analysis = {
            "endpoints": [],
            "data_models": [],
            "authentication": {},
            "middleware": [],
            "dependencies": []
        }

        # Parse AST
        tree = ast.parse(source_code)

        # Extract endpoints (simplified for Flask/FastAPI)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Look for route decorators
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if hasattr(decorator.func, 'attr') and decorator.func.attr in ['route', 'get', 'post', 'put', 'delete']:
                            endpoint = self._extract_endpoint_from_decorator(node, decorator)
                            if endpoint:
                                analysis["endpoints"].append(endpoint)

        # Extract imports for dependencies
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    analysis["dependencies"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    analysis["dependencies"].append(node.module)

        return analysis

    def _extract_endpoint_from_decorator(self, func_node: ast.FunctionDef, decorator: ast.Call) -> Optional[Dict[str, Any]]:
        """Extract endpoint information from decorator"""

        endpoint = {
            "function_name": func_node.name,
            "path": None,
            "method": "GET",
            "parameters": [],
            "docstring": ast.get_docstring(func_node)
        }

        # Extract path from decorator arguments
        if decorator.args:
            if isinstance(decorator.args[0], ast.Str):
                endpoint["path"] = decorator.args[0].s
            elif isinstance(decorator.args[0], ast.Constant):
                endpoint["path"] = decorator.args[0].value

        # Extract method from decorator name or keywords
        if hasattr(decorator.func, 'attr'):
            method_name = decorator.func.attr.upper()
            if method_name in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                endpoint["method"] = method_name

        return endpoint if endpoint["path"] else None

    def generate_nexus_workflow(self, endpoint: Dict[str, Any]) -> WorkflowBuilder:
        """Generate Nexus workflow from API endpoint"""

        workflow = WorkflowBuilder()
        workflow_name = f"{endpoint['method'].lower()}_{endpoint.get('function_name', 'endpoint')}"

        # Add input validation node
        workflow.add_node("ValidationNode", "input_validation", {
            "schema": self._generate_validation_schema(endpoint),
            "strict_mode": self.migration_config["validation_level"] == "strict"
        })

        # Add business logic node
        if endpoint.get("docstring"):
            # Use docstring to understand business logic
            business_logic = self._extract_business_logic(endpoint["docstring"])
        else:
            business_logic = {"operation": "process_request"}

        workflow.add_node("PythonCodeNode", "business_logic", {
            "code": self._generate_business_logic_code(endpoint, business_logic)
        })

        # Add response formatting node
        workflow.add_node("ResponseFormatterNode", "format_response", {
            "format": "json",
            "status_codes": self._extract_status_codes(endpoint)
        })

        # Connect nodes
        workflow.add_connection("input_validation", "business_logic", "output", "input")
        workflow.add_connection("business_logic", "format_response", "output", "input")

        # Store mapping
        self.endpoint_mappings[f"{endpoint['method']} {endpoint['path']}"] = workflow_name

        return workflow

    def _generate_validation_schema(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """Generate validation schema for endpoint"""

        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        # Add path parameters
        path = endpoint.get("path", "")
        path_params = re.findall(r'<([^>]+)>', path)
        for param in path_params:
            schema["properties"][param] = {"type": "string"}
            schema["required"].append(param)

        # Add query parameters from OpenAPI spec
        for param in endpoint.get("parameters", []):
            if param.get("in") == "query":
                param_schema = {
                    "type": param.get("schema", {}).get("type", "string"),
                    "description": param.get("description", "")
                }
                schema["properties"][param["name"]] = param_schema

                if param.get("required", False):
                    schema["required"].append(param["name"])

        return schema

    def _extract_business_logic(self, docstring: str) -> Dict[str, Any]:
        """Extract business logic hints from docstring"""

        logic = {"operation": "process_request", "description": docstring}

        # Simple keyword extraction
        if "create" in docstring.lower():
            logic["operation"] = "create"
        elif "update" in docstring.lower():
            logic["operation"] = "update"
        elif "delete" in docstring.lower():
            logic["operation"] = "delete"
        elif "get" in docstring.lower() or "fetch" in docstring.lower():
            logic["operation"] = "read"

        return logic

    def _generate_business_logic_code(self, endpoint: Dict[str, Any], logic: Dict[str, Any]) -> str:
        """Generate Python code for business logic"""

        function_name = f"process_{endpoint.get('function_name', 'request')}"

        code_template = f'''
def {function_name}(data):
    """
    Generated business logic for {endpoint.get('path', 'unknown')}
    Operation: {logic.get('operation', 'process_request')}
    """

    # Extract input data
    input_data = data.get('input', {{}})

    # Business logic implementation
    result = {{
        "operation": "{logic.get('operation', 'process_request')}",
        "endpoint": "{endpoint.get('path', 'unknown')}",
        "method": "{endpoint.get('method', 'GET')}",
        "processed_data": input_data,
        "timestamp": __import__('time').time(),
        "success": True
    }}

    # Add operation-specific logic
    if "{logic.get('operation')}" == "create":
        result["resource_id"] = "generated_id_" + str(__import__('random').randint(1000, 9999))
        result["status"] = "created"
    elif "{logic.get('operation')}" == "read":
        result["data"] = input_data
        result["status"] = "retrieved"
    elif "{logic.get('operation')}" == "update":
        result["updated_fields"] = list(input_data.keys())
        result["status"] = "updated"
    elif "{logic.get('operation')}" == "delete":
        result["status"] = "deleted"

    return result
'''

        return code_template.strip()

    def _extract_status_codes(self, endpoint: Dict[str, Any]) -> Dict[int, str]:
        """Extract status codes from endpoint definition"""

        status_codes = {200: "OK"}

        responses = endpoint.get("responses", {})
        for status_code, response_def in responses.items():
            try:
                code = int(status_code)
                description = response_def.get("description", "Success")
                status_codes[code] = description
            except ValueError:
                continue

        # Add common status codes based on method
        method = endpoint.get("method", "GET")
        if method == "POST":
            status_codes[201] = "Created"
        elif method == "PUT":
            status_codes[200] = "Updated"
        elif method == "DELETE":
            status_codes[204] = "No Content"

        return status_codes

    def _calculate_complexity_score(self, analysis: Dict[str, Any]) -> int:
        """Calculate migration complexity score (0-100)"""

        score = 0

        # Endpoint complexity
        endpoint_count = len(analysis["endpoints"])
        if endpoint_count <= 5:
            score += 10
        elif endpoint_count <= 20:
            score += 25
        elif endpoint_count <= 50:
            score += 50
        else:
            score += 75

        # Authentication complexity
        auth_schemes = len(analysis["authentication"])
        if auth_schemes == 0:
            score += 5
        elif auth_schemes == 1:
            score += 10
        else:
            score += 20

        # Data model complexity
        model_count = len(analysis["data_models"])
        if model_count <= 5:
            score += 5
        elif model_count <= 15:
            score += 15
        else:
            score += 25

        return min(score, 100)

    def _generate_migration_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate migration recommendations"""

        recommendations = []

        complexity = analysis.get("complexity_score", 0)

        if complexity < 30:
            recommendations.append("Low complexity migration - consider immediate migration")
            recommendations.append("Single workflow per endpoint approach recommended")
        elif complexity < 60:
            recommendations.append("Medium complexity migration - gradual migration recommended")
            recommendations.append("Group related endpoints into workflow collections")
        else:
            recommendations.append("High complexity migration - parallel deployment recommended")
            recommendations.append("Implement compatibility layer during transition")
            recommendations.append("Consider breaking down large APIs into smaller services")

        # Authentication recommendations
        if analysis["authentication"]:
            recommendations.append("Implement Nexus authentication middleware for existing auth")
        else:
            recommendations.append("Add authentication layer during migration")

        # Data model recommendations
        if len(analysis["data_models"]) > 10:
            recommendations.append("Consider using Nexus data validation nodes for complex models")

        return recommendations

    def create_migration_plan(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create detailed migration plan"""

        plan = {
            "migration_strategy": "gradual",
            "phases": [],
            "timeline_weeks": 0,
            "resources_required": [],
            "risk_assessment": {},
            "rollback_plan": {}
        }

        complexity = analysis.get("complexity_score", 0)
        endpoint_count = len(analysis["endpoints"])

        # Determine strategy
        if complexity < 30:
            plan["migration_strategy"] = "immediate"
            plan["timeline_weeks"] = 2
        elif complexity < 60:
            plan["migration_strategy"] = "gradual"
            plan["timeline_weeks"] = 6
        else:
            plan["migration_strategy"] = "parallel"
            plan["timeline_weeks"] = 12

        # Define phases
        if plan["migration_strategy"] == "gradual":
            endpoints_per_phase = max(5, endpoint_count // 4)
            for i in range(0, endpoint_count, endpoints_per_phase):
                phase_endpoints = analysis["endpoints"][i:i + endpoints_per_phase]
                phase = {
                    "phase_number": len(plan["phases"]) + 1,
                    "endpoints": [f"{ep['method']} {ep['path']}" for ep in phase_endpoints],
                    "duration_weeks": 1.5,
                    "dependencies": [],
                    "validation_criteria": [
                        "All endpoints migrated successfully",
                        "Performance benchmarks met",
                        "No regression in functionality"
                    ]
                }
                plan["phases"].append(phase)

        # Risk assessment
        plan["risk_assessment"] = {
            "data_loss_risk": "low" if complexity < 50 else "medium",
            "downtime_risk": "minimal" if plan["migration_strategy"] == "parallel" else "low",
            "performance_impact": "none" if complexity < 30 else "minimal",
            "mitigation_strategies": [
                "Comprehensive testing in staging environment",
                "Blue-green deployment for zero downtime",
                "Automated rollback procedures",
                "Performance monitoring during migration"
            ]
        }

        return plan

# Migration from Microservices
class MicroservicesToNexusMigrator:
    """Migrate microservices architecture to Nexus workflows"""

    def __init__(self):
        self.service_mappings = {}
        self.workflow_collections = {}
        self.integration_patterns = {}

    def analyze_microservices_architecture(self, services_config: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze existing microservices for migration"""

        analysis = {
            "services": [],
            "communication_patterns": [],
            "data_dependencies": [],
            "shared_resources": [],
            "migration_approach": "service_to_workflow_collection"
        }

        for service_name, service_config in services_config.items():
            service_analysis = {
                "name": service_name,
                "endpoints": service_config.get("endpoints", []),
                "dependencies": service_config.get("dependencies", []),
                "database": service_config.get("database"),
                "message_queues": service_config.get("message_queues", []),
                "complexity": self._assess_service_complexity(service_config)
            }
            analysis["services"].append(service_analysis)

        # Analyze communication patterns
        analysis["communication_patterns"] = self._analyze_communication_patterns(services_config)

        return analysis

    def _assess_service_complexity(self, service_config: Dict[str, Any]) -> str:
        """Assess complexity of individual service"""

        endpoint_count = len(service_config.get("endpoints", []))
        dependency_count = len(service_config.get("dependencies", []))

        if endpoint_count <= 5 and dependency_count <= 2:
            return "low"
        elif endpoint_count <= 15 and dependency_count <= 5:
            return "medium"
        else:
            return "high"

    def _analyze_communication_patterns(self, services_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze inter-service communication patterns"""

        patterns = []

        for service_name, service_config in services_config.items():
            for dependency in service_config.get("dependencies", []):
                pattern = {
                    "from_service": service_name,
                    "to_service": dependency,
                    "type": "synchronous",  # Assume REST calls
                    "migration_strategy": "workflow_to_workflow"
                }
                patterns.append(pattern)

        return patterns

    def generate_workflow_collection(self, service_config: Dict[str, Any]) -> Dict[str, WorkflowBuilder]:
        """Generate workflow collection from microservice"""

        workflows = {}
        service_name = service_config["name"]

        # Create workflow for each endpoint or logical group
        for endpoint in service_config.get("endpoints", []):
            workflow_name = f"{service_name}_{endpoint['operation']}"
            workflow = WorkflowBuilder()

            # Add authentication if required
            if service_config.get("requires_auth", True):
                workflow.add_node("AuthenticationNode", "auth", {
                    "provider": "oauth2",
                    "required_scopes": endpoint.get("scopes", [])
                })

            # Add business logic
            workflow.add_node("PythonCodeNode", "business_logic", {
                "code": self._generate_service_logic(service_name, endpoint)
            })

            # Add database integration if needed
            if service_config.get("database"):
                workflow.add_node("DatabaseNode", "data_access", {
                    "connection": service_config["database"],
                    "operation": endpoint.get("db_operation", "select")
                })
                workflow.add_connection("business_logic", "data_access", "output", "input")

            workflows[workflow_name] = workflow

        return workflows

    def _generate_service_logic(self, service_name: str, endpoint: Dict[str, Any]) -> str:
        """Generate business logic code for service endpoint"""

        return f'''
def {service_name}_{endpoint.get('operation', 'process')}(data):
    """
    Migrated logic from {service_name} service
    Operation: {endpoint.get('operation', 'unknown')}
    """

    # Service-specific business logic
    result = {{
        "service": "{service_name}",
        "operation": "{endpoint.get('operation', 'unknown')}",
        "data": data.get('input', {{}}),
        "timestamp": __import__('time').time()
    }}

    # Add operation-specific processing
    operation = "{endpoint.get('operation', 'unknown')}"
    if operation == "create":
        result["status"] = "created"
        result["id"] = __import__('uuid').uuid4().hex
    elif operation == "read":
        result["status"] = "retrieved"
    elif operation == "update":
        result["status"] = "updated"
    elif operation == "delete":
        result["status"] = "deleted"

    return result
'''

# Test migration tools
api_migrator = APIToNexusMigrator("flask")

# Example API analysis
sample_openapi_spec = {
    "openapi": "3.0.0",
    "info": {"title": "Sample API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "operationId": "listUsers",
                "summary": "List all users",
                "responses": {"200": {"description": "Success"}}
            },
            "post": {
                "operationId": "createUser",
                "summary": "Create a new user",
                "responses": {"201": {"description": "Created"}}
            }
        },
        "/users/{userId}": {
            "get": {
                "operationId": "getUser",
                "summary": "Get user by ID",
                "parameters": [
                    {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "Success"}}
            }
        }
    }
}

# Simulate API analysis
analysis = {
    "endpoints": [
        {"path": "/users", "method": "GET", "function_name": "list_users"},
        {"path": "/users", "method": "POST", "function_name": "create_user"},
        {"path": "/users/{userId}", "method": "GET", "function_name": "get_user"}
    ],
    "data_models": [{"name": "User", "properties": {"id": "string", "name": "string"}}],
    "authentication": {"bearer": {"type": "http", "scheme": "bearer"}},
    "complexity_score": 35
}

# Generate workflows for endpoints
sample_endpoint = {
    "path": "/users",
    "method": "POST",
    "function_name": "create_user",
    "docstring": "Create a new user in the system"
}

migrated_workflow = api_migrator.generate_nexus_workflow(sample_endpoint)
migration_plan = api_migrator.create_migration_plan(analysis)

# Test microservices migration
microservices_migrator = MicroservicesToNexusMigrator()

sample_microservices = {
    "user_service": {
        "name": "user_service",
        "endpoints": [
            {"operation": "create_user", "path": "/users", "method": "POST"},
            {"operation": "get_user", "path": "/users/{id}", "method": "GET"}
        ],
        "dependencies": ["auth_service"],
        "database": {"type": "postgresql", "name": "users_db"},
        "requires_auth": True
    },
    "auth_service": {
        "name": "auth_service",
        "endpoints": [
            {"operation": "login", "path": "/auth/login", "method": "POST"},
            {"operation": "validate", "path": "/auth/validate", "method": "POST"}
        ],
        "dependencies": [],
        "database": {"type": "postgresql", "name": "auth_db"},
        "requires_auth": False
    }
}

microservices_analysis = microservices_migrator.analyze_microservices_architecture(sample_microservices)
user_service_workflows = microservices_migrator.generate_workflow_collection(sample_microservices["user_service"])
```

## Legacy System Migration

### Database-First Migration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import sqlparse
from typing import Dict, Any, List
import re

class LegacyDatabaseMigrator:
    """Migrate legacy database-centric applications to Nexus"""

    def __init__(self):
        self.table_mappings = {}
        self.procedure_mappings = {}
        self.workflow_generators = {}

    def analyze_database_schema(self, schema_sql: str) -> Dict[str, Any]:
        """Analyze database schema for migration planning"""

        analysis = {
            "tables": [],
            "stored_procedures": [],
            "triggers": [],
            "views": [],
            "relationships": [],
            "complexity_assessment": {}
        }

        # Parse SQL statements
        statements = sqlparse.split(schema_sql)

        for statement in statements:
            parsed = sqlparse.parse(statement)[0]

            # Identify statement type
            first_token = str(parsed.tokens[0]).upper().strip()

            if first_token == "CREATE":
                self._analyze_create_statement(parsed, analysis)

        # Assess complexity
        analysis["complexity_assessment"] = self._assess_database_complexity(analysis)

        return analysis

    def _analyze_create_statement(self, parsed_stmt, analysis: Dict[str, Any]):
        """Analyze CREATE statements"""

        statement_str = str(parsed_stmt)

        if "CREATE TABLE" in statement_str.upper():
            table_info = self._extract_table_info(statement_str)
            if table_info:
                analysis["tables"].append(table_info)

        elif "CREATE PROCEDURE" in statement_str.upper() or "CREATE FUNCTION" in statement_str.upper():
            proc_info = self._extract_procedure_info(statement_str)
            if proc_info:
                analysis["stored_procedures"].append(proc_info)

        elif "CREATE VIEW" in statement_str.upper():
            view_info = self._extract_view_info(statement_str)
            if view_info:
                analysis["views"].append(view_info)

    def _extract_table_info(self, create_statement: str) -> Dict[str, Any]:
        """Extract table information from CREATE TABLE statement"""

        # Simple regex-based extraction (in production, use proper SQL parser)
        table_match = re.search(r'CREATE TABLE (\w+)', create_statement, re.IGNORECASE)
        if not table_match:
            return {}

        table_name = table_match.group(1)

        # Extract columns (simplified)
        columns = []
        column_pattern = r'(\w+)\s+(\w+)(?:\([^)]+\))?(?:\s+NOT NULL)?(?:\s+PRIMARY KEY)?(?:\s+DEFAULT\s+[^,\s]+)?'

        for match in re.finditer(column_pattern, create_statement):
            column = {
                "name": match.group(1),
                "type": match.group(2),
                "nullable": "NOT NULL" not in match.group(0),
                "primary_key": "PRIMARY KEY" in match.group(0)
            }
            columns.append(column)

        return {
            "name": table_name,
            "columns": columns,
            "primary_keys": [col["name"] for col in columns if col["primary_key"]],
            "estimated_size": "unknown"
        }

    def _extract_procedure_info(self, create_statement: str) -> Dict[str, Any]:
        """Extract stored procedure information"""

        proc_match = re.search(r'CREATE (?:PROCEDURE|FUNCTION) (\w+)', create_statement, re.IGNORECASE)
        if not proc_match:
            return {}

        proc_name = proc_match.group(1)

        # Extract parameters (simplified)
        param_pattern = r'@(\w+)\s+(\w+)'
        parameters = []

        for match in re.finditer(param_pattern, create_statement):
            parameter = {
                "name": match.group(1),
                "type": match.group(2),
                "direction": "IN"  # Assume input by default
            }
            parameters.append(parameter)

        return {
            "name": proc_name,
            "type": "procedure" if "PROCEDURE" in create_statement.upper() else "function",
            "parameters": parameters,
            "complexity": "medium"  # Would analyze actual logic in production
        }

    def _extract_view_info(self, create_statement: str) -> Dict[str, Any]:
        """Extract view information"""

        view_match = re.search(r'CREATE VIEW (\w+)', create_statement, re.IGNORECASE)
        if not view_match:
            return {}

        view_name = view_match.group(1)

        return {
            "name": view_name,
            "underlying_tables": [],  # Would extract in production
            "complexity": "low"
        }

    def _assess_database_complexity(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Assess migration complexity based on database analysis"""

        table_count = len(analysis["tables"])
        procedure_count = len(analysis["stored_procedures"])
        view_count = len(analysis["views"])

        complexity_score = 0

        # Table complexity
        if table_count <= 10:
            complexity_score += 10
        elif table_count <= 50:
            complexity_score += 30
        else:
            complexity_score += 50

        # Procedure complexity
        if procedure_count == 0:
            complexity_score += 5
        elif procedure_count <= 10:
            complexity_score += 20
        else:
            complexity_score += 40

        # View complexity
        complexity_score += min(view_count * 5, 25)

        return {
            "score": min(complexity_score, 100),
            "level": "low" if complexity_score < 30 else "medium" if complexity_score < 60 else "high",
            "migration_weeks": max(2, complexity_score // 10),
            "recommendations": self._generate_db_migration_recommendations(complexity_score)
        }

    def _generate_db_migration_recommendations(self, complexity_score: int) -> List[str]:
        """Generate database migration recommendations"""

        recommendations = []

        if complexity_score < 30:
            recommendations.append("Consider direct workflow mapping for simple CRUD operations")
            recommendations.append("Use Nexus database nodes for data access")
        else:
            recommendations.append("Implement database abstraction layer using Nexus")
            recommendations.append("Migrate stored procedures to workflow logic gradually")
            recommendations.append("Consider data synchronization during transition period")

        return recommendations

    def generate_crud_workflows(self, table_info: Dict[str, Any]) -> Dict[str, WorkflowBuilder]:
        """Generate CRUD workflows for database table"""

        table_name = table_info["name"]
        workflows = {}

        # Create workflow
        create_workflow = WorkflowBuilder()
        create_workflow.add_node("ValidationNode", "validate_input", {
            "schema": self._generate_table_schema(table_info),
            "required_fields": [col["name"] for col in table_info["columns"] if not col["nullable"]]
        })
        create_workflow.add_node("DatabaseNode", "insert_record", {
            "operation": "insert",
            "table": table_name,
            "return_id": True
        })
        create_workflow.add_connection("validate_input", "insert_record", "output", "input")
        workflows[f"create_{table_name}"] = create_workflow

        # Read workflow
        read_workflow = WorkflowBuilder()
        read_workflow.add_node("DatabaseNode", "fetch_record", {
            "operation": "select",
            "table": table_name,
            "conditions": "dynamic"
        })
        workflows[f"read_{table_name}"] = read_workflow

        # Update workflow
        update_workflow = WorkflowBuilder()
        update_workflow.add_node("ValidationNode", "validate_update", {
            "schema": self._generate_table_schema(table_info),
            "partial_update": True
        })
        update_workflow.add_node("DatabaseNode", "update_record", {
            "operation": "update",
            "table": table_name,
            "conditions": "by_id"
        })
        update_workflow.add_connection("validate_update", "update_record", "output", "input")
        workflows[f"update_{table_name}"] = update_workflow

        # Delete workflow
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("DatabaseNode", "delete_record", {
            "operation": "delete",
            "table": table_name,
            "conditions": "by_id",
            "soft_delete": True
        })
        workflows[f"delete_{table_name}"] = delete_workflow

        return workflows

    def _generate_table_schema(self, table_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate validation schema from table structure"""

        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        type_mapping = {
            "VARCHAR": "string",
            "TEXT": "string",
            "INT": "integer",
            "INTEGER": "integer",
            "DECIMAL": "number",
            "FLOAT": "number",
            "BOOLEAN": "boolean",
            "DATE": "string",
            "DATETIME": "string",
            "TIMESTAMP": "string"
        }

        for column in table_info["columns"]:
            column_type = type_mapping.get(column["type"].upper(), "string")

            schema["properties"][column["name"]] = {
                "type": column_type,
                "description": f"Column {column['name']} from table {table_info['name']}"
            }

            if not column["nullable"]:
                schema["required"].append(column["name"])

        return schema

# Test legacy migration
legacy_migrator = LegacyDatabaseMigrator()

# Sample schema
sample_schema = '''
CREATE TABLE users (
    id INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT NOT NULL,
    total_amount DECIMAL(10,2),
    order_date DATE,
    status VARCHAR(20) DEFAULT 'pending'
);

CREATE PROCEDURE GetUserOrders(@user_id INT)
AS
BEGIN
    SELECT * FROM orders WHERE user_id = @user_id;
END
'''

# Analyze schema
schema_analysis = legacy_migrator.analyze_database_schema(sample_schema)

# Generate CRUD workflows for users table
if schema_analysis["tables"]:
    users_table = schema_analysis["tables"][0]  # users table
    crud_workflows = legacy_migrator.generate_crud_workflows(users_table)
```

## Migration Automation Tools

### Automated Code Generation

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import ast
import inspect
from typing import Dict, Any, List, Callable
import importlib.util

class AutomatedMigrationGenerator:
    """Automated tools for generating Nexus workflows from existing code"""

    def __init__(self):
        self.generated_workflows = {}
        self.migration_metadata = {}
        self.code_analyzers = {
            "python": self._analyze_python_function,
            "javascript": self._analyze_javascript_function,
            "java": self._analyze_java_method
        }

    def generate_workflow_from_function(self, func: Callable, workflow_name: str = None) -> WorkflowBuilder:
        """Generate Nexus workflow from Python function"""

        if not workflow_name:
            workflow_name = f"migrated_{func.__name__}"

        workflow = WorkflowBuilder()

        # Analyze function signature
        sig = inspect.signature(func)

        # Add input validation based on parameters
        if sig.parameters:
            validation_schema = self._generate_schema_from_signature(sig)
            workflow.add_node("ValidationNode", "input_validation", {
                "schema": validation_schema
            })

        # Add the function as a PythonCodeNode
        source_code = inspect.getsource(func)
        workflow.add_node("PythonCodeNode", "main_logic", {
            "code": source_code,
            "function_name": func.__name__
        })

        # Connect nodes if validation exists
        if sig.parameters:
            workflow.add_connection("input_validation", "main_logic", "output", "input")

        # Store metadata
        self.migration_metadata[workflow_name] = {
            "original_function": func.__name__,
            "source_module": func.__module__,
            "parameter_count": len(sig.parameters),
            "migration_timestamp": time.time()
        }

        self.generated_workflows[workflow_name] = workflow
        return workflow

    def _generate_schema_from_signature(self, signature: inspect.Signature) -> Dict[str, Any]:
        """Generate validation schema from function signature"""

        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        for param_name, param in signature.parameters.items():
            param_schema = {"type": "string"}  # Default type

            # Use type hints if available
            if param.annotation != inspect.Parameter.empty:
                annotation = param.annotation
                if annotation == int:
                    param_schema["type"] = "integer"
                elif annotation == float:
                    param_schema["type"] = "number"
                elif annotation == bool:
                    param_schema["type"] = "boolean"
                elif annotation == list:
                    param_schema["type"] = "array"
                elif annotation == dict:
                    param_schema["type"] = "object"

            schema["properties"][param_name] = param_schema

            # Required if no default value
            if param.default == inspect.Parameter.empty:
                schema["required"].append(param_name)

        return schema

    def migrate_class_to_workflows(self, cls: type) -> Dict[str, WorkflowBuilder]:
        """Convert class methods to individual workflows"""

        workflows = {}
        class_name = cls.__name__

        # Get all public methods
        for method_name in dir(cls):
            if not method_name.startswith('_'):
                method = getattr(cls, method_name)
                if callable(method):
                    workflow_name = f"{class_name}_{method_name}"

                    # Create workflow for method
                    workflow = WorkflowBuilder()

                    # Add class instantiation if needed
                    workflow.add_node("PythonCodeNode", "class_method", {
                        "code": self._generate_class_method_code(cls, method_name),
                        "function_name": f"execute_{method_name}"
                    })

                    workflows[workflow_name] = workflow

        return workflows

    def _generate_class_method_code(self, cls: type, method_name: str) -> str:
        """Generate code to execute class method"""

        class_name = cls.__name__

        code_template = f'''
def execute_{method_name}(data):
    """
    Generated wrapper for {class_name}.{method_name}
    """

    # Import the class (assuming it's available)
    # In production, you'd handle imports properly

    # Create instance
    instance = {class_name}()

    # Extract method arguments from data
    method_args = data.get('args', [])
    method_kwargs = data.get('kwargs', {{}})

    # Call the method
    result = instance.{method_name}(*method_args, **method_kwargs)

    return {{
        "result": result,
        "class": "{class_name}",
        "method": "{method_name}",
        "success": True
    }}
'''

        return code_template.strip()

    def _analyze_python_function(self, source_code: str) -> Dict[str, Any]:
        """Analyze Python function for migration insights"""

        tree = ast.parse(source_code)
        analysis = {
            "complexity": "low",
            "external_dependencies": [],
            "database_calls": False,
            "api_calls": False,
            "file_operations": False,
            "recommended_nodes": []
        }

        # Walk the AST to find patterns
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for database operations
                if hasattr(node.func, 'attr'):
                    func_name = node.func.attr
                    if func_name in ['execute', 'query', 'commit', 'rollback']:
                        analysis["database_calls"] = True
                        analysis["recommended_nodes"].append("DatabaseNode")

                # Check for HTTP requests
                if hasattr(node.func, 'id') and node.func.id in ['requests', 'urllib']:
                    analysis["api_calls"] = True
                    analysis["recommended_nodes"].append("HTTPRequestNode")

            elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                # Track external dependencies
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        analysis["external_dependencies"].append(alias.name)
                elif node.module:
                    analysis["external_dependencies"].append(node.module)

        # Assess complexity
        if len(analysis["external_dependencies"]) > 5:
            analysis["complexity"] = "high"
        elif len(analysis["external_dependencies"]) > 2:
            analysis["complexity"] = "medium"

        return analysis

    def _analyze_javascript_function(self, source_code: str) -> Dict[str, Any]:
        """Analyze JavaScript function (simplified)"""

        analysis = {
            "complexity": "medium",
            "framework": "unknown",
            "async_operations": "async" in source_code or "await" in source_code,
            "recommended_migration": "rewrite_in_python"
        }

        return analysis

    def _analyze_java_method(self, source_code: str) -> Dict[str, Any]:
        """Analyze Java method (simplified)"""

        analysis = {
            "complexity": "high",
            "framework": "spring" if "@" in source_code else "unknown",
            "recommended_migration": "port_to_python_workflow"
        }

        return analysis

    def generate_migration_report(self) -> Dict[str, Any]:
        """Generate comprehensive migration report"""

        report = {
            "migration_summary": {
                "total_workflows_generated": len(self.generated_workflows),
                "migration_timestamp": time.time(),
                "success_rate": 100.0  # Assume success for generated workflows
            },
            "workflow_details": {},
            "recommendations": [],
            "next_steps": []
        }

        # Add details for each workflow
        for workflow_name, metadata in self.migration_metadata.items():
            report["workflow_details"][workflow_name] = metadata

        # Generate recommendations
        if len(self.generated_workflows) > 0:
            report["recommendations"] = [
                "Test all generated workflows in development environment",
                "Validate input/output schemas match expected formats",
                "Implement error handling for production use",
                "Add monitoring and logging for migrated workflows"
            ]

        # Next steps
        report["next_steps"] = [
            "Deploy workflows to Nexus development environment",
            "Run integration tests with existing systems",
            "Performance benchmark against original implementations",
            "Plan gradual rollout to production"
        ]

        return report

# Test automated migration
automated_migrator = AutomatedMigrationGenerator()

# Example function to migrate
def sample_business_function(user_id: int, amount: float, currency: str = "USD") -> dict:
    """Sample business function to migrate"""

    # Simulate business logic
    result = {
        "user_id": user_id,
        "processed_amount": amount * 1.02,  # Add 2% fee
        "currency": currency,
        "transaction_id": f"txn_{user_id}_{int(time.time())}",
        "status": "completed"
    }

    return result

# Generate workflow from function
import time
migrated_workflow = automated_migrator.generate_workflow_from_function(
    sample_business_function,
    "payment_processing_workflow"
)

# Generate migration report
migration_report = automated_migrator.generate_migration_report()
```

This comprehensive migration guide provides:

1. **API Migration Tools** - Convert REST APIs to Nexus workflows with automated analysis
2. **Microservices Migration** - Transform microservices architecture to workflow collections
3. **Legacy Database Migration** - Migrate database-centric applications with CRUD generation
4. **Automated Code Generation** - Tools for converting existing functions and classes to workflows

Each migration approach includes analysis tools, complexity assessment, and step-by-step transformation processes to ensure smooth transitions to Nexus.
