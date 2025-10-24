# Kaizen Developer: Sprint 1 (Prototype) Instructions

**Sprint:** Phase 0 - Prototype Validation
**Duration:** 4 weeks (Week 0-4)
**Your Workload:** 58 hours (14.5 hours/week average)
**Your Role:** Golden Patterns documentation, pattern embedding, beta testing coordination

---

## Your Objectives

**Primary:**
1. Document 3 Golden Patterns (#1, #2, #5) with AI-friendly examples
2. Embed patterns in template code as AI instructions
3. Lead beta testing coordination (recruit, facilitate, analyze)

**Success criteria:**
- Claude Code successfully uses Golden Patterns (70%+ success rate)
- Token usage reduced by 50%+ (vs full 246 skills)
- Beta testing runs smoothly (10 testers, clean data)

---

## Your Tasks (6 tasks, 58 hours)

| Task | Hours | Week | Priority | Status |
|------|-------|------|----------|--------|
| TODO-006: Golden Patterns #1, #2, #5 | 12h | Week 1-2 | P0 | PENDING |
| TODO-007: Embed Patterns in Template | 8h | Week 3 | P1 | PENDING |
| TODO-012: Recruit Beta Testers | 6h | Week 4 | P0 | PENDING |
| TODO-013: Run Beta Testing | 16h | Week 4 | P0 | PENDING |
| TODO-014: Analyze Beta Results | 8h | Week 4 | P0 | PENDING |
| Documentation Support | 8h | Week 1-3 | P1 | PENDING |

**Total: 58 hours over 4 weeks = 14.5 hours/week average**

---

## Week-by-Week Breakdown

### Week 1: Golden Patterns #1 and #2 (8 hours)

**Your focus:** Document the 2 most critical patterns with working examples

**Monday (4 hours):**

**AM (9am-10am):**
- Kickoff meeting (1h, all 3 + PM)

**AM (10am-1pm, 3h): START TODO-006 - Pattern #1**

**Subagent workflow:**
```bash
# Understand pattern requirements
> Use the requirements-analyst subagent to break down Golden Pattern #1 (Add DataFlow Model) into all information IT teams need

# Find best examples
> Use the sdk-navigator subagent to find the best DataFlow model examples in existing SDK documentation and examples

# Validate approach
> Use the dataflow-specialist subagent to review what makes an excellent DataFlow model pattern for AI assistants
```

**Expected output:**
- Clear understanding of what Pattern #1 must include
- 3-5 excellent existing examples to reference
- DataFlow best practices confirmed

**Implementation (2h):**

Create `.claude/skills/it-team/01-dataflow-model.md`:

```markdown
# Golden Pattern #1: Add a DataFlow Model

## When to Use
You need to store data in a database (users, products, orders, etc.).

## The Pattern

```python
from dataflow import DataFlow
from kailash_dataflow_utils import UUIDField, TimestampField

db = DataFlow("postgresql://...")  # From .env

@db.model
class Product:
    """Product model.

    DataFlow auto-generates 9 nodes:
    - ProductCreateNode
    - ProductReadNode
    - ProductUpdateNode
    - ProductDeleteNode
    - ProductListNode
    - ProductBulkCreateNode
    - ProductBulkUpdateNode
    - ProductBulkDeleteNode
    - ProductBulkUpsertNode
    """
    id: str
    name: str
    price: float
    description: str = ""
    is_available: bool = True
```

## Using Auto-Generated Nodes

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Create product
workflow.add_node("ProductCreateNode", "create", {
    "id": UUIDField.generate(),
    "name": "Widget",
    "price": 9.99
})
```

## Common Mistakes

❌ **Using product_id instead of id**
```python
class Product:
    product_id: str  # WRONG - must be 'id'
```

✅ **Always use id as primary key**
```python
class Product:
    id: str  # CORRECT
```

[... more mistakes and solutions ...]

## Variations

**Variation 1: Optional fields**
[Example with Optional[str]]

**Variation 2: Multi-tenancy**
[Example with __dataflow__ = {'multi_tenant': True}]

**Variation 3: Validation**
[Example with validators]

## AI Prompt Examples

**Prompt:** "Add a Product model with name, price, description"

**Expected:** Claude Code creates models/product.py following this pattern
```

**Validation (1h):**
```bash
# Test with Claude Code
> Use the documentation-validator subagent to test Golden Pattern #1 with Claude Code and verify it successfully generates correct DataFlow model

# Ensure pattern is AI-friendly (clear, copy-paste ready, no ambiguity)
```

**Test process:**
1. Open template in Claude Code
2. Prompt: "Add Product model with name, price, description"
3. Observe: Does Claude Code find Pattern #1?
4. Verify: Does generated code follow pattern correctly?
5. Success rate target: 70%+

**If <70% success:**
- Refine pattern (add more examples, clarify instructions)
- Re-test until 70%+ achieved

---

**Tuesday (4 hours):**

**AM (9am-1pm): PATTERN #2 - Create Workflow**

**Same process as Pattern #1:**
1. Analysis with subagents (1h)
2. Implementation (2h)
3. Validation with Claude Code (1h)

**Create:** `.claude/skills/it-team/02-create-workflow.md`

**Content:**
- When to use (multi-step business logic)
- The pattern (WorkflowBuilder with connections)
- Common mistakes (forgetting .build(), wrong connection syntax)
- Variations (error handling, conditional logic, API calls)
- AI prompt examples

**Test with Claude Code:**
- Prompt: "Create workflow to create product and send notification"
- Success: Claude Code uses Pattern #2 correctly

---

**Wednesday-Thursday (4 hours):**

**Continue TODO-006**

**Wed AM (2h): PATTERN #5 - Authentication Workflow**

**Create:** `.claude/skills/it-team/05-authentication.md`

**This is the most complex pattern (register, login, JWT, sessions).**

**Focus:**
- Clear step-by-step (don't overwhelm)
- Working example (tested)
- Reference kailash-sso component (when to use pre-built vs custom)

**Thurs PM (2h): Finalize all 3 patterns**

- Review and polish
- Ensure consistency across patterns
- Create pattern index
- Get DataFlow dev to review technical accuracy

**Acceptance:**
- [ ] 3 patterns documented (15-20 pages each, 45-60 pages total)
- [ ] All code examples tested and working
- [ ] Claude Code success rate 70%+ for each pattern
- [ ] DataFlow dev technical review approved

**Mark TODO-006 COMPLETE**

---

**Friday (0 hours - retrospective only):**

- Weekly retrospective (30 min)
- Share Pattern #1, #2 drafts with team

**Week 1 total: 12 hours**

---

### Week 2: Complete Pattern #5 + Support (10 hours)

**Monday-Tuesday (6 hours):**

**Complete Pattern #5:**
- Refine authentication pattern
- Test with template's actual auth workflows
- Add troubleshooting section

**Wednesday (2 hours):**

**Review Nexus dev's CUSTOMIZE.md:**
- Read draft from non-technical perspective
- Flag confusing sections
- Suggest simplifications
- Test examples yourself

**Thursday-Friday (2 hours):**

**Create .claude/context/golden-patterns.md:**

This file tells Claude Code which skills to load.

```markdown
# Golden Patterns for AI Assistants

**Context:** IT Team / AI-Assisted Development

**Load these patterns ONLY:**
1. 01-dataflow-model.md - Add DataFlow Model
2. 02-create-workflow.md - Create Workflow
3. 05-authentication.md - Authentication Workflow

**Do NOT load:**
- Full 246 skills (too much context)
- Advanced patterns (not needed for prototype)

**For advanced use cases:** Reference full SDK documentation

**Token optimization:** 90% reduction (from 20K to 2K tokens)
```

**End of week:**
- Weekly retrospective (30 min)

**Week 2 total: 10 hours**
**Running total: 22 hours**

---

### Week 3: Embed Patterns in Template (12 hours)

**TODO-007: Embed Patterns in Template Code** [#472]

**Your task:** Add AI instructions to template files referencing Golden Patterns

**Monday-Tuesday (8 hours):**

**Embedding process:**

1. **models/user.py:**
```python
"""User model for authentication.

AI INSTRUCTION:
===============
SEE: Golden Pattern #1 - Add DataFlow Model

This model demonstrates:
- DataFlow @db.model decorator
- Type hints for fields
- Auto-generated nodes (9 nodes created automatically)
- Multi-tenancy (tenant_id added by DataFlow)

TO ADD A NEW MODEL:
Copy this pattern. Change class name and fields.
DataFlow auto-generates 9 CRUD nodes.

COMMON MISTAKES:
❌ Using user_id instead of id
❌ Including created_at/updated_at (auto-managed)
❌ Using datetime.now().isoformat() (use TimestampField.now())

SEE: kailash-dataflow-utils for field helpers
"""

from dataflow import DataFlow
from kailash_dataflow_utils import UUIDField, TimestampField

# [... actual model code ...]
```

2. **workflows/auth.py:**
```python
"""Authentication workflows.

AI INSTRUCTION:
===============
SEE: Golden Pattern #2 - Create Workflow
SEE: Golden Pattern #5 - Authentication Workflow

This file demonstrates:
- WorkflowBuilder for multi-step workflows
- Node connections (defining execution order)
- Error handling
- JWT token generation

TO ADD A NEW WORKFLOW:
[... instructions ...]

SEE: Golden Pattern #5 for complete auth pattern
OR: pip install kailash-sso for production-ready auth
"""

# [... actual workflow code ...]
```

3. **main.py:**
```python
"""Main application entry point.

AI INSTRUCTION:
===============
SEE: Golden Pattern #3 - Deploy with Nexus (when added)

TO ADD NEW WORKFLOW:
1. Create in workflows/
2. Import here
3. Register: nexus.register("name", workflow())

[... instructions ...]
"""
```

4. **Create `.claude/context/golden-patterns.md`** (auto-loaded by Claude Code)

**Testing (4 hours):**

**Test with Claude Code (critical validation):**

1. **Test Pattern #1:**
   - Prompt: "Add Product model with name, price, description"
   - Expected: Claude Code finds Pattern #1, creates models/product.py correctly
   - Measure: Success? Time taken? Tokens used?

2. **Test Pattern #2:**
   - Prompt: "Create workflow to create product and send notification"
   - Expected: Claude Code uses WorkflowBuilder pattern correctly
   - Measure: Works first try?

3. **Test Pattern #5:**
   - Prompt: "Add email field to registration workflow"
   - Expected: Claude Code modifies auth workflow correctly
   - Measure: Integration maintained?

**For each test:**
```bash
# Validate AI effectiveness
> Use the documentation-validator subagent to test that Claude Code successfully uses Golden Patterns when customizing template

# If success rate <70%, refine patterns and re-test
```

**Acceptance:**
- [ ] All template files have AI instructions
- [ ] Instructions reference Golden Patterns
- [ ] .claude/context/golden-patterns.md created
- [ ] Claude Code tests: 70%+ success rate across 3 patterns
- [ ] Token usage: <10K (vs 20K+ baseline)

**Mark TODO-007 COMPLETE**

---

**Wednesday-Friday (4 hours):**

**Integration testing:**
- Test complete template with all patterns embedded
- Verify patterns don't break template execution
- Test with fresh template generation

**Documentation:**
- Create "AI Optimization" section in template README
- Document token savings for users

**Week 3 total: 12 hours**
**Running total: 34 hours**

---

### Week 4: Beta Testing Leadership (24 hours)

**Your role:** Lead beta testing from start to finish

**Monday (6 hours):**

**TODO-012: Recruit 10 Beta Testers** [#479]

**Target:** 5 IT teams + 5 developers

**Recruitment channels:**
- Email existing Kailash users (if any)
- Post in r/devops, r/sysadmin (IT teams)
- Post in r/Python (developers)
- Personal network

**Recruitment message template:**
```
Subject: You're Invited: Kailash Template Beta Test

Hi [Name],

You're invited to beta test Kailash's new SaaS template.

What: AI-optimized template that generates working multi-tenant SaaS in <30 minutes
Time commitment: 1-2 hours (testing + feedback survey)
Incentive: $50 Amazon gift card + early access + recognition

Why you: [IT professional / Python developer] interested in AI-assisted development

Interested? Reply or click: [signup link]

Thanks,
[Your name]
```

**Tasks:**
- Create tester list (aim for 15, expect 10 to actually complete)
- Email/message recruitment
- Follow up with interested people
- Schedule testing sessions (Tue-Wed Week 4)

**Prepare testing materials:**
- Testing script (step-by-step what testers do)
- Feedback survey (quantitative + qualitative questions)
- Screen recording instructions (if async testing)

**Acceptance:**
- [ ] 10 testers confirmed (5 IT, 5 dev)
- [ ] Testing sessions scheduled
- [ ] Materials prepared
- [ ] Survey ready

**Mark TODO-012 COMPLETE**

---

**Tuesday-Wednesday (16 hours - high intensity):**

**TODO-013: Run Beta Testing Sessions** [#480]

**Format:** Synchronous (recommended) - 2 sessions of 5 testers each

**Tuesday PM (2pm-5pm, 3 hours): Session 1**

**Setup (30 min before):**
- Test template yourself (ensure it works)
- Prepare Zoom room
- Have troubleshooting guide ready

**Session (3h):**
- Introduction (15 min) - What they'll test, how to provide feedback
- Testing (90 min) - Testers follow script, you observe
- Debrief (15 min) - Quick reactions, immediate feedback

**Your role:**
- Observe where people struggle (note timestamps)
- Provide minimal help (let them struggle a bit to see real issues)
- Take detailed notes (quotes, pain points, successes)
- Time each tester (track time-to-first-screen)

**Data to collect:**
- Time-to-first-screen for each tester
- Where they got stuck (which step?)
- Errors encountered
- Whether Claude Code customization worked
- Initial reactions (qualitative)

---

**Wednesday PM (2pm-5pm, 3 hours): Session 2**

**Same format as Session 1**

**This session:**
- Nexus dev facilitates (you support)
- You continue taking notes
- Focus on consistent issues across both sessions

**After session (2h):**
- Compile notes from both sessions
- Categorize issues (CUSTOMIZE.md, AI instructions, bugs, missing features)
- Calculate preliminary metrics (NPS, time-to-screen)

---

**Async testing option (if can't get 10 synchronous):**
- Send testers script + survey
- Ask them to record screen (Loom)
- Follow up individually if issues
- More testers possible but less rich data

**Wednesday PM: Data compilation (5h)**

Compile all data:
- Aggregate timing data (create distribution chart)
- Calculate NPS (% promoters - % detractors)
- Categorize qualitative feedback (themes)
- Identify top 5 issues (if any)

**Week 4 through Wednesday: 16 hours**

---

**Thursday (8 hours):**

**TODO-014: Analyze Beta Results** [#481]

**AM (9am-1pm, 4h): Quantitative Analysis**

**Metrics to calculate:**

**M1: NPS (Net Promoter Score)**
- Count promoters (9-10): X
- Count passives (7-8): Y
- Count detractors (0-6): Z
- NPS = (X - Z) / 10 × 100
- Target: 35+ (40+ from IT teams)

**M2: Time-to-First-Screen**
- Calculate for each tester
- Create distribution (fastest, median, slowest)
- Calculate % achieving <30 min
- Target: 80%+

**M3: AI Customization Success Rate**
- Count testers who successfully customized with Claude Code
- Calculate: Success / Total
- Target: 60%+

**M4: Component Installation Success**
- Count: Successfully installed kailash-dataflow-utils
- Calculate: Success / Total
- Target: 100%

**Create metrics dashboard:**
```
Beta Testing Results (10 testers: 5 IT, 5 dev)

NPS: 42 (PASS ✅) [Target: 35+]
  - Promoters: 6 (60%)
  - Passives: 3 (30%)
  - Detractors: 1 (10%)
  - IT teams NPS: 48 (PASS ✅) [Target: 40+]

Time-to-First-Screen: 85% <30 min (PASS ✅) [Target: 80%+]
  - Fastest: 12 min
  - Median: 25 min
  - Slowest: 45 min (1 outlier)
  - Distribution: [chart]

AI Customization: 70% success (PASS ✅) [Target: 60%+]
  - 7/10 succeeded first try
  - 2/10 needed help
  - 1/10 failed (Claude Code didn't find pattern)

Component Install: 100% (PASS ✅) [Target: 100%]
  - All 10 successfully installed kailash-dataflow-utils

OVERALL: 4/4 primary metrics PASSED → GO recommended
```

**PM (2pm-6pm, 4h): Qualitative Analysis**

**Categorize feedback:**
- **Most helpful:** Templates (8 mentions), Components (6), Patterns (4)
- **Most confusing:** .env setup (3 mentions), Nexus deployment (2), Multi-tenancy (1)
- **Suggestions:** More templates (5), More components (4), Video tutorial (3)

**Issues identified:**
1. .env setup unclear (medium severity, fixable)
2. CUSTOMIZE.md missing deployment section (low severity, easy fix)
3. Claude Code sometimes doesn't find patterns (low severity, improve embedding)

**Create recommendation report:**
```markdown
# Prototype Validation Results

## Executive Summary

**Recommendation: GO** (proceed to full MVR)

**Rationale:**
- All 4 primary metrics passed (NPS 42, time 85%, customization 70%, install 100%)
- 3/3 qualitative metrics positive
- Issues identified are minor and fixable
- Team pairing effective (DataFlow + Nexus report positive)

## Detailed Results

[... metrics, feedback, issues ...]

## Recommended Adjustments for Phase 1

1. Improve .env setup (add interactive prompts)
2. Add deployment guide to CUSTOMIZE.md
3. Enhance pattern embedding (ensure Claude Code finds patterns)

## Decision

**GO:** Proceed to full MVR (Phases 1-4, 7-9 months)

**Confidence:** HIGH (85% - all metrics exceeded targets)

**Next Steps:**
1. Phase 1 kickoff (next Monday)
2. Implement adjustments from beta feedback
3. Begin template refinement and expansion
```

**Mark TODO-014 COMPLETE**

---

**Friday (2 hours):**

**TODO-015: Go/No-Go Decision Meeting** [DECISION GATE]

**AM (10am-12pm): Team Decision Meeting**

**Your role:** Present analysis and recommendation

**Agenda:**
1. **Present metrics** (15 min) - Show dashboard, explain results
2. **Present feedback** (15 min) - Key themes, direct quotes
3. **Present recommendation** (10 min) - GO with rationale
4. **Team discussion** (45 min) - Any concerns? Agreement?
5. **Decision** (10 min) - Formal Go/No-Go/Iterate
6. **Next steps** (10 min) - If GO, plan Phase 1 kickoff

**Outcomes:**
- **If GO:** Phase 1 starts next week, celebrate success
- **If ITERATE:** Fix issues (assign to owners), re-test in 2-4 weeks
- **If NO-GO:** Pivot planning, document learnings

**Document decision:**
- Rationale (why GO/ITERATE/NO-GO)
- Data supporting decision
- Dissenting opinions (if any)
- Next actions

**Mark TODO-015 COMPLETE**

**Sprint retrospective (1h):**
- What went well?
- What could improve?
- Action items for Phase 1 (if GO)

**Week 4 total: 24 hours**
**Sprint 1 total: 58 hours** ✅

---

## Your Detailed Task Guides

### TODO-006: Golden Patterns (12 hours, Week 1-2)

**The quality of these patterns determines AI effectiveness.**

**Pattern template (for each pattern):**

````markdown
# Golden Pattern #X: [Pattern Name]

## When to Use
[Problem statement - when IT teams need this]

## The Pattern

```python
# Complete, working example
# Copy-paste ready
# Tested and verified
```

## Step-by-Step

1. [Step 1 with code]
2. [Step 2 with code]
3. [Step 3 with code]

## Common Mistakes

❌ **Mistake 1: [Description]**
```python
# Wrong code example
```
**Why wrong:** [Explanation]

✅ **Correct approach:**
```python
# Right code example
```

[... 3-5 common mistakes ...]

## Variations

**Variation 1: [Scenario]**
[Code example]

**Variation 2: [Another scenario]**
[Code example]

## AI Prompt Examples

**Prompt:** "[Natural language request]"
**Expected:** Claude Code does [specific actions]
**Verify:** [How to test it worked]

## Troubleshooting

**Issue:** [Common problem]
**Solution:** [Fix with code example]

## Related Patterns

- Pattern #Y: [Related pattern]
- Pattern #Z: [Also useful for X]

## References

- SDK docs: [link]
- Component: [kailash-component if applicable]
````

**Quality checklist for each pattern:**
- [ ] Problem clearly stated (IT teams understand when to use)
- [ ] Complete working example (tested)
- [ ] Common mistakes documented (3-5 with wrong/right examples)
- [ ] Variations cover common scenarios (2-3)
- [ ] AI prompts tested with Claude Code (70%+ success)
- [ ] Troubleshooting section (common issues)

**Don't rush. Quality here determines AI effectiveness.**

---

### TODO-007: Embedding (8 hours, Week 3)

**Embedding guidelines:**

**In model files:**
- Top docstring: AI INSTRUCTION section
- Reference relevant Golden Pattern (#1 for models)
- Show usage in workflows
- List common mistakes
- Point to kailash-dataflow-utils

**In workflow files:**
- Top docstring: AI INSTRUCTION section
- Reference relevant patterns (#2 for workflows, #5 for auth)
- Show complete example
- Explain customization points

**In main.py:**
- Explain Nexus registration
- Reference Pattern #3 (when created)
- Show how to add workflows

**Test embedding:**
- Claude Code should find instructions when working in that file
- Verify: Open models/user.py in Claude Code, prompt "Add email field"
- Claude Code should see AI instructions and follow pattern

---

## Your Success Metrics

**Sprint 1 success for you:**
- ✅ 3 Golden Patterns documented (tested with Claude Code)
- ✅ Patterns embedded in template (AI instructions comprehensive)
- ✅ Beta testing executed smoothly (10 testers, clean data)
- ✅ GO recommendation supported by data (metrics + feedback)

**Measure by:**
- Claude Code success rate (70%+ using patterns)
- Token reduction (50%+ vs full skills)
- Beta testing logistics (10 testers recruited and tested)
- Decision confidence (data supports recommendation)

---

## Resources

**Your instructions:** `09-developer-instructions/04-kaizen-instructions.md` (minimal - Kaizen has no code changes in MVR)
**Golden Patterns spec:** `02-implementation/02-new-components/03-golden-patterns.md` (1,300 lines)
**Testing guide:** `04-prototype-plan/00-validation-prototype.md`

---

**You are the documentation and validation expert. Your patterns enable AI, your testing validates the thesis, your analysis drives the decision.**

**Document with clarity. Test with rigor. Decide with confidence.** 🚀
