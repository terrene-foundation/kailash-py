# Foundation Independence — rs Variant Extended Reference

Companion reference for `.claude/variants/rs/rules/independence.md`. Boundary table, extended examples, BLOCKED rationalizations, and cross-references to sibling rules. The variant rule keeps the load-bearing MUST clauses + minimal DO/DO-NOT pairs + one-line Why; this file holds the rest so the always-loaded baseline stays under its per-CLI byte cap.

## The Boundary

| Layer               | Owner                              | License                                                   |
| ------------------- | ---------------------------------- | --------------------------------------------------------- |
| **Open standards**  | Terrene Foundation (Singapore CLG) | CC BY 4.0 (CARE, PACT, EATP, CO)                          |
| **Open-source SDK** | Terrene Foundation (Singapore CLG) | Apache 2.0 (`kailash-py`, `pact`)                         |
| **This product**    | Product team (proprietary)         | `LicenseRef-Proprietary`, trade secret, `publish = false` |

## Key facts (in full)

1. **This repo is a proprietary product codebase.** Source is trade secret. Every crate has `publish = false` (except `kailash-plugin-macros` and `kailash-plugin-guest`, the only crates published to crates.io).
2. **The product ships a Python SDK** (`pip install kailash-enterprise`) built from Rust-backed bindings. The product is not the SDK — the SDK is what the product delivers.
3. **TF specs are upstream.** CARE, EATP, CO, PACT are CC BY 4.0. Any entity may implement them in any language under any license. This product does so in proprietary Rust. The TF projects do so in open-source Python. Neither has a structural relationship with the other.
4. **There is no special relationship.** This product is one of potentially many commercial implementations of TF standards. The Foundation has no knowledge of, dependency on, or design consideration for any specific commercial product — and this product makes no claim of endorsement, partnership, or preferred status.

## Rule 1 — Proprietary Identity Is Allowed Here

Unlike `kailash-py` (where commercial references are forbidden under TF independence), this repo is itself a commercial product. You MAY:

- Describe this product and its commercial context
- Reference the TF standards it implements
- Describe the SDK it ships (`kailash-enterprise`)

### Extended example

```markdown
# DO — accurate identity

This product ships kailash-enterprise, a Python SDK built from
Rust-backed bindings. It implements the Terrene Foundation's
open standards (CARE, PACT, EATP, CO) in proprietary code.

# DO NOT — claim Foundation ownership or endorsement

kailash-enterprise is a Terrene Foundation project. (It is not.)
This product is the Foundation's official commercial implementation. (There is no such thing.)
```

### Why (extended)

Misrepresenting proprietary code as a TF project violates the Foundation's anti-capture provisions and creates legal ambiguity.

## Rule 2 — TF Specs Are CC BY 4.0; Implementations Are Separate

This product MAY implement TF specs (CARE, EATP, CO, PACT) in proprietary code. The implementation is trade secret; the spec is CC BY 4.0 and remains owned by the Foundation. MUST NOT:

- Claim ownership of any TF spec
- Modify a TF spec without upstreaming through the Foundation's process
- Re-license a TF spec
- Claim that a product-only extension is part of the TF standard

### Extended example

```rust
// DO — implementation header
// Copyright 2026 [Product Entity] (proprietary)
// SPDX-License-Identifier: LicenseRef-Proprietary
// Implements EATP v1.0 (Terrene Foundation, CC BY 4.0).

// DO NOT — confused ownership
// Copyright 2026 Terrene Foundation
// SPDX-License-Identifier: Apache-2.0
// (Proprietary code with TF copyright is misrepresentation.)
```

### Why (extended)

Conflating spec ownership (TF) with implementation ownership (product) is the structural risk both sides must guard against.

## Rule 3 — Cross-Track References Must Be Generic

Docs MAY reference `kailash-py` and `pact` as TF open-source projects. The reference must be factual and MUST NOT imply a structural relationship, partnership, or paired-product framing.

### Extended example

