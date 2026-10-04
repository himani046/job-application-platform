import json
import os
from pathlib import Path

import requests
import streamlit as st

from backend.common_answers import (
    COMMON_QUESTIONS,
    common_answer_for_key,
    normalize_common_question,
    save_common_answer,
)
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

API_TOKEN = os.getenv("LOCAL_API_TOKEN", "")

PORTALS = {
    "linkedin": "LinkedIn",
    "naukri": "Naukri",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "workday": "Workday",
    "custom": "Custom ATS",
}

WORKPLACES = {
    "any": "Any",
    "onsite": "On-site",
    "remote": "Remote",
    "hybrid": "Hybrid",
}

st.set_page_config(
    page_title="Job Application Platform",
    page_icon="💼",
    layout="wide",
)

def api(
    method: str,
    path: str,
    *,
    raw: bool = False,
    timeout: int = 30,
    **kwargs,
):
    try:
        response = requests.request(
            method,
            API_BASE_URL + path,
            headers={"X-API-Token": API_TOKEN},
            timeout=timeout,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Backend connection failed: {exc}"
        ) from exc

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text

        if not isinstance(detail, str):
            detail = json.dumps(detail, indent=2)

        raise RuntimeError(
            f"HTTP {response.status_code}: {detail}"
        )

    return response.content if raw else response.json()

def send_command(
    run_id: str,
    pending: dict | None,
    action: str,
    **extra,
):
    return api(
        "POST",
        f"/runs/{run_id}/commands",
        json={
            "action": action,
            "pause_token": pending["token"] if pending else None,
            **extra,
        },
    )

def launch_run(body: dict):
    run = api("POST", "/runs", json=body)
    st.session_state["run_id"] = run["id"]
    st.rerun()

def command_button(
    run_id: str,
    pending: dict,
    action: str,
    label: str,
    *,
    disabled: bool = False,
    primary: bool = False,
    **extra,
):
    clicked = st.button(
        label,
        key=f"{action}-{pending['token']}",
        disabled=disabled,
        type="primary" if primary else "secondary",
    )

    if clicked:
        try:
            send_command(
                run_id,
                pending,
                action,
                **extra,
            )
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))

