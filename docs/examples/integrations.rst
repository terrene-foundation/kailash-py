.. _examples-integrations:

=====================
Integration Examples
=====================

This section shows how to integrate the Kailash Python SDK with external systems.

SharePoint Integration
----------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.data import SharePointGraphReader, CSVWriterNode
   from kailash.runtime.local import LocalRuntime
   import os

   # Create workflow
   workflow = Workflow("sharepoint_integration", name="SharePoint Integration")

   # Configure SharePoint reader
   sharepoint = SharePointGraphReader()
   csv_writer = CSVWriterNode(file_path="sharepoint_files.csv")

   workflow.add_node("read_sharepoint", sharepoint)
   workflow.add_node("save_csv", csv_writer)
   workflow.connect("read_sharepoint", "save_csv")

   # Execute with credentials
   inputs = {
       "read_sharepoint": {
           "tenant_id": os.getenv("SHAREPOINT_TENANT_ID"),
           "client_id": os.getenv("SHAREPOINT_CLIENT_ID"),
           "client_secret": os.getenv("SHAREPOINT_CLIENT_SECRET"),
           "site_url": "https://company.sharepoint.com/sites/MyTeam",
           "operation": "list_files",
           "library_name": "Documents"
       }
   }

   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow, inputs=inputs)

API Integration
---------------

See the `integration examples <https://github.com/terrene-foundation/kailash-py/tree/main/examples/integration_examples>`_ for more API integration patterns.
