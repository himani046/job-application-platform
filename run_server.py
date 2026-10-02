"""Windows-safe local API launcher.

Use this instead of `uvicorn backend.app:app --reload` when running
Playwright automation on Windows. Uvicorn's reload supervisor may install
WindowsSelectorEventLoopPolicy, while Playwright requires subprocess support.
"""

import asyncio
import sys

import uvicorn


def configure_event_loop() -> None:
    if sys.platform == "win32":
        policy = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if policy is not None:
            asyncio.set_event_loop_policy(policy())


if __name__ == "__main__":
    configure_event_loop()
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
