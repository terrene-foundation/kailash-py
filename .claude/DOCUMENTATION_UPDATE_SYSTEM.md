# Documentation Update System - Quick Start

**Purpose**: Systematic update of 676+ documentation files with "one mistake = disaster" quality level.

**Status**: ✅ System complete and ready for use
**Files Updated**: 25/676 (3.7%)
**Files Remaining**: 651 (96.3%)

---

## 🚀 Quick Start (3 Steps)

### Step 1: Read the Guidelines (30 minutes)
```bash
open .claude/SYSTEMATIC_UPDATE_GUIDELINES.md
```

**What you'll learn**:
- 8 common update patterns to apply
- 7 file type templates to use
- 10 canonical technical facts (exact wording)
- 10 batch definitions (priority order)
- 5 quality gates between batches

### Step 2: Validate Current State (2 minutes)
```bash
# Test validation script on completed file
python .claude/validate_skill.py .claude/skills/01-core-sdk/workflow-quickstart.md

# Validate entire directory
python .claude/validate_skill.py --batch .claude/skills/01-core-sdk/
```

### Step 3: Start First Batch (Following Guidelines)
```bash
# Create branch for Batch 1
git checkout -b update/batch-1-core-sdk

# Apply Template A from Section 2 of guidelines
# Use canonical facts from Section 3
# Validate each file after update

# When batch complete, run quality gates
python .claude/validate_skill.py --batch .claude/skills/01-core-sdk/
```

---

## 📁 System Files

### 1. Main Guidelines (READ THIS FIRST)
**File**: `SYSTEMATIC_UPDATE_GUIDELINES.md` (25,000+ words)

**Contents**:
```
Section 1: Common Update Patterns (8 patterns)
Section 2: Update Templates by File Type (7 templates)
Section 3: Technical Facts - Canonical Descriptions (10 facts)
Section 4: Validation Criteria (comprehensive checklist)
Section 5: Batch Update Strategy (10 batches)
Section 6: Quality Gates (5 gates)
Section 7: Common Mistakes to Avoid (10 mistakes)
Section 8: Automated Validation Script (code)
Section 9: Execution Strategy (3 phases)
Section 10: Progress Tracking Template
Section 11: Emergency Rollback Procedure
Section 12: Success Criteria
```

### 2. Validation Script (AUTOMATION)
**File**: `validate_skill.py` (283 lines)

**Checks**:
- ✅ YAML frontmatter present
- ✅ Skill Metadata block present
- ✅ Required sections exist
- ✅ No deprecated patterns
- ✅ Execution patterns include .build()
- ✅ Absolute imports only
- ✅ Code blocks syntactically valid
- ✅ Internal links work

**Usage**:
```bash
# Single file
python .claude/validate_skill.py path/to/file.md

# Batch directory
python .claude/validate_skill.py --batch path/to/dir/
```

### 3. System Overview (THIS FILE)
**File**: `DOCUMENTATION_UPDATE_SYSTEM.md`

Quick navigation and system overview.

### 4. Detailed Summary
**File**: `UPDATE_SUMMARY.md` (4,000+ words)

Comprehensive analysis of patterns, insights, and usage instructions.

---

## 🎯 Batch Processing Order

### Priority 1: CRITICAL (Completed ✅)
- ✅ **Batch 4**: Error Troubleshooting (7 files)
- ✅ **Batch 5**: Gold Standards (10 files)

### Priority 2: HIGH (Next to Process)
1. **Batch 1**: Core SDK Skills (14 files)
   - Focus: LocalRuntime, WorkflowBuilder patterns
   - Template: A (Core SDK)
   - Includes: BaseRuntime architecture

2. **Batch 2**: DataFlow Skills (25 files)
   - Focus: Zero-config database framework
   - Template: B (DataFlow)
   - Includes: 9 nodes per model, NOT an ORM

3. **Batch 3**: Nexus Skills (24 files)
   - Focus: Multi-channel platform
   - Template: C (Nexus)
   - Includes: Zero-config, always .build()

### Priority 3: MEDIUM
- **Batch 6**: Node References (10 files)
- **Batch 7**: Cheatsheets (35 files)

### Priority 4: LOW
- **Batch 8**: Workflow Patterns (15 files)
- **Batch 9**: Development Guides (30 files)
- **Batch 10**: Other Categories (remaining files)

---

## 📊 File Counts by Category

