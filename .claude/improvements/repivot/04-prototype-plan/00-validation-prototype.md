# Validation Prototype Plan

**Purpose:** Build minimum prototype to validate core thesis before full implementation

**Timeline:** 4 weeks
**Effort:** 80 hours (2 weeks full-time)
**Investment:** Low (validate before committing to 800+ hour full implementation)

---

## Core Thesis to Validate

**Hypothesis:**
> "IT teams using AI coding assistants can build production-ready enterprise applications in hours (not weeks) using AI-optimized templates and pre-built components, reducing time-to-value from 2-4 hours to <30 minutes."

**What needs validation:**
1. ✅ Templates reduce time-to-first-screen to <30 min
2. ✅ AI assistants (Claude Code) successfully customize templates
3. ✅ IT teams (non-coders) can operate "human-on-the-loop"
4. ✅ Marketplace components are actually reused (not rebuilt)
5. ✅ 10 Golden Patterns reduce token consumption by 90%

---

## Prototype Scope (Minimal Viable Validation)

### Build Only:

**1. One Template: SaaS Starter (Minimal)**
- Basic structure (not full-featured)
- 3 models: User, Organization, Session
- 3 workflows: Register, Login, GetProfile
- AI instructions embedded
- CUSTOMIZE.md guide

**2. One Component: kailash-dataflow-utils**
- TimestampField, UUIDField only (not JSONField)
- Prevents datetime errors
- Simple implementation

**3. Minimal Quick Mode (Proof of Concept)**
- QuickDB with validate_create() only
- No QuickApp yet
- Just prove validation works

**4. 3 Golden Patterns (Not 10)**
- Pattern 1: Add DataFlow Model
- Pattern 2: Create Workflow
- Pattern 5: Authentication

**5. Simple CLI**
- `kailash create --template=saas-starter` only
- No `kailash dev`, `kailash upgrade`, `kailash marketplace`
- Prove template generation works

**NOT Building (Yet):**
- ❌ Internal Tools template
- ❌ API Gateway template
- ❌ Full Quick Mode (QuickApp, QuickWorkflow)
- ❌ kailash-sso, kailash-rbac, kailash-admin, kailash-payments
- ❌ Full CLI (dev, upgrade, marketplace)
- ❌ All 10 Golden Patterns
- ❌ Documentation website
- ❌ VS Code extension

**Rationale:** Build minimum to test hypothesis, not complete system

---

## Week-by-Week Plan

### Week 1: Build SaaS Template

**Day 1-2: Template Structure**
```
templates/saas-starter/
├── README.md
├── CUSTOMIZE.md
├── main.py
├── models/
│   ├── user.py
│   └── organization.py
├── workflows/
│   ├── auth.py
│   └── users.py
├── .env.example
└── requirements.txt
```

**Day 3-4: AI Instructions**
- Embed instructions in every file
- Write CUSTOMIZE.md with clear examples
- Add common mistakes sections

**Day 5: Testing**
- Test template generation
- Test that generated project runs
- Test basic workflows work

**Deliverable:** Working SaaS template (minimal but functional)

### Week 2: Build kailash-dataflow-utils

**Day 6-7: Implementation**
```python
# packages/kailash-dataflow-utils/src/dataflow_utils/fields.py

class TimestampField:
    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def validate(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            raise ValueError("Expected datetime, got string. Did you use .isoformat()?")
        raise ValueError(f"Expected datetime, got {type(value)}")

class UUIDField:
    @staticmethod
    def generate() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def validate(value) -> str:
        uuid.UUID(value)  # Validates
        return value
```

**Day 8: Testing**
- Unit tests (validates correctly)
- Integration test (prevents actual error)
- Publish to Test PyPI

**Day 9-10: Integration with Template**
- Update template to use dataflow-utils
- Test that datetime errors are prevented
- Document in CUSTOMIZE.md

**Deliverable:** kailash-dataflow-utils package (minimal but prevents key errors)

### Week 3: Build Basic Quick Mode + Golden Patterns

**Day 11-12: QuickDB Validation**
```python
# kailash/quick/db.py (minimal)

class QuickDB:
    def __init__(self, url: str = None):
        self.dataflow = DataFlow(url, debug=True)

    def model(self, cls):
        # Validate model (check for common mistakes)
        if "created_at" in cls.__annotations__:
            raise ValueError("created_at is auto-managed, remove from model")

        return self.dataflow.model(cls)
```

**Day 13-14: 3 Golden Patterns**
- Write Pattern #1: DataFlow Model
- Write Pattern #2: Create Workflow
- Write Pattern #5: Authentication
- Embed in template code

**Day 15: Create .claude/context/ System**
```python
# Auto-generate in templates

{
  "context": "it-team",
  "patterns": [
    "golden-pattern-1-dataflow-model",
    "golden-pattern-2-create-workflow",
    "golden-pattern-5-authentication"
  ],
  "docs": "See template code for patterns"
}
```