@st.fragment(run_every="2s")
def live_console():
    run_id = st.session_state.get("run_id")

    if not run_id:
        st.info("Start a session, discovery, or application run.")
        return

    try:
        run = api("GET", f"/runs/{run_id}")
    except RuntimeError as exc:
        st.error(str(exc))
        return

    request = run["request"]

    st.subheader("Live browser console")
    st.write(
        f"**Run:** `{run['id']}`  \n"
        f"**Status:** `{run['status']}`  \n"
        f"**Mode:** `{request['mode']}`"
    )

    if request["mode"] == "discover":
        st.write(
            f"**Search location:** "
            f"{request.get('search_location') or 'Not specified'}  \n"
            f"**Workplace:** "
            f"{WORKPLACES.get(request.get('workplace_type', 'any'), 'Any')}"
        )

    active = run["status"] in {"queued", "running", "waiting"}

    if active and st.button(
        "Stop run",
        key=f"stop-{run_id}",
    ):
        try:
            send_command(run_id, run["pending"], "stop")
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))

    pending = run["pending"]

    if pending and not pending.get("claimed"):
        st.warning(pending["message"])

        if pending.get("url"):
            st.code(pending["url"], language=None)

        for error in pending.get("errors", []):
            st.error(error)

        allowed = pending["allowed"]
        token = pending["token"]

        reason = pending.get("reason", "human_review")
        browser_only = reason in {
            "login",
            "challenge",
            "navigation",
            "upload",
            "widget",
        }

        if browser_only:
            st.warning(
                "This step requires a browser action. Answerable application "
                "questions should be handled here in the frontend."
            )
        else:
            st.error(
                "🔴 Action required — answer this application step here. "
                "The browser is paused until you respond."
            )

        if pending.get("category"):
            st.caption(f"Category: {pending['category']}")

        if pending.get("current_value"):
            st.caption(
                f"Current value detected in the form: {pending['current_value']}"
            )

        if pending.get("required") is not None:
            st.caption(
                "Required field" if pending["required"] else "Optional field"
            )

        if pending.get("explanation"):
            st.info(pending["explanation"])

        if "answer_batch" == pending.get("reason") and "answer" in allowed:
            batch_questions = pending.get("batch_questions", [])

            if batch_questions:
                st.subheader(
                    f"Answer {len(batch_questions)} application questions"
                )
                st.caption(
                    "Review the proposed answers below. All required questions "
                    "must have a selection before the answers are submitted."
                )

                batch_answers = {}
                batch_remember = {}

                with st.form(f"batch-answer-form-{token}"):
                    for index, question in enumerate(batch_questions):
                        options = [
                            str(option).strip()
                            for option in question.get("options", [])
                            if str(option).strip()
                        ]
                        suggestion = str(question.get("suggestion") or "").strip()

                        if options:
                            if suggestion in options:
                                default_index = options.index(suggestion)
                            else:
                                default_index = None

                            batch_answers[question["id"]] = st.radio(
                                question.get("question", "Answer"),
                                options=options,
                                index=default_index,
                                key=f"batch-choice-{token}-{index}",
                            )
                        else:
                            batch_answers[question["id"]] = st.text_input(
                                question.get("question", "Answer"),
                                value=suggestion,
                                key=f"batch-text-{token}-{index}",
                            )

                        batch_remember[question["id"]] = st.checkbox(
                            "Remember this answer for this resume profile",
                            key=f"batch-remember-{token}-{index}",
                        )

                    submitted = st.form_submit_button(
                        "Submit all answers & resume",
                        type="primary",
                    )

                if submitted:
                    missing = [
                        question["question"]
                        for question in batch_questions
                        if question.get("required")
                        and not str(batch_answers.get(question["id"], "")).strip()
                    ]

                    if missing:
                        st.error(
                            "Please answer all required questions before continuing."
                        )
                    else:
                        try:
                            send_command(
                                run_id,
                                pending,
                                "answer",
                                answer=json.dumps(
                                    {
                                        "answers": batch_answers,
                                        "remember": batch_remember,
                                    }
                                ),
                            )
                            st.rerun()
                        except RuntimeError as exc:
                            st.error(str(exc))

            return

        if "answer" in allowed:
            options = [
                option for option in pending.get("options", [])
                if str(option).strip()
            ]

            if options:
                question = pending.get("question", "Answer")
                normalized = {
                    str(option).strip().lower()
                    for option in options
                }

                if normalized.issubset({"yes", "no"}) or len(options) <= 6:
                    suggestion = pending.get("suggestion", "")
                    answer = st.radio(
                        question,
                        options=options,
                        index=(
                            options.index(suggestion)
                            if suggestion in options
                            else None
                        ),
                        key=f"answer-choice-{token}",
                    )
                else:
                    answer = st.selectbox(
                        question,
                        options=options,
                        index=(
                            options.index(pending["suggestion"])
                            if pending.get("suggestion") in options
                            else 0
                        ),
                        key=f"answer-choice-{token}",
                    )
            else:
                answer = st.text_area(
                    pending.get("question", "Answer"),
                    value=pending.get("suggestion", ""),
                    key=f"answer-text-{token}",
                    height=140,
                )

            remember = st.checkbox(
                "Remember this answer for this resume profile",
                key=f"remember-{token}",
                help=(
                    "The answer is saved only to the selected resume profile "
                    "and can be reused on future applications."
                ),
            )

            command_button(
                run_id,
                pending,
                "answer",
                "Submit answer & resume browser",
                primary=True,
                answer=answer,
                remember=remember,
            )

        if "resume" in allowed:
            command_button(
                run_id,
                pending,
                "resume",
                "Resume / re-check",
            )

        if "skip" in allowed:
            command_button(
                run_id,
                pending,
                "skip",
                "Skip optional field",
            )

        if "approve" in allowed:
            acknowledged = st.checkbox(
                "I reviewed this action and authorize it, including "
                "submission if this button sends an application.",
                key=f"acknowledge-{token}",
            )

            command_button(
                run_id,
                pending,
                "approve",
                "Approve browser click",
                disabled=not acknowledged,
                primary=True,
            )

        if "mark_submitted" in allowed:
            verified = st.checkbox(
                "I personally verified a successful submission or receipt.",
                key=f"verified-{token}",
            )

            command_button(
                run_id,
                pending,
                "mark_submitted",
                "Mark submitted",
                disabled=not verified,
            )

    elif pending:
        st.info("Your response is being processed.")

    if run["results"]:
        st.subheader("Discovered jobs")

        st.dataframe(
            run["results"],
            use_container_width=True,
            hide_index=True,
            column_config={
                "url": st.column_config.LinkColumn("Job URL"),
            },
        )

        selected = st.selectbox(
            "Choose one job to prepare",
            options=range(len(run["results"])),
            format_func=lambda index: run["results"][index]["title"],
            key=f"job-choice-{run_id}",
        )

        profile_id = st.session_state.get("selected_profile_id")

        if st.button(
            "Prepare selected application",
            key=f"prepare-{run_id}",
            disabled=not profile_id or active,
        ):
            try:
                launch_run(
                    {
                        "mode": "apply",
                        "portal": request["portal"],
                        "profile_id": profile_id,
                        "job_url": run["results"][selected]["url"],
                        "keywords": "",
                        "search_location": "",
                        "workplace_type": "any",
                        "headless": False,
                    }
                )
            except RuntimeError as exc:
                st.error(str(exc))

    log_lines = [
        f"{entry['time'][11:19]} "
        f"{entry['level'].upper():7} "
        f"{entry['message']}"
        for entry in run["logs"]
    ]

    with st.container(height=380, border=True):
        st.code(
            "\n".join(log_lines) or "Waiting for logs...",
            language=None,
        )

