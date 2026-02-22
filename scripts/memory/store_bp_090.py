#!/usr/bin/env python3
"""Store BP-090: RAG Security Scanning Graduated Trust to conventions collection.

This script stores the RAG security scanning graduated trust and content-type
awareness best practices research to the database for semantic retrieval.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.storage import store_best_practice

# Condensed version for storage (optimized for semantic search)
# Full document: oversight/knowledge/best-practices/BP-090-rag-security-scanning-graduated-trust-content-type-awareness-2026.md
CONTENT = """
RAG Security Scanning — Graduated Trust & Content-Type Awareness (2026)

PROBLEM:
Applying identical 3-layer scanning (regex + detect-secrets + SpaCy NER) to ALL content
regardless of source causes catastrophic false positive rates:
- 100% block rate on GitHub API content (1026 blocked, 0 stored)
- detect-secrets Layer 2 entropy scanning is the primary culprit
- Code variable names (API_KEY, TOKEN, SECRET) trigger false positives as identifiers

GRADUATED TRUST MODEL:
Security scanners in RAG pipelines must implement source-type-aware scan policies:
- High trust (0.9+): Internal agent outputs, system prompts — PII check only, skip secrets
- Medium-High (0.7-0.89): GitHub API, Jira API (authenticated) — PII + pattern-only, skip entropy
- Medium (0.5-0.69): Verified webhooks — full scan minus entropy detection
- Low (0.2-0.49): User sessions (authenticated) — full scan + prompt injection check
- Untrusted (0.0-0.19): Anonymous input, scraped web — full scan + adversarial + quarantine

ARCHITECTURE PATTERN:
Content -> Source Classifier -> Policy Router -> [Scan Layers] -> Store/Block
Add source_type parameter to scan(). Route to different scan profiles based on source.

DETECT-SECRETS TUNING FOR CODE CONTENT:
- Raise base64-limit from 4.5 to 5.0-5.5
- Raise hex-limit from 3.0 to 3.5-4.0
- Disable KeywordDetector for code contexts
- Min secret length: 8-12 chars
- Context-word gating: only flag when trigger words (password, secret, auth) appear nearby
- Assignment vs declaration detection: API_KEY = "sk-..." (flag) vs def get_api_key(): (safe)
- Value-quality filtering: ignore strings <9 chars, use gibberish detector for randomness

PII SCANNING IN DEVELOPER TOOLS:
- Prefer Microsoft Presidio over raw SpaCy NER
- Context-aware enhancers boost confidence only with trigger words
- Developer allow lists: team names, bot emails, noreply addresses
- Entity-type selection: skip LOCATION/DATE in code contexts
- Score threshold: 0.7+ for high-trust, 0.5 for untrusted
- Filter SpaCy NER false positives: CamelCase, snake_case, module paths, HTML tags,
  file paths, ALL_CAPS constants

IMPLEMENTATION FOR RAG MEMORY SYSTEMS:
1. Add source_type: str = "user_session" parameter to SecurityScanner.scan()
2. Create ScanPolicy dataclass with per-source-type configuration
3. Add SECURITY_SCAN_GITHUB_MODE=relaxed|strict|off config option
4. When source_type starts with "github_": skip Layer 2 (detect-secrets), use PII-only
5. For session content: raise entropy thresholds, disable KeywordDetector, add context-word gating

ANTI-PATTERNS:
- NEVER apply identical scan rules to authenticated API content and untrusted user input
- NEVER use entropy-based secret detection on code variable names (false positive factory)
- NEVER block-and-discard without audit logging (silent data loss)
- NEVER scan structured API metadata fields (author, labels, timestamps) for secrets

Sources: TrustRAG (AAAI 2026), AWS RAG Security blog, detect-secrets (Yelp),
Microsoft Presidio, BigCode pii-lib, OpenHands entropy tuning, HashiCorp false positives
""".strip()


def main():
    """Store BP-090 to conventions collection."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "bp-090-storage")

    print("Storing BP-090 to conventions collection...")
    print(f"Session ID: {session_id}")
    print(f"Content length: {len(CONTENT)} chars")

    try:
        result = store_best_practice(
            content=CONTENT,
            session_id=session_id,
            source_hook="manual",
            domain="rag-security-scanning",
            tags=[
                "security-scanning",
                "graduated-trust",
                "content-type-awareness",
                "detect-secrets",
                "pii-scanning",
                "rag",
                "false-positives",
                "entropy-detection",
                "source-type",
                "scan-policy",
            ],
            source="oversight/knowledge/best-practices/BP-090-rag-security-scanning-graduated-trust-content-type-awareness-2026.md",
            source_date="2026-02-19",
            auto_seeded=True,
            type="guideline",
            bp_id="BP-090",
            doc_type="best-practice",
            topic="rag-security-scanning-graduated-trust",
            created="2026-02-19",
        )

        print("\nStorage Result:")
        print(f"  Status: {result.get('status')}")
        print(f"  Memory ID: {result.get('memory_id')}")
        print(f"  Embedding Status: {result.get('embedding_status')}")
        print(f"  Collection: {result.get('collection')}")
        print(f"  Group ID: {result.get('group_id')}")

        if result.get("status") == "stored":
            print("\nSUCCESS: BP-090 stored to conventions collection")
            return 0
        elif result.get("status") == "duplicate":
            print("\nDUPLICATE: BP-090 already exists in database")
            return 0
        else:
            print(f"\nWARNING: Unexpected status: {result.get('status')}")
            return 1

    except Exception as e:
        print("\nERROR: Failed to store BP-090")
        print(f"  Error: {e!s}")
        print(f"  Type: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
