from urllib.parse import urlparse

from backend.models import Portal, RunRequest
from backend.portals.base import JobPageRules, PortalCapabilities


_HOSTS = {
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co", "jobs.lever.co"),
    "workday": ("myworkdayjobs.com",),
}


class ATSAdapter:
    def __init__(self, portal: Portal):
        self.portal = portal
        self.capabilities = PortalCapabilities(
            portal=portal,
            display_name=portal.title(),
            notes="Dedicated host validation with the generic form engine as execution fallback.",
        )

    def accepts_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return parsed.scheme == "https" and any(
            host == allowed or host.endswith("." + allowed)
            for allowed in _HOSTS.get(self.portal, ())
        )

    def job_page_rules(self) -> JobPageRules:
        return self.capabilities.job_page_rules

    def build_discovery_url(self, request: RunRequest) -> str | None:
        supplied = (request.job_url or "").strip()
        if not supplied:
            raise ValueError(
                f"Enter the employer's {self.capabilities.display_name} careers URL."
            )
        if not self.accepts_url(supplied):
            raise ValueError(
                f"The URL does not match the expected {self.capabilities.display_name} host."
            )
        return supplied
