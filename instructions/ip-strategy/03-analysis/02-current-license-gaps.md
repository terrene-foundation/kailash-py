> **HISTORICAL DOCUMENT — ANALYSIS**
>
> This analysis was prepared during the IP strategy development process (February 2026).
> The gaps and risks identified here informed the final decision. On 6 February 2026, the
> Board decided to adopt pure Apache 2.0 rather than addressing these gaps with a custom
> license. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 02 - Current License Gap Analysis

## Document Purpose

Detailed analysis of gaps and risks in the current "Apache 2.0 with Additional Terms" license.

## Critical Gaps

### Gap 1: Hosted Service Vulnerability (CRITICAL)

**Current state**: The Additional Terms prohibit "standalone commercial distribution" but do not address hosted/managed services.

**Risk**: A competitor could:

1. Take the Kailash SDK source code
2. Deploy it as "Kailash-as-a-Service" or "DataFlow Cloud"
3. Charge customers for access
4. Argue they are "providing services that use the Software without distributing it" (which is explicitly PERMITTED under Section 2d)

**Impact**: This is the exact scenario that drove MongoDB to create SSPL, Elastic to create ELv2, and n8n to create SUL. It is the most commercially dangerous gap.

**Affected frameworks**:

- DataFlow: Could be offered as a managed database service
- Nexus: Could be offered as a managed API platform
- Kaizen: Could be offered as a managed AI agent platform

### Gap 2: Misleading OSI Classifier (HIGH)

**Current state**: All `setup.py` files declare `"License :: OSI Approved :: Apache Software License"`

**Risk**:

- Users install from PyPI expecting standard Apache 2.0 terms
- Discovery of additional restrictions after adoption creates trust issues
- Potential trademark misuse claim from OSI
- Legal uncertainty if a dispute arises ("I relied on the PyPI listing")

**Impact**: Reputational and legal risk. Every day this remains uncorrected increases exposure.

### Gap 3: No Patent Reference (HIGH)

**Current state**: The license does not mention PCT/SG2024/050503 or any patent rights.

**Risk**:

- Users don't know they have a patent license (via Apache 2.0 Section 3)
- The patent grant from Apache 2.0 Section 3 may be undermined by the Additional Terms' precedence clause
- No defensive termination is clearly tied to the specific Kailash patent
- Enterprise customers don't see the patent protection value

**Impact**: Misses the commercial value of the patent and may create ambiguity about patent rights.

### Gap 4: Ambiguous "Substantial" Criteria (MEDIUM)

**Current state**: Section 3 defines "substantial new functionality" with subjective criteria:

- "Add significant features not present in the original Software"
- "meaningful domain-specific enhancements"

**Risk**:

- "Significant" and "meaningful" are undefined
- A competitor could argue minimal changes constitute "substantial modification"
- Enforcement would require litigation to define the terms
- Creates uncertainty for legitimate derivative work creators

**Impact**: Legal ambiguity reduces both enforcement capability and user confidence.

### Gap 5: Missing Kaizen LICENSE File (MEDIUM)

**Current state**: `apps/kailash-kaizen/` has no LICENSE file; relies on root repository license.

**Risk**:

- PyPI distributions may not include the root LICENSE
- Users installing only `kailash-kaizen` may not see the license terms
- Some package managers require a LICENSE file per package

**Impact**: Distributing software without clear license terms creates legal uncertainty.

### Gap 6: Apache 2.0 Patent Grant Ambiguity (MEDIUM)

**Current state**: Apache 2.0 Section 3 includes a patent grant. The Additional Terms include a precedence clause: "In case of any conflict... these Additional Terms shall prevail."

**Risk**: If the Additional Terms are interpreted as conflicting with the patent grant (e.g., by restricting commercial use of the patented method), the patent grant could be partially invalidated for commercial users.

**Impact**: Users may not have clear patent rights, undermining the defensive value of the patent grant.

## Gap Priority Matrix

| Gap                          | Severity | Likelihood | Effort to Fix           | Priority |
| ---------------------------- | -------- | ---------- | ----------------------- | -------- |
| Hosted service vulnerability | Critical | High       | License change required | 1        |
| Misleading OSI classifier    | High     | Certain    | Trivial (config change) | 2        |
| No patent reference          | High     | Certain    | License change required | 3        |
| Ambiguous "substantial"      | Medium   | Medium     | License change required | 4        |
| Missing Kaizen LICENSE       | Medium   | Medium     | Trivial (copy file)     | 5        |
| Patent grant ambiguity       | Medium   | Low        | License change required | 6        |

## Conclusion

Four of the six gaps require a license change to address. The PyPI classifier and missing Kaizen LICENSE can be fixed immediately regardless of the license decision. The hosted service gap is the most commercially dangerous and should drive the urgency of the license transition.
