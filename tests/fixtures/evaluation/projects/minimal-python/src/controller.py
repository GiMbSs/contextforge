"""Top-level request handling used to exercise a deep dependency chain."""

from app import greet


def build_response(name: str) -> str:
    return greet(name)
