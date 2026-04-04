# CONNECTION: MCP Tool Generation (#250) + Consumer Adapters (#244) Are Complementary

Both extend how products are consumed:

- #244 (consumer adapters): Multiple data views of same product (REST endpoint variations)
- #250 (MCP tools): Auto-generate MCP tool definitions from product registrations

Together they enable: one `@db.product()` definition → multiple REST views + auto-generated MCP tools. This is the "write once, serve everywhere" pattern.

Implementation synergy: both hook into FabricServingLayer and ProductRegistration. Consider coordinating API design so consumers and MCP tools use consistent registration patterns.
