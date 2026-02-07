> **HISTORICAL DOCUMENT — RESEARCH**
>
> This research was conducted as part of the IP strategy development process (February 2026).
> The research informed the final decision to adopt pure Apache 2.0 rather than a custom
> license. On 6 February 2026, the Board decided on unconditional Apache 2.0 donation to
> OCEAN Foundation. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 02 - n8n License Evolution Case Study

## Document Purpose

Detailed case study of n8n's licensing journey, serving as the primary precedent for Kailash's licensing decision.

## Why n8n Is the Key Precedent

n8n is the most relevant precedent for Kailash because:

1. Both are **workflow automation platforms** with node-based architectures
2. Both started with **Apache 2.0 + commercial restrictions**
3. n8n's founder is a **key figure in the fair-code movement**
4. n8n successfully transitioned to a recognized fair-code license
5. n8n has proven the model works commercially (raised $50M+ in funding)

## Timeline

### Phase 1: Apache 2.0 + Commons Clause (June 2019 - March 2022)

**Initial Choice:**
n8n launched with Apache License 2.0 combined with the Commons Clause addendum. This is structurally identical to what Kailash has today (Apache 2.0 + custom commercial restrictions).

**Problems Encountered:**

1. **Ambiguity**: The Commons Clause language was open to interpretation
2. **Over-restriction**: It inadvertently blocked consulting and support services
3. **User confusion**: People saw "Apache 2.0" and assumed standard open-source terms
4. **Not formally fair-code**: While philosophically aligned, the specific combination wasn't on faircode.io's list

**Specific Issues:**

- The Commons Clause restricted the ability to "sell" the software
- "Sell" was interpreted broadly, potentially blocking consulting fees
- Users were uncertain whether they could charge clients for building n8n workflows
- The "Apache 2.0" branding made users assume fewer restrictions existed

### Phase 2: Sustainable Use License (March 17, 2022 - Present)

**The Switch:**
n8n wrote and adopted the Sustainable Use License (SUL), a purpose-built fair-code license.

**Key Changes from Previous License:**

| Aspect                    | Apache 2.0 + Commons Clause | Sustainable Use License              |
| ------------------------- | --------------------------- | ------------------------------------ |
| Clarity of terms          | Ambiguous ("sell")          | Clear ("internal business purposes") |
| Consulting/support        | Inadvertently restricted    | Explicitly permitted                 |
| Internal business use     | Permitted but unclear       | Explicitly permitted                 |
| Commercial redistribution | Blocked                     | Blocked                              |
| License recognition       | Not formally fair-code      | Listed on faircode.io                |
| Legal precedent           | Untested combination        | Purpose-built, growing precedent     |

**Why They Made Their Own License:**

1. No existing license perfectly matched their needs
2. They wanted clearer language than Commons Clause
3. They needed to explicitly permit consulting services
4. They wanted to be listed on faircode.io as a compatible license

### Current License Structure

**Dual License Model:**

| License                 | Applies To                           | Terms                                         |
| ----------------------- | ------------------------------------ | --------------------------------------------- |
| Sustainable Use License | All code except `.ee` files          | Free for internal/personal/non-commercial use |
| n8n Enterprise License  | Files with `.ee` in filename/dirname | Requires commercial agreement                 |

**SUL Key Terms:**

- **Granted rights**: Non-exclusive, royalty-free, worldwide license to use, copy, distribute, make available, and prepare derivative works
- **Use restriction**: Only for internal business purposes, non-commercial, or personal use
- **Distribution restriction**: Only free of charge for non-commercial purposes
- **Attribution**: Must pass license terms to recipients
- **Termination**: Auto-terminates on violation, 30-day cure period after notice

## Lessons for Kailash

### Direct Parallels

| n8n's Journey                            | Kailash's Current Position                                 |
| ---------------------------------------- | ---------------------------------------------------------- |
| Started with Apache 2.0 + Commons Clause | Currently using Apache 2.0 + Additional Terms              |
| Users confused by "Apache 2.0" branding  | PyPI classifier says "OSI Approved :: Apache"              |
| Commons Clause language was ambiguous    | Additional Terms use undefined "substantial"               |
| Consulting restriction was unintended    | Current terms may inadvertently restrict service providers |
| Not recognized as fair-code              | Not recognized as fair-code                                |
| Moved to purpose-built license           | Decision pending                                           |

### Key Takeaways

1. **The "Apache 2.0 + addendum" model doesn't work long-term** - n8n proved this through 3 years of experience
2. **Clarity is worth the transition cost** - A purpose-built license removes ambiguity
3. **Fair-code recognition matters** - Being on faircode.io provides legitimacy and discovery
4. **Consulting must be explicitly permitted** - SDK users need to know they can build commercial services
5. **Dual licensing works** - SUL for community + Enterprise License for commercial generates revenue
6. **The transition didn't kill the community** - n8n grew significantly after the license change

## SUL vs. Kailash's Specific Needs

| SUL Term                              | Kailash Consideration                                                                  |
| ------------------------------------- | -------------------------------------------------------------------------------------- |
| "Internal business purposes"          | May not clearly cover using Kailash as a component in a product (Kailash's Section 2a) |
| No mention of patent rights           | Kailash needs explicit patent grant clause                                             |
| No hosted service restriction         | Kailash needs this (DataFlow-as-a-Service threat)                                      |
| 30-day cure period                    | Reasonable, could adopt                                                                |
| No attribution beyond license passing | Kailash currently requires more (Section 4)                                            |

## Conclusion

n8n's journey from Apache 2.0 + Commons Clause to the Sustainable Use License is the closest available precedent for Kailash. The key insight is that the "Apache 2.0 + addendum" approach was a reasonable starting point but proved inadequate for clarity, community trust, and fair-code recognition. Kailash is at exactly the decision point n8n was at in early 2022.

## Sources

- [Announcing the new Sustainable Use License - n8n Blog](https://blog.n8n.io/announcing-new-sustainable-use-license/)
- [Sustainable Use License - n8n Docs](https://docs.n8n.io/sustainable-use-license/)
- [n8n LICENSE.md on GitHub](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)
- [Fair-code license - n8n Docs](https://docs.n8n.io/faircode-license/)
