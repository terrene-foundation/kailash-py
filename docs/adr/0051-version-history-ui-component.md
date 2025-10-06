# ADR-0051: Version History UI Component Architecture

## Status
Proposed

## Context

### Business Need
Kailash Studio's Enterprise-First prioritization (Tier 2B) requires visual version control capabilities for workflows. This feature unlocks $30K in enterprise value by providing:
- **Audit Compliance**: Complete visual history of workflow changes for SOC 2, HIPAA, GDPR
- **Risk Management**: Safe rollback capabilities for production workflows
- **Collaboration**: Clear visibility into who changed what and why
- **Quality Assurance**: Compare versions to understand impact of changes

### Technical Context
**Backend Foundation (Completed)**:
- WorkflowVersion DataFlow model with 9 auto-generated nodes
- Complete REST API (`/api/workflow-versions`) with CRUD operations
- Snapshot-based storage (delta compression deferred to future optimization)
- Multi-tenant isolation with organization-based access control
- 47 passing backend tests validating all version control operations

**Frontend Requirements**:
- Visual timeline showing version history chronologically
- Side-by-side diff view comparing two versions
- Rollback functionality with preview and confirmation
- Performance: <100ms UI rendering, <500ms diff calculation
- Integration: WorkflowCanvas, Zustand store, React Flow

### Strategic Context
This feature is part of Kailash Studio's progressive enterprise feature rollout:
1. ✅ Phase 1: Core visual workflow editor (WorkflowCanvas)
2. ✅ Phase 2A: Real-time collaboration (WebSocket)
3. **→ Phase 2B: Version control UI (THIS ADR)** ← $30K value unlock
4. Phase 3: Advanced analytics and marketplace

Version control UI is a critical enterprise requirement that directly impacts sales cycles and customer retention.

## Decision

We will implement a **drawer-based version history panel** with three progressive feature layers:

### Architecture Decision: Drawer-Based Progressive Disclosure

```
┌─────────────────────────────────────────────────────────────┐
│                    Kailash Studio UI                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────┐  ┌───────────────────────────┐  │
│  │                      │  │ Version History Panel     │  │
│  │   WorkflowCanvas     │  │ (Drawer from right)       │  │
│  │                      │  │                           │  │
│  │   [Nodes & Edges]    │  │ Layer 1: Timeline         │  │
│  │                      │  │ - Version cards           │  │
│  │                      │  │ - Metadata display        │  │
│  │   Performance:       │  │ - Pagination              │  │
│  │   - <100ms render    │  │                           │  │
│  │   - 1000+ nodes      │  │ Layer 2: Comparison       │  │
│  │                      │  │ - Select 2 versions       │  │
│  │                      │  │ - Diff calculation        │  │
│  │                      │  │ - Visual highlights       │  │
│  │  [Version History]   │  │                           │  │
│  │      Button          │  │ Layer 3: Rollback         │  │
│  └──────────────────────┘  │ - Preview modal           │  │
│                            │ - Confirmation flow       │  │
│                            │ - Execution & feedback    │  │
│                            └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

Integration Points:
├── Zustand Store (state management)
├── Backend API (/api/workflow-versions)
├── React Flow (diff visualization)
└── NotificationToast (feedback)
```

### Key Architectural Decisions

#### 1. Drawer Pattern (Not Modal or Sidebar)
**Decision**: Use slide-in drawer from right side of screen

**Rationale**:
- **Contextual**: Keeps workflow visible while browsing versions
- **Non-blocking**: Users can still see workflow being versioned
- **Mobile-friendly**: Drawer pattern works on tablets (iPad)
- **Studio Convention**: Matches PropertyPanel pattern in Studio

**Rejected Alternatives**:
- ❌ Full modal: Blocks workflow view, poor UX for comparison
- ❌ Persistent sidebar: Takes up screen real estate permanently
- ❌ Inline timeline: Clutters canvas, conflicts with collaboration UI

#### 2. Virtual Scrolling for Timeline
**Decision**: Use `react-window` for version list rendering

**Rationale**:
- **Performance**: Handles 1000+ versions without DOM bloat
- **Memory**: Only renders visible items (~15-20 cards)
- **Smooth scrolling**: No janky rendering or lag
- **Industry standard**: Proven library, well-maintained

**Performance Impact**:
- Without virtualization: 1000 cards = 30MB DOM + 2000ms render
- With virtualization: 20 cards = 1MB DOM + 50ms render

#### 3. Two-Phase Diff Calculation
**Decision**: Calculate summary immediately, details on-demand

**Rationale**:
- **Perceived performance**: Show "2 nodes added, 1 deleted" instantly (<50ms)
- **Actual performance**: Full parameter diff only when user expands
- **Memory efficiency**: Don't hold full diff in memory unless needed