```markdown
# DO — accurate, generic reference

The Terrene Foundation publishes open standards (CARE, PACT, EATP, CO)
and maintains open-source implementations in kailash-py and pact.
This product independently implements the same standards in Rust.

# DO NOT — paired-product framing

kailash-rs is the proprietary counterpart of kailash-py.
(This implies a structural relationship that does not exist.)

# DO NOT — endorsement framing

This product is officially paired with the Terrene Foundation's SDK.
(No such pairing exists.)
```

### Why (extended)

"Counterpart" and "paired" language implies a bilateral agreement. The accurate framing is: the standards are public, anyone can implement them, and multiple independent implementations exist.

## Rule 4 — Proprietary Code MUST NOT Be Claimed As TF Code

Marketing copy, README content, license headers, package metadata, and docs MUST never claim that any proprietary crate is "open source" or "Foundation-owned" or under "Apache 2.0". The `LicenseRef-Proprietary` SPDX identifier is mandatory; `Apache-2.0` is BLOCKED on every proprietary crate.

### Extended example

```toml
# DO — proprietary crate
[package]
name = "kailash-dataflow"
license = "LicenseRef-Proprietary"
publish = false

# DO NOT — false TF licensing
[package]
name = "kailash-dataflow"
license = "Apache-2.0"  # BLOCKED — this crate is proprietary
publish = true          # BLOCKED — would leak source to crates.io
```

### BLOCKED rationalizations

- "Apache 2.0 is more permissive, what's the harm?"
- "The crate is open-source-friendly even if internal"
- "We can re-license later"

### Why (extended)

A single mis-licensed Cargo.toml that says "Apache 2.0" on a proprietary crate, then gets published to crates.io, leaks the source under a license the company never agreed to. The mandatory `LicenseRef-Proprietary` + `publish = false` pair is the structural defense.

## Rule 5 — The Two Crates That ARE Open-Source

`kailash-plugin-macros` and `kailash-plugin-guest` are the only crates in this workspace that publish to crates.io. They MUST be Apache 2.0 OR MIT. They contain only the plugin SDK API surface needed by third-party plugin authors — no product runtime code, no proprietary algorithms.

### Extended example

```toml
# DO — plugin SDK is genuinely open source
[package]
name = "kailash-plugin-guest"
license = "Apache-2.0 OR MIT"
publish = true
```

### Why (extended)

Third-party plugin authors compile against `kailash-plugin-guest` to produce binaries that load into the product runtime. They cannot do this if the dependency is proprietary. The plugin SDK is a deliberate, narrow open-source carve-out — not a precedent for opening other crates.

## MUST NOT (extended)

- Apply the `kailash-py` Foundation independence rules verbatim to this repo

**Why:** Those rules forbid commercial product references entirely. This repo IS a commercial product; applying them creates contradictions agents cannot resolve. This variant rule replaces the global rule.

- Frame this product as having a special or bilateral relationship with the Terrene Foundation

**Why:** The Foundation's independence means no commercial entity has preferred status. Framing a "two-track" or "counterpart" relationship undermines that independence from both sides.

- Use "the SDK" to mean this product or this repo — the SDK is `kailash-enterprise`, what the product ships

**Why:** Conflating the product with its deliverable obscures the boundary between the proprietary codebase (trade secret, never published) and the distributed artifact (the Python package users install).

- Add Apache 2.0 license headers to proprietary source files

**Why:** Mixed-license source files create legal ambiguity and undermine the trade-secret status of the proprietary code.

## Relationship to other rules

- `rules/release.md` — enforces `publish = false` on every crate except the plugin SDK pair
- `rules/security.md` § "Source Protection" — covers what must NEVER be published
- `rules/terrene-naming.md` — the GLOBAL rule for naming TF entities, still applies for any reference TO TF projects from this repo
- `rules/eatp.md`, `rules/pact-governance.md` — apply to the EATP and PACT spec implementations in this repo (which are subject to trade-secret rules, NOT TF Apache 2.0 rules)
- `docs/00-authority/10-source-protection.md` — release auditor's reference for which crates are proprietary
