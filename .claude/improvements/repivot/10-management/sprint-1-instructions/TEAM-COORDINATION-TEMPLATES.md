# Sprint 1 Team Coordination Templates

**Purpose:** Standard templates for daily updates, weekly standups, and reviews

---

## Daily Update Template (5 min/person, async)

**Post in:** #mvr-execution Slack/Discord channel
**Frequency:** End of each work day
**Format:**

```
📅 Daily Update - [Date] - [Your Name]

✅ COMPLETED TODAY:
  - TODO-XXX: [Task name] - Subtask 1 completed
  - Code review: [Teammate]'s TODO-YYY approved
  - [Other accomplishments]

🚧 IN PROGRESS:
  - TODO-XXX: [Task name] - Currently on subtask 2 of 5
  - [Status details: 60% complete, tests passing]

⏭️ TOMORROW:
  - Complete TODO-XXX (remaining 40%)
  - Start TODO-YYY if TODO-XXX finishes
  - Pair session with [Teammate] on [topic]

❓ BLOCKERS/QUESTIONS:
  - None
  - OR: [Describe blocker] - Need help from [person]
  - OR: Question about [topic] - @mention if urgent

📊 HOURS:
  - Today: 4h
  - This week: 12h
  - Sprint total: 28h

🔗 EVIDENCE:
  - Commit: [hash] - [file changes]
  - GitHub: [issue link] with update
  - Tests: [X passing, Y failing]
```

**Example (DataFlow Dev, Week 1 Monday):**
```
📅 Daily Update - Oct 28, 2025 - DataFlow Dev

✅ COMPLETED TODAY:
  - TODO-001: SaaS template structure - Subtasks 1-3 complete
    - Created directory structure (20 files)
    - Added skeleton code to main.py, models/*, workflows/*
    - Basic README.md draft
  - Code review: Started reviewing Kaizen dev's Pattern #1 draft

🚧 IN PROGRESS:
  - TODO-001: Subtasks 4-5 remaining (pyproject.toml, testing)
  - Estimated 80% complete, on track for Tuesday completion

⏭️ TOMORROW:
  - Complete TODO-001 (final 20% + testing + review)
  - Start TODO-002 (Auth models) if TODO-001 approved
  - Pair session with Nexus dev (2pm, review structure)

❓ BLOCKERS/QUESTIONS:
  - None - on track

📊 HOURS:
  - Today: 4h
  - This week: 4h (Monday)
  - Sprint total: 4h

🔗 EVIDENCE:
  - Commit: a1b2c3d - Added template structure (15 files)
  - GitHub: Issue #458 updated with structure screenshot
  - Tests: test_template_generation.py created (not run yet)
```

---

## Weekly Standup Template (30 min, synchronous)

**When:** Every Monday 10am (or team preference)
**Who:** All 3 developers + PM
**Tool:** Zoom/Google Meet or in-person
**Format:**

### Agenda

**1. Celebrate Wins (5 min)**

Go around:
- What are you proud of from last week?
- Recognition for others (did someone help you?)

**Example:**
- DataFlow dev: "Proud of completing TODO-001 with clean code. Thanks to Nexus dev for thoughtful review."
- Nexus dev: "Learned a lot about DataFlow from pairing. DataFlow dev is great teacher."

---

**2. Progress vs Plan (10 min)**

**PM presents:**

