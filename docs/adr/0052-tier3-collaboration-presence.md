# ADR-0052: Real-Time Collaboration Presence Indicators

## Status
Proposed

## Context

Kailash Studio supports real-time collaborative workflow editing via WebSocket, but lacks visual indicators showing who else is actively working on a workflow. This creates coordination problems and potential editing conflicts in team environments.

### Current Limitations
- No visibility of other users in the same workflow
- No cursor position tracking
- No selection state sharing
- Difficult to coordinate edits without external communication
- Potential for concurrent edit conflicts

### Business Requirements
- **Team Coordination**: Show who is actively working on a workflow
- **Conflict Avoidance**: Visual indicators of what others are editing
- **Communication**: Reduce need for external coordination (Slack, email)
- **User Experience**: Smooth, Google Docs-like collaboration experience

### Technical Context
- Existing WebSocket infrastructure (Socket.io) for real-time updates
- CollaborationSession model already exists in DataFlow models
- React Flow canvas for workflow visualization
- Ant Design UI components available
- User model has avatar and profile information

## Decision

We will implement **Real-Time Collaboration Presence Indicators** with live user avatars, cursor tracking, and selection highlighting.

### Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Frontend Components                    │
├─────────────────────────────────────────────────────────┤
│  CollaborationPresence                                  │
│    ├── PresenceIndicators                               │
│    │     ├── UserAvatarStack (5 max, overflow popover)  │
│    │     └── PresenceCount (total active users)         │
│    │                                                     │
│    ├── LiveCursors                                      │
│    │     └── UserCursor × N (throttled to 60fps)        │
│    │                                                     │
│    ├── SelectionOverlays                                │
│    │     └── SelectionHighlight × N (semi-transparent)  │
│    │                                                     │
│    ├── UserListPanel (expandable drawer)                │
│    │     └── UserListItem × N (with status badges)      │
│    │                                                     │
│    └── PresenceNotifications (join/leave toasts)        │
└─────────────────────────────────────────────────────────┘
                            │
                   WebSocket Events
                            ▼
┌─────────────────────────────────────────────────────────┐
│               Socket.io Server (Backend)                │
├─────────────────────────────────────────────────────────┤
│  Presence Management Service                            │
│    ├── Join/Leave handling                              │
│    ├── Cursor position broadcasting                     │
│    ├── Selection state broadcasting                     │
│    ├── Activity heartbeat monitoring                    │
│    └── Session cleanup (idle timeout)                   │
│                                                         │
│  WebSocket Rooms (per workflow)                         │
│    └── Broadcast to all users in workflow room         │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Data Layer                             │
├─────────────────────────────────────────────────────────┤
│  CollaborationSession Model (DataFlow)                  │
│    ├── cursor_position: {x, y, node_id}                │
│    ├── selection: {nodes: [], edges: []}               │
│    ├── is_active: bool                                  │
│    └── last_activity: datetime                         │
│                                                         │
│  Redis (WebSocket session tracking)                     │
│    ├── workflow:{id}:users → Set<user_id>              │
│    └── user:{id}:color → String (assigned color)       │
└─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Throttled Cursor Updates (60fps)
**Decision**: Throttle cursor position updates to 16ms intervals (60fps)

**Rationale**:
- Human eye perception: >60fps provides no visual benefit
- Network efficiency: Reduces message volume by 80%+
- CPU efficiency: Less processing for position updates
- Smooth animations: 60fps is perfectly smooth

**Implementation**:
```typescript
const throttledCursorUpdate = throttle((position: {x: number, y: number}) => {
  socket.emit('cursor:update', {
    workflowId: currentWorkflowId,
    userId: currentUserId,
    position: position,
    nodeId: hoveredNodeId // Optional: node under cursor
  });
}, 16); // 60fps = 1000ms / 60 ≈ 16ms

// On mouse move
const handleMouseMove = (event: MouseEvent) => {
  const position = {
    x: event.clientX,
    y: event.clientY
  };
  throttledCursorUpdate(position);
};
```

#### 2. Deterministic Color Assignment
**Decision**: Generate user colors deterministically from user ID hash

**Rationale**:
- Consistency: Same user always gets same color
- No coordination: No server-side color assignment needed
- Distribution: Hash ensures good color distribution
- Accessibility: Can ensure sufficient contrast

**Implementation**:
```typescript
function getUserColor(userId: string): string {
  const colors = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
    '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
    '#F8B739', '#52B788', '#E76F51', '#2A9D8F'
  ];

  // Hash user ID to deterministic index
  const hash = userId.split('').reduce((acc, char) =>
    acc + char.charCodeAt(0), 0
  );

  return colors[hash % colors.length];
}
```

