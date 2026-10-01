from enum import StrEnum


class ApplicationStatus(StrEnum):
    DISCOVERED = "discovered"
    MATCHED = "matched"
    QUEUED = "queued"
    OPENING = "opening"
    APPLICATION_STARTED = "application_started"
    FORM_ANALYSIS = "form_analysis"
    FILLING = "filling"
    REVIEW = "review"
    AWAITING_APPROVAL = "awaiting_approval"
    SUBMITTING = "submitting"
    VERIFYING = "verifying"
    SUBMITTED = "submitted"
    AUTH_REQUIRED = "auth_required"
    CAPTCHA_REQUIRED = "captcha_required"
    MISSING_INFORMATION = "missing_information"
    UNSUPPORTED_FORM = "unsupported_form"
    VALIDATION_ERROR = "validation_error"
    SUBMISSION_UNCERTAIN = "submission_uncertain"
    FAILED = "failed"
    STOPPED = "stopped"


ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DISCOVERED: {ApplicationStatus.MATCHED, ApplicationStatus.QUEUED},
    ApplicationStatus.MATCHED: {ApplicationStatus.QUEUED},
    ApplicationStatus.QUEUED: {ApplicationStatus.OPENING, ApplicationStatus.STOPPED},
    ApplicationStatus.OPENING: {ApplicationStatus.APPLICATION_STARTED, ApplicationStatus.AUTH_REQUIRED, ApplicationStatus.CAPTCHA_REQUIRED, ApplicationStatus.FAILED},
    ApplicationStatus.APPLICATION_STARTED: {ApplicationStatus.FORM_ANALYSIS, ApplicationStatus.FAILED},
    ApplicationStatus.FORM_ANALYSIS: {ApplicationStatus.FILLING, ApplicationStatus.UNSUPPORTED_FORM, ApplicationStatus.MISSING_INFORMATION},
    ApplicationStatus.FILLING: {ApplicationStatus.FILLING, ApplicationStatus.REVIEW, ApplicationStatus.VALIDATION_ERROR, ApplicationStatus.MISSING_INFORMATION},
    ApplicationStatus.VALIDATION_ERROR: {ApplicationStatus.FILLING, ApplicationStatus.REVIEW},
    ApplicationStatus.REVIEW: {ApplicationStatus.AWAITING_APPROVAL, ApplicationStatus.FILLING},
    ApplicationStatus.AWAITING_APPROVAL: {ApplicationStatus.SUBMITTING, ApplicationStatus.STOPPED},
    ApplicationStatus.SUBMITTING: {ApplicationStatus.VERIFYING, ApplicationStatus.SUBMISSION_UNCERTAIN},
    ApplicationStatus.VERIFYING: {ApplicationStatus.SUBMITTED, ApplicationStatus.SUBMISSION_UNCERTAIN},
    ApplicationStatus.SUBMISSION_UNCERTAIN: {ApplicationStatus.VERIFYING, ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED},
}


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(current: ApplicationStatus, target: ApplicationStatus) -> ApplicationStatus:
    if current == target:
        return current
    if not can_transition(current, target):
        raise ValueError(f"Invalid application transition: {current} -> {target}")
    return target
