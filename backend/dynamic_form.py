import asyncio
from dataclasses import dataclass

from playwright.async_api import Frame, Locator


@dataclass(frozen=True)
class LocatorCandidate:
    strategy: str
    locator: Locator


class DynamicFormExecutor:
    """Resilient interaction layer for native and ARIA-based form controls."""

    def __init__(self, page, log=None):
        self.page = page
        self.log = log or (lambda message, level="info": None)

    def candidates(self, item: dict) -> list[LocatorCandidate]:
        frame: Frame = item["frame"]
        label = (item.get("label") or "").strip()
        key = item.get("key")
        candidates = []

        if key:
            candidates.append(LocatorCandidate("agent-id", frame.locator(f'[data-job-agent-id="{key}"]')))

        if label:
            candidates.append(LocatorCandidate("label", frame.get_by_label(label, exact=False)))
            candidates.append(LocatorCandidate("role", frame.get_by_role(
                {"checkbox": "checkbox", "radio": "radio", "combobox": "combobox"}.get(item.get("kind"), "textbox"),
                name=label,
                exact=False,
            )))

        meta = item.get("meta", "")
        for value in [meta, item.get("placeholder", "")]:
            if value:
                candidates.append(LocatorCandidate("attribute", frame.locator(
                    f'input[placeholder="{value}"], textarea[placeholder="{value}"], '
                    f'input[name="{value}"], textarea[name="{value}"]'
                )))

        return candidates

    async def resolve(self, item: dict) -> tuple[Locator | None, str]:
        for candidate in self.candidates(item):
            try:
                if await candidate.locator.count() == 1 and await candidate.locator.first.is_visible():
                    return candidate.locator.first, candidate.strategy
            except Exception:
                continue
        return None, "none"

    async def fill_text(self, item: dict, answer: str) -> bool:
        locator, strategy = await self.resolve(item)
        if locator is None:
            return False
        try:
            await locator.fill(answer)
            await locator.press("Tab")
            await asyncio.sleep(0.15)
            valid = await locator.evaluate("el => el.validity ? el.validity.valid : true")
            if valid:
                self.log(f"Dynamic executor filled {item.get('label', '')} via {strategy}.")
            return bool(valid)
        except Exception:
            return False

    async def choose(self, item: dict, answer: str, chooser) -> bool:
        locator, strategy = await self.resolve(item)
        if locator is None:
            return False
        try:
            await locator.click()
            await asyncio.sleep(0.2)
            option = chooser(answer, item.get("options", []))
            if option:
                option_locator = item["frame"].get_by_role("option", name=option["label"], exact=True)
                if await option_locator.count() == 1 and await option_locator.first.is_visible():
                    await option_locator.first.click()
                    self.log(f"Dynamic executor selected {item.get('label', '')} via {strategy}.")
                    return True
        except Exception:
            pass
        return False

    async def settle_and_rescan(self, fields_fn, rounds: int = 3) -> list[dict]:
        fields = []
        previous = set()
        for _ in range(rounds):
            await asyncio.sleep(0.2)
            fields = await fields_fn()
            current = {(item["frame"].url, item["key"]) for item in fields}
            if current == previous:
                break
            previous = current
        return fields
