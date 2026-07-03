"""wiki_inventory: heuristic classification + exclude discipline."""

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-wiki"
    / "scripts"
)


def _load(name: str):
    """Load an aim-wiki skill script by bare module name (registered in
    sys.modules) so sibling scripts that `import <name>` resolve correctly —
    without adding scripts/ to sys.path (no sys.path namespace collision)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build_inventory = _load("wiki_inventory").build_inventory


def _mk(root: Path, rel: str, text: str = "x\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_classification_buckets(tmp_path):
    _mk(tmp_path, "README.md")
    _mk(tmp_path, "docs/guide.md")
    _mk(tmp_path, "pyproject.toml")
    _mk(tmp_path, ".github/workflows/ci.yml")
    _mk(tmp_path, "src/main.py")
    _mk(tmp_path, "src/index.ts")
    _mk(tmp_path, "tests/test_app.py")
    _mk(tmp_path, "db/schema.sql")

    inv = build_inventory(tmp_path)
    assert "README.md" in inv["docs"]
    assert "docs/guide.md" in inv["docs"]
    assert "pyproject.toml" in inv["config"]
    assert ".github/workflows/ci.yml" in inv["config"]
    assert "src/main.py" in inv["entrypoints"]
    assert "src/index.ts" in inv["entrypoints"]
    assert "tests/test_app.py" in inv["tests"]
    assert "db/schema.sql" in inv["schema"]


def test_excludes_noise_dirs(tmp_path):
    _mk(tmp_path, "src/main.py")
    _mk(tmp_path, "node_modules/pkg/index.js")
    _mk(tmp_path, ".git/config")
    _mk(tmp_path, "dist/bundle.js")
    _mk(tmp_path, "wiki/quickstart.md")  # the wiki itself is excluded

    inv = build_inventory(tmp_path)
    flat = (
        inv["docs"] + inv["entrypoints"] + inv["config"] + inv["tests"] + inv["schema"]
    )
    joined = " ".join(flat)
    assert "node_modules" not in joined
    assert ".git/" not in joined
    assert "dist/" not in joined
    assert "wiki/" not in joined
    assert "src/main.py" in inv["entrypoints"]


def test_top_level_dirs_and_counts(tmp_path):
    _mk(tmp_path, "src/main.py")
    _mk(tmp_path, "docs/x.md")
    _mk(tmp_path, "node_modules/p/i.js")
    inv = build_inventory(tmp_path)
    assert "src/" in inv["top_level_dirs"]
    assert "docs/" in inv["top_level_dirs"]
    assert "node_modules/" not in inv["top_level_dirs"]
    assert inv["files_scanned"] >= 2
    assert inv["truncated"] is False
