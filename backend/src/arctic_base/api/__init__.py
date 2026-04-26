from fastapi import APIRouter

from arctic_base.api import agent, objects, render, responses, theme, workbenches

router = APIRouter(prefix="/api")
router.include_router(workbenches.router)
router.include_router(theme.router)
router.include_router(objects.router)
router.include_router(responses.router)
router.include_router(render.router)
router.include_router(agent.router)  # mounts /api/agent/*

# Root-level /agent → /openapi.json redirect, registered on the app separately.
agent_top = agent.top_router

__all__ = ["router", "agent_top"]
