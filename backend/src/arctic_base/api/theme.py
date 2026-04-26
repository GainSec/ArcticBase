from typing import Annotated

from fastapi import APIRouter, Body, Depends, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from arctic_base.api.deps import get_storage
from arctic_base.models import Theme
from arctic_base.storage.filesystem import FilesystemStorage

router = APIRouter(prefix="/workbenches/{slug}/theme", tags=["theme"])


class ThemeRawBody(BaseModel):
    raw: str


@router.get("", response_model=Theme, operation_id="getTheme")
def get_theme(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Theme:
    return storage.get_theme(slug)


@router.get("/raw", response_class=PlainTextResponse, operation_id="getThemeRaw")
def get_theme_raw(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> str:
    return storage.get_theme_raw(slug)


_THEME_RAW_EXAMPLE = (
    "---\n"
    "name: Red X — Xenothium\n"
    "core:\n"
    "  bg: '#08070b'\n"
    "  surface: '#15121a'\n"
    "  ink: '#f5f5f5'\n"
    "  muted: '#9c9ca6'\n"
    "  rule: '#2a2530'\n"
    "  accent: '#e80000'\n"
    "  accent-2: '#3df58a'\n"
    "  success: '#3df58a'\n"
    "  error: '#ff2436'\n"
    "typography:\n"
    "  body: { fontFamily: 'Rubik, sans-serif', fontSize: '15px', lineHeight: '1.55' }\n"
    "  mono: { fontFamily: 'JetBrains Mono, monospace', fontSize: '13px', lineHeight: '1.4' }\n"
    "rounded: { sm: '0.25rem', md: '0.375rem', lg: '0.5rem' }\n"
    "spacing: { unit: '8px', gutter: '20px', margin: '28px' }\n"
    "custom:\n"
    "  red-x: '#e80000'\n"
    "layout:\n"
    "  density: compact\n"
    "  corners: sharp\n"
    "  shadow: glow\n"
    "  card-style: inset\n"
    "  motif: hex\n"
    "  banner-shape: t-shape\n"
    "  hero-style: cover\n"
    "---\n\n"
    "# Red X / Xenothium\n\n"
    "Anti-hero monochrome. Sharp corners, recessed inset cards, glow shadows.\n"
)


@router.put(
    "",
    response_model=Theme,
    status_code=200,
    operation_id="putTheme",
    summary="Replace a workbench's theme.md",
    description=(
        "Replace the workbench's theme.md (YAML frontmatter + Markdown prose). "
        "**The `raw` field's format is documented at `/api/agent/conventions`** — "
        "required `core` token names, layout enum values, typography keys, and "
        "the round-trip pattern (GET `/theme/raw` → edit → PUT `/theme`)."
    ),
)
def put_theme(
    slug: str,
    body: Annotated[
        ThemeRawBody,
        Body(
            description=(
                "Wraps the raw theme.md bytes. See `/api/agent/conventions` "
                "for the YAML-frontmatter + prose format."
            ),
            openapi_examples={"default": {"value": {"raw": _THEME_RAW_EXAMPLE}}},
        ),
    ],
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Theme:
    return storage.put_theme(slug, body.raw)


@router.get("/assets", response_model=list[str], operation_id="listThemeAssets")
def list_theme_assets(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> list[str]:
    return storage.list_theme_assets(slug)


@router.get("/assets/{path:path}", response_class=Response, operation_id="getThemeAsset")
def get_theme_asset(
    slug: str,
    path: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    data, etag = storage.get_theme_asset(slug, path)
    headers = {"ETag": etag}
    return Response(content=data, headers=headers)


@router.put("/assets/{path:path}", status_code=204, operation_id="putThemeAsset")
async def put_theme_asset(
    slug: str,
    path: str,
    upload: UploadFile,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    data = await upload.read()
    storage.put_theme_asset(slug, path, data)
    return Response(status_code=204)


@router.delete("/assets/{path:path}", status_code=204, operation_id="deleteThemeAsset")
def delete_theme_asset(
    slug: str,
    path: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    storage.delete_theme_asset(slug, path)
    return Response(status_code=204)