st.title("💼 Job Application Platform")
st.caption(
    "Reviewed profiles • Explicit search locations • "
    "Human-approved application submissions"
)

if not API_TOKEN:
    st.error("Configure LOCAL_API_TOKEN in the project-root .env.")
    st.stop()

try:
    profiles = api("GET", "/profiles")
except RuntimeError as exc:
    st.error(str(exc))
    st.info("Start the backend and check the API token.")
    st.stop()

profile_tab, automation_tab = st.tabs(
    ["Resume & profile", "Browser automation"]
)

with profile_tab:
    st.subheader("Upload a resume")

    st.info(
        "The browser parser sends resume pages or documents to the "
        "ChatGPT website. Original files and parsed profiles are also "
        "stored locally. Review extracted information before applying."
    )

    uploaded = st.file_uploader(
        "PDF or DOCX resume",
        type=["pdf", "docx"],
    )

    if st.button(
        "Upload and parse",
        disabled=uploaded is None,
        type="primary",
    ):
        try:
            with st.spinner(
                "Processing the resume through the browser parser..."
            ):
                record = api(
                    "POST",
                    "/profiles/upload",
                    files={
                        "file": (
                            uploaded.name,
                            uploaded.getvalue(),
                            uploaded.type or "application/octet-stream",
                        )
                    },
                    timeout=1800,
                )

            st.session_state["selected_profile_id"] = record["id"]
            st.rerun()

        except RuntimeError as exc:
            st.error(str(exc))

    st.divider()

    if profiles:
        ids = [profile["id"] for profile in profiles]
        by_id = {
            profile["id"]: profile
            for profile in profiles
        }

        if st.session_state.get("selected_profile_id") not in ids:
            st.session_state["selected_profile_id"] = ids[0]

        selected_profile_id = st.selectbox(
            "Saved resume",
            options=ids,
            format_func=lambda value: (
                f"{by_id[value]['full_name'] or 'Unnamed profile'} — "
                f"{by_id[value]['original_name']} — {value[:8]}"
            ),
            key="selected_profile_id",
        )

        try:
            record = api(
                "GET",
                f"/profiles/{selected_profile_id}",
            )
        except RuntimeError as exc:
            st.error(str(exc))
            st.stop()

        editor_key = f"profile-editor-{selected_profile_id}"
        personal = record["profile"]["personal"]

        st.subheader("Candidate home location")
        st.caption(
            "Used for application fields. This does not set your job-search "
            "location, work authorization, or sponsorship requirements."
        )

        with st.form(
            f"home-location-form-{selected_profile_id}"
        ):
            location = st.text_input(
                "Full location",
                value=personal.get("location", ""),
                placeholder="Indore, Madhya Pradesh, India",
            )

            city_column, state_column = st.columns(2)

            city = city_column.text_input(
                "City",
                value=personal.get("city", ""),
            )

            state = state_column.text_input(
                "State / province",
                value=personal.get("state", ""),
            )

            country_column, postal_column = st.columns(2)

            country = country_column.text_input(
                "Country",
                value=personal.get("country", ""),
                placeholder="India",
            )

            postal_code = postal_column.text_input(
                "Postal code",
                value=personal.get("postal_code", ""),
            )

            save_home_location = st.form_submit_button(
                "Save candidate location"
            )

        if save_home_location:
            try:
                # Fetch the latest profile to preserve other saved fields.
                latest = api(
                    "GET",
                    f"/profiles/{selected_profile_id}",
                )["profile"]

                latest["personal"].update(
                    {
                        "location": location.strip(),
                        "city": city.strip(),
                        "state": state.strip(),
                        "country": country.strip(),
                        "postal_code": postal_code.strip(),
                    }
                )

                api(
                    "PUT",
                    f"/profiles/{selected_profile_id}",
                    json=latest,
                )

                st.session_state.pop(editor_key, None)
                st.rerun()

            except RuntimeError as exc:
                st.error(str(exc))

        st.subheader("Common Application Answers")
        st.caption(
            "Save repetitive application answers once for this resume profile. "
            "Future question wording can reuse the saved answer automatically."
        )

        custom_answers = record["profile"].get("custom_answers", {})

        rows = []
        for common in COMMON_QUESTIONS:
            saved = common_answer_for_key(common.key, custom_answers)
            if not saved and common.key == "total_experience":
                years = record["profile"].get("years_of_experience")
                saved = f"{years:g} years" if years is not None else ""
            elif not saved and common.key == "current_location":
                saved = personal.get("location", "")
            elif not saved and common.key == "notice_period":
                saved = record["profile"].get("ats_defaults", {}).get("notice_period") or ""

            rows.append(
                {
                    "Category": common.category,
                    "Question": common.label,
                    "Answer": saved or "Not saved",
                }
            )

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Question": st.column_config.TextColumn(width="large"),
                "Answer": st.column_config.TextColumn(width="large"),
            },
        )

        common_options = {
            common.key: f"[{common.category}] {common.label}"
            for common in COMMON_QUESTIONS
        }

        selected_common_key = st.selectbox(
            "Choose a common question to edit",
            options=list(common_options),
            format_func=lambda key: common_options[key],
            key=f"common-question-{selected_profile_id}",
        )

        selected_common = next(
            item for item in COMMON_QUESTIONS
            if item.key == selected_common_key
        )

        existing_common_answer = common_answer_for_key(
            selected_common_key,
            custom_answers,
        )

        with st.form(f"common-answer-form-{selected_profile_id}"):
            if selected_common.input_type == "yes_no":
                choices = ["", "Yes", "No"]
                current_choice = (
                    existing_common_answer
                    if existing_common_answer in {"Yes", "No"}
                    else ""
                )
                answer_index = choices.index(current_choice)

                common_answer = st.radio(
                    selected_common.label,
                    options=choices,
                    index=answer_index,
                    horizontal=True,
                    format_func=lambda value: value or "Not saved",
                )
            else:
                common_answer = st.text_input(
                    selected_common.label,
                    value=existing_common_answer,
                    placeholder="Enter the reusable answer...",
                )

            save_common = st.form_submit_button(
                "Save common answer",
                type="primary",
            )

        if save_common:
            latest = api(
                "GET",
                f"/profiles/{selected_profile_id}",
            )["profile"]

            save_common_answer(
                latest.setdefault("custom_answers", {}),
                selected_common_key,
                common_answer,
            )

            api(
                "PUT",
                f"/profiles/{selected_profile_id}",
                json=latest,
            )

            st.success(
                f"Saved reusable answer for: {selected_common.label}"
            )
            st.rerun()

        with st.expander("Add a custom repetitive question"):
            st.caption(
                "Use this for a question not covered by the common library. "
                "The exact question wording will be remembered for this profile."
            )

            with st.form(f"custom-common-answer-{selected_profile_id}"):
                custom_question = st.text_input(
                    "Question",
                    placeholder="e.g. Are you willing to work night shifts?",
                )
                custom_answer = st.text_input(
                    "Answer",
                    placeholder="Yes",
                )
                save_custom = st.form_submit_button("Save custom answer")

            if save_custom:
                if not custom_question.strip():
                    st.error("Enter a question.")
                elif not custom_answer.strip():
                    st.error("Enter an answer.")
                else:
                    latest = api(
                        "GET",
                        f"/profiles/{selected_profile_id}",
                    )["profile"]
                    latest.setdefault("custom_answers", {})[
                        normalize_common_question(custom_question)
                    ] = custom_answer.strip()

                    api(
                        "PUT",
                        f"/profiles/{selected_profile_id}",
                        json=latest,
                    )

                    st.success("Saved custom reusable question and answer.")
                    st.rerun()

        st.divider()

        left, right = st.columns([2, 1])

        with left:
            st.subheader("Complete profile JSON")

            st.caption(
                "Save one editor at a time. Saving candidate location "
                "reloads this JSON editor and discards its unsaved edits."
            )

            edited_json = st.text_area(
                "Profile JSON",
                value=json.dumps(
                    record["profile"],
                    indent=2,
                    ensure_ascii=False,
                ),
                height=600,
                key=editor_key,
            )

            if st.button(
                "Validate and save profile",
                type="primary",
            ):
                try:
                    parsed = json.loads(edited_json)

                    api(
                        "PUT",
                        f"/profiles/{selected_profile_id}",
                        json=parsed,
                    )

                    st.rerun()

                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))

            if st.button("Reload editor from saved profile"):
                st.session_state.pop(editor_key, None)
                st.rerun()

        with right:
            st.subheader("Saved profile")
            st.json(record["profile"], expanded=False)

            try:
                resume_bytes = api(
                    "GET",
                    f"/profiles/{selected_profile_id}/resume",
                    raw=True,
                )

                st.download_button(
                    "Download original resume",
                    data=resume_bytes,
                    file_name=record["original_name"],
                )

            except RuntimeError as exc:
                st.error(str(exc))

            delete_confirmed = st.checkbox(
                "Confirm deletion of this profile and resume"
            )

            if st.button(
                "Delete profile and file",
                disabled=not delete_confirmed,
            ):
                try:
                    api(
                        "DELETE",
                        f"/profiles/{selected_profile_id}",
                    )

                    st.session_state.pop(editor_key, None)
                    st.session_state.pop("selected_profile_id", None)
                    st.rerun()

                except RuntimeError as exc:
                    st.error(str(exc))

    else:
        st.info("Upload a resume to create a profile.")