**Deliverable:** Validation system + minimal Golden Patterns

### Week 4: Testing with Real Users

**Day 16-17: Beta Test Prep**
- Polish template
- Write beta testing guide
- Create feedback survey

**Day 18-20: Beta Testing**
- Recruit 10 testers (5 IT teams, 5 developers)
- Guided testing session (live or async)
- Collect feedback and metrics

**Testing Protocol:**
```markdown
# Beta Test Script

## Setup (5 minutes)
1. Install: pip install kailash==0.10.0-alpha
2. Create: kailash create beta-test --template=saas-starter
3. Configure: cp .env.example .env (use SQLite for speed)

## Task 1: Start the App (5 minutes)
Run: kailash dev

Success criteria:
- App starts without errors
- Can access http://localhost:8000/docs
- See 3 endpoints (register, login, get_profile)

Time: ______ minutes
Issues: _______________

## Task 2: Customize with Claude Code (20 minutes)
Use Claude Code to add:
"Add a Product model with name, price, is_available fields"

Success criteria:
- Model added to models/product.py
- 9 nodes auto-generated
- Workflows generated (optional)

Time: ______ minutes
Token usage: ______ (from Claude Code)
Issues: _______________

## Task 3: Install Component (10 minutes)
Install: pip install kailash-dataflow-utils

Use TimestampField in a workflow

Success criteria:
- Component installs successfully
- Can import TimestampField
- Use in code prevents errors

Time: ______ minutes
Issues: _______________

## Feedback
1. Was time-to-first-screen <30 min? Y/N
2. Did Claude Code customization work? Y/N
3. Would you use Kailash for a real project? Y/N
4. NPS: How likely to recommend (0-10)?
5. What was most confusing?
6. What was most helpful?
7. What would you change?
```

**Day 21: Analysis**
- Aggregate feedback
- Measure time-to-first-screen
- Identify blockers
- Calculate NPS

**Deliverable:** Validation report with go/no-go recommendation

---

## Success Criteria for Prototype

### Quantitative

**1. Time-to-First-Screen**
- Target: 80% of testers achieve <30 minutes
- Current expectation: 2-4 hours
- If achieved: Core thesis validated

**2. AI Customization Success**
- Target: 70% of customizations work first try
- Measure: Claude Code generates working code
- If achieved: AI optimization validated

**3. NPS (Net Promoter Score)**
- Target: NPS 35+ (considered "good" for beta)
- IT teams: Higher priority (NPS 40+ goal)
- Developers: Secondary (NPS 25+ acceptable)

**4. Token Consumption**
- Target: <10K tokens for typical customization
- Current: 20K-50K tokens
- Measure: Claude Code token usage
- If achieved: Golden Patterns validated

**5. Component Installation**
- Target: 100% of testers successfully install component
- Measure: Beta test Task 3 completion
- If achieved: Marketplace model validated

### Qualitative

**6. User Feedback**
- "Would you use for real project?" → Target: 60% Yes
- "Most helpful feature?" → Should mention templates or components
- "Most confusing?" → Identify improvement areas

**7. Technical Validation**
- Template generates without errors (100%)
- Generated app runs successfully (90%+)
- No major bugs found (severity: critical)

---

## Go/No-Go Decision

### After Week 4: Evaluate Results

**GO if:**
- ✅ Time-to-first-screen: 80%+ under 30 min
- ✅ NPS: 35+ overall, 40+ from IT teams
- ✅ AI customization: 70%+ success rate
- ✅ Would use for real: 60%+ yes
- ✅ Token reduction: 50%+ (even if not 90% goal)

**Recommendation:** Proceed to full implementation (800 hours)

**NO-GO if:**
- ❌ Time-to-first-screen: <50% under 30 min
- ❌ NPS: <25
- ❌ AI customization: <50% success rate
- ❌ Would use for real: <40% yes

**Recommendation:** Rethink strategy, iterate prototype

**PIVOT if:**
- ⚠️ Template works but Quick Mode confusing → Skip Quick Mode, focus on templates
- ⚠️ AI customization fails → Improve AI instructions, add more examples
- ⚠️ IT teams struggle → Build visual tools instead (workflow-prototype priority)
- ⚠️ Components not valued → Skip marketplace, focus on templates only

---

## Prototype Budget

### Development Time

**Week 1: Template** - 40 hours
- Template structure: 10 hours
- AI instructions: 10 hours
- Workflows: 15 hours
- Testing: 5 hours

**Week 2: Component** - 20 hours
- Implementation: 10 hours
- Testing: 5 hours
- Documentation: 3 hours
- Publishing: 2 hours

