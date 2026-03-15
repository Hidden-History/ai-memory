#!/usr/bin/env python3
"""model-dispatch: Audio generation (TTS/music) via OpenRouter API (audio/speech endpoint)

Supports TTS models (openai/tts-1-hd, elevenlabs/eleven_multilingual_v2) and
music generation models (suno/chirp-v3-5). Audio response is binary; saves to
output path or outputs JSON metadata when output is "-".
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
    parser = argparse.ArgumentParser(description="Generate audio via OpenRouter API (audio/speech endpoint)")
    parser.add_argument("--model", required=True, help="TTS or audio generation model (e.g., openai/tts-1-hd, elevenlabs/eleven_multilingual_v2)")
    parser.add_argument("--input", required=True, help="Text to synthesize")
    parser.add_argument("--output", default="-", help="Output path for audio file, or - for stdout (outputs JSON metadata)")
    parser.add_argument("--voice", default="alloy", help="Voice ID (model-specific, default: alloy for OpenAI)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API call")
    parser.add_argument("--json", action="store_true", help="Output metadata as JSON (always used with --output -)")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would generate audio with model: {args.model}")
        print(f"Text: {args.input}")
        print(f"Voice: {args.voice}")
        if args.output != "-":
            print(f"Output file: {args.output}")
        print("Dry run complete - no API call made")
        return

    api_key = get_api_key()

    request_body = json.dumps({
        "model": args.model,
        "input": args.input,
        "voice": args.voice,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/audio/speech",
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
            audio_bytes = resp.read()
            content_type = resp.headers.get("Content-Type", "")

        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if args.output != "-":
            # Save binary audio to file
            with open(args.output, "wb") as f:
                f.write(audio_bytes)
            print(f"Audio saved to {args.output}", file=sys.stderr)
            audio_url = args.output
        else:
            # Save to temp file and report path
            import tempfile
            suffix = ".mp3"
            if "ogg" in content_type:
                suffix = ".ogg"
            elif "wav" in content_type:
                suffix = ".wav"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="audio-generate-")
            tmp.write(audio_bytes)
            tmp.close()
            audio_url = tmp.name
            print(f"Audio saved to temp file: {audio_url}", file=sys.stderr)

        output = {
            "model": args.model,
            "audio_url": audio_url,
            "duration_seconds": 0.0,  # Not provided by API endpoint; duration unknown without decoding
            "usage": usage,
        }

        # Always print JSON when --json flag or output is "-"
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
