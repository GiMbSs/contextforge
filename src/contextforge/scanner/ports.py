"""Project Scanner port contract."""

from typing import Protocol

from contextforge.scanner.models import ProjectInventory, ScanRequest


class ProjectScanner(Protocol):
    """Port implemented by deterministic project discovery capabilities."""

    def scan(self, request: ScanRequest) -> ProjectInventory:
        """Produce an immutable Project Inventory."""
        ...
