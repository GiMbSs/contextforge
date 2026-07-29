"""Greeting behavior used by the fixture entry point."""

from settings import GREETING


def format_greeting(name: str) -> str:
    return f"{GREETING}, {name}!"
