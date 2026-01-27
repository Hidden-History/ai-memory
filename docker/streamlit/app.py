"""
BMAD Memory Browser - Streamlit Dashboard
Story 6.4: Streamlit Memory Browser

2026 Best Practices:
- st.set_page_config() MUST be first Streamlit command
- Explicit widget keys (key-based identity in Streamlit 1.50+)
- @st.cache_resource for connections (singleton)
- @st.cache_data(ttl=N) for data with expiration
- Graceful error handling with st.stop()

Widget Key Pattern (V2.0):
- Widgets that change based on other widget state need unique keys
- Pattern: key=f"widget_name_{dependent_state}"
- Example: type_select depends on collection selection → key=f"type_select_{collection}"
- This prevents Streamlit state bleed when collection changes
"""

import datetime
import json
import os
import sys
import time
from typing import Optional

import httpx
import streamlit as st
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Import memory models for canonical type definitions (C1: DRY - single source of truth)
# Import paths tried in order:
#   1. /app/src - Docker container runtime
#   2. ../../src - Local development (streamlit run docker/streamlit/app.py)
#   3. Fallback - Hardcoded values when pydantic_settings not installed
try:
    sys.path.insert(0, "/app/src")
    from memory.models import MemoryType
    MODELS_IMPORTED = True
except ImportError:
    try:
        # Fallback: local development path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
        from memory.models import MemoryType
        MODELS_IMPORTED = True
    except ImportError:
        # Fallback: Container without pydantic_settings - use hardcoded types
        # Dashboard remains functional, just can't import from models.py
        MODELS_IMPORTED = False

# V2.0 Collection Names (hardcoded for multi-project container support)
# These are GLOBAL - same for all projects. Project isolation is via group_id filter.
COLLECTION_CODE_PATTERNS = "code-patterns"
COLLECTION_CONVENTIONS = "conventions"
COLLECTION_DISCUSSIONS = "discussions"

# Collection names list for iteration
COLLECTION_NAMES = [COLLECTION_CODE_PATTERNS, COLLECTION_CONVENTIONS, COLLECTION_DISCUSSIONS]

# V2.0 Type System (C1: Derived from canonical source - src/memory/models.py:34-69)
# Import MemoryType enum to avoid DRY violation and drift between UI and backend
if MODELS_IMPORTED:
    COLLECTION_TYPES = {
        "code-patterns": [
            MemoryType.IMPLEMENTATION.value,
            MemoryType.ERROR_FIX.value,
            MemoryType.REFACTOR.value,
            MemoryType.FILE_PATTERN.value,
        ],
        "conventions": [
            MemoryType.RULE.value,
            MemoryType.GUIDELINE.value,
            MemoryType.PORT.value,
            MemoryType.NAMING.value,
            MemoryType.STRUCTURE.value,
        ],
        "discussions": [
            MemoryType.DECISION.value,
            MemoryType.SESSION.value,
            MemoryType.BLOCKER.value,
            MemoryType.PREFERENCE.value,
            MemoryType.USER_MESSAGE.value,
            MemoryType.AGENT_RESPONSE.value,
        ],
    }
else:
    # Fallback: Hardcoded values if import fails (container missing pydantic_settings)
    # CRITICAL: These values MUST be kept in sync with src/memory/models.py:39-58
    # Last verified: 2026-01-25 (TECH-DEBT-068)
    COLLECTION_TYPES = {
        "code-patterns": ["implementation", "error_fix", "refactor", "file_pattern"],
        "conventions": ["rule", "guideline", "port", "naming", "structure"],
        "discussions": ["decision", "session", "blocker", "preference", "user_message", "agent_response"],
    }

# L2: Startup validation - ensure all collections have type definitions
for collection in COLLECTION_NAMES:
    assert collection in COLLECTION_TYPES, f"Missing types for {collection}"
    assert len(COLLECTION_TYPES[collection]) > 0, f"Empty types for {collection}"

