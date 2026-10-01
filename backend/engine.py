import asyncio
import sys
from urllib.parse import (
    parse_qsl,
    quote,
    urlencode,
    urlparse,
    urlunparse,
)

from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from backend.config import BROWSER_DIR, ENABLE_STEALTH
from backend.engine_base import (
    Engine as BaseEngine,
    Run,
    start_url as base_start_url,
    validate_public_url,
)
from backend.models import RunRequest
from backend.portals import get_adapter

__all__ = [
    "Engine",
    "Run",
    "start_url",
    "validate_public_url",
]

NAVIGATION_WAIT_SECONDS = 20
AUTH_RETRY_DELAY_SECONDS = 2

AUTH_PATHS = (
    "/authwall",
    "/login",
    "/signin",
    "/sign-in",
    "/checkpoint",
)

LINKEDIN_WORKPLACE_CODES = {
    "onsite": "1",
    "remote": "2",
    "hybrid": "3",
}

def is_linkedin_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")

        return (
            parsed.scheme == "https"
            and (
                host == "linkedin.com"
                or host.endswith(".linkedin.com")
            )
        )
    except ValueError:
        return False

def is_linkedin_auth_page(value: str) -> bool:
    if not is_linkedin_url(value):
        return False

    path = urlparse(value).path.lower().rstrip("/")

    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in AUTH_PATHS
    )

def start_url(request: RunRequest) -> str:
    """Resolve the target URL through the selected portal adapter."""
    if request.mode == "discover":
        adapter = get_adapter(request.portal, request)
        target = adapter.build_discovery_url(request)
        if target:
            return target

    return base_start_url(request)

def enter_url_using_desktop_keyboard(url: str) -> None:
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError(
            "PyAutoGUI is missing. Install it with: "
            'python -m pip install "PyAutoGUI>=0.9.54,<1.0"'
        ) from exc

    keyboard_url = quote(
        url,
        safe=":/?#[]@!$&'()*+,;=%",
    )

    modifier = "command" if sys.platform == "darwin" else "ctrl"

    pyautogui.FAILSAFE = True
    pyautogui.hotkey(modifier, "l")
    pyautogui.sleep(0.2)
    pyautogui.press("backspace")
    pyautogui.write(keyboard_url, interval=0.003)
    pyautogui.press("enter")

