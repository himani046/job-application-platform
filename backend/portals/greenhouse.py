from backend.portals.ats import ATSAdapter
from backend.portals.base import PortalCapabilities, PortalFormRules
from backend.models import Portal


class GreenhouseAdapter(ATSAdapter):
    """Greenhouse-specific semantics layered over the generic form engine."""

    RULES = PortalFormRules(
        field_selectors={
            "first_name": (
                'input[name="job_application[first_name]"]',
                "#first_name",
            ),
            "last_name": (
                'input[name="job_application[last_name]"]',
                "#last_name",
            ),
            "email": (
                'input[name="job_application[email]"]',
                "#email",
            ),
            "phone": (
                'input[name="job_application[phone]"]',
                "#phone",
            ),
            "resume": (
                'input[name*="resume"]',
                'input[type="file"]',
            ),
        },
        field_patterns={
            "first_name": (r"\bfirst\s+name\b", r"\bgiven\s+name\b"),
            "last_name": (r"\blast\s+name\b", r"\bfamily\s+name\b", r"\bsurname\b"),
            "email": (r"\be[-\s]?mail\b",),
            "phone": (r"\bphone\b", r"\bmobile\b", r"\btelephone\b"),
            "resume": (r"\bresume\b", r"\brésumé\b", r"\bcv\b"),
            "cover_letter": (r"cover\s*letter",),
        },
        resume_selectors=(
            'input[name*="resume"]',
            'input[type="file"]',
        ),
        next_button_patterns=(
            r"continue",
            r"save and continue",
            r"next",
            r"review",
        ),
        submit_button_patterns=(
            r"submit application",
            r"submit",
        ),
        confirmation_patterns=(
            r"thank you for applying",
            r"your application has been received",
            r"application submitted",
            r"we have received your application",
        ),
    )

    def __init__(self):
        super().__init__("greenhouse")
        self.capabilities = PortalCapabilities(
            portal="greenhouse",
            display_name="Greenhouse",
            notes="Greenhouse-specific field and navigation hints with generic Playwright fallback.",
            form_rules=self.RULES,
        )

    def form_rules(self) -> PortalFormRules:
        return self.RULES
