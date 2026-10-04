"""Reusable common application-question library."""

from dataclasses import dataclass
import re
from typing import Mapping


@dataclass(frozen=True)
class CommonQuestion:
    key: str
    label: str
    category: str
    input_type: str = "text"
    aliases: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()


COMMON_QUESTIONS = (
    CommonQuestion(
        "current_ctc", "Current CTC", "Compensation",
        aliases=(
            "Current salary",
            "Current CTC",
            "Present salary",
            "Present CTC",
            "Current compensation",
            "Current annual salary",
            "Current annual compensation",
            "Present compensation",
            "Last drawn salary",
            "Current package",
        ),
        patterns=(
            r"\bcurrent\s+(?:ctc|compensation|salary)\b",
            r"\b(?:present|existing)\s+(?:ctc|compensation|salary)\b",
        ),
    ),
    CommonQuestion(
        "expected_ctc", "Expected CTC", "Compensation",
        aliases=(
            "Expected salary",
            "Expected CTC",
            "Desired salary",
            "Desired CTC",
            "Expected compensation",
            "Expected annual salary",
            "Expected package",
            "Salary expectation",
        ),
        patterns=(
            r"\bexpected\s+(?:ctc|compensation|salary)\b",
            r"\bdesired\s+(?:ctc|compensation|salary)\b",
        ),
    ),
    CommonQuestion(
        "notice_period", "Notice period", "Availability",
        aliases=(
            "Notice",
            "Notice period",
            "Notice duration",
            "Serving notice period",
            "How long is your notice period",
        ),
        patterns=(
            r"\bnotice\s+period\b",
            r"\bnotice\s+duration\b",
        ),
    ),
    CommonQuestion(
        "last_working_day", "Last working day / Available date", "Availability",
        aliases=(
            "Last working date",
            "Last working day",
            "Available date",
            "Availability date",
            "Date available to join",
            "Earliest joining date",
            "Joining date",
        ),
        patterns=(
            r"\blast\s+working\s+day\b",
            r"\bavailable\s+(?:date|from|on)\b",
            r"\bearliest\s+(?:joining|start)\s+date\b",
            r"\bwhen\s+can\s+you\s+(?:join|start)\b",
        ),
    ),
    CommonQuestion(
        "current_location", "Current location", "Location",
        aliases=(
            "Location",
            "Current city",
            "Present location",
            "Current base location",
            "Where are you currently located",
        ),
        patterns=(
            r"\bcurrent\s+location\b",
            r"\bcurrent\s+city\b",
            r"\bwhere\s+(?:do|are)\s+you\s+(?:currently\s+)?located\b",
        ),
    ),
    CommonQuestion(
        "preferred_location", "Preferred location(s)", "Location",
        aliases=(
            "Preferred location",
            "Preferred locations",
            "Desired location",
            "Preferred work location",
            "Job location preference",
        ),
        patterns=(
            r"\bpreferred\s+(?:location|locations)\b",
            r"\bpreferred\s+(?:work|job)\s+location\b",
            r"\bwhich\s+(?:location|locations)\s+.*\bprefer\b",
        ),
    ),
    CommonQuestion(
        "office_location_willingness",
        "Comfortable working from the specified office?",
        "Work arrangement",
        "yes_no",
        aliases=(
            "Comfortable working from office",
            "Willing to work from office",
            "Comfortable working from the Bengaluru office",
            "Are you comfortable working from the office",
        ),
        patterns=(
            r"\bcomfortable\s+working\s+(?:from|in)\s+.+\boffice\b",
            r"\bwilling\s+to\s+work\s+(?:from|in)\s+.+\boffice\b",
            r"\bcan\s+you\s+work\s+(?:from|in)\s+.+\boffice\b",
        ),
    ),
    CommonQuestion(
        "remote_work", "Comfortable working remotely?", "Work arrangement", "yes_no",
        patterns=(
            r"\bcomfortable\s+working\s+remotely\b",
            r"\bcomfortable\s+(?:with|working)\s+remote\b",
        ),
    ),
    CommonQuestion(
        "hybrid_work", "Comfortable with hybrid work?", "Work arrangement", "yes_no",
        patterns=(
            r"\bcomfortable\s+(?:working\s+)?hybrid\b",
            r"\bwilling\s+to\s+work\s+in\s+a\s+hybrid\s+model\b",
        ),
    ),
    CommonQuestion(
        "relocate", "Willing to relocate?", "Work arrangement", "yes_no",
        patterns=(
            r"\bwilling\s+to\s+relocate\b",
            r"\bopen\s+to\s+relocat(?:e|ion)\b",
            r"\bcan\s+you\s+relocate\b",
        ),
    ),
    CommonQuestion(
        "total_experience", "Total years of IT experience", "Experience",
        aliases=(
            "Total experience",
            "Total years of experience",
            "Total IT experience",
            "Years of experience",
            "Experience in years",
        ),
        patterns=(
            r"\btotal\s+(?:years?\s+(?:of\s+)?(?:it\s+)?experience|it\s+experience)\b",
            r"\btotal\s+year\s+of\s+experience\b",
            r"\bexperience\s+in\s+years\b",
        ),
    ),
    CommonQuestion(
        "ajo_experience", "Adobe Journey Optimizer experience", "Adobe / AJO",
        "yes_no",
        patterns=(
            r"\b5\+?\s+years?.*\badobe\s+journey\s+optimizer\b",
            r"\bexperience\s+with\s+adobe\s+journey\s+optimizer\b",
        ),
    ),
    CommonQuestion(
        "ajo_design_config", "AJO design/configuration experience", "Adobe / AJO", "yes_no",
        patterns=(
            r"\bdesigning\s+and\s+configuring\s+solutions\s+in\s+adobe\s+journey\s+optimizer\b",
        ),
    ),
    CommonQuestion(
        "ajo_implementation", "AJO implementation/customization/enhancement", "Adobe / AJO", "yes_no",
        patterns=(
            r"\badobe\s+journey\s+optimizer.*(?:implementation|customization|enhancement)\b",
        ),
    ),
    CommonQuestion(
        "adobe_campaign_classic", "Adobe Campaign Classic experience", "Adobe / AJO", "yes_no",
        patterns=(
            r"\bexperience\s+with\s+adobe\s+campaign\s+classic\b",
            r"\bworked\s+with\s+adobe\s+campaign\s+classic\b",
        ),
    ),
    CommonQuestion(
        "ajo_integrations", "AJO enterprise integration experience", "Adobe / AJO", "yes_no",
        patterns=(
            r"\bintegrating\s+adobe\s+journey\s+optimizer\s+with\s+other\s+enterprise\s+applications\b",
        ),
    ),
    CommonQuestion(
        "technical_lead", "Technical lead / SME experience", "Leadership", "yes_no",
        patterns=(
            r"\bworked\s+as\s+an\s+sme\b",
            r"\btechnical\s+lead\s+experience\b",
        ),
    ),
    CommonQuestion(
        "team_leadership", "Technical decisions / multiple-team coordination", "Leadership", "yes_no",
        patterns=(
            r"\bleading\s+technical\s+decisions\b",
            r"\bcoordinating\s+with\s+multiple\s+teams\b",
        ),
    ),
    CommonQuestion(
        "mentoring", "Mentoring junior team members", "Leadership", "yes_no",
        patterns=(
            r"\bmentoring\s+junior\s+team\s+members\b",
            r"\bmentor(?:ed|ing)\s+junior\b",
        ),
    ),
    CommonQuestion(
        "work_authorization", "Authorized to work?", "Work authorization", "yes_no",
        patterns=(
            r"\bauthorized\s+to\s+work\b",
            r"\bauthorised\s+to\s+work\b",
            r"\bwork\s+authorization\b",
        ),
    ),
    CommonQuestion(
        "visa_sponsorship", "Require visa sponsorship?", "Work authorization", "yes_no",
        patterns=(
            r"\bvisa\s+sponsorship\b",
            r"\brequire\s+.*sponsorship\b",
        ),
    ),
    CommonQuestion(
        "budget_fit", "Current / expected CTC within the stated budget?", "Compensation", "yes_no",
        patterns=(
            r"\b(?:current|expected)\s+(?:ctc|compensation|salary).*\bbudget\b",
            r"\bctc\b.*\bwithin\s+(?:the\s+)?budget\b",
        ),
    ),
    CommonQuestion(
        "shift_work", "Comfortable working shifts?", "Work arrangement", "yes_no",
        patterns=(
            r"\bcomfortable\s+working\s+(?:in\s+)?shifts?\b",
            r"\bwilling\s+to\s+work\s+(?:in\s+)?shifts?\b",
        ),
    ),
    CommonQuestion(
        "travel", "Willing to travel for work?", "Work arrangement", "yes_no",
        patterns=(
            r"\bwilling\s+to\s+travel\b",
            r"\bcomfortable\s+with\s+travel\s+for\s+work\b",
        ),
    ),
    CommonQuestion(
        "employment_type", "Preferred employment type", "Employment",
        patterns=(
            r"\bpreferred\s+(?:employment|job)\s+type\b",
            r"\bfull[- ]?time\s+(?:or|vs)\s+(?:part[- ]?time|contract)\b",
        ),
    ),
)


