from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from backend.models import Portal, RunRequest


@dataclass(frozen=True)
class PortalCapabilities:
    portal: Portal
    display_name: str
    supports_login: bool = True
    supports_discovery: bool = True
    supports_application: bool = True
    notes: str = ""


class PortalAdapter(Protocol):
    capabilities: PortalCapabilities

    def accepts_url(self, url: str) -> bool:
        ...

    def build_discovery_url(self, request: RunRequest) -> str | None:
        ...


class GenericPortalAdapter:
    """Metadata-first adapter used while a portal-specific adapter is absent."""

    capabilities = PortalCapabilities(
        portal="custom",
        display_name="Custom ATS",
        notes="Uses the generic browser/form engine; portal-specific rules can be added without changing the engine.",
    )

    def __init__(self, portal: Portal):
        self.portal = portal
        self.capabilities = PortalCapabilities(
            portal=portal,
            display_name=portal.replace("_", " ").title(),
            notes="Generic Playwright adapter.",
        )

    def accepts_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme == "https" and bool(parsed.hostname)

    def build_discovery_url(self, request: RunRequest) -> str | None:
        return request.job_url or None
