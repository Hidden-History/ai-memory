#!/usr/bin/env python3
"""
Pydantic-aware drift gate: asserts every MemoryConfig field is documented
in docker/.env.example (as an active line or a commented-out line) AND that
any commented default shown in the example matches the schema Field default
and stays within its declared bounds.

Exit 0 — no drift detected (in-bounds value drift is reported as a warning,
         not a failure).
Exit 1 — one or more MemoryConfig fields have no corresponding documentation
         in docker/.env.example, OR a commented default in the example falls
         outside the field's Ge/Le/Gt/Lt bounds.

Usage:
    python3 scripts/check_env_completeness.py
    PYTHONPATH=src python3 scripts/check_env_completeness.py  # from repo root

BP-152 §5.2 — Pydantic-aware completeness check.
BP-185 D6/D1 — commented-default bounds/drift check.
"""

import sys
from pathlib import Path

from annotated_types import Ge, Gt, Le, Lt

# Self-contained import: resolve src/ relative to this script so the script
# works both as `python3 scripts/check_env_completeness.py` and when
# PYTHONPATH=src is set externally (CI does both as belt-and-suspenders).
_repo_root = Path(__file__).resolve().parent.parent
_src_dir = _repo_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

try:
    from memory.config import MemoryConfig
except ImportError as exc:
    print(f"FAIL: cannot import MemoryConfig — {exc}", file=sys.stderr)
    print(
        "      Run from repo root: PYTHONPATH=src python3 scripts/check_env_completeness.py",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    from pydantic.aliases import AliasChoices, AliasPath
    from pydantic.fields import FieldInfo
except ImportError as exc:
    print(f"FAIL: pydantic/pydantic_settings import error — {exc}", file=sys.stderr)
    sys.exit(2)


# Fields that are internal/computed and intentionally absent from .env.example.
# These are excluded from the drift check because:
#   - Path fields (AUDIT_DIR, QUEUE_PATH, SESSION_LOG_PATH) are derived from INSTALL_DIR.
#   - Connection fields (EMBEDDING_HOST, MONITORING_HOST, MONITORING_PORT) have
#     no meaningful user-facing tuning surface.
#   - EMBEDDING_DIMENSION is fixed at model build time.
#   - LOG_FORMAT is an internal formatting choice without user docs.
#   - COLLECTION_SIZE_WARNING/CRITICAL are rarely tuned ops-level thresholds.
#   - GITHUB_SYNC_USABLE is a derived flag set by the validate_github_config
#     model-validator (PLAN-028 P1 RC-B); never user-set, so not documented.
EXCLUDED_FIELDS = {
    "AUDIT_DIR",
    "COLLECTION_SIZE_CRITICAL",
    "COLLECTION_SIZE_WARNING",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_HOST",
    "GITHUB_SYNC_USABLE",
    "LOG_FORMAT",
    "MONITORING_HOST",
    "MONITORING_PORT",
    "QUEUE_PATH",
    "SESSION_LOG_PATH",
}


def _alias_env_names(field_name: str, field_info: FieldInfo) -> set[str]:
    """Return all env var names for a field: uppercased field name + any AliasChoices."""
    names = {field_name.upper()}
    alias = field_info.validation_alias
    if alias is None:
        return names
    if isinstance(alias, str):
        names.add(alias.upper())
    elif isinstance(alias, AliasChoices):
        for choice in alias.choices:
            if isinstance(choice, str):
                names.add(choice.upper())
            elif isinstance(choice, AliasPath) and choice.path:
                # AliasPath first element is the env key name when used with pydantic-settings
                first = choice.path[0]
                if isinstance(first, str):
                    names.add(first.upper())
    return names


def _parse_env_file_documented_keys(path: Path) -> set[str]:
    """Return all keys present in an env file — both active and commented-out lines."""
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        # Active key
        if not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key:
                keys.add(key.upper())
        # Commented-out key (single #, then optional space, then KEY=...)
        elif stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip()
            if "=" in candidate and not candidate.startswith(" "):
                # Strict: no leading space after # (avoids matching prose comments)
                key = candidate.split("=", 1)[0].strip()
                if key and key == key.upper() and "_" in key:
                    keys.add(key.upper())
    return keys


def _parse_env_file_documented_values(path: Path) -> dict[str, str]:
    """Return {KEY: value} for commented-out ``# KEY=value`` documentation lines.

    Value-extracting companion to _parse_env_file_documented_keys (which returns
    keys only). Scans only commented lines because the active lines carry a
    site-specific value, whereas commented lines document the intended default
    (BP-185 D6). Matching mirrors the commented-key branch of
    _parse_env_file_documented_keys: single ``#``, no leading space after it,
    SCREAMING_SNAKE key containing an underscore.
    """
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        candidate = stripped.lstrip("#").strip()
        if "=" not in candidate or candidate.startswith(" "):
            continue
        key, value = candidate.split("=", 1)
        key = key.strip()
        if key and key == key.upper() and "_" in key:
            values[key.upper()] = value.strip()
    return values


def _field_bounds(field_info) -> tuple:
    """Extract (ge, le, gt, lt) numeric bounds from a FieldInfo's metadata."""
    ge = le = gt = lt = None
    for meta in field_info.metadata:
        if isinstance(meta, Ge):
            ge = meta.ge
        elif isinstance(meta, Le):
            le = meta.le
        elif isinstance(meta, Gt):
            gt = meta.gt
        elif isinstance(meta, Lt):
            lt = meta.lt
    return ge, le, gt, lt


def _coerce_env_value(raw: str, annotation):
    """Coerce a documented string value to the field's type (bool/int/float/str).

    Returns the coerced value, or None if the string cannot be parsed as the
    target type (caller treats an unparseable value as "not comparable").
    ``bool`` is checked before ``int`` because bool is an int subclass.
    """
    if annotation is bool:
        low = raw.strip().lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off"}:
            return False
        return None
    if annotation is int:
        try:
            return int(raw)
        except ValueError:
            return None
    if annotation is float:
        try:
            return float(raw)
        except ValueError:
            return None
    return raw.strip()


def check_commented_defaults(commented_values: dict[str, str]) -> tuple[list, list]:
    """Compare each documented commented default to the schema (BP-185 D6/D1).

    Returns (violations, drifts):
      - violations: commented value outside the field's Ge/Le/Gt/Lt bounds
        (ERROR — the example advertises an invalid default). Fails the gate.
      - drifts: commented value differs from the Field default but stays in
        bounds (WARN — usually a stale example). Does NOT fail the gate.
    """
    # Map every env name (field name + aliases) to its FieldInfo once.
    env_to_field: dict[str, object] = {}
    for field_name, field_info in MemoryConfig.model_fields.items():
        for env_name in _alias_env_names(field_name, field_info):
            env_to_field[env_name] = field_info

    violations: list[str] = []
    drifts: list[str] = []
    for key, raw in commented_values.items():
        field_info = env_to_field.get(key)
        if field_info is None:
            continue  # non-schema documented key — not our concern here
        annotation = field_info.annotation
        if annotation not in (bool, int, float):
            continue  # only numeric/bool defaults are bounds/drift-checkable
        value = _coerce_env_value(raw, annotation)
        if value is None:
            continue

        ge, le, gt, lt = _field_bounds(field_info)
        if (
            (ge is not None and value < ge)
            or (le is not None and value > le)
            or (gt is not None and value <= gt)
            or (lt is not None and value >= lt)
        ):
            bound_desc = ", ".join(
                part
                for part in (
                    f"ge={ge}" if ge is not None else "",
                    f"le={le}" if le is not None else "",
                    f"gt={gt}" if gt is not None else "",
                    f"lt={lt}" if lt is not None else "",
                )
                if part
            )
            violations.append(f"  {key}={raw}  (out of bounds: {bound_desc})")
            continue

        if value != field_info.default:
            drifts.append(f"  {key}={raw}  (schema default: {field_info.default})")

    return violations, drifts


def run_check(env_example: Path) -> int:
    """Run the completeness (D1) + commented-default (D6) checks on env_example."""
    if not env_example.exists():
        print(f"FAIL: docker/.env.example not found at {env_example}", file=sys.stderr)
        return 1

    documented_keys = _parse_env_file_documented_keys(env_example)

    missing: list[str] = []
    for field_name, field_info in MemoryConfig.model_fields.items():
        env_names = _alias_env_names(field_name, field_info)
        canonical = field_name.upper()

        if canonical in EXCLUDED_FIELDS:
            continue

        if not env_names.intersection(documented_keys):
            missing.append(
                f"  {canonical}  (also checked aliases: {sorted(env_names - {canonical})})"
            )

    commented_values = _parse_env_file_documented_values(env_example)
    violations, drifts = check_commented_defaults(commented_values)

    if missing:
        print("FAIL: MemoryConfig fields not documented in docker/.env.example:")
        for item in sorted(missing):
            print(item)
        print(f"\nTotal undocumented: {len(missing)}")
        print("Add these keys (active or commented) to docker/.env.example to fix.")

    if violations:
        print("FAIL: commented defaults in docker/.env.example are out of bounds:")
        for item in sorted(violations):
            print(item)
        print("Correct these commented values to a valid in-bounds default.")

    if drifts:
        print("WARN: commented defaults differ from schema Field defaults:")
        for item in sorted(drifts):
            print(item)
        print("(non-blocking — update the example to match config.py when convenient)")

    if missing or violations:
        return 1

    print(
        f"OK: all {len(MemoryConfig.model_fields) - len(EXCLUDED_FIELDS)} checked "
        "MemoryConfig fields are documented in docker/.env.example; "
        "commented defaults are in bounds"
    )
    return 0


def main() -> int:
    return run_check(_repo_root / "docker" / ".env.example")


if __name__ == "__main__":
    sys.exit(main())
