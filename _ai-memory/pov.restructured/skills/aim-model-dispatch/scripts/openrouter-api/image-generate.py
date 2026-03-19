#!/usr/bin/env python3
"""model-dispatch: Image generation via OpenRouter API (chat completions)

Modern image generation models (GPT-5 Image, Gemini Image) use the chat
completions API, not the legacy images.generate() endpoint. The response
contains image URLs or base64 data embedded in the message content.
"""
import argparse
import base64
import json
import re
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


def extract_images_from_text(text):
    """Extract image URLs from text content (markdown images or raw URLs)."""
    images = []
    # Match markdown image syntax: ![alt](url)
    md_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', text)
    for alt, url in md_images:
        images.append({"url": url, "alt": alt})
    # Match raw image URLs not already captured
    if not images:
        url_pattern = r'https?://[^\s<>"]+\.(?:png|jpg|jpeg|gif|webp|svg)[^\s<>"]*'
        raw_urls = re.findall(url_pattern, text, re.IGNORECASE)
        for url in raw_urls:
            images.append({"url": url, "alt": ""})
    # Match base64 data URIs
    if not images:
        b64_pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+'
        b64_urls = re.findall(b64_pattern, text)
        for url in b64_urls:
            images.append({"url": url, "alt": ""})
    return images


def extract_images_from_message_field(message):
    """Extract images from message.images (OpenRouter's non-standard field).

    OpenRouter returns generated images in message.images, a sibling of
    message.content. The openai Python library drops non-standard fields
    from object attributes, so we must access it via model_dump().

    Structure: message.images = [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]
    """
    images = []
    raw = message.model_dump() if hasattr(message, "model_dump") else {}
    for img in raw.get("images", []) or []:
        if isinstance(img, dict):
            url = img.get("image_url", {}).get("url", "")
            if url:
                images.append({"url": url, "alt": ""})
    return images


def extract_images_from_response(message):
    """Extract images from message — checks message.images first, then content."""
    images = []
    text_parts = []

    # Primary: check message.images field (OpenRouter image generation format)
    images.extend(extract_images_from_message_field(message))

    # Extract text from content
    content = message.content

    # Case 1: content is a string
    if isinstance(content, str):
        text_parts.append(content)
        if not images:
            images.extend(extract_images_from_text(content))
        return images, "\n".join(text_parts)

    # Case 2: content is a list of content parts (multimodal response)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                ptype = part.get("type", "")
                if ptype == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url and not any(i["url"] == url for i in images):
                        images.append({"url": url, "alt": ""})
                elif ptype == "text":
                    text = part.get("text", "")
                    text_parts.append(text)
                    if not images:
                        images.extend(extract_images_from_text(text))
            elif hasattr(part, "type"):
                if part.type == "image_url" and hasattr(part, "image_url"):
                    url = part.image_url.url if hasattr(part.image_url, "url") else ""
                    if url and not any(i["url"] == url for i in images):
                        images.append({"url": url, "alt": ""})
                elif part.type == "text" and hasattr(part, "text"):
                    text_parts.append(part.text)
                    if not images:
                        images.extend(extract_images_from_text(part.text))
        return images, "\n".join(text_parts)

    # Case 3: content is None
    text_parts.append(str(content) if content else "")
    return images, "\n".join(text_parts)


def main():
    parser = argparse.ArgumentParser(description="Generate images via OpenRouter API (chat completions)")
    parser.add_argument("--model", required=True, help="Image generation model (e.g., openai/gpt-5-image, google/gemini-3-pro-image-preview)")
    parser.add_argument("--input", required=True, help="Text prompt for image generation")
    parser.add_argument("--output", default="-", help="Output file path for saving image, or - for stdout")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API call")
    parser.add_argument("--json", action="store_true", help="Output structured JSON result")
    parser.add_argument("--size", default="1024x1024", help="Desired image size (hint, model may ignore)")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request")
    args = parser.parse_args()

    if args.dry_run:
        print(f"Would generate image(s) with model: {args.model}")
        print(f"Prompt: {args.input}")
        print(f"Size hint: {args.size}, Count: {args.n}")
        if args.output != "-":
            print(f"Output file: {args.output}")
        print("Dry run complete - no API call made")
        return

    client = get_client()

    prompt = args.input
    if args.n > 1:
        prompt = f"Generate {args.n} distinct images. {prompt}"

    try:
        response = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": prompt}],
            extra_headers={"X-OpenRouter-Title": "model-dispatch"},
        )

        message = response.choices[0].message
        images, text_content = extract_images_from_response(message)

        # Debug: dump raw response structure if no images found
        if not images:
            raw = message.model_dump() if hasattr(message, "model_dump") else str(message)
            print(f"DEBUG: No images extracted. Raw message structure:", file=sys.stderr)
            print(json.dumps(raw, indent=2, default=str), file=sys.stderr)

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        # Save image to file (works with both --json and non-json modes)
        if args.output != "-" and images:
            url = images[0]["url"]
            if not url or not isinstance(url, str):
                print("Error: Empty or invalid image URL received from API", file=sys.stderr)
                sys.exit(1)
            if url.startswith("data:"):
                if "," not in url:
                    print("Error: Malformed data URI — missing comma separator", file=sys.stderr)
                    sys.exit(1)
                header, b64data = url.split(",", 1)
                try:
                    img_bytes = base64.b64decode(b64data)
                except Exception as e:
                    print(f"Error: Invalid base64 image data: {e}", file=sys.stderr)
                    sys.exit(1)
                with open(args.output, "wb") as f:
                    f.write(img_bytes)
            else:
                import urllib.request
                urllib.request.urlretrieve(url, args.output)
            print(f"Image saved to {args.output}", file=sys.stderr)

        if args.json:
            output = {
                "model": args.model,
                "images": images,
                "content": text_content,
                "usage": usage,
            }
            print(json.dumps(output, indent=2))
        else:
            if images:
                for i, img in enumerate(images):
                    url_display = img["url"][:100] + "..." if len(img["url"]) > 100 else img["url"]
                    print(f"Image {i + 1}: {url_display}")
            else:
                print(text_content)

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
