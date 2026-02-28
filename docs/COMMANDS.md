# 🎯 Commands & Skills Reference

> Comprehensive guide to all AI Memory Module slash commands and manual operations

## 📋 Table of Contents

- [Overview](#overview)
- [Memory Management Commands](#memory-management-commands)
  - [/aim-status](#aim-status)
  - [/aim-save](#aim-save)
  - [/aim-search](#aim-search)
- [How Commands Work](#how-commands-work)
- [Command vs Hook](#command-vs-hook)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

AI Memory Module provides slash commands for manual memory operations. These complement the automatic hooks (see [HOOKS.md](HOOKS.md)) and give you direct control over memory management.

### Available Commands

| Command | Purpose | Use Case | Typical Usage |
|---------|---------|----------|---------------|
| `/aim-status` | Check system health | Verify services running | Session startup, debugging |
| `/aim-save` | Manually save session | Before ending without compaction | Major milestone completed |
| `/aim-search` | Search all memories | Find specific pattern | Recall past implementation |

---

## 🧠 Memory Management Commands

### /aim-status

**Check AI Memory System Status**

#### Purpose
Displays comprehensive health check of all memory system components including Qdrant, embedding service, and collection statistics.

#### Syntax
```bash
/aim-status
```

No arguments required.

#### What It Checks

1. **Qdrant Health**
   - Connection status
   - Response time
   - Available collections

2. **Embedding Service Health**
   - Service availability
   - Endpoint accessibility
   - Model loaded status

3. **Collection Statistics**
   - discussions: Session summaries count
   - code-patterns: Code patterns count
   - conventions: Shared patterns count

4. **Recent Activity**
   - Last memory captured
   - Last session summary
   - Last search performed

#### Example Output

```markdown
## 🧠 AI Memory System Status

### ✅ Services Health

**Qdrant Vector Database**
- Status: ✅ Healthy
- URL: http://localhost:26350
- Response Time: 45ms
- Version: 1.7.4

**Embedding Service**
- Status: ✅ Healthy
- URL: http://localhost:28080
- Model: jinaai/jina-embeddings-v2-base-en
- Response Time: 120ms

### 📊 Collection Statistics

**discussions** (Session Summaries)
- Total Memories: 47
- Current Project: 12
- Last Updated: 2 hours ago

**code-patterns** (Code Patterns)
- Total Memories: 234
- Current Project: 89
- Last Updated: 15 minutes ago

**conventions** (Shared Patterns)
- Total Memories: 156 (shared across all projects)
- Last Updated: 3 days ago

### 📈 Recent Activity (Last 24 Hours)

- Memories Captured: 23
- Sessions Summarized: 3
- Searches Performed: 45
- Duplicates Avoided: 8

### 💾 Storage Health

- Disk Usage: 1.2 GB / 5 GB (24%)
- Index Status: Optimized
- Backup Status: Not configured

### ⚡ Performance Metrics

- Average Embedding Time: 1.8s
- Average Search Time: 0.3s
- Hook Overhead: <500ms

---

**All Systems Operational ✅**

To view detailed metrics, visit:
- Streamlit Dashboard: http://localhost:28501
- Grafana: http://localhost:23000
- Prometheus: http://localhost:29090
```

#### When to Use

**✅ Good Use Cases:**
- Starting a new session (verify system ready)
- After installation (confirm setup successful)
- Debugging issues (identify which service is down)
- Before important work (ensure memory capture working)

**❌ Don't Use For:**
- Checking if specific memory exists (use `/aim-search` instead)
- Viewing memory content (use Streamlit dashboard)
- Performance tuning (use Grafana dashboards)

#### Troubleshooting

<details>
<summary><strong>Command returns "Service Unavailable"</strong></summary>

**Diagnosis:**
```bash
# Check Docker services
docker compose -f docker/docker-compose.yml ps

# Check if services are running
curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/health
curl http://localhost:28080/health
```

**Solution:**
```bash
# Restart services
docker compose -f docker/docker-compose.yml restart

# Or rebuild if needed
docker compose -f docker/docker-compose.yml up -d --build
```
</details>

<details>
<summary><strong>Collection counts are 0</strong></summary>

**Possible Causes:**
1. First time using the system (no memories captured yet)
2. Wrong project directory (memories exist but for different project)
3. Collections not initialized

**Diagnosis:**
```bash
# Check all collections exist
curl http://localhost:26350/collections

# Check memories for current project
curl http://localhost:26350/collections/code-patterns/points/scroll \
  | jq '.result.points[] | select(.payload.group_id == "current-project")'
```

**Solution:**
- If first time: Perform some Write/Edit operations to capture memories
- If wrong project: Verify `cwd` detection is working
- If collections missing: Check Docker logs for initialization errors
</details>

---

### /aim-save

**Manually Save Current Session to Memory**

#### Purpose
Saves the current session summary to discussions collection without waiting for automatic compaction. Useful before ending a session or after completing a major milestone.

#### Syntax
```bash
/aim-save [note]
```

**Arguments:**
- `note` (optional): User note to attach to the session summary

#### Examples

```bash
# Basic save
/aim-save

# Save with note
/aim-save Completed authentication feature

# Save with multi-word note (quotes not needed)
/aim-save Fixed critical bug in JWT token validation
```

#### What It Saves

The command captures current session context:

1. **Session Metadata**
   - Session ID
   - Project name (group_id)
   - Timestamp
   - Duration

2. **Activity Summary**
   - Tools used (Edit, Write, Read, etc.)
   - Files modified (with file paths)
   - User prompts count

3. **Context Extraction**
   - Key implementations
   - Decisions made
   - Errors encountered and fixed
   - Architecture changes

4. **User Note** (if provided)
   - Attached to the summary for future context

#### Example Saved Summary

```markdown
Manual Session Save: my-project
Session ID: sess-abc123
Timestamp: 2026-01-17T10:30:00.000Z
User Note: Completed authentication feature

This session summary was manually saved by the user using /aim-save command.

Tools Used: Edit, Write, Read, Bash
Files Modified (8):
- src/auth/login.py
- src/auth/middleware.py
- src/models/user.py
- tests/test_auth.py
- docs/AUTH.md

User Interactions: 15 prompts

Key Activities:
1. Implemented JWT authentication
   - Login endpoint with email/password
   - Token generation and validation
   - Refresh token mechanism

2. Created auth middleware
   - Protected route decorator
   - Token verification from cookies
   - User session extraction

3. Added comprehensive tests
   - Login flow tests (happy path + errors)
   - Middleware tests
   - Token expiration tests

Technical Decisions:
- JWT tokens in httpOnly cookies (XSS prevention)
- 15-minute access token + 7-day refresh token
- RS256 signing (asymmetric keys)

Next Session: Consider implementing OAuth2 providers
```

#### When to Use

**✅ Good Use Cases:**
- **Before ending session**: Preserve context before closing Claude Code
- **After major milestone**: Save progress after completing a feature
- **Before switching projects**: Capture current state before context switch
- **Testing memory system**: Verify manual save functionality

**❌ Don't Use For:**
- Every small change (automatic hooks handle this)
- Just to check status (use `/aim-status` instead)
- Searching past work (use `/aim-search` instead)

#### Comparison with Automatic Hooks

| Method | Trigger | Use Case |
|--------|---------|----------|
| **PreCompact Hook** | Auto compaction | Automatic session continuity |
| **/aim-save** | Manual command | User-controlled checkpoints |
| **PostToolUse Hook** | After Edit/Write | Automatic implementation capture |

#### Troubleshooting

<details>
<summary><strong>Command succeeds but summary not in SessionStart</strong></summary>

**Diagnosis:**
```bash
# Check if summary was stored
curl http://localhost:26350/collections/discussions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "session")' \
  | jq -r '.payload.timestamp'

# Should show recent timestamp
```

**Possible Causes:**
1. Summary older than 48 hours (SessionStart filters recent only)
2. Wrong group_id (project mismatch)
3. Stored but low similarity to next session's query

**Solution:**
- Verify timestamp is recent
- Check group_id matches current project
- Lower similarity threshold if needed
</details>

<details>
<summary><strong>Command fails with "Qdrant unavailable"</strong></summary>

**Solution:**
```bash
# Check Qdrant health
curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/health

# If down, restart
docker compose -f docker/docker-compose.yml restart ai-memory-qdrant
```
</details>

---

### /aim-search

**Search Across All Project Memories**

#### Purpose
Performs semantic search across all memory collections (discussions, code-patterns, conventions) to find relevant patterns, implementations, and decisions.

#### Syntax
```bash
/aim-search <query> [--collection COLLECTION] [--limit N]
```

**Arguments:**
- `query` (required): Search query (semantic, not literal)
- `--collection` (optional): Specific collection to search (`discussions`, `code-patterns`, `conventions`, or `all`)
- `--limit` (optional): Maximum results to return (default: 5, max: 20)

#### Examples

```bash
# Basic semantic search
/aim-search JWT authentication implementation

# Search specific collection
/aim-search database migrations --collection code-patterns

# Limit results
/aim-search error handling patterns --limit 10

# Search all collections
/aim-search React hooks best practices --collection all

# Complex query
/aim-search how did we handle user sessions in the authentication module
```

#### Search Behavior

**Semantic Search:**
Searches by *meaning*, not exact text matching:

```bash
# These queries all find similar results:
/aim-search authentication with JWT
/aim-search user login with tokens
/aim-search securing API endpoints

# Because they share semantic meaning
```

**Collection Filtering:**

| Collection | Contains | Filtered By |
|------------|----------|-------------|
| `discussions` | Session summaries | Current project only |
| `code-patterns` | Code patterns | Current project only |
| `conventions` | Universal patterns | ALL projects (shared) |
| `all` (default) | All three collections | Mixed filtering |

**Relevance Scoring:**
Results are scored by similarity (0-100%):
- **90-100%**: High relevance (exact match)
- **50-90%**: Medium relevance (related concept)
- **0-50%**: Low relevance (filtered out)

#### Example Output

```markdown
## 🔍 Search Results for "JWT authentication implementation"

Found 8 relevant memories across 2 collections

---

### High Relevance (>90%)

**implementation** (95%) [code-patterns]
File: src/auth/login.py:23-45
Project: my-project
Captured: 2 hours ago

```python
def authenticate_user(email: str, password: str) -> dict:
    """Authenticate user and return JWT tokens.

    Args:
        email: User email address
        password: Plain text password

    Returns:
        dict with access_token and refresh_token
    """
    user = User.query.filter_by(email=email).first()
    if not user or not user.verify_password(password):
        raise AuthenticationError("Invalid credentials")

    access_token = generate_jwt(
        user_id=user.id,
        expiry=timedelta(minutes=15)
    )
    refresh_token = generate_jwt(
        user_id=user.id,
        expiry=timedelta(days=7),
        token_type="refresh"
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token
    }
```

**Decision Context:**
- Chose RS256 asymmetric signing for security
- Short access token (15min) + long refresh (7 days)
- httpOnly cookies to prevent XSS

---

**session** (92%) [discussions]
Session: sess-abc123
Project: my-project
Captured: 3 hours ago

Session Summary: Implemented JWT authentication system

Key Activities:
1. Created login endpoint with email/password validation
2. Implemented JWT token generation (access + refresh)
3. Added middleware for protected routes
4. Wrote comprehensive tests

Technical Decisions:
- JWT in httpOnly cookies (not localStorage)
- Asymmetric keys (RS256) for token signing
- Token refresh mechanism for security

Files Modified:
- src/auth/login.py (login logic)
- src/auth/middleware.py (route protection)
- src/models/user.py (password verification)

---

### Medium Relevance (50-90%)

**best_practice** (78%) [conventions]
Domain: security
Shared: All projects

Best Practice: JWT Token Security

When implementing JWT authentication:

1. **Storage**: Use httpOnly cookies, never localStorage
   - Prevents XSS attacks
   - Automatic inclusion in requests

2. **Signing**: Use RS256 (asymmetric) not HS256
   - Public key can be shared
   - Private key stays on server

3. **Expiry**: Short access tokens + refresh mechanism
   - Access: 15-30 minutes
   - Refresh: 7-30 days

4. **Validation**: Always verify signature AND expiry
   ```python
   jwt.decode(token, public_key, algorithms=['RS256'])
   ```

---

**implementation** (72%) [code-patterns]
File: src/middleware/auth.py:12-28
Project: my-project
Captured: 2 hours ago

```python
def require_auth(f):
    """Decorator to protect routes with JWT authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get('access_token')
        if not token:
            return jsonify({"error": "No token provided"}), 401

        try:
            payload = jwt.decode(token, PUBLIC_KEY, algorithms=['RS256'])
            request.user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated_function
```

---

Total Results: 8 memories (4 shown)
Collections Searched: code-patterns (5), discussions (2), conventions (1)
Search Duration: 0.4s
```

#### When to Use

**✅ Good Use Cases:**
- **Recall past implementations**: "How did we handle database migrations?"
- **Find patterns**: "Show me all error handling examples"
- **Refresh memory**: "What was the architecture decision for caching?"
- **Cross-project learning**: "Best practices for React testing" (searches shared collection)

**❌ Don't Use For:**
- System health check (use `/aim-status` instead)
- Saving current work (use `/aim-save` instead)
- Exact text matching (semantic search, not grep)

#### Search Tips

**Good Queries:**
```bash
# Conceptual
/aim-search how we handle user authentication

# Implementation-focused
/aim-search database connection pooling pattern

# Decision-focused
/aim-search why we chose PostgreSQL over MongoDB

# Error-focused
/aim-search how to fix CORS errors in React
```

**Bad Queries:**
```bash
# Too vague
/aim-search code

# Too specific (exact text)
/aim-search def authenticate_user(email: str

# Too broad
/aim-search everything about the project
```

#### Advanced Usage

**Collection-Specific Searches:**

```bash
# Only session summaries
/aim-search authentication --collection discussions

# Only code implementations
/aim-search database queries --collection code-patterns

# Only shared best practices
/aim-search testing patterns --collection conventions

# All collections (default)
/aim-search API design --collection all
```

**Result Limiting:**

```bash
# Top 3 results (quick overview)
/aim-search caching strategy --limit 3

# Comprehensive search (up to 20)
/aim-search all authentication implementations --limit 20
```

#### Troubleshooting

<details>
<summary><strong>No results found but memories exist</strong></summary>

**Possible Causes:**
1. **Semantic mismatch**: Query doesn't match meaning
2. **Similarity threshold**: Results below 50% filtered out
3. **Collection filtering**: Searching wrong collection
4. **Project isolation**: Memories are in different project

**Solutions:**
```bash
# Try broader query
/aim-search auth  # instead of "JWT HS256 authentication"

# Search all collections
/aim-search your-query --collection all

# Check if memories exist
curl http://localhost:26350/collections/code-patterns/points/scroll

# Lower threshold (in config)
export MEMORY_SIMILARITY_THRESHOLD=0.3
```
</details>

<details>
<summary><strong>Results not relevant</strong></summary>

**Diagnosis:**
Semantic search returns conceptually similar results, not exact matches.

**Solutions:**
1. **Refine query**: Be more specific
   ```bash
   # Instead of:
   /aim-search database

   # Use:
   /aim-search PostgreSQL connection pooling with SQLAlchemy
   ```

2. **Filter by collection**:
   ```bash
   # Implementations only
   /aim-search database --collection code-patterns
   ```

3. **Increase limit to see lower scores**:
   ```bash
   /aim-search database --limit 15
   ```
</details>

<details>
<summary><strong>Search is slow (>2 seconds)</strong></summary>

**Performance Targets:**
- Embedding generation: <2s
- Vector search: <300ms
- Total: <2.5s

**Diagnosis:**
```bash
# Check service health
/aim-status

# Check Qdrant metrics
curl http://localhost:26350/metrics
```

**Solutions:**
1. Reduce limit: `/aim-search query --limit 3`
2. Check embedding service: `curl http://localhost:28080/health`
3. Optimize Qdrant (see Prometheus metrics)
</details>

---

## 🔄 How Commands Work

### Execution Flow

```
User enters /aim-search in Claude Code
    ↓
Claude Code executes skill script
    ↓
Script calls Python memory module
    ↓
Python module:
  1. Generates query embedding
  2. Searches Qdrant collections
  3. Formats results
    ↓
Returns formatted markdown to Claude
    ↓
Claude displays results to user
```

### Behind the Scenes

Each command maps to a Python script:

| Command | Script | Module |
|---------|--------|--------|
| `/aim-status` | `scripts/memory/check_status.py` | `memory.health` |
| `/aim-save` | `scripts/memory/manual_save.py` | `memory.storage` |
| `/aim-search` | `scripts/memory/search_command.py` | `memory.search` |

---

## ⚡ Command vs Hook

**When to use each:**

| Scenario | Use | Reason |
|----------|-----|--------|
| Session starts | **Hook** (SessionStart) | Automatic context loading |
| File edited | **Hook** (PostToolUse) | Automatic capture |
| Context compacts | **Hook** (PreCompact) | Automatic summary |
| Check if system working | **Command** (/aim-status) | Manual verification |
| Before ending session | **Command** (/aim-save) | User-controlled checkpoint |
| Find past implementation | **Command** (/aim-search) | Manual retrieval |

**Hooks** = Automatic, invisible, continuous
**Commands** = Manual, explicit, on-demand

---

## 🔧 Troubleshooting

### Command Not Found

<details>
<summary><strong>/aim-status command not recognized</strong></summary>

**Cause**: Skills not installed correctly

**Solution:**
```bash
# Verify skill files exist
ls -la .claude/skills/

# Re-run installer if missing
./scripts/install.sh /path/to/project
```
</details>

### Command Execution Errors

<details>
<summary><strong>Command returns error message</strong></summary>

**Common Errors:**

1. **"Qdrant unavailable"**
   ```bash
   docker compose -f docker/docker-compose.yml restart ai-memory-qdrant
   ```

2. **"No memories found"**
   - First time using system (normal)
   - Wrong project (check cwd)

3. **"Embedding service timeout"**
   ```bash
   docker compose -f docker/docker-compose.yml restart ai-memory-embedding
   ```
</details>

### Performance Issues

<details>
<summary><strong>Commands are slow</strong></summary>

**Benchmarks:**
- `/aim-status`: <1s
- `/aim-save`: <3s
- `/aim-search`: <2.5s

**If slower:**
1. Check Docker resources (CPU, memory)
2. Check network latency to localhost
3. View metrics: http://localhost:29090
</details>

---

## 🔬 Skills & Agents

In addition to slash commands, AI-Memory includes skills (auto-activated by Claude) and agents (invoked via Task tool).

### best-practices-researcher (Skill)

**Activation:** Automatic when you ask about best practices, conventions, or "how should I" questions.

**What It Does:**
1. Searches local conventions collection
2. Performs web research (2024-2026 sources)
3. Saves findings to `oversight/knowledge/best-practices/`
4. Stores in Qdrant for future retrieval
5. Evaluates if a reusable skill should be created

**Location:** `.claude/skills/best-practices-researcher/`

### skill-creator (Agent)

**Activation:** Invoked by best-practices-researcher when findings warrant a skill, or manually.

**What It Does:**
1. Takes research findings as input
2. Applies BP-044 (Claude Skill authoring best practices)
3. Generates properly formatted SKILL.md
4. Creates skill in `.claude/skills/[name]/`

**Location:** `.claude/agents/skill-creator.md`

### aim-settings (Skill)

**Activation:** When you ask about memory configuration or settings.

**What It Does:** Displays current memory system configuration and settings.

**Location:** `.claude/skills/aim-settings/`

### aim-search (Skill)

**Activation:** When you ask to search memories, recall past decisions, or find previous discussions.

**What It Does:**
1. Searches across all memory collections (code-patterns, conventions, discussions)
2. Uses semantic search to find relevant memories
3. Returns formatted results with source and confidence

**Location:** `.claude/skills/aim-search/`

### aim-status (Skill)

**Activation:** When you ask about memory system health, statistics, or diagnostics.

**What It Does:**
1. Checks Docker service health (Qdrant, Embedding, Monitoring)
2. Reports collection sizes and memory counts
3. Shows recent activity and system status

**Location:** `.claude/skills/aim-status/`

---

## 📚 See Also

- [HOOKS.md](HOOKS.md) - Comprehensive hooks documentation
- [CONFIGURATION.md](CONFIGURATION.md) - Environment variables and settings
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Comprehensive troubleshooting
- [prometheus-queries.md](prometheus-queries.md) - Performance metrics

---

**2026 Best Practices Applied:**
- Clear command syntax with examples
- Semantic search explanation (not literal matching)
- Expandable troubleshooting sections
- Performance benchmarks stated
- Visual comparison tables
- Real-world use cases
