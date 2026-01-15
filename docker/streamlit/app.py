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
import os
import sys
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
# CACHED RESOURCES (SINGLETON PATTERN)
# ============================================================================
@st.cache_resource
def get_qdrant_client() -> QdrantClient:
    """Get cached Qdrant client - reused across sessions."""
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "16350")),
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
    st.code(f"QDRANT_HOST={os.getenv('QDRANT_HOST', 'localhost')}\nQDRANT_PORT={os.getenv('QDRANT_PORT', '16350')}")
    st.stop()  # Halt execution gracefully


# ============================================================================
# DATA FETCHING FUNCTIONS
# ============================================================================
@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_unique_projects(_client: QdrantClient, collection_name: str) -> list[str]:
    """Get unique project IDs from collection."""
    try:
        # Scroll through points to extract unique group_ids
        points, _ = _client.scroll(
            collection_name=collection_name,
            limit=1000,
            with_payload=True,
            with_vectors=False
        )
        projects = set(p.payload.get("group_id", "unknown") for p in points)
        return sorted(list(projects))
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
def display_memory_card(memory: dict, index: int):
    """Display a single memory as an expandable card."""
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

    for collection_name in ["implementations", "best_practices"]:
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
    queue_dir = os.path.expanduser("~/.claude-memory/queue/pending")
    if os.path.exists(queue_dir):
        queue_count = len([f for f in os.listdir(queue_dir) if f.endswith(".json")])
        if queue_count > 0:
            st.sidebar.warning(f"⏳ **Queue:** {queue_count} pending")

    # Last update timestamp
    st.sidebar.caption(f"Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ============================================================================
# SIDEBAR (FILTERS)
# ============================================================================
st.sidebar.title("🧠 BMAD Memory Browser")

collection = st.sidebar.selectbox(
    "Collection",
    ["implementations", "best_practices"],
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
# MAIN CONTENT
# ============================================================================
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
            display_memory_card(memory_data, idx)
else:
    st.info("👈 Use the sidebar to search memories or browse by collection.")
    st.markdown("""
    ### Getting Started

    1. Select a **Collection** (implementations or best_practices)
    2. Optionally filter by **Project** or **Type**
    3. Enter a **Search Query** (semantic search)
    4. Click **🔍 Search**

    Results will show memories ranked by relevance (score >0.70).
    """)
