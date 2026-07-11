#!/usr/bin/env python3
"""
BP-185 Gate-3: on-demand env-parity doctor (report-only).

Three-way parity between the typed schema (MemoryConfig), the committed
docker/.env.example, and the DEPLOYED runtime env (docker/.env +
docker/.env.secrets under $AI_MEMORY_INSTALL_DIR, default ~/.ai-memory).

Every key is classified into exactly one BP-185 taxonomy class (§2.3):
    MISSING_REQUIRED, MISSING_OPTIONAL_DEFAULTED, PRESENT_OK, ORPHAN_UNKNOWN,
    COMMENTED_DOCUMENTED, VALUE_DRIFT_FROM_DEFAULT, PLACEHOLDER_RESIDUE,
    SECRET_MISPLACED, DUPLICATE, INLINE_COMMENT_HAZARD

Report-only: this script NEVER edits or writes any env file. It exits 1 only
when an ERROR-class finding is present (otherwise 0).

SECURITY (CLAUDE.md §7 / BP-185 D6): this script NEVER prints, echoes, or emits
any env VALUE — secret or otherwise. Output is key names, classifications, and
booleans only. Value reads happen in-memory solely to decide drift/placeholder
classification and are never surfaced.

Usage:
    python3 scripts/verify/check_env_parity.py
    python3 scripts/verify/check_env_parity.py --json
    python3 scripts/verify/check_env_parity.py --install-dir /path/to/install
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Standalone-runnable: resolve src/ and scripts/ relative to this file
# (scripts/verify/check_env_parity.py -> repo root is three parents up).
_repo_root = Path(__file__).resolve().parent.parent.parent
for _extra in (_repo_root / "src", _repo_root / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

try:
    from memory.config import MemoryConfig
except ImportError as exc:  # pragma: no cover - env-specific
    print(f"FAIL: cannot import MemoryConfig — {exc}", file=sys.stderr)
    print(
        "      Run from repo root: python3 scripts/verify/check_env_parity.py",
        file=sys.stderr,
    )
    sys.exit(2)

from check_env_completeness import (  # noqa: E402  (path set above)
    _alias_env_names,
    _coerce_env_value,
    _parse_env_file_documented_keys,
    _parse_env_file_documented_values,
)
from pydantic import SecretStr  # noqa: E402  (path set above)

# Taxonomy class -> severity. ERROR-class findings drive a non-zero exit.
SEVERITY = {
    "MISSING_REQUIRED": "ERROR",
    "PLACEHOLDER_RESIDUE": "ERROR",
    "SECRET_MISPLACED": "ERROR",
    "DUPLICATE": "ERROR",
    "INLINE_COMMENT_HAZARD": "ERROR",
    "ORPHAN_UNKNOWN": "WARN",
    "MISSING_OPTIONAL_DEFAULTED": "INFO",
    "VALUE_DRIFT_FROM_DEFAULT": "INFO",
    "COMMENTED_DOCUMENTED": "OK",
    "PRESENT_OK": "OK",
}

# Runtime values that still equal a template placeholder (D7 / PLACEHOLDER_RESIDUE).
_PLACEHOLDERS = {
    "changeme",
    "change-me",
    "changethis",
    "replace-me",
    "your-token-here",
    "your-secret-here",
    "your-key-here",
    "your-token",
    "your-api-token",
}

# Secret-class key names — heuristic used ONLY for non-schema keys (infra
# secrets like GRAFANA_ADMIN_PASSWORD that MemoryConfig never types). Schema
# keys are classed by their SecretStr annotation instead, which is authoritative
# and avoids false hits on budgets/counters (TOKEN_BUDGET, MAX_TOKENS) or names
# that merely contain "SECRET"/"PATTERN" (SECRETS_BACKEND, CODE_PATTERNS).
# PUBLIC_KEY is deliberately excluded (it is not a secret).
_SECRET_NAME_RE = re.compile(
    r"(_TOKEN$|PASSWORD|_SECRET$|SECRET_KEY|API_KEY|PASSPHRASE)"
)


def _field_is_secret(field_info) -> bool:
    """True when the field's annotation is SecretStr (bare or Optional)."""
    annotation = field_info.annotation
    if annotation is SecretStr:
        return True
    return any(arg is SecretStr for arg in getattr(annotation, "__args__", ()))


