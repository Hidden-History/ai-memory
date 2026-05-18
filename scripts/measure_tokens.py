#!/usr/bin/env python3
"""Measure Parzival session-cost token surfaces for v2.4.2 AC verification.

Engines: Anthropic SDK `count_tokens` (authoritative when ANTHROPIC_API_KEY set)
        + tiktoken cl100k_base (always available; ~3-5% drift vs Claude BPE).

Per DEC-089 + DEC-090: tokenizer choice is user preference. Default mode is
tiktoken-only (offline, free). Authoritative mode requires API key but is
opt-in via --mode=authoritative. When the key is absent under authoritative
mode, the script falls back to tiktoken with a stderr notice and an
`[Inferred -- 3-5% drift]` tag in the output. The API key is never required.

Surface file lists for [ST], [DA], [CL] are derived by chain-walking each
workflow.md frontmatter `firstStep:` and following `nextStepFile:` links.
The activation surface is hand-coded from parzival.md activation steps 1-7.

Usage:
  python measure_tokens.py --surface activation --mode tiktoken
  python measure_tokens.py --surface all --mode authoritative \\
      --output ../oversight/audits/v2.4.2-baseline-tokens
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MODEL = "claude-opus-4-7"
DRIFT_TAG = "[Inferred -- 3-5% drift]"
ESTIMATE_TAG = "[Estimated -- char-div-4]"
SURFACES = ("activation", "st_additional", "da_additional", "cl_additional")
PHASES = (
    "execution",
    "discovery",
    "architecture",
    "planning",
    "integration",
    "release",
    "maintenance",
)
PROFILES = ("full", "module-only")
SANCTUM_TIER_A = ("CREED.md", "PERSONA.md")
SANCTUM_TIER_B = ("LORE.md", "BOND.md", "MEMORY.md")
ST_AUXILIARY_MODULE = (
    "{workflows_path}/STEP-PREAMBLE.md",
    "{workflows_path}/STEP-SCAFFOLD.md",
)
ST_AUXILIARY_OPERATOR = (
    "{oversight_path}/SESSION_WORK_INDEX.md",
    "{oversight_path}/tracking/task-tracker.md",
    "{oversight_path}/tracking/blockers-log.md",
    "{oversight_path}/tracking/risk-register.md",
)
SANCTUM_ASSETS_SUBPATH = "_ai-memory/pov/skills/aim-agent-sanctum-init/assets"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
NEXT_STEP_RE = re.compile(r"^nextStepFile:\s*['\"]?([^'\"\n]+)['\"]?\s*$", re.MULTILINE)
FIRST_STEP_RE = re.compile(r"^firstStep:\s*['\"]?([^'\"\n]+)['\"]?\s*$", re.MULTILINE)
CURRENT_PHASE_RE = re.compile(
    r"^current_phase:\s*['\"]?([A-Za-z_]+)['\"]?\s*$", re.MULTILINE
)


@dataclass
class SurfaceResult:
    """Per-surface measurement record."""

    name: str
    files: list[str] = field(default_factory=list)
    char_count: int = 0
    byte_count: int = 0
    tokens_anthropic_sdk: int | None = None
    tokens_tiktoken_cl100k_base: int | None = None
    warnings: list[str] = field(default_factory=list)
    text: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files)


def parse_frontmatter(text: str) -> str | None:
    """Return the YAML frontmatter block of a step/workflow file, or None."""
    match = FRONTMATTER_RE.match(text)
    return match.group(1) if match else None


def extract_first_step(workflow_text: str) -> str | None:
    """Return the `firstStep:` value from workflow.md frontmatter."""
    fm = parse_frontmatter(workflow_text)
    if not fm:
        return None
    match = FIRST_STEP_RE.search(fm)
    return match.group(1).strip() if match else None


def extract_next_step(step_text: str) -> str | None:
    """Return the `nextStepFile:` value from a step file's frontmatter."""
    fm = parse_frontmatter(step_text)
    if not fm:
        return None
    match = NEXT_STEP_RE.search(fm)
    return match.group(1).strip() if match else None


