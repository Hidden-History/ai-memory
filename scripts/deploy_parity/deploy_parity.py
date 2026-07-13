#!/usr/bin/env python3
"""deploy-parity — managed-file deploy-parity / drift gate (BP-186).

One tool, one declarative registry (managed-files.yaml), two check surfaces:

  * Source-side structural gate (default; no --project) — audits scripts/install.sh
    against the registry. Proves the *class* of bug unshippable: a refresh class
    whose deploy `cp` is dominated by the hook-config force-gate (BUG-527), or a
    set/dir class with no prune path (BUG-528), fails here. Runs with no deployed
    project — pure static + registry reconciliation.

  * Runtime deployed-vs-source gate (--install-dir I --project P) — compares a
    deployed consumer project against the current source templates: adapters
    byte-equal, guidance present when the IDE is configured, pov shims set-equal,
    skills byte-equal against the CANONICAL baseline (_ai-memory/skills +
    _ai-memory/pov/skills, not the .claude/skills mirror — TD-816), oversight
    templates byte-equal OR deployed-hash in the known-versions registry.

Modes:
  --check    exit non-zero on any ERROR-class finding (drift / missing / orphan /
             force-gated refresh / missing prune). Contract = chezmoi `verify`.
  --report   print every finding (ERROR + WARN) and exit 0 unless an ERROR exists
             *and* --check is also set; on its own, --report never blocks.

Never prints file contents or secret-bearing values (CLAUDE.md §7) — only class,
relative path, and a one-line verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

# ── Finding model ───────────────────────────────────────────────────────────

ERROR = "ERROR"
WARN = "WARN"

_KNOWN_OWNERSHIP = {
    "exact_filename",
    "glob",
    "directory",
    "canonical_tree",
    "migrated_tree",
    "marker",
    "json_member",
    "user",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    class_id: str
    verdict: str
    path: str
    message: str

    def render(self) -> str:
        return f"  [{self.severity:5}] {self.verdict:16} {self.class_id}: {self.path} — {self.message}"


# ── Registry loading ────────────────────────────────────────────────────────


def load_registry(registry_path: Path) -> list[dict]:
    with registry_path.open() as fh:
        data = yaml.safe_load(fh)
    classes = data.get("classes", []) if isinstance(data, dict) else []
    if not classes:
        raise SystemExit(f"deploy-parity: no classes in registry {registry_path}")
    return classes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _subst(template: str, **kw: str) -> str:
    out = template
    for key, val in kw.items():
        out = out.replace("{" + key + "}", val)
    return out


# ── Source-side structural checks (BP-186 §2.2) ─────────────────────────────


_FN_DEF = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\(\)\s*\{")


def _fn_body(install_sh: str, fn: str) -> list[str] | None:
    """Return a bash function's body lines, or None if undefined.

    Sliced from the function definition to the next top-level function
    definition (or EOF). This is robust against column-0 `}` lines that appear
    *inside* embedded `python3 -c "..."` heredocs (which a naive brace-match
    would mistake for the function close). A Python `def`/dict never matches the
    bash `name() {` signature, so the next-def delimiter is safe.
    """
    lines = install_sh.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(fn)}\(\)\s*\{{", line):
            start = i
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _FN_DEF.match(line):  # next top-level function begins → body ends
            break
        body.append(line)
    return body


def _cp_marker(cls: dict) -> str | None:
    """The source path fragment a class's deploy cp must reference."""
    locator = cls.get("source_glob") or cls.get("source_dir") or cls.get("source")
    if not locator:
        return None
    frag = locator.replace("{INSTALL_DIR}/", "")
    # Trim a trailing glob so we match the directory fragment in the cp line.
    return (
        frag.rsplit("/*", 1)[0].rsplit("/", 1)[0]
        if frag.endswith((".toml", ".md", ".mdc"))
        else frag.split("*")[0].rstrip("/")
    )


