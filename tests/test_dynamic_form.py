import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.dynamic_form import DynamicFormExecutor


class DynamicFormTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_prefers_agent_id(self):
        page = MagicMock()
        executor = DynamicFormExecutor(page)
        first = MagicMock()
        first.count = AsyncMock(return_value=1)
        first.first.is_visible = AsyncMock(return_value=True)

        executor.candidates = lambda item: [
            type("Candidate", (), {"strategy": "agent-id", "locator": first})(),
        ]

        locator, strategy = await executor.resolve({
            "key": "field-1",
            "label": "First Name",
            "kind": "text",
            "frame": MagicMock(),
        })
        self.assertIs(locator, first.first)
        self.assertEqual(strategy, "agent-id")

    async def test_resolve_falls_back_when_first_locator_fails(self):
        page = MagicMock()
        executor = DynamicFormExecutor(page)
        broken = MagicMock()
        broken.count = AsyncMock(side_effect=RuntimeError("stale"))
        working = MagicMock()
        working.count = AsyncMock(return_value=1)
        working.first.is_visible = AsyncMock(return_value=True)

        executor.candidates = lambda item: [
            type("Candidate", (), {"strategy": "stale", "locator": broken})(),
            type("Candidate", (), {"strategy": "role", "locator": working})(),
        ]

        locator, strategy = await executor.resolve({"key": "x", "label": "Email", "kind": "text", "frame": MagicMock()})
        self.assertIs(locator, working.first)
        self.assertEqual(strategy, "role")


if __name__ == "__main__":
    unittest.main()