# ============================================================================
# PAGE CONFIGURATION (MUST BE FIRST STREAMLIT COMMAND)
# ============================================================================
st.set_page_config(
    page_title="BMAD Memory Browser",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================================
# CONFIGURATION
# ============================================================================
# Activity log path - uses BMAD_INSTALL_DIR from environment
# In container: /app/logs/activity.log (mounted from host's $BMAD_INSTALL_DIR/logs)
INSTALL_DIR = os.getenv("BMAD_INSTALL_DIR", "/app")
ACTIVITY_LOG_PATH = os.path.join(INSTALL_DIR, "logs", "activity.log")


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================
def validate_log_mount() -> tuple[bool, str]:
    """Validate that activity log is accessible and current.

    Returns:
        (is_valid, message): Tuple of validation status and message
    """
    if not os.path.exists(ACTIVITY_LOG_PATH):
        return False, f"Activity log not found: {ACTIVITY_LOG_PATH}"

    # Check if log is stale (older than 24 hours with minimal content)
    try:
        stat = os.stat(ACTIVITY_LOG_PATH)
        file_age_hours = (time.time() - stat.st_mtime) / 3600
        file_size = stat.st_size

        if file_size < 100 and file_age_hours > 24:
            return False, f"Activity log appears stale: {file_size} bytes, {file_age_hours:.1f}h old"
    except OSError as e:
        return False, f"Cannot stat activity log: {e}"

    return True, "OK"


# ============================================================================
# CACHED RESOURCES (SINGLETON PATTERN)
# ============================================================================
@st.cache_resource
def get_qdrant_client() -> QdrantClient:
    """Get cached Qdrant client - reused across sessions."""
    use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "26350")),
        api_key=os.getenv("QDRANT_API_KEY"),
        https=use_https,  # BP-040
        timeout=float(os.getenv("QDRANT_TIMEOUT", "10.0"))
    )


# ============================================================================
# CONNECTION VALIDATION
# ============================================================================
try:
    client = get_qdrant_client()
    # Verify connection by listing collections
    _ = client.get_collections()
except Exception as e:
    st.error(f"❌ **Failed to connect to Qdrant:** {e}")
    st.info("🔧 **Troubleshooting:** Check that Qdrant is running on the configured host/port.")
    st.code(f"QDRANT_HOST={os.getenv('QDRANT_HOST', 'localhost')}\nQDRANT_PORT={os.getenv('QDRANT_PORT', '26350')}")
    st.stop()  # Halt execution gracefully


# ============================================================================
# DATA FETCHING FUNCTIONS
# ============================================================================
@st.cache_data(ttl=600, max_entries=50)  # Cache for 10 minutes (BP-031) - projects rarely change
def get_unique_projects(_client: QdrantClient, collection_name: str) -> list[str]:
    """Get unique project IDs from collection, filtering out infrastructure pollution.

    Filters out project names that are likely from infrastructure directories
    that accidentally got captured (e.g., "docker", "scripts", "test", etc.)

    Returns:
        Sorted list of clean project names
    """
    try:
        # Scroll through points to extract unique group_ids
        points, _ = _client.scroll(
            collection_name=collection_name,
            limit=1000,
            with_payload=True,
            with_vectors=False
        )
        projects = set(p.payload.get("group_id", "unknown") for p in points)

        # Filter out infrastructure directory names that snuck in
        # Note: "shared" is intentional for conventions collection (v2.0)
        pollution_patterns = {"docker", "scripts", "test", "build", "tmp", "temp", "unknown"}
        clean_projects = {p for p in projects if p not in pollution_patterns}

        return sorted(list(clean_projects))
    except Exception:
        return []