def substitute_placeholders(value: str, substitutions: dict[str, str]) -> str:
    """Replace `{key}` placeholders in `value` using `substitutions`."""
    result = value
    for key, replacement in substitutions.items():
        result = result.replace("{" + key + "}", replacement)
    return result


def resolve_step_path(
    current_path: Path, raw_next: str, substitutions: dict[str, str]
) -> Path:
    """Resolve a `nextStepFile:` value to an absolute path."""
    substituted = substitute_placeholders(raw_next, substitutions)
    candidate = Path(substituted)
    if candidate.is_absolute():
        return candidate.resolve()
    return (current_path.parent / candidate).resolve()


def walk_workflow_chain(
    workflow_path: Path,
    substitutions: dict[str, str],
    warnings: list[str],
) -> list[Path]:
    """Walk workflow.md and its step chain via frontmatter; return file list.

    Terminates on missing files, cycles, or absent `nextStepFile:`.
    """
    files: list[Path] = []
    if not workflow_path.exists():
        warnings.append(f"workflow.md missing: {workflow_path}")
        return files

    files.append(workflow_path)
    workflow_text = workflow_path.read_text(encoding="utf-8", errors="replace")
    first_step = extract_first_step(workflow_text)
    if not first_step:
        warnings.append(f"no firstStep in {workflow_path}")
        return files

    current = resolve_step_path(workflow_path, first_step, substitutions)
    seen: set[Path] = set()
    while True:
        if current in seen:
            warnings.append(f"cycle detected at {current}")
            break
        if not current.exists():
            warnings.append(f"step missing (terminus): {current}")
            break
        seen.add(current)
        files.append(current)
        step_text = current.read_text(encoding="utf-8", errors="replace")
        raw_next = extract_next_step(step_text)
        if not raw_next:
            break
        current = resolve_step_path(current, raw_next, substitutions)

    return files


def read_phase_from_status(project_root: Path) -> str | None:
    """Read `current_phase:` from project-status.md if present."""
    status = project_root / "project-status.md"
    if not status.exists():
        return None
    text = status.read_text(encoding="utf-8", errors="replace")
    match = CURRENT_PHASE_RE.search(text)
    return match.group(1).strip().lower() if match else None


def most_recent_handoff(oversight_path: Path) -> Path | None:
    """Return the most-recent SESSION_HANDOFF_*.md from oversight/session-logs/.

    Per step-01-load-context.md section 2 + step-01b CASE B fallback path;
    reliably loaded on real [ST] runs. Absence is a legitimate first-session
    state, not a warning.
    """
    session_logs_dir = oversight_path / "session-logs"
    if not session_logs_dir.is_dir():
        return None
    handoffs = sorted(session_logs_dir.glob("SESSION_HANDOFF_*.md"), reverse=True)
    return handoffs[0] if handoffs else None


def sanctum_template_path(project_root: Path, sanctum_filename: str) -> Path:
    """Map a sanctum filename (e.g. CREED.md) to its Track-A template asset."""
    stem = sanctum_filename.removesuffix(".md")
    return project_root / SANCTUM_ASSETS_SUBPATH / f"{stem}-template.md"


