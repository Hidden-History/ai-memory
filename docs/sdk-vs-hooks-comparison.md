# SDK Wrapper vs File-Based Hooks Comparison

**Document:** TECH-DEBT-035 Phase 1 Output
**Status:** COMPLETE
**Date:** 2026-01-20

---

## Overview

This document compares two approaches for capturing Claude Code conversations:

1. **SDK Wrapper** (`src/memory/sdk_wrapper.py`) - New approach using Anthropic Python SDK
2. **File-Based Hooks** (`.claude/hooks/scripts/*`) - Existing approach using Claude Code hooks

Both store memories to the `discussions` collection with `USER_MESSAGE` and `AGENT_RESPONSE` types.

---

## Architecture Comparison

### SDK Wrapper

```
User Code (Python/BMAD Agent)
    ↓
SDKWrapper.send_message()
    ├── Capture user message → discussions collection
    ├── Send to Anthropic API
    ├── Receive response (streaming or non-streaming)
    └── Capture agent response → discussions collection
```

**Key Characteristics:**
- **Direct API integration** - Uses `anthropic.Anthropic()` client
- **Programmatic control** - Full control over message timing and capture
- **Real-time capture** - Messages captured during API call
- **No file dependency** - Does not rely on transcript files
- **Explicit invocation** - Must be called programmatically from code

### File-Based Hooks

```
Claude Code Session
    ↓
User submits prompt
    ↓
Claude processes and generates response
    ↓
Stop Hook fires (AFTER response complete)
    ↓
Hook script reads transcript file
    ↓
Extract messages → discussions collection
```

**Key Characteristics:**
- **Event-driven** - Triggered by Claude Code hook events
- **Automatic capture** - No code changes required
- **File-dependent** - Reads from transcript files
- **Post-response timing** - Captures after agent completes
- **Universal** - Works with ANY Claude Code session

---

## Key Differences

| Aspect | SDK Wrapper | File-Based Hooks |
|--------|-------------|------------------|
| **Trigger** | Programmatic (manual) | Automatic (event-driven) |
| **Timing** | During API call | After response complete |
| **Data Source** | API response objects | Transcript files |
| **Control** | Full programmatic control | Limited (hook configuration) |
| **Dependencies** | Anthropic SDK, API key | Claude Code, transcript files |
| **Use Cases** | BMAD agents, custom tools | General Claude Code sessions |
| **Integration** | Requires code changes | Zero code changes |
| **Reliability** | Depends on API availability | Depends on file writes |

---

## Detailed Behavior Differences

### 1. Message Capture Timing

**SDK Wrapper:**
```python
wrapper = SDKWrapper(cwd="/path/to/project", api_key="...")

# User message captured BEFORE API call
# Agent response captured IMMEDIATELY after API response
result = wrapper.send_message(prompt="What is 2+2?")

# Both messages already in discussions collection
print(result["capture_status"])  # {"user": "stored", "agent": "stored"}
```

**File-Based Hooks:**
```bash
# User types: "What is 2+2?"
# Claude processes...
# Claude responds: "2+2 = 4"
# Stop hook fires
# Hook script reads transcript file
# Extracts last turn from transcript
# Stores to discussions collection
```

**Timing Impact:**
- **SDK**: ~100-500ms between user message and API call
- **Hooks**: ~1-3s after response completion (file I/O + parsing)

### 2. Data Source and Format

**SDK Wrapper:**
```python
# Raw API response
message = Message(
    id="msg_123",
    role="assistant",
    content=[
        TextBlock(text="The answer is 4.", type="text")
    ],
    model="claude-3-5-sonnet-20241022",
    usage=Usage(input_tokens=10, output_tokens=8)
)

# Extract text directly
response_text = "".join(block.text for block in message.content)
```

**File-Based Hooks:**
```python
# Read from transcript file
transcript = read_json_file(transcript_path)

# Parse messages
messages = transcript.get("messages", [])
last_user = messages[-2]  # Assume second-to-last is user
last_agent = messages[-1]  # Last is agent

# Extract content
user_content = extract_content(last_user)
agent_content = extract_content(last_agent)
```

