"""Realistic payload generation for the embedding capacity harness (BP-179 §2/§4).

BP-179 §2 is explicit that sizing off a light single-caller / toy-string
measurement is the #1 way to ship an envelope that passes CI and dies in
production. This module slices real repository content (prose for the "en"
model, code for the "code" model) to hit a target character-length
distribution, instead of generating lorem-ipsum.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

EN_GLOB_PATTERNS = ("*.md",)
CODE_GLOB_PATTERNS = ("*.py",)

# Bound how much corpus text a single harness run reads, so pointing --corpus-dir
# at a large tree (e.g. the whole repo) stays fast instead of walking everything.
MAX_CORPUS_FILES = 200
MAX_CORPUS_CHARS = 2_000_000


@dataclass
class LengthDistribution:
    """A payload character-length distribution, anchored to measured production data.

    Defaults are BP-179 §6's anchor (~2KB/text at the S115 cap-reproducing load).
    Override p50/p99 with a fresh measured sample when one becomes available.
    """

    p50_chars: int = 800
    p99_chars: int = 2048

    def sample(self, rng: random.Random) -> int:
        """Log-uniform draw between p50 and p99; ~1% of draws exceed p99 (tail)."""
        if rng.random() < 0.01:
            return int(self.p99_chars * rng.uniform(1.0, 1.5))
        lo, hi = math.log(max(self.p50_chars, 1)), math.log(max(self.p99_chars, 2))
        return int(math.exp(rng.uniform(lo, hi)))


def _collect_corpus_text(corpus_dir: Path, patterns: tuple[str, ...]) -> str:
    chunks: list[str] = []
    total_chars = 0
    files_read = 0
    for pattern in patterns:
        for path in sorted(corpus_dir.rglob(pattern)):
            if files_read >= MAX_CORPUS_FILES or total_chars >= MAX_CORPUS_CHARS:
                break
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            chunks.append(text)
            total_chars += len(text)
            files_read += 1
    return "\n\n".join(chunks)


def sample_texts(
    corpus_dir: Path,
    n: int,
    distribution: LengthDistribution,
    model: str = "en",
    seed: int | None = None,
) -> list[str]:
    """Slice `n` real contiguous windows of corpus text sized per `distribution`.

    Falls back to a clearly-marked repeated placeholder if the corpus is empty —
    a degraded mode for smoke-testing the harness itself, NOT a substitute for
    BP-179 §2's "realistic payloads" requirement in an actual measurement run.
    """
    rng = random.Random(seed)
    patterns = CODE_GLOB_PATTERNS if model == "code" else EN_GLOB_PATTERNS
    corpus = _collect_corpus_text(corpus_dir, patterns)
    if not corpus:
        return [
            "[harness-smoke-placeholder-corpus-empty] "
            * (distribution.sample(rng) // 40 + 1)
            for _ in range(n)
        ]
    texts = []
    for _ in range(n):
        length = min(distribution.sample(rng), len(corpus))
        start = rng.randint(0, len(corpus) - length) if len(corpus) > length else 0
        texts.append(corpus[start : start + length])
    return texts
