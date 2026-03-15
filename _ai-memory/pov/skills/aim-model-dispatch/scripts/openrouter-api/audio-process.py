#!/usr/bin/env python3
"""model-dispatch: Audio processing via OpenRouter API (Whisper transcription)"""
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


def detect_audio_type(file_path):
    """Detect audio file type from extension."""
    ext = os.path.splitext(file_path)[1].lower()
    type_map = {
        ".mp3": "mp3",
        ".wav": "wav",
        ".ogg": "ogg",
        ".webm": "webm",
        ".m4a": "m4a",
        ".flac": "flac",
    }
    return type_map.get(ext, "mp3")


def main():
    parser = argparse.ArgumentParser(description="Process audio via OpenRouter API")
    parser.add_argument("--model", required=True, help="OpenRouter audio model ID (e.g., openai/whisper-1)")
    parser.add_argument("--input", required=True, help="Audio file path")
    parser.add_argument("--output", default="-", help="Output file or '-' for stdout")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API call")
    parser.add_argument("--json", action="store_true", help="Output structured JSON result")
    parser.add_argument("--language", help="ISO language code (e.g., en, es) - optional, auto-detected if not specified")
    parser.add_argument("--prompt", help="Optional prompt to guide transcription")
    parser.add_argument("--response-format", choices=["json", "text", "srt", "vtt", "verbose_json"], default="json", help="Response format")
    parser.add_argument("--temperature", type=float, default=0, help="Temperature for generation")
    parser.add_argument("--translate", action="store_true", help="Translate to English if non-English audio")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would process audio with model: {args.model}")
        print(f"Audio file: {args.input}")
        print(f"Response format: {args.response_format}")
        if args.output != "-":
            print(f"Output to: {args.output}")
        print("Dry run complete - no API call made")
        return

    if not os.path.exists(args.input):
        print(f"Error: Audio file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    client = get_client()

    try:
        with open(args.input, "rb") as audio_file:
            if args.translate:
                response = client.audio.translations.create(
                    model=args.model,
                    file=audio_file,
                    prompt=args.prompt or None,
                    response_format=args.response_format,
                    temperature=args.temperature,
                    extra_headers={"X-OpenRouter-Title": "model-dispatch"},
                )
            else:
                response = client.audio.transcriptions.create(
                    model=args.model,
                    file=audio_file,
                    language=args.language or None,
                    prompt=args.prompt or None,
                    response_format=args.response_format,
                    temperature=args.temperature,
                    extra_headers={"X-OpenRouter-Title": "model-dispatch"},
                )

        # Handle different response formats
        if args.response_format == "json":
            # Structured JSON response
            result_text = response.text
            result_data = response.model_dump() if hasattr(response, "model_dump") else {"text": str(response)}
        else:
            # Text-based formats
            result_text = str(response)
            result_data = {"text": result_text, "format": args.response_format}

        if args.json:
            output = {
                "model": args.model,
                "transcription": result_data,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
            print(json.dumps(output, indent=2))
        else:
            if args.output == "-":
                print(result_text)
            else:
                with open(args.output, "w") as f:
                    f.write(result_text)
                print(f"Output written to {args.output}")

        # Print duration info if available
        if hasattr(response, "duration") and response.duration:
            print(f"Duration: {response.duration:.2f} seconds", file=sys.stderr)

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
