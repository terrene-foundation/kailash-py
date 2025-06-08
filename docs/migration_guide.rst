.. _migration-guide:


Migration Guide
===============

This guide helps you migrate from earlier versions of the Kailash Python SDK.

.. note::
   This migration guide is under development. As the SDK is currently at version 0.1.x,
   there are no prior versions to migrate from. This page will be updated when
   breaking changes are introduced in future versions.

Version Compatibility
---------------------

The current version of the Kailash Python SDK is **0.1.7-dev** (Unreleased).

- **Python Support**: Requires Python 3.11 or higher
- **Dependencies**: All dependencies are managed through `pyproject.toml`

What's New in 0.1.7
-------------------

**Universal Hybrid Cyclic Graph Architecture**

The SDK now supports cyclic workflows for iterative processing:

- New ``CycleAwareNode`` base class with helper methods
- ``Workflow.connect()`` supports ``cycle=True`` parameter
- Automatic cycle detection and validation
- Built-in convergence detection
- Performance optimized (~30,000 iterations/second)

**Migration Steps for Cyclic Workflows:**

1. **Using CycleAwareNode**: Inherit from ``CycleAwareNode`` instead of ``Node`` for cycle support
2. **Marking Cycles**: Use ``cycle=True`` in ``connect()`` for the closing edge only
3. **Convergence**: Always set ``convergence_check`` or return a convergence flag
4. **State Management**: Use the provided helper methods for state tracking

Example migration:

.. code-block:: python

   # Old approach (manual iteration tracking)
   class IterativeNode(Node):
       def __init__(self):
           self.iteration = 0
           self.state = {}

       def run(self, context, **kwargs):
           self.iteration += 1
           # Manual state management

   # New approach (using CycleAwareNode)
   class IterativeNode(CycleAwareNode):
       def run(self, context, **kwargs):
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)
           # Automatic state management

Future Migration Notes
----------------------

When migrating between versions in the future, this guide will cover:

- API changes and deprecations
- Configuration file format updates
- Node interface changes
- Workflow format changes
- Runtime behavior changes

Best Practices for Future-Proofing
----------------------------------

To minimize migration effort in future versions:

1. **Use Type Hints**: Always specify types for better compatibility checking
2. **Pin Dependencies**: Use specific version ranges in your requirements
3. **Test Coverage**: Maintain good test coverage to catch breaking changes
4. **Follow SDK Patterns**: Use documented patterns and avoid internal APIs

Getting Help
------------

If you need help with migration:

- Check the `GitHub Issues <https://github.com/terrene-foundation/kailash-py/issues>`_
- Review the `CHANGELOG <https://github.com/terrene-foundation/kailash-py/blob/main/CHANGELOG.md>`_
- Contact support at support@terrene.foundation