```
Total Files: 676
├─ Skill Files: ~224
│  ├─ 01-core-sdk: 14 files (HIGH) ← Start here
│  ├─ 02-dataflow: 25 files (HIGH)
│  ├─ 03-nexus: 24 files (HIGH)
│  ├─ 04-kaizen: 25 files (MEDIUM)
│  ├─ 05-mcp: 6 files (MEDIUM)
│  ├─ 06-cheatsheets: 35 files (MEDIUM)
│  ├─ 07-development-guides: 30 files (LOW)
│  ├─ 08-nodes-reference: 10 files (MEDIUM)
│  ├─ 09-workflow-patterns: 15 files (LOW)
│  ├─ 10-deployment-git: 2 files (LOW)
│  ├─ 11-frontend-integration: 2 files (LOW)
│  ├─ 12-testing-strategies: 1 file (MEDIUM)
│  ├─ 13-architecture-decisions: 5 files (MEDIUM)
│  ├─ 14-code-templates: 7 files (MEDIUM)
│  ├─ 15-error-troubleshooting: 7 files (CRITICAL) ✅
│  ├─ 16-validation-patterns: 6 files (HIGH)
│  └─ 17-gold-standards: 10 files (CRITICAL) ✅
└─ Other Documentation: ~452 files
```

---

## 🔑 10 Canonical Technical Facts

**CRITICAL**: Copy these EXACTLY when updating files (from Section 3 of guidelines)

### Fact 1: BaseRuntime Architecture
```markdown
Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use shared mixins:

- **BaseRuntime**: Provides 29 configuration parameters, execution metadata, workflow caching
- **ValidationMixin**: Shared validation logic (workflow validation, connection contracts, conditional execution)
- **ParameterHandlingMixin**: Shared parameter resolution (${param} templates, type preservation, deep merge)

This architecture ensures consistent behavior between sync and async runtimes.
```

### Fact 2-10: Runtime Returns, String-Based Nodes, Connections, Execution, DataFlow, Imports, Versions
*(See Section 3 of SYSTEMATIC_UPDATE_GUIDELINES.md for complete list)*

---

## 📝 Standard File Structure (Template)

Every skill file should have:

```markdown
---
name: skill-name
description: "Brief description with trigger keywords"
---

# Skill Title

One-line description.

> **Skill Metadata**
> Category: `category-name`
> Priority: `CRITICAL|HIGH|MEDIUM|LOW`
> SDK Version: `0.9.25+`
> Related Skills: [links]
> Related Subagents: agent-name

## Quick Reference
[Key info for quick lookup]

## Core Pattern
[Minimal working code example]

## Key Parameters / Options
[Parameter documentation]

## Common Use Cases
[List of use cases]

## Common Mistakes
[❌ Wrong vs ✅ Correct examples]

## Related Patterns
[Links to related skills]

## When to Escalate to Subagent
[Guidance on subagent usage]

## Documentation References
[Links to sdk-users/ docs]

## Quick Tips
[Actionable tips]

## Keywords for Auto-Trigger
<!-- Trigger Keywords: keyword1, keyword2 -->
```

---

## ✅ Validation Checklist (Per File)

Before considering a file "complete":

### Structure
- [ ] YAML frontmatter with name and description
- [ ] Skill Metadata block (category, priority, SDK version)
- [ ] Quick Reference section
- [ ] Core Pattern with working code
- [ ] Common Mistakes section (❌/✅ examples)
- [ ] Related Patterns section
- [ ] Documentation References section
- [ ] Trigger keywords at bottom

### Technical Accuracy
- [ ] String-based node API (`"NodeName"` not `NodeClass()`)
- [ ] `runtime.execute(workflow.build())` pattern
- [ ] 4-parameter connections
- [ ] Correct SDK versions
- [ ] Absolute imports only
- [ ] Correct documentation links
- [ ] BaseRuntime architecture (if runtime-related)

### Code Quality
- [ ] All examples syntactically valid
- [ ] Current API patterns (not deprecated)
- [ ] Necessary imports included
- [ ] Minimal but complete examples
- [ ] Follows gold standards

### Links & References
- [ ] All internal links valid
- [ ] Relative paths correct
- [ ] sdk-users/ links correct
- [ ] Source code line numbers (if specific)
- [ ] No broken links

---

## 🚀 Example Workflow (Batch 1: Core SDK)

