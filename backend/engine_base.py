import asyncio
import ipaddress
import re
import socket
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from playwright.async_api import (
    BrowserContext,
    Frame,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from backend.config import (
    BROWSER_DIR,
    ENABLE_STEALTH,
    HUMAN_TIMEOUT_SECONDS,
)
from backend.models import Profile, RunCommand, RunRequest
from backend.parser import suggest_answer
from backend.storage import normalize_question, remember_answer
from backend.portals import get_adapter
from backend.application_prepare import review_field, submission_blockers
from backend.application_store import get_application, record_event
from backend.universal_form import answer_from_profile, build_field_spec
from backend.dynamic_form import DynamicFormExecutor

FORM_SCRIPT = r"""
() => {
    const visible = el => {
        const style = getComputedStyle(el);
        return style.visibility !== "hidden" &&
               style.display !== "none" &&
               el.getClientRects().length > 0;
    };

    const mark = el => {
        if (!el.dataset.jobAgentId) {
            el.dataset.jobAgentId = crypto.randomUUID();
        }
        return el.dataset.jobAgentId;
    };

    const dialogs = [...document.querySelectorAll(
        '[role="dialog"], dialog'
    )].filter(visible);

    let scope = dialogs.at(-1);

    if (!scope) {
        const forms = [...document.forms].filter(visible);

        const score = form => {
            let count = form.querySelectorAll(
                'input:not([type="hidden"]), select, textarea'
            ).length;

            if (form.querySelector('input[type="file"]')) {
                count += 20;
            }

            if (/appl|candidate/i.test(
                (form.id || "") + " " + (form.name || "")
            )) {
                count += 20;
            }

            if (form.closest("header, nav, footer")) {
                count = -1;
            }

            return count;
        };

        forms.sort((a, b) => score(b) - score(a));

        if (forms.length && score(forms[0]) > 1) {
            scope = forms[0];
        }
    }

    scope ||= document.querySelector("main") || document.body;

    if (!scope) {
        return [];
    }

    const labelOf = el => {
        const labels = el.labels
            ? [...el.labels]
                .map(item => item.innerText)
                .filter(Boolean)
                .join(" ")
            : "";

        const labelledBy = (el.getAttribute("aria-labelledby") || "")
            .split(/\s+/)
            .map(id => document.getElementById(id)?.innerText || "")
            .join(" ");

        const describedBy = (el.getAttribute("aria-describedby") || "")
            .split(/\s+/)
            .map(id => document.getElementById(id)?.innerText || "")
            .join(" ");

        const container = el.closest(
            '[data-automation-id^="formField"], ' +
            '[data-test-form-element], ' +
            '.form-group, .field, .application-question, ' +
            '[class*="form-field"], [class*="formField"]'
        );

        const nearby = container?.querySelector("label")?.innerText || "";
        const legend = el.closest("fieldset")
            ?.querySelector("legend")?.innerText || "";

        const containerText = container?.innerText || "";
        const parentText = el.parentElement?.innerText || "";
        const previousText = [
            el.previousElementSibling?.innerText || "",
            el.parentElement?.previousElementSibling?.innerText || ""
        ].join(" ");

        const cleanQuestion = value =>
            (value || "")
                .replace(/\s+/g, " ")
                .trim()
                .slice(0, 1000);

        const generatedId = /^_r_[a-z0-9_]+$/i.test(el.id || "");
        const surrounding = [
            containerText,
            parentText,
            previousText
        ]
            .map(cleanQuestion)
            .filter(value => value && value.length > 1)
            .find(value => !/^(yes|no|select|choose|optional)$/i.test(value)) || "";

        const candidates = [
            labels,
            el.getAttribute("aria-label") || "",
            labelledBy.trim(),
            describedBy.trim(),
            nearby,
            legend,
            surrounding,
            el.getAttribute("placeholder") || "",
            el.name || "",
            generatedId ? "" : (el.id || "")
        ];

        return candidates
            .map(cleanQuestion)
            .find(value => value) || "Unlabeled field";
    };

    const nodes = [...scope.querySelectorAll(
        'input, textarea, select, [role="combobox"], ' +
        'button[aria-haspopup="listbox"]'
    )];

    const result = [];
    const seenRadioGroups = new Set();

    for (const el of nodes) {
        const type = (el.type || "").toLowerCase();

        if (el.disabled || el.readOnly) {
            continue;
        }

        if (
            ["hidden", "submit", "button", "reset", "image", "search", "password"]
                .includes(type) &&
            el.getAttribute("role") !== "combobox" &&
            el.getAttribute("aria-haspopup") !== "listbox"
        ) {
            continue;
        }

        if (el.closest("header, nav, footer")) {
            continue;
        }

        if (el.closest('[aria-hidden="true"]')) {
            continue;
        }

        if (!visible(el) && type !== "file") {
            continue;
        }

        const label = labelOf(el);

        const meta = [
            el.id,
            el.name,
            el.getAttribute("placeholder"),
            el.getAttribute("autocomplete"),
            el.getAttribute("aria-label")
        ].filter(Boolean).join(" ");

        if (
            type !== "file" &&
            /\bsearch\b/i.test(label + " " + meta)
        ) {
            continue;
        }

        const required = Boolean(
            el.required ||
            el.getAttribute("aria-required") === "true" ||
            /\*\s*$/.test(label)
        );

        const kind = el.tagName === "SELECT"
            ? "select"
            : type === "radio"
            ? "radio"
            : type === "checkbox"
            ? "checkbox"
            : type === "file"
            ? "file"
            : el.getAttribute("role") === "combobox" ||
              el.getAttribute("aria-haspopup") === "listbox"
            ? "combobox"
            : "text";

        if (kind === "radio") {
            const formIndex = [...document.forms].indexOf(el.form);
            const groupKey = `${formIndex}:${el.name || mark(el)}`;

            if (seenRadioGroups.has(groupKey)) {
                continue;
            }

            seenRadioGroups.add(groupKey);

            const members = el.name
                ? nodes.filter(other =>
                    other.type === "radio" &&
                    other.name === el.name &&
                    other.form === el.form &&
                    !other.disabled &&
                    visible(other)
                )
                : [el];

            const group = el.closest(
                'fieldset, [role="radiogroup"], ' +
                '[data-automation-id^="formField"], ' +
                '[data-test-form-element], .form-group, .field, ' +
                '.application-question, [class*="form-field"], [class*="formField"]'
            );

            const optionLabels = new Set(
                members
                    .map(item => labelOf(item))
                    .map(value => cleanQuestion(value).toLowerCase())
                    .filter(Boolean)
            );

            const explicitQuestion =
                group?.querySelector("legend, [role="heading"], label")?.innerText ||
                group?.getAttribute("aria-label") ||
                group?.getAttribute("data-label") ||
                "";

            const groupText = cleanQuestion(group?.innerText || "");

            // Some ATS forms render radio buttons without a fieldset/legend.
            // In that layout the useful question is usually the text immediately
            // before the radio group. Never use the generated React id/name as
            // the question because it produces useless prompts such as
            // "radio-group-*r_1o*".
            const previousText = [
                el.closest("form")?.previousElementSibling?.innerText || "",
                el.parentElement?.previousElementSibling?.innerText || "",
                el.parentElement?.parentElement?.previousElementSibling?.innerText || ""
            ]
                .map(cleanQuestion)
                .filter(Boolean)
                .join(" ");

            const stripOptions = value =>
                cleanQuestion(value)
                    .replace(/\b(?:yes|no|true|false|select|choose|optional)\b/gi, " ")
                    .replace(/\s+/g, " ")
                    .trim();

            const questionCandidates = [
                explicitQuestion,
                stripOptions(groupText),
                stripOptions(previousText),
            ];

            const question = (
                questionCandidates.find(value => {
                    const normalized = cleanQuestion(value).toLowerCase();
                    return (
                        normalized &&
                        !optionLabels.has(normalized) &&
                        !/^radio-group-|^_r_[a-z0-9_]+$/i.test(normalized)
                    );
                }) ||
                ""
            ).replace(/\\s+/g, " ").trim();

            result.push({
                key: mark(el),
                kind,
                label: question,
                meta,
                required: required || members.some(item => item.required),
                input_type: type,
                filled: members.some(item => item.checked),
                options: members.map(item => ({
                    label: labelOf(item),
                    value: item.value,
                    key: mark(item)
                })),
                accept: ""
            });

            continue;
        }

        let options = [];
        let filled = false;

        if (kind === "select") {
            options = [...el.options]
                .filter(item => !item.disabled)
                .map(item => ({
                    label: item.text.trim(),
                    value: item.value
                }));

            const selectedText = el.selectedOptions[0]?.text || "";

            filled = Boolean(
                el.value &&
                !/^(select|choose|please select|please choose)(\b|\.|$)/i
                    .test(selectedText.trim())
            );
        } else if (kind === "checkbox") {
            options = [
                {label: "Yes", value: "true"},
                {label: "No", value: "false"}
            ];
            filled = el.checked;
        } else if (kind === "file") {
            filled = Boolean(el.files?.length);
        } else if (kind === "combobox") {
            const value = el.value || el.innerText || "";

            filled = Boolean(
                value.trim() &&
                !/^(select|choose|please select|please choose)(\b|\.|$)/i
                    .test(value.trim())
            );
        } else {
            filled = Boolean((el.value || "").trim());
        }

        result.push({
            key: mark(el),
            kind,
            label,
            meta,
            required,
            input_type: type,
            filled,
            options,
            accept: el.accept || ""
        });
    }

    return result;
}
"""

BUTTON_SCRIPT = r"""
() => {
    const visible = el =>
        getComputedStyle(el).visibility !== "hidden" &&
        getComputedStyle(el).display !== "none" &&
        el.getClientRects().length > 0;

    const dialogs = [...document.querySelectorAll(
        '[role="dialog"], dialog'
    )].filter(visible);

    const scope = dialogs.at(-1) ||
                  document.querySelector("main") ||
                  document.body;

    if (!scope) {
        return [];
    }

    return [...scope.querySelectorAll(
        'button, input[type="submit"], a, [role="button"]'
    )].filter(el =>
        visible(el) &&
        !el.disabled &&
        el.getAttribute("aria-disabled") !== "true" &&
        !el.closest("header, nav, footer")
    ).map(el => {
        if (!el.dataset.jobAgentId) {
            el.dataset.jobAgentId = crypto.randomUUID();
        }

        return {
            key: el.dataset.jobAgentId,
            text: (
                el.getAttribute("aria-label") ||
                el.innerText ||
                el.value ||
                ""
            ).replace(/\\s+/g, " ").trim()
        };
    }).filter(item => item.text);
}
"""

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

def host_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)

