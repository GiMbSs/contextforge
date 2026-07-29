"""Test entry point used to exercise navigation to production code."""

from service import format_greeting


def test_format_greeting() -> None:
    assert format_greeting("Ada") == "Hello, Ada!"
