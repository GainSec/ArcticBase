"""Entry point: `python -m arctic_base` or the `arctic-base` console script.

Reads host/port from settings (env-driven) so the default is 0.0.0.0:2929 — listening on all
interfaces, no flags required.
"""

from __future__ import annotations

import uvicorn

from arctic_base.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "arctic_base.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,  # use our JSON formatter installed by configure_logging()
    )


if __name__ == "__main__":
    main()