def build_activation_files(
    project_root: Path,
    substitutions: dict[str, str],
    phase: str,
    profile: str,
    warnings: list[str],
) -> list[Path]:
    """Hand-coded activation file list per parzival.md activation steps 1-7.

    Step 1: parzival.md agent file (loaded by /pov:parzival).
    Step 2: config.yaml (session variables).
    Step 3: project-status.md (project root) for phase detection,
        then constraints/global/constraints.md + constraints/{phase}/constraints.md.
    Step 5 (Tier A full-load — the CREED.md + PERSONA.md read bullets):
        CREED.md + PERSONA.md (Tier B per the step-5 deferred-load note
        = LORE + BOND + MEMORY, deferred to st_additional).
    Step 6: WORKFLOW-MAP.md.

    profile=module-only (r2 Section 5 Track B carveout): drop project-status.md
    and substitute operator sanctum CREED/PERSONA with their Track-A templates.
    """
    workflows_path = Path(substitutions["workflows_path"])
    constraints_path = Path(substitutions["constraints_path"])
    sanctum_path = Path(substitutions["sanctum_path"])

    files: list[Path] = [
        project_root / "_ai-memory" / "pov" / "agents" / "parzival.md",
        project_root / "_ai-memory" / "pov" / "config.yaml",
    ]
    if profile == "full":
        files.append(project_root / "project-status.md")
    files.extend(
        [
            constraints_path / "global" / "constraints.md",
            constraints_path / phase / "constraints.md",
            workflows_path / "WORKFLOW-MAP.md",
        ]
    )
    parzival_sanctum = sanctum_path / "parzival"
    for fname in SANCTUM_TIER_A:
        if profile == "module-only":
            template = sanctum_template_path(project_root, fname)
            if not template.exists():
                warnings.append(f"sanctum template missing: {template}")
            files.append(template)
        else:
            files.append(parzival_sanctum / fname)

    for f in files:
        if not f.exists():
            warnings.append(f"activation file missing: {f}")
    return files


def build_st_additional_files(
    project_root: Path,
    substitutions: dict[str, str],
    profile: str,
    warnings: list[str],
) -> list[Path]:
    """Files loaded during [ST] session-start beyond activation.

    profile=module-only (r2 Section 5 Track B carveout): drop oversight/* +
    session-logs handoff; substitute operator sanctum Tier-B with templates.
    """
    workflows_path = Path(substitutions["workflows_path"])
    oversight_path = Path(substitutions["oversight_path"])
    sanctum_path = Path(substitutions["sanctum_path"])

    files: list[Path] = []
    files.extend(
        walk_workflow_chain(
            workflows_path / "session" / "start" / "workflow.md",
            substitutions,
            warnings,
        )
    )

    for template in ST_AUXILIARY_MODULE:
        files.append(Path(substitute_placeholders(template, substitutions)))

    if profile == "full":
        for template in ST_AUXILIARY_OPERATOR:
            files.append(Path(substitute_placeholders(template, substitutions)))
        handoff = most_recent_handoff(oversight_path)
        if handoff is not None:
            files.append(handoff)

    parzival_sanctum = sanctum_path / "parzival"
    for fname in SANCTUM_TIER_B:
        if profile == "module-only":
            template = sanctum_template_path(project_root, fname)
            if not template.exists():
                warnings.append(f"sanctum template missing: {template}")
            files.append(template)
        else:
            files.append(parzival_sanctum / fname)

    for f in files:
        if not f.exists():
            warnings.append(f"st_additional file missing: {f}")
    return files


def build_chain_additional_files(
    workflow_path: Path,
    substitutions: dict[str, str],
    warnings: list[str],
    surface_label: str,
) -> list[Path]:
    """Chain-walk a workflow's step files for [DA] or [CL]."""
    files = walk_workflow_chain(workflow_path, substitutions, warnings)
    for f in files:
        if not f.exists():
            warnings.append(f"{surface_label} file missing: {f}")
    return files


def collect_surface_files(
    surface: str,
    project_root: Path,
    substitutions: dict[str, str],
    phase: str,
    profile: str,
    warnings: list[str],
) -> list[Path]:
    """Dispatch to the correct file-list builder for a surface."""
    workflows_path = Path(substitutions["workflows_path"])
    if surface == "activation":
        return build_activation_files(
            project_root, substitutions, phase, profile, warnings
        )
    if surface == "st_additional":
        return build_st_additional_files(project_root, substitutions, profile, warnings)
    if surface == "da_additional":
        return build_chain_additional_files(
            workflows_path / "cycles" / "agent-dispatch" / "workflow.md",
            substitutions,
            warnings,
            "da_additional",
        )
    if surface == "cl_additional":
        return build_chain_additional_files(
            workflows_path / "session" / "close" / "workflow.md",
            substitutions,
            warnings,
            "cl_additional",
        )
    raise ValueError(f"unknown surface: {surface}")


