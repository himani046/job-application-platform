from backend.models import Portal, RunRequest
from backend.portals.base import GenericPortalAdapter, PortalAdapter, PortalCapabilities


_CAPABILITIES: dict[Portal, PortalCapabilities] = {
    "linkedin": PortalCapabilities(
        portal="linkedin",
        display_name="LinkedIn",
        notes="Location-aware discovery and manual authentication/challenge recovery.",
    ),
    "naukri": PortalCapabilities(
        portal="naukri",
        display_name="Naukri",
        notes="Generic discovery/application engine with explicit filter confirmation.",
    ),
    "greenhouse": PortalCapabilities(
        portal="greenhouse",
        display_name="Greenhouse",
        notes="Generic ATS form engine; dedicated Greenhouse selectors can be added independently.",
    ),
    "lever": PortalCapabilities(
        portal="lever",
        display_name="Lever",
        notes="Generic ATS form engine; dedicated Lever selectors can be added independently.",
    ),
    "workday": PortalCapabilities(
        portal="workday",
        display_name="Workday",
        notes="Generic ATS form engine; dedicated Workday selectors can be added independently.",
    ),
    "custom": PortalCapabilities(
        portal="custom",
        display_name="Custom ATS",
        notes="Generic HTTPS browser/form engine.",
    ),
}


class RegistryAdapter(GenericPortalAdapter):
    def __init__(self, capabilities: PortalCapabilities):
        super().__init__(capabilities.portal)
        self.capabilities = capabilities


def get_adapter(portal: Portal, request: RunRequest | None = None) -> PortalAdapter:
    # request is accepted now so future adapters can use per-run configuration.
    del request
    return RegistryAdapter(_CAPABILITIES[portal])


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
