"""Windows-safe launcher for the FastAPI + Playwright backend.

Playwright's async driver needs a Proactor event loop on Windows. In
particular, do not use Uvicorn's --reload mode for this backend: the reload
process can create a SelectorEventLoop, which makes Playwright subprocess
startup fail with NotImplementedError.
"""
import asyncio
import sys

if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
