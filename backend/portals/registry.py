from backend.models import Portal, RunRequest
from backend.portals.ats import ATSAdapter
from backend.portals.base import GenericPortalAdapter, PortalAdapter, PortalCapabilities
from backend.portals.linkedin import LinkedInAdapter
from backend.portals.naukri import NaukriAdapter


_CAPABILITIES: dict[Portal, PortalCapabilities] = {
    "linkedin": LinkedInAdapter.capabilities,
    "naukri": NaukriAdapter.capabilities,
    "greenhouse": ATSAdapter("greenhouse").capabilities,
    "lever": ATSAdapter("lever").capabilities,
    "workday": ATSAdapter("workday").capabilities,
    "custom": PortalCapabilities(
        portal="custom",
        display_name="Custom ATS",
        notes="Generic HTTPS browser/form engine.",
    ),
}


def get_adapter(portal: Portal, request: RunRequest | None = None) -> PortalAdapter:
    del request

    if portal == "linkedin":
        return LinkedInAdapter()
    if portal == "naukri":
        return NaukriAdapter()
    if portal in {"greenhouse", "lever", "workday"}:
        return ATSAdapter(portal)

    return GenericPortalAdapter("custom")


def list_adapters() -> list[dict]:
    return [
        {
            "portal": capability.portal,
            "display_name": capability.display_name,
            "supports_login": capability.supports_login,
            "supports_discovery": capability.supports_discovery,
            "supports_application": capability.supports_application,
            "notes": capability.notes,
        }
        for capability in _CAPABILITIES.values()
    ]
