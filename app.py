from __future__ import annotations

import uvicorn

from cuny_tracker.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "cuny_tracker.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
