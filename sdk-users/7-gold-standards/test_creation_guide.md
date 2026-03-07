# GOLD STANDARD: Test Case Creation Guide

**Version**: 1.0
**Date**: 2025-07-22
**Purpose**: Eliminate parameter errors and test failures through systematic test case creation
**Problem Solved**: Repeated test case changes due to parameter mismatches like "valid" vs "success"

## 🚨 CRITICAL PROBLEM STATEMENT

**Observed Issue**: We keep repeating parameter errors in test cases:

- Using `result["valid"]` when node outputs `result["success"]`
- Missing required parameters like `requestor_id`
- Wrong parameter types or structures
- Incorrect output path assertions

**Root Cause**: Writing test cases without systematically checking:

1. Node parameter contracts
2. Node output structures
3. Parameter passing gold standards
4. Connection parameter requirements

**Impact**:

- Wasted development time fixing preventable errors
- Inconsistent test patterns across codebase
- Reduced confidence in test reliability

## 📋 Table of Contents

1. [Pre-Test Research Checklist](#pre-test-research-checklist)
2. [Systematic Test Creation Process](#systematic-test-creation-process)
3. [Contract-First Test Development](#contract-first-test-development)
4. [Output Structure Validation](#output-structure-validation)
5. [Parameter Passing Method Selection](#parameter-passing-method-selection)
6. [Common Error Prevention](#common-error-prevention)
7. [Test Templates by Scenario](#test-templates-by-scenario)

## 🔍 Pre-Test Research Checklist

**Recommended: Complete this checklist before writing test cases**

### ✅ Step 1: Contract Research

```bash
# 1. Check the Custom Node Contract Reference
grep -A 10 "NodeName" src/tpc/tpc_user_management/nodes/CUSTOM_NODE_CONTRACT_REFERENCE.md

# 2. Find the actual contract class
find . -name "*.py" -exec grep -l "NodeNameContract" {} \;

# 3. Read the contract definition
# Look for: required parameters, optional parameters, types, validation rules
```

### ✅ Step 2: Output Structure Research

```bash
# 1. Find the node implementation
find . -name "*node_name*.py" -path "*/nodes/*"

# 2. Check the run() method return structure
grep -A 20 "def run" src/path/to/node.py

# 3. Look for result structure examples in existing tests
grep -r "NodeName" tests/ --include="*.py" -A 5 -B 5
```

### ✅ Step 3: Parameter Passing Research

```bash
# 1. Review parameter passing gold standard
cat docs/sdk-improvement-active/GOLD_STANDARD_PARAMETER_PASSING_COMPREHENSIVE.md

# 2. Check if node has connection parameter contract
grep -A 10 "get_connection_contract" src/path/to/node.py
```

### ✅ Step 4: Existing Test Pattern Research

```bash
# 1. Find similar working tests
find tests/ -name "*.py" -exec grep -l "similar_node_or_workflow" {} \;

# 2. Study successful patterns
# Look for: parameter structure, assertion patterns, connection usage
```

## 🏗️ Systematic Test Creation Process

### Phase 1: Research and Planning

**1.1 Identify All Nodes in Test Workflow**

```python
# Document each node you'll test:
nodes_to_test = [
    {
        "class": "TPCParameterPrepNode",
        "id": "prep",
        "contract": "ParameterPrepContract",
        "purpose": "Prepare DB parameters"
    },
    {
        "class": "TPCPasswordValidatorNode",
        "id": "validator",
        "contract": "PasswordValidatorContract",
        "purpose": "Validate user password"
    }
]
```

**1.2 Research Each Node Contract**

```python
# For EACH node, document:
node_requirements = {
    "TPCParameterPrepNode": {
        "required_params": ["credentials", "tenant_id"],
        "optional_params": ["operation"],
        "output_structure": {"result": {"db_params": list, "credentials": dict}},
        "connections_out": ["result.db_params", "result.credentials"]
    },
    "TPCPasswordValidatorNode": {
        "required_params": ["credentials", "user_info", "hardcoded_password"],
        "optional_params": ["validation_rules"],
        "output_structure": {"result": {"success": bool, "username": str, "user": dict}},
        "connections_in": ["credentials", "user_info"]
    }
}
```

**1.3 Plan Parameter Passing Strategy**

```python
# Choose method based on gold standard:
parameter_strategy = {
    "method": "Method 1 (Node Configuration)",  # Most reliable for tests
    "rationale": "Static test values, maximum reliability",
    "fallback": "Method 3 with minimal config if dynamic values needed"
}
```

### Phase 2: Contract-Driven Implementation

**2.1 Create Test Parameters from Contracts**

```python
# SYSTEMATIC: Build parameters from contract research
def create_test_parameters():
    """Build test parameters based on contract research."""

    # From TPCParameterPrepContract research:
    prep_params = {
        "credentials": {  # Required dict from contract
            "username": "admin_test",
            "password": "SecureP@ss123!"
        },
        "tenant_id": "tpc_user_management",  # Required string from contract
        "operation": "authentication"  # Optional string from contract
    }

    # From PasswordValidatorContract research:
    validator_params = {
        "hardcoded_password": "SecureP@ss123!",  # Required string from contract
        "validation_rules": {  # Optional dict from contract
            "min_length": 8,
            "require_special": True
        }
        # credentials and user_info will come via connections
    }

    return prep_params, validator_params
```

**2.2 Build Workflow with Researched Parameters**

```python
def build_test_workflow():
    """Build workflow using contract-researched parameters."""
    workflow = WorkflowBuilder()

    prep_params, validator_params = create_test_parameters()

    # Method 1: All parameters in configuration (gold standard for tests)
    workflow.add_node("TPCParameterPrepNode", "prep", prep_params)
    workflow.add_node("TPCPasswordValidatorNode", "validator", validator_params)

    # Database node needs connection string (from environment setup)
    workflow.add_node("AsyncSQLDatabaseNode", "lookup", {
        "connection_string": database_url,  # From fixture
        "query": "SELECT * FROM users WHERE username = $1"
    })

    # Connections based on contract research
    workflow.add_connection("prep", "result.db_params", "lookup", "params")
    workflow.add_connection("prep", "result.credentials", "validator", "credentials")
    workflow.add_connection("lookup", "result", "validator", "user_info")  # Note: not direct user_info

    return workflow.build()
```

**2.3 Create Assertions from Output Structure Research**

```python
def validate_results(results):
    """Validate results using researched output structures."""

    # TPCParameterPrepNode output structure from research:
    prep_result = results["prep"]["result"]
    assert "db_params" in prep_result  # From contract research
    assert "credentials" in prep_result  # From contract research
    assert isinstance(prep_result["db_params"], list)  # Type from research
    assert isinstance(prep_result["credentials"], dict)  # Type from research

    # TPCPasswordValidatorNode output structure from research:
    validator_result = results["validator"]["result"]  # Note: ["result"] not direct
    assert "success" in validator_result  # NOT "valid" - from actual node code research
    assert "username" in validator_result  # From contract research
    assert "user" in validator_result  # From contract research
    assert isinstance(validator_result["success"], bool)  # Type from research

    # Business logic validation
    assert validator_result["success"] is True
    assert validator_result["username"] == "admin_test"
```

## 📝 Contract-First Test Development

### Template: Full Contract Research Process

```python
"""
Integration test using systematic contract-first development.

RESEARCH COMPLETED:
1. ✅ Node contracts checked in CUSTOM_NODE_CONTRACT_REFERENCE.md
2. ✅ Parameter requirements documented from contracts/parameter_contracts.py
3. ✅ Output structures verified from node implementations
4. ✅ Connection requirements identified from SecureGovernedNode patterns
5. ✅ Parameter passing method selected: Method 1 (Node Configuration)

CONTRACT SUMMARY:
- TPCParameterPrepNode: credentials (dict, req), tenant_id (str, req) → result.db_params (list)
- AsyncSQLDatabaseNode: connection_string (str, req), query (str, req) → result.data (list)
- TPCPasswordValidatorNode: hardcoded_password (str, req) + connections → result.success (bool)
"""

import pytest
from typing import Dict, Any

# Import based on contract reference research
from tests.fixtures.workflow_fixtures import test_environment
from tests.fixtures.database_fixtures import seed_json_data, database_url
from tests.fixtures.data_fixtures import admin_user

# SDK imports
from kailash.workflow.builder import WorkflowBuilder

class TestContractFirstAuthentication:
    """Authentication test using contract-first methodology."""

    def test_authentication_workflow_contract_first(
        self,
        test_environment,
        seed_json_data,
        database_url,
        admin_user
    ):
        """Test authentication using systematic contract research."""

        # PHASE 1: CONTRACT-RESEARCHED PARAMETERS
        # Based on TPCParameterPrepContract research
        prep_config = {
            "credentials": {
                "username": admin_user["username"],  # From fixture research
                "password": "SecureP@ss123!"  # From migration ADR research
            },
            "tenant_id": "tpc_user_management",  # Required string from contract
            "operation": "authentication"  # Optional string for context
        }

        # Based on AsyncSQLDatabaseNode SDK research
        database_config = {
            "connection_string": database_url,  # From fixture research
            "query": """
                SELECT id, username, email, role, clearance, department,
                       location, is_active, attributes
                FROM users
                WHERE username = $1 AND is_active = true
            """,  # Query structure from database schema research
            "pool_size": 5,
            "max_overflow": 10
        }

        # Based on PasswordValidatorContract research
        validator_config = {
            "hardcoded_password": "SecureP@ss123!",  # Required string from contract
            "validation_rules": {  # Optional dict from contract
                "min_length": 8,
                "require_special": True,
                "require_numbers": True
            }
        }

        # PHASE 2: WORKFLOW CONSTRUCTION WITH RESEARCHED PATTERNS
        workflow = WorkflowBuilder()

        # Method 1 (Node Configuration) per gold standard
        workflow.add_node("TPCParameterPrepNode", "prep", prep_config)
        workflow.add_node("AsyncSQLDatabaseNode", "lookup", database_config)
        workflow.add_node("TPCPasswordValidatorNode", "validator", validator_config)

        # Connections based on contract connection research
        workflow.add_connection("prep", "result.db_params", "lookup", "params")
        workflow.add_connection("prep", "result.credentials", "validator", "credentials")
        workflow.add_connection("lookup", "result", "validator", "user_info")

        # PHASE 3: EXECUTION
        runtime = test_environment.runtime
        results, run_id = runtime.execute(workflow.build())

        # PHASE 4: CONTRACT-BASED VALIDATION
        # Based on researched output structures

        # TPCParameterPrepNode validation (from contract research)
        prep_result = results["prep"]["result"]
        assert isinstance(prep_result["db_params"], list)
        assert prep_result["db_params"] == [admin_user["username"]]
        assert isinstance(prep_result["credentials"], dict)
        assert prep_result["credentials"]["username"] == admin_user["username"]

        # AsyncSQLDatabaseNode validation (from SDK research)
        lookup_result = results["lookup"]["result"]
        assert "data" in lookup_result
        assert isinstance(lookup_result["data"], list)
        assert len(lookup_result["data"]) > 0

        # TPCPasswordValidatorNode validation (from contract research)
        validator_result = results["validator"]["result"]
        # CRITICAL: Use "success" NOT "valid" per node implementation research
        assert validator_result["success"] is True
        assert validator_result["username"] == admin_user["username"]
        assert "user" in validator_result  # Full user object per contract

        # Business validation
        user_data = validator_result["user"]
        assert user_data["role"] == admin_user["role"]
        assert user_data["is_active"] is True
```

## 🎯 Output Structure Validation

### Systematic Output Research Method

```python
def research_node_output_structure(node_name: str) -> Dict[str, Any]:
    """Template for researching node output structure."""

    # Step 1: Check contract reference
    contract_output = "Check CUSTOM_NODE_CONTRACT_REFERENCE.md"

    # Step 2: Find node implementation
    node_file = f"find . -name '*{node_name.lower()}*' -path '*/nodes/*'"

    # Step 3: Read run() method
    # Look for return statement structure

    # Step 4: Check existing tests
    existing_tests = f"grep -r '{node_name}' tests/ -A 5"

    return {
        "structure": "Document the actual return structure",
        "key_fields": ["field1", "field2"],
        "types": {"field1": "type", "field2": "type"},
        "common_errors": ["Using wrong field name", "Wrong nested path"]
    }

# Example: TPCPasswordValidatorNode research results
PASSWORD_VALIDATOR_OUTPUT = {
    "structure": {
        "result": {
            "success": "bool",  # NOT "valid"!
            "username": "str",
            "user_id": "str",
            "user": "dict",  # Full user object
            "validation_details": "dict"
        }
    },
    "common_errors": [
        "Using result['valid'] instead of result['success']",
        "Expecting direct user fields instead of result['user']"
    ],
    "correct_assertions": [
        "assert results['validator']['result']['success'] is True",
        "assert results['validator']['result']['username'] == expected",
        "assert 'user' in results['validator']['result']"
    ]
}
```

## ⚡ Parameter Passing Method Selection

### Decision Tree for Test Parameter Passing

```python
def select_parameter_method(test_scenario: str) -> str:
    """Systematic method selection per gold standard."""

    if test_scenario == "unit_test":
        return "Method 1 (Node Configuration) - Most reliable for tests"

    elif test_scenario == "integration_test_static":
        return "Method 1 (Node Configuration) - Static values, maximum reliability"

    elif test_scenario == "integration_test_dynamic":
        return "Method 3 (Runtime Parameters) with minimal config to avoid edge case"

    elif test_scenario == "workflow_data_flow":
        return "Method 2 (Workflow Connections) - Test inter-node communication"

    else:
        return "Default: Method 1 - Safest choice per gold standard"

# Implementation template
def build_test_with_method_selection(test_type: str):
    """Build test using systematic method selection."""

    method = select_parameter_method(test_type)
    workflow = WorkflowBuilder()

    if method.startswith("Method 1"):
        # All parameters in node configuration
        workflow.add_node("NodeClass", "node_id", {
            "all_params": "provided_here",
            "no_runtime": "needed"
        })

    elif method.startswith("Method 3"):
        # Minimal config + runtime parameters
        workflow.add_node("NodeClass", "node_id", {
            "_configured": True  # Avoid edge case
        })
        # Parameters provided at runtime.execute()

    elif method.startswith("Method 2"):
        # Connection-based flow
        workflow.add_node("SourceNode", "source", {...})
        workflow.add_node("TargetNode", "target", {})
        workflow.add_connection("source", "output", "target", "input")

    return workflow
```

## 🚫 Common Error Prevention

### Error Pattern Database

```python
COMMON_TEST_ERRORS = {
    "wrong_output_field": {
        "error": "Using 'valid' instead of 'success'",
        "prevention": "Always check node implementation run() method return structure",
        "fix": "results['node']['result']['success'] not results['node']['valid']"
    },

    "missing_required_param": {
        "error": "Missing 'requestor_id' parameter",
        "prevention": "Check parameter contract for ALL required fields",
        "fix": "Add all required parameters from contract research"
    },

    "wrong_parameter_type": {
        "error": "Passing string when dict expected",
        "prevention": "Verify parameter types in contract definition",
        "fix": "Match exact type from contract: dict not str"
    },

    "incorrect_connection_path": {
        "error": "Using 'result' instead of 'result.credentials'",
        "prevention": "Research node output structure and connection requirements",
        "fix": "Use exact output path: 'result.credentials' for nested data"
    },

    "edge_case_parameter_method": {
        "error": "Runtime parameters not received with empty config",
        "prevention": "Follow parameter passing gold standard edge case warnings",
        "fix": "Add minimal config or use Method 1 for tests"
    }
}

def prevent_common_error(error_type: str) -> str:
    """Get prevention strategy for common error."""
    return COMMON_TEST_ERRORS.get(error_type, {}).get("prevention", "Check contracts first")
```

### Pre-Flight Error Check

```python
def validate_test_before_writing(test_plan: Dict[str, Any]) -> List[str]:
    """Pre-flight check to catch common errors before writing test."""

    issues = []

    # Check 1: All nodes have contract research
    for node in test_plan.get("nodes", []):
        if "contract_checked" not in node:
            issues.append(f"Node {node['name']}: Contract not researched")

    # Check 2: Output assertions use researched structure
    for assertion in test_plan.get("assertions", []):
        if "research_verified" not in assertion:
            issues.append(f"Assertion {assertion}: Output structure not verified")

    # Check 3: Parameter method follows gold standard
    method = test_plan.get("parameter_method")
    if method not in ["Method 1", "Method 2", "Method 3 with minimal config"]:
        issues.append(f"Parameter method not following gold standard: {method}")

    # Check 4: Required parameters identified
    for node in test_plan.get("nodes", []):
        if not node.get("required_params_identified"):
            issues.append(f"Node {node['name']}: Required parameters not identified")

    return issues

# Usage example
test_plan = {
    "nodes": [
        {
            "name": "TPCPasswordValidatorNode",
            "contract_checked": True,
            "required_params_identified": True,
            "output_structure_researched": True
        }
    ],
    "parameter_method": "Method 1",
    "assertions": [
        {
            "field": "result.success",
            "research_verified": True
        }
    ]
}

issues = validate_test_before_writing(test_plan)
if issues:
    print("Fix these issues before writing test:")
    for issue in issues:
        print(f"- {issue}")
```

## 📋 Test Templates by Scenario

### Template 1: Single Node Unit Test

```python
def test_single_node_contract_first(self):
    """Template for single node testing with contract research."""

    # RESEARCH PHASE (document your findings)
    # 1. ✅ Contract: NodeNameContract in contracts/parameter_contracts.py
    # 2. ✅ Required params: param1 (str), param2 (dict)
    # 3. ✅ Output structure: {"result": {"success": bool, "data": dict}}
    # 4. ✅ Method: Method 1 (most reliable for unit tests)

    # IMPLEMENTATION PHASE
    from src.path.to.node import NodeClass

    # Contract-based parameter construction
    node_params = {
        "param1": "test_value",  # str, required per contract
        "param2": {"key": "value"},  # dict, required per contract
        "param3": "optional_value"  # str, optional per contract
    }

    # Direct node testing
    node = NodeClass(**node_params)
    result = node.execute()

    # Contract-based assertions
    assert "result" in result  # Top level per contract
    assert "success" in result["result"]  # NOT "valid"
    assert isinstance(result["result"]["success"], bool)
    assert result["result"]["success"] is True
```

### Template 2: Workflow Integration Test

```python
def test_workflow_integration_contract_first(self, test_environment, database_url):
    """Template for workflow testing with systematic research."""

    # RESEARCH PHASE DOCUMENTATION
    """
    Contract Research Completed:
    ✅ Node 1: TPCParameterPrepNode
       - Contract: ParameterPrepContract
       - Required: credentials (dict), tenant_id (str)
       - Output: result.db_params (list), result.credentials (dict)

    ✅ Node 2: AsyncSQLDatabaseNode
       - SDK Node: No custom contract
       - Required: connection_string (str), query (str), params (list via connection)
       - Output: result.data (list)

    ✅ Parameter Method: Method 1 (Node Configuration) - Gold standard for tests
    ✅ Connection Research: prep.result.db_params → lookup.params
    """

    # IMPLEMENTATION PHASE
    workflow = WorkflowBuilder()

    # Node 1: Contract-researched configuration
    workflow.add_node("TPCParameterPrepNode", "prep", {
        "credentials": {"username": "test_user", "password": "test_pass"},
        "tenant_id": "test_tenant"
    })

    # Node 2: SDK node configuration
    workflow.add_node("AsyncSQLDatabaseNode", "lookup", {
        "connection_string": database_url,
        "query": "SELECT * FROM users WHERE username = $1"
    })

    # Researched connection pattern
    workflow.add_connection("prep", "result.db_params", "lookup", "params")

    # EXECUTION PHASE
    runtime = test_environment.runtime
    results, run_id = runtime.execute(workflow.build())

    # VALIDATION PHASE - Contract-based assertions
    # TPCParameterPrepNode validation
    prep_result = results["prep"]["result"]
    assert isinstance(prep_result["db_params"], list)
    assert isinstance(prep_result["credentials"], dict)

    # AsyncSQLDatabaseNode validation
    lookup_result = results["lookup"]["result"]
    assert "data" in lookup_result
    assert isinstance(lookup_result["data"], list)
```

### Template 3: Error Scenario Test

```python
def test_error_scenario_contract_first(self):
    """Template for testing error scenarios with contract validation."""

    # RESEARCH PHASE
    # ✅ Error Contract: What errors does the node define in contract?
    # ✅ Error Structure: How are errors returned? Exception or error result?
    # ✅ Required Fields: What happens when required fields are missing?

    from src.path.to.node import NodeClass

    # Test missing required parameter (from contract research)
    with pytest.raises(ValueError, match="Required parameter.*missing"):
        node = NodeClass()
        node.execute(
            # param1 missing - required per contract research
            param2={"key": "value"}
        )

    # Test invalid parameter type (from contract research)
    with pytest.raises(ValueError, match="Invalid type"):
        node = NodeClass()
        node.execute(
            param1="valid_string",
            param2="invalid_string"  # Should be dict per contract
        )

    # Test business logic error (from contract research)
    node = NodeClass()
    result = node.execute(
        param1="valid",
        param2={"trigger": "business_error"}
    )

    # Verify error structure from contract research
    assert result["result"]["success"] is False  # NOT "valid"
    assert "error" in result["result"]
    assert "error_code" in result["result"]
```

## ✅ Checklist: Before Writing Any Test

**Print this checklist and check off each item BEFORE writing test code:**

### 📚 Research Phase

- [ ] ✅ **Contract Reference**: Checked CUSTOM_NODE_CONTRACT_REFERENCE.md for all nodes
- [ ] ✅ **Parameter Contracts**: Read actual contract classes in contracts/parameter_contracts.py
- [ ] ✅ **Node Implementation**: Checked run() method return structure in node files
- [ ] ✅ **Connection Contracts**: Identified connection parameter requirements for SecureGovernedNode
- [ ] ✅ **Parameter Method**: Selected method per GOLD_STANDARD_PARAMETER_PASSING_COMPREHENSIVE.md
- [ ] ✅ **Existing Tests**: Found and studied similar working test patterns

### 🏗️ Planning Phase

- [ ] ✅ **Required Parameters**: Listed all required parameters with types
- [ ] ✅ **Optional Parameters**: Listed all optional parameters with defaults
- [ ] ✅ **Output Structure**: Documented expected output structure with field names
- [ ] ✅ **Connection Flow**: Mapped all connections with exact field paths
- [ ] ✅ **Error Prevention**: Checked common error patterns for these nodes

### 💻 Implementation Phase

- [ ] ✅ **Parameter Construction**: Built parameters from contract research
- [ ] ✅ **Method Implementation**: Used selected parameter passing method correctly
- [ ] ✅ **Connection Setup**: Used exact connection paths from research
- [ ] ✅ **Assertion Planning**: Planned assertions using researched output structure

### ✨ Validation Phase

- [ ] ✅ **Contract Compliance**: All assertions use researched field names
- [ ] ✅ **Type Validation**: All type checks match contract specifications
- [ ] ✅ **Error Handling**: Error scenarios test actual contract validation
- [ ] ✅ **Pattern Consistency**: Test follows established patterns from similar tests

---

## 🎯 Success Metrics

**Test Creation is successful when:**

1. ✅ **Zero parameter errors** - All parameters are correct on first attempt
2. ✅ **Zero assertion errors** - All output field references are correct
3. ✅ **Zero type errors** - All parameter types match contracts
4. ✅ **Zero connection errors** - All connection paths work as expected
5. ✅ **Consistent patterns** - Test follows established codebase patterns

**Quality Indicators:**

- Test passes on first run without parameter adjustments
- Assertions use exact field names from node implementation
- All required parameters provided, optional parameters handled properly
- Error scenarios test actual contract validation rules
- Code reviewer can understand test logic from contract references

---

**Remember**: Time spent on systematic research prevents hours of debugging parameter errors!

**Usage**: Follow this guide step-by-step for every new test to eliminate the "parameter error cycle" and create reliable, maintainable test cases.
