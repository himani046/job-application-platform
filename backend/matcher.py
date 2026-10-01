import re
from dataclasses import dataclass

from backend.models import JobRecord, Profile


_STOPWORDS = {
    "and", "the", "for", "with", "from", "that", "this", "you", "your",
    "our", "are", "will", "have", "has", "into", "using", "use", "job",
    "role", "work", "years", "year", "experience", "required", "preferred",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9+#.]+", value.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _profile_tokens(profile: Profile) -> set[str]:
    values = list(profile.skills)
    values.extend(item.title for item in profile.work_history)
    values.extend(item.achievements for item in profile.work_history)
    values.extend(item.field_of_study for item in profile.education)
    return _tokens(" ".join(values))


def _required_years(text: str) -> float | None:
    patterns = (
        r"(?:minimum|at least|of)\s+(\d+(?:\.\d+)?)\+?\s+years",
        r"(\d+(?:\.\d+)?)\+?\s+years\s+(?:of\s+)?experience",
    )
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return float(match.group(1))
    return None


@dataclass(frozen=True)
class MatchResult:
    score: float
    matched_skills: list[str]
    missing_required_years: float | None
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "matched_skills": self.matched_skills,
            "missing_required_years": self.missing_required_years,
            "reasons": self.reasons,
        }


def match_job(profile: Profile, job: JobRecord) -> MatchResult:
    profile_tokens = _profile_tokens(profile)
    job_text = f"{job.title} {job.description}"
    job_tokens = _tokens(job_text)

    overlap = sorted(profile_tokens & job_tokens)
    title_tokens = _tokens(job.title)
    title_overlap = len(profile_tokens & title_tokens)

    # Skill relevance is intentionally explainable and deterministic.
    skill_score = min(len(overlap) / 12.0, 1.0)
    title_score = min(title_overlap / max(len(title_tokens), 1), 1.0)

    required_years = _required_years(job_text)
    missing_years = None
    experience_score = 1.0
    if required_years is not None:
        candidate_years = profile.years_of_experience
        if candidate_years is None:
            experience_score = 0.5
        elif candidate_years < required_years:
            missing_years = required_years - candidate_years
            experience_score = max(candidate_years / required_years, 0.0)

    score = 0.55 * skill_score + 0.30 * title_score + 0.15 * experience_score

    reasons = []
    if overlap:
        reasons.append(f"{len(overlap)} profile/job keywords overlap.")
    else:
        reasons.append("No meaningful profile/job keyword overlap detected.")

    if title_overlap:
        reasons.append(f"{title_overlap} title keywords match profile history.")
    if required_years is not None:
        if missing_years:
            reasons.append(
                f"Profile appears {missing_years:g} years below the detected requirement."
            )
        else:
            reasons.append("Detected experience requirement is covered by the profile.")

    return MatchResult(
        score=score,
        matched_skills=overlap[:30],
        missing_required_years=missing_years,
        reasons=reasons,
    )


def rank_jobs(profile: Profile, jobs: list[JobRecord], limit: int = 50) -> list[dict]:
    ranked = []
    for job in jobs:
        result = match_job(profile, job)
        ranked.append(
            {
                "job": job.model_dump(mode="json"),
                "match": result.as_dict(),
            }
        )

    ranked.sort(
        key=lambda item: item["match"]["score"],
        reverse=True,
    )
    return ranked[:limit]
