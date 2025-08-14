# Project Board #56 Update Reference

## Field IDs (from GraphQL query)

### Status Field
- **Field ID**: `PVTSSF_lADOBRwFFs4A5KqhzguAt_8`
- **Options**:
  - Backlog: `f75ad846`
  - Ready: `08afe404`  
  - In progress: `47fc9ee4`
  - In review: `4cc61d42`
  - Done: `98236657`

### Priority Field  
- **Field ID**: `PVTSSF_lADOBRwFFs4A5KqhzguAuEw`
- **Options**:
  - P0: `79628723`
  - P1: `0a877460` 
  - P2: `da944a9c`

### Date Fields
- **Start Date**: `PVTF_lADOBRwFFs4A5KqhzguAuFA`
- **End Date**: `PVTF_lADOBRwFFs4A5KqhzguAuFE`

## Current Status Analysis

### Issues to Add by Category:

#### ✅ Completed Issues (Set to "Done" status):
- **#200**: AsyncSQL Lock Contention Fix (v0.9.17) - **P1 Priority**
- **#213-384**: 162 completed todo issues - **P2 Priority**

#### 🔄 Active Issues (Set appropriate active status):

**High Priority (P1) - Ready/In Progress:**
- **#201**: PostgreSQL Tier 1 Violations Fix → **In Progress**
- **#203**: PythonCodeNode Serialization Fix → **Ready** 
- **#210**: Application Documentation & Standards → **Ready**
- **#211**: RAG Toolkit Testing → **Ready**

**Medium Priority (P2) - Ready/Backlog:**
- **#202**: Production-Ready Framework → **Ready**
- **#204**: MCP Forge Ecosystem → **Backlog**
- **#205**: Unimplemented SDK Components → **Backlog**
- **#206**: DataFlow Integration Enhancements → **Backlog**
- **#207**: A/B Testing with Claude Code → **Backlog**
- **#208**: Workflow Library Expansion → **Backlog**

**Note**: Issues #209 and #212 are CLOSED, so they won't be added.

## Quick Commands

### 1. Get Current Project Status
```bash
gh project view 56 --owner terrene-foundation --format json
gh project item-list 56 --owner terrene-foundation --format json
```

### 2. Add Single Issue
```bash
gh project item-add 56 --owner terrene-foundation --url https://github.com/terrene-foundation/kailash-py/issues/[NUMBER]
```

### 3. Update Item Status/Priority
```bash
# Get item ID first
ITEM_ID=$(gh project item-list 56 --owner terrene-foundation --format json | jq -r '.items[] | select(.content.number==[ISSUE_NUMBER]) | .id')

# Set status to Done
gh project item-edit --id $ITEM_ID --field-id PVTSSF_lADOBRwFFs4A5KqhzguAt_8 --single-select-option-id 98236657

# Set priority to P1  
gh project item-edit --id $ITEM_ID --field-id PVTSSF_lADOBRwFFs4A5KqhzguAuEw --single-select-option-id 0a877460
```

### 4. Set Dates
```bash
# Set start date (YYYY-MM-DD format)
gh project item-edit --id $ITEM_ID --field-id PVTF_lADOBRwFFs4A5KqhzguAuFA --date "2025-08-14"

# Set end date  
gh project item-edit --id $ITEM_ID --field-id PVTF_lADOBRwFFs4A5KqhzguAuFE --date "2025-08-20"
```

## Execution Plan

### Option 1: Full Automated Script
```bash
./update_project_board.sh
```

### Option 2: Quick Add Then Manual Organization
```bash
./quick_project_update.sh
```

### Option 3: Manual Step-by-Step
1. Add completed issue #200
2. Add active issues #201-211 (skip #209, #212 - closed)
3. Batch add completed issues #213-384
4. Update statuses for completed issues to "Done"
5. Set appropriate statuses for active issues
6. Set priorities based on urgency/content
7. Add timeline dates based on historical completion

## Project URL
https://github.com/orgs/terrene-foundation/projects/56