def _is_secret(key: str, field_info) -> bool:
    if field_info is not None:
        # Schema key: its declared type is authoritative.
        return _field_is_secret(field_info)
    # Non-schema key (infra secret not in MemoryConfig): fall back to a name test.
    return bool(_SECRET_NAME_RE.search(key))


def _safe_key_token(key: str) -> str:
    """Reduce a parsed env key to a bare ``[A-Z0-9_]`` token before it is emitted.

    Only key NAMES are ever reported — values (secret or otherwise) never are.
    Rebuilding the emitted name from an allowlist of characters is a hard barrier:
    even a malformed deployed line can only ever contribute a key-name token to
    the output, never a value fragment. Real keys are already SCREAMING_SNAKE, so
    this is a no-op for valid input.
    """
    return re.sub(r"[^A-Z0-9_]", "", key.upper())


def _is_placeholder(value: str) -> bool:
    low = value.strip().lower()
    if low in _PLACEHOLDERS:
        return True
    if low.startswith(("your-", "your_")):
        return True
    return bool(re.fullmatch(r"<.*>", low))


def _drifts_from_default(field_info, raw: str) -> bool:
    """True when a numeric/bool runtime value differs from the Field default.

    String fields are skipped (site-specific strings like hosts/URLs drift
    legitimately and would only add noise). Values are read in-memory only —
    never emitted.
    """
    annotation = field_info.annotation
    if annotation not in (bool, int, float):
        return False
    value = _coerce_env_value(raw, annotation)
    if value is None:
        return False
    return value != field_info.default


def _parse_deployed_file(path: Path) -> tuple:
    """Parse a deployed env file into (active{KEY:value}, dups, hazards, present).

    Detects duplicated keys (last-wins differs by parser) and inline-comment
    hazards (unquoted value followed by whitespace + '#', which parsers treat
    inconsistently — BP-185 D12).
    """
    active: dict[str, str] = {}
    dups: set[str] = set()
    hazards: set[str] = set()
    if not path.exists():
        return active, dups, hazards, False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if not key:
            continue
        value = value.strip()
        if value and value[0] not in "\"'" and re.search(r"\s#", value):
            hazards.add(key)
        if key in active:
            dups.add(key)
        active[key] = value
    return active, dups, hazards, True


