# Integration Workflow Tests Migration Plan

## Overview
The files in `tests/integration/workflows/` are mostly workflow examples, not integration tests. They need to be migrated to appropriate directories.

## Migration Plan

### To `sdk-users/workflows/by-pattern/`
- **ETL Pattern**:
  - basic_workflow_test.py → etl/basic_etl_workflow.py ✅
  - csv_python_test.py → etl/csv_data_processing.py
  - data_transformation_test.py → etl/data_transformation_workflow.py

- **Control Flow Pattern**:
  - conditional_routing_test.py → control-flow/conditional_routing_examples.py
  - conditional_workflow_test.py → control-flow/switch_merge_workflow.py
  - switch_node_test.py → control-flow/simple_switch_example.py

- **Parallel Processing Pattern**:
  - parallel_execution_test.py → parallel/async_parallel_workflow.py

- **Error Handling Pattern**:
  - error_handling_test.py → error-handling/workflow_error_handling.py
  - comprehensive_error_testing.py → error-handling/cycle_error_validation.py

- **State Management Pattern**:
  - state_management_test.py → state/simple_state_workflow.py
  - task_tracking_test.py → state/task_tracking_example.py

- **Advanced Patterns**:
  - complex_workflow_test.py → advanced/multi_node_analysis_workflow.py
  - nested_composition_test.py → advanced/hierarchical_workflow_composition.py
  - cycle_aware_nodes_test.py → cyclic/cycle_aware_enhancements.py
  - cyclic_examples_test.py → cyclic/phase1_cyclic_demonstrations.py

### To `examples/feature_examples/workflows/`
- comprehensive_test.py → comprehensive_workflow_demo.py
- general_workflow_test.py → general_workflow_example.py
- direct_comparison_test.py → execution_comparison_demo.py
- runtime_integration_test.py → runtime_integration_examples.py
- external_inputs_test.py → external_inputs_example.py
- export_test.py → workflow_export_example.py
- task_list_test.py → task_manager_list_example.py
- test_exception_handling.py → exception_handling_demo.py

## True Integration Tests to Keep/Create
Need to create proper integration tests in `tests/integration/` that:
1. Test component interactions (nodes ↔ runtime ↔ workflow)
2. Test error propagation across components
3. Test data flow between different node types
4. Test runtime behavior with different workflow patterns
5. Test security and access control integration
6. Test async node execution in workflows

## Action Items
1. ✅ Migrate basic_workflow_test.py
2. Continue migrating other workflow examples
3. Create proper integration tests
4. Remove workflow examples from test directory
5. Update test documentation