**Implementation**:
```typescript
// Phase 1: Fast summary (50ms for 100 nodes)
const summary = {
  nodesAdded: countAdded(versionA.nodes, versionB.nodes),
  nodesDeleted: countDeleted(versionA.nodes, versionB.nodes),
  nodesModified: countModified(versionA.nodes, versionB.nodes),
};

// Phase 2: Detailed diff (lazy, on click)
const handleNodeClick = async (nodeId) => {
  const parameterDiff = await computeParameterDiff(nodeId);
  setExpandedDiff(parameterDiff);
};
```

#### 4. Rollback as New Version (Not In-Place Modification)
**Decision**: Rollback creates a NEW version, doesn't delete existing versions

**Rationale**:
- **Audit trail**: Complete history preserved for compliance
- **Safety**: Can rollback the rollback if mistake made
- **Clarity**: Version numbers always increase (no gaps)
- **Backend design**: Matches WorkflowVersion model semantics

**User Experience**:
```
Before rollback:
  v1 → v2 → v3 → v4 → v5 (current)

After rollback to v3:
  v1 → v2 → v3 → v4 → v5 → v6 (new current, snapshot from v3)
                           ↑ metadata: { rollback_to_version: 3 }
```

#### 5. Zustand Store Integration (Not Separate Context)
**Decision**: Extend existing `useWorkflowStore` with version history slice

**Rationale**:
- **Single source of truth**: All workflow-related state in one store
- **Performance**: Zustand's selector-based rendering prevents unnecessary re-renders
- **Consistency**: Follows Studio's established state management pattern
- **Debugging**: Single DevTools instance for all workflow state

**Store Structure**:
```typescript
interface WorkflowStore {
  // Existing state...
  current_workflow: Workflow | null;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];

  // NEW: Version history slice
  versionHistory: {
    versions: WorkflowVersion[];
    selectedVersionIds: string[];
    diffData: DiffResult | null;
    rollbackInProgress: boolean;
    // ... actions
  };
}
```

#### 6. Color + Icon Diff Indicators (Accessibility)
**Decision**: Use BOTH color and icons for change types

**Rationale**:
- **Accessibility**: Colorblind users can distinguish changes
- **WCAG AA**: Meets accessibility standards
- **Clarity**: Icons reinforce meaning (➕ = added, ➖ = deleted, ✏️ = modified)

**Implementation**:
```typescript
const DiffNode = ({ changeType }: { changeType: 'added' | 'deleted' | 'modified' }) => (
  <div className={`border-2 ${getBorderColor(changeType)}`}>
    <Icon name={getChangeIcon(changeType)} />
    <span>{changeType}</span>
  </div>
);

const getBorderColor = (type) => ({
  added: 'border-green-500',
  deleted: 'border-red-500',
  modified: 'border-yellow-500',
}[type]);

const getChangeIcon = (type) => ({
  added: 'plus-circle',
  deleted: 'minus-circle',
  modified: 'edit',
}[type]);
```

## Consequences

### Positive Consequences

#### Immediate Benefits
1. **Enterprise Sales**: $30K value unlock through version control feature
2. **Compliance**: Meets audit trail requirements for SOC 2, HIPAA, GDPR
3. **User Confidence**: Safe rollback reduces fear of breaking workflows
4. **Developer Productivity**: Visual diff accelerates change understanding

#### Technical Benefits
1. **Code Reuse**: Leverages existing WorkflowCanvas for preview/diff
2. **Performance**: Virtual scrolling handles large version histories efficiently
3. **Maintainability**: Single state management approach (Zustand)
4. **Testability**: Clear component boundaries enable TDD

#### User Experience Benefits
1. **Contextual**: Drawer keeps workflow visible during version browsing
2. **Progressive Disclosure**: Simple timeline → advanced diff → rollback
3. **Accessible**: WCAG AA compliant with keyboard navigation
4. **Responsive**: Works on desktop, tablet (iPad), future mobile

### Negative Consequences

#### Development Complexity
1. **Virtual Scrolling**: Requires careful implementation to avoid scroll jank
   - **Mitigation**: Use `react-window`, follow official docs, performance testing

2. **Diff Algorithm**: Complex logic for deep parameter comparison
   - **Mitigation**: Use `deep-object-diff` library, extensive unit tests

3. **State Management**: Version history state adds complexity to store
   - **Mitigation**: Clear slice boundaries, isolated actions, devtools debugging

#### Operational Challenges
1. **Memory**: Large workflows (1000+ nodes) in diff view consume memory
   - **Mitigation**: Lazy loading, progressive rendering, memory profiling

