from __future__ import annotations

from subscription_bridge.browser.ui_guard import default_unsafe_words, make_bad_words_check


def test_default_unsafe_words() -> None:
    words = default_unsafe_words()
    assert isinstance(words, list)
    assert len(words) >= 10
    assert "delete" in words
    assert "settings" in words


def test_make_bad_words_check_script() -> None:
    script = make_bad_words_check(["delete", "share"])
    assert "delete" in script
    assert "share" in script
    assert "badWords" in script