@st.cache_data(ttl=300, max_entries=100)  # Cache for 5 minutes - balance freshness vs performance per BP-031
def get_type_counts(_client: QdrantClient, collection_name: str) -> dict[str, int]:
    """Get count of memories per type in a collection.

    C2: Uses Qdrant count() API for efficiency instead of scroll() which fetches all points.
    M1: Catches specific exceptions only (network/Qdrant errors).

    Args:
        _client: Qdrant client (underscore prevents Streamlit from hashing)
        collection_name: Collection to query

    Returns:
        Dictionary mapping type names to counts (e.g., {"implementation": 245, "error_fix": 32})
    """
    type_counts = {}
    expected_types = COLLECTION_TYPES.get(collection_name, [])

    for mem_type in expected_types:
        try:
            # C2: Use count() API instead of scroll() - massive performance improvement
            # Old: scroll(limit=10000) fetched all points just to count them
            # New: count() returns count directly without transferring point data
            result = _client.count(
                collection_name=collection_name,
                count_filter=Filter(
                    must=[FieldCondition(key="type", match=MatchValue(value=mem_type))]
                ),
                exact=True  # True = precise count, False = approximate (faster)
            )
            type_counts[mem_type] = result.count

        except (UnexpectedResponse, httpx.HTTPError, ConnectionError) as e:
            # M1: Catch specific exceptions only (not KeyboardInterrupt, SystemExit, etc.)
            st.warning(f"⚠️ Failed to count {mem_type} in {collection_name}: {e}")
            type_counts[mem_type] = 0  # Graceful degradation

    return type_counts


def get_embedding(text: str) -> Optional[list[float]]:
    """Generate embedding vector via embedding service."""
    embedding_url = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8080")

    try:
        response = httpx.post(
            f"{embedding_url}/embed",
            json={"texts": [text]},
            timeout=5.0
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]
    except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
        st.error(f"❌ **Embedding generation failed:** {e}")
        return None


def perform_search(query: str, collection: str, project: str, memory_type: str):
    """Execute semantic search and display results."""
    if not query.strip():
        st.warning("⚠️ Please enter a search query.")
        return

    # Generate embedding for query
    with st.spinner("🔄 Generating embedding..."):
        query_embedding = get_embedding(query)

    if query_embedding is None:
        st.error("Cannot perform search without embedding.")
        return

    # Build filter conditions
    must_conditions = []
    if project != "All":
        must_conditions.append({
            "key": "group_id",
            "match": {"value": project}
        })
    if memory_type != "All":
        must_conditions.append({
            "key": "type",
            "match": {"value": memory_type}
        })

    # Execute search
    try:
        with st.spinner("🔍 Searching memories..."):
            results = client.query_points(
                collection_name=collection,
                query=query_embedding,
                limit=20,
                score_threshold=0.70,  # Only show >70% relevance
                query_filter={"must": must_conditions} if must_conditions else None,
                with_payload=True
            ).points

        # Store in session state
        st.session_state["search_results"] = results
        st.session_state["last_query"] = query

        # Display result count
        st.success(f"✅ Found {len(results)} matching memories")

    except (UnexpectedResponse, httpx.HTTPError, ConnectionError) as e:
        st.error(f"❌ **Search failed:** {e}")


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================
def display_memory_card(memory: dict, index: int, point_id: str = None):
    """Display a single memory as an expandable card.

    Args:
        memory: Memory payload dictionary
        index: Card index (for auto-expand first result)
        point_id: Optional Qdrant point ID to display
    """
    # Extract key fields with fallbacks
    mem_type = memory.get("type", "unknown")
    timestamp = memory.get("timestamp", "N/A")
    if timestamp != "N/A" and len(timestamp) >= 10:
        timestamp = timestamp[:10]  # YYYY-MM-DD
    score = memory.get("score", 0.0)
    content = memory.get("content", "")

    # Expandable card (first result auto-expanded)
    with st.expander(
        f"**{mem_type}** | {timestamp} | Score: {score:.3f}",
        expanded=(index == 0)
    ):
        # Show Qdrant Point ID prominently if available
        if point_id:
            st.caption(f"🔑 **Qdrant Point ID:** `{point_id}`")

        # Content preview with scrollable container
        st.markdown("**Content:**")
        # Show preview by default, full content on demand
        PREVIEW_LENGTH = 500
        if len(content) <= PREVIEW_LENGTH:
            st.code(content, language="text")
        else:
            st.code(content[:PREVIEW_LENGTH] + f"... [{len(content) - PREVIEW_LENGTH} more chars]", language="text")
            if st.checkbox("📄 Show Full Content", key=f"full_content_{index}"):
                st.code(content, language="text")

        # Metrics in columns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Project", memory.get("group_id", "unknown"))
        with col2:
            st.metric("Source", memory.get("source_hook", "unknown"))
        with col3:
            st.metric("Importance", memory.get("importance", "normal"))

        # Full metadata toggle (nested expanders not allowed in Streamlit 1.52+)
        if st.checkbox("📋 Show Full Metadata", key=f"metadata_{index}"):
            st.json(memory, expanded=False)