#### 3. Activity-Based Status Calculation
**Decision**: Derive user status from last_activity timestamp

**Rationale**:
- No additional fields: Uses existing last_activity
- Real-time accuracy: Updates with every heartbeat
- Clear semantics: Active, viewing, idle

**Status Calculation**:
```python
def calculate_user_status(last_activity: datetime) -> str:
    now = datetime.utcnow()
    time_since_activity = (now - last_activity).total_seconds()

    if time_since_activity < 30:  # 30 seconds
        return 'active'
    elif time_since_activity < 300:  # 5 minutes
        return 'viewing'
    else:
        return 'idle'
```

#### 4. WebSocket Room-Based Broadcasting
**Decision**: Use Socket.io rooms for per-workflow broadcasting

**Rationale**:
- Efficiency: Messages only sent to relevant users
- Scalability: Each workflow is independent
- Isolation: Presence in one workflow doesn't affect others

**Implementation**:
```python
@socketio.on('user:join')
def handle_user_join(data):
    workflow_id = data['workflowId']
    user_id = data['userId']

    # Join workflow room
    join_room(f"workflow:{workflow_id}")

    # Create/update collaboration session
    session = CollaborationSession(
        workflow_id=workflow_id,
        user_id=user_id,
        is_active=True,
        last_activity=datetime.utcnow()
    )
    db.save(session)

    # Broadcast to others in room
    emit('user:joined', {
        'workflowId': workflow_id,
        'user': {
            'userId': user_id,
            'username': get_username(user_id),
            'color': get_user_color(user_id)
        }
    }, room=f"workflow:{workflow_id}", skip_sid=request.sid)
```

#### 5. Session Cleanup Strategy
**Decision**: Automated cleanup of stale sessions (30-minute idle timeout)

**Rationale**:
- Ghost sessions: Prevent accumulation of inactive sessions
- Accuracy: Keep presence indicators accurate
- Resources: Free up database/Redis space

**Cleanup Job**:
```python
@scheduled_task(interval=minutes(5))
def cleanup_stale_sessions():
    threshold = datetime.utcnow() - timedelta(minutes=30)

    stale_sessions = CollaborationSession.query.filter(
        CollaborationSession.last_activity < threshold,
        CollaborationSession.is_active == True
    ).all()

    for session in stale_sessions:
        session.is_active = False
        db.save(session)

        # Notify others user has left
        socketio.emit('user:left', {
            'workflowId': session.workflow_id,
            'userId': session.user_id
        }, room=f"workflow:{session.workflow_id}")
```

## Alternatives Considered

### Option 1: Polling-Based Presence
**Description**: Poll server every 2-3 seconds for presence updates

**Pros**:
- Simpler implementation (no WebSocket complexity)
- Works with any HTTP client
- Easier to debug

**Cons**:
- High latency (2-3 second updates)
- Inefficient (constant polling even with no changes)
- High server load
- Poor user experience (janky cursor updates)

**Rejection Reason**: Unacceptable latency for real-time collaboration. WebSocket already available in Kailash Studio.

### Option 2: Full Operational Transform (OT)
**Description**: Implement Google Docs-style OT for concurrent editing

**Pros**:
- Automatic conflict resolution
- True concurrent editing of same node
- Gold standard for collaboration

**Cons**:
- Extremely complex implementation
- Requires complete redesign of workflow editing
- High risk for bugs and edge cases
- Over-engineered for current needs

**Rejection Reason**: Presence indicators alone provide 80% of value with 20% of complexity. OT can be added later if needed.

### Option 3: CRDT-Based State Sync
**Description**: Use CRDTs (Yjs, Automerge) for state synchronization

**Pros**:
- Automatic conflict-free merging
- Offline editing support
- Proven libraries available

**Cons**:
- Large dependency (Yjs is ~50KB)
- Significant architecture changes
- Learning curve for team
- Potential performance overhead

**Rejection Reason**: Overkill for presence indicators. Simpler WebSocket approach sufficient for current requirements.

### Option 4: Server-Side Cursor Rendering
**Description**: Server renders all cursors, sends as video stream

**Pros**:
- No client-side rendering complexity
- Consistent appearance across clients

**Cons**:
- Extremely high bandwidth
- Massive server resources required
- Unacceptable latency
- Ridiculous over-engineering

**Rejection Reason**: Clearly impractical. Included for completeness.

## Consequences

### Positive Consequences

