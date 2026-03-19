#!/usr/bin/env python3
"""model-dispatch: Text generation via OpenRouter API"""
import argparse
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


def read_input(input_str):
    """Read input from string or file."""
    if os.path.exists(input_str):
        with open(input_str, "r") as f:
            return f.read()
    return input_str


def main():
    parser = argparse.ArgumentParser(description="Generate text via OpenRouter API")
    parser.add_argument("--model", required=True, help="OpenRouter model ID")
    parser.add_argument("--input", required=True, help="Prompt text or file path")
    parser.add_argument("--output", default="-", help="Output file or '-' for stdout")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API call")
    parser.add_argument("--json", action="store_true", help="Output structured JSON result")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature for generation")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Maximum output tokens")
    parser.add_argument("--instructions", help="System instructions")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would call model: {args.model}")
        print(f"Input: {args.input[:100]}...")
        if args.output != "-":
            print(f"Output to: {args.output}")
        print("Dry run complete - no API call made")
        return

    client = get_client()
    prompt = read_input(args.input)

    try:
        messages = []
        if args.instructions:
            messages.append({"role": "system", "content": args.instructions})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=args.model,
            messages=messages,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            extra_headers={"X-OpenRouter-Title": "model-dispatch"},
        )

        result = response.choices[0].message.content
        usage = response.usage
        if usage:
            input_tokens = usage.prompt_tokens or 0
            output_tokens = usage.completion_tokens or 0
            total_tokens = usage.total_tokens or 0
        else:
            input_tokens = output_tokens = total_tokens = 0

        if args.json:
            output = {
                "model": args.model,
                "content": result,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
            }
            print(json.dumps(output, indent=2))
        else:
            if args.output == "-":
                print(result)
            else:
                with open(args.output, "w") as f:
                    f.write(result)
                print(f"Output written to {args.output}")

        # Print token usage to stderr
        print(f"Tokens: {total_tokens} (input: {input_tokens}, output: {output_tokens})", file=sys.stderr)

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
