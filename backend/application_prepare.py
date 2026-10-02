import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldReview:
    category: str
    sensitive: bool
    reason: str


_SENSITIVE_PATTERNS = {
    "work_authorization": (
        r"work authorization|work authori[sz]ed|authorized to work|legally entitled to work|"
        r"right to work|employment eligibility|eligible to work|permission to work|"
        r"visa status|visa sponsorship|sponsor(?:ship)?|require sponsorship|"
        r"future sponsorship|immigration status",
    ),
    "salary": (
        r"salary|compensation|pay expectation|expected pay|desired pay|ctc|"
        r"annual compensation|hourly rate|desired salary|expected salary",
    ),
    "demographic": (
        r"gender|gender identity|sex|race|ethnicity|disability|disabled|"
        r"veteran|protected veteran|military status",
    ),
    "citizenship": (
        r"citizenship|nationality|country of citizenship|dual citizen",
    ),
    "legal": (
        r"criminal|conviction|felony|misdemeanor|background check|"
        r"security clearance|drug test|legally required",
    ),
}


def classify_field(label: str, meta: str = "") -> FieldReview:
    question = f"{label} {meta}".strip()
    for category, patterns in _SENSITIVE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, question, re.I):
                return FieldReview(
                    category=category,
                    sensitive=True,
                    reason="Requires explicit candidate review before submission.",
                )
    return FieldReview(category="standard", sensitive=False, reason="Safe for profile-based filling when a factual answer is available.")


def review_field(item: dict) -> dict:
    review = classify_field(item.get("label", ""), item.get("meta", ""))
    return {
        "key": item.get("key", ""),
        "label": item.get("label", ""),
        "kind": item.get("kind", "text"),
        "required": bool(item.get("required")),
        "filled": bool(item.get("filled")),
        "category": review.category,
        "sensitive": review.sensitive,
        "review_required": review.sensitive or not item.get("filled", False),
        "reason": review.reason,
    }
