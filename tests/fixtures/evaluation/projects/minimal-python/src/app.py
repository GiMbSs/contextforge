"""Small entry point used by evaluation fixtures."""

from service import format_greeting


def greet(name: str) -> str:
    return format_greeting(name)