def source_side_findings(repo: Path, classes: list[dict]) -> list[Finding]:
    install_sh_path = repo / "scripts" / "install.sh"
    if not install_sh_path.is_file():
        return [
            Finding(ERROR, "-", "MISSING", str(install_sh_path), "install.sh not found")
        ]
    install_sh = install_sh_path.read_text()
    findings: list[Finding] = []

    # C5 — ownership declared, of a known kind.
    for cls in classes:
        own = cls.get("ownership") or {}
        kind = own.get("kind") if isinstance(own, dict) else None
        if kind not in _KNOWN_OWNERSHIP:
            findings.append(
                Finding(
                    ERROR,
                    cls.get("id", "?"),
                    "OWNERSHIP_UNDECLARED",
                    cls.get("id", "?"),
                    f"ownership.kind missing/unknown ({kind!r})",
                )
            )

    # Structural checks over deploy functions.
    for cls in classes:
        cid = cls["id"]
        fn = cls.get("deploy_fn")
        if not fn or cls.get("class") == "USER_OWNED_PRESERVE":
            continue

        # merge_agents_md.py (block-in-user-file) is a script, not a bash fn.
        if fn.endswith(".py"):
            if not (repo / "scripts" / fn).is_file():
                findings.append(
                    Finding(
                        ERROR, cid, "DEPLOY_FN_MISSING", fn, "deploy script not found"
                    )
                )
            continue

        body = _fn_body(install_sh, fn)
        if body is None:
            findings.append(
                Finding(
                    ERROR,
                    cid,
                    "DEPLOY_FN_MISSING",
                    fn,
                    "deploy function not defined in install.sh",
                )
            )
            continue
        joined = "\n".join(body)

        # C3 — refresh must NOT be dominated by the force-gate (BUG-527 lint).
        if cls.get("refresh") == "unconditional":
            marker = _cp_marker(cls)
            gate_idx = next(
                (i for i, ln in enumerate(body) if '"$force" != "true"' in ln), None
            )
            cp_idx = next(
                (
                    i
                    for i, ln in enumerate(body)
                    if marker and marker in ln and "cp " in ln
                ),
                None,
            )
            if cp_idx is None:
                findings.append(
                    Finding(
                        ERROR,
                        cid,
                        "REFRESH_CP_MISSING",
                        fn,
                        f"no deploy cp referencing {marker!r} found",
                    )
                )
            elif gate_idx is not None and cp_idx > gate_idx:
                findings.append(
                    Finding(
                        ERROR,
                        cid,
                        "REFRESH_FORCE_GATED",
                        fn,
                        "managed-template cp is dominated by the force-gate early-return (BUG-527)",
                    )
                )

        # C2 — a set/dir class that can gain/lose members needs a prune path (BUG-528 lint).
        if cls.get("prune") == "required":
            has_prune = ("prune_pov_shims" in joined) or (
                "rm -" in joined and re.search(r"!\s+-[edf]\s", joined) is not None
            )
            if not has_prune:
                findings.append(
                    Finding(
                        ERROR,
                        cid,
                        "PRUNE_MISSING",
                        fn,
                        "no prune path for retired members (BUG-528)",
                    )
                )

        # C4 — every rm -rf in the fn is bounded to a validated owned path.
        for ln in body:
            if "rm -rf" in ln and "$" in ln:
                # Accept if the same fn body carries a path-shape guard.
                if (
                    'log_error "Refusing to rm -rf' not in joined
                    and "Refusing to rm" not in joined
                    and "prune_pov_shims" not in joined
                ):
                    findings.append(
                        Finding(
                            WARN,
                            cid,
                            "UNGUARDED_RM",
                            fn,
                            "rm -rf on a variable path without a visible path-shape guard",
                        )
                    )
                break

    # C6 — registry deploy_fn ↔ reality: every referenced target dir appears in install.sh.
    for cls in classes:
        if cls.get("class") == "USER_OWNED_PRESERVE":
            continue
        for key in ("target_dir", "target"):
            tgt = cls.get(key)
            if not tgt:
                continue
            frag = tgt.replace("{PROJECT}/", "")
            if frag not in install_sh:
                findings.append(
                    Finding(
                        WARN,
                        cls["id"],
                        "TARGET_UNWRITTEN",
                        frag,
                        "registry target path not found in install.sh (registry drift?)",
                    )
                )
        for tgt in cls.get("target_dirs", []):
            frag = tgt.replace("{PROJECT}/", "")
            if frag not in install_sh:
                findings.append(
                    Finding(
                        WARN,
                        cls["id"],
                        "TARGET_UNWRITTEN",
                        frag,
                        "registry target path not found in install.sh (registry drift?)",
                    )
                )

    # C7 — no target path claimed by both a refresh and a preserve class.
    refresh_targets: dict[str, str] = {}
    preserve_targets: dict[str, str] = {}
    for cls in classes:
        bucket = (
            preserve_targets
            if cls.get("class") == "USER_OWNED_PRESERVE"
            else refresh_targets
        )
        for t in (
            [cls.get("target")]
            + ([cls.get("target_dir")] if cls.get("target_dir") else [])
            + cls.get("target_dirs", [])
        ):
            if t:
                bucket[t] = cls["id"]
    for t, cid in refresh_targets.items():
        if t in preserve_targets:
            findings.append(
                Finding(
                    ERROR,
                    cid,
                    "OWNERSHIP_CONFLICT",
                    t.replace("{PROJECT}/", ""),
                    f"path claimed by both refresh ({cid}) and preserve ({preserve_targets[t]})",
                )
            )

    return findings


