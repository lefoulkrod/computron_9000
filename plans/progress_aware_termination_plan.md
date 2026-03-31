# Progress-Aware Termination with Cognitive Debt Detection

## Implementation Plan

### Overview

This feature enhances the existing loop detection system to create a comprehensive "circuit breaker" that monitors agent execution patterns, detects when an agent is stuck or spinning without meaningful progress, and provides intelligent intervention options.

### Current State Analysis

The codebase already has:
1. **LoopDetector** (`sdk/hooks/_loop_detector.py`): Detects identical tool-call signatures repeated N times
2. **BudgetGuard** (`sdk/hooks/_budget_guard.py`): Enforces max iteration limits
3. **Hook system** (`sdk/hooks/`): Pluggable lifecycle hooks for tool execution
4. **Event system** (`sdk/events/`): Rich event streaming for UI feedback

### Limitations of Current System

1. **Identical Detection Only**: Current `LoopDetector` only catches EXACTLY identical tool call sequences
2. **No Progress Metrics**: No tracking of whether tool results are changing meaningfully
3. **No Severity Levels**: Binary detection (loop or no loop) vs. progressive concern levels
4. **Limited Intervention**: Only injects nudges; no escalation or user notification
5. **No Persistence**: Loop state is lost between agent calls

---

## Implementation Steps

### Phase 1: Enhanced Progress Metrics Tracking

**File**: `sdk/hooks/_progress_tracker.py` (NEW)

Create a new hook that tracks sophisticated progress metrics:

```python
class ProgressTracker:
    """Tracks execution patterns and progress metrics over time."""
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.tool_calls: deque[ToolCallRecord] = deque(maxlen=window_size)
        self.results_hash: deque[str] = deque(maxlen=window_size)
        self.progress_score: float = 1.0  # 0.0-1.0
        self.cognitive_debt: float = 0.0  # Accumulated wasted effort
        
    def after_tool(self, tool_name, tool_arguments, tool_result):
        # Hash result to detect if anything actually changed
        # Track tool call patterns
        # Update progress score based on novelty
        pass
        
    def before_model(self, history, iteration, agent_name):
        # Calculate current progress metrics
        # Emit progress event for UI
        pass
```

**Features**:
- Track tool call patterns (not just identical, but similar)
- Hash tool results to detect if outputs are actually changing
- Calculate "progress velocity" (are we moving forward?)
- Compute "cognitive debt" (wasted tokens on repetitive operations)

**Testing Approach**:
- Unit tests with mock tool calls
- Test progress score calculation with known patterns
- Test cognitive debt accumulation

---

### Phase 2: Similarity-Based Loop Detection

**File**: `sdk/hooks/_loop_detector.py` (MODIFY)

Enhance existing `LoopDetector` to detect:

1. **Exact Match Loops** (current behavior)
2. **Semantic Similarity Loops** (similar but not identical calls)
3. **Result-Driven Loops** (same results despite different inputs)
4. **Cyclic Patterns** (A→B→C→A tool call sequences)

**Code Changes**:

```python
class LoopDetector:
    """Enhanced loop detection with multiple detection modes."""
    
    def __init__(
        self,
        exact_threshold: int = 5,
        similarity_threshold: float = 0.85,
        result_repetition_threshold: int = 3,
    ):
        self.exact_threshold = exact_threshold
        self.similarity_threshold = similarity_threshold
        self.result_repetition_threshold = result_repetition_threshold
        
    def _calculate_similarity(self, round_a, round_b) -> float:
        """Calculate Jaccard similarity or other metric between tool call rounds."""
        pass
        
    def _detect_cycle(self) -> bool:
        """Detect cyclic patterns in tool call sequences."""
        pass
```

**Testing Approach**:
- Test each detection mode independently
- Test combinations (exact + similarity)
- Edge cases: empty rounds, single tool calls

---

### Phase 3: Cognitive Debt Scoring System

**File**: `sdk/hooks/_cognitive_debt.py` (NEW)

Create a scoring system that accumulates "debt" when the agent wastes effort:

```python
class CognitiveDebtTracker:
    """Tracks wasted effort and escalating intervention needs."""
    
    def __init__(self, thresholds: DebtThresholds | None = None):
        self.thresholds = thresholds or DebtThresholds(
            warning=0.3,    # 30% debt ratio
            concerning=0.6,  # 60% debt ratio
            critical=0.85,   # 85% debt ratio
        )
        self.debt_score = 0.0
        self.debt_items: list[DebtItem] = []
        
    def add_repetitive_tool_call(self, tool_name, args, result, token_cost):
        """Record a potentially wasted tool call."""
        pass
        
    def get_debt_level(self) -> DebtLevel:
        """Return current debt severity."""
        pass
        
    def should_escalate(self) -> bool:
        """Determine if we need stronger intervention."""
        pass
```

