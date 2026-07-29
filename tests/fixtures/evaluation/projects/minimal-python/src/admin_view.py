"""Administrative view with a deliberately homonymous entry point."""


def render(name: str) -> str:
    return f"Admin greeting for {name}"
