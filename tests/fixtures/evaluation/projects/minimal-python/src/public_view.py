"""Public view with a deliberately homonymous entry point."""


def render(name: str) -> str:
    return f"Public greeting for {name}"
