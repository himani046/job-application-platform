import re
from urllib.parse import urlparse

from backend.models import RunRequest
from backend.portals.base import PortalCapabilities, PortalFormRules


class NaukriAdapter:
    capabilities = PortalCapabilities(
        portal="naukri",
        display_name="Naukri",
        notes="Keyword-based discovery with visible browser filter confirmation.",
    )

    def accepts_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return parsed.scheme == "https" and (
            host == "naukri.com" or host.endswith(".naukri.com")
        )

    def build_discovery_url(self, request: RunRequest) -> str:
        supplied = (request.job_url or "").strip()
        if supplied:
            if not self.accepts_url(supplied):
                raise ValueError("Naukri discovery requires a Naukri URL.")
            return supplied

        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            request.keywords.lower(),
        ).strip("-")
        if not slug:
            raise ValueError("Enter search keywords for Naukri discovery.")
        return f"https://www.naukri.com/{slug}-jobs"

    def form_rules(self) -> PortalFormRules:
        return self.capabilities.form_rules