**Debt Accumulation Rules**:
- Identical tool calls: +0.2 debt per repetition
- Similar tool calls: +0.1 debt per near-repetition
- Failed/error results: +0.15 debt
- Empty/unhelpful results: +0.1 debt
- New/novel tool calls: -0.1 debt (reward progress)

**Testing Approach**:
- Test debt calculation with known patterns
- Test threshold detection
- Test escalation triggers

---

### Phase 4: Event Types for Progress Tracking

**File**: `sdk/events/_models.py` (MODIFY)

Add new event payloads:

```python
class ProgressMetricsPayload(BaseModel):
    """Emits current progress metrics during execution."""
    type: Literal["progress_metrics"]
    progress_score: float  # 0.0-1.0
    cognitive_debt: float  # 0.0-1.0
    debt_level: Literal["none", "warning", "concerning", "critical"]
    recent_tool_calls: list[ToolCallSummary]
    suggestion: str | None  # Optional suggestion for user

class LoopDetectedPayload(BaseModel):
    """Emitted when a loop pattern is detected."""
    type: Literal["loop_detected"]
    detection_type: Literal["exact", "similar", "result_repetition", "cycle"]
    confidence: float
    affected_tools: list[str]
    recommendation: str
    severity: Literal["low", "medium", "high"]

class InterventionPayload(BaseModel):
    """Emitted when system intervenes in execution."""
    type: Literal["intervention"]
    intervention_type: Literal["nudge", "pause", "escalate", "stop"]
    reason: str
    debt_at_intervention: float
```

**Testing Approach**:
- Test event serialization
- Test event emission in integration tests

---

### Phase 5: Progressive Intervention System

**File**: `sdk/hooks/_intervention.py` (NEW)

Create a tiered intervention system:

```python
class InterventionLevel(Enum):
    NONE = "none"
    NUDGE = "nudge"           # Inject helpful prompt
    PAUSE = "pause"           # Ask user for guidance
    ESCALATE = "escalate"     # Trigger reflection agent
    STOP = "stop"             # Hard stop with summary

class InterventionHook:
    """Manages progressive intervention based on cognitive debt."""
    
    def __init__(self, config: InterventionConfig | None = None):
        self.config = config or InterventionConfig.default()
        self.progress_tracker = ProgressTracker()
        self.debt_tracker = CognitiveDebtTracker()
        self.intervention_history: list[Intervention] = []
        
    async def before_model(self, history, iteration, agent_name):
        """Check if intervention is needed and apply appropriate level."""
        debt_level = self.debt_tracker.get_debt_level()
        
        if debt_level == DebtLevel.WARNING:
            await self._apply_nudge(history, agent_name)
        elif debt_level == DebtLevel.CONCERNING:
            await self._apply_pause(history, agent_name)
        elif debt_level == DebtLevel.CRITICAL:
            await self._apply_escalation_or_stop(history, agent_name)
            
    async def _apply_nudge(self, history, agent_name):
        """Gentle nudge to try different approach."""
        nudge = self._generate_contextual_nudge()
        history.append({"role": "user", "content": nudge})
        self._emit_intervention_event("nudge", nudge)
        
    async def _apply_pause(self, history, agent_name):
        """Pause and request user guidance."""
        # Emit event to UI for user decision
        # Wait for user input
        pass
        
    def _generate_contextual_nudge(self) -> str:
        """Generate a helpful nudge based on detected patterns."""
        # Analyze recent tool calls
        # Suggest alternatives based on available tools
        pass
```

**Testing Approach**:
- Test each intervention level
- Test escalation between levels
- Test user pause/resume flow

---

### Phase 6: Integration with Hook System

**File**: `sdk/hooks/_default.py` (MODIFY)

Update default hooks to include new progress-aware hooks:

```python
def default_hooks(agent, *, max_iterations=0, ctx_manager=None, 
                  enable_progress_tracking=True) -> list[Any]:
    hooks: list[Any] = [NudgeHook(), StopHook()]
    
    if max_iterations > 0:
        hooks.append(BudgetGuard(max_iterations))
        
    # Replace simple LoopDetector with ProgressAwareHooks
    if enable_progress_tracking:
        progress_hooks = ProgressAwareHooks(
            loop_threshold=5,
            debt_thresholds=DebtThresholds(
                warning=0.3,
                concerning=0.6,
                critical=0.85
            )
        )
        hooks.append(progress_hooks)
    else:
        hooks.append(LoopDetector())  # Fallback to simple detector
        
    hooks.append(LoggingHook(agent))
    hooks.append(ScratchpadHook())
    
    if ctx_manager is not None:
        hooks.append(ContextHook(ctx_manager, max_iterations=max_iterations))
        
    return hooks
```