| Person | Planned (Last Week) | Actual | Variance | This Week Plan |
|--------|---------------------|--------|----------|----------------|
| DataFlow | 20h (TODO-001,002,003) | 18h (001 done, 002 90% done) | -10% | 16h (complete 002, start 003) |
| Nexus | 12h (Review 001,002,003) | 10h (reviewed 001,002) | -17% | 10h (review 003, start 004) |
| Kaizen | 8h (Pattern #1, #2) | 10h (Patterns done, extra polish) | +25% | 8h (Pattern #5) |

**Discussion:**
- Are we on track for Week 4 decision gate?
- Any risks to timeline?
- Need to adjust plan?

---

**3. Blockers and Risks (10 min)**

**Round-robin:**

Each person shares:
- **Blockers:** Anything preventing progress?
  - Example: "Waiting for Nexus dev's TODO-004 to test integration"
  - Action: Nexus dev commits to completing by Wednesday
- **Risks:** Anything that might become a blocker?
  - Example: "TODO-003 might take 15h instead of 12h (auth is complex)"
  - Action: Plan for 15h, adjust Week 2 schedule if needed

**PM assigns action items:**
- Who will resolve blocker?
- By when?
- Follow-up in daily update

---

**4. Next Week Planning (5 min)**

**Quick confirmation:**
- Week 2 plan: DataFlow dev on TODO-002/003, Nexus dev on TODO-004/005, Kaizen on Pattern #5
- Pair sessions: Monday, Wednesday (2h each)
- Any changes needed?

**Action items from standup:**
- Documented in meeting notes
- Assigned to owners
- Tracked in daily updates

---

## Weekly Retrospective Template (1 hour, end of week)

**When:** Every Friday 4pm (or end of week)
**Who:** All 3 developers (PM optional)
**Tool:** Zoom or async (Slack thread)
**Format:**

### Retro Agenda

**1. Week Review (10 min)**

**Metrics:**
- Planned hours: 50h (DataFlow 20, Nexus 12, Kaizen 18)
- Actual hours: 48h (DataFlow 18, Nexus 10, Kaizen 20)
- Variance: -4% (good!)
- Tasks completed: 5/5 planned (100%)
- Quality: All tests passing, reviews approved

**2. What Went Well (15 min)**

**Round-robin (5 min each):**
- DataFlow dev: "Pairing with Nexus dev was productive. Learned I need to explain DataFlow concepts more clearly."
- Nexus dev: "Appreciated DataFlow dev's patience. Learned a lot. Structure review worked well."
- Kaizen dev: "Patterns came together nicely. Claude Code testing was revealing."

**Capture:**
- Practices to continue (pairing, async reviews, daily updates)
- Tools that worked (Zoom for pairing, Slack for daily updates)

**3. What Could Improve (15 min)**

**Round-robin (5 min each):**
- DataFlow dev: "Would help to have Nexus dev's input earlier in design phase."
- Nexus dev: "Pair sessions could be 90 min instead of 2h (fatigue sets in)."
- Kaizen dev: "Need more time for Claude Code testing (patterns took longer than expected)."

**Capture:**
- Pain points (long pair sessions, late input, underestimated tasks)
- Process improvements (earlier collaboration, shorter sessions, better estimates)

**4. Action Items for Next Week (10 min)**

**What will we do differently?**
- ✅ Shorter pair sessions (90 min max, 15 min break)
- ✅ Design review meetings at start of tasks (get all input upfront)
- ✅ Add 20% buffer to estimates (tasks taking longer than expected)

**Assign owners:**
- Who implements each improvement?
- When?

**5. Sprint Health Check (5 min)**

**Quick poll (1-5 scale):**
- **Confidence in hitting Week 4 gate:** 1 (low) to 5 (high)
- **Team collaboration quality:** 1 (poor) to 5 (excellent)
- **Personal energy/morale:** 1 (burned out) to 5 (energized)
- **Code quality satisfaction:** 1 (technical debt) to 5 (proud)

**If any score <3:** Discuss and address next week

**6. Celebrate (5 min)**

- Acknowledge hard work
- Share funny moments or learnings
- Build team camaraderie

---

## Quality Gate Review Template (2 hours, milestone meetings)

**When:** Week 4 (Prototype), Week 8 (Foundation), Week 16 (Infrastructure), Week 28 (Launch)
**Who:** All 3 developers + PM + optional stakeholders
**Format:**

### Gate 0: Prototype Validation (Week 4)

**Agenda (2 hours):**

**1. Metrics Presentation (30 min)**

**Kaizen dev presents:**
- Dashboard with all metrics
- Comparison to targets (Pass/Fail per metric)
- Statistical significance (sample size, confidence)

**Questions from team:**
- Is data reliable?
- Any anomalies?
- How do IT teams vs developers differ?

---

**2. Qualitative Feedback (30 min)**

**Kaizen dev presents:**
- Key themes from feedback
- Direct quotes (positive and negative)
- Issues identified
- User suggestions

**Discussion:**
- Are issues fixable?
- What would it take?
- Should we prioritize differently?

---

**3. Team Assessment (20 min)**

**Each developer shares:**
- **DataFlow dev:** Was pairing valuable? Would you pair again in Phase 1?
- **Nexus dev:** Same question from your perspective
- **Kaizen dev:** Did beta testing run smoothly? Is data trustworthy?

**PM asks:**
- Is team healthy (morale, collaboration, energy)?
- Can team sustain 7-9 months if we GO?
- Any concerns about proceeding?

---

**4. Decision Discussion (30 min)**

**Options review:**

**Option A: GO (Proceed to Phase 1)**
- **Requires:** 3/4 primary metrics pass, 2/3 secondary pass, team willing
- **Means:** Commit to 7-9 months, Phases 1-4
- **Next:** Phase 1 kickoff next Monday

**Option B: ITERATE (Fix issues, re-test)**
- **Requires:** 2/4 primary metrics pass, issues fixable
- **Means:** 2-4 weeks iteration, then re-test
- **Next:** Assign fixes, schedule re-test

**Option C: NO-GO (Pivot or abandon)**
- **Requires:** <2/4 primary metrics pass, fundamental issues
- **Means:** MVR not viable, explore alternatives
- **Next:** Pivot planning (workflow-prototype, developer-only, or status quo)

**Team discussion:**
- Each person voices opinion (GO/ITERATE/NO-GO)
- Concerns aired
- Questions answered

---

**5. Formal Decision (10 min)**

**PM facilitates:**
- Review criteria one more time
- Confirm data supports recommendation
- Any dissenting opinions?
- **Make decision:** GO, ITERATE, or NO-GO

**Document:**
- Decision made (GO/ITERATE/NO-GO)
- Rationale (metrics, feedback, team input)
- Dissents (if any, with reasoning)
- Next actions (specific, assigned, dated)

**If GO:**
- Phase 1 starts next Monday
- Celebration (small wins matter!)
- Adjust based on learnings

**If ITERATE:**
- Issues assigned to owners
- Re-test schedule set
- Adjust timeline expectations

**If NO-GO:**
- Pivot planning session scheduled
- Lessons documented
- Team debriefed

---

## Communication Best Practices

### Daily Updates

**Do:**
- ✅ Post every day you work (even if just 1 hour)
- ✅ Be specific ("Completed subtask 2" not "worked on TODO")
- ✅ Include evidence (commit hash, issue link, test results)
- ✅ Flag blockers immediately (don't wait)
- ✅ Keep it short (5 min to write, 2 min to read)

**Don't:**
- ❌ Skip days (breaks visibility)
- ❌ Be vague ("made progress" - on what?)
- ❌ Hide blockers (escalate early)
- ❌ Write essays (keep it concise)

### Weekly Standups

**Do:**
- ✅ Come prepared (know your status)
- ✅ Share wins (recognize good work)
- ✅ Be honest about blockers (team can help)
- ✅ Suggest solutions (not just problems)
- ✅ Respect time (30 min max)

**Don't:**
- ❌ Ramble (stick to agenda)
- ❌ Solve problems in standup (take offline)
- ❌ Skip (important for coordination)
- ❌ Blame (focus on solutions)

### Quality Gates

**Do:**
- ✅ Prepare data (have metrics ready)
- ✅ Be objective (data drives decision)
- ✅ Voice concerns (speak up if issues)
- ✅ Make tough calls (NO-GO is OK if data says so)
- ✅ Document decision (rationale matters)

**Don't:**
- ❌ Sugar-coat (be honest about results)
- ❌ Decide emotionally (ignore data)
- ❌ Skip gate (don't proceed if fail)
- ❌ Blame (focus on system, not people)

---

## Escalation Process

### When to Escalate

**Immediate escalation (within hours):**
- 🚨 Blocking bug (can't make progress)
- 🚨 Team conflict (can't resolve with discussion)
- 🚨 Major scope change needed (task is 2x estimate)
- 🚨 Security issue discovered

**Daily escalation (next standup):**
- ⚠️ Task taking longer than estimated (but still progressing)
- ⚠️ Integration issue (workaround exists but not ideal)
- ⚠️ Test coverage below target (<80%)
- ⚠️ Coordination issue (handoff delayed)

**Weekly escalation (retrospective):**
- ℹ️ Process improvement idea
- ℹ️ Tool suggestion
- ℹ️ Documentation gap
- ℹ️ Future concern

### How to Escalate

**To PM (immediate):**
- Slack DM: "[URGENT] Blocked on TODO-XXX due to [reason]"
- Provide: What's blocked, why, proposed solution, need decision by when

**To team (daily update):**
- Daily update: "❓ BLOCKERS: [describe] - Need input from @teammate"
- Tag person, be specific about what you need

**In standup (weekly):**
- "I have a blocker: [describe]"
- PM facilitates discussion
- Action item assigned

---

## Templates by Week

### Week 1 Templates

**Monday (Kickoff Day):**
```
📅 Daily Update - Oct 28, 2025 - [Name]

✅ COMPLETED TODAY:
  - Attended team kickoff meeting (1h)
  - Read my sprint instructions ([X] hours of reading)
  - Set up dev environment for Sprint 1
  - Read GitHub issue #[XXX] for my first task

🚧 IN PROGRESS:
  - TODO-[XXX]: Starting tomorrow morning
  - Understanding requirements and dependencies

⏭️ TOMORROW:
  - Start TODO-[XXX] implementation
  - Run subagent workflow (requirements-analyst → sdk-navigator → ...)
  - Complete subtask 1 if possible

❓ BLOCKERS/QUESTIONS:
  - None - ready to start

📊 HOURS:
  - Today: 2h (kickoff + reading)
  - This week: 2h
  - Sprint total: 2h
```

**Mid-week (Active Development):**
```
📅 Daily Update - Oct 30, 2025 - DataFlow Dev

✅ COMPLETED TODAY:
  - TODO-001: COMPLETE ✅
    - All 5 subtasks done
    - Tests passing (test_template_generation: 100%)
    - Nexus dev review approved
    - GitHub issue #458 closed
  - TODO-002: Started - subtasks 1-2 complete (User, Organization models defined)

🚧 IN PROGRESS:
  - TODO-002: Subtask 3 (Session model) - 50% done
  - AI instructions being added to model docstrings

⏭️ TOMORROW:
  - Complete TODO-002 (remaining 50%)
  - Get Nexus dev final review
  - Start TODO-003 if time permits

❓ BLOCKERS/QUESTIONS:
  - Question for Nexus dev: Should Session model include MCP-specific fields?
    - Not urgent, can discuss in pair session Friday

📊 HOURS:
  - Today: 4h
  - This week: 16h
  - Sprint total: 16h

🔗 EVIDENCE:
  - Commit: d4e5f6g - Completed template structure + started auth models
  - GitHub: #458 closed, #468 updated (50% complete)
  - Tests: test_user_model_registration passing, test_organization_model_registration passing
  - File refs: templates/saas-starter/models/user.py:1-45, models/organization.py:1-38
```

**Friday (Retrospective Day):**
```
📅 Daily Update - Nov 1, 2025 - [Name]

✅ COMPLETED TODAY:
  - TODO-[XXX]: COMPLETE ✅
  - Weekly retrospective participation (1h)
  - Week 1 complete - all planned tasks done

🚧 IN PROGRESS:
  - None - clean slate for Week 2

⏭️ NEXT WEEK:
  - Monday: Start TODO-[YYY]
  - Continue making good progress

❓ BLOCKERS/QUESTIONS:
  - None

📊 HOURS:
  - Today: 2h
  - This week: 20h (hit target!)
  - Sprint total: 20h (25% of sprint complete)

💭 REFLECTION:
  - Week 1 went well, hit all targets
  - Pairing with [teammate] was productive
  - Ready for Week 2

🎉 Looking forward to Week 2!
```

---

### Week 4 Templates (Beta Testing Week)

**Monday (Recruiting):**
```
📅 Daily Update - Nov 18, 2025 - Kaizen Dev

✅ COMPLETED TODAY:
  - TODO-012: Recruiting progress
    - Sent recruitment emails to 20 people (15 existing users, 5 new contacts)
    - Posted in r/devops, r/Python
    - Created testing script (final draft)
    - Created feedback survey (Google Forms)
  - Scheduled testing sessions:
    - Tuesday 2pm: 5 IT professionals
    - Wednesday 2pm: 5 developers

🚧 IN PROGRESS:
  - TODO-012: 85% complete
    - Have 8 confirmed testers, need 2 more
    - Following up with 5 maybes

⏭️ TOMORROW:
  - Finalize 10 testers (send reminders)
  - Prepare Zoom rooms and materials
  - Brief DataFlow and Nexus devs on their roles (facilitator vs support)

❓ BLOCKERS/QUESTIONS:
  - Slight concern: Only 8 confirmed so far
  - Backup plan: Proceed with 8 if can't get 10 by tomorrow AM

📊 HOURS:
  - Today: 6h (recruiting is time-consuming!)
  - This week: 6h
  - Sprint total: 54h

🔗 EVIDENCE:
  - Testing script: templates/saas-starter/BETA-TESTING-SCRIPT.md
  - Survey: [Google Forms link]
  - Tester list: 8 confirmed, 5 pending
```

**Friday (Decision Day):**
```
📅 Daily Update - Nov 22, 2025 - All Team

✅ SPRINT 1 COMPLETE:
  - TODO-015: Go/No-Go decision made → **GO** ✅
  - NPS: 42 (exceeded target of 35)
  - Time-to-first-screen: 85% <30 min (exceeded 80% target)
  - AI customization: 70% success (hit target exactly)
  - Component install: 100% (perfect)

  **Decision:** Proceed to full MVR (Phases 1-4)

  **Confidence:** HIGH (85%) - all metrics exceeded targets

  **Adjustments for Phase 1:**
  1. Improve .env setup (add interactive prompts)
  2. Add deployment guide to CUSTOMIZE.md
  3. Enhance pattern embedding for Claude Code

🚧 IN PROGRESS:
  - Phase 1 planning (next Monday kickoff)

⏭️ NEXT WEEK:
  - Phase 1 kickoff meeting (Monday)
  - Start implementing adjustments from beta feedback
  - Begin template refinement work

🎉 CELEBRATION:
  - Prototype successful!
  - Team worked great together!
  - Excited for Phase 1!

📊 SPRINT 1 TOTALS:
  - DataFlow dev: 62h (slightly over 60h estimate)
  - Nexus dev: 38h (on estimate)
  - Kaizen dev: 58h (on estimate)
  - Total: 158h (vs 80h original - more realistic estimate for thorough validation)

💭 LEARNINGS:
  - Prototype takes longer than estimated (2x) but provides invaluable validation
  - Pairing works well (will continue in Phase 1)
  - Beta testing data is gold (clear decision possible)

🚀 Onward to Phase 1!
```

---

## Retrospective Formats

### Start/Stop/Continue (Simple)

**START doing:**
- Shorter pair sessions (90 min instead of 2h)
- Design reviews before implementation (get input early)

**STOP doing:**
- Working beyond planned hours (rest is important)
- Skipping daily updates (breaks visibility)

**CONTINUE doing:**
- Pairing on complex tasks (works well)
- Using subagent workflows (ensures quality)
- Daily async updates (good communication)

### 4Ls (Detailed)

**Liked:**
- Pairing between DataFlow and Nexus devs
- Claude Code testing of Golden Patterns
- Clear task breakdown (easy to know what's next)

**Learned:**
- Estimates need 20-30% buffer (tasks take longer)
- Beta testing requires more prep than expected
- AI instructions need iteration (test with Claude Code)

**Lacked:**
- Earlier design input (Nexus dev input late in TODO-001)
- Deployment guide in CUSTOMIZE.md (beta testers asked for it)

**Longed for:**
- More time for quality polish (always rushing)
- Automated sync between GitHub and local todos

---

## Meeting Best Practices

### Making Meetings Effective

**Before meeting:**
- [ ] Agenda shared 24h advance
- [ ] Materials distributed (data, documents)
- [ ] Attendees prepared (read materials)

**During meeting:**
- [ ] Start on time (respect schedules)
- [ ] Follow agenda (stay on topic)
- [ ] Timebox discussions (use timer)
- [ ] Document decisions (who writes notes)
- [ ] Assign action items (who, what, when)

**After meeting:**
- [ ] Notes shared within 2 hours
- [ ] Action items tracked (GitHub issues or todos)
- [ ] Decisions documented (ADRs if architectural)

### When to Meet Synchronously

**Sync meetings needed for:**
- Complex decisions (Go/No-Go)
- Conflict resolution (async doesn't work)
- Brainstorming (real-time collaboration)
- Celebration (team bonding)

**Async works for:**
- Status updates (daily updates)
- Code reviews (GitHub PRs)
- Simple questions (Slack)
- Information sharing (documents)

**Default to async, meet synchronously when needed.**

---

## Key Coordination Moments

### Week 1: High Coordination (Pairing Intensive)

**Touchpoints:**
- Monday: Kickoff (1h sync)
- Monday PM: Pair session 1 (2h sync)
- Tuesday: Daily updates (async)
- Wednesday PM: Pair session 2 (2h sync)
- Thursday: Daily updates (async)
- Friday PM: Pair session 3 (2h sync) + retrospective (1h sync)

**Total sync time: 8 hours (high but necessary for pairing)**

### Week 2-3: Medium Coordination

**Touchpoints:**
- Monday: Weekly standup (30 min sync)
- Daily: Updates (async)
- As needed: Quick syncs (15-30 min)
- Friday: Retrospective (1h sync)

**Total sync time: 2-3 hours (sustainable)**

### Week 4: High Coordination (Beta Testing)

**Touchpoints:**
- Monday: Standup + beta prep (1h sync)
- Tuesday PM: Beta session 1 (3h sync, all 3)
- Wednesday PM: Beta session 2 (3h sync, all 3)
- Thursday: Analysis (mostly async)
- Friday AM: Decision meeting (2h sync)
- Friday PM: Retrospective (1h sync)

**Total sync time: 10 hours (acceptable for critical decision week)**

---

## Sprint 1 Success Checklist

**Week 1:**
- [ ] All 3 developers complete their Week 1 tasks
- [ ] Pairing is productive (positive feedback)
- [ ] Daily updates posted every day
- [ ] Retrospective identifies learnings

**Week 2:**
- [ ] Template works end-to-end (generate, configure, run)
- [ ] CUSTOMIZE.md complete and reviewed
- [ ] Patterns documented and reviewed

**Week 3:**
- [ ] kailash-dataflow-utils published to PyPI
- [ ] Patterns embedded in template
- [ ] End-to-end integration tested

**Week 4:**
- [ ] 10 beta testers recruited and tested
- [ ] Data collected and analyzed
- [ ] Go/No-Go decision made
- [ ] Next steps planned

**If all checked: Sprint 1 successful, ready for Phase 1 (if GO)**

---

## Templates Quick Reference

**Daily update:** 5 min/day, async, format above
**Weekly standup:** 30 min/week, sync, Monday 10am
**Retrospective:** 1 hour/week, sync, Friday 4pm
**Quality gate:** 2 hours, sync, end of phase

**Use templates consistently. Adjust as needed. Focus on communication quality, not format perfection.**

---

**These templates are tools, not rules. Adapt to what works for your team. The goal is clarity and coordination, not bureaucracy.**
