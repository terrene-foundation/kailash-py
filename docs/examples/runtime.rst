:orphan:

.. _examples-runtime:


Runtime Examples
================

This section demonstrates different runtime options available in the Kailash Python SDK.

Local Runtime
-------------

.. code-block:: python

   from kailash.runtime.local import LocalRuntime

   runtime = LocalRuntime(debug=True)
   results, run_id = runtime.execute(workflow)

Parallel Runtime
----------------

.. code-block:: python

   from kailash.runtime.parallel import ParallelRuntime

   runtime = ParallelRuntime(max_workers=4)
   results, run_id = runtime.execute(workflow)

For more runtime examples, see the repository.
