#!/usr/bin/env python3
"""
bug-search.py — Search oversight/bugs/ for prior reports before creating new ones.

Implements GC-14 (check-similar-issues) compliance. Returns ranked matches or a
CLEAR signal. Also provides --next-id for BUG/BLK ID sequence assignment (L6-F8).

Usage — similarity search:
  python bug-search.py --query "embedding chunking threshold"
  python bug-search.py --query "trace flush worker permission" --threshold 0.2
  python bug-search.py --query "langfuse" --bugs-dir oversight/bugs

Usage — ID sequence:
  python bug-search.py --next-id                  # next BUG-NNN
  python bug-search.py --next-id --id-type BLK    # next BLK-NNN

Integration: blocker workflow step-01-capture-blocker.md + any bug creation flow.
Savings: 380-650 tokens/event (compounds as bug count grows).
"""

import argparse
import re
import sys
from pathlib import Path


# Files whose names contain these strings (as whole tokens) are skipped during load.
# Hyphen/underscore variants are normalised before matching (ROOT-CAUSE == ROOT_CAUSE).
_SKIP_PATTERNS = ("TEMPLATE", "ROOT_CAUSE", "README")


def _should_skip(fname):
    """Return True if filename should be skipped based on word-boundary pattern matching.

    Uses token-level matching (not substring) to avoid false positives on names like
    ROOT_CAUSES.md that merely contain a skip-pattern as a prefix.
    Normalises hyphens to underscores so ROOT-CAUSE.md and ROOT_CAUSE.md both match.
    """
    if fname.startswith("_"):
        return True
    # Normalise separators then check each pattern as a whole token
    normalized = fname.upper().replace("-", "_")
    for pat in _SKIP_PATTERNS:
        pat_norm = pat.replace("-", "_")
        if re.search(rf'(?:^|_){re.escape(pat_norm)}(?:_|\.| |$)', normalized):
            return True
    return False


def _load_bug_reports(bugs_dir):
    """
    Load all bug report markdown files from bugs_dir.
    Returns a list of dicts with id, file, status, component, summary, full_text.
    """
    reports = []
    path = Path(bugs_dir)
    if not path.exists():
        return reports

    for f in sorted(path.glob("*.md")):
        if _should_skip(f.name):
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # ID
        id_m = re.search(r'\*\*ID\*\*:\s*(BUG-\d+)', content)
        bug_id = id_m.group(1) if id_m else f.stem

        # Status
        status_m = re.search(r'\*\*Status\*\*:\s*\[?([^\]\n]+)\]?', content)
        status = status_m.group(1).strip() if status_m else "Unknown"

        # Component
        comp_m = re.search(r'\*\*Component\*\*:\s*(.+)', content)
        component = comp_m.group(1).strip() if comp_m else ""

        # Summary (first non-empty line after "## Summary")
        summary_m = re.search(r'## Summary\s*\n+(.+?)(?=\n---|\n##|\Z)', content, re.DOTALL)
        summary = summary_m.group(1).strip().split('\n')[0] if summary_m else ""

        reports.append({
            "id":        bug_id,
            "file":      str(f),
            "status":    status,
            "component": component,
            "summary":   summary,
            "full_text": content.lower(),
        })

    return reports


def _score(report, terms):
    """
    Score a report against a list of query terms.
    Returns a float in [0.0, 1.0].

    Weights per term (additive, then normalised by term count):
      summary match   → +0.50
      component match → +0.30
      body match      → +0.10  (only if not already matched in summary or component)
    Max raw score per term = 0.90; we normalize and cap at 1.0.
    """
    raw = 0.0
    summary_low   = report["summary"].lower()
    component_low = report["component"].lower()
    full_text     = report["full_text"]

    for term in terms:
        t = term.lower()
        in_summary   = t in summary_low
        in_component = t in component_low
        if in_summary:
            raw += 0.50
        if in_component:
            raw += 0.30
        # Only count full_text for terms not already counted above to avoid double-counting
        if t in full_text and not in_summary and not in_component:
            raw += 0.10

    if not terms:
        return 0.0
    # Normalise: max raw per term = 0.90
    return round(min(raw / (len(terms) * 0.90), 1.0), 3)


def _tokenise(query):
    """Split query into meaningful tokens (skip single-char words)."""
    tokens = [t for t in re.split(r'[\s,/]+', query.strip()) if len(t) > 1]
    return tokens or [query.strip()]


