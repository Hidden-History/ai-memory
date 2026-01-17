"""
BMAD Memory Browser - Streamlit Dashboard
Story 6.4: Streamlit Memory Browser

2026 Best Practices:
- st.set_page_config() MUST be first Streamlit command
- Explicit widget keys (key-based identity in Streamlit 1.50+)
- @st.cache_resource for connections (singleton)
- @st.cache_data(ttl=N) for data with expiration
- Graceful error handling with st.stop()
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
# CACHED RESOURCES (SINGLETON PATTERN)
# ============================================================================
@st.cache_resource
def get_qdrant_client() -> QdrantClient:
    """Get cached Qdrant client - reused across sessions."""
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "26350")),
        timeout=10.0  # 10s timeout for requests
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
@st.cache_data(ttl=60)  # Cache for 60 seconds
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
        # Note: "shared" is intentional for best_practices collection
        pollution_patterns = {"docker", "scripts", "test", "build", "tmp", "temp", "unknown"}
        clean_projects = {p for p in projects if p not in pollution_patterns}

        return sorted(list(clean_projects))
    except Exception:
        return []


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
    except Exception as e:
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

    except Exception as e:
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
        st.code(content[:500] + ("..." if len(content) > 500 else ""), language="text")

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

    for collection_name in ["implementations", "best_practices", "agent-memory"]:
        try:
            info = client.get_collection(collection_name)
            st.sidebar.metric(
                collection_name,
                f"{info.points_count:,} memories",
                delta=None
            )
        except Exception:
            st.sidebar.warning(f"⚠️ {collection_name}: unavailable")

    # Queue status (from retry queue directory)
    queue_dir = os.path.join(INSTALL_DIR, "queue", "pending")
    if os.path.exists(queue_dir):
        queue_count = len([f for f in os.listdir(queue_dir) if f.endswith(".json")])
        if queue_count > 0:
            st.sidebar.warning(f"⏳ **Queue:** {queue_count} pending")

    # Last update timestamp
    st.sidebar.caption(f"Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def display_logs_page():
    """Display activity logs with filtering and controls.

    TECH-DEBT-014: Comprehensive activity logging with FULL_CONTENT expansion.
    All entries use st.expander() - entries with FULL_CONTENT show expanded details.
    """
    st.title("📋 Activity Logs")

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
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to clear logs: {e}")
            else:
                st.warning("⚠️ No log file found")

    st.markdown("---")

    # Read and display logs (TECH-DEBT-014: Parse FULL_CONTENT format)
    if os.path.exists(ACTIVITY_LOG_PATH):
        try:
            with open(ACTIVITY_LOG_PATH, 'r') as f:
                lines = f.readlines()

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
                    else:
                        # No detailed content - show helpful message
                        st.caption("ℹ️ No detailed content for this entry (logged before TECH-DEBT-014)")
                        if len(summary) > 100:
                            st.text(summary)  # Show full text if it was truncated

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
    """Display detailed statistics page."""
    st.title("📊 Memory Statistics")

    st.markdown("### Collection Overview")

    # Collection stats in cards
    cols = st.columns(3)
    for idx, collection_name in enumerate(["implementations", "best_practices", "agent-memory"]):
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

    st.markdown("---")
    st.markdown("### Queue Status")

    # Queue status
    queue_dir = os.path.join(INSTALL_DIR, "queue", "pending")
    if os.path.exists(queue_dir):
        queue_files = [f for f in os.listdir(queue_dir) if f.endswith(".json")]
        queue_count = len(queue_files)

        if queue_count > 0:
            st.warning(f"⏳ **{queue_count} items pending** in retry queue")

            # Show details in expander
            with st.expander("View Queue Items"):
                for qfile in queue_files[:10]:  # Show first 10
                    st.code(qfile, language="text")
                if queue_count > 10:
                    st.caption(f"... and {queue_count - 10} more")
        else:
            st.success("✅ Queue is empty")
    else:
        st.info("ℹ️ Queue directory not found")

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
        ["implementations", "best_practices", "agent-memory"],
        key="collection_select"  # Explicit key prevents widget resets
    )

    # Get unique projects from collection
    projects = get_unique_projects(client, collection)
    project = st.sidebar.selectbox(
        "Project",
        ["All"] + projects,
        key="project_select"
    )

    memory_type = st.sidebar.selectbox(
        "Type",
        ["All", "implementation", "session_summary", "decision", "pattern", "best_practice", "error_pattern"],
        key="type_select"
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

        1. Select a **Collection** (implementations, best_practices, or agent-memory)
        2. Optionally filter by **Project** or **Type**
        3. Enter a **Search Query** (semantic search)
        4. Click **🔍 Search**

        Results will show memories ranked by relevance (score >0.70).
        """)