class Engine(BaseEngine):
    @property
    def automatic_linkedin_discovery(self) -> bool:
        return (
            self.run.request.portal == "linkedin"
            and self.run.request.mode == "discover"
        )

    async def execute(self) -> None:
        request = self.run.request
        adapter = get_adapter(request.portal, request)
        target = await validate_public_url(start_url(request))

        if not adapter.accepts_url(target):
            raise ValueError(
                f"The target URL is not supported by the {request.portal} adapter."
            )

        self.run.log(
            f"Using portal adapter: {adapter.capabilities.display_name}"
        )

        browser_directory = BROWSER_DIR / request.portal
        browser_directory.mkdir(parents=True, exist_ok=True)

        # Discovery includes human review of the actual portal filters.
        effective_headless = request.headless

        if request.mode == "discover":
            effective_headless = False

            if request.headless:
                self.run.log(
                    "Headless mode overridden: discovery requires "
                    "visible location-filter confirmation.",
                    "warning",
                )

        async with async_playwright() as playwright:
            self.run.log(
                f"Launching "
                f"{'headless' if effective_headless else 'headed'} "
                f"Chromium with persistent {request.portal} session."
            )

            self.context = (
                await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(browser_directory),
                    headless=effective_headless,
                    viewport={"width": 1440, "height": 1000},
                    locale="en-US",
                    accept_downloads=False,
                )
            )

            try:
                if ENABLE_STEALTH:
                    from playwright_stealth import Stealth

                    await Stealth().apply_stealth_async(self.context)

                    self.run.log(
                        "Optional browser compatibility adjustments enabled."
                    )

                self.context.set_default_timeout(8000)
                self.context.set_default_navigation_timeout(45000)

                self.page = await self.context.new_page()

                for old_page in list(self.context.pages):
                    if old_page != self.page:
                        await old_page.close()

                self.run.status = "running"

                if request.mode == "discover":
                    self.run.log(
                        f"Requested search location: "
                        f"{request.search_location.strip()}"
                    )
                    self.run.log(
                        f"Requested workplace type: {request.workplace_type}"
                    )

                if self.automatic_linkedin_discovery:
                    self.run.log(f"Location-aware search URL: {target}")

                    await self.prepare_linkedin_discovery(target)
                    await self.confirm_search_filters()
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
                        "Navigation timed out; inspecting the loaded page.",
                        "warning",
                    )

                await self.settle()
                self.run.log(f"Browser landed on: {self.page.url}")

                if request.mode == "login":
                    await self.run.pause(
                        "login",
                        (
                            "Complete login and MFA manually, then click "
                            "Resume. The browser session will be retained."
                        ),
                        ["resume"],
                    )

                    self.run.status = "completed"
                    self.run.log(
                        "Session setup finished; persistent state retained."
                    )
                    return

                if request.mode == "discover":
                    await self.clear_obstacles()
                    await self.confirm_search_filters()
                    await self.discover()
                    return

                await self.apply()

            finally:
                if self.context:
                    await self.context.close()

    async def navigate_through_address_bar(
        self,
        target: str,
    ) -> None:
        if self.page is None or self.page.is_closed():
            raise RuntimeError("The browser window is unavailable.")

        await validate_public_url(target)

        if not is_linkedin_url(target):
            raise ValueError(
                "Address-bar automation is restricted to LinkedIn."
            )

        await self.page.bring_to_front()

        self.run.log(
            "Entering the location-aware search URL in the address bar. "
            "Do not type or switch windows."
        )

        await asyncio.sleep(0.8)

        try:
            await asyncio.to_thread(
                enter_url_using_desktop_keyboard,
                target,
            )
        except Exception as exc:
            raise RuntimeError(
                "Desktop address-bar navigation failed. "
                "Keep Chromium visible and check desktop permissions. "
                f"Error type: {type(exc).__name__}."
            ) from exc

        await asyncio.sleep(1.5)

    async def wait_for_linkedin_destination(self) -> str:
        deadline = (
            asyncio.get_running_loop().time()
            + NAVIGATION_WAIT_SECONDS
        )
        auth_observations = 0

        while asyncio.get_running_loop().time() < deadline:
            await self.settle()

            if self.page is None or self.page.is_closed():
                raise RuntimeError("The browser was closed.")

            current_url = self.page.url

            if is_linkedin_auth_page(current_url):
                auth_observations += 1

                if auth_observations >= 2:
                    return "auth"

                continue

            auth_observations = 0

            if not is_linkedin_url(current_url):
                continue

            if await self.challenge_present():
                return "challenge"

            if await self.linkedin_job_links_visible():
                return "results"

            await asyncio.sleep(0.5)

        return "unknown"

    async def prepare_linkedin_discovery(
        self,
        target: str,
    ) -> None:
        try:
            await self.navigate_through_address_bar(target)
            destination = await self.wait_for_linkedin_destination()

            self.run.log(
                f"First navigation landed on: {self.page.url}"
            )

            if destination == "results":
                self.run.log("Job listings detected.")
                return

            if destination == "auth":
                current_path = (
                    urlparse(self.page.url).path.lower().rstrip("/")
                )

                if (
                    current_path == "/authwall"
                    or current_path.startswith("/authwall/")
                ):
                    self.run.log(
                        "Authentication wall detected. Entering the same "
                        "location-aware URL once more.",
                        "warning",
                    )

                    await asyncio.sleep(AUTH_RETRY_DELAY_SECONDS)
                    await self.navigate_through_address_bar(target)

                    destination = (
                        await self.wait_for_linkedin_destination()
                    )

                    self.run.log(
                        f"Second navigation landed on: {self.page.url}"
                    )

                    if destination == "results":
                        self.run.log(
                            "Job listings detected after the second navigation."
                        )
                        return

        except Exception as exc:
            self.run.log(str(exc), "warning")

        await self.wait_for_manual_search_page(target)

    async def wait_for_manual_search_page(
        self,
        target: str,
    ) -> None:
        while True:
            await self.run.pause(
                "navigation",
                (
                    "Accessible job listings were not verified. Automatic "
                    "navigation retries are finished. If public search is "
                    "available, open the location-aware URL shown below "
                    "in this browser and click Resume. Otherwise stop the run."
                ),
                ["resume"],
                url=target,
            )

            await self.settle()
            current_url = self.page.url

            self.run.log(f"Inspecting current page: {current_url}")

            if not is_linkedin_url(current_url):
                self.run.log(
                    "The current tab is not an HTTPS LinkedIn page.",
                    "warning",
                )
                continue

            if is_linkedin_auth_page(current_url):
                self.run.log(
                    "Authentication is still required. "
                    "No further automatic navigation will be attempted.",
                    "warning",
                )
                continue

            if await self.challenge_present():
                self.run.log(
                    "An access challenge remains. Resolve it manually "
                    "if you wish, or stop the run.",
                    "warning",
                )
                continue

            if await self.linkedin_job_links_visible():
                return

            if urlparse(current_url).path.lower().startswith(
                "/jobs/search"
            ):
                return

    async def confirm_search_filters(self) -> None:
        """
        Portal URL parameters are requests, not proof that filters applied.
        Require explicit confirmation of the visible search filters.
        """
        request = self.run.request
        location = request.search_location.strip()
        workplace = request.workplace_type

        if request.portal == "linkedin":
            instructions = (
                f"The search URL requests location '{location}' and "
                f"workplace type '{workplace}'. Verify the visible LinkedIn "
                "location and workplace filters. If LinkedIn ignored or "
                "changed them, correct them in the browser. Click Resume "
                "only when the filters match your intended search. "
                "Use Stop if the requested filter is unavailable."
            )
        else:
            instructions = (
                f"Set this portal's search location to '{location}' and "
                f"workplace type to '{workplace}' where supported. "
                "Naukri and employer ATS filter controls differ, so the "
                "engine does not guess them. Apply the filters manually, "
                "wait for results, then click Resume. If the portal cannot "
                "filter as requested, stop the run rather than collecting "
                "unfiltered results."
            )

        while True:
            await self.run.pause(
                "navigation",
                instructions,
                ["resume"],
                url=self.page.url,
            )

            await self.settle()
            await validate_public_url(self.page.url)

            if self.automatic_linkedin_discovery:
                if not is_linkedin_url(self.page.url):
                    self.run.log(
                        "Return to LinkedIn search before confirming.",
                        "warning",
                    )
                    continue

                if is_linkedin_auth_page(self.page.url):
                    await self.wait_for_manual_search_page(
                        start_url(request)
                    )
                    continue

            if await self.challenge_present():
                self.run.log(
                    "An access challenge is present. Resolve it manually "
                    "or stop the run.",
                    "warning",
                )
                continue

            if await self.login_present():
                self.run.log(
                    "A login screen is present. Return to accessible "
                    "search results or stop the run.",
                    "warning",
                )
                continue

            self.run.log(
                f"User confirmed search filters: location={location}; "
                f"workplace={workplace}."
            )
            return

    async def clear_obstacles(self) -> None:
        if not self.automatic_linkedin_discovery:
            await super().clear_obstacles()
            return

        # Keep manual recovery URLs location-aware even when discovery
        # encounters an obstacle after initial navigation.
        while True:
            if await self.challenge_present():
                await self.run.pause(
                    "challenge",
                    (
                        "An access challenge was detected. Resolve it "
                        "manually if you wish, then Resume, or stop the run."
                    ),
                    ["resume"],
                )
                await self.settle()
                continue

            if await self.login_present():
                await self.wait_for_manual_search_page(
                    start_url(self.run.request)
                )
                await self.confirm_search_filters()
                continue

            return