#### User Experience Improvements
- **Team Awareness**: Instant visibility of teammates
- **Conflict Avoidance**: See what others are editing before conflicts occur
- **Reduced Coordination**: Less need for external communication
- **Professionalism**: Google Docs-like experience increases perceived quality

#### Technical Benefits
- **Leverages Existing Infrastructure**: Socket.io, CollaborationSession model, Redis
- **Low Latency**: <16ms cursor updates, <100ms join/leave notifications
- **Scalability**: Room-based broadcasting scales to 50+ users per workflow
- **Minimal Overhead**: Throttled updates minimize network/CPU usage

#### Business Value
- **Team Productivity**: Fewer coordination bottlenecks
- **User Satisfaction**: Professional collaboration experience
- **Differentiation**: Not common in workflow automation tools
- **Retention**: Better collaboration increases stickiness

### Negative Consequences

#### Development Complexity
- **WebSocket State Management**: Need to handle connections, disconnections, reconnections
- **Race Conditions**: Potential for cursor/selection state conflicts
- **Browser Compatibility**: Need to test across browsers

#### Performance Considerations
- **Network Traffic**: Additional WebSocket messages for cursor/selection
- **Client CPU**: Rendering multiple cursors/selections
- **Server CPU**: Broadcasting to all users in room

#### User Experience Challenges
- **Visual Clutter**: Too many cursors can be distracting
- **Color Collisions**: Similar user colors may be confusing
- **Privacy Concerns**: Some users may not want to be tracked

### Risk Mitigation Strategies

#### Performance Risks
- **Mitigation**: Throttle updates to 60fps, limit visible cursors to 10
- **Monitoring**: Track WebSocket message volume, latency
- **Graceful Degradation**: Disable cursors if >50 users in workflow

#### Privacy Risks
- **Mitigation**: Add user preference to disable presence tracking
- **Transparency**: Clear documentation of what's tracked
- **Control**: Allow users to go "invisible"

#### Browser Compatibility Risks
- **Mitigation**: Comprehensive cross-browser testing
- **Fallback**: Presence indicators without cursors if WebSocket fails
- **Progressive Enhancement**: Core editing works without presence

## Implementation Plan

### Phase 1: Backend WebSocket Events (1h)
1. Implement WebSocket event handlers (join, leave, cursor, selection, heartbeat)
2. Add room-based broadcasting
3. Implement session cleanup job
4. Write backend tests

### Phase 2: Frontend Components (1.5h)
1. Create CollaborationPresence component structure
2. Implement UserAvatarStack and PresenceCount
3. Build LiveCursors with throttling
4. Add SelectionOverlays
5. Create UserListPanel drawer

### Phase 3: Integration and Polish (0.5h)
1. Connect frontend to WebSocket events
2. Add join/leave toast notifications
3. Implement deterministic color generation
4. Test with multiple users
5. Performance optimization

## Success Metrics

### Performance Metrics
- Cursor update latency: <16ms (60fps)
- Join/leave notification: <100ms
- User list refresh: <50ms
- Avatar loading: <200ms

### User Metrics
- Collaboration usage: 40%+ of workflows edited collaboratively
- Conflict reduction: 80% fewer reported edit conflicts
- User satisfaction: >4.5/5 NPS for collaboration features

### Technical Metrics
- WebSocket message rate: <1000 messages/second
- Connection stability: >99.9% uptime
- Memory overhead: <50MB for 100 concurrent workflows
- CPU overhead: <5% increase on client and server

## Dependencies

### Technical Dependencies
- Socket.io (existing WebSocket infrastructure)
- CollaborationSession model (already in DataFlow models)
- Redis (WebSocket session tracking)
- React Flow (workflow canvas)
- Ant Design (Avatar, Badge, Drawer, Popover)

### Data Dependencies
- User model (avatar, username)
- CollaborationSession model (cursor, selection, activity)

### Timeline Dependencies
- Can be developed independently
- Should be implemented before advanced collaborative features (comments, chat)

## Conclusion

Real-Time Collaboration Presence Indicators provide essential team coordination capabilities for Kailash Studio. By leveraging existing WebSocket infrastructure and the CollaborationSession model, we can deliver a professional Google Docs-like collaboration experience with minimal architectural changes.

The throttled cursor updates and room-based broadcasting ensure scalability to 50+ concurrent users per workflow, while deterministic color assignment and activity-based status calculation keep the implementation simple and efficient.

This feature directly addresses user pain points around coordination and conflict avoidance, improving both productivity and user satisfaction with minimal development effort (3 hours).