def normalize_common_question(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip(" *?:")


def get_common_question(key: str) -> CommonQuestion | None:
    for item in COMMON_QUESTIONS:
        if item.key == key:
            return item
    return None


def matches_common_question(
    question: str,
    item: CommonQuestion,
    extra_aliases: tuple[str, ...] = (),
) -> bool:
    normalized = normalize_common_question(question)

    if normalized == normalize_common_question(item.label):
        return True

    aliases = (*item.aliases, *extra_aliases)
    if any(normalized == normalize_common_question(alias) for alias in aliases):
        return True

    return any(
        re.search(pattern, normalized, re.I)
        for pattern in item.patterns
    )


def common_answer_for_question(
    question: str,
    custom_answers: Mapping[str, str] | None,
    common_aliases: Mapping[str, list[str]] | None = None,
) -> str | None:
    if not custom_answers:
        return None

    normalized = normalize_common_question(question)

    exact = custom_answers.get(normalized)
    if exact and str(exact).strip():
        return str(exact).strip()

    for item in COMMON_QUESTIONS:
        extra = tuple(
            common_aliases.get(item.key, ())
            if common_aliases
            else ()
        )

        if not matches_common_question(question, item, extra):
            continue

        canonical = normalize_common_question(item.label)
        answer = custom_answers.get(canonical) or custom_answers.get(item.key)
        if answer and str(answer).strip():
            return str(answer).strip()

    return None


def common_answer_for_key(
    key: str,
    custom_answers: Mapping[str, str] | None,
) -> str:
    item = get_common_question(key)
    if not item or not custom_answers:
        return ""

    canonical = normalize_common_question(item.label)
    return str(custom_answers.get(canonical) or custom_answers.get(key) or "").strip()


def save_common_answer(
    custom_answers: dict[str, str],
    key: str,
    answer: str,
) -> None:
    item = get_common_question(key)
    if not item:
        raise KeyError(key)

    canonical = normalize_common_question(item.label)

    for existing in list(custom_answers):
        if existing == canonical or matches_common_question(existing, item):
            custom_answers.pop(existing, None)

    if answer.strip():
        custom_answers[canonical] = answer.strip()


def save_common_alias(
    common_aliases: dict[str, list[str]],
    key: str,
    alias: str,
) -> None:
    item = get_common_question(key)
    cleaned = normalize_common_question(alias)

    if not item:
        raise KeyError(key)
    if not cleaned or cleaned == normalize_common_question(item.label):
        return

    bucket = common_aliases.setdefault(key, [])
    existing = {
        normalize_common_question(value)
        for value in bucket
    }

    if cleaned not in existing:
        bucket.append(alias.strip())
