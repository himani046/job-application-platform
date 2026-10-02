from dataclasses import dataclass, asdict
import re

from backend.universal_form import build_field_spec, answer_from_profile


@dataclass(frozen=True)
class PlannedField:
    key: str
    label: str
    semantic: str
    action: str
    answer: str | None
    reason: str

    def to_dict(self):
        return asdict(self)


def plan_application(fields: list[dict], profile) -> dict:
    planned = []
    for item in fields:
        spec = build_field_spec(item)
        answer = answer_from_profile(spec, profile)

        if spec.sensitive:
            action, reason = "review", "Sensitive or consequential question requires explicit candidate review."
        elif item.get("kind") == "file":
            action, reason = "upload", "Document field should be handled by the resume/document executor."
        elif answer is not None:
            action, reason = "auto_fill", "A verified profile value matches this field semantically."
        elif item.get("required"):
            action, reason = "review", "Required field has no verified profile answer."
        else:
            action, reason = "skip_or_review", "Optional field has no verified profile answer."

        planned.append(PlannedField(
            key=item.get("key", ""),
            label=item.get("label", ""),
            semantic=spec.semantic,
            action=action,
            answer=answer,
            reason=reason,
        ))

    counts = {}
    for item in planned:
        counts[item.action] = counts.get(item.action, 0) + 1

    return {
        "fields": [item.to_dict() for item in planned],
        "counts": counts,
        "requires_human_review": any(item.action == "review" for item in planned),
        "safe_to_auto_fill": all(item.action not in {"review"} for item in planned),
    }


def extract_job_requirements(description: str) -> dict:
    text = (description or "").lower()
    years = None
    match = re.search(r"(?:minimum|min|at least)\s+(\d+(?:\.\d+)?)\s+years?", text)
    if match:
        years = float(match.group(1))

    skills = sorted(set(re.findall(
        r"\b(?:python|java|javascript|typescript|c\+\+|sql|aws|azure|gcp|docker|kubernetes|react|node(?:\.js)?|pytorch|tensorflow|machine learning|deep learning)\b",
        text,
    )))

    return {
        "required_years": years,
        "skills": skills,
        "remote": bool(re.search(r"\bremote\b", text)),
        "hybrid": bool(re.search(r"\bhybrid\b", text)),
    }