**Reliability:**
- **SDK**: Guaranteed accurate (direct from API)
- **Hooks**: Depends on file write timing and format stability

### 3. Error Handling and Graceful Degradation

**SDK Wrapper:**
```python
try:
    result = wrapper.send_message(prompt="Test")
except Exception as api_error:
    # API errors propagate immediately
    handle_api_error(api_error)

# Storage failures are caught internally
if result["capture_status"]["user"] == "failed":
    # User message capture failed but API call succeeded
    pass
```

**File-Based Hooks:**
```bash
# Hook script exit codes:
# 0 = Success (both captured)
# 1 = Non-blocking error (graceful degradation)
# 2 = Blocking error (rare)

# If hook fails, Claude Code continues normally
# No impact on user experience
```

**Degradation:**
- **SDK**: API errors block, storage errors degrade gracefully
- **Hooks**: All errors degrade gracefully (hooks can't block Claude)

### 4. Session and Turn Management

**SDK Wrapper:**
```python
wrapper = SDKWrapper(cwd="/path", session_id="custom_123")

# Turn 1
wrapper.send_message("First question")  # turn_number=1

# Turn 2
wrapper.send_message("Second question")  # turn_number=2

# Explicit turn tracking
print(wrapper.capture.turn_number)  # 2
```

**File-Based Hooks:**
```python
# Session ID from Claude Code
session_id = hook_input["session_id"]  # e.g., "sess_abc123def456"

# Turn number inferred from transcript
messages = read_transcript(transcript_path)
turn_number = len([m for m in messages if m["role"] == "user"])

# Automatic tracking via Claude Code
```

**Session Management:**
- **SDK**: Manual session/turn tracking
- **Hooks**: Automatic via Claude Code session state

---

## Use Cases

### When to Use SDK Wrapper

✅ **BMAD Agents** - When building custom agents that need conversation capture
✅ **Custom Tools** - Integration into Python tools/scripts
✅ **Testing** - Unit tests requiring controlled message capture
✅ **Batch Processing** - Programmatic message processing pipelines
✅ **Real-time Triggers** - Need immediate access to messages

**Example:**
```python
# Parzival agent using SDK wrapper
class ParzivalAgent:
    def __init__(self):
        self.sdk = SDKWrapper(cwd=os.getcwd())

    def process_decision(self, context):
        result = self.sdk.send_message(
            prompt=f"Analyze decision: {context}",
            model="claude-opus-4-5-20251101"
        )
        # Immediately available in discussions collection
        return result["content"]
```

### When to Use File-Based Hooks

✅ **General Sessions** - Regular Claude Code usage
✅ **Zero Integration** - No code changes needed
✅ **Universal Capture** - Works with all tools (Bash, Read, Edit, etc.)
✅ **Automatic Operation** - Set-and-forget configuration
✅ **Cross-Project** - Same hooks work across all projects

**Example:**
```json
// .claude/settings.json
{
  "hooks": {
    "Stop": [
      {
        "matcher": ".*",
        "hooks": [{
          "type": "command",
          "command": "python3 /path/to/stop_hook_capture.py"
        }]
      }
    ]
  }
}
```

---

## Performance Comparison

### SDK Wrapper Timing

```
User call wrapper.send_message()
    ├── 0ms    - User message captured
    ├── 100ms  - API request sent
    ├── 2000ms - API response received
    └── 2100ms - Agent response captured
Total: ~2100ms (API time + 100ms overhead)
```

### File-Based Hook Timing

```
User submits prompt in Claude Code
    ├── 0ms    - Prompt submitted
    ├── 2000ms - Agent response complete
    ├── 2500ms - Stop hook fires
    ├── 2600ms - Read transcript file
    ├── 2700ms - Parse and extract messages
    └── 3000ms - Both messages captured
Total: ~3000ms (response time + 1000ms hook overhead)
```

**Performance Summary:**
- **SDK**: Lower overhead (~100ms), but requires API call
- **Hooks**: Higher overhead (~1000ms), but zero user impact (background)

---

## Migration Strategy

### Current State (File-Based Hooks)
- ✅ Working for general Claude Code sessions
- ✅ Zero maintenance required
- ❌ Stop hook timing issues (BLK-004, BLK-006)
- ❌ File dependency fragility

### Future State (Hybrid Approach)

**Phase 1-3 (Current):** SDK Prototype
- Build and validate SDK wrapper
- Prove concept with tests
- No production usage yet

**Phase 4 (Next):** BMAD Agent Integration
- Parzival agent uses SDK wrapper
- Other BMAD agents use SDK wrapper
- File-based hooks remain for general sessions

**Phase 5 (Future):** Full Replacement
- Deprecate Stop hook (if SDK proves reliable)
- All conversation capture via SDK
- Hooks remain for other events (PreToolUse, PostToolUse, etc.)

---

## Limitations and Considerations

### SDK Wrapper Limitations

❌ **Requires API Key** - Must have ANTHROPIC_API_KEY configured
❌ **Code Changes** - Not drop-in replacement for hooks
❌ **API Costs** - Each call billed (hooks use existing session)
❌ **No Tool Access** - Can't use Claude Code tools (Read, Write, Bash, etc.)
❌ **Manual Session Management** - Must track sessions/turns manually

### File-Based Hook Limitations

❌ **Timing Issues** - Stop hook fires after completion (BLK-004, BLK-006)
❌ **File Dependency** - Relies on transcript file writes
❌ **Parsing Fragility** - Format changes can break extraction
❌ **No Real-time Access** - Can't capture during generation
❌ **Limited Control** - Hook configuration only

---

## Recommendations

### For BMAD Memory Module

1. **Keep Both Approaches**
   - SDK wrapper for Parzival and custom agents
   - File-based hooks for general Claude Code sessions

2. **Use SDK for Critical Paths**
   - Parzival decision logging
   - Agent handoff documentation
   - Structured conversation capture

3. **Use Hooks for Background Capture**
   - General session memory
   - Low-priority conversation logging
   - Automatic best practices capture

### For Phase 1-2 (COMPLETE)

✅ **Implemented:**
- [x] SDK wrapper created (`src/memory/sdk_wrapper.py`)
- [x] AsyncSDKWrapper with async/await support (`src/memory/async_sdk_wrapper.py`)
- [x] Rate limiting with token bucket algorithm (Tier 1: 50 RPM, 30K TPM)
- [x] Exponential backoff retry logic (3 retries: 1s, 2s, 4s ±20% jitter)
- [x] Background conversation capture to discussions collection
- [x] Tests passing (28 total: 12 sync + 16 async)
- [x] Anthropic SDK integrated
- [x] Basic prompt→response→capture flow working

🔄 **Next Steps (Phase 3-4):**
- [ ] Agent SDK integration (claude-agent-sdk package)
- [ ] Multi-agent orchestration and subagent tracking
- [ ] Integration with Parzival agent
- [ ] Production validation

---

## Conclusion

**SDK Wrapper** and **File-Based Hooks** serve different purposes:

- **SDK**: Programmatic control, real-time access, custom integration
- **Hooks**: Universal capture, zero maintenance, automatic operation

**Recommendation:** Use a **hybrid approach** where both coexist:
- SDK for BMAD agents and custom tools (explicit, controlled)
- Hooks for general sessions (automatic, background)

This provides the benefits of both while mitigating their limitations.

---

## References

- **Spec:** `oversight/specs/tech-debt-035/SPEC.md`
- **Research:** `oversight/specs/tech-debt-035/phase-0-research/`
- **Implementation:** `src/memory/sdk_wrapper.py`
- **Tests:** `tests/test_sdk_wrapper.py`
- **Hook System:** `.claude/hooks/scripts/`
