from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonalDetails(StrictModel):
    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    postal_code: str = ""


class OnlineProfiles(StrictModel):
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""


class Employment(StrictModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str | None = None
    end_date: str | None = None
    current: bool = False
    achievements: list[str] = Field(default_factory=list)


class Education(StrictModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str | None = None
    end_date: str | None = None


class ATSDefaults(StrictModel):
    notice_period: str | None = None
    expected_salary_amount: float | None = Field(default=None, ge=0)
    salary_currency: str = ""
    salary_period: Literal["annual", "monthly", "hourly"] = "annual"
    work_authorized: bool | None = None
    requires_sponsorship: bool | None = None
    gender: str = "Prefer not to say"
    ethnicity: str = "Prefer not to say"
    disability: str = "Prefer not to say"
    veteran_status: str = "Prefer not to say"


class Profile(StrictModel):
    personal: PersonalDetails = Field(default_factory=PersonalDetails)
    online_profiles: OnlineProfiles = Field(default_factory=OnlineProfiles)
    work_history: list[Employment] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    years_of_experience: float | None = Field(default=None, ge=0)
    ats_defaults: ATSDefaults = Field(default_factory=ATSDefaults)
    custom_answers: dict[str, str] = Field(default_factory=dict)


class AnswerSuggestion(StrictModel):
    answer: str | None = None
    explanation: str


Portal = Literal[
    "linkedin",
    "naukri",
    "greenhouse",
    "lever",
    "workday",
    "custom",
]


class RunRequest(StrictModel):
    mode: Literal["login", "discover", "apply"]
    portal: Portal
    profile_id: str | None = None
    job_url: str | None = None
    keywords: str = ""
    search_location: str = Field(default="", max_length=200)
    workplace_type: Literal["any", "onsite", "remote", "hybrid"] = "any"
    headless: bool = False
    priority: int = Field(default=100, ge=1, le=1000)
    scheduled_at: str | None = None


class ResolveUncertainApplication(StrictModel):
    action: Literal["retry", "submitted"]
    confirmation_text: str | None = None


class RunCommand(StrictModel):
    action: Literal[
        "resume",
        "answer",
        "skip",
        "approve",
        "mark_submitted",
        "stop",
    ]
    pause_token: str | None = None
    answer: str | None = None
    remember: bool = False


class JobRecord(StrictModel):
    id: str
    portal: Portal
    title: str
    url: str
    company: str = ""
    location: str = ""
    description: str = ""
    discovered_at: str = ""
    metadata: dict = Field(default_factory=dict)


class JobMatchRequest(StrictModel):
    profile_id: str
    limit: int = Field(default=50, ge=1, le=200)


class ApplicationRecord(StrictModel):
    id: str
    profile_id: str
    job_id: str
    job_url: str
    portal: Portal
    title: str = ""
    company: str = ""
    status: str = "queued"
    resume_version: str | None = None
    run_id: str | None = None
    confirmation_text: str | None = None
    application_key: str | None = None
    created_at: str
    updated_at: str
    events: list[dict] = Field(default_factory=list)
    review_fields: list[dict] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    sensitive_fields: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    human_approved: bool = False
