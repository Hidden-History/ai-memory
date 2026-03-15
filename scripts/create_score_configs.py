#!/usr/bin/env python3
# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse() constructor, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), api.score_configs.create(), api.score_configs.get(), flush()
"""Idempotent Score Config setup in Langfuse.

Creates 6 Score Configs that enforce validation schemas on evaluation scores.
Safe to run multiple times — existing configs are skipped (pre-checked via list API).

Score Configs created:
  NUMERIC:     retrieval_relevance (0-1), bootstrap_quality (0-1), session_coherence (0-1)
  BOOLEAN:     injection_value, capture_completeness
  CATEGORICAL: classification_accuracy (correct | partially_correct | incorrect)

Usage:
  python scripts/create_score_configs.py
  python scripts/create_score_configs.py --cleanup-duplicates

Requires env vars: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL

PLAN-012 Phase 2 — Section 5.6
"""

import argparse
import sys


def _fetch_existing_configs(langfuse) -> dict[str, list]:
    """Fetch all existing score configs from Langfuse, keyed by name.

    Returns a dict of {name: [config, ...]} to detect duplicates.
    Uses cursor-based pagination to retrieve all pages.
    """
    existing: dict[str, list] = {}
    page = 1
    while True:
        try:
            response = langfuse.api.score_configs.get(page=page, limit=100)
        except Exception as exc:
            print(f"  [WARN] Could not list existing score configs: {exc}")
            break

        items = getattr(response, "data", None) or []
        if not items:
            break

        for cfg in items:
            name = getattr(cfg, "name", None)
            if name:
                existing.setdefault(name, []).append(cfg)

        # Check if there are more pages
        meta = getattr(response, "meta", None)
        total_pages = getattr(meta, "total_pages", 1) if meta else 1
        if page >= total_pages:
            break
        page += 1

    return existing


def _cleanup_duplicates(langfuse, existing: dict[str, list]) -> None:
    """Archive duplicate score configs, keeping the oldest one (first created).

    Langfuse API does not support DELETE on score configs (405).
    Uses update(isArchived=True) instead — archived configs are hidden in UI.
    """
    from langfuse.api.resources.score_configs.types import UpdateScoreConfigRequest

    for name, configs in existing.items():
        if len(configs) <= 1:
            continue
        # Sort by created_at ascending, keep first, archive the rest
        try:
            sorted_configs = sorted(
                configs, key=lambda c: getattr(c, "created_at", "9999-99-99")
            )
        except Exception:
            sorted_configs = configs

        to_archive = sorted_configs[1:]
        for cfg in to_archive:
            cfg_id = getattr(cfg, "id", None)
            if not cfg_id:
                continue
            try:
                langfuse.api.score_configs.update(
                    cfg_id,
                    request=UpdateScoreConfigRequest(isArchived=True),
                )
                print(f"  [ARCHIVED] Duplicate config '{name}' id={cfg_id}")
            except Exception as exc:
                print(
                    f"  [WARN] Could not archive duplicate '{name}' id={cfg_id}: {exc}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Langfuse score configs idempotently"
    )
    parser.add_argument(
        "--cleanup-duplicates",
        action="store_true",
        help="Delete duplicate score configs (keep oldest), then recreate missing ones",
    )
    args = parser.parse_args()

    try:
        from langfuse import (
            get_client,  # V3 singleton — NEVER use Langfuse() constructor
        )
        from langfuse.api.resources.commons.types import (
            ConfigCategory,
            ScoreConfigDataType,
        )
        from langfuse.api.resources.score_configs.types import CreateScoreConfigRequest

        langfuse = get_client()

        print("Fetching existing Score Configs from Langfuse...")
        existing = _fetch_existing_configs(langfuse)
        if existing:
            print(
                f"  Found {sum(len(v) for v in existing.values())} existing config(s): {list(existing.keys())}"
            )
        else:
            print("  No existing configs found.")

        if args.cleanup_duplicates:
            print("\nCleaning up duplicate Score Configs...")
            _cleanup_duplicates(langfuse, existing)
            # Re-fetch after cleanup
            existing = _fetch_existing_configs(langfuse)

        print("\nCreating Score Configs in Langfuse...")

        # --- NUMERIC scores (0.0 - 1.0) ---
        numeric_names = [
            "retrieval_relevance",
            "bootstrap_quality",
            "session_coherence",
        ]
        for name in numeric_names:
            if name in existing:
                print(f"  [SKIP] NUMERIC: {name} (already exists)")
                continue
            try:
                langfuse.api.score_configs.create(
                    request=CreateScoreConfigRequest(
                        name=name,
                        dataType=ScoreConfigDataType.NUMERIC,
                        minValue=0.0,
                        maxValue=1.0,
                        description=f"LLM-as-judge score for {name.replace('_', ' ')} (PLAN-012)",
                    )
                )
                print(f"  [OK] NUMERIC: {name} (0.0 - 1.0)")
            except Exception as exc:
                print(f"  [ERROR] {name}: {exc}")

        # --- BOOLEAN scores ---
        boolean_names = ["injection_value", "capture_completeness"]
        for name in boolean_names:
            if name in existing:
                print(f"  [SKIP] BOOLEAN: {name} (already exists)")
                continue
            try:
                langfuse.api.score_configs.create(
                    request=CreateScoreConfigRequest(
                        name=name,
                        dataType=ScoreConfigDataType.BOOLEAN,
                        description=f"LLM-as-judge pass/fail for {name.replace('_', ' ')} (PLAN-012)",
                    )
                )
                print(f"  [OK] BOOLEAN: {name}")
            except Exception as exc:
                print(f"  [ERROR] {name}: {exc}")

        # --- CATEGORICAL score ---
        cat_name = "classification_accuracy"
        if cat_name in existing:
            print(f"  [SKIP] CATEGORICAL: {cat_name} (already exists)")
        else:
            try:
                langfuse.api.score_configs.create(
                    request=CreateScoreConfigRequest(
                        name=cat_name,
                        dataType=ScoreConfigDataType.CATEGORICAL,
                        categories=[
                            ConfigCategory(label="correct", value=1.0),
                            ConfigCategory(label="partially_correct", value=0.5),
                            ConfigCategory(label="incorrect", value=0.0),
                        ],
                        description="LLM-as-judge classification accuracy (PLAN-012)",
                    )
                )
                print(
                    "  [OK] CATEGORICAL: classification_accuracy (correct|partially_correct|incorrect)"
                )
            except Exception as exc:
                print(f"  [ERROR] {cat_name}: {exc}")

        # Flush all buffered data before exit (V3 requirement for short-lived scripts)
        langfuse.flush()
        print("\nDone. All Score Configs flushed to Langfuse.")
        return 0

    except ImportError as exc:
        print(f"ERROR: langfuse package not installed — {exc}", file=sys.stderr)
        print("Run: pip install 'langfuse>=3.0,<4.0'", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
