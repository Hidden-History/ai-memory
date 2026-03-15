#!/usr/bin/env python3
"""model-dispatch: Query and list available OpenRouter models by category."""
import argparse
import json
import os
import sys

import requests

# Category detection patterns for model IDs
CATEGORY_PATTERNS = {
    "coding": ["coder", "codestral", "deepseek-coder", "starcoder"],
    "reasoning": ["o1", "o3", "opus", "reasoning", "think"],
    "fast": ["mini", "flash", "haiku", "instant", "8b", "7b"],
}

# Known model-to-category overrides
KNOWN_MODELS = {
    "anthropic/claude-sonnet-4-6": "coding",
    "anthropic/claude-opus-4-6": "reasoning",
    "anthropic/claude-haiku-4-5": "fast",
    "openai/gpt-4o": "general",
    "openai/gpt-4o-mini": "fast",
    "openai/o1": "reasoning",
    "openai/o1-preview": "reasoning",
    "openai/o3-mini": "reasoning",
    "openai/whisper-1": "audio",
    "openai/tts-1": "audio",
    "openai/dall-e-3": "image-gen",
    "openai/gpt-5-image": "image-gen",
    "openai/gpt-5-image-mini": "image-gen",
}


def get_api_key():
    """Read OpenRouter API key from env or token file."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        token_path = os.path.expanduser("~/.openrouter-token")
        if os.path.exists(token_path):
            with open(token_path) as f:
                key = f.read().strip()
    if not key:
        print("Error: No OpenRouter API key. Store in ~/.openrouter-token or OPENROUTER_API_KEY", file=sys.stderr)
        sys.exit(1)
    return key


def categorize_model(model):
    """Assign a category to a model based on modality, ID patterns, and known overrides."""
    model_id = model.get("id", "")

    # Check known overrides first
    if model_id in KNOWN_MODELS:
        return KNOWN_MODELS[model_id]

    # Use structured input_modalities/output_modalities arrays (most reliable)
    arch = model.get("architecture", {})
    input_mods = arch.get("input_modalities", [])
    output_mods = arch.get("output_modalities", [])

    if "video" in output_mods:
        return "video-gen"
    if "audio" in output_mods:
        return "audio-gen"
    if "image" in output_mods:
        return "image-gen"
    if "audio" in input_mods:
        return "audio"
    if "image" in input_mods:
        return "vision"

    # Fallback: check legacy modality string
    modality = arch.get("modality", "")
    if "->video" in modality:
        return "video-gen"
    if "->image" in modality:
        return "image-gen"
    if "->audio" in modality:
        return "audio-gen"
    if "image->" in modality or "image+" in modality:
        return "vision"
    if "audio" in modality:
        return "audio"

    # Check ID patterns
    model_lower = model_id.lower()
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern in model_lower:
                return category

    return "general"


def format_price(price_str):
    """Convert price string to $/1M tokens display."""
    if not price_str:
        return "N/A"
    try:
        price = float(price_str)
        per_million = price * 1_000_000
        if per_million < 0.01:
            return "free"
        return f"${per_million:.2f}"
    except (ValueError, TypeError):
        return "N/A"


def fetch_models(api_key):
    """Fetch model list from OpenRouter API."""
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        if status == 401:
            print("Error: Unauthorized - check your API key", file=sys.stderr)
        elif status == 402:
            print("Error: Payment required - check your credits", file=sys.stderr)
        elif status == 429:
            print("Error: Rate limited - try again later", file=sys.stderr)
        else:
            print(f"Error: HTTP {status} from OpenRouter", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="List available OpenRouter models by category")
    parser.add_argument(
        "--category",
        choices=["coding", "reasoning", "vision", "image-gen", "audio", "audio-gen", "video-gen", "fast", "general"],
        help="Filter by task category",
    )
    parser.add_argument("--query", help="Task description (shown in output header)")
    parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    parser.add_argument("--limit", type=int, default=15, help="Max models to show")
    args = parser.parse_args()

    api_key = get_api_key()
    models = fetch_models(api_key)

    # Categorize and filter
    categorized = []
    for m in models:
        cat = categorize_model(m)
        if args.category and cat != args.category:
            continue
        pricing = m.get("pricing", {})
        categorized.append({
            "id": m.get("id", ""),
            "name": m.get("name", ""),
            "category": cat,
            "context_length": m.get("context_length", 0),
            "price_input": format_price(pricing.get("prompt")),
            "price_output": format_price(pricing.get("completion")),
        })

    # Sort: known models first, then by context length descending
    categorized.sort(key=lambda x: (x["id"] not in KNOWN_MODELS, -x["context_length"]))
    categorized = categorized[: args.limit]

    if not categorized:
        cat_label = args.category or "any"
        print(f"No models found for category: {cat_label}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(categorized, indent=2))
        return

    # Table output
    cat_label = args.category or "all"
    if args.query:
        print(f"Task: {args.query}")
    print(f"Category: {cat_label} | Showing top {len(categorized)} models")
    print(f"{'Recommended →':>14} {categorized[0]['id']}")
    print()
    print(f"{'#':<4} {'Model ID':<45} {'Name':<25} {'Context':<10} {'In $/1M':<10} {'Out $/1M':<10}")
    print("-" * 104)
    for i, m in enumerate(categorized, 1):
        ctx = f"{m['context_length']:,}" if m["context_length"] else "N/A"
        name = m["name"][:24] if m["name"] else ""
        marker = " *" if i == 1 else ""
        print(f"{i:<4} {m['id']:<45} {name:<25} {ctx:<10} {m['price_input']:<10} {m['price_output']:<10}{marker}")


if __name__ == "__main__":
    main()
