#!/usr/bin/env python3
# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse() constructor, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), create_score_config(), flush()
"""Idempotent Score Config setup in Langfuse.

Creates 6 Score Configs that enforce validation schemas on evaluation scores.
Safe to run multiple times — existing configs are left unchanged.

Score Configs created:
  NUMERIC:     retrieval_relevance (0-1), bootstrap_quality (0-1), session_coherence (0-1)
  BOOLEAN:     injection_value, capture_completeness
  CATEGORICAL: classification_accuracy (correct | partially_correct | incorrect)

Usage:
  python scripts/create_score_configs.py

Requires env vars: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL

PLAN-012 Phase 2 — Section 5.6
"""

import sys


def main() -> int:
    try:
        from langfuse import (
            get_client,  # V3 singleton — NEVER use Langfuse() constructor
        )

        langfuse = get_client()

        print("Creating Score Configs in Langfuse...")

        # --- NUMERIC scores (0.0 - 1.0) ---
        numeric_names = [
            "retrieval_relevance",
            "bootstrap_quality",
            "session_coherence",
        ]
        for name in numeric_names:
            try:
                langfuse.create_score_config(
                    name=name,
                    data_type="NUMERIC",
                    min_value=0.0,
                    max_value=1.0,
                )
                print(f"  [OK] NUMERIC: {name} (0.0 - 1.0)")
            except Exception as exc:
                # Idempotent: log but don't fail if config already exists
                print(f"  [SKIP] {name}: {exc}")

        # --- BOOLEAN scores ---
        boolean_names = ["injection_value", "capture_completeness"]
        for name in boolean_names:
            try:
                langfuse.create_score_config(
                    name=name,
                    data_type="BOOLEAN",
                )
                print(f"  [OK] BOOLEAN: {name}")
            except Exception as exc:
                print(f"  [SKIP] {name}: {exc}")

        # --- CATEGORICAL score (PM #190 addition) ---
        try:
            langfuse.create_score_config(
                name="classification_accuracy",
                data_type="CATEGORICAL",
                categories=["correct", "partially_correct", "incorrect"],
            )
            print(
                "  [OK] CATEGORICAL: classification_accuracy (correct|partially_correct|incorrect)"
            )
        except Exception as exc:
            print(f"  [SKIP] classification_accuracy: {exc}")

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
