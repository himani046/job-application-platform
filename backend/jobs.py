import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.models import JobRecord


_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "trk", "trkInfo", "refId", "trackingId",
}


def canonical_job_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in _TRACKING_KEYS
    ]
    path = re.sub(r"/+$", "", parsed.path) or "/"
    return urlunparse((parsed.scheme.lower(), (parsed.hostname or "").lower(), path, "", urlencode(query), ""))


def job_fingerprint(url: str, title: str = "") -> str:
    """Return a stable identity for a canonical job URL.

    The title parameter remains for API compatibility, but URL identity is
    authoritative so a changed listing title does not create a duplicate job.
    """
    canonical = canonical_job_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_job(item: dict, portal: str) -> JobRecord:
    url = canonical_job_url(item["url"])
    return JobRecord(
        id=job_fingerprint(url, item.get("title", "")),
        portal=portal,
        title=item.get("title", "").strip(),
        url=url,
        company=item.get("company", "").strip(),
        location=item.get("location", "").strip(),
        description=item.get("description", "").strip(),
        discovered_at=item.get(
            "discovered_at",
            datetime.now(timezone.utc).isoformat(),
        ),
        metadata=item.get("metadata", {}),
    )
