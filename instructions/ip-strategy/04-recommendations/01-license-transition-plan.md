> **PARTIALLY SUPERSEDED — RECOMMENDATIONS**
>
> These recommendations were prepared during the IP strategy development process (February
> 2026). The licensing recommendations (custom KSL v1.0) were superseded by the 6 February
> 2026 decision to adopt pure Apache 2.0. Patent filing recommendations remain valid and
> actionable. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the current strategy.

# 01 - License Transition Plan

## Document Purpose

Step-by-step plan for transitioning from Apache 2.0 with Additional Terms to a recognized fair-code license with integrated patent grant.

## Recommended License: Kailash Software License v1.0

Based on the analysis in `03-comparable-licenses.md`, the recommendation is a **custom license modeled on Elastic License 2.0** with additions from the Sustainable Use License and an integrated patent grant clause. The rationale for a custom license over adopting ELv2 directly:

1. ELv2's "license key" restriction is irrelevant to Kailash
2. SUL's "internal business purposes" language doesn't clearly cover SDK-as-component use
3. The patent grant clause is unique to Kailash and must be purpose-drafted
4. A custom license can explicitly address consulting, component use, and the specific Kailash use cases

## License Structure

### Kailash Software License v1.0

**Section 1: Grant of Rights**

- Use, copy, modify, create derivative works, redistribute
- Subject to limitations in Sections 2 and 3

**Section 2: Limitations**

- 2.1: You may not provide the Software to third parties as a hosted or managed service where the service provides users with access to any substantial set of the features or functionality of the Software
- 2.2: You may not move, change, disable, or circumvent the license key functionality in the Software, if any
- 2.3: You may not alter, remove, or obscure any licensing, copyright, or other notices of the Licensor in the Software

**Section 3: Permitted Uses (Explicit)**

- 3.1: Internal business use within your organization
- 3.2: Personal, educational, and non-commercial research use
- 3.3: Using the Software as a component within a larger application or system
- 3.4: Providing consulting, implementation, and support services to third parties using the Software
- 3.5: Creating and distributing derivative works that integrate the Software with substantial additional functionality

**Section 4: Patent Grant**

- 4.1: Grant of patent license for patents necessarily infringed by the Software
- 4.2: Defensive termination upon patent litigation against Licensor or community
- 4.3: Scope limitations (does not cover modifications or combinations)
- 4.4: Patent identification (PCT/SG2024/050503 and national entries)

**Section 5: Attribution**

- Maintain copyright notices
- Include license text in redistributions
- Do not imply endorsement

**Section 6: Termination**

- Auto-terminates on violation
- 30-day cure period after notice
- Patent termination immediate (no cure period for patent litigation)

**Section 7: Disclaimer and Limitation of Liability**

- Standard warranty disclaimer
- Limitation of liability

## Transition Steps

### Phase 1: Immediate Fixes (No License Change Required)

**Step 1.1**: Fix PyPI classifiers

- Change `"License :: OSI Approved :: Apache Software License"` to `"License :: Other/Proprietary License"` in all `setup.py` files
- Affected files:
  - `apps/kailash-dataflow/setup.py`
  - `apps/kailash-nexus/setup.py`
  - `apps/kailash-kaizen/setup.py`

**Step 1.2**: Add LICENSE to Kaizen

- Copy root `/LICENSE` to `apps/kailash-kaizen/LICENSE`

**Step 1.3**: Update pyproject.toml license declarations

- All packages should declare `license = {text = "Kailash Software License 1.0"}` (after license is finalized)

### Phase 2: License Drafting

**Step 2.1**: Draft Kailash Software License v1.0

- Use ELv2 as structural template
- Add patent grant section (Section 4)
- Add explicit permitted uses (Section 3)
- Add 30-day cure period from SUL
- Review by IP attorney (Auriga IP or dedicated licensing counsel)

**Step 2.2**: Draft Kailash Enterprise License

- Standard commercial license template
- Include patent indemnification clause
- Include hosted service rights
- Include trademark usage rights

**Step 2.3**: Legal review

- Auriga IP reviews patent grant clause for consistency with PCT claims
- Licensing counsel reviews fair-code compliance
- Verify registration eligibility with faircode.io

### Phase 3: Community Communication

**Step 3.1**: Draft announcement blog post

- Explain WHY the change is happening (clarity, protection for users)
- Explain WHAT changes (and what doesn't)
- Highlight the patent grant (users get MORE protection, not less)
- Reference n8n's successful transition as precedent

**Step 3.2**: Update repository

- Add LICENSING.md explaining the dual-license model
- Update README.md with license badge and brief explanation
- Add PATENTS file referencing PCT/SG2024/050503

**Step 3.3**: Give advance notice

- 30-day notice period before the new license takes effect
- GitHub issue/discussion for community questions
- FAQ document addressing common concerns

### Phase 4: Implementation

**Step 4.1**: Replace LICENSE files

- Replace `/LICENSE` with Kailash Software License v1.0
- Replace `/apps/kailash-dataflow/LICENSE` with Kailash Software License v1.0
- Replace `/apps/kailash-nexus/LICENSE` with Kailash Software License v1.0
- Create `/apps/kailash-kaizen/LICENSE` with Kailash Software License v1.0

**Step 4.2**: Update package metadata

- Update all `pyproject.toml` license declarations
- Update all `setup.py` classifiers
- Update all `setup.py` license fields

**Step 4.3**: Update documentation

- Update `/docs/license.rst`
- Add license page to documentation site
- Update CLAUDE.md references

**Step 4.4**: Register with faircode.io

- Submit Kailash Software License for listing
- Register Kailash SDK as a fair-code project

### Phase 5: Enterprise License Launch

**Step 5.1**: Create enterprise licensing page on website
**Step 5.2**: Define pricing tiers
**Step 5.3**: Create enterprise license agreement template
**Step 5.4**: Sales enablement materials highlighting patent value

## Rollback Plan

If the license transition encounters significant community pushback:

1. The old license can be reinstated for a specific version
2. The new license applies to new versions only
3. This is the same approach MongoDB and Elastic used

## Success Criteria

- [ ] All LICENSE files updated
- [ ] All package metadata updated
- [ ] Community announcement published
- [ ] FAQ document available
- [ ] faircode.io listing submitted
- [ ] Enterprise license template ready
- [ ] No significant community attrition (track GitHub stars, downloads)