2. **Network**: Loading many versions can be bandwidth-intensive
   - **Mitigation**: Pagination (50 per page), metadata-only initial load

3. **Storage**: Snapshot-based storage grows with version count
   - **Mitigation**: Future: delta compression, version archival policy

#### Technical Debt
1. **Browser Support**: Virtual scrolling may have quirks in older browsers
   - **Mitigation**: Target modern browsers (Chrome, Firefox, Safari), graceful degradation

2. **Mobile UX**: Drawer pattern may need adaptation for small screens
   - **Mitigation**: Defer mobile optimization to Phase 4, focus desktop/tablet first

3. **Diff Visualization**: Custom React Flow styling may conflict with updates
   - **Mitigation**: Use React Flow's official theming API, avoid CSS hacks

### Risk Mitigation Strategies

#### Performance Risks
**Risk**: Diff calculation blocks UI for large workflows
- **Mitigation 1**: Web Workers for background diff calculation
- **Mitigation 2**: Progressive rendering (summary first, details on-demand)
- **Mitigation 3**: Performance budget (500ms max for 100-node diff)

**Risk**: Timeline rendering slow for 1000+ versions
- **Mitigation 1**: Virtual scrolling with `react-window`
- **Mitigation 2**: Pagination (50 versions per page)
- **Mitigation 3**: Performance testing with realistic datasets

#### UX Risks
**Risk**: Users confused about rollback semantics (creates new version)
- **Mitigation 1**: Clear messaging in confirmation dialog
- **Mitigation 2**: Visual timeline showing new version after rollback
- **Mitigation 3**: Help tooltips explaining behavior

**Risk**: Diff view overwhelming for complex workflows
- **Mitigation 1**: Change summary panel (counts, not full details)
- **Mitigation 2**: Expandable parameter diff (opt-in complexity)
- **Mitigation 3**: Filter options (show only added/deleted/modified)

#### Integration Risks
**Risk**: Version history panel conflicts with collaboration UI
- **Mitigation 1**: Z-index management, clear visual hierarchy
- **Mitigation 2**: Mutual exclusion (close one when other opens)
- **Mitigation 3**: User testing to validate combined UX

## Alternatives Considered

### Option 1: Git-Style Branch Visualization
**Description**: Show version history as branching tree (like GitHub)
```
    v1 → v2 → v3 → v4 → v5 (main)
              ↓
              v3.1 → v3.2 (feature branch)
```

**Pros**:
- Familiar to developers (Git mental model)
- Supports future branching features
- Visually represents relationships

**Cons**:
- Backend doesn't support branching yet (MVP is linear)
- Complex visualization for non-technical users
- Higher development effort (8h → 16h)

**Rejection Reason**: Over-engineered for MVP. Backend only supports linear history. YAGNI principle applies. Future ADR can revisit when branching needed.

### Option 2: Inline Timeline in Canvas
**Description**: Show version timeline as overlay on workflow canvas
```
┌─────────────────────────────────────┐
│  Workflow Canvas                    │
│                                     │
│  ┌────────────────────────────────┐│
│  │ Timeline Overlay (bottom)      ││
│  │ [v1] [v2] [v3] [v4] [v5]       ││
│  └────────────────────────────────┘│
└─────────────────────────────────────┘
```

**Pros**:
- No screen real estate cost (overlay)
- Minimal navigation required
- Fits in single view

**Cons**:
- Obscures workflow nodes (bad UX)
- Limited space for metadata
- Conflicts with collaboration cursors/selections
- Difficult to show detailed version info

**Rejection Reason**: Poor UX. Overlays clutter canvas and hide important workflow details. Drawer provides dedicated space without conflicts.

### Option 3: Separate Version History Page
**Description**: Navigate to `/workflows/:id/versions` route for history
```
Workflow Editor (/workflows/:id/edit)
    ↓ [View History button]
Version History Page (/workflows/:id/versions)
    ↓ [Back to Editor]
Workflow Editor (/workflows/:id/edit)
```

**Pros**:
- Clean separation of concerns
- Full screen for version timeline
- No layout conflicts

**Cons**:
- Context switching (lose workflow view)
- Multiple round-trips to compare/rollback
- Slower workflow (navigation overhead)
- Doesn't support simultaneous workflow + history view

**Rejection Reason**: Poor user flow. Enterprise users need to see workflow while browsing versions. Context switching breaks mental model.

### Option 4: Modal-Based Approach
**Description**: Open version history in centered modal dialog

**Pros**:
- Focus on version history (no distractions)
- Standard UI pattern (familiar)
- Easier to implement (less layout complexity)

