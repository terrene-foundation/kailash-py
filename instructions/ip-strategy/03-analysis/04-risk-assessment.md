> **HISTORICAL DOCUMENT — ANALYSIS**
>
> This analysis was prepared during the IP strategy development process (February 2026).
> The gaps and risks identified here informed the final decision. On 6 February 2026, the
> Board decided to adopt pure Apache 2.0 rather than addressing these gaps with a custom
> license. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 04 - Risk Assessment

## Document Purpose

Identification and assessment of risks associated with each strategic option.

## Risk Matrix

### Risk 1: License Transition Disrupts Community

**Description**: Changing from Apache 2.0-based license to a new license could alarm existing users.

**Probability**: Medium
**Impact**: Medium
**Mitigation**:

- Communicate the change transparently (blog post, GitHub notice)
- Emphasize what DOESN'T change (free for internal use, consulting, component use)
- Emphasize what IMPROVES (clarity, patent protection for users)
- Follow n8n's precedent (their community grew after the change)
- Give advance notice (30-60 days before effective date)

**Residual risk**: Low (n8n proved transitions work if communicated well)

### Risk 2: Patent Application Rejected

**Description**: Despite favorable IPRP signals, national phase applications could face additional objections.

**Probability**: Low-Medium (favorable IPRP significantly reduces risk)
**Impact**: Medium (reduces commercial leverage but doesn't affect license)
**Mitigation**:

- IPRP findings carry weight in national examinations
- Amended claims address prior examiner's concerns
- Technical claims (metadata transformation) have strong patentability arguments
- Use PPH/ASPEC to leverage favorable IPRP across jurisdictions

**Residual risk**: Low (novelty already conceded; inventive step well-argued)

### Risk 3: Competitor Files Blocking Patent

**Description**: A competitor patents a variation of the data fabric architecture before Kailash's national grants.

**Probability**: Low (PCT provides priority)
**Impact**: High (could block market access)
**Mitigation**:

- PCT priority date establishes prior art
- File national phases promptly after favorable IPRP
- The published PCT application itself serves as prior art against later filers
- Monitor competitor patent filings in the workflow automation space

**Residual risk**: Very Low (PCT priority provides strong protection)

### Risk 4: Alice Corp Rejection in US

**Description**: USPTO rejects claims under 35 U.S.C. 101 (abstract idea).

**Probability**: Medium (software patents face heightened scrutiny)
**Impact**: Medium (loses US patent but retains others)
**Mitigation**:

- Claims emphasize technical architecture, not business method
- IPRP finding of novelty supports "inventive concept" under Step 2
- Engage US-experienced patent counsel for prosecution
- Prepare claims amendments emphasizing technical implementation details
- Consider continuation application with narrower technical claims if needed

**Residual risk**: Medium (Alice remains unpredictable)

### Risk 5: Fair-Code License Not Enforced

**Description**: A party violates the license (e.g., offers hosted service) and Terrene Foundation cannot effectively enforce.

**Probability**: Low
**Impact**: Medium
**Mitigation**:

- Patent provides independent enforcement mechanism (even if license isn't enforced, patent can be)
- Use recognized license with judicial precedent (ELv2 preferred over custom)
- Clear, unambiguous terms reduce litigation risk
- Enterprise licensing creates incentive to comply (cheaper than litigation)

**Residual risk**: Low (patent + license = dual enforcement path)

### Risk 6: Enterprise Customers Avoid Fair-Code

**Description**: Large enterprises avoid fair-code software due to compliance concerns.

**Probability**: Medium (enterprise legal teams are conservative)
**Impact**: Medium (reduces enterprise adoption)
**Mitigation**:

- Enterprise license explicitly resolves all restrictions
- Patent indemnification addresses enterprise IP concerns
- Clear dual-license structure (community vs. enterprise) is well-understood
- Precedent: n8n, Elastic, MongoDB all have enterprise customers under similar models

**Residual risk**: Low-Medium (some enterprises will always prefer pure OSI licenses)

### Risk 7: Patent Grant Clause Interpreted Too Broadly

**Description**: The patent grant clause in the fair-code license is interpreted as waiving more patent rights than intended.

**Probability**: Low
**Impact**: Medium
**Mitigation**:

- Carefully scope grant to "necessarily infringed by the Software as provided"
- Exclude modifications, combinations, and derivative works from grant
- Have patent attorney review clause language
- Include explicit scope limitation section

**Residual risk**: Very Low (with proper drafting)

### Risk 8: National Phase Deadline Missed

**Description**: Failure to file national phase entries before the 30/31-month deadline.

**Probability**: Very Low (deadline is known and tracked)
**Impact**: Critical (permanent loss of patent rights in missed jurisdictions)
**Mitigation**:

- Track deadline explicitly (estimated early-mid 2026)
- Instruct Auriga IP to calendar the deadline
- Prioritize SG and US filings as soon as IPRP is received
- Have budget allocated in advance

**Residual risk**: Very Low (with proper project management)

## Aggregate Risk Assessment

| Strategic Action      | Risk Level | Key Mitigant                              |
| --------------------- | ---------- | ----------------------------------------- |
| License transition    | Low        | n8n precedent + transparent communication |
| Patent prosecution    | Low-Medium | Favorable IPRP + strong claims            |
| US filing (Alice)     | Medium     | Technical claims + experienced counsel    |
| Enterprise licensing  | Low-Medium | Dual-license model is proven              |
| Patent grant clause   | Very Low   | Careful legal drafting                    |
| National phase timing | Very Low   | Calendar management                       |

## Overall Assessment

The proposed strategy (fair-code license + patent + patent grant + enterprise license) has a **low aggregate risk profile**. The highest individual risk (Alice Corp in US) is jurisdiction-specific and does not affect the overall strategy. All other risks have well-established mitigations with precedent.

**Recommendation**: Proceed with the integrated strategy. The risks of inaction (hosted service vulnerability, misleading classifier, lost patent value) exceed the risks of action.