**Week 3: Quick Mode + Patterns** - 15 hours
- QuickDB validation: 8 hours
- 3 Golden Patterns: 4 hours
- Context system: 3 hours

**Week 4: Testing** - 5 hours
- Beta test prep: 2 hours
- Running tests: 2 hours
- Analysis: 1 hour

**Total: 80 hours**

### Resource Allocation

**Option A: Solo (You)**
- Timeline: 4 weeks part-time (20 hours/week)
- Cost: $0 (your time)
- Benefit: Full control

**Option B: Contractor**
- Timeline: 2 weeks full-time
- Cost: $8K-12K ($100-150/hour × 80 hours)
- Benefit: Faster, focused

**Option C: Hybrid**
- You: Template + Golden Patterns (30 hours)
- Contractor: Component + Quick Mode (50 hours)
- Timeline: 2-3 weeks
- Cost: $5K-7.5K
- Benefit: Leverage expertise where needed

**Recommended:** Option A (validate yourself first, then scale)

---

## Risk Mitigation for Prototype

### Risk 1: Prototype Takes Too Long

**Mitigation:**
- Strict scope (no scope creep)
- Time-box each week
- Cut features if behind schedule

**If Week 1 takes 50 hours instead of 40:**
- Simplify template (fewer workflows)
- Reduce AI instructions (just essentials)
- Goal is validation, not perfection

### Risk 2: Beta Testers Don't Complete Testing

**Mitigation:**
- Clear testing script (1 hour or less)
- Incentives ($50 Amazon gift card)
- Synchronous testing session (guided)
- Async option for flexibility

**If <5 completions:**
- Extend testing period
- Recruit more testers
- Offer higher incentive

### Risk 3: Results Are Inconclusive

**Mitigation:**
- Clear success criteria upfront
- Quantitative + qualitative metrics
- Statistical significance (minimum 10 testers)

**If results unclear:**
- Run second round of testing
- Interview users (qualitative depth)
- A/B test variations

---

## Validation Report Template

### After Week 4: Document Results

```markdown
# Kailash Repivot Validation Report

Date: [Date]
Prototype Version: 0.10.0-alpha
Beta Testers: 10 (5 IT teams, 5 developers)

## Hypothesis Validation

### H1: Time-to-First-Screen <30 Minutes
Result: 8/10 (80%) achieved <30 min
Average time: 22 minutes
Fastest: 12 minutes
Slowest: 45 minutes (struggled with .env setup)

Conclusion: ✅ VALIDATED

### H2: AI Customization Success >70%
Result: 7/10 (70%) first-try success
Token usage: 8K tokens average (vs 20K+ before)

Conclusion: ✅ VALIDATED

### H3: IT Teams Operate Human-on-the-Loop
Result: 4/5 IT teams completed without help
1/5 needed guidance on workflow debugging

Conclusion: ⚠️  PARTIALLY VALIDATED (needs better error messages)

### H4: Component Reuse
Result: 10/10 installed dataflow-utils
10/10 said they'd use more components

Conclusion: ✅ VALIDATED

### H5: Token Reduction >50%
Result: 60% reduction (8K vs 20K tokens)
Goal was 90%, achieved 60%

Conclusion: ⚠️  PARTIALLY VALIDATED (Golden Patterns help, need refinement)

## NPS Score

IT Teams: 44 (2 promoters, 3 passives, 0 detractors)
Developers: 32 (1 promoter, 4 passives, 0 detractors)
Overall: 38 (target was 35)

Conclusion: ✅ ABOVE TARGET

## Qualitative Feedback

**Most Helpful:**
- "Template gave me working app immediately" (8 mentions)
- "AI instructions in code were clear" (6 mentions)
- "Not having to build auth from scratch" (7 mentions)

**Most Confusing:**
- ".env setup was unclear" (4 mentions)
- "When to use Quick Mode vs Full SDK" (3 mentions)
- "How to deploy to production" (2 mentions)

**Suggestions:**
- "Add more templates" (5 requests)
- "Visual workflow builder" (3 requests)
- "More marketplace components" (4 requests)

## Go/No-Go Recommendation

**Recommendation: GO**

**Rationale:**
- 4/5 hypotheses validated
- NPS above target
- Strong positive feedback
- Identified improvements are minor

**Next steps:**
1. Fix .env setup UX (add interactive prompts)
2. Add "Quick Mode vs Full SDK" decision guide
3. Add deployment guide to template
4. Proceed to full implementation

**Estimated success probability: 75%**
```

---

## Decision Tree

### If Results Are Strong (NPS 35+, 80%+ success)

**Decision:** Proceed to full implementation

**Confidence:** High (prototype validated core thesis)

**Next Steps:**
1. Complete all 3 templates
2. Build all 5 marketplace components
3. Implement full Quick Mode
4. Document all 10 Golden Patterns
5. Build complete CLI
6. Public beta launch

