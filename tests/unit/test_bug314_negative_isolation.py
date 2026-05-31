"""BUG-314 two-project negative-isolation test through PRODUCTION entry points.

Proves an agent operating in project A can never write to, or read from, project
B's group_id — in either direction — when the scope is resolved by the shared
resolve_project_id and stored/searched by the real production code paths.

What is real vs stubbed (per BP-166 Q4):
- REAL: the save entry point (scripts/memory/parzival_save_handoff.py ``main()``),
  MemoryStorage.store_agent_memory, MemorySearch.search, and resolve_project_id.
- REAL ENGINE: an in-memory ``QdrantClient(":memory:")`` (a real Qdrant engine, not
  a mock) — no Docker required, like tests/integration/test_tenant_isolation.py.
- STUBBED: only the external embedding service (a deterministic unit vector), which
  is irrelevant to the tenant-isolation logic under test.

This DEC-PM314-D2 tenant-isolation regression needs NO Docker (``:memory:`` engine),
so it lives in the always-on unit lane (``tests/unit``) — keeping it under the
``integration`` marker would have excluded it from both the default unit run and the
release gate (both run ``--ignore=tests/integration``).

Case coverage (DONE-WHEN):
  1. WRITE A↛B  — save scoped A; B-scoped search finds nothing; stored group_id == A.
  2. READ  B↛A — seed A and B; resolve B on the READ path (not a hardcoded id) and
     prove that B-resolved search returns zero A-results.
  3. MISMATCH env=A / cwd=B(git) — resolver picks env A deterministically; the
     cwd-git-resolved B id sees nothing the env-A write produced.
  4. WRAPPER non-clobber — covered in tests/unit/test_resolve_project_id.py
     (TestWrapperNonClobber): caller A beats install B; install-global never injected.
  5. FAIL-LOUD — no env, non-git cwd → friendly error, nothing written.
  6. REALISTIC-SIZE — case 1 uses a full multi-section handoff document.
  7. MARKER TIER — a .ai-memory-project marker scopes the write; env overrides it.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from memory.config import COLLECTION_DISCUSSIONS, MemoryConfig  # noqa: E402

_SAVE_SCRIPT = _REPO / "scripts" / "memory" / "parzival_save_handoff.py"


def _unit_vector() -> list[float]:
    vec = [0.0] * 768
    vec[0] = 1.0
    return vec


@pytest.fixture
def mem_env(monkeypatch) -> types.SimpleNamespace:
    """In-memory Qdrant engine wired into the real storage + search code paths."""
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=COLLECTION_DISCUSSIONS,
        vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
    )
    client.create_payload_index(
        collection_name=COLLECTION_DISCUSSIONS,
        field_name="group_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )

    # Route both storage and search at the shared in-memory engine.
    monkeypatch.setattr("memory.storage.get_qdrant_client", lambda *a, **k: client)
    monkeypatch.setattr("memory.search.get_qdrant_client", lambda *a, **k: client)
    # Stub only the external embedding service: deterministic unit vector per text.
    monkeypatch.setattr(
        "memory.embeddings.EmbeddingClient.embed",
        lambda self, texts, *a, **k: [_unit_vector() for _ in texts],
    )
    monkeypatch.setenv("PARZIVAL_ENABLED", "true")
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    # Pin the save script's INSTALL_DIR to THIS worktree so its module-level
    # sys.path.insert points at the worktree src (never the installed package),
    # keeping every memory.* import single-sourced and deterministic.
    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(_REPO))

    # Keep the in-memory engine to a single plain dense vector: disable hybrid
    # dense+sparse storage (the install enables it) so we need no bm25 sparse
    # config or the external sparse-embedding service. Tenant isolation is
    # vector-scheme agnostic — group_id filtering is what is under test.
    cfg = MemoryConfig(hybrid_search_enabled=False, colbert_reranking_enabled=False)
    monkeypatch.setattr("memory.config.get_config", lambda: cfg)
    return types.SimpleNamespace(client=client, cfg=cfg)


@pytest.fixture
def save_module(mem_env, monkeypatch):
    spec = importlib.util.spec_from_file_location("_bug314_save_handoff", _SAVE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # main() calls get_config() via the module's bound name — point it at the
    # hybrid-off config so storage uses the plain dense vector scheme.
    monkeypatch.setattr(module, "get_config", lambda: mem_env.cfg)
    return module


def _make_git_repo(path: Path, remote_url: str) -> None:
    git_dir = path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        f'[remote "origin"]\n\turl = {remote_url}\n', encoding="utf-8"
    )


def _save(save_module, monkeypatch, tmp_path, *, content, env_project, cwd) -> int:
    """Invoke the real save-script main() with controlled scope inputs."""
    if env_project is None:
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    else:
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", env_project)
    handoff = tmp_path / f"handoff_{uuid.uuid4().hex[:8]}.md"
    handoff.write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["parzival_save_handoff.py", "--file", str(handoff)]
    )
    monkeypatch.chdir(cwd)
    return save_module.main()


def _search(cfg, group_id: str) -> list[dict]:
    from memory.search import MemorySearch

    return MemorySearch(cfg).search(
        query="session handoff",
        group_id=group_id,
        collection=COLLECTION_DISCUSSIONS,
        memory_type=["agent_handoff"],
        limit=50,
    )


def _resolve_read_scope(monkeypatch, *, env_project=None, cwd=None) -> str:
    """Resolve the READ-path group_id exactly as production does.

    The negative-isolation guarantee (BP-166 Q4 Case 2) requires proving the id
    fed into the search floor is produced by the RESOLVER on the read path — not a
    hardcoded literal. This sets the same scope inputs a reader would have (env
    and/or cwd) and returns ``resolve_project_id``'s answer, which the caller then
    feeds into :func:`_search`.
    """
    from memory.project import resolve_project_id

    if env_project is None:
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    else:
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", env_project)
    return resolve_project_id(cwd)


def _scroll_group(client: QdrantClient, group_id: str) -> list:
    pts, _ = client.scroll(
        collection_name=COLLECTION_DISCUSSIONS,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="group_id", match=models.MatchValue(value=group_id)
                )
            ]
        ),
        limit=1000,
        with_payload=True,
    )
    return pts


_REALISTIC_HANDOFF = (
    "# PM #999 — Session Handoff (realistic-size production artifact)\n\n"
    + "## Context\n"
    + ("Tenant-isolation regression coverage for BUG-314. " * 40)
    + "\n\n## Decisions\n"
    + "".join(
        f"- DEC-PM999-D{i}: locked decision number {i} with rationale.\n"
        for i in range(1, 40)
    )
    + "\n## Next Steps\n"
    + "".join(
        f"{i}. Follow-up action item {i} carried into the next session.\n"
        for i in range(1, 40)
    )
    + "\n## Notes\n"
    + ("Cross-session continuity must never silently degrade. " * 60)
)


def test_write_a_not_visible_to_b(mem_env, save_module, monkeypatch, tmp_path):
    """Case 1 + 6: realistic-size save scoped A; B sees nothing; stored group_id == A."""
    nongit = tmp_path / "ws_a"
    nongit.mkdir()
    marker = "isolationmarkeralpha"
    content = _REALISTIC_HANDOFF + f"\n\nMARKER-{marker}\n"

    rc = _save(
        save_module,
        monkeypatch,
        tmp_path,
        content=content,
        env_project="proj-a",
        cwd=nongit,
    )
    assert rc == 0

    a_points = _scroll_group(mem_env.client, "proj-a")
    assert a_points, "save did not store under project A"
    assert all(p.payload["group_id"] == "proj-a" for p in a_points)
    # Realistic doc is chunked into multiple vectors; the marker lands in one
    # chunk. Scroll returns ALL of A's points, so this is a reliable positive
    # control (semantic top-k ranking over identical stub vectors is arbitrary).
    assert any(
        marker in p.payload.get("content", "") for p in a_points
    ), "A's own write is not retrievable under project A"

    assert (
        _search(mem_env.cfg, "proj-b") == []
    ), "ISOLATION VIOLATION: project B saw project A's write"
    assert _search(mem_env.cfg, "proj-a"), "A cannot read its own project via search"


def test_read_b_excludes_a(mem_env, save_module, monkeypatch, tmp_path):
    """Case 2: seed A and B; the RESOLVED B read scope returns zero A-results."""
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    a_marker, b_marker = "markeraaaaalpha", "markerbbbbbeta"

    assert (
        _save(
            save_module,
            monkeypatch,
            tmp_path,
            content=f"Handoff A only MARKER-{a_marker}",
            env_project="proj-a",
            cwd=ws_a,
        )
        == 0
    )
    assert (
        _save(
            save_module,
            monkeypatch,
            tmp_path,
            content=f"Handoff B only MARKER-{b_marker}",
            env_project="proj-b",
            cwd=ws_b,
        )
        == 0
    )

    # Derive the read scope through the production resolver (env=proj-b), proving
    # the id fed into the search floor is what the RESOLVER produces — not a
    # hardcoded literal (BP-166 Q4 Case 2).
    read_scope = _resolve_read_scope(monkeypatch, env_project="proj-b", cwd=str(ws_b))
    assert read_scope == "proj-b", "resolver did not produce B on the read path"

    b_results = _search(mem_env.cfg, read_scope)
    # Positive control keeps the zero-result assertion non-vacuous.
    assert any(b_marker in r.get("content", "") for r in b_results)
    assert all(
        a_marker not in r.get("content", "") for r in b_results
    ), "ISOLATION VIOLATION: a B-scoped read returned project A content"
    assert all(r.get("group_id") == "proj-b" for r in b_results if r.get("group_id"))


def test_mismatch_env_a_cwd_b_prefers_env(mem_env, save_module, monkeypatch, tmp_path):
    """Case 3: env=A while cwd resolves (git) to B → resolver picks A; nothing crosses."""
    cwd_b = tmp_path / "checkout_b"
    cwd_b.mkdir()
    _make_git_repo(cwd_b, "https://github.com/acme/project-b.git")
    marker = "mismatchmarkergamma"

    rc = _save(
        save_module,
        monkeypatch,
        tmp_path,
        content=f"Mismatch handoff MARKER-{marker}",
        env_project="proj-a",
        cwd=cwd_b,
    )
    assert rc == 0

    # Stored under env A, not the cwd git slug B.
    assert any(
        marker in p.payload.get("content", "")
        for p in _scroll_group(mem_env.client, "proj-a")
    )

    # A reader in cwd B with no env override resolves to the cwd git slug; derive
    # that id through the resolver (not a hardcoded literal) and prove the env-A
    # write is invisible to it.
    cwd_b_scope = _resolve_read_scope(monkeypatch, env_project=None, cwd=str(cwd_b))
    assert cwd_b_scope == "acme/project-b", "resolver did not produce B from cwd git"
    assert _scroll_group(mem_env.client, cwd_b_scope) == []
    assert _search(mem_env.cfg, cwd_b_scope) == []


def test_fail_loud_writes_nothing(mem_env, save_module, monkeypatch, tmp_path):
    """Case 5: no env + non-git cwd → friendly fail-loud, nothing written."""
    nongit = tmp_path / "orphan"
    nongit.mkdir()
    marker = "failloudmarkerdelta"

    rc = _save(
        save_module,
        monkeypatch,
        tmp_path,
        content=f"Should not persist MARKER-{marker}",
        env_project=None,
        cwd=nongit,
    )
    assert rc == 0  # handoff save degrades gracefully (file is the primary record)

    all_points, _ = mem_env.client.scroll(
        collection_name=COLLECTION_DISCUSSIONS, limit=1000, with_payload=True
    )
    assert all(
        marker not in p.payload.get("content", "") for p in all_points
    ), "fail-loud path still wrote a point under a guessed id"


def test_marker_file_scopes_workspace(mem_env, save_module, monkeypatch, tmp_path):
    """Marker tier: a .ai-memory-project marker scopes the save; env still overrides it."""
    ws = tmp_path / "marked_ws"
    ws.mkdir()
    (ws / ".ai-memory-project").write_text(
        "# workspace project\nproj-marker\n", encoding="utf-8"
    )

    # No env -> the marker scopes the write.
    assert (
        _save(
            save_module,
            monkeypatch,
            tmp_path,
            content="Handoff scoped by marker MARKER-markerscopealpha",
            env_project=None,
            cwd=ws,
        )
        == 0
    )
    assert any(
        "markerscopealpha" in p.payload.get("content", "")
        for p in _scroll_group(mem_env.client, "proj-marker")
    )
    assert _search(mem_env.cfg, "proj-other") == []

    # A live env override beats the marker.
    assert (
        _save(
            save_module,
            monkeypatch,
            tmp_path,
            content="Handoff via env override MARKER-envoverridebeta",
            env_project="proj-env",
            cwd=ws,
        )
        == 0
    )
    assert any(
        "envoverridebeta" in p.payload.get("content", "")
        for p in _scroll_group(mem_env.client, "proj-env")
    )
    assert _scroll_group(mem_env.client, "proj-marker") and all(
        "envoverridebeta" not in p.payload.get("content", "")
        for p in _scroll_group(mem_env.client, "proj-marker")
    ), "env override leaked into the marker-scoped project"