**Testing Approach**:
- Test hook ordering
- Test enable/disable flag
- Test backward compatibility

---

### Phase 7: Configuration Support

**File**: `config.yaml` (MODIFY)

Add configuration section:

```yaml
progress_aware_termination:
  enabled: true
  
  loop_detection:
    exact_threshold: 5
    similarity_threshold: 0.85
    result_repetition_threshold: 3
    
  cognitive_debt:
    warning_threshold: 0.3
    concerning_threshold: 0.6
    critical_threshold: 0.85
    
  intervention:
    auto_nudge: true
    auto_pause: true
    max_debt_before_stop: 0.95
    
  metrics:
    window_size: 20
    emit_metrics_events: true
```

**File**: `config/__init__.py` (MODIFY)

Add config models for new settings.

**Testing Approach**:
- Test config loading
- Test config validation
- Test defaults

---

### Phase 8: UI Integration (Frontend)

**File**: `server/ui/src/components/` (NEW files)

Create React components:

1. **ProgressMetricsPanel**: Display cognitive debt and progress score
2. **LoopWarning**: Visual warning when loops detected
3. **InterventionDialog**: User decision dialog for pause interventions
4. **DebtMeter**: Visual debt accumulation indicator

**Key features**:
- Real-time debt meter (progress bar)
- Warning badges when thresholds crossed
- "Help Agent" button for manual intervention
- Loop pattern visualization

**Testing Approach**:
- Component unit tests with Vitest
- Integration tests with mocked events

---

### Phase 9: Integration Tests

**File**: `tests/test_progress_aware_termination.py` (NEW)

Create comprehensive integration tests:

```python
class TestProgressAwareTermination:
    """Integration tests for the full progress-aware termination system."""
    
    async def test_exact_loop_detection(self):
        """Test detection of identical tool call loops."""
        pass
        
    async def test_similarity_loop_detection(self):
        """Test detection of similar (but not identical) loops."""
        pass
        
    async def test_cognitive_debt_accumulation(self):
        """Test debt scoring with known patterns."""
        pass
        
    async def test_progressive_intervention(self):
        """Test escalation through intervention levels."""
        pass
        
    async def test_event_emission(self):
        """Test that all expected events are emitted."""
        pass
```

---

## File Summary

### New Files (8)
1. `sdk/hooks/_progress_tracker.py` - Core progress metrics tracking
2. `sdk/hooks/_cognitive_debt.py` - Debt scoring system
3. `sdk/hooks/_intervention.py` - Progressive intervention manager
4. `sdk/hooks/_progress_aware_hooks.py` - Combined hook container
5. `tests/test_progress_aware_termination.py` - Integration tests
6. `docs/progress_aware_termination.md` - Documentation
7. `server/ui/src/components/ProgressMetricsPanel.tsx` - UI component
8. `server/ui/src/components/LoopWarning.tsx` - UI component

### Modified Files (5)
1. `sdk/hooks/_loop_detector.py` - Enhance with similarity detection
2. `sdk/hooks/_default.py` - Integrate new hooks
3. `sdk/hooks/__init__.py` - Export new classes
4. `sdk/events/_models.py` - Add new event payloads
5. `config.yaml` - Add configuration section

---

## Implementation Order

1. **Phase 1-2**: Core detection (ProgressTracker + enhanced LoopDetector)
2. **Phase 3**: Debt scoring (CognitiveDebtTracker)
3. **Phase 4**: Event system (new payload types)
4. **Phase 5**: Intervention system
5. **Phase 6**: Hook integration
6. **Phase 7**: Configuration
7. **Phase 8**: Frontend (can be parallel)
8. **Phase 9**: Integration tests

---

## Success Metrics

- **Loop Detection Rate**: Should catch >95% of repetitive patterns (vs ~60% with current identical-only detection)
- **False Positive Rate**: <5% of productive tool call sequences flagged as loops
- **Token Savings**: Estimated 20-40% reduction in wasted tokens from looped executions
- **User Experience**: Interventions feel helpful, not intrusive

---

## Dependencies

- **No new external dependencies** - Uses existing Python standard library + current stack
- **Frontend**: Uses existing React/Vite setup

## Estimated Effort

- **Phase 1-2**: 1 day
- **Phase 3**: 0.5 day
- **Phase 4**: 0.5 day
- **Phase 5**: 1 day
- **Phase 6-7**: 0.5 day
- **Phase 8**: 1 day (can be parallel)
- **Phase 9**: 0.5 day
- **Total**: ~4-5 days
