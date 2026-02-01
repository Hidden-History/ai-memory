"""Multi-session memory persistence tests.

Uses MemoryStorage for storage (with real embeddings) to test semantic retrieval.
Full PostToolUse flow will be tested after Epic 5 delivers background embedding worker.

References:
- architecture.md:282 "Store Without Embedding + Backfill" pattern
- FR14: Multi-project isolation via group_id filtering
- NFR-R2: Data persistence requirements
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

# Import core modules for direct storage
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.config import get_config
from memory.models import MemoryType
from memory.storage import MemoryStorage

# Hook script path for SessionStart
SESSION_START = (
    Path(__file__).parent.parent.parent
    / ".claude"
    / "hooks"
    / "scripts"
    / "session_start.py"
)


def get_python_exe():
    """Get the Python executable to use for subprocess calls."""
    project_root = Path(__file__).parent.parent.parent
    venv_python = project_root / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def get_test_env():
    """Get environment variables for subprocess calls."""
    env = os.environ.copy()
    env["EMBEDDING_READ_TIMEOUT"] = "60.0"  # CPU mode needs 20-30s
    env["QDRANT_URL"] = "http://localhost:26350"
    env["SIMILARITY_THRESHOLD"] = "0.4"  # Production threshold (TECH-DEBT-002)

    # Add project src/ to PYTHONPATH for development mode
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"
    env["PYTHONPATH"] = str(src_dir) + ":" + env.get("PYTHONPATH", "")

    return env


@pytest.mark.integration
@pytest.mark.slow
class TestMultiSessionMemory:
    """Test memory persists and retrieves across multiple sessions."""

    def test_memory_persists_across_sessions(self):
        """Store in session 1, retrieve in session 2 and session 3.

        Validates:
        - Memory stored in session-1 is retrievable in session-2
        - Memory persists through session-3 (long-term persistence)
        - Session IDs are different but group_id filtering works
        - No session ID leakage into context (privacy)
        """
        config = get_config()
        storage = MemoryStorage(config)

        project_name = f"multi-session-test-{uuid.uuid4().hex[:8]}"
        unique_marker = uuid.uuid4().hex[:12]
        # Content with project context for semantic matching (TECH-DEBT-002)
        unique_content = (
            f"Working on {project_name}: Implementation of dependency injection pattern "
            f"for service architecture. Test marker: {unique_marker}.\n\n"
            f"Code implementation:\n"
            f"def multi_session_test_{unique_marker}():\n"
            f"    '''Multi-session persistence test'''\n"
            "    return 'dependency injection pattern'"
        )

        print(f"\n{'=' * 70}")
        print("  MULTI-SESSION PERSISTENCE TEST")
        print(f"  Project: {project_name}")
        print(f"={'=' * 70}\n")

        # Session 1: Store via MemoryStorage
        print("[SESSION 1] Storing memory...")
        session1_id = f"session-{uuid.uuid4().hex[:8]}"

        result = storage.store_memory(
            content=unique_content,
            cwd=f"/tmp/{project_name}",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="seed_script",
            session_id=session1_id,
        )

        assert result["status"] == "stored", f"Storage failed: {result}"
        assert result["embedding_status"] == "complete", "Embeddings not generated"
        print(f"✓ Memory stored (session_id: {session1_id})")
        print(f"  Memory ID: {result['memory_id']}")

        # Session 2: Retrieve via SessionStart hook (different session_id)
        print("\n[SESSION 2] Retrieving from different session...")
        session2_id = f"session-{uuid.uuid4().hex[:8]}"

        hook_input = {
            "cwd": f"/tmp/{project_name}",
            "session_id": session2_id,  # Different session!
        }

        proc = subprocess.run(
            [get_python_exe(), str(SESSION_START)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=150,
            env=get_test_env(),
        )

        assert proc.returncode == 0, f"SessionStart failed: {proc.stderr}"

        context_session2 = proc.stdout

        # Memory from session-1 should be retrievable in session-2
        assert (
            unique_marker in context_session2
            or "dependency injection" in context_session2.lower()
        ), (
            f"Memory from session 1 NOT available in session 2!\n"
            f"Expected marker: {unique_marker}\n"
            f"Got: {context_session2[:500]}"
        )

        # Privacy check: Session 1 ID should not leak
        assert session1_id not in context_session2, (
            f"Session ID leaked into context!\n"
            f"Found: {session1_id}\n"
            f"Context: {context_session2[:500]}"
        )

        print(f"✓ Session 2 retrieved session 1 memory (session_id: {session2_id})")
        print("  No session ID leakage ✓")

        # Session 3: Still available (long-term persistence)
        print("\n[SESSION 3] Verifying long-term persistence...")
        time.sleep(1)  # Small gap between sessions
        session3_id = f"session-{uuid.uuid4().hex[:8]}"

        hook_input["session_id"] = session3_id

        proc = subprocess.run(
            [get_python_exe(), str(SESSION_START)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=150,
            env=get_test_env(),
        )

        assert proc.returncode == 0, f"SessionStart failed: {proc.stderr}"

        context_session3 = proc.stdout

        assert (
            unique_marker in context_session3
            or "dependency injection" in context_session3.lower()
        ), (
            f"Memory lost after session 2! Persistence failure.\n"
            f"Expected marker: {unique_marker}\n"
            f"Got: {context_session3[:500]}"
        )

        print(f"✓ Session 3 retrieved session 1 memory (session_id: {session3_id})")

        print(f"\n{'=' * 70}")
        print("  ✅ Memory persisted across 3 sessions:")
        print(f"     Session 1 (store): {session1_id}")
        print(f"     Session 2 (retrieve): {session2_id}")
        print(f"     Session 3 (retrieve): {session3_id}")
        print(f"{'=' * 70}\n")
