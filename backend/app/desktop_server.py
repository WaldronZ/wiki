from __future__ import annotations

import os

import uvicorn


def main() -> None:
    os.environ.setdefault("AUTOPAPER_DESKTOP", "1")
    uvicorn.run(
        "backend.app.main:app",
        host=os.environ.get("AUTOPAPER_HOST", "127.0.0.1"),
        port=int(os.environ.get("AUTOPAPER_PORT", "8765")),
        log_level=os.environ.get("AUTOPAPER_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