**Cons**:
- Blocks workflow view (can't compare while viewing workflow)
- Bad UX for diff (need to see current workflow)
- Mobile: full-screen modal feels heavy

**Rejection Reason**: Blocks context. Users need to see current workflow while browsing versions. Modal prevents this critical use case.

## Implementation Plan

### Phase 1: Foundation (3h)
**Components**: VersionHistoryPanel, VersionCard, VersionTimeline
**State**: Zustand store extension with version history slice
**API**: Integration with `/api/workflow-versions`
**Tests**: Unit tests for components, integration tests for API

**Deliverables**:
- [ ] Drawer component with open/close behavior
- [ ] Version card showing metadata
- [ ] Timeline with pagination
- [ ] Current version highlighting
- [ ] Loading/error states

### Phase 2: Diff View (3h)
**Components**: DiffViewer, SideBySidePanels, ParameterDiffPanel
**Logic**: Diff calculation algorithm, change detection
**Visualization**: React Flow integration with custom styling
**Tests**: Diff algorithm tests, visual regression tests

**Deliverables**:
- [ ] Select 2 versions for comparison
- [ ] Diff calculation (summary + details)
- [ ] Side-by-side visualization
- [ ] Color + icon change indicators
- [ ] Parameter diff drill-down

### Phase 3: Rollback (2h)
**Components**: RollbackDialog, RollbackPreview
**Flow**: Confirmation dialog, preview, execution, feedback
**API**: POST new version with rollback metadata
**Tests**: Rollback flow tests, error handling tests

**Deliverables**:
- [ ] Rollback confirmation dialog
- [ ] Workflow preview (read-only)
- [ ] Commit message input
- [ ] Rollback execution
- [ ] Success/error notifications

### Total Effort: 8 hours

## Success Metrics

### Performance Metrics
- [ ] Timeline renders 50 versions in <100ms
- [ ] Pagination loads next page in <200ms
- [ ] Diff calculation completes in <500ms (100-node workflows)
- [ ] Rollback operation completes in <1s

### Functional Metrics
- [ ] All 14 functional requirements met (REQ-001 to REQ-014)
- [ ] Test coverage >90% for version history components
- [ ] Zero critical bugs in staging environment

### Adoption Metrics (30 days post-launch)
- [ ] 80% of active users use version history at least once
- [ ] 10+ rollback operations per day
- [ ] 50+ diff comparisons per day
- [ ] >4.0/5 user satisfaction rating

### Business Metrics (90 days)
- [ ] Version history cited in 30% of enterprise demos
- [ ] <5 version history support tickets per week
- [ ] Feature contributes to $30K enterprise value realization

## Dependencies

### Technical Dependencies (Completed)
- ✅ WorkflowVersion DataFlow model
- ✅ Backend API endpoints
- ✅ WorkflowCanvas component
- ✅ Zustand store infrastructure

### New Dependencies (Required)
- `react-window` (virtual scrolling)
- `deep-object-diff` (parameter comparison)
- `date-fns` (timestamp formatting)
- `lucide-react` (icons)

### Team Dependencies
- 1 React developer (8 hours)
- Design assets (version icons, color palette)
- Backend running for integration testing

## Related Documents

### Requirements
- [Version History UI Requirements](./repos/projects/kailash_python_sdk/docs/requirements/version-history-ui-requirements.md)

### Architecture
- [ADR-0050: Kailash Studio Platform Architecture](./repos/projects/kailash_python_sdk/docs/adr/0050-kailash-studio-visual-workflow-platform.md)

### Implementation
- Backend Model: `/apps/kailash-studio/backend/src/kailash_studio/models.py:387-427`
- Backend API: `/apps/kailash-studio/backend/src/kailash_studio/api/workflow_versions.py`
- Frontend Types: `/apps/kailash-studio/frontend/src/types/index.ts`

## Conclusion

The drawer-based version history UI provides an optimal balance of:
1. **User Experience**: Contextual access to version history without leaving workflow
2. **Performance**: Virtual scrolling and progressive rendering meet <100ms targets
3. **Enterprise Value**: Audit trails, safe rollback, and compliance capabilities
4. **Development Efficiency**: 8-hour implementation leveraging existing infrastructure

This architecture decision enables Kailash Studio to deliver enterprise-grade version control with minimal complexity and maximum user value. The progressive feature layers (Timeline → Diff → Rollback) allow iterative validation and reduce implementation risk.

The drawer pattern aligns with Studio's existing UI conventions (PropertyPanel), ensuring consistent user experience while providing dedicated space for version management without cluttering the workflow canvas.

**Approval Required**: Frontend architecture team, UX review, Product owner
**Next Step**: Begin Phase 1 TDD implementation after requirements approval
