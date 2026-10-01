import json
import os
from pathlib import Path

import requests
import streamlit as st
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

        if pending.get("explanation"):
            st.info(pending["explanation"])

        if pending.get("options"):
            st.write("Available choices:")
            st.code(
                "\n".join(pending["options"]),
                language=None,
            )

        if "answer" in allowed:
            answer = st.text_area(
                pending.get("question", "Answer"),
                value=pending.get("suggestion", ""),
                key=f"answer-text-{token}",
                height=140,
            )

            remember = st.checkbox(
                "Remember this exact question and approved answer",
                key=f"remember-{token}",
            )

            command_button(
                run_id,
                pending,
                "answer",
                "Use reviewed answer",
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
        "Job URL, careers-board URL, or login URL",
        help=(
            "Application mode requires a specific job URL. "
            "ATS discovery requires the employer's careers-board URL. "
            "For LinkedIn discovery, leave empty or provide a search URL."
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
