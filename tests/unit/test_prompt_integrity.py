from __future__ import annotations

from subscription_bridge.providers.gemini.prompt_io import (
    compact_prompt_compare,
    normalize_prompt_compare,
    prompt_integrity_report,
    sample_chunks,
)


def test_normalize_removes_carriage_returns() -> None:
    result = normalize_prompt_compare("hello\r\nworld\r\n")
    assert "\r" not in result


def test_normalize_replaces_nbsp() -> None:
    result = normalize_prompt_compare("hello\u00a0world")
    assert "\u00a0" not in result


def test_normalize_collapses_tabs() -> None:
    result = normalize_prompt_compare("hello\t\tworld")
    assert "\t" not in result


def test_compact_removes_all_whitespace() -> None:
    result = compact_prompt_compare("hello\n\nworld  ")
    assert "  " not in result
    assert "\n" not in result


def test_compact_preserves_word_order() -> None:
    result = compact_prompt_compare("hello\nworld")
    assert result == "hello world"


def test_exact_prompt_passes_integrity() -> None:
    expected = "Hello, please explain how Python async works"
    report = prompt_integrity_report(expected, expected, min_ratio=0.98)
    assert report["ok"] is True
    assert report["ratio"] >= 0.98


def test_whitespace_normalized_prompt_passes() -> None:
    expected = "Hello world"
    actual = "Hello   world\n\n"
    report = prompt_integrity_report(expected, actual, min_ratio=0.98)
    assert report["ok"] is True


def test_truncated_prompt_fails() -> None:
    expected = "This is a very long prompt that should fail the integrity check because it was truncated at the end"
    actual = "This is a very long"
    report = prompt_integrity_report(expected, actual, min_ratio=0.98)
    assert report["ok"] is False


def test_missing_suffix_fails() -> None:
    expected = "Hello world this is a test prompt with important suffix information at the end"
    actual = "Hello world this is a test"
    report = prompt_integrity_report(expected, actual, min_ratio=0.98)
    assert report["ok"] is False


def test_partial_match_with_lower_min_ratio() -> None:
    long_preamble = "This is the start of a very long prompt that has many words. " * 5
    body = "This is the middle section with important content to verify. " * 3
    suffix = "This is the end with a different conclusion. " * 3
    expected = long_preamble + body + suffix
    actual = long_preamble + body
    report = prompt_integrity_report(expected, actual, min_ratio=0.50)
    assert report["ratio"] >= 0.50
    assert report["prefix_ok"] is True
    assert report["suffix_ok"] is False
    assert report["ok"] is False


def test_empty_expected_passes() -> None:
    report = prompt_integrity_report("", "", min_ratio=0.98)
    assert report["ok"] is True


def test_empty_actual_fails() -> None:
    report = prompt_integrity_report("non-empty prompt", "", min_ratio=0.98)
    assert report["ok"] is False


def test_sample_chunks_short_text() -> None:
    chunks = sample_chunks("short", chunk_size=10)
    assert len(chunks) == 1
    assert chunks[0] == "short"


def test_sample_chunks_long_text() -> None:
    text = "word " * 200
    chunks = sample_chunks(text.rstrip(), chunk_size=96)
    assert len(chunks) >= 3


def test_sample_chunks_empty() -> None:
    assert sample_chunks("") == []


def test_integrity_report_contains_all_keys() -> None:
    report = prompt_integrity_report("test", "test", min_ratio=0.98)
    assert "ok" in report
    assert "expected_len" in report
    assert "actual_len" in report
    assert "ratio" in report
    assert "prefix_ok" in report
    assert "suffix_ok" in report
    assert "chunks_found" in report
    assert "chunks_total" in report
