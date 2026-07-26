"""Project Scanner port contracts."""

from typing import Protocol

from contextforge.scanner.models import ProjectInventory, ScanRequest


class ProjectScanner(Protocol):
    """Port implemented by deterministic project discovery capabilities."""

    def scan(self, request: ScanRequest) -> ProjectInventory:
        """Produce an immutable Project Inventory."""
        ...


class IncrementalProjectScanner(ProjectScanner, Protocol):
    """Scanner capable of reusing a compatible prior inventory."""

    def scan(
        self,
        request: ScanRequest,
        previous_inventory: ProjectInventory | None = None,
    ) -> ProjectInventory:
        """Produce an inventory while reusing compatible prior artifacts."""
        ...
