import logging
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from arctic_base import __version__
from arctic_base.api import agent_top, router as api_router
from arctic_base.api.errors import install_error_handlers
from arctic_base.config import get_settings
from arctic_base.logging_setup import RequestIdMiddleware, configure_logging


def _seed_if_empty(data: Path, seed: Path) -> None:
    """Copy seed/workbenches into data/workbenches on a fresh install.

    Triggered only when data/workbenches is missing or empty — never overwrites
    an existing deployment. Safe to call on every startup.
    """
    if not seed.is_dir():
        return
    src = seed / "workbenches"
    if not src.is_dir():
        return
    dst = data / "workbenches"
    # If dst has any subdirs already, treat the install as initialised and skip.
    if dst.is_dir() and any(p.is_dir() for p in dst.iterdir()):
        return
    dst.mkdir(parents=True, exist_ok=True)
    for wb in src.iterdir():
        if wb.is_dir():
            shutil.copytree(wb, dst / wb.name, dirs_exist_ok=True)
    logging.getLogger("arctic_base").info("seeded data dir from %s", src)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    _seed_if_empty(settings.data, settings.seed_data)
    app = FastAPI(
        title="Arctic Base",
        version=__version__,
        description="Self-hosted workbench host for AI agents.",
    )
    app.add_middleware(RequestIdMiddleware)

    install_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.include_router(api_router)
    # Mount /agent (root-level redirect) AFTER /api/agent/* and BEFORE the SPA catch-all,
    # so the agent landing route resolves before the SPA fallback handler.
    app.include_router(agent_top)

    # Redirect common typos to the real workbench route. Independent of whether
    # the SPA is mounted — agents/scripts hitting these should always be helped.
    @app.get("/workbench/{slug:path}", include_in_schema=False)
    @app.get("/workbenches/{slug:path}", include_in_schema=False)
    def _wb_typo_redirect(slug: str) -> RedirectResponse:
        return RedirectResponse(url=f"/wb/{slug}", status_code=302)

    dist = settings.frontend_dist.resolve()
    if dist.is_dir():
        assets_dir = dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="spa-assets")

        @app.get("/", include_in_schema=False, response_model=None)
        def root_index():
            return FileResponse(dist / "index.html")

        @app.get("/{spa_path:path}", include_in_schema=False, response_model=None)
        def spa_fallback(spa_path: str):
            if spa_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = dist / spa_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
