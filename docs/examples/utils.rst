:orphan:

.. _examples-utils:

================
Utility Examples
================

This section shows examples of using utility functions and helpers.

Workflow Export
---------------

.. code-block:: python

   from kailash.utils.export import WorkflowExporter
   
   exporter = WorkflowExporter()
   
   # Export to YAML
   workflow.save("my_workflow.yaml", format="yaml")
   
   # Export to JSON
   workflow.save("my_workflow.json", format="json")

Template Usage
--------------

.. code-block:: python

   from kailash.utils.templates import WorkflowTemplates
   
   # Create from template
   workflow = WorkflowTemplates.create_data_pipeline(
       name="my_pipeline",
       source="data.csv",
       destination="output.csv"
   )