def read_concatenated(files: list[Path], warnings: list[str]) -> tuple[str, int, int]:
    """Concatenate file contents (newline-joined); return (text, chars, bytes)."""
    parts: list[str] = []
    total_bytes = 0
    for f in files:
        if not f.exists():
            continue
        try:
            data = f.read_bytes()
        except OSError as exc:
            warnings.append(f"read error {f}: {exc}")
            continue
        total_bytes += len(data)
        parts.append(data.decode("utf-8", errors="replace"))
    text = "\n".join(parts)
    return text, len(text), total_bytes


def count_tiktoken(text: str, warnings: list[str]) -> int | None:
    """Count tokens with tiktoken cl100k_base; warn and return None on failure."""
    try:
        import tiktoken
    except ImportError:
        warnings.append("tiktoken not installed; using char-div-4 estimate")
        return None
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception as exc:
        warnings.append(f"tiktoken error: {exc}")
        return None


def count_anthropic_sdk(text: str, model: str, warnings: list[str]) -> int | None:
    """Call Anthropic SDK count_tokens for the surface text."""
    try:
        import anthropic
    except ImportError:
        warnings.append("anthropic SDK not installed")
        return None
    try:
        client = anthropic.Anthropic()
        response = client.messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return int(response.input_tokens)
    except Exception as exc:
        warnings.append(f"anthropic SDK error: {exc}")
        return None


