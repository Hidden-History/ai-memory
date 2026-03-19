#!/usr/bin/env python3
"""model-dispatch: Image analysis via OpenRouter API"""
import argparse
import base64
import json
import sys
import os
from openai import OpenAI


def get_client():
    """Create OpenRouter client with authentication."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key and os.path.exists(os.path.expanduser("~/.openrouter-token")):
        with open(os.path.expanduser("~/.openrouter-token")) as f:
            key = f.read().strip()
    if not key:
        print("Error: No OpenRouter API key. Store in ~/.openrouter-token or OPENROUTER_API_KEY", file=sys.stderr)
        sys.exit(1)
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


def encode_image_to_base64(image_path):
    """Encode an image file to base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_image_source(input_str):
    """Detect if input is a URL or file path."""
    if input_str.startswith(("http://", "https://")):
        return "url", input_str
    if os.path.exists(input_str):
        return "file", input_str
    return "unknown", input_str


def main():
    parser = argparse.ArgumentParser(description="Analyze images via OpenRouter API")
    parser.add_argument("--model", required=True, help="OpenRouter vision model ID")
    parser.add_argument("--input", required=True, help="Image URL or file path")
    parser.add_argument("--output", default="-", help="Output file or '-' for stdout")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API call")
    parser.add_argument("--json", action="store_true", help="Output structured JSON result")
    parser.add_argument("--prompt", default="Describe this image in detail", help="Prompt for analysis")
    parser.add_argument("--detail", choices=["auto", "low", "high"], default="auto", help="Image detail level")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would call vision model: {args.model}")
        print(f"Image source: {args.input}")
        print(f"Prompt: {args.prompt}")
        if args.output != "-":
            print(f"Output to: {args.output}")
        print("Dry run complete - no API call made")
        return

    client = get_client()
    source_type, source_value = detect_image_source(args.input)

    # Build multimodal content
    content = [
        {"type": "text", "text": args.prompt},
    ]

    if source_type == "url":
        content.append({
            "type": "image_url",
            "image_url": {
                "url": source_value,
                "detail": args.detail,
            },
        })
    elif source_type == "file":
        try:
            base64_image = encode_image_to_base64(source_value)
            # Determine media type from extension
            ext = os.path.splitext(source_value)[1].lower()
            media_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}
            media_type = media_map.get(ext, "image/jpeg")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{base64_image}",
                    "detail": args.detail,
                },
            })
        except Exception as e:
            print(f"Error reading image file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: Could not detect image source. Provide a valid URL or file path.", file=sys.stderr)
        sys.exit(1)

    try:
        response = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": content}],
            extra_headers={"X-OpenRouter-Title": "model-dispatch"},
        )

        result = response.choices[0].message.content

        if response.usage:
            usage_data = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }
        else:
            usage_data = {}

        if args.json:
            output = {
                "model": args.model,
                "analysis": result,
                "usage": usage_data,
            }
            print(json.dumps(output, indent=2))
        else:
            if args.output == "-":
                print(result)
            else:
                with open(args.output, "w") as f:
                    f.write(result)
                print(f"Output written to {args.output}")

        print(f"Tokens: {usage_data.get('total_tokens', 0)} (input: {usage_data.get('input_tokens', 0)}, output: {usage_data.get('output_tokens', 0)})", file=sys.stderr)

    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg:
            print("Error: Unauthorized - check your API key", file=sys.stderr)
        elif "402" in error_msg:
            print("Error: Payment required - check your credits", file=sys.stderr)
        elif "404" in error_msg:
            print("Error: Model not found - check model ID", file=sys.stderr)
        elif "429" in error_msg:
            print("Error: Rate limited - try again later", file=sys.stderr)
        else:
            print(f"Error: {error_msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
