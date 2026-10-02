from dataclasses import dataclass


@dataclass(frozen=True)
class ResumeChoice:
    profile_id: str
    score: float
    reasons: tuple[str, ...]


def choose_profile_for_job(profiles: list[dict], job: dict) -> list[ResumeChoice]:
    """Rank saved profiles/resume variants without changing candidate facts."""
    title = f"{job.get('title', '')} {job.get('description', '')}".lower()
    required = set(str(job.get("required_skills", "")).lower().split())

    choices = []
    for record in profiles:
        profile = record.get("profile", record)
        skills = {str(skill).lower() for skill in profile.get("skills", [])}
        score = 0.0
        reasons = []

        overlap = sorted(skills & required)
        if overlap:
            score += min(len(overlap) / max(len(required), 1), 1.0) * 0.65
            reasons.append(f"skills: {', '.join(overlap[:8])}")

        years = profile.get("years_of_experience")
        if years is not None:
            score += min(float(years) / 5.0, 1.0) * 0.20
            reasons.append(f"{years:g} years recorded")

        education = profile.get("education", [])
        if education:
            score += 0.10
            reasons.append("education profile available")

        if record.get("original_name"):
            score += 0.05
            reasons.append("resume file available")

        choices.append(ResumeChoice(
            profile_id=record.get("id", ""),
            score=min(score, 1.0),
            reasons=tuple(reasons),
        ))

    return sorted(choices, key=lambda item: (-item.score, item.profile_id))