def estimate_char_div_4(text: str) -> int:
    """Best-effort char-div-4 fallback when no tokenizer is available."""
    return max(1, len(text) // 4)


def measure_surface(
    surface: str,
    project_root: Path,
    substitutions: dict[str, str],
    phase: str,
    profile: str,
    run_sdk: bool,
    run_tiktoken: bool,
    model: str,
    timing_warnings: list[str],
) -> SurfaceResult:
    """Build file list, read contents, and run requested tokenizers."""
    result = SurfaceResult(name=surface)
    files = collect_surface_files(
        surface, project_root, substitutions, phase, profile, result.warnings
    )
    result.files = [str(f) for f in files]

    start = time.monotonic()
    text, char_count, byte_count = read_concatenated(files, result.warnings)
    result.text = text
    result.char_count = char_count
    result.byte_count = byte_count

    if run_tiktoken:
        tk = count_tiktoken(text, result.warnings)
        if tk is None:
            tk = estimate_char_div_4(text)
            result.warnings.append(f"{surface}: {ESTIMATE_TAG}")
        result.tokens_tiktoken_cl100k_base = tk

    if run_sdk:
        sdk = count_anthropic_sdk(text, model, result.warnings)
        if sdk is None and not run_tiktoken:
            fallback = count_tiktoken(text, result.warnings)
            if fallback is not None:
                result.tokens_tiktoken_cl100k_base = fallback
                result.warnings.append(f"{surface}: {DRIFT_TAG}")
        result.tokens_anthropic_sdk = sdk

    elapsed = time.monotonic() - start
    if elapsed > 30.0:
        timing_warnings.append(
            f"{surface}: tokenization took {elapsed:.1f}s (>30s threshold)"
        )
    return result


def build_substitutions(project_root: Path) -> dict[str, str]:
    """Construct the placeholder substitution table from project root + config."""
    subs = {
        "project-root": str(project_root),
        "workflows_path": str(project_root / "_ai-memory" / "pov" / "workflows"),
        "constraints_path": str(project_root / "_ai-memory" / "pov" / "constraints"),
        "oversight_path": str(project_root / "oversight"),
        "skills_path": str(project_root / "_ai-memory" / "pov" / "skills"),
        "knowledge_path": str(project_root / "_ai-memory" / "pov" / "knowledge"),
        "sanctum_path": str(project_root / "_ai-memory" / "sanctum"),
        "scripts_path": str(project_root / "_ai-memory" / "pov" / "scripts"),
    }
    config = project_root / "_ai-memory" / "pov" / "config.yaml"
    if config.exists():
        text = config.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key in subs and "{project-root}" in value:
                subs[key] = value.replace("{project-root}", str(project_root))
    return subs


def render_markdown(report: dict) -> str:
    """Render a human-readable markdown summary table from the report dict."""
    lines = [
        f"# Parzival Token Surface Measurement (profile: {report['profile']})",
        "",
        f"- Measured at: {report['measured_at']}",
        f"- Project root: {report['project_root']}",
        f"- Phase: {report['phase']}",
        f"- Profile: {report['profile']}",
        f"- Engines used: {', '.join(report['engines_used']) or '(none)'}",
        "",
        "| Surface | Files | Chars | SDK tokens | tiktoken tokens | Drift % |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in SURFACES:
        if name not in report["surfaces"]:
            continue
        s = report["surfaces"][name]
        sdk = s["tokens_anthropic_sdk"]
        tk = s["tokens_tiktoken_cl100k_base"]
        drift = f"{(tk - sdk) / sdk * 100:+.2f}" if sdk and tk else "n/a"
        lines.append(
            f"| {name} | {s['file_count']} | {s['char_count']} | "
            f"{sdk if sdk is not None else 'n/a'} | "
            f"{tk if tk is not None else 'n/a'} | {drift} |"
        )
    totals = report["totals"]
    lines.append("")
    lines.append(
        f"**Totals** -- SDK: {totals['tokens_anthropic_sdk']} | "
        f"tiktoken: {totals['tokens_tiktoken_cl100k_base']}"
    )
    if report["warnings"]:
        lines.append("")
        lines.append("## Warnings")
        for w in report["warnings"]:
            lines.append(f"- {w}")
    if report["notes"]:
        lines.append("")
        lines.append("## Notes")
        for n in report["notes"]:
            lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


def render_dry_run(report: dict) -> str:
    """Render a manifest-only view (no tokenizer counts) for --dry-run."""
    lines = [
        f"# Parzival Token Surface Manifest (dry-run, profile: {report['profile']})",
        "",
        f"- Project root: {report['project_root']}",
        f"- Phase: {report['phase']}",
        f"- Profile: {report['profile']}",
        "",
    ]
    for name in SURFACES:
        if name not in report["surfaces"]:
            continue
        s = report["surfaces"][name]
        lines.append(f"## {name} ({s['file_count']} files)")
        for fpath in s["files"]:
            lines.append(f"- {fpath}")
        lines.append("")
    if report["warnings"]:
        lines.append("## Warnings")
        for w in report["warnings"]:
            lines.append(f"- {w}")
        lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Measure Parzival session-cost token surfaces "
            "(activation / [ST] / [DA] / [CL])."
        )
    )
    parser.add_argument(
        "--surface",
        choices=(*SURFACES, "all"),
        default="all",
        help="which surface(s) to measure (default: all)",
    )
    parser.add_argument(
        "--mode",
        choices=("tiktoken", "authoritative", "both"),
        default="tiktoken",
        help=(
            "tokenizer engine(s) to run. tiktoken is offline + free (default); "
            "authoritative uses Anthropic SDK count_tokens; both runs SDK + "
            "tiktoken cross-reference. DEC-090: API key is a choice, never required."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="project root containing _ai-memory/ (default: parent of scripts dir)",
    )
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default=None,
        help="phase for activation constraint loading (default: from project-status.md)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model id for count_tokens (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="base output path; writes PATH.json + PATH.md (default: stdout only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list files per surface without invoking any tokenizer",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default="full",
        help=(
            "measurement profile (default: full). 'module-only' applies the "
            "r2 Section 5 Track B carveout: drops operator data (project-status, "
            "tracking/, session-logs) and substitutes operator sanctum content "
            "with Track-A templates."
        ),
    )
    return parser.parse_args(argv)


def resolve_project_root(arg: Path | None) -> Path:
    """Resolve --project-root, defaulting to the parent of this script's parent."""
    if arg is not None:
        return arg.resolve()
    return Path(__file__).resolve().parent.parent


def resolve_phase(arg: str | None, project_root: Path) -> str:
    """Resolve --phase, falling back to project-status.md, then execution."""
    if arg:
        return arg
    detected = read_phase_from_status(project_root)
    if detected and detected in PHASES:
        return detected
    return "execution"


def decide_engines(mode: str, notes: list[str]) -> tuple[bool, bool]:
    """Apply DEC-090: API key absence under authoritative falls back to tiktoken."""
    api_key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if mode == "tiktoken":
        return False, True
    if mode == "both":
        if api_key_present:
            return True, True
        sys.stderr.write(
            "notice: ANTHROPIC_API_KEY not set -- skipping SDK leg, "
            "running tiktoken only (DEC-090: tokenizer choice is user preference). "
            f"Output tagged {DRIFT_TAG}.\n"
        )
        notes.append(f"{DRIFT_TAG} -- SDK unavailable, tiktoken-only result")
        return False, True
    if api_key_present:
        return True, False
    sys.stderr.write(
        "notice: ANTHROPIC_API_KEY not set -- falling back to tiktoken "
        "(DEC-090: tokenizer choice is user preference). "
        f"Output tagged {DRIFT_TAG}.\n"
    )
    notes.append(f"{DRIFT_TAG} -- SDK unavailable, tiktoken fallback applied")
    return False, True


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns process exit code."""
    args = parse_args(argv)
    project_root = resolve_project_root(args.project_root)
    phase = resolve_phase(args.phase, project_root)
    substitutions = build_substitutions(project_root)

    notes = ["DEC-090 framing applied: tokenizer choice is user preference"]
    if args.dry_run:
        run_sdk, run_tiktoken = False, False
    else:
        run_sdk, run_tiktoken = decide_engines(args.mode, notes)

    surfaces_to_run = SURFACES if args.surface == "all" else (args.surface,)
    timing_warnings: list[str] = []
    surface_results: dict[str, SurfaceResult] = {}

    for surface in surfaces_to_run:
        if args.dry_run:
            result = SurfaceResult(name=surface)
            files = collect_surface_files(
                surface,
                project_root,
                substitutions,
                phase,
                args.profile,
                result.warnings,
            )
            result.files = [str(f) for f in files]
            surface_results[surface] = result
            continue
        surface_results[surface] = measure_surface(
            surface,
            project_root,
            substitutions,
            phase,
            args.profile,
            run_sdk,
            run_tiktoken,
            args.model,
            timing_warnings,
        )

    engines_used: list[str] = []
    if run_sdk:
        engines_used.append("anthropic_sdk")
    if run_tiktoken:
        engines_used.append("tiktoken_cl100k_base")

    aggregated_warnings: list[str] = list(timing_warnings)
    surfaces_json: dict[str, dict] = {}
    total_sdk = 0
    total_tk = 0
    any_sdk = False
    any_tk = False
    for name, r in surface_results.items():
        surfaces_json[name] = {
            "file_count": r.file_count,
            "char_count": r.char_count,
            "byte_count": r.byte_count,
            "tokens_anthropic_sdk": r.tokens_anthropic_sdk,
            "tokens_tiktoken_cl100k_base": r.tokens_tiktoken_cl100k_base,
            "files": r.files,
        }
        aggregated_warnings.extend(f"{name}: {w}" for w in r.warnings)
        if r.tokens_anthropic_sdk is not None:
            total_sdk += r.tokens_anthropic_sdk
            any_sdk = True
        if r.tokens_tiktoken_cl100k_base is not None:
            total_tk += r.tokens_tiktoken_cl100k_base
            any_tk = True

    report = {
        "measured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project_root": str(project_root),
        "phase": phase,
        "profile": args.profile,
        "engines_used": engines_used,
        "surfaces": surfaces_json,
        "totals": {
            "tokens_anthropic_sdk": total_sdk if any_sdk else None,
            "tokens_tiktoken_cl100k_base": total_tk if any_tk else None,
        },
        "warnings": aggregated_warnings,
        "notes": notes,
    }

    if args.dry_run:
        sys.stdout.write(render_dry_run(report))
    else:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.write("\n")
        sys.stdout.write(render_markdown(report))

    if args.output is not None and not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        json_path = args.output.with_suffix(".json")
        md_path = args.output.with_suffix(".md")
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        md_path.write_text(render_markdown(report), encoding="utf-8")
        sys.stderr.write(f"wrote {json_path}\nwrote {md_path}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