with automation_tab:
    st.subheader("Browser run configuration")

    portal = st.selectbox(
        "Portal",
        options=list(PORTALS),
        format_func=lambda value: PORTALS[value],
    )

    mode_label = st.radio(
        "Action",
        [
            "Set up / refresh login session",
            "Discover jobs",
            "Prepare one application",
        ],
        horizontal=True,
    )

    mode = {
        "Set up / refresh login session": "login",
        "Discover jobs": "discover",
        "Prepare one application": "apply",
    }[mode_label]

    job_url = st.text_input(
        (
            "Job URL"
            if mode == "apply"
            else "Careers-board / search URL"
            if mode == "discover"
            else "Job URL, careers-board URL, or login URL"
        ),
        key=f"automation-job-url-{mode}",
        help=(
            "Application mode requires a specific job URL. "
            "ATS discovery requires the employer's careers-board URL. "
            "For LinkedIn discovery, leave empty or provide a LinkedIn "
            "jobs/search URL."
        ),
    ).strip()

    keywords = st.text_input(
        "Search keywords",
        disabled=mode != "discover",
        placeholder="AJO or Adobe Experience Platform",
    ).strip()

    search_location = ""
    workplace_type = "any"

    if mode == "discover":
        search_location = st.text_input(
            "Job search location",
            value="India",
            key="job_search_location",
            placeholder="India or Bengaluru, Karnataka, India",
            help=(
                "Where you want to find jobs. This is separate from "
                "your candidate home location."
            ),
        ).strip()

        workplace_type = st.selectbox(
            "Workplace type",
            options=list(WORKPLACES),
            format_func=lambda value: WORKPLACES[value],
            key="job_search_workplace",
        )

        if portal == "linkedin":
            st.info(
                "Your selected location overrides location parameters in "
                "a pasted LinkedIn search URL. The browser will request "
                "these filters, then pause for you to verify them."
            )
        else:
            st.info(
                "This portal's location controls vary. The browser will "
                "pause so you can apply and confirm the requested filters "
                "before links are collected."
            )

    priority = st.slider(
        "Queue priority",
        min_value=1,
        max_value=1000,
        value=100,
        help="Lower values run earlier. Priority only affects queued work.",
    )

    scheduled_at = st.text_input(
        "Schedule for later (optional ISO-8601)",
        placeholder="2026-10-02T15:30:00+05:30",
        help="Leave blank to queue immediately. Scheduled runs remain queued until their time.",
    ).strip() or None

    headless = st.checkbox(
        "Run headless",
        value=False,
        disabled=mode in {"login", "discover"},
        help=(
            "Discovery uses a visible browser for location verification. "
            "Interactive login also requires headed mode."
        ),
    )

    if mode in {"login", "discover"}:
        headless = False

    profile_id = st.session_state.get("selected_profile_id")

    if profile_id:
        st.caption(f"Application profile: {profile_id}")
    elif mode == "apply":
        st.warning("Upload and save a profile before applying.")

    st.warning(
        "Portal restrictions still apply. The platform does not bypass "
        "authentication or CAPTCHAs. Remote jobs may still have country "
        "or work-authorization restrictions."
    )

    invalid_configuration = (
        (mode == "apply" and not profile_id)
        or (mode == "discover" and not search_location)
    )

    if st.button(
        "Start browser run",
        type="primary",
        disabled=invalid_configuration,
    ):
        try:
            launch_run(
                {
                    "mode": mode,
                    "portal": portal,
                    "profile_id": profile_id,
                    "job_url": job_url or None,
                    "keywords": keywords if mode == "discover" else "",
                    "search_location": search_location,
                    "workplace_type": workplace_type,
                    "headless": headless,
                    "priority": priority,
                    "scheduled_at": scheduled_at,
                }
            )
        except RuntimeError as exc:
            st.error(str(exc))

    with st.expander("Reconnect to an existing run"):
        try:
            response = api("GET", "/runs")
            previous_runs = response["runs"]

            if previous_runs:
                lookup = {
                    run["id"]: run
                    for run in previous_runs
                }

                reconnect_id = st.selectbox(
                    "Run",
                    options=list(lookup),
                    format_func=lambda value: (
                        f"{value[:8]} — "
                        f"{lookup[value]['request']['mode']} — "
                        f"{lookup[value]['status']}"
                    ),
                )

                if st.button("Show selected run"):
                    st.session_state["run_id"] = reconnect_id
                    st.rerun()

            else:
                st.caption("No runs exist in this backend process.")

        except RuntimeError as exc:
            st.error(str(exc))

    st.divider()
    live_console()

    st.divider()
    st.subheader("Operations")
    try:
        operations = api("GET", "/queue")
        q = operations["queue"]
        s = operations["scheduler"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Queued", q["queued"])
        metric_cols[1].metric("Workers", q["running_workers"])
        metric_cols[2].metric("Scheduled", s["scheduled"])
        metric_cols[3].metric("Active portals", len(operations["active_portals"]))
    except RuntimeError as exc:
        st.caption(f"Queue status unavailable: {exc}")

    st.divider()
    history_tab, jobs_tab, matches_tab = st.tabs(
        ["Application history", "Saved jobs", "Profile matches"]
    )

    with history_tab:
        try:
            application_records = api("GET", "/applications")
            if application_records:
                st.dataframe(
                    application_records,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "job_url": st.column_config.LinkColumn("Job URL")
                    },
                )
            else:
                st.info("No application records yet.")

            if application_records:
                try:
                    analytics = api("GET", "/analytics/applications")
                    metric_cols = st.columns(4)
                    metric_cols[0].metric("Applications", analytics["total"])
                    metric_cols[1].metric("Submitted", analytics["submitted"])
                    metric_cols[2].metric("Submission rate", f"{analytics['submission_rate']:.0%}")
                    metric_cols[3].metric("Avg. lifecycle", f"{analytics['average_lifecycle_seconds'] / 60:.1f} min")
                    st.caption("Status breakdown: " + ", ".join(f"{key}: {value}" for key, value in analytics["by_status"].items()))
                except RuntimeError as exc:
                    st.caption(f"Analytics unavailable: {exc}")

                st.markdown("#### Application review state")
                application_choices = {
                    f"{item.get('title') or 'Untitled job'} — {item.get('status', 'unknown')} — {item['id'][:8]}": item
                    for item in application_records
                }
                selected_application_label = st.selectbox(
                    "Application",
                    options=list(application_choices),
                    key="application-review-choice",
                )
                selected_application = application_choices[selected_application_label]
                review_fields = selected_application.get("review_fields", [])
                if review_fields:
                    rows = []
                    for field in review_fields:
                        rows.append({
                            "Field": field.get("label", ""),
                            "Category": field.get("category", ""),
                            "Required": "Yes" if field.get("required") else "No",
                            "Filled": "Yes" if field.get("filled") else "No",
                            "Review": "NEEDS REVIEW" if field.get("review_required") else "Ready",
                        })
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                if selected_application.get("missing_fields"):
                    st.error("Missing required information: " + ", ".join(selected_application["missing_fields"]))
                if selected_application.get("sensitive_fields"):
                    st.warning("Sensitive fields require explicit review: " + ", ".join(selected_application["sensitive_fields"]))
                if selected_application.get("validation_errors"):
                    st.error("Validation errors: " + " | ".join(selected_application["validation_errors"]))
                if selected_application.get("human_approved"):
                    st.success("Human approval recorded for the final submission action.")

                if selected_application.get("status") == "submission_uncertain":
                    st.warning(
                        "This application needs your decision. Verify LinkedIn before choosing an action."
                    )

                    action_col1, action_col2 = st.columns(2)

                    with action_col1:
                        if st.button(
                            "✅ Applied",
                            key=f"mark-applied-{selected_application['id']}",
                            type="primary",
                        ):
                            try:
                                api(
                                    "POST",
                                    f"/applications/{selected_application['id']}/resolve",
                                    json={
                                        "action": "submitted",
                                        "confirmation_text": "Marked Applied from Application History after candidate verification.",
                                    },
                                )
                                st.success("Application marked as Applied.")
                                st.rerun()
                            except RuntimeError as exc:
                                st.error(str(exc))

                    with action_col2:
                        if st.button(
                            "❌ Cancel application",
                            key=f"cancel-application-{selected_application['id']}",
                        ):
                            try:
                                api(
                                    "POST",
                                    f"/applications/{selected_application['id']}/resolve",
                                    json={"action": "cancelled"},
                                )
                                st.success(
                                    "Application cancelled. It will not be replayed automatically."
                                )
                                st.rerun()
                            except RuntimeError as exc:
                                st.error(str(exc))
        except RuntimeError as exc:
            st.warning(f"Application history unavailable: {exc}")

    with jobs_tab:
        try:
            saved_jobs = api("GET", "/jobs")
            if saved_jobs:
                st.dataframe(
                    saved_jobs,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "url": st.column_config.LinkColumn("Job URL")
                    },
                )
            else:
                st.info(
                    "No saved jobs yet. Run a discovery session to populate "
                    "the reusable job library."
                )
        except RuntimeError as exc:
            st.warning(f"Saved job library unavailable: {exc}")

    with matches_tab:
        selected_profile = st.session_state.get("selected_profile_id")
        if not selected_profile:
            st.info("Select a saved profile to calculate job matches.")
        else:
            if st.button("Refresh profile matches", key="refresh-matches"):
                try:
                    matches = api(
                        "POST",
                        "/jobs/match",
                        json={
                            "profile_id": selected_profile,
                            "limit": 50,
                        },
                    )
                    if matches:
                        rows = []
                        for item in matches:
                            job = item["job"]
                            match = item["match"]
                            rows.append(
                                {
                                    "score": f"{match['score']:.0%}",
                                    "title": job["title"],
                                    "company": job["company"],
                                    "location": job["location"],
                                    "matched_keywords": ", ".join(
                                        match["matched_skills"][:10]
                                    ),
                                    "job_url": job["url"],
                                }
                            )
                        st.dataframe(
                            rows,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "job_url": st.column_config.LinkColumn(
                                    "Job URL"
                                )
                            },
                        )
                    else:
                        st.info("No saved jobs available for matching.")
                except RuntimeError as exc:
                    st.warning(f"Matching unavailable: {exc}")

            st.markdown("#### Application intelligence")
            st.caption(
                "Inspect the requirements and profile facts before preparing an application. "
                "The planner never invents qualifications or legal answers."
            )
            try:
                saved_jobs = api("GET", "/jobs")
                if saved_jobs:
                    job_lookup = {
                        f"{job.get('title') or 'Untitled'} — {job.get('company') or 'Unknown'} — {job['id'][:8]}": job
                        for job in saved_jobs
                    }
                    chosen_label = st.selectbox(
                        "Job to analyze",
                        options=list(job_lookup),
                        key="planner-job",
                    )
                    chosen_job = job_lookup[chosen_label]
                    if st.button("Analyze application readiness", key="planner-analyze"):
                        plan = api(
                            "GET",
                            f"/jobs/{chosen_job['id']}/application-plan",
                            params={"profile_id": selected_profile},
                        )
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Matched skills", len(plan["matched_skills"]))
                        c2.metric("Missing skills", len(plan["missing_skills"]))
                        c3.metric(
                            "Experience requirement",
                            "Satisfied" if plan["experience_requirement_satisfied"] else "Review",
                        )
                        st.write("**Matched:**", ", ".join(plan["matched_skills"]) or "None detected")
                        st.write("**Missing:**", ", ".join(plan["missing_skills"]) or "None detected")
                        st.info("\n".join(plan["planning_notes"]))
            except RuntimeError as exc:
                st.warning(f"Application intelligence unavailable: {exc}")
