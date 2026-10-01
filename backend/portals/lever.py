from backend.portals.ats import ATSAdapter
from backend.portals.base import PortalCapabilities, PortalFormRules


class LeverAdapter(ATSAdapter):
    """Lever-specific semantics layered over the generic form engine."""

    RULES = PortalFormRules(
        field_selectors={
            "name": (
                'input[name="name"]',
                'input[data-qa="name"]',
            ),
            "email": (
                'input[name="email"]',
                'input[data-qa="email"]',
            ),
            "phone": (
                'input[name="phone"]',
                'input[data-qa="phone"]',
            ),
            "company": (
                'input[name="org"]',
                'input[data-qa="org"]',
            ),
            "resume": (
                'input[type="file"]',
                'input[name*="resume"]',
            ),
        },
        field_patterns={
            "name": (r"^name$", r"\bfull\s+name\b"),
            "email": (r"\be[-\s]?mail\b",),
            "phone": (r"\bphone\b", r"\bmobile\b", r"\btelephone\b"),
            "resume": (r"\bresume\b", r"\brésumé\b", r"\bcv\b"),
            "cover_letter": (r"cover\s*letter",),
            "location": (r"\blocation\b", r"\bcity\b"),
        },
        resume_selectors=(
            'input[type="file"]',
            'input[name*="resume"]',
        ),
        next_button_patterns=(
            r"continue",
            r"next",
            r"review",
        ),
        submit_button_patterns=(
            r"submit application",
            r"submit",
        ),
        confirmation_patterns=(
            r"thank you",
            r"application submitted",
            r"we have received your application",
            r"application has been received",
        ),
    )

    def __init__(self):
        super().__init__("lever")
        self.capabilities = PortalCapabilities(
            portal="lever",
            display_name="Lever",
            notes="Lever-specific field and navigation hints with generic Playwright fallback.",
            form_rules=self.RULES,
        )

    def form_rules(self) -> PortalFormRules:
        return self.RULES