def build_report(env_example: Path, install_dir: Path) -> dict:
    """Classify every key across schema / example / deployed env (report-only)."""
    # --- schema side ---
    env_to_field: dict[str, object] = {}
    for field_name, field_info in MemoryConfig.model_fields.items():
        for env_name in _alias_env_names(field_name, field_info):
            env_to_field.setdefault(env_name, field_info)
    schema_env_names = set(env_to_field)

    # --- example side ---
    example_keys: set[str] = set()
    example_commented: set[str] = set()
    if env_example.exists():
        example_keys = _parse_env_file_documented_keys(env_example)
        example_commented = set(_parse_env_file_documented_values(env_example))

    # --- deployed side ---
    env_active, env_dups, env_hazards, env_present = _parse_deployed_file(
        install_dir / "docker" / ".env"
    )
    sec_active, sec_dups, sec_hazards, sec_present = _parse_deployed_file(
        install_dir / "docker" / ".env.secrets"
    )
    deployed_present = env_present or sec_present
    deployed_keys = set(env_active) | set(sec_active)
    dups = env_dups | sec_dups
    hazards = env_hazards | sec_hazards
    merged = {**env_active, **sec_active}  # secrets-first precedence (BP-153)

    known_keys = schema_env_names | example_keys
    universe = schema_env_names | example_keys | deployed_keys

    findings = []
    for key in sorted(universe):
        field_info = env_to_field.get(key)
        in_schema = field_info is not None
        secret = _is_secret(key, field_info)

        if key in dups:
            cls = "DUPLICATE"
        elif key in hazards:
            cls = "INLINE_COMMENT_HAZARD"
        elif (
            secret
            and key in env_active
            and env_active[key] != ""
            and key not in sec_active
        ):
            # Secret-class key with a real value sitting in the non-secret .env
            # file (and not shadowed by a .env.secrets entry). Emptiness is read
            # only to decide this — the value itself is never emitted.
            cls = "SECRET_MISPLACED"
        elif key in deployed_keys:
            if key not in known_keys:
                cls = "ORPHAN_UNKNOWN"
            elif _is_placeholder(merged.get(key, "")):
                cls = "PLACEHOLDER_RESIDUE"
            elif (
                in_schema
                and not secret
                and _drifts_from_default(field_info, merged.get(key, ""))
            ):
                cls = "VALUE_DRIFT_FROM_DEFAULT"
            else:
                cls = "PRESENT_OK"
        else:  # absent from deployed env
            if in_schema:
                if field_info.is_required():
                    cls = "MISSING_REQUIRED"
                elif key in example_commented:
                    cls = "COMMENTED_DOCUMENTED"
                else:
                    cls = "MISSING_OPTIONAL_DEFAULTED"
            elif key in example_commented:
                cls = "COMMENTED_DOCUMENTED"
            else:
                cls = "ORPHAN_UNKNOWN"

        findings.append(
            {
                "key": _safe_key_token(key),
                "classification": cls,
                "severity": SEVERITY[cls],
            }
        )

    class_counts: dict[str, int] = {}
    sev_counts: dict[str, int] = {}
    for finding in findings:
        class_counts[finding["classification"]] = (
            class_counts.get(finding["classification"], 0) + 1
        )
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1

    return {
        "install_dir": str(install_dir),
        "deployed_env_found": deployed_present,
        "error_count": sev_counts.get("ERROR", 0),
        "summary": {"by_class": class_counts, "by_severity": sev_counts},
        "findings": findings,
    }


def _print_human(report: dict) -> None:
    print("BP-185 env-parity doctor (report-only)")
    print(f"  install dir: {report['install_dir']}")
    if not report["deployed_env_found"]:
        print(
            "  deployed env not found — classifying schema vs example only "
            "(runtime keys unavailable)"
        )
    order = ["ERROR", "WARN", "INFO", "OK"]
    by_sev: dict[str, list] = {sev: [] for sev in order}
    for finding in report["findings"]:
        by_sev[finding["severity"]].append(finding)
    for sev in order:
        items = by_sev[sev]
        if not items:
            continue
        print(f"\n{sev} ({len(items)}):")
        for finding in items:
            print(f"  [{finding['classification']}] {finding['key']}")
    print(
        f"\nERROR-class findings: {report['error_count']} "
        f"(exit {1 if report['error_count'] else 0})"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="BP-185 env-parity doctor (report-only; never prints values)."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--install-dir",
        default=None,
        help="Deployed install dir (default: $AI_MEMORY_INSTALL_DIR or ~/.ai-memory).",
    )
    parser.add_argument(
        "--env-example",
        default=None,
        help="Path to docker/.env.example (default: repo docker/.env.example).",
    )
    args = parser.parse_args(argv)

    if args.install_dir:
        install_dir = Path(args.install_dir).expanduser()
    else:
        install_dir = Path(
            os.environ.get("AI_MEMORY_INSTALL_DIR", str(Path.home() / ".ai-memory"))
        ).expanduser()

    env_example = (
        Path(args.env_example).expanduser()
        if args.env_example
        else _repo_root / "docker" / ".env.example"
    )

    report = build_report(env_example, install_dir)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)

    return 1 if report["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
