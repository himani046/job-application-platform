from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.models import RunRequest
from backend.portals.base import PortalCapabilities


class LinkedInAdapter:
    capabilities = PortalCapabilities(
        portal="linkedin",
        display_name="LinkedIn",
        notes="Location-aware search URL generation with manual authentication/challenge recovery.",
    )

    def accepts_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme == "https"
            and (host == "linkedin.com" or host.endswith(".linkedin.com"))
        )

    def build_discovery_url(self, request: RunRequest) -> str:
        location = request.search_location.strip()
        if not location:
            raise ValueError(
                "Enter a job search location, such as India or Bengaluru, India."
            )

        supplied = (request.job_url or "").strip()
        parsed = urlparse(supplied or "https://www.linkedin.com/jobs/search/")
        if not self.accepts_url(parsed.geturl()):
            raise ValueError("LinkedIn discovery requires a LinkedIn URL.")
        if parsed.path.rstrip("/") != "/jobs/search":
            raise ValueError(
                "Use a LinkedIn /jobs/search/ URL for discovery, or leave it empty."
            )

        parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for key in (
            "location", "geoId", "f_PP", "f_G", "f_WT", "distance",
            "start", "pageNum", "position", "trk", "trkInfo",
        ):
            parameters.pop(key, None)

        if request.keywords.strip():
            parameters["keywords"] = request.keywords.strip()
        parameters["location"] = location

        workplace = {"onsite": "1", "remote": "2", "hybrid": "3"}
        if request.workplace_type in workplace:
            parameters["f_WT"] = workplace[request.workplace_type]

        return urlunparse((
            "https",
            parsed.netloc,
            "/jobs/search/",
            "",
            urlencode(parameters),
            "",
        ))
