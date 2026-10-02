import re
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class FieldSpec:
    key: str
    kind: str
    label: str
    meta: str = ""
    required: bool = False
    sensitive: bool = False
    semantic: str = "unknown"
    options: tuple[dict, ...] = ()
    filled: bool = False
    def to_dict(self) -> dict:
        data = asdict(self)
        data["options"] = list(self.options)
        return data

SEMANTICS = {
    "first_name": (r"\bfirst\s*name\b", r"\bgiven\s*name\b"),
    "last_name": (r"\blast\s*name\b", r"\bfamily\s*name\b", r"\bsurname\b"),
    "full_name": (r"\bfull\s*name\b", r"\bcandidate\s*name\b"),
    "email": (r"\be[-\s]?mail\b",),
    "phone": (r"\bphone\b", r"\bmobile\b", r"\btelephone\b"),
    "linkedin": (r"\blinkedin\b",),
    "github": (r"\bgithub\b",),
    "portfolio": (r"\bportfolio\b", r"\bpersonal\s+(?:site|website)\b"),
    "city": (r"\bcurrent\s+city\b", r"^city$"),
    "state": (r"\bstate\b", r"\bprovince\b"),
    "country": (r"\bcountry\b",),
    "postal_code": (r"\bpostal\b", r"\bzip\s*code\b"),
    "degree": (r"\bdegree\b", r"\beducation\s+level\b"),
    "institution": (r"\buniversity\b", r"\bcollege\b", r"\binstitution\b"),
    "years_experience": (r"\byears?\s+(?:of\s+)?experience\b",),
    "notice_period": (r"\bnotice\s+period\b",),
}

def classify_semantic(label: str, meta: str = "", portal_hints: list[str] | None = None) -> str:
    text = f"{label} {meta}".lower()
    for semantic, patterns in SEMANTICS.items():
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            return semantic
    for hint in portal_hints or []:
        if hint in SEMANTICS:
            return hint
    return "unknown"

def is_sensitive(label: str, meta: str = "") -> bool:
    return bool(re.search(r"sponsor|visa|authorization|authorized|citizenship|salary|compensation|gender|ethnicity|race|disability|veteran|criminal|conviction", f"{label} {meta}", re.I))

def build_field_spec(item: dict) -> FieldSpec:
    semantic = classify_semantic(item.get("label", ""), item.get("meta", ""), item.get("portal_hints", []))
    return FieldSpec(key=item.get("key", ""), kind=item.get("kind", "text"), label=item.get("label", ""),
        meta=item.get("meta", ""), required=bool(item.get("required")),
        sensitive=is_sensitive(item.get("label", ""), item.get("meta", "")),
        semantic=semantic, options=tuple(item.get("options", [])), filled=bool(item.get("filled")))

def answer_from_profile(spec: FieldSpec, profile: Any) -> str | None:
    if profile is None or spec.sensitive:
        return None
    p, o = profile.personal, profile.online_profiles
    values = {
        "first_name": p.first_name, "last_name": p.last_name, "full_name": p.full_name,
        "email": p.email, "phone": p.phone, "linkedin": o.linkedin, "github": o.github,
        "portfolio": o.portfolio, "city": p.city, "state": p.state, "country": p.country,
        "postal_code": p.postal_code,
        "years_experience": f"{profile.years_of_experience:g}" if profile.years_of_experience is not None else None,
        "notice_period": profile.ats_defaults.notice_period,
        "degree": profile.education[0].degree if profile.education else None,
        "institution": profile.education[0].institution if profile.education else None,
    }
    answer = values.get(spec.semantic)
    if answer is not None and str(answer).strip():
        return str(answer).strip()
    return profile.custom_answers.get(re.sub(r"[^a-z0-9]+", " ", spec.label.lower()).strip())

def plan_fields(items: list[dict], profile: Any) -> list[dict]:
    result = []
    for item in items:
        spec = build_field_spec(item)
        answer = answer_from_profile(spec, profile)
        result.append({**spec.to_dict(), "answer": answer, "action": "review" if spec.sensitive or answer is None else "fill"})
    return result
