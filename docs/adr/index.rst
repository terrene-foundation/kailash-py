Architecture Decision Records
=============================

This directory contains Architecture Decision Records (ADRs) that document significant architectural decisions made during the development of the Kailash Python SDK.

.. toctree::
   :maxdepth: 1
   :caption: ADRs

   README
   0017-llm-provider-architecture
   0017-multi-workflow-api-architecture
   0018-http-rest-client-architecture

What is an ADR?
---------------

An Architecture Decision Record (ADR) captures an important architectural decision made along with its context and consequences. ADRs help team members understand:

- Why certain decisions were made
- What alternatives were considered
- What the trade-offs are
- How to evolve the architecture

ADR Format
----------

Each ADR follows this structure:

1. **Title**: Short descriptive title
2. **Status**: Draft, Proposed, Accepted, Deprecated, or Superseded
3. **Context**: The issue motivating this decision
4. **Decision**: The change we're proposing or have agreed to implement
5. **Consequences**: What becomes easier or harder as a result

Contributing
------------

To propose a new architectural decision:

1. Create a new ADR file following the naming pattern: ``NNNN-title-with-dashes.md``
2. Use the next available number in sequence
3. Follow the standard ADR format
4. Submit a pull request for review
