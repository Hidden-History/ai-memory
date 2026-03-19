#!/usr/bin/env python3
"""model-dispatch: Video generation via OpenRouter API (images/generations endpoint)

OpenRouter routes video generation models (Runway, Kling, Pika, Luma, etc.) through
the images generations endpoint. The response contains a video URL in the data array.
"""
import argparse
import json
import sys
import os
import urllib.request


def get_api_key():
    """Retrieve OpenRouter API key from environment or token file."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key and os.path.exists(os.path.expanduser("~/.openrouter-token")):
        with open(os.path.expanduser("~/.openrouter-token")) as f:
            key = f.read().strip()
    if not key:
        print("Error: No OpenRouter API key. Store in ~/.openrouter-token or OPENROUTER_API_KEY", file=sys.stderr)
        sys.exit(1)
    return key


def main():
    parser = argparse.ArgumentParser(description="Generate video via OpenRouter API (images/generations endpoint)")
    parser.add_argument("--model", required=True, help="Video generation model (e.g., runway/gen-4-turbo, kling-ai/kling-v2-master)")
    parser.add_argument("--input", required=True, help="Text prompt for video generation")
    parser.add_argument("--output", default="-", help="Output path for saving video URL info, or - for stdout")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API call")
    parser.add_argument("--json", action="store_true", help="Output structured JSON result")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would generate video with model: {args.model}")
        print(f"Prompt: {args.input}")
        if args.output != "-":
            print(f"Output file: {args.output}")
        print("Dry run complete - no API call made")
        return

    api_key = get_api_key()

    request_body = json.dumps({
        "model": args.model,
        "prompt": args.input,
        "n": 1,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/images/generations",
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "model-dispatch",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")

        data = json.loads(raw)

        # Extract video URL from response
        # OpenRouter returns data array: [{"url": "...", ...}]
        video_url = ""
        prompt_used = args.input

        if "data" in data and isinstance(data["data"], list) and data["data"]:
            first = data["data"][0]
            video_url = first.get("url", "")
            prompt_used = first.get("revised_prompt", args.input) or args.input

        usage = data.get("usage", {})
        if usage:
            usage = {
                "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens", 0),
                "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        else:
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if not video_url or not isinstance(video_url, str):
            print("Error: Empty or invalid video URL received from API", file=sys.stderr)
            print("DEBUG: Raw response:", file=sys.stderr)
            print(json.dumps(data, indent=2, default=str), file=sys.stderr)
            sys.exit(1)

        output = {
            "model": args.model,
            "video_url": video_url,
            "prompt_used": prompt_used,
            "usage": usage,
        }

        if args.output != "-":
            with open(args.output, "w") as f:
                json.dump(output, f, indent=2)
            print(f"Result saved to {args.output}", file=sys.stderr)
        if args.json or args.output == "-":
            print(json.dumps(output, indent=2))

    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
        if status == 401:
            print("Error: Unauthorized - check your API key", file=sys.stderr)
        elif status == 402:
            print("Error: Payment required - check your credits", file=sys.stderr)
        elif status == 404:
            print("Error: Model not found - check model ID", file=sys.stderr)
        elif status == 429:
            print("Error: Rate limited - try again later", file=sys.stderr)
        else:
            print(f"Error: HTTP {status}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
