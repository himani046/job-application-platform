"""Portal adapter package.

Adapters isolate portal-specific discovery and navigation rules from the
generic Playwright form engine. The current engine remains the execution
fallback while dedicated adapters are introduced incrementally.
"""
from backend.portals.registry import get_adapter, list_adapters

__all__ = ["get_adapter", "list_adapters"]