### Step-by-Step Process

```bash
# 1. Create branch
git checkout -b update/batch-1-core-sdk

# 2. For each file in .claude/skills/01-core-sdk/*.md:

# 2a. Read current file
open .claude/skills/01-core-sdk/async-workflow-patterns.md

# 2b. Apply Template A from guidelines Section 2
# - Add YAML frontmatter if missing
# - Add Skill Metadata block
# - Add Quick Reference section
# - Update Core Pattern section
# - Add Common Mistakes section
# - Add Related Patterns section
# - Add Documentation References section
# - Add trigger keywords

# 2c. Insert canonical facts from guidelines Section 3
# - BaseRuntime architecture (for runtime files)
# - String-based node API
# - 4-parameter connections
# - Execution pattern with .build()

# 2d. Validate file
python .claude/validate_skill.py .claude/skills/01-core-sdk/async-workflow-patterns.md

# 2e. Fix any errors reported

# 2f. Extract and test code examples
# Create /tmp/test_async_workflow.py
# Add code from file
# Run pytest /tmp/test_async_workflow.py

# 2g. Commit individual file
git add .claude/skills/01-core-sdk/async-workflow-patterns.md
git commit -m "docs: Update async-workflow-patterns.md"

# 3. After all files in batch:

# 3a. Batch validation
python .claude/validate_skill.py --batch .claude/skills/01-core-sdk/

# 3b. Run quality gates (Section 6 of guidelines)
# - Structural validation
# - Technical accuracy check
# - Code example validation
# - Link validation
# - Consistency check

# 3c. Final commit and merge
git push origin update/batch-1-core-sdk
# Create PR, review, merge to main

# 4. Update progress tracking (Section 10 of guidelines)
```

---

## ⚠️ Common Mistakes to Avoid

### Top 10 Mistakes (From Guidelines Section 7)

1. **Inconsistent Technical Facts**
   - ❌ Different descriptions of BaseRuntime
   - ✅ Copy canonical facts exactly

2. **Missing .build() in Examples**
   - ❌ `runtime.execute(workflow)`
   - ✅ `runtime.execute(workflow.build())`

3. **Using Deprecated API Patterns**
   - ❌ Instance-based nodes, 3-param connections
   - ✅ String-based nodes, 4-param connections

4. **Broken Documentation Links**
   - ❌ Wrong relative paths to sdk-users/
   - ✅ Verify paths from skill file location

5. **Missing Common Mistakes Section**
   - ❌ Only showing correct examples
   - ✅ Show wrong vs correct patterns

6. **Outdated SDK Versions**
   - ❌ Referencing v0.8.0
   - ✅ Use current v0.9.25+

7. **No Quick Reference**
   - ❌ Diving into details immediately
   - ✅ Start with Quick Reference section

8. **Untested Code Examples**
   - ❌ Assuming examples work
   - ✅ Extract and test every example

9. **Missing Keywords**
   - ❌ No trigger keywords at bottom
   - ✅ Include comprehensive keywords

10. **Relative Imports in Examples**
    - ❌ `from ..workflow.builder`
    - ✅ `from kailash.workflow.builder`

---

## 🎓 Quality Gates (Between Batches)

Before merging each batch, run these 5 gates:

### Gate 1: Structural Validation
```bash
for file in batch/*.md; do
  grep -q "## Quick Reference" "$file" || echo "MISSING: $file"
  grep -q "## Core Pattern" "$file" || echo "MISSING: $file"
  grep -q "## Common Mistakes" "$file" || echo "MISSING: $file"
done
```

### Gate 2: Technical Accuracy
```bash
grep -r "workflow.execute(" batch/*.md && echo "ERROR: Wrong pattern"
grep -r "from \.\." batch/*.md && echo "ERROR: Relative imports"
```

### Gate 3: Code Example Validation
```bash
for file in batch/*.md; do
  python extract_and_test_examples.py "$file"
done
```

### Gate 4: Link Validation
```bash
for file in batch/*.md; do
  python validate_links.py "$file"
done
```

### Gate 5: Consistency Check
```bash
grep -r "pipeline" batch/*.md && echo "WARNING: Use 'workflow'"
```

---

## 📈 Progress Tracking

### Current Status
- **Total files**: 676
- **Completed**: 25 (3.7%)
  - Error Troubleshooting: 7/7 ✅
  - Gold Standards: 10/10 ✅
  - Core SDK: 5/14 partial
  - DataFlow: 1/25 partial
  - Nexus: 1/24 partial
  - Node References: 1/10 partial