def display_statistics():
    """Display collection statistics in sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Statistics")

    for collection_name in COLLECTION_NAMES:
        try:
            info = client.get_collection(collection_name)
            st.sidebar.metric(
                collection_name,
                f"{info.points_count:,} memories",
                delta=None
            )
        except Exception:
            st.sidebar.warning(f"⚠️ {collection_name}: unavailable")

    # Queue status - Unified JSONL queue (QUEUE-UNIFY: all hooks use same queue)
    queue_file = os.path.join(INSTALL_DIR, "queue", "pending_queue.jsonl")
    queue_count = 0
    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r') as f:
                queue_count = sum(1 for line in f if line.strip())
        except Exception:
            pass

    if queue_count > 0:
        st.sidebar.warning(f"⏳ **Queue:** {queue_count} pending")

    # Last update timestamp
    st.sidebar.caption(f"Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


@st.cache_data(ttl=60)  # Cache for 60s, invalidate on file change via mtime
def read_activity_log_cached(log_path: str, mtime: float) -> list[str]:
    """Read activity log with cache invalidation based on file modification time.

    BUG-022: Cache with mtime ensures fresh reads after container restart.
    Cache expires after 60s OR when file changes (mtime in cache key).

    Args:
        log_path: Path to activity log file
        mtime: File modification time (used as cache key)

    Returns:
        List of log lines
    """
    try:
        with open(log_path, 'r') as f:
            return f.readlines()
    except Exception as e:
        st.error(f"❌ Error reading log file: {e}")
        return []


def get_log_stats() -> dict:
    """Get activity log statistics.

    Returns:
        Dictionary with size_mb and lines count
    """
    if os.path.exists(ACTIVITY_LOG_PATH):
        try:
            stat = os.stat(ACTIVITY_LOG_PATH)
            size = stat.st_size
            with open(ACTIVITY_LOG_PATH, 'r') as f:
                lines = sum(1 for _ in f)
            return {
                "size_mb": size / 1024 / 1024,
                "lines": lines,
                "mtime": stat.st_mtime
            }
        except Exception:
            return {"size_mb": 0, "lines": 0, "mtime": 0}
    return {"size_mb": 0, "lines": 0, "mtime": 0}


def display_logs_page():
    """Display activity logs with filtering and controls.

    TECH-DEBT-014: Comprehensive activity logging with FULL_CONTENT expansion.
    All entries use st.expander() - entries with FULL_CONTENT show expanded details.
    BUG-022: Added cache with mtime-based invalidation and manual refresh.
    """
    st.title("📋 Activity Logs")

    # Validate log mount - CRITICAL: Detect stale/missing logs early
    log_valid, log_message = validate_log_mount()
    if not log_valid:
        st.error("⚠️ **Volume Mount Issue Detected**")
        st.warning(f"**Problem**: {log_message}")
        st.code(f"Container BMAD_INSTALL_DIR: {INSTALL_DIR}\nExpected log path: {ACTIVITY_LOG_PATH}")
        st.info("🔧 **Fix**: Restart Docker Compose with `BMAD_INSTALL_DIR` environment variable set, or check `docker/.env` file.")
        # Continue anyway to show whatever logs exist

    # BUG-022: Log stats and manual refresh button
    stats = get_log_stats()
    col_stat1, col_stat2, col_stat3 = st.columns([2, 2, 2])
    with col_stat1:
        st.metric("Log Size", f"{stats['size_mb']:.2f} MB")
    with col_stat2:
        st.metric("Total Lines", f"{stats['lines']:,}")
    with col_stat3:
        if st.button("🔄 Force Refresh", type="primary", help="Clear cache and reload logs"):
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")

    # Filter by hook type - PROMINENT at top
    filter_type = st.selectbox(
        "🔍 Filter by Hook Type",
        ["All Types", "🧠 SessionStart", "📤 PreCompact", "📥 Capture", "🔧 PreToolUse",
         "📋 PostToolUse", "🔴 Error", "💾 ManualSave", "🔍 Search", "💬 UserPrompt",
         "🔔 Notification", "⏹️ Stop", "🤖 Subagent", "🔚 SessionEnd", "🎯 BestPractices"],
        key="log_type_filter"
    )

    # Controls row
    col1, col2, col3 = st.columns([2, 4, 1])

    with col1:
        auto_refresh = st.checkbox("🔄 Auto-refresh (5s)", key="auto_refresh")

    with col2:
        search_text = st.text_input(
            "Search logs...",
            placeholder="Filter by text...",
            key="log_search"
        )

    with col3:
        if st.button("🗑️ Clear Logs", type="secondary", key="clear_logs"):
            if os.path.exists(ACTIVITY_LOG_PATH):
                try:
                    os.remove(ACTIVITY_LOG_PATH)
                    st.success("✅ Logs cleared!")
                    st.cache_data.clear()  # BUG-022: Clear cache after deleting log
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to clear logs: {e}")
            else:
                st.warning("⚠️ No log file found")

    st.markdown("---")

    # Read and display logs (TECH-DEBT-014: Parse FULL_CONTENT format)
    # BUG-022: Use cached reader with mtime-based invalidation
    if os.path.exists(ACTIVITY_LOG_PATH):
        try:
            # Get current mtime for cache key
            mtime = stats['mtime']
            lines = read_activity_log_cached(ACTIVITY_LOG_PATH, mtime)

            # Parse entries - group summaries with their FULL_CONTENT
            entries = []
            i = len(lines) - 1

            while i >= 0:
                line = lines[i].strip()
                if not line:
                    i -= 1
                    continue

                # Check if this is a FULL_CONTENT line
                if "📄 FULL_CONTENT:" in line:
                    # Extract full content (escaped newlines → real newlines)
                    parts = line.split("📄 FULL_CONTENT:", 1)
                    full_content = parts[1].replace('\\n', '\n') if len(parts) > 1 else ""

                    # Look for previous summary line
                    if i > 0:
                        prev_line = lines[i - 1].strip()
                        if prev_line and "📄 FULL_CONTENT:" not in prev_line:
                            entries.append({
                                'summary': prev_line,
                                'full_content': full_content,
                                'has_content': True
                            })
                            i -= 2
                            continue

                    i -= 1
                else:
                    # Regular summary line without full content
                    entries.append({
                        'summary': line,
                        'full_content': None,
                        'has_content': False
                    })
                    i -= 1

            # Display entries (already in reverse chronological order)
            total_entries = len(entries)
            display_limit = 100
            st.caption(f"Showing {min(total_entries, display_limit)} of {total_entries} recent activity log entries (newest first)")

            # Apply filters and display with EXPANDERS for ALL entries
            displayed = 0
            for idx, entry in enumerate(entries[:display_limit]):
                summary = entry['summary']

                # Apply type filter
                if filter_type != "All Types":
                    # Extract the icon and keyword from filter
                    filter_parts = filter_type.split()
                    filter_icon = filter_parts[0] if filter_parts else ""
                    filter_keyword = filter_parts[1] if len(filter_parts) > 1 else ""

                    # Check if entry matches filter (icon OR keyword in summary)
                    if filter_icon not in summary and filter_keyword.lower() not in summary.lower():
                        continue

                # Apply search filter
                if search_text and search_text.lower() not in summary.lower():
                    if entry['full_content'] and search_text.lower() in entry['full_content'].lower():
                        pass  # Match in full content - show it
                    else:
                        continue

                displayed += 1

                # Detect icon for visual indicator
                if "🧠" in summary:
                    icon = "🧠"
                elif "📤" in summary:
                    icon = "📤"
                elif "📥" in summary:
                    icon = "📥"
                elif "🔴" in summary:
                    icon = "🔴"
                elif "💾" in summary:
                    icon = "💾"
                elif "🔍" in summary:
                    icon = "🔍"
                elif "🔧" in summary:
                    icon = "🔧"
                elif "📋" in summary:
                    icon = "📋"
                elif "💬" in summary:
                    icon = "💬"
                elif "🔔" in summary:
                    icon = "🔔"
                elif "🔐" in summary:
                    icon = "🔐"
                elif "⏹️" in summary:
                    icon = "⏹️"
                elif "🤖" in summary:
                    icon = "🤖"
                elif "🔚" in summary:
                    icon = "🔚"
                elif "🎯" in summary:
                    icon = "🎯"
                elif "⚠️" in summary:
                    icon = "⚠️"
                else:
                    icon = "📝"

                # ALWAYS use st.expander for every entry
                # Truncate summary for title (remove timestamp prefix for cleaner display)
                summary_display = summary
                if len(summary_display) > 100:
                    summary_display = summary_display[:100] + "..."

                with st.expander(summary_display, expanded=False, icon=icon):
                    if entry['has_content'] and entry['full_content']:
                        # Show full content in code block
                        st.code(entry['full_content'], language=None)
                    elif len(summary) > 100:
                        # Show full summary text if it was truncated in title
                        st.text(summary)

            if displayed == 0:
                st.info("ℹ️ No log entries match your filters")

        except Exception as e:
            st.error(f"❌ Error reading logs: {e}")
            import traceback
            st.code(traceback.format_exc(), language="python")
    else:
        st.warning("⚠️ No activity log found")
        st.info(f"Expected location: `{ACTIVITY_LOG_PATH}`")

    # Auto-refresh logic
    if auto_refresh:
        time.sleep(5)
        st.rerun()


def display_statistics_page():
    """Display detailed statistics page (V2.0 with type breakdown)."""
    st.title("📊 Memory Statistics")

    st.markdown("### Collection Overview")

    # Collection stats in cards
    cols = st.columns(3)
    for idx, collection_name in enumerate(COLLECTION_NAMES):
        with cols[idx]:
            try:
                info = client.get_collection(collection_name)
                st.metric(
                    label=collection_name.replace("-", " ").title(),
                    value=f"{info.points_count:,}",
                    delta=None,
                    help=f"Total memories in {collection_name}"
                )

                # Additional details
                st.caption(f"Vector size: {info.config.params.vectors.size if hasattr(info.config.params, 'vectors') else 'N/A'}")
            except Exception as e:
                st.error(f"❌ {collection_name}")
                st.caption(str(e)[:50])

    # R2: Type breakdown per collection (V2.0 spec Section 11.4)
    st.markdown("---")
    st.markdown("### Type Breakdown by Collection")

    for idx, collection_name in enumerate(COLLECTION_NAMES):
        # H3: Only expand first collection to reduce vertical space usage
        with st.expander(f"📂 {collection_name}", expanded=(idx == 0)):
            try:
                # Get collection info for total count
                info = client.get_collection(collection_name)
                total_count = info.points_count

                # Get type counts
                type_counts = get_type_counts(client, collection_name)

                if total_count > 0 and type_counts:
                    # Display tree format per V2.0 spec
                    st.markdown(f"**{collection_name}:** {total_count:,} memories")

                    # Tree-style breakdown
                    types_list = list(type_counts.items())
                    for type_idx, (mem_type, count) in enumerate(types_list):
                        # Use └── for last item, ├── for others
                        prefix = "└──" if type_idx == len(types_list) - 1 else "├──"
                        st.text(f"{prefix} {mem_type}: {count:,}")

                    # R3: Type distribution chart (bar chart for clarity)
                    st.markdown("**Distribution Chart:**")

                    # M2: Validate chart data before rendering (handle empty/zero counts)
                    if type_counts and any(count > 0 for count in type_counts.values()):
                        # Prepare data for chart
                        chart_data = {
                            "Type": list(type_counts.keys()),
                            "Count": list(type_counts.values())
                        }
                        # Use Streamlit's built-in bar chart (simple and effective)
                        st.bar_chart(chart_data, x="Type", y="Count", height=250)
                    else:
                        st.caption("No data to visualize (all counts are zero)")

                elif total_count == 0:
                    st.info(f"ℹ️ No memories in {collection_name}")
                else:
                    st.warning(f"⚠️ Could not retrieve type breakdown")

            except Exception as e:
                st.error(f"❌ Error analyzing {collection_name}: {e}")

    st.markdown("---")
    st.markdown("### Retry Queue Status")
    st.caption("QUEUE-UNIFY: All hooks and scripts use unified JSONL queue with automatic retry")

    # Unified JSONL queue with automatic retry (exponential backoff)
    queue_file = os.path.join(INSTALL_DIR, "queue", "pending_queue.jsonl")

    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            queue_count = len(lines)

            if queue_count > 0:
                st.warning(f"⏳ **{queue_count} items pending** (auto-retry with exponential backoff)")

                # Parse and display stats
                reasons = {}
                exhausted = 0
                ready = 0
                for line in lines:
                    try:
                        item = json.loads(line)
                        reason = item.get("failure_reason", "unknown")
                        reasons[reason] = reasons.get(reason, 0) + 1
                        if item.get("retry_count", 0) >= item.get("max_retries", 3):
                            exhausted += 1
                        else:
                            ready += 1
                    except json.JSONDecodeError:
                        pass

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Ready for retry", ready)
                with col2:
                    st.metric("Exhausted (max retries)", exhausted)

                if reasons:
                    st.markdown("**By failure reason:**")
                    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                        st.text(f"  • {reason}: {count}")

                # Action buttons
                st.markdown("**Actions:**")
                btn_col1, btn_col2, btn_col3 = st.columns(3)

                with btn_col1:
                    if st.button("🔄 Process Queue", key="process_queue_btn", type="primary"):
                        with st.spinner("Processing queue..."):
                            try:
                                # Import and run queue processor
                                sys.path.insert(0, "/app/src")
                                from memory.queue import MemoryQueue
                                from memory.storage import MemoryStorage
                                from memory.models import MemoryType
                                from memory.config import COLLECTION_CODE_PATTERNS

                                queue = MemoryQueue()
                                storage = MemoryStorage()
                                pending = queue.get_pending(limit=50)

                                success_count = 0
                                fail_count = 0

                                for entry in pending:
                                    try:
                                        memory_data = entry.get("memory_data", {})
                                        content = memory_data.get("content", "")

                                        if content and len(content) >= 20:
                                            result = storage.store_memory(
                                                content=content,
                                                cwd="/",
                                                group_id=memory_data.get("group_id", "unknown"),
                                                memory_type=MemoryType.IMPLEMENTATION,
                                                source_hook="retry",
                                                session_id="retry",
                                                collection=COLLECTION_CODE_PATTERNS,
                                            )
                                            if result["status"] in ["stored", "duplicate"]:
                                                queue.dequeue(entry["id"])
                                                success_count += 1
                                            else:
                                                queue.mark_failed(entry["id"])
                                                fail_count += 1
                                        else:
                                            # Remove items with no content
                                            queue.dequeue(entry["id"])
                                            success_count += 1
                                    except Exception as e:
                                        queue.mark_failed(entry["id"])
                                        fail_count += 1

                                st.success(f"✅ Processed: {success_count} success, {fail_count} failed")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {e}")

                with btn_col2:
                    if st.button("🗑️ Clear Queue", key="clear_queue_btn"):
                        try:
                            from memory.queue import MemoryQueue
                            queue = MemoryQueue()
                            pending = queue.get_pending(limit=1000, include_exhausted=True)
                            for entry in pending:
                                queue.dequeue(entry["id"])
                            st.success(f"✅ Cleared {len(pending)} items")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")

                with btn_col3:
                    if st.button("🔄 Refresh", key="refresh_queue_btn"):
                        st.rerun()

                with st.expander("View Queue Items"):
                    for idx, line in enumerate(lines[:10], 1):
                        try:
                            item = json.loads(line)
                            st.json(item, expanded=False)
                        except json.JSONDecodeError:
                            st.code(f"Item {idx}: {line[:100]}...", language="text")
                    if queue_count > 10:
                        st.caption(f"... and {queue_count - 10} more")
            else:
                st.success("✅ Queue is empty - all items processed successfully")
        except Exception as e:
            st.error(f"❌ Error reading queue: {e}")
    else:
        st.success("✅ No queue file - nothing pending")

    st.markdown("---")
    st.markdown("### System Info")

    # System info
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.metric("Qdrant Host", os.getenv("QDRANT_HOST", "localhost"))
        # Show external port for user reference, internal port for container
        qdrant_port = os.getenv("QDRANT_EXTERNAL_PORT") or os.getenv("QDRANT_PORT", "26350")
        st.metric("Qdrant Port (External)", qdrant_port)
    with info_col2:
        st.metric("Embedding Service", os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8080"))
        st.metric("Log Location", ACTIVITY_LOG_PATH)


# ============================================================================
# SIDEBAR (NAVIGATION & FILTERS)
# ============================================================================
st.sidebar.title("🧠 BMAD Memory Browser")

# Page navigation
page = st.sidebar.radio(
    "Navigation",
    ["🔍 Memory Browser", "📋 Activity Logs", "📊 Statistics"],
    key="page_select"
)

st.sidebar.markdown("---")

# Show filters only for Memory Browser page
if page == "🔍 Memory Browser":
    st.sidebar.subheader("Filters")

    collection = st.sidebar.selectbox(
        "Collection",
        COLLECTION_NAMES,
        key="collection_select"  # Explicit key prevents widget resets
    )

    # Get unique projects from collection
    projects = get_unique_projects(client, collection)
    project = st.sidebar.selectbox(
        "Project",
        ["All"] + projects,
        key="project_select"
    )

    # R1: Dynamic type dropdown based on collection (V2.0)
    collection_types = COLLECTION_TYPES.get(collection, [])
    memory_type = st.sidebar.selectbox(
        "Type",
        ["All"] + collection_types,
        key=f"type_select_{collection}"  # Unique key per collection prevents state bleed
    )

    search_query = st.sidebar.text_input(
        "Search",
        placeholder="Enter search query...",
        key="search_input"
    )

    if st.sidebar.button("🔍 Search", type="primary", key="search_button"):
        st.session_state["perform_search"] = True

# Display statistics panel
display_statistics()


# ============================================================================
# MAIN CONTENT (PAGE ROUTING)
# ============================================================================

if page == "📋 Activity Logs":
    display_logs_page()

elif page == "📊 Statistics":
    display_statistics_page()

else:  # Default: 🔍 Memory Browser
    st.title("🧠 BMAD Memory Browser")

    # Execute search if triggered
    if st.session_state.get("perform_search", False):
        perform_search(search_query, collection, project, memory_type)
        st.session_state["perform_search"] = False  # Reset trigger

    # Display search results or recent memories
    if "search_results" in st.session_state:
        results = st.session_state["search_results"]
        st.subheader(f"🔍 Search Results ({len(results)} found)")

        if len(results) == 0:
            st.info("No results found matching your criteria. Try adjusting your query or filters.")
        else:
            for idx, result in enumerate(results):
                # Merge payload with score
                memory_data = result.payload.copy()
                memory_data["score"] = result.score
                # Pass Qdrant point ID for display
                display_memory_card(memory_data, idx, point_id=str(result.id))
    else:
        st.info("👈 Use the sidebar to search memories or browse by collection.")
        st.markdown("""
        ### Getting Started

        1. Select a **Collection** (code-patterns, conventions, or discussions)
        2. Optionally filter by **Project** or **Type**
        3. Enter a **Search Query** (semantic search)
        4. Click **🔍 Search**

        Results will show memories ranked by relevance (score >0.70).
        """)