# ── Runtime deployed-vs-source checks (BP-186 §2.1) ─────────────────────────


def _iter_files(root: Path):
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                yield p


def _byte_equal_tree(cid: str, src_root: Path, dst_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not src_root.is_dir():
        return findings
    src_files = {p.relative_to(src_root): p for p in _iter_files(src_root)}
    dst_files = {p.relative_to(dst_root): p for p in _iter_files(dst_root)}
    for rel, sp in src_files.items():
        dp = dst_root / rel
        if not dp.is_file():
            findings.append(
                Finding(ERROR, cid, "MISSING", str(rel), "source file not deployed")
            )
        elif _sha256(sp) != _sha256(dp):
            findings.append(
                Finding(
                    ERROR,
                    cid,
                    "STALE_DRIFT",
                    str(rel),
                    "deployed content ≠ source template",
                )
            )
    # Orphans: owned deployed file with no source (F3).
    for rel in dst_files:
        if rel not in src_files:
            findings.append(
                Finding(
                    ERROR,
                    cid,
                    "ORPHAN_RETIRED",
                    str(rel),
                    "deployed file has no source (retired, un-pruned)",
                )
            )
    return findings


def _adapter_set(cls: dict, install_dir: str, project: str) -> list[tuple[Path, Path]]:
    """(source_file, deployed_file) pairs for an adapter MANAGED_REFRESH_SET class."""
    pairs: list[tuple[Path, Path]] = []
    if cls.get("source_glob"):
        src_dir = Path(_subst(cls["source_glob"], INSTALL_DIR=install_dir)).parent
        pat = cls["source_glob"].rsplit("/", 1)[-1]
        tgt = Path(_subst(cls["target_dir"], PROJECT=project))
        for sp in sorted(src_dir.glob(pat)):
            pairs.append((sp, tgt / sp.name))
    elif cls.get("source_skill_dirs"):
        src_root = Path(_subst(cls["source_dir"], INSTALL_DIR=install_dir))
        targets = cls.get("target_dirs") or [cls["target_dir"]]
        for skill in cls["source_skill_dirs"]:
            sp = src_root / skill / "SKILL.md"
            for tdir in targets:
                pairs.append(
                    (sp, Path(_subst(tdir, PROJECT=project)) / skill / "SKILL.md")
                )
    return pairs


def _ide_configured(project: Path, cls: dict) -> bool:
    marker = cls.get("config_marker")
    if not marker:
        return False
    cfg = project / marker
    if not cfg.is_file():
        return False
    try:
        return "AI_MEMORY_INSTALL_DIR" in cfg.read_text()
    except OSError:
        return False


def runtime_findings(
    install_dir: str, project: str, classes: list[dict]
) -> list[Finding]:
    proj = Path(project)
    findings: list[Finding] = []

    for cls in classes:
        cid = cls["id"]
        kind = (cls.get("ownership") or {}).get("kind")
        cls_type = cls.get("class")

        # Adapter command/skill templates — byte-equal + orphan sweep.
        if cls_type == "MANAGED_REFRESH_SET" and (
            cls.get("source_glob") or cls.get("source_skill_dirs")
        ):
            pairs = _adapter_set(cls, install_dir, project)
            for sp, dp in pairs:
                if not sp.is_file():
                    continue
                if not dp.is_file():
                    findings.append(
                        Finding(
                            ERROR,
                            cid,
                            "MISSING",
                            str(dp.relative_to(proj)),
                            "adapter template not deployed",
                        )
                    )
                elif _sha256(sp) != _sha256(dp):
                    findings.append(
                        Finding(
                            ERROR,
                            cid,
                            "STALE_DRIFT",
                            str(dp.relative_to(proj)),
                            "deployed adapter ≠ source template",
                        )
                    )
            # Orphan owned files in the target dir(s).
            expected = {dp.resolve() for _, dp in pairs}
            for tdir in cls.get("target_dirs") or (
                [cls["target_dir"]] if cls.get("target_dir") else []
            ):
                troot = Path(_subst(tdir, PROJECT=project))
                pattern = (cls.get("ownership") or {}).get("pattern", "*")
                for dep in _iter_files(troot):
                    if pattern != "*" and not dep.match(pattern):
                        continue
                    if (
                        dep.name == "SKILL.md" or dep.suffix == ".toml"
                    ) and dep.resolve() not in expected:
                        findings.append(
                            Finding(
                                ERROR,
                                cid,
                                "ORPHAN_RETIRED",
                                str(dep.relative_to(proj)),
                                "deployed adapter has no source template",
                            )
                        )
            continue

        # pov shims / canonical skill trees — whole-tree byte-equal + set-equal.
        if kind in ("directory", "canonical_tree"):
            src_root = Path(_subst(cls["source_dir"], INSTALL_DIR=install_dir))
            dst_root = Path(_subst(cls["target_dir"], PROJECT=project))
            findings.extend(_byte_equal_tree(cid, src_root, dst_root))
            continue

        # Agent-guidance file — refresh + present-when-IDE-configured.
        if cls_type == "MANAGED_REFRESH_FILE":
            sp = Path(_subst(cls["source"], INSTALL_DIR=install_dir))
            dp = Path(_subst(cls["target"], PROJECT=project))
            expected = ("ide" not in cls) or _ide_configured(proj, cls)
            if not expected:
                continue
            if not dp.is_file():
                findings.append(
                    Finding(
                        ERROR,
                        cid,
                        "MISSING",
                        str(cls["target"]).replace("{PROJECT}/", ""),
                        "guidance file absent though IDE is configured",
                    )
                )
            elif sp.is_file() and _sha256(sp) != _sha256(dp):
                findings.append(
                    Finding(
                        ERROR,
                        cid,
                        "STALE_DRIFT",
                        str(cls["target"]).replace("{PROJECT}/", ""),
                        "deployed guidance ≠ source",
                    )
                )
            continue

        # Managed marker-block inside a user file (Codex AGENTS.md).
        if cls_type == "MANAGED_BLOCK_IN_USER_FILE":
            if not _ide_configured(proj, cls):
                continue
            dp = Path(_subst(cls["target"], PROJECT=project))
            own = cls["ownership"]
            if not dp.is_file() or own["begin"] not in dp.read_text():
                findings.append(
                    Finding(
                        ERROR,
                        cid,
                        "BLOCK_DRIFT",
                        str(cls["target"]).replace("{PROJECT}/", ""),
                        "managed AGENTS.md block absent though Codex is configured",
                    )
                )
            continue

        # Oversight templates — byte-equal OR deployed-hash in the known-versions registry.
        if cls_type == "MANAGED_MIGRATED_FILE":
            src_root = Path(_subst(cls["source_dir"], INSTALL_DIR=install_dir))
            dst_root = Path(_subst(cls["target_dir"], PROJECT=project))
            registry = _load_known_hashes(
                Path(_subst(cls["version_registry"], INSTALL_DIR=install_dir))
            )
            for sp in _iter_files(src_root):
                rel = sp.relative_to(src_root)
                dp = dst_root / rel
                if not dp.is_file():
                    continue  # not-yet-deployed is not drift for migrated user-data templates
                if _sha256(sp) == _sha256(dp):
                    continue
                if _sha256(dp) in registry.get(str(rel), set()):
                    findings.append(
                        Finding(
                            WARN,
                            cid,
                            "MIGRATABLE",
                            str(rel),
                            "deployed = known prior version; migrates to current on next install",
                        )
                    )
                # else: locally-modified user data — never flagged as ERROR (preserve).
            continue

    return findings


def _load_known_hashes(registry_path: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if not registry_path.is_file():
        return out
    for line in registry_path.read_text().splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        rel, _, h = line.partition("\t")
        out.setdefault(rel.strip(), set()).add(h.strip())
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deploy-parity",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check", action="store_true", help="exit non-zero on ERROR-class drift"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print all findings; never blocks on its own",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="repo root for the source-side structural gate",
    )
    parser.add_argument(
        "--install-dir", default=None, help="source INSTALL_DIR for the runtime gate"
    )
    parser.add_argument(
        "--project", default=None, help="deployed consumer project for the runtime gate"
    )
    parser.add_argument(
        "--registry", type=Path, default=None, help="path to managed-files.yaml"
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    if not args.check and not args.report:
        args.check = True  # default posture is the blocking gate

    repo = args.repo or _repo_root()
    registry_path = args.registry or (
        Path(__file__).resolve().parent / "managed-files.yaml"
    )
    classes = load_registry(registry_path)

    if args.project:
        if not args.install_dir:
            parser.error(
                "--project requires --install-dir (the source templates to compare against)"
            )
        findings = runtime_findings(args.install_dir, args.project, classes)
        mode = "runtime deployed-vs-source"
    else:
        findings = source_side_findings(repo, classes)
        mode = "source-side structural"

    errors = [f for f in findings if f.severity == ERROR]
    warns = [f for f in findings if f.severity == WARN]

    if args.json:
        import json

        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        if not findings:
            print(f"deploy-parity ({mode}): PARITY_OK — no drift")
        else:
            print(
                f"deploy-parity ({mode}): {len(errors)} error(s), {len(warns)} warning(s)"
            )
            for f in findings:
                print(f.render())

    # --check blocks on ERROR; --report alone never blocks.
    if args.check and errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
