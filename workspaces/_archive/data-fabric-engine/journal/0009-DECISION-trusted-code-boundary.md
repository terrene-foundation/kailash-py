---
type: DECISION
date: 2026-04-02
created_at: 2026-04-02T18:35:00+08:00
author: co-authored
session_turn: 11
project: data-fabric-engine
topic: Product functions are trusted code — depends_on controls refresh, not access
phase: analyze
tags: [security, trust-boundary, product-functions, design-decision]
---

# Decision: Product Functions Are Trusted Code

## Context

Security review flagged that `@db.product()` functions have unrestricted access — they can read any source, access `os.environ`, import arbitrary modules. The question: should `depends_on` be an access control mechanism (hard block on undeclared sources) or a refresh control mechanism (only controls when products auto-refresh)?

## Decision

**Trusted code. `depends_on` controls refresh, not access.**

Product functions are written by the application developer — the same person who writes `@app.handler()`, has SSH access to the server, and manages the database credentials. Restricting their access to sources would add complexity without security benefit — they could bypass it trivially by importing httpx directly.

`depends_on` serves ONE purpose: telling the fabric which products to refresh when a source changes. If a product accesses a source not in `depends_on`, it works — but the product won't auto-refresh when that source changes. A runtime warning helps the developer catch missed declarations.

## Alternatives Considered

**Hard access control**: `ctx.source("undeclared")` raises `PermissionError`. Rejected because: (1) the developer can bypass it by calling the source directly, (2) it creates false security — the real attack surface is the server process, not the product function, (3) it punishes legitimate use cases like optional data enrichment.

## For Discussion

1. If the fabric later supports tenant-provided product functions (plugins, marketplace), this decision must be revisited. But that is a different product, not the current one.
2. Should the warning for undeclared source access be configurable to an error for strict teams? `@db.product("x", depends_on=["a"], strict_depends=True)` → error on undeclared access.