async def validate_public_url(value: str) -> str:
    parsed = urlparse(value)

    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Use a public HTTPS URL.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not accepted.")

    if parsed.port not in (None, 443):
        raise ValueError("Only the standard HTTPS port is accepted.")

    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            443,
            0,
            socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError(
            "The URL hostname could not be resolved."
        ) from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])

        if not ip.is_global:
            raise ValueError(
                "Private and loopback destinations are not accepted."
            )

    return value

def start_url(request: RunRequest) -> str:
    supplied_url = (request.job_url or "").strip()

    if supplied_url:
        return supplied_url

    if request.portal == "linkedin":
        if request.mode == "discover":
            keywords = quote(
                (request.keywords or "").strip(),
                safe="",
            )

            return (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords}"
            )

        return "https://www.linkedin.com/login"

    if request.portal == "naukri":
        if request.mode == "discover":
            slug = re.sub(
                r"[^a-z0-9]+",
                "-",
                request.keywords.lower(),
            ).strip("-")

            if not slug:
                raise ValueError(
                    "Enter search keywords for Naukri discovery."
                )

            return f"https://www.naukri.com/{slug}-jobs"

        return "https://www.naukri.com/"

    raise ValueError(
        "Enter a job, careers-board, or login URL for this portal."
    )

@dataclass
class Run:
    id: str
    request: RunRequest
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    logs: deque = field(default_factory=lambda: deque(maxlen=800))
    pending: dict[str, Any] | None = None
    results: list[dict] = field(default_factory=list)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None
    sequence: int = 0
    application_id: str | None = None

    def log(self, message: str, level: str = "info") -> None:
        self.sequence += 1

        self.logs.append(
            {
                "sequence": self.sequence,
                "time": utc_now(),
                "level": level,
                "message": message,
            }
        )

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "request": self.request.model_dump(),
            "status": self.status,
            "created_at": self.created_at,
            "logs": list(self.logs),
            "pending": self.pending,
            "results": self.results,
            "application_id": self.application_id,
        }

    async def pause(
        self,
        reason: str,
        message: str,
        allowed: list[str],
        **details: Any,
    ) -> RunCommand:
        token = str(uuid.uuid4())

        self.status = "waiting"
        self.pending = {
            "token": token,
            "reason": reason,
            "message": message,
            "allowed": allowed,
            "claimed": False,
            **details,
        }

        self.log(message, "warning")

        try:
            command = await asyncio.wait_for(
                self.queue.get(),
                timeout=HUMAN_TIMEOUT_SECONDS,
            )

            self.status = "running"
            return command

        finally:
            if self.pending and self.pending["token"] == token:
                self.pending = None