def search_bugs(bugs_dir, query, threshold):
    """
    Search bug reports for query terms above threshold.
    Returns (matches, total_searched).
    Each match: {id, file, status, component, summary, score}.
    """
    reports = _load_bug_reports(bugs_dir)
    terms = _tokenise(query)

    scored = []
    for r in reports:
        s = _score(r, terms)
        if s >= threshold:
            scored.append({
                "id":        r["id"],
                "file":      r["file"],
                "status":    r["status"],
                "component": r["component"],
                "summary":   r["summary"],
                "score":     s,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored, len(reports)


def _max_numeric_id(pattern, text):
    """Return the highest integer found for pattern (e.g. r'BUG-(\\d+)') in text."""
    found = re.findall(pattern, text)
    return max((int(n) for n in found), default=0)


def next_bug_id(bugs_dir):
    """Return next BUG-NNN based on the highest ID present in bugs_dir files."""
    path = Path(bugs_dir)
    max_id = 0
    if path.exists():
        for f in path.glob("*.md"):
            if _should_skip(f.name):
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            max_id = max(max_id, _max_numeric_id(r'BUG-(\d+)', content))
    return f"BUG-{max_id + 1:03d}"


def next_blk_id(blockers_log_path, bugs_dir=None):
    """Return next BLK-NNN based on the highest ID in blockers-log.md and bugs directory."""
    max_id = 0

    # Scan blockers-log.md
    path = Path(blockers_log_path)
    if path.exists():
        try:
            content = path.read_text(encoding="utf-8")
            max_id = max(max_id, _max_numeric_id(r'BLK-(\d+)', content))
        except (OSError, UnicodeDecodeError):
            pass

    # Also scan bugs directory for any BLK references
    if bugs_dir:
        bugs_path = Path(bugs_dir)
        if bugs_path.exists():
            for f in bugs_path.glob("*.md"):
                if _should_skip(f.name):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    max_id = max(max_id, _max_numeric_id(r'BLK-(\d+)', content))
                except (OSError, UnicodeDecodeError):
                    continue

    return f"BLK-{max_id + 1:03d}"


def _run(args, bugs_dir, blockers_log):
    """Core logic — separated so main() can wrap with an exit-code-2 error handler."""
    # ---- --next-id mode ------------------------------------------------ #
    if args.next_id:
        if args.id_type == "BLK":
            print(next_blk_id(blockers_log, bugs_dir))
        else:
            print(next_bug_id(bugs_dir))
        return

    # ---- search mode ---------------------------------------------------- #
    # P-10: reject whitespace-only queries
    if not args.query.strip():
        raise ValueError("--query must contain non-whitespace characters")

    if args.threshold < 0.0 or args.threshold > 1.0:
        raise ValueError("--threshold must be between 0.0 and 1.0")

    matches, total = search_bugs(bugs_dir, args.query, args.threshold)

    if not matches:
        print(f"CLEAR — no prior reports matching '{args.query}'")
        print(f"(searched {total} file(s) in {bugs_dir}, threshold={args.threshold})")
        print("Safe to create a new bug report.")
    else:
        print(f"MATCHES FOUND — {len(matches)} prior report(s) for '{args.query}'")
        print(f"(searched {total} file(s), threshold={args.threshold})")
        print()
        for i, m in enumerate(matches, 1):
            print(f"  {i}. [{m['id']}] {m['summary']}")
            print(f"     Status: {m['status']}  |  Component: {m['component']}  |  Score: {m['score']}")
            print(f"     File:   {m['file']}")
            print()
        print("Review prior reports before creating a new one (GC-14 compliance).")
        sys.exit(1)   # exit 1 = matches found


def main():
    parser = argparse.ArgumentParser(
        description="Search oversight/bugs/ for prior reports — GC-14 compliance"
    )
    parser.add_argument("--root", default=".",
                        help="Project root directory (default: current directory)")
    parser.add_argument("--bugs-dir", default=None,
                        help="Path to bugs directory (default: <root>/oversight/bugs)")
    parser.add_argument("--threshold", type=float, default=0.1,
                        help="Minimum relevance score 0.0–1.0 (default: 0.1)")
    parser.add_argument("--id-type", choices=["BUG", "BLK"], default="BUG",
                        help="ID type for --next-id: BUG (default) or BLK")
    parser.add_argument("--blockers-log", default=None,
                        help="Path to blockers-log.md (used for BLK --next-id)")

    # L-5: --query and --next-id are mutually exclusive; one is required
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query",
                       help="Symptom or component keywords to search for")
    group.add_argument("--next-id", action="store_true",
                       help="Print next available BUG or BLK ID and exit")

    args = parser.parse_args()

    root        = Path(args.root).resolve()
    bugs_dir    = args.bugs_dir     or str(root / "oversight" / "bugs")
    blockers_log = args.blockers_log or str(root / "oversight" / "tracking" / "blockers-log.md")

    # D-3: exit 2 for unexpected errors (exit 1 is reserved for "matches found")
    try:
        _run(args, bugs_dir, blockers_log)
    except ValueError as e:
        parser.error(str(e))   # argparse-style error → exit 2
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
