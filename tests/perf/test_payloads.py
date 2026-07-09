"""Unit tests for scripts/perf/embedding_capacity/payloads.py — realistic payload sampling.

BP-179 §2 requires realistic payloads, NOT toy strings; these tests verify the
module slices genuine corpus content (given a real directory) and only falls
back to a clearly-marked placeholder when the corpus is empty.
"""

import warnings

import pytest
from embedding_capacity import payloads


def test_sample_texts_slices_real_corpus_content(tmp_path):
    corpus = tmp_path / "notes.md"
    corpus.write_text("word " * 5000)  # 25000 chars of real (if repetitive) content
    dist = payloads.LengthDistribution(p50_chars=100, p99_chars=500)

    texts = payloads.sample_texts(tmp_path, n=10, distribution=dist, model="en", seed=1)

    assert len(texts) == 10
    assert all(text.strip() for text in texts)
    assert not any("harness-smoke-placeholder" in text for text in texts)


def test_sample_texts_respects_model_glob_pattern(tmp_path):
    (tmp_path / "prose.md").write_text("prose content " * 1000)
    (tmp_path / "code.py").write_text("def f():\n    return 1\n" * 1000)
    dist = payloads.LengthDistribution(p50_chars=50, p99_chars=200)

    en_texts = payloads.sample_texts(
        tmp_path, n=5, distribution=dist, model="en", seed=1
    )
    code_texts = payloads.sample_texts(
        tmp_path, n=5, distribution=dist, model="code", seed=1
    )

    assert all("prose content" in t for t in en_texts)
    assert all("def f" in t or "return 1" in t for t in code_texts)


def test_sample_texts_falls_back_to_marked_placeholder_when_corpus_empty(tmp_path):
    dist = payloads.LengthDistribution(p50_chars=100, p99_chars=500)
    with pytest.warns(UserWarning, match="falling back to placeholder"):
        texts = payloads.sample_texts(
            tmp_path, n=3, distribution=dist, model="en", seed=1
        )

    assert len(texts) == 3
    assert all("harness-smoke-placeholder-corpus-empty" in text for text in texts)


def test_sample_texts_does_not_warn_when_corpus_has_content(tmp_path):
    (tmp_path / "notes.md").write_text("word " * 5000)
    dist = payloads.LengthDistribution(p50_chars=100, p99_chars=500)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        payloads.sample_texts(tmp_path, n=3, distribution=dist, model="en", seed=1)


def test_corpus_is_empty_true_when_no_matching_files(tmp_path):
    assert payloads.corpus_is_empty(tmp_path, model="en") is True


def test_corpus_is_empty_false_when_matching_files_present(tmp_path):
    (tmp_path / "notes.md").write_text("some content")
    assert payloads.corpus_is_empty(tmp_path, model="en") is False


def test_corpus_is_empty_respects_model_glob(tmp_path):
    (tmp_path / "code.py").write_text("def f():\n    return 1\n")
    assert payloads.corpus_is_empty(tmp_path, model="en") is True
    assert payloads.corpus_is_empty(tmp_path, model="code") is False


def test_sample_texts_is_deterministic_with_seed(tmp_path):
    corpus = tmp_path / "notes.md"
    corpus.write_text("some deterministic content " * 500)
    dist = payloads.LengthDistribution(p50_chars=100, p99_chars=300)

    first = payloads.sample_texts(tmp_path, n=5, distribution=dist, model="en", seed=42)
    second = payloads.sample_texts(
        tmp_path, n=5, distribution=dist, model="en", seed=42
    )

    assert first == second


def test_length_distribution_sample_is_near_p50_to_p99_range():
    dist = payloads.LengthDistribution(p50_chars=800, p99_chars=2048)
    import random

    rng = random.Random(7)
    samples = [dist.sample(rng) for _ in range(500)]
    # Almost all draws should land within [p50, p99] * generous slack for the ~1% tail.
    within_range = sum(
        1 for s in samples if dist.p50_chars <= s <= dist.p99_chars * 1.5
    )
    assert within_range / len(samples) > 0.95