class Engine:
    def __init__(
        self,
        run: Run,
        profile: Profile | None,
        resume_path: Path | None,
    ):
        self.run = run
        self.profile = profile
        self.resume_path = resume_path
        self.adapter = get_adapter(run.request.portal, run.request)
        self.form_rules = self.adapter.form_rules()
        self.context: BrowserContext | None = None
        self.page: Page | None = None

        self.handled: set[tuple[str, str]] = set()
        self.entry_clicks: set[tuple[str, str]] = set()
        self.navigation_attempts: dict[tuple, int] = {}

        self.submission_clicked = False
        self.review_snapshot: list[dict] = []
        self.dynamic_form = None
        self.linkedin_easy_apply_open = False

    @property
    def manual_linkedin_discovery(self) -> bool:
        return (
            self.run.request.portal == "linkedin"
            and self.run.request.mode == "discover"
        )

    async def execute(self) -> None:
        request = self.run.request
        target = await validate_public_url(start_url(request))

        if self.manual_linkedin_discovery:
            target_host = urlparse(target).hostname or ""

            if not host_matches(target_host, "linkedin.com"):
                raise ValueError(
                    "For LinkedIn discovery, provide a LinkedIn search URL "
                    "or leave the URL empty and enter search keywords."
                )

        browser_directory = BROWSER_DIR / request.portal
        browser_directory.mkdir(parents=True, exist_ok=True)

        effective_headless = request.headless

        if self.manual_linkedin_discovery:
            effective_headless = False

            if request.headless:
                self.run.log(
                    "Headless mode was overridden: LinkedIn discovery "
                    "requires manual navigation in a visible browser.",
                    "warning",
                )

        async with async_playwright() as playwright:
            self.run.log(
                f"Launching {'headless' if effective_headless else 'headed'} "
                f"Chromium with persistent {request.portal} session."
            )

            self.context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(browser_directory),
                headless=effective_headless,
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                accept_downloads=False,
            )

            try:
                if ENABLE_STEALTH:
                    from playwright_stealth import Stealth

                    await Stealth().apply_stealth_async(self.context)

                    self.run.log(
                        "Optional stealth compatibility adjustments enabled."
                    )

                self.context.set_default_timeout(8000)
                self.context.set_default_navigation_timeout(45000)

                # Use a fresh blank tab instead of a restored portal page.
                self.page = await self.context.new_page()

                for old_page in list(self.context.pages):
                    if old_page != self.page:
                        await old_page.close()

                self.run.status = "running"
                self.dynamic_form = DynamicFormExecutor(self.page, self.run.log)

                if self.manual_linkedin_discovery:
                    self.run.log(
                        "LinkedIn manual-navigation discovery enabled. "
                        "No automated LinkedIn navigation will be performed."
                    )

                    await self.page.bring_to_front()

                    await self.prepare_manual_linkedin_discovery(target)
                    await self.discover()
                    return

                self.run.log(f"Opening {target}")

                try:
                    await self.page.goto(
                        target,
                        wait_until="domcontentloaded",
                    )
                except PlaywrightTimeoutError:
                    self.run.log(
                        "Navigation exceeded its timeout; "
                        "inspecting the loaded page.",
                        "warning",
                    )

                await self.settle()
                self.run.log(f"Browser landed on: {self.page.url}")

                if request.mode == "login":
                    await self.run.pause(
                        "login",
                        (
                            "Complete login and MFA in the browser, then "
                            "click Resume. This retains browser session state; "
                            "it does not verify successful authentication."
                        ),
                        ["resume"],
                    )

                    self.run.status = "completed"
                    self.run.log(
                        "Session setup finished; persistent state retained."
                    )
                    return

                if request.mode == "discover":
                    await self.discover()
                    return

                await self.apply()

            finally:
                if self.context:
                    await self.context.close()

    async def settle(self) -> None:
        await asyncio.sleep(0.8)

        if not self.context:
            return

        pages = [
            page
            for page in self.context.pages
            if not page.is_closed()
        ]

        if not pages:
            raise RuntimeError("The browser was closed.")

        # If the user opened a new tab, use the newest live tab.
        self.page = pages[-1]

        try:
            await self.page.wait_for_load_state(
                "domcontentloaded",
                timeout=5000,
            )
        except PlaywrightTimeoutError:
            pass

    async def prepare_manual_linkedin_discovery(
        self,
        target: str,
    ) -> None:
        message = (
            "A blank Chromium window is ready. Copy the search URL shown "
            "below and paste it into that window's address bar. Press Enter "
            "and wait until job listings are visible. Then click "
            "Resume / re-check here. The engine will not navigate to "
            "LinkedIn automatically. Use the same browser window, not "
            "your regular Chrome browser."
        )

        while True:
            await self.run.pause(
                "navigation",
                message,
                ["resume"],
                url=target,
            )

            await self.settle()

            current_url = self.page.url
            self.run.log(f"Inspecting manually opened page: {current_url}")

            try:
                await validate_public_url(current_url)
            except ValueError as exc:
                message = (
                    f"The current tab is not a valid public HTTPS page: {exc} "
                    "Paste the LinkedIn search URL into the automated "
                    "browser's address bar, wait for job results, "
                    "then click Resume."
                )
                continue

            current_host = urlparse(current_url).hostname or ""

            if not host_matches(current_host, "linkedin.com"):
                message = (
                    "The current tab is not a LinkedIn page. Paste the "
                    "LinkedIn search URL into this automated browser, "
                    "wait for job results, then click Resume."
                )
                continue

            await self.clear_obstacles()
            await self.settle()

            current_host = urlparse(self.page.url).hostname or ""

            if not host_matches(current_host, "linkedin.com"):
                message = (
                    "The browser is no longer on LinkedIn. Return to the "
                    "public job-search page and click Resume."
                )
                continue

            if await self.linkedin_job_links_visible():
                self.run.log(
                    "Visible LinkedIn job links detected. "
                    "Starting extraction from the manually opened page."
                )
                return

            page_path = urlparse(self.page.url).path.lower()

            if page_path.startswith("/jobs/search"):
                self.run.log(
                    "LinkedIn search page detected. No visible job links "
                    "were recognized yet; discovery will inspect the page "
                    "and perform a few scrolls.",
                    "warning",
                )
                return

            message = (
                "No LinkedIn job-result links were found on the current "
                "page. Open a LinkedIn job-search results page manually, "
                "wait until it loads, then click Resume."
            )

    async def linkedin_job_links_visible(self) -> bool:
        for frame in self.page.frames:
            try:
                links = frame.locator('a[href*="/jobs/view/"]')

                for link in await links.all():
                    if await link.is_visible():
                        return True

            except Exception:
                continue

        return False

    async def page_text(self) -> str:
        parts = []

        for frame in self.page.frames:
            try:
                parts.append(
                    await frame.locator("body").inner_text(timeout=1500)
                )
            except Exception:
                continue

        return "\n".join(parts)[:200_000]

    async def challenge_present(self) -> bool:
        text = (await self.page_text()).lower()
        title = (await self.page.title()).lower()

        phrases = (
            "verify you are human",
            "verify that you are human",
            "checking your browser",
            "performing security verification",
            "unusual traffic from your computer",
            "access to this page has been denied",
        )

        if any(phrase in text for phrase in phrases):
            return True

        if "just a moment" in title or "attention required" in title:
            return True

        for frame in self.page.frames:
            try:
                detected = await frame.evaluate(
                    r"""
                    () => {
                        const solved = [...document.querySelectorAll(
                            'textarea[name="g-recaptcha-response"], ' +
                            'textarea[name="h-captcha-response"], ' +
                            'input[name="cf-turnstile-response"]'
                        )].some(el => Boolean(el.value));

                        if (solved) {
                            return false;
                        }

                        return [...document.querySelectorAll("iframe")]
                            .some(el => {
                                const description = (
                                    el.src + " " + el.title
                                ).toLowerCase();

                                const box = el.getBoundingClientRect();

                                return /captcha|challenge/.test(description) &&
                                    box.width > 180 &&
                                    box.height > 60 &&
                                    getComputedStyle(el).display !== "none";
                            });
                    }
                    """
                )

                if detected:
                    return True

            except Exception:
                continue

        return False

    async def linkedin_authenticated_present(self) -> bool:
        """Detect an authenticated LinkedIn shell before treating password inputs as login."""
        if self.run.request.portal != "linkedin":
            return False

        authenticated_selectors = [
            'button[aria-label*="Me" i]',
            'a[aria-label*="Me" i]',
            '[data-control-name*="identity_profile" i]',
            'a[href*="/in/"]',
            'a[href*="/mynetwork/"]',
            'a[href*="/messaging/"]',
        ]

        for selector in authenticated_selectors:
            try:
                locator = self.page.locator(selector)
                for index in range(await locator.count()):
                    if await locator.nth(index).is_visible():
                        return True
            except Exception:
                continue

        try:
            nav = self.page.locator("header nav, nav")
            for index in range(await nav.count()):
                item = nav.nth(index)
                if not await item.is_visible():
                    continue
                text = re.sub(r"\s+", " ", await item.inner_text()).strip()
                if re.search(r"\bMe\b", text, re.I):
                    return True
        except Exception:
            pass

        return False

    async def login_present(self) -> bool:
        # LinkedIn may keep hidden authentication controls mounted in an
        # otherwise authenticated job page. Prefer positive authenticated
        # signals before treating password fields as a login requirement.
        if self.run.request.portal == "linkedin":
            if await self.linkedin_authenticated_present():
                return False

        if re.search(
            r"/(?:login|signin|sign-in|checkpoint|authwall)(?:/|\?|$)",
            self.page.url,
            re.I,
        ):
            return True

        if self.manual_linkedin_discovery:
            if await self.linkedin_job_links_visible():
                return False

        for frame in self.page.frames:
            try:
                fields = frame.locator('input[type="password"]')

                for password_field in await fields.all():
                    if await password_field.is_visible():
                        return True

            except Exception:
                continue

        return False

    async def clear_obstacles(self) -> None:
        while True:
            if await self.challenge_present():
                await self.run.pause(
                    "challenge",
                    (
                        "A CAPTCHA or access challenge was detected. "
                        "Resolve it manually if you wish, then click Resume, "
                        "or stop this run. No challenge solver or "
                        "authentication bypass is used."
                    ),
                    ["resume"],
                )

                await self.settle()
                self.run.log(f"Browser is now on: {self.page.url}")
                continue

            if await self.login_present():
                if self.manual_linkedin_discovery:
                    await self.run.pause(
                        "navigation",
                        (
                            "The current LinkedIn page is an authentication "
                            "screen, not accessible job results. This run "
                            "will not log in or navigate automatically. "
                            "If public search is available to you, open it "
                            "manually in this same window and click Resume "
                            "once listings are visible. Otherwise stop the run."
                        ),
                        ["resume"],
                        url=start_url(self.run.request),
                    )
                else:
                    await self.run.pause(
                        "login",
                        (
                            "Login, MFA, or account creation is required. "
                            "Complete it in the headed browser and return "
                            "to the application, then click Resume, "
                            "or stop the run."
                        ),
                        ["resume"],
                    )

                await self.settle()
                self.run.log(f"Browser is now on: {self.page.url}")
                continue

            return

    async def fields(self) -> list[dict]:
        collected = []

        for frame in self.page.frames:
            try:
                for item in await frame.evaluate(FORM_SCRIPT):
                    item["frame"] = frame
                    item["portal_hints"] = await self.portal_field_hints(item)
                    spec = build_field_spec(item)
                    item["semantic"] = spec.semantic
                    item["sensitive"] = spec.sensitive
                    item["answer_action"] = "review" if spec.sensitive else "auto_fill_or_review"
                    collected.append(item)
            except Exception:
                continue

        return collected

    def locator(self, item: dict) -> Locator:
        frame: Frame = item["frame"]

        return frame.locator(
            f'[data-job-agent-id="{item["key"]}"]'
        )

    async def portal_field_hints(self, item: dict) -> list[str]:
        """Classify fields using semantic patterns and stable portal selectors."""
        haystack = " ".join(
            str(item.get(key, "")) for key in ("label", "meta", "accept")
        )
        hints = [
            semantic
            for semantic, patterns in self.form_rules.field_patterns.items()
            if any(re.search(pattern, haystack, re.I) for pattern in patterns)
        ]

        if self.form_rules.field_selectors:
            locator = self.locator(item)
            for semantic, selectors in self.form_rules.field_selectors.items():
                if semantic in hints:
                    continue
                for selector in selectors:
                    try:
                        if await locator.evaluate(
                            "(el, value) => el.matches(value)",
                            selector,
                        ):
                            hints.append(semantic)
                            break
                    except Exception:
                        continue

        return hints

    def button_pattern(self, kind: str, fallback: str) -> str:
        patterns = self.form_rules.next_button_patterns if kind == "next" else self.form_rules.submit_button_patterns
        if not patterns:
            return fallback
        return "(?:" + "|".join(f"(?:{pattern})" for pattern in patterns) + f"|(?:{fallback}))"

    async def find_button(self, pattern: str) -> dict | None:
        regex = re.compile(pattern, re.I)

        for frame in self.page.frames:
            try:
                buttons = await frame.evaluate(BUTTON_SCRIPT)

                for button in buttons:
                    text = (button.get("text") or "").strip()

                    # Portal UIs frequently add context around an action
                    # ("Next: Education", "Continue to next step", etc.).
                    # A full-string match was too strict for LinkedIn's
                    # dynamically rendered Easy Apply controls.
                    if regex.fullmatch(text) or regex.search(text):
                        button["frame"] = frame
                        return button

                # LinkedIn sometimes exposes the action through aria-label
                # or button markup that is not represented cleanly by the
                # generic action scan. Re-query visible controls directly.
                if self.run.request.portal == "linkedin":
                    candidates = await frame.locator(
                        'button, [role="button"], input[type="submit"]'
                    ).all()

                    for candidate in candidates:
                        try:
                            if not await candidate.is_visible():
                                continue
                            if await candidate.is_disabled():
                                continue

                            text = " ".join(
                                value
                                for value in [
                                    await candidate.inner_text(),
                                    await candidate.get_attribute("aria-label"),
                                    await candidate.get_attribute("title"),
                                    await candidate.get_attribute("value"),
                                ]
                                if value
                            )
                            text = re.sub(r"\s+", " ", text).strip()

                            if regex.search(text):
                                key = await candidate.get_attribute(
                                    "data-job-agent-id"
                                )
                                if not key:
                                    key = str(uuid.uuid4())
                                    await candidate.set_attribute(
                                        "data-job-agent-id", key
                                    )

                                return {
                                    "key": key,
                                    "text": text,
                                    "frame": frame,
                                }
                        except Exception:
                            continue

            except Exception:
                continue

        return None

    async def find_linkedin_next_button(self) -> dict | None:
        """Find the visible Next/Continue control inside LinkedIn's Easy Apply dialog."""
        if self.run.request.portal != "linkedin":
            return None

        # Search the actual top-level document first. LinkedIn's current Easy
        # Apply DOM uses a native <dialog> with a footer button. This is more
        # reliable than scanning every frame or the job-page DOM.
        selectors = (
            "dialog:visible footer button",
            "dialog:visible button",
            '[role="dialog"]:visible footer button',
            '[role="dialog"]:visible button',
        )

        for selector in selectors:
            try:
                controls = self.page.locator(selector)
                count = await controls.count()
                self.run.log(
                    f"LinkedIn Next search: {selector} -> {count} visible candidates."
                )

                for index in range(count):
                    candidate = controls.nth(index)
                    if not await candidate.is_visible():
                        continue

                    state = await candidate.evaluate(
                        """el => ({
                            text: (el.innerText || el.textContent || '').trim(),
                            ariaDisabled: el.getAttribute('aria-disabled'),
                            disabled: !!el.disabled
                        })"""
                    )

                    text = re.sub(r"\s+", " ", state["text"]).strip()

                    if state["ariaDisabled"] == "true" or state["disabled"]:
                        self.run.log(
                            f"LinkedIn navigation candidate is disabled: {text or '<unnamed>'}",
                            "warning",
                        )
                        continue

                    normalized_text = re.sub(r"\s+", " ", text).strip().lower()
                    if not (
                        normalized_text == "next"
                        or normalized_text == "continue"
                        or "review application" == normalized_text
                        or "save and continue" == normalized_text
                        or normalized_text.startswith("next ")
                        or normalized_text.startswith("continue ")
                    ):
                        continue

                    key = await candidate.get_attribute("data-job-agent-id")
                    if not key:
                        key = str(uuid.uuid4())
                        await candidate.evaluate(
                            "(el, value) => el.setAttribute('data-job-agent-id', value)",
                            key,
                        )

                    self.run.log(
                        f"LinkedIn Next button FOUND in dialog: {text}"
                    )
                    return {
                        "key": key,
                        "text": text,
                        "frame": self.page.main_frame,
                    }

            except Exception as exc:
                self.run.log(
                    f"LinkedIn Next search failed for {selector}: "
                    f"{type(exc).__name__}: {exc}",
                    "warning",
                )

        return None

    async def confirmed(self) -> bool:
        text = await self.page_text()

        return bool(
            re.search(
                r"your application (?:has been|was) (?:successfully )?submitted|"
                r"application submitted successfully|"
                r"thank you for applying|"
                r"we have received your application|"
                r"your application (?:has been|was) sent",
                text,
                re.I,
            )
        )

    async def visible_errors(self) -> list[str]:
        errors = []

        for frame in self.page.frames:
            try:
                items = await frame.locator(
                    '[role="alert"], [aria-invalid="true"]'
                ).all()

                for item in items[:20]:
                    if not await item.is_visible():
                        continue

                    if await item.get_attribute("aria-invalid") == "true":
                        label = (
                            await item.get_attribute("aria-label")
                            or await item.get_attribute("name")
                            or "A form field"
                        )

                        errors.append(f"{label} is marked invalid.")

                    else:
                        text = (await item.inner_text()).strip()

                        if text and re.search(
                            r"error|invalid|required|failed|unable|try again",
                            text,
                            re.I,
                        ):
                            errors.append(text[:500])

            except Exception:
                continue

        return errors

    async def enrich_job_results(self) -> None:
        """Enrich ATS discovery links from their public job-page DOM."""
        if self.run.request.portal not in {"greenhouse", "lever"}:
            return

        rules = self.adapter.job_page_rules()
        if not (
            rules.title_selectors
            or rules.company_selectors
            or rules.location_selectors
            or rules.description_selectors
        ):
            return

        candidates = list(self.run.results)[:25]
        if not candidates:
            return

        self.run.log(
            f"Enriching up to {len(candidates)} {self.run.request.portal.title()} "
            "job pages with structured metadata."
        )

        detail_page = await self.context.new_page()
        try:
            for index, job in enumerate(candidates, start=1):
                url = job.get("url", "")
                if not url or not self.adapter.accepts_url(url):
                    continue

                try:
                    await validate_public_url(url)
                    await detail_page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    await detail_page.wait_for_timeout(400)

                    data = await detail_page.evaluate(
                        """
                        rules => {
                            const clean = value =>
                                (value || "").replace(/\\s+/g, " ").trim();

                            const read = selectors => {
                                for (const selector of selectors || []) {
                                    const nodes = [...document.querySelectorAll(selector)];
                                    for (const node of nodes) {
                                        const value = clean(
                                            node.getAttribute("content") ||
                                            node.innerText ||
                                            node.textContent
                                        );
                                        if (value) return value;
                                    }
                                }
                                return "";
                            };

                            return {
                                title: read(rules.title_selectors),
                                company: read(rules.company_selectors),
                                location: read(rules.location_selectors),
                                description: read(rules.description_selectors),
                                job_id: read(rules.job_id_selectors),
                            };
                        }
                        """,
                        {
                            "title_selectors": list(rules.title_selectors),
                            "company_selectors": list(rules.company_selectors),
                            "location_selectors": list(rules.location_selectors),
                            "description_selectors": list(rules.description_selectors),
                            "job_id_selectors": list(rules.job_id_selectors),
                        },
                    )

                    for key in ("title", "company", "location", "description", "job_id"):
                        value = (data.get(key) or "").strip()
                        if value:
                            job[key] = value[:12000 if key == "description" else 500]

                    job_id = (data.get("job_id") or "").strip()
                    if not job_id:
                        parsed_job_url = urlparse(url)
                        job_id = parsed_job_url.path.rstrip("/").split("/")[-1]
                        query_match = re.search(
                            r"(?:gh_jid|lever-job-id)=([A-Za-z0-9_-]+)",
                            parsed_job_url.query,
                            re.I,
                        )
                        if query_match:
                            job_id = query_match.group(1)

                    job.setdefault("metadata", {})
                    job["metadata"]["source"] = "portal_job_page"
                    job["metadata"]["job_id"] = job_id

                    self.run.log(
                        f"Enriched {index}/{len(candidates)}: "
                        f"{job.get('title') or job.get('url')}"
                    )
                except Exception as exc:
                    self.run.log(
                        f"Could not enrich {url}: {type(exc).__name__}. "
                        "Keeping the discovered link.",
                        "warning",
                    )
        finally:
            await detail_page.close()

    async def discover(self) -> None:
        await self.settle()
        await self.clear_obstacles()

        self.run.log(
            "Collecting job links from the current page. "
            "The search URL will not be reopened."
        )

        found: dict[str, dict] = {}
        keywords = compact(self.run.request.keywords).split()

        # LinkedIn virtualizes its result list. Scrolling the document itself
        # may leave the visible job list unchanged, so discovery explicitly
        # scrolls the known results containers and rescans after each load.
        max_passes = 12
        stagnant_passes = 0

        for pass_number in range(max_passes):
            await self.settle()
            await self.clear_obstacles()
            before_count = len(found)

            for frame in self.page.frames:
                try:
                    links = await frame.locator("a[href]").evaluate_all(
                        """
                        elements => elements.map(el => ({
                            url: el.href,
                            title: (
                                el.innerText ||
                                el.getAttribute("aria-label") ||
                                el.getAttribute("title") ||
                                ""
                            ).replace(/\\s+/g, " ").trim()
                        }))
                        """
                    )
                except Exception:
                    continue

                for link in links:
                    url = link["url"].split("#")[0]
                    title = link["title"]

                    if not title or not url.startswith("https://"):
                        continue

                    parsed = urlparse(url)
                    host = parsed.hostname or ""
                    path = parsed.path.lower()

                    is_job = (
                        (
                            host_matches(host, "linkedin.com")
                            and "/jobs/view/" in path
                        )
                        or (
                            host_matches(host, "naukri.com")
                            and "job-listings" in path
                        )
                        or (
                            host_matches(host, "greenhouse.io")
                            and (
                                "/jobs/" in path
                                or "gh_jid=" in parsed.query
                            )
                        )
                        or (
                            host == "jobs.lever.co"
                            and len(path.strip("/").split("/")) >= 2
                        )
                        or (
                            host_matches(host, "myworkdayjobs.com")
                            and "/job/" in path
                        )
                        or (
                            self.run.request.portal == "custom"
                            and re.search(r"/jobs?/|/positions?/", path)
                        )
                    )

                    if not is_job:
                        continue

                    if (
                        self.run.request.portal not in {"linkedin", "naukri"}
                        and keywords
                        and not any(
                            word in compact(title)
                            for word in keywords
                        )
                    ):
                        continue

                    # LinkedIn tracking parameters can otherwise produce
                    # duplicate entries for the same job.
                    if host_matches(host, "linkedin.com"):
                        url = parsed._replace(
                            query="",
                            fragment="",
                        ).geturl()

                    found[url] = {
                        "title": title[:250],
                        "url": url,
                    }

            self.run.results = list(found.values())[:100]

            added = len(found) - before_count
            self.run.log(
                f"Discovery pass {pass_number + 1}/{max_passes}: "
                f"{len(self.run.results)} unique candidate links "
                f"(+{added} this pass)."
            )

            if added == 0:
                stagnant_passes += 1
            else:
                stagnant_passes = 0

            if stagnant_passes >= 2:
                self.run.log(
                    "LinkedIn job-list scrolling produced no new links "
                    "for two consecutive passes; ending discovery."
                )
                break

            # Scroll the virtualized LinkedIn results list, not just the
            # document. Keep the page-level wheel as a fallback for layouts
            # that do not expose the standard list container.
            for frame in self.page.frames:
                try:
                    await frame.locator(
                        ".jobs-search-results-list, "
                        ".jobs-search-results__list, "
                        "ul.scaffold-layout__list, "
                        ".scaffold-layout__list"
                    ).evaluate_all(
                        """
                        elements => elements.forEach(el => {
                            el.scrollTop = el.scrollHeight;
                            el.dispatchEvent(new Event("scroll", {bubbles: true}));
                        })
                        """
                    )
                except Exception:
                    pass

            try:
                await self.page.mouse.wheel(0, 1400)
            except Exception:
                pass

            await asyncio.sleep(1.0)

        await self.enrich_job_results()

        self.run.status = "completed"

        self.run.log(
            f"Discovery finished with {len(self.run.results)} candidate links. "
            "No applications were submitted."
        )

        if not self.run.results:
            self.run.log(
                "No supported job links were found. The search may have "
                "zero results, may not have finished loading, or may use "
                "a different link layout.",
                "warning",
            )

    def known_answer(self, item: dict) -> str | None:
        profile = self.profile

        if profile is None:
            return None

        label = normalize_question(item["label"])

        if label in profile.custom_answers:
            return profile.custom_answers[label]

        question = compact(item["label"])
        metadata = compact(item["meta"])
        text = question + " " + metadata

        personal = profile.personal
        online = profile.online_profiles
        defaults = profile.ats_defaults

        if item["kind"] == "checkbox":
            return None

        if re.search(r"first name|given name|givenname|fname", text):
            return personal.first_name or None

        if re.search(r"last name|family name|surname|lname", text):
            return personal.last_name or None

        if re.search(r"full name|your name|candidate name|fullname", text):
            return personal.full_name or None

        if question == "name":
            return personal.full_name or None

        if "email" in text or "e mail" in text:
            return personal.email or None

        if re.search(r"country code|dial code|extension", text):
            return None

        if re.search(r"phone|mobile|telephone|tel national", text):
            return personal.phone or None

        if "linkedin" in text:
            return online.linkedin or None

        if "github" in text:
            return online.github or None

        if re.search(r"portfolio|personal website|website url", text):
            return online.portfolio or None

        if re.search(r"postal|zip code|zipcode", text):
            return personal.postal_code or None

        if question in {"city", "current city", "town"}:
            return personal.city or None

        if question in {"state", "province", "state province"}:
            return personal.state or None

        if question in {"country", "country of residence"}:
            return personal.country or None

        if question in {
            "location",
            "current location",
            "your location",
            "where are you located",
        }:
            return personal.location or None

        if re.search(r"street|address line|address 1", question):
            return personal.street or None

        if re.search(
            r"current job title|current title|present job title|present title",
            question,
        ):
            current_job = next(
                (
                    job.title
                    for job in profile.work_history
                    if job.current and job.title
                ),
                None,
            )
            if current_job:
                return current_job

            if profile.work_history and profile.work_history[0].title:
                return profile.work_history[0].title

        if re.search(r"notice period", question):
            return defaults.notice_period

        if re.search(r"expected|desired", question) and re.search(
            r"salary|compensation|ctc",
            question,
        ):
            if "currency" in question:
                return defaults.salary_currency or None

            if defaults.expected_salary_amount is None:
                return None

            requested_period = next(
                (
                    period
                    for term, period in (
                        ("annual", "annual"),
                        ("year", "annual"),
                        ("monthly", "monthly"),
                        ("month", "monthly"),
                        ("hourly", "hourly"),
                        ("hour", "hourly"),
                    )
                    if term in question
                ),
                None,
            )

            if (
                requested_period
                and requested_period != defaults.salary_period
            ):
                return None

            if re.search(r"lakh|lpa|crore|thousand", question):
                return None

            if item["input_type"] == "number":
                if not requested_period:
                    return None

                return f"{defaults.expected_salary_amount:g}"

            return (
                f"{defaults.expected_salary_amount:g} "
                f"{defaults.salary_currency} {defaults.salary_period}"
            ).strip()

        if "sponsor" in question:
            if re.search(r"not require|without|no sponsorship", question):
                return None

            if defaults.requires_sponsorship is not None:
                return "Yes" if defaults.requires_sponsorship else "No"

        if re.search(
            r"authorized|authorised|authorization to work",
            question,
        ):
            if re.search(
                r"not authorized|not authorised|without",
                question,
            ):
                return None

            if defaults.work_authorized is not None:
                return "Yes" if defaults.work_authorized else "No"

        # Answer boolean experience-range questions when the saved
        # profile has a verified total-experience value. This is safe only
        # for total/general experience; technology-specific experience still
        # requires an explicit candidate fact.
        if profile.years_of_experience is not None and "experience" in question:
            range_match = re.search(
                r"\b(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*years?\b",
                question,
            )
            plus_match = re.search(
                r"\b(\d+(?:\.\d+)?)\s*\+\s*years?\b",
                question,
            )

            has_specific_skill = bool(
                re.search(
                    r"\b(?:with|using|in)\s+[a-z0-9+#.][^?]*",
                    question,
                )
            )

            if not has_specific_skill:
                years = profile.years_of_experience
                if range_match:
                    lower = float(range_match.group(1))
                    upper = float(range_match.group(2))
                    return "Yes" if lower <= years <= upper else "No"

                if plus_match:
                    lower = float(plus_match.group(1))
                    return "Yes" if years >= lower else "No"

        # LinkedIn uses several phrasings for the same verified
        # profile fact. Do not send these to the generic answer suggester.
        if (
            profile.years_of_experience is not None
            and (
                re.search(r"\bexperience\s+in\s+years?\b", question)
                or re.search(r"\byears?\s+(?:of\s+)?experience\b", question)
                or question in {
                    "total experience",
                    "experience years",
                }
            )
        ):
            # Skill-specific questions such as "experience with Python" must
            # not be answered with total experience.
            if not re.search(
                r"\b(?:with|using|in)\s+[a-z0-9+#.]+",
                question,
            ):
                return f"{profile.years_of_experience:g}"

        if re.search(
            r"\b(?:highest\s+qualification|highest\s+degree|"
            r"qualification\s+held|degree|education\s+level)\b",
            question,
        ):
            if profile.education and profile.education[0].degree:
                return profile.education[0].degree

        if re.search(
            r"\b(?:skill\s*set|skills?|technical\s+skills?|"
            r"key\s+skills?|skillset)\b",
            question,
        ):
            skills = [
                str(skill).strip()
                for skill in profile.skills
                if str(skill).strip()
            ]
            if skills:
                return ", ".join(skills)

        if question in {"gender", "gender identity"}:
            return defaults.gender

        if question in {"ethnicity", "race ethnicity", "race"}:
            return defaults.ethnicity

        if question in {"disability", "disability status"}:
            return defaults.disability

        if question in {"veteran status", "protected veteran status"}:
            return defaults.veteran_status

        return None

    def choose_option(
        self,
        answer: str,
        options: list[dict],
    ) -> dict | None:
        normalized = compact(answer)

        for option in options:
            if compact(option["label"]) == normalized:
                return option

        if normalized in {"yes", "no"}:
            matches = [
                option
                for option in options
                if compact(option["label"]).split(" ", 1)[0] == normalized
            ]

            if len(matches) == 1:
                return matches[0]

        if normalized in {
            "prefer not to say",
            "prefer not to answer",
            "decline to answer",
        }:
            matches = [
                option
                for option in options
                if re.search(
                    r"prefer not|decline|do not wish|don t wish|choose not",
                    compact(option["label"]),
                )
            ]

            if len(matches) == 1:
                return matches[0]

        return None

    async def focus_first_application_field(self, fields: list[dict]) -> bool:
        """Focus the first editable application control when a step opens."""
        for item in fields:
            if item.get("filled") or item.get("kind") == "file":
                continue
            try:
                locator = self.locator(item)
                if self.dynamic_form:
                    resolved, _strategy = await self.dynamic_form.resolve(item)
                    if resolved is not None:
                        locator = resolved
                if await locator.count() and await locator.first.is_visible():
                    target = locator.first
                    await target.scroll_into_view_if_needed()
                    await target.focus()
                    if await target.evaluate("el => document.activeElement === el"):
                        self.run.log(f"Focused first application field: {item['label']}")
                        return True
            except Exception:
                continue
        try:
            scope = self.page.main_frame.locator(
                'dialog:visible, [role="dialog"]:visible, main'
            ).first
            controls = scope.locator(
                'input:not([type="hidden"]):not([type="submit"]):not([disabled]), textarea:not([disabled]), select:not([disabled]), [role="combobox"]:not([aria-disabled="true"])'
            )
            for index in range(await controls.count()):
                candidate = controls.nth(index)
                if await candidate.is_visible():
                    await candidate.scroll_into_view_if_needed()
                    await candidate.focus()
                    if await candidate.evaluate("el => document.activeElement === el"):
                        self.run.log("Focused first application field using keyboard fallback.")
                        return True
        except Exception:
            pass
        return False

    async def _tab_to_field(self, item: dict) -> Locator | None:
        """Fallback for React/ATS controls whose generated IDs are unstable.

        Start from the first visible form control in the active application
        dialog and use real keyboard Tab navigation. This mirrors how a
        candidate moves through these forms and avoids depending on generated
        React IDs.
        """
        if not self.page:
            return None

        frame = item.get("frame") or self.page.main_frame
        target_key = item.get("key")
        target_label = compact(item.get("label", ""))

        try:
            scope = frame.locator(
                'dialog:visible, [role="dialog"]:visible, '
                'main'
            ).first

            controls = scope.locator(
                'input:not([type="hidden"]):not([type="submit"]):not([disabled]), '
                'textarea:not([disabled]), select:not([disabled]), '
                '[role="combobox"]:not([aria-disabled="true"])'
            )

            count = await controls.count()
            if count == 0:
                return None

            # Prefer the first visible editable control as the keyboard start.
            start = None
            for index in range(count):
                candidate = controls.nth(index)
                if await candidate.is_visible():
                    start = candidate
                    break

            if start is None:
                return None

            await start.focus()

            # Check the currently focused element and then walk forward.
            for _ in range(min(count + 3, 40)):
                focused = frame.locator(":focus")
                if await focused.count():
                    current = focused.first
                    try:
                        current_key = await current.get_attribute("data-job-agent-id")
                        current_label = compact(
                            await current.get_attribute("aria-label") or ""
                        )
                        current_name = compact(
                            await current.get_attribute("name") or ""
                        )

                        if target_key and current_key == target_key:
                            return current

                        if target_label and (
                            target_label == current_label
                            or target_label == current_name
                        ):
                            return current
                    except Exception:
                        pass

                await self.page.keyboard.press("Tab")
                await asyncio.sleep(0.08)

            return None
        except Exception as exc:
            self.run.log(
                f"Keyboard field navigation failed: {type(exc).__name__}.",
                "warning",
            )
            return None

    async def fill(self, item: dict, answer: str) -> bool:
        locator = self.locator(item)
        kind = item["kind"]

        # Prefer resilient user-facing locators when the DOM has changed.
        if self.dynamic_form:
            resolved, _strategy = await self.dynamic_form.resolve(item)
            if resolved is not None:
                locator = resolved

        if kind == "select":
            option = self.choose_option(answer, item["options"])

            if option is None:
                answer_tokens = {
                    token
                    for token in re.findall(r"[a-z0-9]+", compact(answer).lower())
                    if len(token) > 2
                }

                best = None
                best_score = 0
                for candidate in item.get("options", []):
                    label = compact(candidate.get("label", "")).lower()
                    if not label or label.startswith("select "):
                        continue
                    tokens = {
                        token
                        for token in re.findall(r"[a-z0-9]+", label)
                        if len(token) > 2
                    }
                    score = len(answer_tokens & tokens)
                    if score > best_score:
                        best_score = score
                        best = candidate

                option = best if best_score >= 2 else None

            if option is None:
                return False

            await locator.select_option(value=option["value"])
            selected = await self.read_field_value(item)
            return bool(selected and compact(selected).lower() != "select an option")

        if kind == "radio":
            option = self.choose_option(answer, item["options"])

            if option is None:
                return False

            await item["frame"].locator(
                f'[data-job-agent-id="{option["key"]}"]'
            ).check()

            return True

        if kind == "checkbox":
            normalized = compact(answer)

            if normalized not in {"yes", "no", "true", "false"}:
                return False

            await locator.set_checked(
                normalized in {"yes", "true"}
            )
            return True

        if kind == "combobox":
            await locator.click()

            tag = await locator.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            if tag in {"input", "textarea"}:
                await locator.fill(answer)

            await asyncio.sleep(0.5)

            options = item["frame"].get_by_role(
                "option",
                name=answer,
                exact=True,
            )

            if (
                await options.count() == 1
                and await options.first.is_visible()
            ):
                await options.first.click()
                return True

            await self.page.keyboard.press("Escape")
            return False

        if kind == "date":
            try:
                await locator.fill(answer)
                await locator.press("Tab")
                return True
            except Exception:
                return False

        if kind == "text":
            max_length = await locator.get_attribute("maxlength")

            if (
                max_length
                and max_length.isdigit()
                and len(answer) > int(max_length)
            ):
                return False

            async def type_and_verify(target: Locator) -> bool:
                try:
                    await target.scroll_into_view_if_needed()
                    await target.click()

                    # LinkedIn uses React-controlled inputs. Set the native
                    # value through the prototype setter and dispatch real
                    # input/change events so React updates its controlled
                    # state as if the candidate had typed the value.
                    await target.evaluate(
                        """(el, value) => {
                            const proto = Object.getPrototypeOf(el);
                            const descriptor =
                                Object.getOwnPropertyDescriptor(proto, 'value') ||
                                Object.getOwnPropertyDescriptor(
                                    HTMLInputElement.prototype, 'value'
                                ) ||
                                Object.getOwnPropertyDescriptor(
                                    HTMLTextAreaElement.prototype, 'value'
                                );

                            if (descriptor && descriptor.set) {
                                descriptor.set.call(el, value);
                            } else {
                                el.value = value;
                            }

                            el.dispatchEvent(
                                new Event('input', {bubbles: true})
                            );
                            el.dispatchEvent(
                                new Event('change', {bubbles: true})
                            );
                        }""",
                        answer,
                    )

                    actual = await target.input_value()

                    if actual.strip() != answer.strip():
                        # Last fallback: actual keyboard input.
                        await target.press("Control+A")
                        await target.type(answer, delay=12)
                        actual = await target.input_value()

                    if actual.strip() != answer.strip():
                        return False

                    await target.press("Tab")

                    validity = await target.evaluate(
                        "el => el.validity ? el.validity.valid : true"
                    )
                    return bool(validity)
                except Exception:
                    return False

            # If the application step was just opened, the runner may
            # already have the correct control focused. Type into the actual
            # active element first instead of switching to a generated React
            # locator that can point at a stale/hidden node.
            try:
                active = self.page.locator(":focus")
                if await active.count() == 1:
                    active_tag = await active.evaluate(
                        "el => el.tagName.toLowerCase()"
                    )
                    editable = await active.evaluate(
                        "el => !el.disabled && !el.readOnly && "
                        "('value' in el)"
                    )
                    if active_tag in {"input", "textarea"} and editable:
                        await active.press("Control+A")
                        await self.page.keyboard.type(answer, delay=12)
                        actual = await active.input_value()
                        if actual.strip() == answer.strip():
                            await self.page.keyboard.press("Tab")
                            self.run.log(
                                f"Filled focused application field: {item['label']}"
                            )
                            return True
                        self.run.log(
                            f"Focused field rejected typed value for: {item['label']}",
                            "warning",
                        )
            except Exception:
                pass

            # First use the resolved semantic/label locator.
            if await type_and_verify(locator):
                self.run.log(f"Filled and verified: {item['label']}")
                return True

            # Then use real keyboard Tab navigation from the first form
            # control. This handles unstable React-generated IDs.
            tab_locator = await self._tab_to_field(item)
            if tab_locator is not None and await type_and_verify(tab_locator):
                self.run.log(
                    f"Filled and verified via keyboard Tab: {item['label']}"
                )
                return True

            self.run.log(
                f"Could not verify text entered for: {item['label']}; "
                "the application will not advance.",
                "warning",
            )
            return False

        return False

    def sync_application(self, status: str | None = None, event_type: str = "state_changed", message: str = "") -> None:
        if not self.run.application_id:
            return
        try:
            application = get_application(self.run.application_id)
            if status:
                application.status = status
            record_event(application, event_type, message or f"Application state: {status or application.status}.")
        except (FileNotFoundError, ValueError):
            self.run.log("Application lifecycle state could not be persisted.", "warning")

    def update_application_review(self, fields: list[dict], errors: list[str] | None = None) -> None:
        """Persist a review snapshot without treating it as submission approval."""
        if not self.run.application_id:
            return
        try:
            application = get_application(self.run.application_id)
            snapshot = [review_field(item) for item in fields]
            application.review_fields = snapshot
            application.missing_fields = [item["label"] for item in snapshot if item["required"] and not item["filled"]]
            application.sensitive_fields = [item["label"] for item in snapshot if item["sensitive"]]
            application.validation_errors = list(errors or [])
            record_event(
                application,
                "review_snapshot",
                "Application review state updated.",
                missing_fields=application.missing_fields,
                sensitive_fields=application.sensitive_fields,
                validation_errors=application.validation_errors,
            )
        except (FileNotFoundError, ValueError):
            self.run.log("Application review state could not be persisted.", "warning")

    async def read_field_value(self, item: dict) -> str:
        """Read the candidate-visible value from a live form control."""
        locator = self.locator(item)

        if self.dynamic_form:
            resolved, _strategy = await self.dynamic_form.resolve(item)
            if resolved is not None:
                locator = resolved

        try:
            kind = item.get("kind", "text")

            if kind == "select":
                value = (
                    await locator.locator("option:checked").inner_text()
                ).strip()
                if compact(value).lower() in {
                    "",
                    "select",
                    "select an option",
                    "select an answer",
                    "choose",
                    "choose an option",
                }:
                    return ""
                return value

            if kind == "radio":
                for option in item.get("options", []):
                    option_locator = item["frame"].locator(
                        f'[data-job-agent-id="{option["key"]}"]'
                    )
                    if await option_locator.is_checked():
                        return option["label"].strip()

                return ""

            if kind == "checkbox":
                return "Yes" if await locator.is_checked() else ""

            value = await locator.input_value()
            return value.strip()

        except Exception:
            try:
                return (await locator.inner_text()).strip()
            except Exception:
                return ""

    async def remember_manual_field_value(
        self,
        item: dict,
        previous_value: str,
    ) -> bool:
        """Persist a newly entered browser value to this run's profile."""
        if not self.profile or not self.run.request.profile_id:
            return False

        current_value = await self.read_field_value(item)

        if not current_value or current_value == previous_value:
            return False

        # Never silently convert an unchanged placeholder/default into memory.
        if current_value.lower() in {"select", "choose", "please select", "please choose"}:
            return False

        remember_answer(
            self.run.request.profile_id,
            item["label"],
            current_value,
        )

        self.run.log(
            f"Remembered manual answer for this profile: {item['label']}"
        )
        return True

    async def answer_field(self, item: dict) -> bool:
        key = (item["frame"].url, item["key"])

        if key in self.handled:
            return False

        if item["kind"] == "file":
            return False

        # LinkedIn reuses React controls between Easy Apply pages, so the
        # captured FORM_SCRIPT "filled" flag can be stale. Read the live DOM
        # before deciding that a field is already complete.
        if item.get("filled"):
            try:
                live_value = await self.read_field_value(item)
                if live_value.strip():
                    return False
            except Exception:
                pass

        review = review_field(item)
        if review["sensitive"]:
            self.sync_application("review", "sensitive_question", f"Sensitive field requires candidate review: {item['label']}.")
            options = [option["label"] for option in item["options"]]
            previous_value = await self.read_field_value(item)
            command = await self.run.pause(
                "sensitive_review",
                (
                    f"Review sensitive application question: {item['label']}. "
                    "The platform will not infer or silently answer this field. "
                    "Provide the candidate's factual answer or Resume to review it manually."
                ),
                ["answer", "resume", "skip"] if not item["required"] else ["answer", "resume"],
                question=item["label"],
                category=review["category"],
                options=options,
                current_value="filled" if item["filled"] else "",
                review_required=True,
            )
            if command.action == "resume":
                await self.remember_manual_field_value(item, previous_value)
                if item["filled"]:
                    self.handled.add(key)
                    self.run.log(f"Candidate reviewed existing sensitive field: {item['label']}")
                return True
            if command.action == "skip":
                self.handled.add(key)
                return True
            if command.action == "answer" and command.answer:
                if await self.fill(item, command.answer):
                    self.handled.add(key)
                    self.run.log(f"Candidate-reviewed field filled: {item['label']}")
                    return True
            return True

        spec = build_field_spec(item)
        answer = self.known_answer(item)
        if answer is None:
            answer = answer_from_profile(spec, self.profile)

        if answer is not None:
            if await self.fill(item, answer):
                self.handled.add(key)
                self.run.log(f"Filled: {item['label']}")
                return True

        options = [
            option["label"]
            for option in item["options"]
        ]

        proposal = answer

        explanation = (
            "The saved answer could not be matched to this control."
            if answer is not None
            else "Please provide a factual answer."
        )

        if answer is None and not item["required"]:
            # Unknown optional fields must never block the application.
            # Leave them untouched and continue to the next field.
            self.handled.add(key)
            self.run.log(
                f"Skipped optional field without a saved answer: {item['label']}"
            )
            return True

        if answer is None:
            self.run.log(
                f"Preparing an answer draft for: {item['label']}"
            )

            try:
                suggestion = await asyncio.to_thread(
                    suggest_answer,
                    self.profile,
                    item["label"],
                    options,
                    (await self.page_text())[:6000],
                )

                proposal = suggestion.answer
                explanation = suggestion.explanation

            except Exception as exc:
                explanation = (
                    f"Answer generation unavailable ({type(exc).__name__}). "
                    "Please answer manually."
                )

        allowed = ["answer", "resume"]

        if not item["required"]:
            allowed.append("skip")

        previous_value = await self.read_field_value(item)

        self.sync_application(
            "review",
            "human_input_required",
            f"Frontend answer required for application field: {item['label']}.",
        )

        command = await self.run.pause(
            "answer",
            f"Answer required: {item['label']}",
            allowed,
            question=item["label"],
            options=options,
            suggestion=proposal or "",
            explanation=explanation,
            required=item["required"],
            current_value=previous_value,
            category=review["category"],
        )

        if command.action == "skip":
            self.handled.add(key)

            self.run.log(
                f"Skipped optional field: {item['label']}"
            )
            return True

        if command.action == "resume":
            await self.settle()
            await self.remember_manual_field_value(item, previous_value)
            return True

        approved = command.answer or ""

        if not approved.strip():
            self.run.log(
                "An empty answer was not entered.",
                "warning",
            )
            return True

        if not await self.fill(item, approved):
            manual_previous_value = await self.read_field_value(item)
            self.sync_application(
                "review",
                "answer_retry_required",
                f"The browser control could not accept the proposed answer for: {item['label']}.",
            )
            retry_command = await self.run.pause(
                "answer",
                (
                    f"The browser control could not accept the answer for "
                    f"'{item['label']}'. Choose a valid option or enter a "
                    "different factual answer in the frontend."
                ),
                ["answer", "resume"],
                question=item["label"],
                options=options,
                suggestion="",
                explanation=(
                    "The first answer did not pass the control validation. "
                    "The browser remains paused while you provide another "
                    "answer."
                ),
                required=item["required"],
                current_value=manual_previous_value,
                category=review["category"],
            )

            if retry_command.action == "answer" and retry_command.answer:
                if await self.fill(item, retry_command.answer):
                    self.handled.add(key)
                    if retry_command.remember and self.run.request.profile_id:
                        remember_answer(
                            self.run.request.profile_id,
                            item["label"],
                            retry_command.answer,
                        )
                    self.run.log(
                        f"Filled retry answer from frontend: {item['label']}"
                    )
                    return True

            await self.settle()
            await self.remember_manual_field_value(item, manual_previous_value)
            return True

        self.handled.add(key)

        if command.remember and self.run.request.profile_id:
            normalized = normalize_question(item["label"])
            self.profile.custom_answers[normalized] = approved

            remember_answer(
                self.run.request.profile_id,
                item["label"],
                approved,
            )

        self.run.log(
            f"Filled approved answer: {item['label']}"
        )
        return True

    async def upload_resumes(self, fields: list[dict]) -> bool:
        files = [
            item
            for item in fields
            if item["kind"] == "file"
        ]

        changed = False

        for item in files:
            key = (item["frame"].url, item["key"])

            if item["filled"] or key in self.handled:
                continue

            description = (
                item["label"]
                + " "
                + item["meta"]
                + " "
                + item["accept"]
            ).lower()

            resume_field = bool(
                re.search(r"resume|résumé|\bcv\b", description)
            )

            other_document = bool(
                re.search(
                    r"cover.?letter|photo|image|certificate|transcript|"
                    r"passport|supporting|additional document",
                    description,
                )
            )

            accepted = item["accept"].lower()

            looks_document_compatible = (
                not accepted
                or "pdf" in accepted
                or "doc" in accepted
                or "application/" in accepted
                or accepted == "*"
            )

            if (
                not other_document
                and looks_document_compatible
                and (resume_field or len(files) == 1)
            ):
                upload_locator = self.locator(item)
                if self.dynamic_form:
                    resolved, _strategy = await self.dynamic_form.resolve(item)
                    if resolved is not None:
                        upload_locator = resolved
                await upload_locator.set_input_files(str(self.resume_path))

                self.handled.add(key)

                self.run.log(
                    f"Attached resume to: {item['label']}"
                )

                changed = True

            elif item["required"]:
                await self.run.pause(
                    "upload",
                    (
                        f"Upload the required document for '{item['label']}' "
                        "manually in the headed browser, then Resume."
                    ),
                    ["resume"],
                )

                await self.settle()
                return True

            else:
                self.handled.add(key)

                self.run.log(
                    "Left optional non-resume upload unchanged: "
                    f"{item['label']}"
                )

        return changed

    async def confirm_after_submission(self) -> None:
        # Never automatically click submit again when the result is uncertain.
        for _ in range(10):
            await self.settle()

            if await self.confirmed():
                self.run.status = "completed"

                self.run.log(
                    "The page displays an application confirmation."
                )
                return

            await asyncio.sleep(0.7)

        while True:
            command = await self.run.pause(
                "confirmation",
                (
                    "A submission was clicked, but no reliable confirmation "
                    "was recognized. Inspect the browser and any portal "
                    "receipt. Resume only re-checks confirmation; it never "
                    "submits again. Use Mark submitted only after "
                    "personally verifying success."
                ),
                ["resume", "mark_submitted"],
            )

            if command.action == "mark_submitted":
                self.run.status = "completed"

                self.run.log(
                    "Submission success was confirmed by the user."
                )
                return

            await self.settle()

            if await self.confirmed():
                self.run.status = "completed"

                self.run.log(
                    "The page now displays an application confirmation."
                )
                return

    async def linkedin_application_scope_ready(self) -> bool:
        """Return True only when LinkedIn's Easy Apply dialog is actually open."""
        if self.run.request.portal != "linkedin":
            return True

        try:
            dialogs = self.page.locator('[role="dialog"], dialog')
            count = await dialogs.count()

            for index in range(count):
                dialog = dialogs.nth(index)
                if not await dialog.is_visible():
                    continue

                text = (await dialog.inner_text()).strip()
                controls = await dialog.locator(
                    'input:not([type="hidden"]), select, textarea, '
                    '[role="combobox"], input[type="file"], button'
                ).count()

                # LinkedIn may render the modal before its controls finish
                # loading, so the dialog itself is sufficient to establish
                # application scope.
                if controls > 0 or text:
                    return True
        except Exception:
            return False

        return False

    async def find_linkedin_easy_apply_button(self) -> dict | None:
        """Find LinkedIn's Easy Apply control using a broader, page-specific scan."""
        pattern = re.compile(r"easy\s*apply", re.I)

        for frame in self.page.frames:
            try:
                candidates = await frame.evaluate(
                    """
                    () => {
                        const visible = el => {
                            const style = getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.visibility !== "hidden" &&
                                   style.display !== "none" &&
                                   rect.width > 0 &&
                                   rect.height > 0;
                        };

                        const clean = value =>
                            (value || "").replace(/\\s+/g, " ").trim();

                        const nodes = [
                            ...document.querySelectorAll(
                                'button, a, [role="button"], ' +
                                '[aria-label*="Easy Apply" i], ' +
                                '[data-control-name*="apply" i]'
                            )
                        ];

                        const seen = new Set();
                        return nodes
                            .filter(visible)
                            .map(el => {
                                if (!el.dataset.jobAgentId) {
                                    el.dataset.jobAgentId = crypto.randomUUID();
                                }

                                const text = clean(
                                    el.innerText ||
                                    el.getAttribute("aria-label") ||
                                    el.getAttribute("title") ||
                                    el.getAttribute("data-control-name") ||
                                    ""
                                );

                                return {
                                    key: el.dataset.jobAgentId,
                                    text
                                };
                            })
                            .filter(item => item.text)
                            .filter(item => {
                                if (seen.has(item.key)) return false;
                                seen.add(item.key);
                                return true;
                            });
                    }
                    """
                )

                for button in candidates:
                    if pattern.search(button["text"]):
                        button["frame"] = frame
                        return button
            except Exception:
                continue

        return None

    async def open_linkedin_easy_apply(self) -> bool:
        """Open Easy Apply before any application-field inspection."""
        if self.run.request.portal != "linkedin":
            return True

        if await self.linkedin_application_scope_ready():
            self.linkedin_easy_apply_open = True
            return True

        entry_button = await self.find_linkedin_easy_apply_button()

        if not entry_button:
            return False

        self.run.log(
            f"Clicking Easy Apply entry: {entry_button['text']}"
        )

        await self.locator(entry_button).click()
        await self.settle()

        for _ in range(10):
            if await self.linkedin_application_scope_ready():
                self.linkedin_easy_apply_open = True
                self.run.log(
                    "LinkedIn Easy Apply dialog opened. "
                    "Application-field inspection is now enabled."
                )
                return True
            await asyncio.sleep(0.4)

        return False

    async def apply(self) -> None:
        self.sync_application("opening", "opening", "Opening the job page for application preparation.")
        if self.profile is None or self.resume_path is None:
            raise ValueError(
                "Application mode requires a saved profile and resume."
            )

        for step in range(1, 151):
            await self.settle()
            await self.clear_obstacles()

            if await self.confirmed():
                self.run.status = "completed"

                self.run.log(
                    "A confirmation message is displayed on this page."
                )
                return

            # LinkedIn's job page contains many unrelated controls.
            # Never pass them through the application form analyzer. The
            # Easy Apply dialog must be opened first.
            if self.run.request.portal == "linkedin" and not self.linkedin_easy_apply_open:
                opened = await self.open_linkedin_easy_apply()

                if not opened:
                    await self.run.pause(
                        "navigation",
                        (
                            "LinkedIn Easy Apply has not been opened. "
                            "Open the Easy Apply form in the headed browser, "
                            "then Resume."
                        ),
                        ["resume"],
                        url=self.page.url,
                    )
                    continue

                continue

            if self.run.request.portal == "linkedin":
                if not await self.linkedin_application_scope_ready():
                    self.linkedin_easy_apply_open = False
                    continue

            self.run.log(
                f"Inspecting application step {step}."
            )
            self.sync_application("form_analysis", "form_analysis", "Analyzing the current application form.")

            fields = await self.fields()
            self.run.log(
                f"Form analyzer detected {len(fields)} editable field(s) on step {step}."
            )
            for field in fields:
                try:
                    live_value = await self.read_field_value(field)
                except Exception:
                    live_value = ""
                self.run.log(
                    f"Field: {field.get('label', '<unlabeled>')} | "
                    f"kind={field.get('kind')} | "
                    f"required={field.get('required')} | "
                    f"detected_filled={field.get('filled')} | "
                    f"live_filled={bool(live_value.strip())} | "
                    f"semantic={field.get('semantic', 'unknown')}"
                )

            self.update_application_review(fields)
            self.sync_application("filling", "fields_detected", "Application fields detected and classified for review.")
            await self.focus_first_application_field(fields)

            try:
                if await self.upload_resumes(fields):
                    continue

                changed = False

                for item in fields:
                    if await self.answer_field(item):
                        changed = True
                        break

                if changed:
                    continue

            except asyncio.TimeoutError:
                # Preserve the run manager's human-response expiry handling.
                raise

            except Exception as exc:
                self.run.log(
                    "A control changed or rejected input: "
                    f"{type(exc).__name__}.",
                    "warning",
                )

                await self.run.pause(
                    "widget",
                    (
                        "A field could not be completed reliably. "
                        "Inspect and correct it in the headed browser, "
                        "then Resume."
                    ),
                    ["resume"],
                )
                continue

            # Re-scan the live application controls before clicking
            # Next. Do not trust the earlier field snapshot for required
            # values on LinkedIn's reused React components.
            live_fields = await self.fields()
            unresolved_required = []
            for field in live_fields:
                if not field.get("required") or field.get("kind") == "file":
                    continue
                try:
                    value = await self.read_field_value(field)
                except Exception:
                    value = ""
                if not compact(value) or compact(value) in {
                    "select",
                    "select an option",
                    "choose",
                    "choose an option",
                }:
                    unresolved_required.append(field)

            if unresolved_required:
                field = unresolved_required[0]
                await self.run.pause(
                    "answer",
                    f"Required field needs an answer before continuing: {field['label']}",
                    ["answer", "resume"],
                    question=field["label"],
                    options=[
                        option.get("label", "")
                        for option in field.get("options", [])
                        if option.get("label")
                    ],
                    current_value="",
                    category=field.get("semantic", "application_field"),
                    required=True,
                    explanation=(
                        "This required field is still empty. The application "
                        "will not click Next until it has a value."
                    ),
                )
                continue

            if not fields:
                try:
                    visible_controls = await self.page.locator(
                        'dialog:visible input:not([type="hidden"]), '
                        'dialog:visible select, dialog:visible textarea, '
                        '[role="dialog"]:visible input:not([type="hidden"]), '
                        '[role="dialog"]:visible select, '
                        '[role="dialog"]:visible textarea'
                    ).count()
                except Exception:
                    visible_controls = 0

                if visible_controls:
                    await self.run.pause(
                        "form_analysis",
                        (
                            "The browser shows application controls, but the "
                            "form analyzer recognized none. The runner is "
                            "paused instead of clicking Next."
                        ),
                        ["resume"],
                        visible_control_count=visible_controls,
                    )
                    continue

            errors = await self.visible_errors()

            if errors:
                await self.run.pause(
                    "error",
                    (
                        "The page reports a validation error. "
                        "Correct it, then Resume."
                    ),
                    ["resume"],
                    errors=errors,
                )

                self.navigation_attempts.clear()
                continue

            next_button = None

            if self.run.request.portal == "linkedin":
                next_button = await self.find_linkedin_next_button()
                if next_button:
                    self.run.log(
                        f"LinkedIn step navigation detected before submission checks: {next_button['text']}"
                    )

            if next_button is None:
                next_button = await self.find_button(
                    self.button_pattern(
                        "next",
                        r"next|continue|review|save and continue|"
                        r"continue application|review application|next step"
                    )
                )

            if next_button:
                signature = (
                    self.page.url,
                    next_button["text"],
                    tuple(
                        (
                            item["label"],
                            item["kind"],
                            item["filled"],
                        )
                        for item in fields
                    ),
                )

                attempts = self.navigation_attempts.get(
                    signature,
                    0,
                )

                if attempts >= 4:
                    current_errors = await self.visible_errors()
                    if current_errors:
                        await self.run.pause(
                            "error",
                            (
                                "LinkedIn did not advance because the form "
                                "reported a validation error. Review it in "
                                "the frontend/browser and Resume."
                            ),
                            ["resume"],
                            errors=current_errors,
                        )
                    else:
                        await self.run.pause(
                            "error",
                            (
                                "The Next button was clicked, but the "
                                "application step did not change after "
                                "several navigation attempts."
                            ),
                            ["resume"],
                        )

                    self.navigation_attempts.clear()
                    continue

                self.navigation_attempts[signature] = attempts + 1

                self.run.log(
                    f"Clicking navigation: {next_button['text']}"
                )

                await self.locator(next_button).click()

                # LinkedIn transitions its Easy Apply dialog asynchronously.
                # Do not immediately compare the old field snapshot: the
                # next page may still be rendering. Wait for either the URL,
                # field set, or navigation button to change before rescanning.
                previous_url = self.page.url
                previous_labels = tuple(
                    (item["label"], item["kind"])
                    for item in fields
                )

                for _ in range(20):
                    await asyncio.sleep(0.25)

                    if self.page.url != previous_url:
                        self.run.log(
                            "Application URL changed after Next; rescanning."
                        )
                        break

                    current_errors = await self.visible_errors()
                    if current_errors:
                        self.run.log(
                            "Validation feedback appeared after Next; "
                            "rescanning before another click.",
                            "warning",
                        )
                        break

                    try:
                        refreshed_fields = await self.fields()
                        refreshed_labels = tuple(
                            (item["label"], item["kind"])
                            for item in refreshed_fields
                        )
                        if refreshed_labels != previous_labels:
                            self.run.log(
                                "LinkedIn application fields changed after "
                                "Next; rescanning the new step."
                            )
                            break
                    except Exception:
                        pass

                await self.settle()

                # LinkedIn reuses the same DOM nodes and data-job-agent-id
                # values across Easy Apply pages. Those IDs are only valid
                # for the current form step; retaining them in handled
                # causes later pages to be incorrectly skipped.
                self.handled.clear()

                continue

            self.update_application_review(fields, errors)
            blockers = submission_blockers(fields, errors, human_approved=True)
            if blockers:
                missing_required = [
                    item["label"] for item in fields
                    if item["required"] and not item["filled"] and item["kind"] != "file"
                ]
                if missing_required:
                    self.sync_application("missing_information", "missing_information", "Required application information is missing.")
                    await self.run.pause(
                        "missing_information",
                        "Required application fields are still incomplete. Complete them in the browser, then Resume.",
                        ["resume"],
                        missing_fields=missing_required,
                    )
                    continue

            if self.run.request.portal == "linkedin":
                # Never search the whole job page for a submit/apply button.
                # The underlying "Easy Apply" entry button can remain mounted
                # behind the dialog and is NOT a submission control.
                submit_button = None
                dialog_submit = self.page.locator(
                    "dialog:visible footer button, "
                    '[role="dialog"]:visible footer button'
                )
                for index in range(await dialog_submit.count()):
                    candidate = dialog_submit.nth(index)
                    if not await candidate.is_visible():
                        continue
                    state = await candidate.evaluate(
                        """el => ({
                            text: (el.innerText || el.textContent || '').trim(),
                            ariaDisabled: el.getAttribute('aria-disabled'),
                            disabled: !!el.disabled
                        })"""
                    )
                    submit_text = re.sub(r"\s+", " ", state["text"]).strip()
                    if (
                        state["ariaDisabled"] == "true"
                        or state["disabled"]
                        or re.fullmatch(
                            r"(?:Next|Continue|Review application|Save and continue)",
                            submit_text,
                            re.I,
                        )
                    ):
                        continue
                    if re.search(
                        r"^(?:Submit|Submit application|Send application|"
                        r"Complete application|Finish|Finish application|"
                        r"Submit my application)$",
                        submit_text,
                        re.I,
                    ):
                        key = await candidate.get_attribute("data-job-agent-id")
                        if not key:
                            key = str(uuid.uuid4())
                            await candidate.evaluate(
                                "(el, value) => el.setAttribute('data-job-agent-id', value)",
                                key,
                            )
                        submit_button = {
                            "key": key,
                            "text": submit_text,
                            "frame": self.page.main_frame,
                        }
                        break
            else:
                submit_button = await self.find_button(
                    self.button_pattern(
                        "submit",
                        r"submit|submit application|send application|"
                        r"complete application|finish|finish application|"
                        r"submit my application|apply|apply now",
                    )
                )

            if submit_button and fields:
                self.sync_application("awaiting_approval", "review_requested", "Application is ready for final human approval.")
                command = await self.run.pause(
                    "submit",
                    (
                        f"Ready to click '{submit_button['text']}'. "
                        "Review the entire application in the browser, "
                        "including pre-filled fields, consent, salary, "
                        "and eligibility. Approval authorizes this "
                        "submission click."
                    ),
                    ["approve", "resume"],
                    url=self.page.url,
                    button=submit_button["text"],
                )

                if command.action == "resume":
                    continue

                if self.submission_clicked:
                    raise RuntimeError(
                        "A second submission click was blocked."
                    )

                self.submission_clicked = True
                if self.run.application_id:
                    try:
                        application = get_application(self.run.application_id)
                        application.human_approved = True
                        application.status = "submitting"
                        record_event(application, "approved", "Human approval granted for the final submission click.")
                    except (FileNotFoundError, ValueError):
                        pass

                self.run.log(
                    "Clicking user-approved submission: "
                    f"{submit_button['text']}"
                )

                try:
                    await self.locator(submit_button).click()
                except Exception:
                    self.run.log(
                        "The submit click returned an error. Its result "
                        "is uncertain, so automatic retries are disabled.",
                        "warning",
                    )

                await self.confirm_after_submission()
                return

            entry_button = None if self.run.request.portal == "linkedin" else await self.find_button(
                r"easy apply|apply|apply now|apply for this job|"
                r"apply for job|start application|apply manually"
            )

            if entry_button:
                entry_key = (
                    self.page.url,
                    entry_button["text"],
                )

                if entry_key not in self.entry_clicks:
                    command = await self.run.pause(
                        "navigation",
                        (
                            f"The next action is '{entry_button['text']}'. "
                            "Some portals, especially Naukri, may immediately "
                            "submit when Apply is clicked. Approve only if "
                            "you authorize that possibility, or open the "
                            "form manually and click Resume."
                        ),
                        ["approve", "resume"],
                        url=self.page.url,
                    )

                    if command.action == "approve":
                        self.entry_clicks.add(entry_key)

                        self.run.log(
                            "Clicking user-approved entry: "
                            f"{entry_button['text']}"
                        )

                        await self.locator(entry_button).click()

                    continue

            command = await self.run.pause(
                "navigation",
                (
                    "No supported next-step or submission control was "
                    "found. Open the application, resolve an unsupported "
                    "widget, or navigate to the next step manually, then "
                    "Resume. You may also mark the application submitted "
                    "after verifying a receipt."
                ),
                ["resume", "mark_submitted"],
                url=self.page.url,
            )

            if command.action == "mark_submitted":
                self.run.status = "completed"

                self.run.log(
                    "Submission success was confirmed by the user."
                )
                return

        raise RuntimeError(
            "The application exceeded the 150-step safety limit."
        )