**Timeline:** 4-6 months to full launch

### If Results Are Mixed (NPS 25-35, 50-80% success)

**Decision:** Iterate prototype

**Confidence:** Medium (some validation, needs improvement)

**Next Steps:**
1. Identify top 3 issues from feedback
2. Fix issues in prototype
3. Run second round of testing (10 new testers)
4. Re-evaluate after round 2

**Timeline:** Add 2-4 weeks for iteration

### If Results Are Poor (NPS <25, <50% success)

**Decision:** Pivot or abandon

**Confidence:** Low (core thesis may be wrong)

**Options:**
1. **Pivot to visual tools** (workflow-prototype) instead of AI-assisted code
2. **Pivot to developer-only** (skip IT team market)
3. **Pivot to pure marketplace** (skip templates and Quick Mode)
4. **Abandon repivot** (keep current SDK as-is)

**Timeline:** 2-3 weeks to decide next direction

---

## Prototype Testing Logistics

### Recruting Beta Testers

**IT Teams (5 needed):**

**Recruitment channels:**
- Email existing Kailash users with DevOps background
- Post in r/devops, r/sysadmin
- Post in Platform Engineering Slack
- Ask current users for referrals

**Criteria:**
- Use AI coding assistants (Claude Code, Cursor, or Copilot)
- Need to build internal tools (current pain point)
- 2-4 hours available for testing
- Willing to provide feedback

**Incentive:**
- $50 Amazon gift card
- Early access to full release
- Credit in release notes
- Potential case study subject

**Developers (5 needed):**

**Recruitment channels:**
- Email existing Kailash contributors
- Post in r/Python
- GitHub issue for beta testers
- Twitter/X announcement

**Criteria:**
- Experienced with Python frameworks (FastAPI, Django, or Flask)
- Interested in workflow-based applications
- 2-4 hours available for testing
- Can provide technical feedback

**Incentive:**
- Early access
- Credit in release notes
- Priority for feature requests

### Testing Sessions

**Option A: Synchronous (Recommended for first 5)**
- 2-hour Zoom session
- Screenshare while using
- Real-time feedback
- Can guide if stuck

**Benefits:**
- Rich qualitative feedback
- See where users struggle
- Immediate clarification

**Option B: Asynchronous (Next 5)**
- Send testing script
- Users complete on their time
- Record screen (Loom)
- Submit feedback survey

**Benefits:**
- More testers (flexible timing)
- Less coordination needed
- Users in natural environment

### Data Collection

**Quantitative:**
- Time-to-first-screen (stopwatch)
- Task completion rates (checklist)
- Token consumption (Claude Code logs)
- Error rates (telemetry)

**Qualitative:**
- Screen recordings (with permission)
- Think-aloud protocol (synchronous sessions)
- Post-test interview (15 min)
- Open-ended survey

**Survey questions:**
```
1. How long did it take to get a working app? ______ minutes

2. Did Claude Code successfully customize the template? Y/N

3. How many times did you get stuck? 0 / 1-2 / 3-5 / 5+

4. Rate experience (1-10): ______

5. Would you use Kailash for a real project? Y/N/Maybe

6. Why or why not? [open response]

7. Most helpful feature: [open response]

8. Most confusing aspect: [open response]

9. What would make this better? [open response]

10. NPS: How likely to recommend to a colleague (0-10)? ______
```

---

## Prototype Success Checklist

**Before starting beta testing:**
- [ ] SaaS template generates successfully
- [ ] Generated app runs without errors
- [ ] kailash-dataflow-utils installable from PyPI
- [ ] Claude Code can customize template (tested internally)
- [ ] 3 Golden Patterns documented
- [ ] Beta testing script written
- [ ] Feedback survey created
- [ ] 10 beta testers recruited

**After beta testing:**
- [ ] ≥8/10 testers completed full script
- [ ] Time-to-first-screen: 80%+ <30 min
- [ ] NPS: 35+
- [ ] AI customization: 70%+ success
- [ ] All feedback collected and analyzed
- [ ] Validation report written
- [ ] Go/no-go decision made

---

## Key Takeaways

**Prototype is risk mitigation:**
- 80 hours investment vs 800+ hours full implementation
- Validates core thesis before committing
- Identifies issues early (when cheap to fix)
- Provides real user data (not speculation)

**Success unlocks:**
- Confidence to invest in full implementation
- Real user feedback to guide development
- Proof points for marketing
- Early adopters for launch

**Failure is valuable:**
- Learn what doesn't work (saves 800 hours)
- Opportunity to pivot before sunk cost
- User feedback guides better direction

**Either way, prototype provides clarity and reduces risk.**

---

**Next:** See `05-risks-mitigation/` for comprehensive risk analysis
