> **HISTORICAL DOCUMENT**
>
> This background analysis was prepared as part of the IP strategy development process
> (February 2026). On 6 February 2026, the decision was made to adopt pure Apache 2.0
> licensing and donate all platform assets to OCEAN Foundation. See `DECISION-MEMORANDUM.md`
> and `07-foundation/` for the final strategy.

# 01 - Current License Analysis

## Document Purpose

Analysis of the current licensing state of the Kailash Python SDK and all framework packages.

## License Type

**Apache License 2.0 with Additional Terms**

- Copyright: 2025 Terrene Foundation
- Base: Standard Apache License 2.0 (Sections 1-14)
- Custom: Additional Terms and Conditions (appended after Section 14)

## Packages Covered

| Package            | Version | License File Present                   | pyproject.toml Declaration         |
| ------------------ | ------- | -------------------------------------- | ---------------------------------- |
| kailash (Core SDK) | 0.10.16 | Yes (`/LICENSE`)                       | `Apache-2.0 WITH Additional-Terms` |
| kailash-dataflow   | 0.10.16 | Yes (`/apps/kailash-dataflow/LICENSE`) | `Apache-2.0 WITH Additional-Terms` |
| kailash-nexus      | 1.1.3   | Yes (`/apps/kailash-nexus/LICENSE`)    | `Apache-2.0 WITH Additional-Terms` |
| kailash-kaizen     | 1.0.1   | **No** (inherits from root)            | `Apache-2.0 WITH Additional-Terms` |

## Additional Terms (Full Text)

The Additional Terms appended to the Apache 2.0 base license contain four sections:

### Section 1: Prohibition on Standalone Commercial Distribution

> The Software may not be sold, licensed, or distributed on a standalone basis for commercial purposes. This includes, but is not limited to:
>
> - Selling the unmodified Software as a product
> - Repackaging the Software with only cosmetic changes
> - Offering the Software as-is through commercial channels

### Section 2: Permitted Uses

> The above restriction does NOT apply to:
> a) Using the Software as a component of a larger application or service
> b) Creating and distributing Derivative Works that add substantial new functionality beyond the original Software
> c) Using the Software internally within an organization
> d) Providing services that use the Software without distributing it
> e) Educational and non-commercial research use

### Section 3: Substantial Modification Criteria

> For the purpose of these Additional Terms, "substantial new functionality" means modifications that:
>
> - Add significant features not present in the original Software
> - Integrate the Software into a larger system as a component
> - Adapt the Software for a specific industry or use case with meaningful domain-specific enhancements

### Section 4: Attribution for Derivative Works

> Any distribution of Derivative Works must:
>
> - Clearly indicate the modifications made
> - Not imply endorsement by the original authors
> - Maintain the copyright notice and license information

### Precedence Clause

> These Additional Terms are supplementary to, and do not replace or modify, the Apache License 2.0 terms above. In case of any conflict between these Additional Terms and the Apache License 2.0, these Additional Terms shall prevail only to the extent of such conflict.

## PyPI Classifier Issue

All `setup.py` files across all four packages declare:

```
"License :: OSI Approved :: Apache Software License"
```

**This is inaccurate.** The additional commercial restrictions violate the Open Source Definition (specifically, Clause 6: "No Discrimination Against Fields of Endeavor"). The license is _based on_ Apache 2.0 but is not a standard OSI-approved Apache 2.0 license. This creates a risk of:

- User confusion (assuming standard Apache 2.0 terms)
- Potential legal claims of misrepresentation
- Incompatibility with OSI's trademark on "Open Source"

## Gaps Identified

1. **Missing LICENSE in Kaizen**: `apps/kailash-kaizen/` does not have its own LICENSE file
2. **Misleading PyPI classifier**: All packages incorrectly claim OSI approval
3. **No patent reference**: License does not mention the PCT patent application
4. **Hosted service gap**: No restriction on running Kailash as a managed/hosted service
5. **Ambiguous patent grant**: Apache 2.0 Section 3 contains a patent grant, but the Additional Terms may create ambiguity about its scope
6. **Custom/untested terms**: The Additional Terms have no legal precedent and have not been judicially tested

## Source Files Referenced

- `/LICENSE` (lines 203-244 for Additional Terms)
- `/pyproject.toml` (line 13)
- `/apps/kailash-dataflow/pyproject.toml` (line 10)
- `/apps/kailash-dataflow/setup.py` (line 19)
- `/apps/kailash-nexus/pyproject.toml` (line 11)
- `/apps/kailash-nexus/setup.py` (line 11)
- `/apps/kailash-kaizen/pyproject.toml` (line 11)
- `/apps/kailash-kaizen/setup.py` (line 19)