- **Remaining**: 651 (96.3%)

### Next Priorities
1. Complete Batch 1 (Core SDK) - 9 files remaining
2. Complete Batch 2 (DataFlow) - 24 files remaining
3. Complete Batch 3 (Nexus) - 23 files remaining

### Estimated Time
- **With system**: ~10 min per file = 108 hours
- **Without system**: ~30 min per file = 325 hours
- **Savings**: 217 hours (67% reduction)

---

## 🆘 Emergency Rollback

If a batch introduces issues:

```bash
# 1. Create rollback branch
git checkout main
git checkout -b rollback/batch-N [commit-before-batch]

# 2. Identify issues
git diff [commit-before-batch]..HEAD --name-only

# 3. Force push rollback
git push origin main --force

# 4. Document
echo "Batch N rolled back: [reason]" >> ROLLBACK_LOG.md

# 5. Fix in new branch
git checkout -b fix/batch-N-issues
# Apply corrections
# Re-validate
# Merge when clean
```

---

## 💡 Tips for Success

### Before Starting
1. ✅ Read guidelines completely (30 min investment saves hours later)
2. ✅ Understand canonical facts (Section 3)
3. ✅ Familiarize with templates (Section 2)
4. ✅ Test validation script on completed files

### During Updates
1. ✅ Process files sequentially (avoid merge conflicts)
2. ✅ Copy-paste canonical facts (don't paraphrase)
3. ✅ Validate each file immediately after update
4. ✅ Test code examples before committing
5. ✅ Check links are valid

### After Each Batch
1. ✅ Run batch validation
2. ✅ Run all 5 quality gates
3. ✅ Update progress tracking
4. ✅ Commit with clear message
5. ✅ Merge only when gates pass

---

## 📞 Getting Help

### System Documentation
- **Main guidelines**: `SYSTEMATIC_UPDATE_GUIDELINES.md` (comprehensive)
- **Summary**: `UPDATE_SUMMARY.md` (key insights)
- **This file**: `DOCUMENTATION_UPDATE_SYSTEM.md` (quick start)

### Validation Issues
```bash
# Run validation script for detailed error messages
python .claude/validate_skill.py path/to/file.md
```

### Pattern Questions
- Check Section 1 (Common Update Patterns) in guidelines
- Check Section 2 (Templates) for file type examples
- Check Section 3 (Technical Facts) for exact wording

### Process Questions
- Check Section 9 (Execution Strategy) in guidelines
- Check Section 5 (Batch Update Strategy) for order
- Check Section 6 (Quality Gates) for validation

---

## 🎯 Success Criteria

### Per Batch
- [ ] All files have required sections
- [ ] All code examples tested
- [ ] All links verified
- [ ] No deprecated patterns
- [ ] Consistent terminology
- [ ] All 5 quality gates pass

### Overall Project
- [ ] 676 files updated
- [ ] 100% structural compliance
- [ ] 100% code examples tested
- [ ] Zero broken links
- [ ] Zero deprecated patterns
- [ ] Consistent technical facts

---

## 🚀 Ready to Start?

1. **Read**: Open `SYSTEMATIC_UPDATE_GUIDELINES.md`
2. **Test**: Run `python .claude/validate_skill.py` on sample file
3. **Start**: Begin with Batch 1 (Core SDK Skills)
4. **Follow**: Use templates from Section 2
5. **Validate**: Check each file before committing
6. **Track**: Update progress after each batch

**Remember**: "One mistake = disaster" - Quality over speed. Triple-check everything.

---

**System Status**: ✅ Complete and ready for use
**Created**: 2025-10-25
**Based on**: Analysis of 25 completed CRITICAL files
**Confidence**: High (validated on real files)

**Files in This System**:
- `DOCUMENTATION_UPDATE_SYSTEM.md` (this file) - Quick start
- `SYSTEMATIC_UPDATE_GUIDELINES.md` - Comprehensive guidelines (25k+ words)
- `validate_skill.py` - Automated validation (283 lines)
- `UPDATE_SUMMARY.md` - Detailed analysis (4k+ words)

**Start Here**: Read `SYSTEMATIC_UPDATE_GUIDELINES.md` Section 1-3, then begin Batch 1.
